# MinBackup - Minimalistic Backup Automation Tool

A lightweight backup automation suite supporting VM snapshots and file backups with retention management.

## Features

- VM snapshot automation (Multipass, VirtualBox, VMware)
- File backup with compression and integrity verification
- Configurable retention policies
- Simple CLI interface
- Recovery system

## Quick Start

1. Install dependencies: `pip install -r requirements.txt`
2. Initialize configuration: `python -m minbackup init`
3. Create backup: `python -m minbackup backup /path/to/files`
4. List backups: `python -m minbackup list`

## Documentation

See `docs/` directory for detailed installation and usage instructions.