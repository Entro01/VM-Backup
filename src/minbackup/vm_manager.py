"""VM snapshot management for multiple virtualization platforms."""

import subprocess
import json
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any, Optional

from .utils import NotificationManager, generate_timestamp, is_command_available


class VMPlatform(ABC):
    """Abstract base class for VM platform implementations."""
    
    def __init__(self, config, notifier: NotificationManager):
        self.config = config
        self.notifier = notifier
        self.timeout = config.get(f'vm.{self.platform_name}.timeout', 300)
    
    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return platform name."""
        pass
    
    @property
    @abstractmethod
    def command_name(self) -> str:
        """Return command name for platform."""
        pass
    
    @abstractmethod
    def list_vms(self) -> List[Dict[str, Any]]:
        """List available VMs."""
        pass
    
    @abstractmethod
    def create_snapshot(self, vm_name: str, snapshot_name: str) -> bool:
        """Create VM snapshot."""
        pass
    
    @abstractmethod
    def list_snapshots(self, vm_name: str) -> List[Dict[str, Any]]:
        """List VM snapshots."""
        pass
    
    @abstractmethod
    def delete_snapshot(self, vm_name: str, snapshot_name: str, purge: bool = True) -> bool:
        """Delete VM snapshot."""
        pass
    
    def is_available(self) -> bool:
        """Check if platform is available."""
        return is_command_available(self.command_name)
    
    def _run_command(self, command: List[str]) -> subprocess.CompletedProcess:
        """Run command with timeout and error handling."""
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False
            )
            return result
        except subprocess.TimeoutExpired:
            self.notifier.error(f"Command timeout: {' '.join(command)}")
            raise
        except Exception as e:
            self.notifier.error(f"Command execution failed: {str(e)}")
            raise


class MultipassPlatform(VMPlatform):
    """Multipass VM platform implementation using real snapshot functionality."""
    
    @property
    def platform_name(self) -> str:
        return "multipass"
    
    @property
    def command_name(self) -> str:
        return "multipass"
    
    def _generate_valid_snapshot_name(self, custom_name: Optional[str] = None) -> str:
        """Generate a valid Multipass snapshot name."""
        if custom_name:
            # Sanitize custom name
            sanitized = custom_name.lower()
            sanitized = re.sub(r'[^a-z0-9-]', '-', sanitized)
            sanitized = re.sub(r'-+', '-', sanitized)
            sanitized = sanitized.strip('-')
            
            if not sanitized or not sanitized[0].isalpha():
                sanitized = f"backup-{sanitized}" if sanitized else "backup"
            
            return sanitized
        else:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            return f"minbackup-{timestamp}"
    
    def list_vms(self) -> List[Dict[str, Any]]:
        """List Multipass VMs."""
        try:
            result = self._run_command(["multipass", "list", "--format", "json"])
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return [
                    {
                        "name": vm["name"],
                        "state": vm["state"],
                        "platform": self.platform_name
                    }
                    for vm in data.get("list", [])
                ]
            else:
                self.notifier.error(f"Failed to list VMs: {result.stderr}")
                return []
        except Exception as e:
            self.notifier.error(f"Error listing VMs: {str(e)}")
            return []
    
    def create_snapshot(self, vm_name: str, snapshot_name: str) -> bool:
        """Create Multipass snapshot using native snapshot functionality."""
        try:
            vm_info = self._get_vm_info(vm_name)
            if not vm_info:
                self.notifier.error(f"VM '{vm_name}' not found")
                return False
            
            valid_snapshot_name = self._generate_valid_snapshot_name(snapshot_name)
            if valid_snapshot_name != snapshot_name:
                self.notifier.info(f"Adjusted snapshot name from '{snapshot_name}' to '{valid_snapshot_name}'")
            
            if vm_info["state"] == "Running":
                self.notifier.info(f"Stopping VM '{vm_name}' for snapshot...")
                stop_result = self._run_command(["multipass", "stop", vm_name])
                if stop_result.returncode != 0:
                    self.notifier.error(f"Failed to stop VM: {stop_result.stderr}")
                    return False
                self.notifier.info(f"VM '{vm_name}' stopped successfully")
            elif vm_info["state"] != "Stopped":
                self.notifier.error(f"VM '{vm_name}' is in '{vm_info['state']}' state. Only stopped VMs can be snapshotted.")
                return False
            
            self.notifier.info(f"Creating snapshot '{valid_snapshot_name}' for VM '{vm_name}'...")
            
            snapshot_result = self._run_command([
                "multipass", "snapshot", vm_name, 
                "--name", valid_snapshot_name,
                "--comment", f"MinBackup snapshot created at {datetime.now().isoformat()}"
            ])
            
            if snapshot_result.returncode == 0:
                self.notifier.success(f"Created snapshot '{valid_snapshot_name}' for VM '{vm_name}'")
                return True
            else:
                self.notifier.error(f"Failed to create snapshot: {snapshot_result.stderr}")
                
                if "comment" in snapshot_result.stderr.lower() or "invalid" in snapshot_result.stderr.lower():
                    self.notifier.info("Retrying without comment...")
                    retry_result = self._run_command([
                        "multipass", "snapshot", vm_name, "--name", valid_snapshot_name
                    ])
                    if retry_result.returncode == 0:
                        self.notifier.success(f"Created snapshot '{valid_snapshot_name}' for VM '{vm_name}'")
                        return True
                    else:
                        self.notifier.error(f"Retry also failed: {retry_result.stderr}")
                
                return False
                
        except Exception as e:
            self.notifier.error(f"Error creating snapshot: {str(e)}")
            return False
    
    def _get_vm_info(self, vm_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific VM."""
        vms = self.list_vms()
        for vm in vms:
            if vm["name"] == vm_name:
                return vm
        return None
    
    def list_snapshots(self, vm_name: str) -> List[Dict[str, Any]]:
        """List Multipass snapshots for a specific VM."""
        try:
            result = self._run_command(["multipass", "list", "--snapshots"])
            
            if result.returncode != 0:
                self.notifier.error(f"Failed to list snapshots: {result.stderr}")
                return []
            
            snapshots = []
            lines = result.stdout.strip().split('\n')
            
            if lines and ("Instance" in lines[0] and "Snapshot" in lines[0]):
                lines = lines[1:]
            
            for line in lines:
                if line.strip():
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        instance_name = parts[0]
                        snapshot_name = parts[1]
                        
                        if instance_name == vm_name:
                            comment = ""
                            if len(parts) > 3:
                                comment = " ".join(parts[3:])
                            
                            # Extract creation timestamp from comment if available
                            created_at = comment if comment and comment != "--" else "unknown"
                            
                            # Try to parse ISO timestamp from comment
                            timestamp = None
                            if "MinBackup snapshot created at" in comment:
                                try:
                                    # Extract timestamp after "at "
                                    timestamp_str = comment.split("at ")[-1].split("…")[0]
                                    timestamp = datetime.fromisoformat(timestamp_str.replace("â€¦", ""))
                                except:
                                    timestamp = None
                            
                            snapshots.append({
                                "name": snapshot_name,
                                "vm_name": vm_name,
                                "created_at": created_at,
                                "timestamp": timestamp,
                                "platform": self.platform_name
                            })
            
            return snapshots
            
        except Exception as e:
            self.notifier.error(f"Error listing snapshots: {str(e)}")
            return []
    
    def delete_snapshot(self, vm_name: str, snapshot_name: str, purge: bool = True) -> bool:
        """Delete Multipass snapshot with proper two-step process."""
        try:
            snapshot_identifier = f"{vm_name}.{snapshot_name}"
            
            self.notifier.info(f"Deleting snapshot '{snapshot_name}' for VM '{vm_name}'...")
            
            if purge:
                delete_result = self._run_command([
                    "multipass", "delete", snapshot_identifier, "--purge"
                ])
                
                if delete_result.returncode == 0:
                    self.notifier.success(f"Deleted and purged snapshot '{snapshot_name}' for VM '{vm_name}'")
                    return True
                else:
                    self.notifier.error(f"Failed to delete snapshot: {delete_result.stderr}")
                    return False
            else:
                delete_result = self._run_command([
                    "multipass", "delete", snapshot_identifier
                ])
                
                if delete_result.returncode == 0:
                    self.notifier.info(f"Marked snapshot '{snapshot_name}' for deletion")
                    
                    purge_result = self._run_command(["multipass", "purge"])
                    
                    if purge_result.returncode == 0:
                        self.notifier.success(f"Purged snapshot '{snapshot_name}' for VM '{vm_name}'")
                        return True
                    else:
                        self.notifier.error(f"Failed to purge snapshot: {purge_result.stderr}")
                        return False
                else:
                    self.notifier.error(f"Failed to delete snapshot: {delete_result.stderr}")
                    return False
                
        except Exception as e:
            self.notifier.error(f"Error deleting snapshot: {str(e)}")
            return False
    
    def delete_all_snapshots(self, vm_name: str, purge: bool = True) -> int:
        """Delete all snapshots for a VM."""
        try:
            snapshots = self.list_snapshots(vm_name)
            if not snapshots:
                self.notifier.info(f"No snapshots found for VM '{vm_name}'")
                return 0
            
            deleted_count = 0
            snapshot_identifiers = []
            
            for snapshot in snapshots:
                snapshot_identifiers.append(f"{vm_name}.{snapshot['name']}")
            
            if purge:
                for identifier in snapshot_identifiers:
                    result = self._run_command([
                        "multipass", "delete", identifier, "--purge"
                    ])
                    
                    if result.returncode == 0:
                        deleted_count += 1
                        snapshot_name = identifier.split('.', 1)[1]
                        self.notifier.info(f"Deleted and purged: {snapshot_name}")
                    else:
                        self.notifier.error(f"Failed to delete {identifier}: {result.stderr}")
            else:
                for identifier in snapshot_identifiers:
                    result = self._run_command([
                        "multipass", "delete", identifier
                    ])
                    
                    if result.returncode == 0:
                        deleted_count += 1
                        snapshot_name = identifier.split('.', 1)[1]
                        self.notifier.info(f"Marked for deletion: {snapshot_name}")
                    else:
                        self.notifier.error(f"Failed to delete {identifier}: {result.stderr}")
                
                if deleted_count > 0:
                    purge_result = self._run_command(["multipass", "purge"])
                    if purge_result.returncode == 0:
                        self.notifier.success(f"Purged {deleted_count} snapshots for VM '{vm_name}'")
                    else:
                        self.notifier.error(f"Failed to purge snapshots: {purge_result.stderr}")
            
            return deleted_count
            
        except Exception as e:
            self.notifier.error(f"Error deleting all snapshots: {str(e)}")
            return 0
    
    def cleanup_old_snapshots(self, vm_name: str, retention_count: int) -> int:
        """Clean up old MinBackup snapshots for a specific VM."""
        try:
            all_snapshots = self.list_snapshots(vm_name)
            
            # Filter only MinBackup snapshots (those starting with "minbackup" or "backup")
            minbackup_snapshots = [
                s for s in all_snapshots 
                if s["name"].startswith("auto") or s["name"].startswith("minbackup") or s["name"].startswith("backup")
            ]
            
            if len(minbackup_snapshots) <= retention_count:
                self.notifier.info(f"VM '{vm_name}': {len(minbackup_snapshots)} MinBackup snapshots (within retention limit of {retention_count})")
                return 0
            
            # Sort by timestamp if available, otherwise by name
            try:
                minbackup_snapshots.sort(key=lambda x: x.get("timestamp") or datetime.min, reverse=True)
            except:
                minbackup_snapshots.sort(key=lambda x: x.get("name", ""), reverse=True)
            
            # Delete old snapshots
            old_snapshots = minbackup_snapshots[retention_count:]
            deleted_count = 0
            
            self.notifier.info(f"VM '{vm_name}': Deleting {len(old_snapshots)} old MinBackup snapshots (keeping {retention_count})")
            
            for snapshot in old_snapshots:
                if self.delete_snapshot(vm_name, snapshot["name"], True):
                    deleted_count += 1
                    self.notifier.info(f"Deleted old snapshot: {snapshot['name']}")
                else:
                    self.notifier.error(f"Failed to delete old snapshot: {snapshot['name']}")
            
            return deleted_count
            
        except Exception as e:
            self.notifier.error(f"Error cleaning up snapshots for VM '{vm_name}': {str(e)}")
            return 0


# Keep the rest of the classes the same for now...
class VirtualBoxPlatform(VMPlatform):
    """VirtualBox VM platform implementation."""
    
    @property
    def platform_name(self) -> str:
        return "virtualbox"
    
    @property
    def command_name(self) -> str:
        return "vboxmanage"
    
    def list_vms(self) -> List[Dict[str, Any]]:
        """List VirtualBox VMs."""
        try:
            result = self._run_command(["vboxmanage", "list", "vms"])
            if result.returncode == 0:
                vms = []
                for line in result.stdout.strip().split('\n'):
                    if line:
                        match = re.match(r'"([^"]+)"\s+\{([^}]+)\}', line)
                        if match:
                            vm_name = match.group(1)
                            vm_uuid = match.group(2)
                            
                            state_result = self._run_command([
                                "vboxmanage", "showvminfo", vm_uuid, "--machinereadable"
                            ])
                            state = "unknown"
                            if state_result.returncode == 0:
                                for state_line in state_result.stdout.split('\n'):
                                    if state_line.startswith('VMState='):
                                        state = state_line.split('=')[1].strip('"')
                                        break
                            
                            vms.append({
                                "name": vm_name,
                                "uuid": vm_uuid,
                                "state": state,
                                "platform": self.platform_name
                            })
                return vms
            else:
                self.notifier.error(f"Failed to list VMs: {result.stderr}")
                return []
        except Exception as e:
            self.notifier.error(f"Error listing VMs: {str(e)}")
            return []
    
    def create_snapshot(self, vm_name: str, snapshot_name: str) -> bool:
        """Create VirtualBox snapshot."""
        try:
            result = self._run_command([
                "vboxmanage", "snapshot", vm_name, "take", snapshot_name,
                "--description", f"MinBackup snapshot created at {datetime.now().isoformat()}"
            ])
            
            if result.returncode == 0:
                self.notifier.success(f"Created snapshot '{snapshot_name}' for VM '{vm_name}'")
                return True
            else:
                self.notifier.error(f"Failed to create snapshot: {result.stderr}")
                return False
                
        except Exception as e:
            self.notifier.error(f"Error creating snapshot: {str(e)}")
            return False
    
    def list_snapshots(self, vm_name: str) -> List[Dict[str, Any]]:
        """List VirtualBox snapshots."""
        try:
            result = self._run_command([
                "vboxmanage", "snapshot", vm_name, "list", "--machinereadable"
            ])
            
            if result.returncode == 0:
                snapshots = []
                current_snapshot = {}
                
                for line in result.stdout.split('\n'):
                    if line.startswith('SnapshotName'):
                        if current_snapshot:
                            snapshots.append(current_snapshot)
                        current_snapshot = {
                            "name": line.split('=')[1].strip('"'),
                            "vm_name": vm_name
                        }
                    elif line.startswith('SnapshotTimeStamp') and current_snapshot:
                        timestamp = line.split('=')[1].strip('"')
                        current_snapshot["created_at"] = timestamp
                
                if current_snapshot:
                    snapshots.append(current_snapshot)
                
                return snapshots
            else:
                self.notifier.error(f"Failed to list snapshots: {result.stderr}")
                return []
                
        except Exception as e:
            self.notifier.error(f"Error listing snapshots: {str(e)}")
            return []
    
    def delete_snapshot(self, vm_name: str, snapshot_name: str, purge: bool = True) -> bool:
        """Delete VirtualBox snapshot."""
        try:
            result = self._run_command([
                "vboxmanage", "snapshot", vm_name, "delete", snapshot_name
            ])
            
            if result.returncode == 0:
                self.notifier.success(f"Deleted snapshot '{snapshot_name}' from VM '{vm_name}'")
                return True
            else:
                self.notifier.error(f"Failed to delete snapshot: {result.stderr}")
                return False
                
        except Exception as e:
            self.notifier.error(f"Error deleting snapshot: {str(e)}")
            return False


class VMwarePlatform(VMPlatform):
    """VMware platform implementation (basic)."""
    
    @property
    def platform_name(self) -> str:
        return "vmware"
    
    @property
    def command_name(self) -> str:
        return "vmrun"
    
    def list_vms(self) -> List[Dict[str, Any]]:
        """List VMware VMs."""
        try:
            result = self._run_command(["vmrun", "list"])
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')[1:]
                return [
                    {
                        "name": line.split('/')[-1].replace('.vmx', ''),
                        "path": line,
                        "state": "unknown",
                        "platform": self.platform_name
                    }
                    for line in lines if line.strip()
                ]
            else:
                self.notifier.error(f"Failed to list VMs: {result.stderr}")
                return []
        except Exception as e:
            self.notifier.error(f"Error listing VMs: {str(e)}")
            return []
    
    def create_snapshot(self, vm_name: str, snapshot_name: str) -> bool:
        """Create VMware snapshot."""
        vms = self.list_vms()
        vm_path = None
        for vm in vms:
            if vm["name"] == vm_name:
                vm_path = vm["path"]
                break
        
        if not vm_path:
            self.notifier.error(f"VM not found: {vm_name}")
            return False
        
        try:
            result = self._run_command([
                "vmrun", "snapshot", vm_path, snapshot_name
            ])
            
            if result.returncode == 0:
                self.notifier.success(f"Created snapshot '{snapshot_name}' for VM '{vm_name}'")
                return True
            else:
                self.notifier.error(f"Failed to create snapshot: {result.stderr}")
                return False
                
        except Exception as e:
            self.notifier.error(f"Error creating snapshot: {str(e)}")
            return False
    
    def list_snapshots(self, vm_name: str) -> List[Dict[str, Any]]:
        """List VMware snapshots."""
        self.notifier.warning("VMware snapshot listing not fully implemented")
        return []
    
    def delete_snapshot(self, vm_name: str, snapshot_name: str, purge: bool = True) -> bool:
        """Delete VMware snapshot."""
        vms = self.list_vms()
        vm_path = None
        for vm in vms:
            if vm["name"] == vm_name:
                vm_path = vm["path"]
                break
        
        if not vm_path:
            self.notifier.error(f"VM not found: {vm_name}")
            return False
        
        try:
            result = self._run_command([
                "vmrun", "deleteSnapshot", vm_path, snapshot_name
            ])
            
            if result.returncode == 0:
                self.notifier.success(f"Deleted snapshot '{snapshot_name}' from VM '{vm_name}'")
                return True
            else:
                self.notifier.error(f"Failed to delete snapshot: {result.stderr}")
                return False
                
        except Exception as e:
            self.notifier.error(f"Error deleting snapshot: {str(e)}")
            return False


class VMManager:
    """VM manager that supports multiple virtualization platforms."""
    
    def __init__(self, config, notification_manager=None):
        """Initialize VM manager."""
        self.config = config
        self.notifier = notification_manager or NotificationManager(config)
        
        self.platforms = {
            "multipass": MultipassPlatform(config, self.notifier),
            "virtualbox": VirtualBoxPlatform(config, self.notifier),
            "vmware": VMwarePlatform(config, self.notifier)
        }
        
        self.available_platforms = self._detect_platforms()
        
        if not self.available_platforms:
            self.notifier.warning("No VM platforms detected")
        else:
            self.notifier.info(f"Available VM platforms: {', '.join(self.available_platforms.keys())}")
    
    def _detect_platforms(self) -> Dict[str, VMPlatform]:
        """Detect available VM platforms."""
        available = {}
        supported_platforms = self.config.supported_vm_platforms
        
        for platform_name in supported_platforms:
            if platform_name in self.platforms:
                platform = self.platforms[platform_name]
                if platform.is_available():
                    available[platform_name] = platform
                    self.notifier.info(f"Detected {platform_name} platform")
                else:
                    self.notifier.warning(f"{platform_name} command not found")
        
        return available
    
    def list_all_vms(self) -> Dict[str, List[Dict[str, Any]]]:
        """List VMs from all available platforms."""
        all_vms = {}
        
        for platform_name, platform in self.available_platforms.items():
            try:
                vms = platform.list_vms()
                all_vms[platform_name] = vms
                self.notifier.info(f"Found {len(vms)} VMs on {platform_name}")
            except Exception as e:
                self.notifier.error(f"Failed to list VMs from {platform_name}: {str(e)}")
                all_vms[platform_name] = []
        
        return all_vms
    
    def create_snapshot(self, vm_name: str, platform: Optional[str] = None, 
                       snapshot_name: Optional[str] = None) -> bool:
        """Create VM snapshot."""
        if not snapshot_name:
            if platform == "multipass" or (not platform and "multipass" in self.available_platforms):
                timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                snapshot_name = f"minbackup-{timestamp}"
            else:
                timestamp = generate_timestamp()
                snapshot_name = f"minbackup_{timestamp}"
        
        if platform:
            if platform not in self.available_platforms:
                self.notifier.error(f"Platform not available: {platform}")
                return False
            platform_obj = self.available_platforms[platform]
        else:
            platform_obj = self._find_vm_platform(vm_name)
            if not platform_obj:
                self.notifier.error(f"VM not found: {vm_name}")
                return False
        
        return platform_obj.create_snapshot(vm_name, snapshot_name)
    
    def _find_vm_platform(self, vm_name: str) -> Optional[VMPlatform]:
        """Find which platform has the specified VM."""
        for platform_name, platform in self.available_platforms.items():
            vms = platform.list_vms()
            for vm in vms:
                if vm["name"] == vm_name:
                    return platform
        return None
    
    def list_snapshots(self, vm_name: str, platform: Optional[str] = None) -> List[Dict[str, Any]]:
        """List snapshots for a VM."""
        if platform:
            if platform not in self.available_platforms:
                self.notifier.error(f"Platform not available: {platform}")
                return []
            platform_obj = self.available_platforms[platform]
        else:
            platform_obj = self._find_vm_platform(vm_name)
            if not platform_obj:
                self.notifier.error(f"VM not found: {vm_name}")
                return []
        
        return platform_obj.list_snapshots(vm_name)
    
    def delete_snapshot(self, vm_name: str, snapshot_name: str, 
                       platform: Optional[str] = None, purge: bool = True) -> bool:
        """Delete a specific snapshot."""
        if platform:
            if platform not in self.available_platforms:
                self.notifier.error(f"Platform not available: {platform}")
                return False
            platform_obj = self.available_platforms[platform]
        else:
            platform_obj = self._find_vm_platform(vm_name)
            if not platform_obj:
                self.notifier.error(f"VM not found: {vm_name}")
                return False
        
        return platform_obj.delete_snapshot(vm_name, snapshot_name, purge)
    
    def delete_all_snapshots(self, vm_name: str, platform: Optional[str] = None, 
                           purge: bool = True) -> int:
        """Delete all snapshots for a VM."""
        if platform:
            if platform not in self.available_platforms:
                self.notifier.error(f"Platform not available: {platform}")
                return 0
            platform_obj = self.available_platforms[platform]
        else:
            platform_obj = self._find_vm_platform(vm_name)
            if not platform_obj:
                self.notifier.error(f"VM not found: {vm_name}")
                return 0
        
        if hasattr(platform_obj, 'delete_all_snapshots'):
            return platform_obj.delete_all_snapshots(vm_name, purge)
        else:
            snapshots = platform_obj.list_snapshots(vm_name)
            deleted_count = 0
            for snapshot in snapshots:
                if platform_obj.delete_snapshot(vm_name, snapshot['name'], purge):
                    deleted_count += 1
            return deleted_count
    
    def cleanup_old_snapshots(self) -> Dict[str, Any]:
        """Clean up old snapshots based on retention policy."""
        retention_count = self.config.vm_snapshot_retention
        self.notifier.info(f"Cleaning up snapshots (keeping last {retention_count})")
        
        cleanup_summary = {
            "total_deleted": 0,
            "vms_processed": 0,
            "errors": []
        }
        
        for platform_name, platform in self.available_platforms.items():
            try:
                vms = platform.list_vms()
                for vm in vms:
                    vm_name = vm["name"]
                    cleanup_summary["vms_processed"] += 1
                    
                    if hasattr(platform, 'cleanup_old_snapshots'):
                        # Use platform-specific cleanup
                        deleted = platform.cleanup_old_snapshots(vm_name, retention_count)
                        cleanup_summary["total_deleted"] += deleted
                    else:
                        # Fallback: manual cleanup
                        snapshots = platform.list_snapshots(vm_name)
                        minbackup_snapshots = [
                            s for s in snapshots 
                            if s["name"].startswith("minbackup") or s["name"].startswith("backup")
                        ]
                        
                        if len(minbackup_snapshots) > retention_count:
                            minbackup_snapshots.sort(key=lambda x: x.get("created_at", ""), reverse=True)
                            old_snapshots = minbackup_snapshots[retention_count:]
                            
                            for snapshot in old_snapshots:
                                if platform.delete_snapshot(vm_name, snapshot["name"], True):
                                    cleanup_summary["total_deleted"] += 1
                                    self.notifier.info(f"Deleted old snapshot: {snapshot['name']} from {vm_name}")
                                else:
                                    error_msg = f"Failed to delete {snapshot['name']} from {vm_name}"
                                    cleanup_summary["errors"].append(error_msg)
                                    self.notifier.error(error_msg)
                            
            except Exception as e:
                error_msg = f"Error cleaning up snapshots for {platform_name}: {str(e)}"
                cleanup_summary["errors"].append(error_msg)
                self.notifier.error(error_msg)
        
        if cleanup_summary["total_deleted"] > 0:
            self.notifier.success(f"Deleted {cleanup_summary['total_deleted']} old snapshots from {cleanup_summary['vms_processed']} VMs")
        else:
            self.notifier.info(f"No old snapshots to clean up from {cleanup_summary['vms_processed']} VMs")
        
        return cleanup_summary