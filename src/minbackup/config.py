"""Configuration management for MinBackup."""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional


class Config:
    """Configuration manager for MinBackup."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize configuration.
        
        Args:
            config_path: Path to custom configuration file
        """
        self.config_path = config_path
        self._config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file."""
        # Default configuration path
        default_config = Path(__file__).parent.parent.parent / "config" / "default.yaml"
        
        # Load default configuration
        with open(default_config, 'r') as f:
            config = yaml.safe_load(f)
        
        # Override with custom configuration if provided
        if self.config_path and os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                custom_config = yaml.safe_load(f)
                config.update(custom_config)
        
        # Override with environment variables
        config = self._apply_env_overrides(config)
        
        return config
    
    def _apply_env_overrides(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variable overrides."""
        # Example: MINBACKUP_BACKUP_DESTINATION overrides backup.destination
        env_mappings = {
            'MINBACKUP_BACKUP_DESTINATION': ['backup', 'destination'],
            'MINBACKUP_BACKUP_RETENTION_COUNT': ['backup', 'retention', 'count'],
            'MINBACKUP_VM_SNAPSHOT_RETENTION': ['vm', 'snapshot_retention'],
            'MINBACKUP_LOG_LEVEL': ['notifications', 'level'],
        }
        
        for env_var, config_path in env_mappings.items():
            if env_var in os.environ:
                value = os.environ[env_var]
                # Convert to appropriate type
                if config_path[-1] in ['count', 'snapshot_retention', 'days']:
                    value = int(value)
                elif config_path[-1] in ['console']:
                    value = value.lower() in ['true', '1', 'yes']
                
                # Set nested configuration value
                current = config
                for key in config_path[:-1]:
                    if key not in current:
                        current[key] = {}
                    current = current[key]
                current[config_path[-1]] = value
        
        return config
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation.
        
        Args:
            key: Configuration key in dot notation (e.g., 'backup.destination')
            default: Default value if key not found
            
        Returns:
            Configuration value
        """
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any) -> None:
        """Set configuration value using dot notation.
        
        Args:
            key: Configuration key in dot notation
            value: Value to set
        """
        keys = key.split('.')
        current = self._config
        
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        
        current[keys[-1]] = value
    
    def save(self, path: str) -> None:
        """Save current configuration to file.
        
        Args:
            path: Path to save configuration file
        """
        with open(path, 'w') as f:
            yaml.dump(self._config, f, default_flow_style=False, indent=2)
    
    @property
    def backup_destination(self) -> str:
        """Get backup destination directory."""
        return self.get('backup.destination', './backups')
    
    @property
    def retention_count(self) -> int:
        """Get backup retention count."""
        return self.get('backup.retention.count', 7)
    
    @property
    def retention_days(self) -> int:
        """Get backup retention days."""
        return self.get('backup.retention.days', 30)
    
    @property
    def vm_snapshot_retention(self) -> int:
        """Get VM snapshot retention count."""
        return self.get('vm.snapshot_retention', 7)
    
    @property
    def supported_vm_platforms(self) -> list:
        """Get list of supported VM platforms."""
        return self.get('vm.platforms', ['multipass', 'virtualbox', 'vmware'])
    
    @property
    def exclude_patterns(self) -> list:
        """Get list of exclude patterns for backup."""
        return self.get('backup.exclude_patterns', [])