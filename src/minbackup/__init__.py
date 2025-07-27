"""
MinBackup - Minimalistic Backup Automation Tool

A lightweight backup automation suite supporting VM snapshots and file backups
with retention management.
"""

__version__ = "0.1.0"
__author__ = "Entro01"

from .backup_engine import BackupEngine
from .vm_manager import VMManager
from .storage_manager import StorageManager
from .config import Config

__all__ = [
    "BackupEngine",
    "VMManager", 
    "StorageManager",
    "Config"
]