"""Command-line interface for MinBackup."""

import os
import sys
import click
import json
from pathlib import Path
from typing import Optional

from .config import Config
from .backup_engine import BackupEngine
from .vm_manager import VMManager
from .storage_manager import StorageManager
from .utils import NotificationManager, format_size


# Global configuration
config = None
notifier = None


def initialize_config(config_file: Optional[str] = None) -> tuple:
    """Initialize configuration and notification manager."""
    global config, notifier
    
    try:
        config = Config(config_file)
        notifier = NotificationManager(config)
        return config, notifier
    except Exception as e:
        click.echo(f"Error: Failed to initialize configuration: {str(e)}", err=True)
        sys.exit(1)


@click.group()
@click.option('--config', '-c', type=click.Path(exists=True), 
              help='Path to configuration file')
@click.option('--verbose', '-v', is_flag=True, 
              help='Enable verbose output')
@click.pass_context
def cli(ctx, config: Optional[str], verbose: bool):
    """MinBackup - Minimalistic backup automation tool.
    
    A lightweight backup suite supporting VM snapshots and file backups
    with retention management and recovery capabilities.
    """
    ctx.ensure_object(dict)
    
    # Initialize configuration
    global_config, global_notifier = initialize_config(config)
    
    # Set verbose mode
    if verbose:
        global_config.set('notifications.level', 'DEBUG')
        global_notifier = NotificationManager(global_config)
    
    # Store in context for subcommands
    ctx.obj['config'] = global_config
    ctx.obj['notifier'] = global_notifier


@cli.command()
@click.option('--destination', '-d', default='./backups',
              help='Backup destination directory')
@click.option('--example', '-e', type=click.Choice(['server', 'development']),
              help='Create example configuration')
@click.pass_context
def init(ctx, destination: str, example: Optional[str]):
    """Initialize MinBackup configuration."""
    config_obj = ctx.obj['config']
    notifier_obj = ctx.obj['notifier']
    
    try:
        # Set custom destination
        config_obj.set('backup.destination', destination)
        
        # Create destination directory
        dest_path = Path(destination)
        dest_path.mkdir(parents=True, exist_ok=True)
        
        # Save configuration
        config_file = "minbackup.yaml"
        if example:
            config_file = f"minbackup-{example}.yaml"
            # Load example configuration
            example_config_path = Path(__file__).parent.parent.parent / "config" / "examples" / f"{example}.yaml"
            if example_config_path.exists():
                import yaml
                with open(example_config_path, 'r') as f:
                    example_config = yaml.safe_load(f)
                for key, value in example_config.items():
                    config_obj._config[key] = value
                config_obj.set('backup.destination', destination)
        
        config_obj.save(config_file)
        
        notifier_obj.success(f"MinBackup initialized successfully!")
        click.echo(f"Configuration saved to: {config_file}")
        click.echo(f"Backup destination: {destination}")
        
        # Check VM platforms
        vm_manager = VMManager(config_obj, notifier_obj)
        if vm_manager.available_platforms:
            click.echo(f"Available VM platforms: {', '.join(vm_manager.available_platforms.keys())}")
        else:
            click.echo("No VM platforms detected. Install multipass, VirtualBox, or VMware for VM snapshot support.")
        
    except Exception as e:
        notifier_obj.error(f"Initialization failed: {str(e)}")
        sys.exit(1)


@cli.command()
@click.argument('sources', nargs=-1, required=True, type=click.Path())
@click.option('--name', '-n', help='Custom backup name')
@click.option('--exclude', '-x', multiple=True, help='Additional exclude patterns')
@click.pass_context
def backup(ctx, sources: tuple, name: Optional[str], exclude: tuple):
    """Create backup of specified files and directories."""
    config_obj = ctx.obj['config']
    notifier_obj = ctx.obj['notifier']
    
    try:
        # Add additional exclude patterns
        if exclude:
            current_excludes = config_obj.exclude_patterns.copy()
            current_excludes.extend(exclude)
            config_obj.set('backup.exclude_patterns', current_excludes)
        
        # Create backup
        backup_engine = BackupEngine(config_obj, notifier_obj)
        metadata = backup_engine.create_backup(list(sources), name)
        
        # Display backup info
        click.echo("\n📦 Backup Created Successfully!")
        click.echo(f"Backup ID: {metadata['backup_id']}")
        click.echo(f"File: {metadata['backup_file']}")
        click.echo(f"Files: {metadata['files_count']}")
        click.echo(f"Original Size: {format_size(metadata['total_size'])}")
        click.echo(f"Compressed Size: {format_size(metadata['compressed_size'])}")
        click.echo(f"Compression: {metadata['compression_ratio']}%")
        
    except Exception as e:
        notifier_obj.error(f"Backup failed: {str(e)}")
        sys.exit(1)


@cli.command()
@click.option('--format', '-f', type=click.Choice(['table', 'json']), default='table',
              help='Output format')
@click.pass_context
def list(ctx, format: str):
    """List all available backups."""
    config_obj = ctx.obj['config']
    notifier_obj = ctx.obj['notifier']
    
    try:
        storage_manager = StorageManager(config_obj, notifier_obj)
        backups = storage_manager.list_backups()
        
        if not backups:
            click.echo("No backups found.")
            return
        
        if format == 'json':
            click.echo(json.dumps(backups, indent=2))
        else:
            # Table format
            click.echo("\n📋 Available Backups:")
            click.echo("-" * 80)
            
            header = f"{'ID':<25} {'Created':<20} {'Size':<10} {'Files':<8} {'Status':<10}"
            click.echo(header)
            click.echo("-" * 80)
            
            for backup in backups:
                backup_id = backup.get('backup_id', 'unknown')[:24]
                created = backup.get('created_at', 'unknown')[:19].replace('T', ' ')
                size = backup.get('file_size_human', 'unknown')
                files = str(backup.get('files_count', '?'))
                status = "OK" if backup.get('exists') and not backup.get('metadata_missing') else "WARN"
                
                row = f"{backup_id:<25} {created:<20} {size:<10} {files:<8} {status:<10}"
                click.echo(row)
        
    except Exception as e:
        notifier_obj.error(f"Failed to list backups: {str(e)}")
        sys.exit(1)


@cli.command()
@click.argument('backup_id')
@click.argument('restore_path', type=click.Path())
@click.option('--files', '-f', multiple=True, help='Specific files to restore')
@click.option('--verify', is_flag=True, help='Verify backup before restoring')
@click.pass_context
def restore(ctx, backup_id: str, restore_path: str, files: tuple, verify: bool):
    """Restore files from backup."""
    config_obj = ctx.obj['config']
    notifier_obj = ctx.obj['notifier']
    
    try:
        storage_manager = StorageManager(config_obj, notifier_obj)
        
        # Verify backup if requested
        if verify:
            click.echo("🔍 Verifying backup integrity...")
            if not storage_manager.verify_backup(backup_id):
                click.echo("❌ Backup verification failed. Aborting restore.")
                sys.exit(1)
            click.echo("✅ Backup verification passed.")
        
        # Perform restore
        click.echo(f"🔄 Restoring backup {backup_id} to {restore_path}...")
        
        file_list = list(files) if files else None
        success = storage_manager.restore_backup(backup_id, restore_path, file_list)
        
        if success:
            click.echo(f"✅ Restore completed successfully to {restore_path}")
        else:
            click.echo("❌ Restore failed.")
            sys.exit(1)
            
    except Exception as e:
        notifier_obj.error(f"Restore failed: {str(e)}")
        sys.exit(1)


@cli.command()
@click.option('--dry-run', is_flag=True, help='Show what would be deleted without actually deleting')
@click.pass_context
def cleanup(ctx, dry_run: bool):
    """Clean up old backups based on retention policy."""
    config_obj = ctx.obj['config']
    notifier_obj = ctx.obj['notifier']
    
    try:
        storage_manager = StorageManager(config_obj, notifier_obj)
        
        if dry_run:
            click.echo("🔍 Dry run - showing what would be deleted:")
            backups = storage_manager.list_backups()
            retention_count = config_obj.retention_count
            
            if len(backups) > retention_count:
                old_backups = backups[retention_count:]
                click.echo(f"Would delete {len(old_backups)} old backups:")
                for backup in old_backups:
                    click.echo(f"  - {backup['backup_id']} ({backup.get('file_size_human', 'unknown')})")
            else:
                click.echo("No backups would be deleted.")
        else:
            summary = storage_manager.cleanup_old_backups()
            
            click.echo("\n🧹 Cleanup Summary:")
            click.echo(f"Total backups: {summary['total_backups']}")
            click.echo(f"Deleted: {summary['deleted_count']} ({format_size(summary['deleted_size'])})")
            click.echo(f"Kept: {summary['kept_count']}")
            
            if summary['errors']:
                click.echo(f"Errors: {len(summary['errors'])}")
                for error in summary['errors']:
                    click.echo(f"  - {error}")
        
    except Exception as e:
        notifier_obj.error(f"Cleanup failed: {str(e)}")
        sys.exit(1)


@cli.group()
def vm():
    """VM snapshot management commands."""
    pass


@vm.command('list')
@click.option('--platform', '-p', help='Specific VM platform')
@click.pass_context
def vm_list(ctx, platform: Optional[str]):
    """List all VMs and their snapshots."""
    config_obj = ctx.obj['config']
    notifier_obj = ctx.obj['notifier']
    
    try:
        vm_manager = VMManager(config_obj, notifier_obj)
        
        if not vm_manager.available_platforms:
            click.echo("No VM platforms available.")
            return
        
        click.echo("\n🖥️  Available VMs:")
        click.echo("-" * 60)
        
        all_vms = vm_manager.list_all_vms()
        
        for platform_name, vms in all_vms.items():
            if platform and platform != platform_name:
                continue
                
            click.echo(f"\n{platform_name.upper()}:")
            if not vms:
                click.echo("  No VMs found")
                continue
            
            for vm in vms:
                click.echo(f"  📱 {vm['name']} ({vm.get('state', 'unknown')})")
                
                # List snapshots
                try:
                    snapshots = vm_manager.list_snapshots(vm['name'], platform_name)
                    if snapshots:
                        click.echo(f"     Snapshots: {len(snapshots)}")
                        for snapshot in snapshots[:3]:  # Show first 3
                            click.echo(f"       - {snapshot['name']}")
                        if len(snapshots) > 3:
                            click.echo(f"       ... and {len(snapshots) - 3} more")
                    else:
                        click.echo("     No snapshots")
                except Exception:
                    click.echo("     Snapshots: unknown")
        
    except Exception as e:
        notifier_obj.error(f"Failed to list VMs: {str(e)}")
        sys.exit(1)


@vm.command('snapshot')
@click.argument('vm_name')
@click.option('--platform', '-p', help='Specific VM platform')
@click.option('--name', '-n', help='Custom snapshot name')
@click.pass_context
def vm_snapshot(ctx, vm_name: str, platform: Optional[str], name: Optional[str]):
    """Create VM snapshot."""
    config_obj = ctx.obj['config']
    notifier_obj = ctx.obj['notifier']
    
    try:
        vm_manager = VMManager(config_obj, notifier_obj)
        
        success = vm_manager.create_snapshot(vm_name, platform, name)
        
        if success:
            click.echo(f"✅ Snapshot created for VM: {vm_name}")
        else:
            click.echo(f"❌ Failed to create snapshot for VM: {vm_name}")
            sys.exit(1)
            
    except Exception as e:
        notifier_obj.error(f"Snapshot creation failed: {str(e)}")
        sys.exit(1)


@vm.command('cleanup')
@click.pass_context
def vm_cleanup(ctx):
    """Clean up old VM snapshots."""
    config_obj = ctx.obj['config']
    notifier_obj = ctx.obj['notifier']
    
    try:
        vm_manager = VMManager(config_obj, notifier_obj)
        vm_manager.cleanup_old_snapshots()
        click.echo("✅ VM snapshot cleanup completed.")
        
    except Exception as e:
        notifier_obj.error(f"VM cleanup failed: {str(e)}")
        sys.exit(1)


@cli.command()
@click.option('--json', 'output_json', is_flag=True, help='Output in JSON format')
@click.pass_context
def status(ctx, output_json: bool):
    """Show system status and backup statistics."""
    config_obj = ctx.obj['config']
    notifier_obj = ctx.obj['notifier']
    
    try:
        storage_manager = StorageManager(config_obj, notifier_obj)
        vm_manager = VMManager(config_obj, notifier_obj)
        
        # Get storage status
        storage_status = storage_manager.get_storage_status()
        
        # Get VM status
        vm_status = {
            "available_platforms": list(vm_manager.available_platforms.keys()),
            "total_vms": sum(len(vms) for vms in vm_manager.list_all_vms().values())
        }
        
        # Combined status
        status_info = {
            "storage": storage_status,
            "vm": vm_status,
            "config": {
                "destination": storage_status.get("destination"),
                "retention_count": storage_status.get("retention_count"),
                "retention_days": storage_status.get("retention_days")
            }
        }
        
        if output_json:
            click.echo(json.dumps(status_info, indent=2))
        else:
            click.echo("\n📊 MinBackup Status")
            click.echo("=" * 50)
            
            # Storage info
            click.echo(f"\n📦 Storage:")
            click.echo(f"  Destination: {storage_status.get('destination')}")
            click.echo(f"  Backups: {storage_status.get('backup_count', 0)}")
            click.echo(f"  Total Size: {storage_status.get('total_backup_size_human', '0 B')}")
            click.echo(f"  Directory Size: {storage_status.get('directory_size_human', '0 B')}")
            
            # VM info
            click.echo(f"\n🖥️  Virtual Machines:")
            click.echo(f"  Available Platforms: {', '.join(vm_status['available_platforms']) or 'None'}")
            click.echo(f"  Total VMs: {vm_status['total_vms']}")
            
            # Alerts
            alerts = storage_status.get('alerts', [])
            if alerts:
                click.echo(f"\n⚠️  Alerts ({len(alerts)}):")
                for alert in alerts:
                    click.echo(f"  - {alert}")
            else:
                click.echo(f"\n✅ No alerts")
        
    except Exception as e:
        notifier_obj.error(f"Status check failed: {str(e)}")
        sys.exit(1)


@cli.command()
@click.argument('backup_id')
@click.pass_context
def verify(ctx, backup_id: str):
    """Verify backup integrity."""
    config_obj = ctx.obj['config']
    notifier_obj = ctx.obj['notifier']
    
    try:
        storage_manager = StorageManager(config_obj, notifier_obj)
        
        click.echo(f"🔍 Verifying backup: {backup_id}")
        
        if storage_manager.verify_backup(backup_id):
            click.echo("✅ Backup verification successful.")
        else:
            click.echo("❌ Backup verification failed.")
            sys.exit(1)
            
    except Exception as e:
        notifier_obj.error(f"Verification failed: {str(e)}")
        sys.exit(1)


@cli.command('info')
@click.argument('backup_id')
@click.option('--contents', is_flag=True, help='Show backup contents')
@click.pass_context
def info(ctx, backup_id: str, contents: bool):
    """Show detailed backup information."""
    config_obj = ctx.obj['config']
    notifier_obj = ctx.obj['notifier']
    
    try:
        storage_manager = StorageManager(config_obj, notifier_obj)
        
        backup_info = storage_manager.get_backup_info(backup_id)
        if not backup_info:
            click.echo(f"Backup not found: {backup_id}")
            sys.exit(1)
        
        click.echo(f"\n📋 Backup Information: {backup_id}")
        click.echo("=" * 60)
        
        click.echo(f"File: {backup_info.get('backup_file')}")
        click.echo(f"Created: {backup_info.get('created_at', 'unknown')}")
        click.echo(f"Size: {backup_info.get('file_size_human', 'unknown')}")
        click.echo(f"Files: {backup_info.get('files_count', 'unknown')}")
        click.echo(f"Compression: {backup_info.get('compression_ratio', 'unknown')}%")
        click.echo(f"Checksum: {backup_info.get('checksum', 'none')}")
        
        # Source paths
        source_paths = backup_info.get('source_paths', [])
        if source_paths:
            click.echo(f"\nSource Paths:")
            for path in source_paths:
                click.echo(f"  - {path}")
        
        # Contents
        if contents:
            click.echo(f"\n📁 Contents:")
            contents_list = storage_manager.list_backup_contents(backup_id)
            if contents_list:
                for item in contents_list[:20]:  # Show first 20 items
                    size_info = f" ({item['size_human']})" if item['size_human'] else ""
                    click.echo(f"  {item['type'][0].upper()} {item['name']}{size_info}")
                
                if len(contents_list) > 20:
                    click.echo(f"  ... and {len(contents_list) - 20} more items")
            else:
                click.echo("  Could not read contents")
        
    except Exception as e:
        notifier_obj.error(f"Info retrieval failed: {str(e)}")
        sys.exit(1)


def main():
    """Main entry point for CLI."""
    cli()


if __name__ == '__main__':
    main()