"""Core backup engine for file and directory backup operations."""

import os
import json
import tarfile
import fnmatch
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from .utils import (
    NotificationManager, 
    generate_timestamp, 
    calculate_checksum,
    format_size,
    ensure_directory
)


class BackupEngine:
    """Core backup engine for creating and managing file backups."""
    
    def __init__(self, config, notification_manager: Optional[NotificationManager] = None):
        """Initialize backup engine.
        
        Args:
            config: Configuration object
            notification_manager: Notification manager instance
        """
        self.config = config
        self.notifier = notification_manager or NotificationManager(config)
        self.backup_destination = Path(config.backup_destination)
        ensure_directory(self.backup_destination)
    
    def create_backup(self, source_paths: List[str], backup_name: Optional[str] = None) -> Dict[str, Any]:
        """Create a backup of specified source paths.
        
        Args:
            source_paths: List of file/directory paths to backup
            backup_name: Optional custom backup name
            
        Returns:
            Backup metadata dictionary
        """
        self.notifier.info("Starting backup operation...")
        
        # Generate backup name and paths
        timestamp = generate_timestamp()
        if backup_name:
            backup_filename = f"{backup_name}_{timestamp}.tar.gz"
        else:
            backup_filename = f"backup_{timestamp}.tar.gz"
        
        backup_path = self.backup_destination / backup_filename
        metadata_path = self.backup_destination / f"{backup_filename}.meta.json"
        
        # Validate source paths
        valid_sources = self._validate_sources(source_paths)
        if not valid_sources:
            self.notifier.failure("No valid source paths found")
            raise ValueError("No valid source paths provided")
        
        # Create backup metadata
        metadata = {
            "backup_id": backup_filename.replace('.tar.gz', ''),
            "timestamp": timestamp,
            "created_at": datetime.now().isoformat(),
            "source_paths": valid_sources,
            "backup_file": backup_filename,
            "compression": self.config.get('backup.compression', 'gzip'),
            "checksum_algorithm": self.config.get('backup.checksum', 'sha256'),
            "files_count": 0,
            "total_size": 0,
            "compressed_size": 0,
            "checksum": "",
            "exclude_patterns": self.config.exclude_patterns
        }
        
        try:
            # Create compressed backup
            self.notifier.info(f"Creating backup: {backup_filename}")
            files_count, total_size = self._create_compressed_backup(
                valid_sources, backup_path, metadata["exclude_patterns"]
            )
            
            # Calculate backup file size and checksum
            compressed_size = backup_path.stat().st_size
            checksum = calculate_checksum(backup_path, metadata["checksum_algorithm"])
            
            # Update metadata
            metadata.update({
                "files_count": files_count,
                "total_size": total_size,
                "compressed_size": compressed_size,
                "checksum": checksum,
                "compression_ratio": round((1 - compressed_size / total_size) * 100, 2) if total_size > 0 else 0
            })
            
            # Save metadata
            self._save_metadata(metadata, metadata_path)
            
            self.notifier.success(
                f"Backup created successfully: {backup_filename} "
                f"({format_size(compressed_size)}, {metadata['compression_ratio']}% compression)"
            )
            
            return metadata
            
        except Exception as e:
            self.notifier.failure(f"Backup failed: {str(e)}")
            # Cleanup failed backup
            if backup_path.exists():
                backup_path.unlink()
            if metadata_path.exists():
                metadata_path.unlink()
            raise
    
    def _validate_sources(self, source_paths: List[str]) -> List[str]:
        """Validate and filter source paths.
        
        Args:
            source_paths: List of source paths
            
        Returns:
            List of valid source paths
        """
        valid_sources = []
        for path in source_paths:
            path_obj = Path(path).resolve()
            if path_obj.exists():
                valid_sources.append(str(path_obj))
                self.notifier.info(f"Added source: {path_obj}")
            else:
                self.notifier.warning(f"Source path not found: {path}")
        
        return valid_sources
    
    def _create_compressed_backup(self, source_paths: List[str], backup_path: Path, 
                                exclude_patterns: List[str]) -> tuple:
        """Create compressed tar.gz backup.
        
        Args:
            source_paths: List of source paths
            backup_path: Path for backup file
            exclude_patterns: List of exclude patterns
            
        Returns:
            Tuple of (files_count, total_size)
        """
        files_count = 0
        total_size = 0
        
        with tarfile.open(backup_path, 'w:gz') as tar:
            for source_path in source_paths:
                source_obj = Path(source_path)
                
                if source_obj.is_file():
                    if not self._should_exclude(source_path, exclude_patterns):
                        tar.add(source_path, arcname=source_obj.name)
                        files_count += 1
                        total_size += source_obj.stat().st_size
                        self.notifier.info(f"Added file: {source_path}")
                
                elif source_obj.is_dir():
                    for root, dirs, files in os.walk(source_path):
                        # Filter directories
                        dirs[:] = [d for d in dirs if not self._should_exclude(
                            os.path.join(root, d), exclude_patterns)]
                        
                        for file in files:
                            file_path = os.path.join(root, file)
                            if not self._should_exclude(file_path, exclude_patterns):
                                # Create relative archive path
                                rel_path = os.path.relpath(file_path, os.path.dirname(source_path))
                                tar.add(file_path, arcname=rel_path)
                                files_count += 1
                                total_size += os.path.getsize(file_path)
                                
                                if files_count % 100 == 0:
                                    self.notifier.info(f"Processed {files_count} files...")
        
        return files_count, total_size
    
    def _should_exclude(self, file_path: str, exclude_patterns: List[str]) -> bool:
        """Check if file should be excluded based on patterns.
        
        Args:
            file_path: File path to check
            exclude_patterns: List of exclude patterns
            
        Returns:
            True if file should be excluded
        """
        file_path = os.path.normpath(file_path)
        
        for pattern in exclude_patterns:
            if fnmatch.fnmatch(file_path, pattern) or fnmatch.fnmatch(os.path.basename(file_path), pattern):
                return True
            
            # Check directory patterns
            if pattern.endswith('/') and pattern[:-1] in file_path:
                return True
        
        return False
    
    def _save_metadata(self, metadata: Dict[str, Any], metadata_path: Path) -> None:
        """Save backup metadata to file.
        
        Args:
            metadata: Metadata dictionary
            metadata_path: Path to save metadata
        """
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        self.notifier.info(f"Metadata saved: {metadata_path}")
    
    def verify_backup(self, backup_filename: str) -> bool:
        """Verify backup integrity using checksum.
        
        Args:
            backup_filename: Name of backup file to verify
            
        Returns:
            True if backup is valid
        """
        backup_path = self.backup_destination / backup_filename
        metadata_path = self.backup_destination / f"{backup_filename}.meta.json"
        
        if not backup_path.exists():
            self.notifier.error(f"Backup file not found: {backup_filename}")
            return False
        
        if not metadata_path.exists():
            self.notifier.error(f"Metadata file not found: {backup_filename}.meta.json")
            return False
        
        try:
            # Load metadata
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
            
            # Calculate current checksum
            current_checksum = calculate_checksum(backup_path, metadata["checksum_algorithm"])
            
            # Compare checksums
            if current_checksum == metadata["checksum"]:
                self.notifier.success(f"Backup verification successful: {backup_filename}")
                return True
            else:
                self.notifier.failure(f"Backup verification failed: {backup_filename} (checksum mismatch)")
                return False
                
        except Exception as e:
            self.notifier.error(f"Backup verification error: {str(e)}")
            return False