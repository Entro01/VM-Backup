"""Utility functions and notification system for MinBackup."""

import os
import sys
import logging
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Union


class NotificationManager:
    """Simple notification manager for console and file logging."""
    
    def __init__(self, config):
        """Initialize notification manager.
        
        Args:
            config: Configuration object
        """
        self.config = config
        self.logger = self._setup_logger()
        self.use_unicode = self._check_unicode_support()
    
    def _check_unicode_support(self) -> bool:
        """Check if the terminal supports Unicode characters."""
        try:
            # Try to encode a checkmark to see if it's supported
            "✅".encode(sys.stdout.encoding or 'utf-8')
            return True
        except (UnicodeEncodeError, LookupError):
            return False
    
    def _setup_logger(self) -> logging.Logger:
        """Setup logging configuration."""
        logger = logging.getLogger('minbackup')
        
        # Clear existing handlers
        logger.handlers.clear()
        
        # Set log level
        level = getattr(logging, self.config.get('notifications.level', 'INFO'))
        logger.setLevel(level)
        
        # Console handler with encoding fix
        if self.config.get('notifications.console', True):
            console_handler = logging.StreamHandler(sys.stdout)
            
            # Set encoding for Windows compatibility
            if hasattr(console_handler.stream, 'reconfigure'):
                try:
                    console_handler.stream.reconfigure(encoding='utf-8', errors='replace')
                except (AttributeError, OSError):
                    pass
            
            console_formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)
        
        # File handler with UTF-8 encoding
        log_file = self.config.get('notifications.file')
        if log_file:
            # Ensure log directory exists
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        
        return logger
    
    def _format_message(self, message: str, prefix: str) -> str:
        """Format message with appropriate prefix based on Unicode support."""
        if self.use_unicode:
            return f"{prefix} {message}"
        else:
            # Use ASCII alternatives for Windows compatibility
            ascii_prefixes = {
                "✅": "[SUCCESS]",
                "❌": "[FAILED]",
                "⚠️": "[WARNING]",
                "ℹ️": "[INFO]"
            }
            ascii_prefix = ascii_prefixes.get(prefix, prefix)
            return f"{ascii_prefix} {message}"
    
    def info(self, message: str) -> None:
        """Log info message."""
        self.logger.info(message)
    
    def warning(self, message: str) -> None:
        """Log warning message."""
        self.logger.warning(message)
    
    def error(self, message: str) -> None:
        """Log error message."""
        self.logger.error(message)
    
    def success(self, message: str) -> None:
        """Log success message."""
        formatted_message = self._format_message(message, "✅")
        self.logger.info(formatted_message)
    
    def failure(self, message: str) -> None:
        """Log failure message."""
        formatted_message = self._format_message(message, "❌")
        self.logger.error(formatted_message)


def generate_timestamp() -> str:
    """Generate timestamp string for backup naming.
    
    Returns:
        Timestamp string in format YYYYMMDD_HHMMSS
    """
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def calculate_checksum(file_path: Union[str, Path], algorithm: str = 'sha256') -> str:
    """Calculate checksum for a file.
    
    Args:
        file_path: Path to file
        algorithm: Hash algorithm to use
        
    Returns:
        Hexadecimal checksum string
    """
    hash_obj = hashlib.new(algorithm)
    
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_obj.update(chunk)
    
    return hash_obj.hexdigest()


def format_size(size_bytes: int) -> str:
    """Format file size in human readable format.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted size string
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def get_directory_size(directory: Union[str, Path]) -> int:
    """Get total size of directory in bytes.
    
    Args:
        directory: Directory path
        
    Returns:
        Total size in bytes
    """
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(directory):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            if os.path.exists(filepath):
                total_size += os.path.getsize(filepath)
    return total_size


def ensure_directory(path: Union[str, Path]) -> Path:
    """Ensure directory exists, create if it doesn't.
    
    Args:
        path: Directory path
        
    Returns:
        Path object
    """
    path_obj = Path(path)
    path_obj.mkdir(parents=True, exist_ok=True)
    return path_obj


def is_command_available(command: str) -> bool:
    """Check if a command is available in the system PATH.
    
    Args:
        command: Command name to check
        
    Returns:
        True if command is available, False otherwise
    """
    import shutil
    return shutil.which(command) is not None