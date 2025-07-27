# MinBackup Installation Guide

## Prerequisites

### System Requirements
- Python 3.8 or higher
- Operating System: Linux, macOS, or Windows
- Minimum 100MB free disk space
- Administrative privileges (for some VM operations)

### VM Platform Requirements (Optional)

#### Multipass
```bash
# Ubuntu/Debian
sudo snap install multipass

# macOS
brew install multipass

# Windows
# Download from: https://multipass.run/download/windows
```

#### VirtualBox
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install virtualbox

# macOS
brew install virtualbox

# Windows
# Download from: https://www.virtualbox.org/wiki/Downloads
```

#### VMware
- VMware Workstation (Windows/Linux)
- VMware Fusion (macOS)
- VMware Player (Free version)

## Installation Steps

### 1. Clone or Download MinBackup
```bash
git clone <repository-url> minbackup
cd minbackup
```

### 2. Install Python Dependencies
```bash
# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
```

### 3. Install MinBackup
```bash
# Development installation
pip install -e .

# Or regular installation
pip install .
```

### 4. Verify Installation
```bash
minbackup --help
```

## Quick Setup

### 1. Initialize Configuration
```bash
# Basic setup
minbackup init

# Server environment
minbackup init --example server --destination /opt/backups

# Development environment
minbackup init --example development --destination ./dev-backups
```

### 2. Test Backup
```bash
# Create a test backup
echo "test file" > test.txt
minbackup backup test.txt

# List backups
minbackup list

# Check status
minbackup status
```

## Configuration

MinBackup uses YAML configuration files. The default configuration is created during initialization.

### Environment Variables
You can override configuration settings using environment variables:

```bash
export MINBACKUP_BACKUP_DESTINATION="/custom/backup/path"
export MINBACKUP_BACKUP_RETENTION_COUNT=14
export MINBACKUP_LOG_LEVEL=DEBUG
```

### Configuration File Locations
1. `./minbackup.yaml` (current directory)
2. Custom path via `--config` option

## Troubleshooting

### Common Issues

#### Permission Denied
```bash
# Linux/macOS - ensure proper permissions
sudo chown -R $USER:$USER /backup/destination
chmod 755 /backup/destination
```

#### VM Commands Not Found
```bash
# Check if VM tools are in PATH
which multipass
which vboxmanage
which vmrun

# Add to PATH if needed (example for Linux)
export PATH=$PATH:/usr/local/bin
```

#### Python Module Not Found
```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Reinstall if needed
pip install -r requirements.txt
```

### Debug Mode
Enable debug logging for troubleshooting:
```bash
minbackup --verbose status
```

## Uninstallation

```bash
# Remove Python package
pip uninstall minbackup

# Remove configuration and backups
rm -rf ./backups ./minbackup.yaml ./minbackup.log
```