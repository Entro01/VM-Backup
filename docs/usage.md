# MinBackup Usage Guide

MinBackup is a lightweight VM snapshot management tool that supports Multipass, VirtualBox, and VMware platforms with automatic scheduling and retention management.

## Quick Start

```bash
# Initialize MinBackup
minbackup init

# List all VMs and snapshots
minbackup list

# Create a snapshot
minbackup snapshot my-vm

# Enable automatic snapshots every 4 hours
minbackup auto enable 4h
minbackup auto start
```

## Complete Command Reference

### 1. Initialize Configuration

```bash
# Create default configuration
minbackup init

# Create with example configurations
minbackup init --example development
minbackup init --example server
```

**What it creates:**
- `minbackup.yaml` configuration file
- Detects available VM platforms (Multipass, VirtualBox, VMware)
- Sets default retention policy (keep last 7 snapshots)

### 2. List VMs and Snapshots

```bash
# Basic VM listing
minbackup list

# Show VM disk sizes
minbackup list --show-sizes

# Filter by specific platform
minbackup list --platform multipass
minbackup list --platform virtualbox
```

**Example Output:**
```
🖥️ Virtual Machines & Snapshots
================================================================================

MULTIPASS:
  📱 dev-server (Stopped) - Size: 2.1GB
     📸 Snapshots: 4
       🤖 auto-20250127-194522 (2025-01-27 19:45:22)
       📦 minbackup-20250127-140530 (2025-01-27 14:05:30)
       📦 backup-pre-update (2025-01-27 12:30:15)
       📸 manual-snapshot (2025-01-26 16:45:22)
  📱 test-vm (Running) - Size: 1.8GB
     No snapshots

ℹ️ Summary: 2 VMs, 4 snapshots
```

**Icons:**
- 🤖 = Automatic snapshot (created by scheduler)
- 📦 = MinBackup snapshot (manual MinBackup created)
- 📸 = Manual snapshot (created outside MinBackup)

### 3. View VM Snapshots

```bash
# List snapshots for specific VM
minbackup snapshots my-vm

# Show detailed information
minbackup snapshots my-vm --details

# Show estimated sizes
minbackup snapshots my-vm --show-sizes

# Sort by name instead of date
minbackup snapshots my-vm --sort name

# JSON output for scripting
minbackup snapshots my-vm --format json

# Combine options
minbackup snapshots my-vm --details --show-sizes
```

**Example Output:**
```
📸 Snapshots for VM: dev-server
======================================================================
#   Type Name                      Created              Est. Size
----------------------------------------------------------------------
1   AUTO auto-20250127-194522      2025-01-27 19:45:22  ~420MB
2   MB   minbackup-20250127-140530  2025-01-27 14:05:30  ~380MB
3   MB   backup-pre-update          2025-01-27 12:30:15  ~390MB
4   MAN  manual-snapshot            2025-01-26 16:45:22  ~400MB

Total snapshots: 4
Automatic snapshots: 1
MinBackup snapshots: 2
Manual snapshots: 1
```

**Type Legend:**
- `AUTO` = Automatic snapshot (scheduler created)
- `MB` = MinBackup snapshot (manual)
- `MAN` = Manual snapshot (external)

### 4. Create Snapshots

```bash
# Create snapshot with auto-generated name
minbackup snapshot my-vm

# Create with custom name
minbackup snapshot my-vm --name "before-major-update"

# Specify platform (if multiple available)
minbackup snapshot my-vm --platform multipass
```

**Auto-generated naming:**
- Manual snapshots: `minbackup-YYYYMMDD-HHMMSS`
- Automatic snapshots: `auto-YYYYMMDD-HHMMSS`

**Examples:**
```bash
# Quick snapshot before changes
minbackup snapshot production-vm

# Named snapshot for specific purpose
minbackup snapshot dev-vm --name "working-feature-auth"

# Platform-specific (if you have multiple VM platforms)
minbackup snapshot "Ubuntu Server" --platform virtualbox
```

### 5. Delete Snapshots

```bash
# Delete single snapshot
minbackup delete-snapshot my-vm snapshot-name

# Delete multiple snapshots
minbackup delete-snapshot my-vm snapshot1 snapshot2 snapshot3

# Delete ALL snapshots (with confirmation)
minbackup delete-snapshot my-vm all

# Skip confirmation prompt
minbackup delete-snapshot my-vm snapshot-name --confirm

# Delete without purging (Multipass two-step process)
minbackup delete-snapshot my-vm snapshot-name --no-purge
```

**Examples:**
```bash
# Delete old snapshots
minbackup delete-snapshot dev-server auto-20250120-100030 backup-old

# Delete all snapshots (careful!)
minbackup delete-snapshot test-vm all

# Quick delete without confirmation
minbackup delete-snapshot dev-vm old-snapshot --confirm

# Multipass: delete without immediate purge
minbackup delete-snapshot my-vm snapshot-name --no-purge
```

**Example Output:**
```
🗑️ Snapshots to delete from VM 'dev-server':
  - auto-20250120-100030 (created: 2025-01-20 10:00:30)
  - backup-old (created: 2025-01-19 15:20:10)

Are you sure you want to delete and purge 2 snapshot(s)? [y/N]: y
✅ Deleted and purged: auto-20250120-100030
✅ Deleted and purged: backup-old

ℹ️ Deleted 2 of 2 snapshots.
```

### 6. Cleanup Old Snapshots

```bash
# Preview what would be cleaned up
minbackup cleanup --dry-run

# Perform cleanup
minbackup cleanup
```

**Cleanup Rules:**
- Keeps last 7 MinBackup snapshots per VM (configurable)
- Only affects automatic and MinBackup snapshots
- Manual snapshots (created outside MinBackup) are never deleted
- Applies to snapshots starting with "auto", "minbackup", or "backup"

**Example Output:**
```bash
minbackup cleanup --dry-run

ℹ️ Dry run - showing what snapshots would be deleted:
Retention policy: Keep last 7 MinBackup snapshots per VM
----------------------------------------------------------------------

  VM: dev-server (multipass)
    Total MinBackup snapshots: 10
    Would keep: 7
    Would delete: 3
      📦 minbackup-20250115-100030 (created: 2025-01-15 10:00:30)
      🤖 auto-20250114-100030 (created: 2025-01-14 10:00:30)
      📦 backup-20250113-100030 (created: 2025-01-13 10:00:30)

ℹ️ Total snapshots that would be deleted: 3
```

### 7. Automatic Snapshots

#### Enable/Disable Automatic Snapshots

```bash
# Enable with interval
minbackup auto enable 30m     # Every 30 minutes
minbackup auto enable 4h      # Every 4 hours
minbackup auto enable 1d      # Every day
minbackup auto enable 12h     # Every 12 hours

# Disable automatic snapshots
minbackup auto disable
```

**Supported intervals:**
- `m` = minutes (e.g., `30m`, `45m`)
- `h` = hours (e.g., `2h`, `6h`, `12h`)
- `d` = days (e.g., `1d`, `3d`, `7d`)

#### Control Scheduler Daemon

```bash
# Start scheduler (runs in foreground)
minbackup auto start

# Check scheduler status
minbackup auto status

# Run snapshots immediately (one-time)
minbackup auto run-now
```

**Note:** The scheduler runs in foreground. Use `Ctrl+C` to stop it.

#### Scheduler Status

```bash
# Show detailed status
minbackup auto status

# JSON output for scripting
minbackup auto status --json
```

**Example Output:**
```
ℹ️ Automatic Snapshot Status
==================================================

Enabled: ✅ True
Daemon Running: 🟢 True
Interval: 4h

Last Run: 2025-01-27 19:45:22
Next Run: 2025-01-27 23:45:22

VMs Monitored: 2
Total Snapshots: 8

🟢 Scheduler is running!
```

### 8. System Status

```bash
# Show system status
minbackup status

# JSON output for scripting
minbackup status --json
```

**Example Output:**
```
🖥️ MinBackup VM Status
==================================================

📸 Virtual Machines:
  Available Platforms: multipass
  Total VMs: 2
  Total Snapshots: 8
  MinBackup Snapshots: 4
  Snapshot Retention: Keep last 7

ℹ️ VM Details:
    📱 dev-server (multipass):
      State: Stopped
      Snapshots: 5 total, 3 MinBackup
    📱 test-vm (multipass):
      State: Running
      Snapshots: 3 total, 1 MinBackup

✅ System ready for VM snapshot management
```

## Workflow Examples

### Daily Development Workflow

```bash
# 1. Morning: Check VM status
minbackup list --show-sizes

# 2. Before major changes: Create snapshot
minbackup snapshot dev-vm --name "before-refactoring"

# 3. After work: Check automatic snapshots
minbackup snapshots dev-vm

# 4. Weekly: Clean up old snapshots
minbackup cleanup --dry-run
minbackup cleanup
```

### Setting Up Automatic Backups

```bash
# 1. Initialize MinBackup
minbackup init

# 2. Set up automatic snapshots every 6 hours
minbackup auto enable 6h

# 3. Check configuration
minbackup auto status

# 4. Start the scheduler
minbackup auto start

# (Scheduler runs in foreground - use Ctrl+C to stop)
```

### Production Server Setup

```bash
# 1. Initialize with server configuration
minbackup init --example server

# 2. Test snapshot creation
minbackup snapshot production-vm --name "initial-snapshot"

# 3. Set up daily automatic snapshots
minbackup auto enable 1d

# 4. Run immediate test
minbackup auto run-now

# 5. Start scheduler daemon
minbackup auto start
```

### Emergency Recovery Preparation

```bash
# 1. Create immediate snapshot before risky operation
minbackup snapshot critical-vm --name "pre-emergency-fix"

# 2. Verify snapshot was created
minbackup snapshots critical-vm --details

# 3. Proceed with risky operation...

# 4. If needed, use native VM platform tools to restore:
# Multipass: multipass restore critical-vm.pre-emergency-fix
# VirtualBox: vboxmanage snapshot critical-vm restore pre-emergency-fix
```

## Platform-Specific Examples

### Windows (Multipass)

```cmd
REM Initialize MinBackup
minbackup init

REM List VMs with sizes
minbackup list --show-sizes

REM Create snapshot (VM auto-stopped if running)
minbackup snapshot pacific-bluegill --name "pre-update"

REM Set up automatic snapshots
minbackup auto enable 4h
minbackup auto start

REM In another PowerShell window, monitor status:
minbackup auto status
minbackup status
```

### Linux/macOS (VirtualBox)

```bash
# Initialize for server use
minbackup init --example server

# Create snapshots (works with running VMs)
minbackup snapshot "Ubuntu Server" --name "before-kernel-update"

# Set up automated snapshots
minbackup auto enable 12h

# Start scheduler in background (using screen/tmux)
screen -S minbackup-scheduler
minbackup auto start
# Ctrl+A, D to detach

# Check status later
minbackup status
minbackup snapshots "Ubuntu Server" --show-sizes
```

## Configuration

### Basic Configuration (minbackup.yaml)

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

### Development Environment

```yaml
vm:
  platforms:
    - multipass
  snapshot_retention: 5  # Less retention for dev
  timeout: 300

notifications:
  console: true
  file: "./minbackup.log"
  level: "DEBUG"  # More verbose for development
```

### Server Environment

```yaml
vm:
  platforms:
    - virtualbox
    - vmware
  snapshot_retention: 14  # More retention for production
  timeout: 600

notifications:
  console: true
  file: "/var/log/minbackup.log"
  level: "WARNING"  # Less verbose for production
```
