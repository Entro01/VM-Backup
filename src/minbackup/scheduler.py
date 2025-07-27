"""Automatic VM snapshot scheduler - Windows-friendly version."""

import time
import signal
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional

from .vm_manager import VMManager
from .utils import NotificationManager


class SnapshotScheduler:
    """Automatic VM snapshot scheduler."""
    
    def __init__(self, config, notification_manager=None):
        """Initialize scheduler."""
        self.config = config
        self.notifier = notification_manager or NotificationManager(config)
        self.vm_manager = VMManager(config, self.notifier)
        
        # State file for persistence
        self.state_file = Path("minbackup_scheduler.json")
        
        # Load state
        self.state = self._load_state()
        self.running = False
    
    def _load_state(self) -> Dict[str, Any]:
        """Load scheduler state from file."""
        default_state = {
            "enabled": False,
            "interval_minutes": 360,  # 6 hours default
            "last_run": None,
            "next_run": None,
            "vm_last_snapshot": {}
        }
        
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    saved_state = json.load(f)
                    default_state.update(saved_state)
            except Exception as e:
                self.notifier.warning(f"Failed to load scheduler state: {e}")
        
        return default_state
    
    def _save_state(self):
        """Save scheduler state to file."""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            self.notifier.error(f"Failed to save scheduler state: {e}")
    
    def _parse_interval(self, interval_str: str) -> int:
        """Parse interval string to minutes."""
        interval_str = interval_str.lower().strip()
        
        import re
        match = re.match(r'^(\d+)([mhd]?)$', interval_str)
        if not match:
            raise ValueError(f"Invalid interval format: {interval_str}. Use format like '10m', '2h', '1d'")
        
        number = int(match.group(1))
        unit = match.group(2) or 'm'
        
        multipliers = {'m': 1, 'h': 60, 'd': 1440}
        return number * multipliers[unit]
    
    def _format_interval(self, minutes: int) -> str:
        """Format minutes to human readable string."""
        if minutes < 60:
            return f"{minutes}m"
        elif minutes < 1440:
            hours = minutes // 60
            remaining_minutes = minutes % 60
            if remaining_minutes == 0:
                return f"{hours}h"
            else:
                return f"{hours}h{remaining_minutes}m"
        else:
            days = minutes // 1440
            remaining_hours = (minutes % 1440) // 60
            if remaining_hours == 0:
                return f"{days}d"
            else:
                return f"{days}d{remaining_hours}h"
    
    def enable(self, interval: str):
        """Enable automatic snapshots with specified interval."""
        try:
            interval_minutes = self._parse_interval(interval)
            
            self.state["enabled"] = True
            self.state["interval_minutes"] = interval_minutes
            self.state["next_run"] = (datetime.now() + timedelta(minutes=interval_minutes)).isoformat()
            
            self._save_state()
            
            interval_formatted = self._format_interval(interval_minutes)
            self.notifier.success(f"Automatic snapshots enabled with interval: {interval_formatted}")
            self.notifier.info(f"Next snapshot scheduled for: {self.state['next_run'][:19].replace('T', ' ')}")
            
        except ValueError as e:
            self.notifier.error(str(e))
            raise
    
    def disable(self):
        """Disable automatic snapshots."""
        self.state["enabled"] = False
        self.state["next_run"] = None
        self._save_state()
        
        self.notifier.success("Automatic snapshots disabled")
    
    def is_enabled(self) -> bool:
        """Check if automatic snapshots are enabled."""
        return self.state.get("enabled", False)
    
    def get_status(self) -> Dict[str, Any]:
        """Get scheduler status information."""
        status = {
            "enabled": self.state.get("enabled", False),
            "running": self.running,
            "interval": self._format_interval(self.state.get("interval_minutes", 360)),
            "interval_minutes": self.state.get("interval_minutes", 360),
            "last_run": self.state.get("last_run"),
            "next_run": self.state.get("next_run"),
            "vm_count": 0,
            "total_snapshots": 0
        }
        
        # Get VM counts
        try:
            all_vms = self.vm_manager.list_all_vms()
            status["vm_count"] = sum(len(vms) for vms in all_vms.values())
            
            for platform_name, platform in self.vm_manager.available_platforms.items():
                for vm in all_vms.get(platform_name, []):
                    try:
                        snapshots = self.vm_manager.list_snapshots(vm['name'], platform_name)
                        status["total_snapshots"] += len(snapshots)
                    except:
                        pass
        except:
            pass
        
        return status
    
    def _should_run_snapshot(self) -> bool:
        """Check if it's time to run snapshots."""
        if not self.state.get("enabled", False):
            return False
        
        next_run_str = self.state.get("next_run")
        if not next_run_str:
            return True
        
        try:
            next_run = datetime.fromisoformat(next_run_str)
            return datetime.now() >= next_run
        except:
            return True
    
    def _create_auto_snapshots(self):
        """Create automatic snapshots for all VMs."""
        try:
            self.notifier.info("Starting automatic snapshot creation...")
            
            all_vms = self.vm_manager.list_all_vms()
            snapshot_count = 0
            error_count = 0
            
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            
            for platform_name, vms in all_vms.items():
                for vm in vms:
                    vm_name = vm["name"]
                    
                    try:
                        snapshot_name = f"auto-{timestamp}"
                        
                        success = self.vm_manager.create_snapshot(
                            vm_name, platform_name, snapshot_name
                        )
                        
                        if success:
                            snapshot_count += 1
                            self.notifier.info(f"Auto snapshot created for {vm_name}: {snapshot_name}")
                            self.state["vm_last_snapshot"][vm_name] = datetime.now().isoformat()
                        else:
                            error_count += 1
                            self.notifier.warning(f"Failed to create auto snapshot for {vm_name}")
                            
                    except Exception as e:
                        error_count += 1
                        self.notifier.error(f"Error creating snapshot for {vm_name}: {str(e)}")
            
            # Update state
            self.state["last_run"] = datetime.now().isoformat()
            self.state["next_run"] = (
                datetime.now() + timedelta(minutes=self.state["interval_minutes"])
            ).isoformat()
            self._save_state()
            
            # Summary
            total_vms = sum(len(vms) for vms in all_vms.values())
            self.notifier.success(
                f"Auto snapshot round completed: {snapshot_count}/{total_vms} successful"
            )
            
            if error_count > 0:
                self.notifier.warning(f"{error_count} snapshots failed")
            
            # Run cleanup
            try:
                cleanup_summary = self.vm_manager.cleanup_old_snapshots()
                if cleanup_summary["total_deleted"] > 0:
                    self.notifier.info(f"Cleaned up {cleanup_summary['total_deleted']} old snapshots")
            except Exception as e:
                self.notifier.warning(f"Cleanup failed: {str(e)}")
                
        except Exception as e:
            self.notifier.error(f"Auto snapshot creation failed: {str(e)}")
    
    def start_daemon(self):
        """Start the scheduler daemon (foreground)."""
        if not self.state.get("enabled", False):
            self.notifier.error("Automatic snapshots are not enabled.")
            return
        
        self.running = True
        
        # Setup signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            self.notifier.info("Received shutdown signal...")
            self.running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, signal_handler)
        
        interval_formatted = self._format_interval(self.state["interval_minutes"])
        self.notifier.success(f"Scheduler daemon started (interval: {interval_formatted})")
        
        if self.state.get("next_run"):
            next_run = self.state["next_run"][:19].replace('T', ' ')
            self.notifier.info(f"Next snapshot scheduled for: {next_run}")
        
        # Main daemon loop
        while self.running:
            try:
                if self._should_run_snapshot():
                    self._create_auto_snapshots()
                
                # Sleep for 30 seconds, checking if we should stop
                for _ in range(30):
                    if not self.running:
                        break
                    time.sleep(1)
                        
            except Exception as e:
                self.notifier.error(f"Scheduler daemon error: {str(e)}")
                time.sleep(60)
        
        self.notifier.info("Snapshot scheduler daemon stopped")
    
    def run_now(self):
        """Run snapshot creation immediately (one-time)."""
        if not self.state.get("enabled", False):
            self.notifier.error("Automatic snapshots are not enabled.")
            return
        
        self.notifier.info("Running automatic snapshots now...")
        self._create_auto_snapshots()