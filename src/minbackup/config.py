"""Simplified configuration management for VM snapshots only."""

import os
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional


class Config:
    """Configuration manager for MinBackup VM snapshots."""
    
    def __init__(self, config_file: Optional[str] = None):
        """Initialize configuration.
        
        Args:
            config_file: Path to configuration file
        """
        self._config = self._get_default_config()
        
        # Load configuration file if provided
        if config_file and Path(config_file).exists():
            self.load(config_file)
        elif Path("minbackup.yaml").exists():
            self.load("minbackup.yaml")
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            "vm": {
                "platforms": ["multipass", "virtualbox", "vmware"],
                "snapshot_retention": 7,
                "timeout": 300
            },
            "notifications": {
                "console": True,
                "file": "./minbackup.log",
                "level": "INFO"
            }
        }
    
    def load(self, config_file: str) -> None:
        """Load configuration from file.
        
        Args:
            config_file: Path to configuration file
        """
        try:
            with open(config_file, 'r') as f:
                file_config = yaml.safe_load(f)
            
            if file_config:
                self._merge_config(self._config, file_config)
                
        except Exception as e:
            raise ValueError(f"Failed to load configuration from {config_file}: {str(e)}")
    
    def save(self, config_file: str) -> None:
        """Save configuration to file.
        
        Args:
            config_file: Path to save configuration
        """
        try:
            with open(config_file, 'w') as f:
                yaml.dump(self._config, f, default_flow_style=False, indent=2)
        except Exception as e:
            raise ValueError(f"Failed to save configuration to {config_file}: {str(e)}")
    
    def _merge_config(self, base: Dict[str, Any], override: Dict[str, Any]) -> None:
        """Recursively merge configuration dictionaries."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation.
        
        Args:
            key: Configuration key (e.g., 'vm.snapshot_retention')
            default: Default value if key not found
            
        Returns:
            Configuration value
        """
        keys = key.split('.')
        value = self._config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key: str, value: Any) -> None:
        """Set configuration value using dot notation.
        
        Args:
            key: Configuration key (e.g., 'vm.snapshot_retention')
            value: Value to set
        """
        keys = key.split('.')
        config = self._config
        
        # Navigate to parent
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        # Set value
        config[keys[-1]] = value
    
    @property
    def supported_vm_platforms(self) -> List[str]:
        """Get list of supported VM platforms."""
        return self.get('vm.platforms', ['multipass', 'virtualbox', 'vmware'])
    
    @property
    def vm_snapshot_retention(self) -> int:
        """Get VM snapshot retention count."""
        return self.get('vm.snapshot_retention', 7)