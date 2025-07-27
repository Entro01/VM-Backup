"""Storage management for backup retention, cleanup, and recovery operations."""

import os
import json
import tarfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Union

from .utils import (
    NotificationManager,
    format_size,
    get_directory_size,
    calculate_checksum,
    ensure_directory
)


class StorageManager:
    """Manages backup storage, retention, cleanup, and recovery operations."""
    
    def __init__(self, config, notification_manager=None):
        """Initialize storage manager.
        
        Args:
            config: Configuration object
            notification_manager: Notification manager instance (optional)
        """
        self.config = config
        self.notifier = notification_manager or NotificationManager(config)
        self.backup_destination = Path(config.backup_destination)
        ensure_directory(self.backup_destination)
    
    # ... rest of the class remains the same ...
    def list_backups(self) -> List[Dict[str, Any]]:
        """List all available backups with metadata.
        
        Returns:
            List of backup metadata dictionaries
        """
        backups = []
        
        try:
            for backup_file in self.backup_destination.glob("*.tar.gz"):
                metadata_file = self.backup_destination / f"{backup_file.name}.meta.json"
                
                if metadata_file.exists():
                    try:
                        with open(metadata_file, 'r') as f:
                            metadata = json.load(f)
                        
                        # Add file system info
                        stat = backup_file.stat()
                        metadata.update({
                            "file_path": str(backup_file),
                            "file_size": stat.st_size,
                            "file_size_human": format_size(stat.st_size),
                            "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            "exists": True
                        })
                        
                        backups.append(metadata)
                        
                    except (json.JSONDecodeError, KeyError) as e:
                        self.notifier.warning(f"Invalid metadata file: {metadata_file} - {str(e)}")
                        
                        # Create basic metadata for backup without valid metadata
                        stat = backup_file.stat()
                        backups.append({
                            "backup_id": backup_file.stem.replace('.tar', ''),
                            "backup_file": backup_file.name,
                            "file_path": str(backup_file),
                            "file_size": stat.st_size,
                            "file_size_human": format_size(stat.st_size),
                            "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                            "exists": True,
                            "metadata_missing": True
                        })
                else:
                    self.notifier.warning(f"Metadata file missing for: {backup_file.name}")
            
            # Sort by creation time (newest first)
            backups.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            
            return backups
            
        except Exception as e:
            self.notifier.error(f"Error listing backups: {str(e)}")
            return []
    
    def get_backup_info(self, backup_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific backup.
        
        Args:
            backup_id: Backup identifier
            
        Returns:
            Backup metadata dictionary or None if not found
        """
        backups = self.list_backups()
        for backup in backups:
            if backup.get("backup_id") == backup_id:
                return backup
        
        self.notifier.error(f"Backup not found: {backup_id}")
        return None
    
    def cleanup_old_backups(self) -> Dict[str, Any]:
        """Clean up old backups based on retention policies.
        
        Returns:
            Cleanup summary dictionary
        """
        self.notifier.info("Starting backup cleanup...")
        
        retention_count = self.config.retention_count
        retention_days = self.config.retention_days
        
        backups = self.list_backups()
        cleanup_summary = {
            "total_backups": len(backups),
            "deleted_count": 0,
            "deleted_size": 0,
            "kept_count": 0,
            "errors": []
        }
        
        # Cleanup by count (keep last N backups)
        if len(backups) > retention_count:
            old_backups = backups[retention_count:]
            
            for backup in old_backups:
                try:
                    if self._delete_backup(backup):
                        cleanup_summary["deleted_count"] += 1
                        cleanup_summary["deleted_size"] += backup.get("file_size", 0)
                        self.notifier.info(f"Deleted old backup: {backup['backup_id']}")
                    else:
                        cleanup_summary["errors"].append(f"Failed to delete: {backup['backup_id']}")
                        
                except Exception as e:
                    error_msg = f"Error deleting {backup['backup_id']}: {str(e)}"
                    cleanup_summary["errors"].append(error_msg)
                    self.notifier.error(error_msg)
        
        # Cleanup by age
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        
        for backup in backups:
            try:
                created_at = datetime.fromisoformat(backup.get("created_at", ""))
                if created_at < cutoff_date:
                    if self._delete_backup(backup):
                        cleanup_summary["deleted_count"] += 1
                        cleanup_summary["deleted_size"] += backup.get("file_size", 0)
                        self.notifier.info(f"Deleted expired backup: {backup['backup_id']}")
                    else:
                        cleanup_summary["errors"].append(f"Failed to delete expired: {backup['backup_id']}")
                        
            except (ValueError, TypeError):
                self.notifier.warning(f"Invalid date format for backup: {backup['backup_id']}")
        
        cleanup_summary["kept_count"] = cleanup_summary["total_backups"] - cleanup_summary["deleted_count"]
        
        self.notifier.success(
            f"Cleanup completed: deleted {cleanup_summary['deleted_count']} backups "
            f"({format_size(cleanup_summary['deleted_size'])}), kept {cleanup_summary['kept_count']}"
        )
        
        return cleanup_summary
    
    def _delete_backup(self, backup: Dict[str, Any]) -> bool:
        """Delete a backup and its metadata file.
        
        Args:
            backup: Backup metadata dictionary
            
        Returns:
            True if deletion successful
        """
        try:
            backup_file = Path(backup["file_path"])
            metadata_file = backup_file.parent / f"{backup_file.name}.meta.json"
            
            # Delete backup file
            if backup_file.exists():
                backup_file.unlink()
            
            # Delete metadata file
            if metadata_file.exists():
                metadata_file.unlink()
            
            return True
            
        except Exception as e:
            self.notifier.error(f"Error deleting backup files: {str(e)}")
            return False
    
    def get_storage_status(self) -> Dict[str, Any]:
        """Get storage status and statistics.
        
        Returns:
            Storage status dictionary
        """
        try:
            backups = self.list_backups()
            
            total_size = 0
            total_files = 0
            oldest_backup = None
            newest_backup = None
            
            for backup in backups:
                total_size += backup.get("file_size", 0)
                total_files += backup.get("files_count", 0)
                
                created_at = backup.get("created_at")
                if created_at:
                    if not oldest_backup or created_at < oldest_backup:
                        oldest_backup = created_at
                    if not newest_backup or created_at > newest_backup:
                        newest_backup = created_at
            
            # Get directory size (includes all files)
            directory_size = get_directory_size(self.backup_destination)
            
            # Check alerts
            max_size_gb = self.config.get('monitoring.max_backup_size_gb', 10)
            alert_threshold_gb = self.config.get('monitoring.alert_threshold_gb', 8)
            
            max_size_bytes = max_size_gb * 1024 * 1024 * 1024
            alert_threshold_bytes = alert_threshold_gb * 1024 * 1024 * 1024
            
            alerts = []
            if directory_size > alert_threshold_bytes:
                alerts.append(f"Storage usage above threshold: {format_size(directory_size)} > {format_size(alert_threshold_bytes)}")
            
            if directory_size > max_size_bytes:
                alerts.append(f"Storage usage above maximum: {format_size(directory_size)} > {format_size(max_size_bytes)}")
            
            status = {
                "backup_count": len(backups),
                "total_backup_size": total_size,
                "total_backup_size_human": format_size(total_size),
                "directory_size": directory_size,
                "directory_size_human": format_size(directory_size),
                "total_files_backed_up": total_files,
                "oldest_backup": oldest_backup,
                "newest_backup": newest_backup,
                "destination": str(self.backup_destination),
                "retention_count": self.config.retention_count,
                "retention_days": self.config.retention_days,
                "alerts": alerts,
                "alert_count": len(alerts)
            }
            
            # Log alerts
            for alert in alerts:
                self.notifier.warning(alert)
            
            return status
            
        except Exception as e:
            self.notifier.error(f"Error getting storage status: {str(e)}")
            return {"error": str(e)}
    
    def restore_backup(self, backup_id: str, restore_path: str, 
                      files: Optional[List[str]] = None) -> bool:
        """Restore files from backup.
        
        Args:
            backup_id: Backup identifier
            restore_path: Path to restore files to
            files: Specific files to restore (None for all files)
            
        Returns:
            True if restore successful
        """
        backup_info = self.get_backup_info(backup_id)
        if not backup_info:
            return False
        
        backup_file = Path(backup_info["file_path"])
        restore_path_obj = Path(restore_path)
        
        # Ensure restore directory exists
        ensure_directory(restore_path_obj)
        
        try:
            self.notifier.info(f"Restoring backup {backup_id} to {restore_path}")
            
            with tarfile.open(backup_file, 'r:gz') as tar:
                if files:
                    # Restore specific files
                    restored_count = 0
                    for file_pattern in files:
                        members = [m for m in tar.getmembers() if file_pattern in m.name]
                        for member in members:
                            tar.extract(member, restore_path_obj)
                            restored_count += 1
                            self.notifier.info(f"Restored: {member.name}")
                    
                    if restored_count == 0:
                        self.notifier.warning("No files matched the specified patterns")
                        return False
                    
                    self.notifier.success(f"Restored {restored_count} files")
                    
                else:
                    # Restore all files
                    tar.extractall(restore_path_obj)
                    member_count = len(tar.getmembers())
                    self.notifier.success(f"Restored all files ({member_count} items)")
            
            return True
            
        except Exception as e:
            self.notifier.error(f"Error restoring backup: {str(e)}")
            return False
    
    def verify_backup(self, backup_id: str) -> bool:
        """Verify backup integrity.
        
        Args:
            backup_id: Backup identifier
            
        Returns:
            True if backup is valid
        """
        backup_info = self.get_backup_info(backup_id)
        if not backup_info:
            return False
        
        backup_file = Path(backup_info["file_path"])
        
        try:
            self.notifier.info(f"Verifying backup: {backup_id}")
            
            # Check if file exists and is readable
            if not backup_file.exists():
                self.notifier.error(f"Backup file not found: {backup_file}")
                return False
            
            # Verify checksum if available
            if "checksum" in backup_info and "checksum_algorithm" in backup_info:
                current_checksum = calculate_checksum(backup_file, backup_info["checksum_algorithm"])
                if current_checksum != backup_info["checksum"]:
                    self.notifier.failure(f"Checksum verification failed for {backup_id}")
                    return False
                else:
                    self.notifier.info("Checksum verification passed")
            
            # Verify tar file integrity
            try:
                with tarfile.open(backup_file, 'r:gz') as tar:
                    # Try to list all members
                    members = tar.getmembers()
                    self.notifier.info(f"Tar file contains {len(members)} members")
                    
                    # Test extraction of first few files
                    test_count = min(5, len(members))
                    for i, member in enumerate(members[:test_count]):
                        if member.isfile():
                            # Test read without extracting
                            f = tar.extractfile(member)
                            if f:
                                f.read(1024)  # Read first 1KB
                                f.close()
                            else:
                                self.notifier.warning(f"Could not read member: {member.name}")
                    
                    self.notifier.info(f"Successfully tested {test_count} archive members")
                    
            except tarfile.TarError as e:
                self.notifier.error(f"Tar file verification failed: {str(e)}")
                return False
            
            self.notifier.success(f"Backup verification completed successfully: {backup_id}")
            return True
            
        except Exception as e:
            self.notifier.error(f"Error verifying backup: {str(e)}")
            return False
    
    def list_backup_contents(self, backup_id: str) -> List[Dict[str, Any]]:
        """List contents of a backup.
        
        Args:
            backup_id: Backup identifier
            
        Returns:
            List of file information dictionaries
        """
        backup_info = self.get_backup_info(backup_id)
        if not backup_info:
            return []
        
        backup_file = Path(backup_info["file_path"])
        contents = []
        
        try:
            with tarfile.open(backup_file, 'r:gz') as tar:
                for member in tar.getmembers():
                    contents.append({
                        "name": member.name,
                        "type": "file" if member.isfile() else "directory" if member.isdir() else "other",
                        "size": member.size,
                        "size_human": format_size(member.size) if member.isfile() else "",
                        "mode": oct(member.mode),
                        "modified": datetime.fromtimestamp(member.mtime).isoformat() if member.mtime else ""
                    })
            
            # Sort by name
            contents.sort(key=lambda x: x["name"])
            
            return contents
            
        except Exception as e:
            self.notifier.error(f"Error listing backup contents: {str(e)}")
            return []