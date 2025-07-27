# MinBackup

A lightweight VM snapshot management tool with automatic scheduling and retention management. Supports Multipass, VirtualBox, and VMware platforms.

![MinBackup Demo](docs/demo.gif)

## Features

- 🖥️ **Multi-Platform Support**: Multipass, VirtualBox, VMware
- 🤖 **Automatic Snapshots**: Configurable scheduling (minutes, hours, days)
- 📦 **Smart Retention**: Automatic cleanup of old snapshots
- 📊 **Size Monitoring**: VM and snapshot size estimation
- 🎯 **Selective Management**: Distinguishes between automatic, manual, and external snapshots
- ⚡ **Simple CLI**: Easy-to-use command interface
- 🔧 **Cross-Platform**: Windows, Linux, macOS support

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt
pip install -e .

# Initialize MinBackup
minbackup init

# List your VMs
minbackup list --show-sizes

# Create a snapshot
minbackup snapshot my-vm --name "before-update"

# Enable automatic snapshots every 4 hours
minbackup auto enable 4h
minbackup auto start
```

## Installation

### Prerequisites

- Python 3.8+
- At least one VM platform:
  - [Multipass](https://multipass.run/) (recommended)
  - [VirtualBox](https://www.virtualbox.org/)
  - [VMware Workstation/Player](https://www.vmware.com/)

### Install MinBackup

```bash
# Clone the repository
git clone https://github.com/yourusername/minbackup.git
cd minbackup

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install MinBackup
pip install -e .

# Initialize configuration
minbackup init
```

## Command Overview

| Command | Description |
|---------|-------------|
| `minbackup init` | Initialize configuration |
| `minbackup list` | List VMs and snapshots |
| `minbackup snapshots <vm>` | Show snapshots for specific VM |
| `minbackup snapshot <vm>` | Create VM snapshot |
| `minbackup delete-snapshot <vm> <snapshot>` | Delete snapshot(s) |
| `minbackup cleanup` | Clean up old snapshots |
| `minbackup auto enable <interval>` | Enable automatic snapshots |
| `minbackup auto start` | Start scheduler daemon |
| `minbackup auto status` | Show scheduler status |
| `minbackup status` | Show system status |

## Usage Examples

### Basic VM Management

```bash
# List all VMs with sizes
minbackup list --show-sizes

# Create named snapshot
minbackup snapshot dev-vm --name "working-feature-auth"

# View detailed snapshots
minbackup snapshots dev-vm --details --show-sizes

# Delete old snapshots
minbackup delete-snapshot dev-vm old-snapshot1 old-snapshot2
```

### Automatic Snapshots

```bash
# Enable automatic snapshots every 6 hours
minbackup auto enable 6h

# Start the scheduler (foreground)
minbackup auto start

# Check scheduler status
minbackup auto status

# Run snapshots immediately
minbackup auto run-now

# Disable automatic snapshots
minbackup auto disable
```

### Snapshot Types

MinBackup distinguishes between three types of snapshots:

- **🤖 AUTO** - Created by automatic scheduler (`auto-YYYYMMDD-HHMMSS`)
- **📦 MB** - Created manually by MinBackup (`minbackup-YYYYMMDD-HHMMSS` or custom names)
- **📸 MAN** - Created outside MinBackup (via native VM tools)

### Cleanup and Retention

```bash
# Preview cleanup (safe)
minbackup cleanup --dry-run

# Perform cleanup
minbackup cleanup

# Only automatic and MinBackup snapshots are cleaned up
# Manual snapshots (created outside MinBackup) are preserved
```

## Configuration

MinBackup creates a `minbackup.yaml` configuration file:

```yaml
vm:
  platforms:
    - multipass
    - virtualbox 
    - vmware
  snapshot_retention: 7  # Keep last 7 snapshots
  timeout: 300

notifications:
  console: true
  file: "./minbackup.log"
  level: "INFO"
```

## Platform Support

### Multipass
- **Platforms**: Windows, Linux, macOS
- **Snapshot Support**: Native snapshots
- **VM State**: Must be stopped for snapshot creation
- **Size Detection**: Via `multipass info` command

### VirtualBox
- **Platforms**: Windows, Linux, macOS
- **Snapshot Support**: Native snapshots
- **VM State**: Works with running VMs
- **Size Detection**: VM directory calculation

### VMware
- **Platforms**: Windows, Linux
- **Snapshot Support**: Basic support via `vmrun`
- **VM State**: Platform dependent
- **Size Detection**: Not implemented

## Scheduling

MinBackup supports flexible scheduling intervals:

```bash
# Minutes
minbackup auto enable 30m    # Every 30 minutes
minbackup auto enable 90m    # Every 90 minutes

# Hours  
minbackup auto enable 2h     # Every 2 hours
minbackup auto enable 12h    # Every 12 hours

# Days
minbackup auto enable 1d     # Daily
minbackup auto enable 7d     # Weekly
```

The scheduler runs in foreground and can be stopped with `Ctrl+C`.

## Development

### Project Structure

```
minbackup/
├── src/minbackup/
│   ├── cli.py              # Command-line interface
│   ├── vm_manager.py       # VM platform abstraction
│   ├── scheduler.py        # Automatic scheduling
│   ├── config.py           # Configuration management
│   └── utils.py            # Utilities and notifications
├── docs/
│   └── usage.md            # Detailed usage guide
├── requirements.txt        # Python dependencies
├── setup.py               # Package setup
└── README.md              # This file
```

**MinBackup** - Simple, automated VM snapshot management for developers and system administrators.