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
    def delete_snapshot(self, vm_name: str, snapshot_name: str) -> bool:
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
    """Multipass VM platform implementation."""
    
    @property
    def platform_name(self) -> str:
        return "multipass"
    
    @property
    def command_name(self) -> str:
        return "multipass"
    
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
        """Create Multipass snapshot."""
        try:
            # Stop VM if running
            result = self._run_command(["multipass", "stop", vm_name])
            if result.returncode != 0:
                self.notifier.warning(f"Could not stop VM {vm_name}: {result.stderr}")
            
            # Create snapshot (Multipass uses suspend/restore pattern)
            result = self._run_command(["multipass", "suspend", vm_name])
            if result.returncode == 0:
                self.notifier.success(f"Created snapshot for {vm_name} (suspended state)")
                return True
            else:
                self.notifier.error(f"Failed to create snapshot: {result.stderr}")
                return False
                
        except Exception as e:
            self.notifier.error(f"Error creating snapshot: {str(e)}")
            return False
    
    def list_snapshots(self, vm_name: str) -> List[Dict[str, Any]]:
        """List Multipass snapshots (suspended instances)."""
        vms = self.list_vms()
        vm_info = next((vm for vm in vms if vm["name"] == vm_name), None)
        
        if vm_info and vm_info["state"] == "Suspended":
            return [{
                "name": f"{vm_name}_suspended",
                "created_at": datetime.now().isoformat(),
                "vm_name": vm_name
            }]
        return []
    
    def delete_snapshot(self, vm_name: str, snapshot_name: str) -> bool:
        """Delete Multipass snapshot (restart VM)."""
        try:
            result = self._run_command(["multipass", "start", vm_name])
            if result.returncode == 0:
                self.notifier.success(f"Restored VM {vm_name} from suspended state")
                return True
            else:
                self.notifier.error(f"Failed to restore VM: {result.stderr}")
                return False
        except Exception as e:
            self.notifier.error(f"Error restoring VM: {str(e)}")
            return False


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
                        # Parse format: "VM Name" {UUID}
                        match = re.match(r'"([^"]+)"\s+\{([^}]+)\}', line)
                        if match:
                            vm_name = match.group(1)
                            vm_uuid = match.group(2)
                            
                            # Get VM state
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
    
    def delete_snapshot(self, vm_name: str, snapshot_name: str) -> bool:
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
                lines = result.stdout.strip().split('\n')[1:]  # Skip header
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
        # Find VM path
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
        # VMware snapshot listing is more complex and varies by version
        # This is a simplified implementation
        self.notifier.warning("VMware snapshot listing not fully implemented")
        return []
    
    def delete_snapshot(self, vm_name: str, snapshot_name: str) -> bool:
        """Delete VMware snapshot."""
        # Find VM path
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
    
    def __init__(self, config, notification_manager: Optional[NotificationManager] = None):
        """Initialize VM manager.
        
        Args:
            config: Configuration object
            notification_manager: Notification manager instance
        """
        self.config = config
        self.notifier = notification_manager or NotificationManager(config)
        
        # Initialize platforms
        self.platforms = {
            "multipass": MultipassPlatform(config, self.notifier),
            "virtualbox": VirtualBoxPlatform(config, self.notifier),
            "vmware": VMwarePlatform(config, self.notifier)
        }
        
        # Detect available platforms
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
        """Create VM snapshot.
        
        Args:
            vm_name: Name of VM
            platform: Specific platform to use (auto-detect if None)
            snapshot_name: Custom snapshot name
            
        Returns:
            True if snapshot created successfully
        """
        if not snapshot_name:
            timestamp = generate_timestamp()
            snapshot_name = f"minbackup_{timestamp}"
        
        # Find VM platform if not specified
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
    
    def cleanup_old_snapshots(self) -> None:
        """Clean up old snapshots based on retention policy."""
        retention_count = self.config.vm_snapshot_retention
        self.notifier.info(f"Cleaning up snapshots (keeping last {retention_count})")
        
        for platform_name, platform in self.available_platforms.items():
            try:
                vms = platform.list_vms()
                for vm in vms:
                    snapshots = platform.list_snapshots(vm["name"])
                    
                    if len(snapshots) > retention_count:
                        # Sort by creation date (assuming created_at field exists)
                        snapshots.sort(key=lambda x: x.get("created_at", ""), reverse=True)
                        
                        # Delete old snapshots
                        for snapshot in snapshots[retention_count:]:
                            if snapshot["name"].startswith("minbackup_"):
                                self.notifier.info(f"Deleting old snapshot: {snapshot['name']}")
                                platform.delete_snapshot(vm["name"], snapshot["name"])
                            
            except Exception as e:
                self.notifier.error(f"Error cleaning up snapshots for {platform_name}: {str(e)}")