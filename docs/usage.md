# MinBackup Usage Guide

## Basic Commands

### Initialize MinBackup
```bash
# Basic initialization
minbackup init

# Custom destination
minbackup init --destination /path/to/backups

# Use example configuration
minbackup init --example server
```

### Create Backups
```bash
# Backup single file
minbackup backup /path/to/file.txt

# Backup directory
minbackup backup /path/to/directory

# Backup multiple paths
minbackup backup /home/user/documents /home/user/projects

# Custom backup name
minbackup backup --name "daily-backup" /path/to/data

# Exclude patterns
minbackup backup --exclude "*.log" --exclude "tmp/*" /path/to/data
```

### List and Manage Backups
```bash
# List all backups
minbackup list

# List in JSON format
minbackup list --format json

# Show backup details
minbackup info backup_20250127_162651

# Show backup contents
minbackup info backup_20250127_162651 --contents

# Verify backup integrity
minbackup verify backup_20250127_162651
```

### Restore Backups
```bash
# Restore entire backup
minbackup restore backup_20250127_162651 /restore/path

# Restore specific files
minbackup restore backup_20250127_162651 /restore/path --files "*.txt"

# Verify before restore
minbackup restore backup_20250127_162651 /restore/path --verify
```

### Cleanup Operations
```bash
# Show what would be cleaned up
minbackup cleanup --dry-run

# Perform cleanup
minbackup cleanup
```

## VM Snapshot Management

### List VMs
```bash
# List all VMs
minbackup vm list

# List VMs from specific platform
minbackup vm list --platform virtualbox
```

### Create Snapshots
```bash
# Create snapshot (auto-detect platform)
minbackup vm snapshot my-vm

# Specify platform
minbackup vm snapshot my-vm --platform multipass

# Custom snapshot name
minbackup vm snapshot my-vm --name "pre-update-snapshot"
```

### Cleanup VM Snapshots
```bash
# Clean up old snapshots
minbackup vm cleanup
```

## Monitoring and Status

### System Status
```bash
# Show status summary
minbackup status

# JSON output
minbackup status --json
```

### Example Status Output
```
📊 MinBackup Status
==================================================

📦 Storage:
  Destination: ./backups
  Backups: 5
  Total Size: 2.3 GB
  Directory Size: 2.3 GB

🖥️  Virtual Machines:
  Available Platforms: multipass, virtualbox
  Total VMs: 3

✅ No alerts
```

## Configuration Examples

### Basic Configuration
```yaml
backup:
  destination: "./backups"
  retention:
    count: 7
    days: 30
  compression: gzip
  exclude_patterns:
    - "*.tmp"
    - "*.log"
    - "__pycache__"

vm:
  platforms:
    - multipass
    - virtualbox
  snapshot_retention: 7

notifications:
  console: true
  file: "./minbackup.log"
  level: INFO
```

### Server Configuration
```yaml
backup:
  destination: "/opt/backups"
  retention:
    count: 14
    days: 90
  exclude_patterns:
    - "*.tmp"
    - "*.log"
    - "/var/cache/*"
    - "/tmp/*"

vm:
  platforms:
    - virtualbox
  snapshot_retention: 10

notifications:
  console: true
  file: "/var/log/minbackup.log"
  level: INFO

monitoring:
  max_backup_size_gb: 50
  alert_threshold_gb: 40
```

## Automation Examples

### Cron Jobs
```bash
# Daily backup at 2 AM
0 2 * * * /path/to/venv/bin/minbackup backup /home/user/important-data

# Weekly cleanup on Sunday at 3 AM
0 3 * * 0 /path/to/venv/bin/minbackup cleanup

# Daily VM snapshots at 1 AM
0 1 * * * /path/to/venv/bin/minbackup vm snapshot production-vm
```

### Shell Scripts
```bash
#!/bin/bash
# backup-script.sh

# Set configuration
export MINBACKUP_BACKUP_DESTINATION="/backups"
export MINBACKUP_LOG_LEVEL=INFO

# Create backup
minbackup backup /home/user/projects /home/user/documents

# Create VM snapshot
minbackup vm snapshot dev-vm

# Cleanup old backups
minbackup cleanup

# Send status
minbackup status
```

## Best Practices

### 1. Regular Backups
- Schedule daily backups for important data
- Use descriptive backup names
- Verify backups periodically

### 2. Retention Management
- Set appropriate retention counts based on storage capacity
- Consider different retention policies for different data types
- Monitor storage usage regularly

### 3. VM Snapshots
- Create snapshots before major system changes
- Use descriptive snapshot names
- Clean up old snapshots regularly

### 4. Monitoring
- Check backup status regularly
- Set up alerts for storage thresholds
- Monitor backup sizes and trends

### 5. Recovery Testing
- Periodically test restore procedures
- Verify backup integrity
- Document recovery procedures

## Advanced Usage

### Custom Exclude Patterns
```bash
# Exclude by file extension
minbackup backup /data --exclude "*.tmp" --exclude "*.cache"

# Exclude directories
minbackup backup /home --exclude "*/node_modules" --exclude "*/.git"

# Complex patterns
minbackup backup /project --exclude "build/*" --exclude "dist/*" --exclude "*.pyc"
```

### Environment-Specific Configurations
```bash
# Development
minbackup --config dev-config.yaml backup ./src

# Production
minbackup --config prod-config.yaml backup /opt/application

# Testing
MINBACKUP_LOG_LEVEL=DEBUG minbackup backup /test/data
```