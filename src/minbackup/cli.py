"""Command-line interface for MinBackup - VM Snapshot Management Only."""

import os
import sys
import click
import json
from pathlib import Path
from typing import Optional
from datetime import datetime

from .config import Config
from .vm_manager import VMManager
from .utils import NotificationManager
from .scheduler import SnapshotScheduler


# Global configuration
config = None
notifier = None


def get_unicode_support() -> bool:
    """Check if Unicode is supported in the current terminal."""
    try:
        "✅".encode(sys.stdout.encoding or 'utf-8')
        return True
    except (UnicodeEncodeError, LookupError):
        return False


def format_status_icon(status: str) -> str:
    """Format status with appropriate icon."""
    if get_unicode_support():
        icons = {
            "success": "✅",
            "error": "❌", 
            "warning": "⚠️",
            "info": "ℹ️",
            "vm": "🖥️",
            "cleanup": "🧹",
            "delete": "🗑️",
            "snapshot": "📸"
        }
        return icons.get(status, "")
    else:
        prefixes = {
            "success": "[OK]",
            "error": "[ERROR]",
            "warning": "[WARN]",
            "info": "[INFO]",
            "vm": "[VM]",
            "cleanup": "[CLEANUP]",
            "delete": "[DELETE]",
            "snapshot": "[SNAPSHOT]"
        }
        return prefixes.get(status, "")


def parse_datetime(date_str: str) -> datetime:
    """Parse datetime string in various formats."""
    formats = [
        "%Y-%m-%dT%H:%M:%S.%f",  # ISO format with microseconds
        "%Y-%m-%dT%H:%M:%S",     # ISO format
        "%Y-%m-%d %H:%M:%S",     # Standard format
        "%Y%m%d-%H%M%S",         # Timestamp format
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    return datetime.min


def extract_clean_timestamp(created_str: str) -> str:
    """Extract clean timestamp from snapshot created string."""
    if not created_str or created_str == "unknown":
        return "unknown"
    
    # Handle MinBackup snapshot format
    if "MinBackup snapshot created at" in created_str:
        try:
            # Extract timestamp after "at "
            timestamp_part = created_str.split("at ")[-1]
            # Remove any trailing characters like "…"
            timestamp_part = timestamp_part.split("…")[0].strip()
            
            # Try to parse and reformat
            dt = datetime.fromisoformat(timestamp_part.replace("â€¦", ""))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            # Fallback: just extract the visible part
            timestamp_part = created_str.split("at ")[-1]
            if len(timestamp_part) > 19:
                return timestamp_part[:19]
            return timestamp_part
    
    # Handle ISO format timestamps
    if "T" in created_str:
        try:
            dt = datetime.fromisoformat(created_str.replace("â€¦", ""))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            # Fallback: just show first 19 characters
            return created_str[:19].replace("T", " ")
    
    # For other formats, truncate if too long
    if len(created_str) > 19:
        return created_str[:19]
    
    return created_str


def get_vm_size_estimate(vm_name: str, platform_name: str) -> str:
    """Get estimated VM size."""
    try:
        if platform_name == "multipass":
            import subprocess
            result = subprocess.run(
                ["multipass", "info", vm_name, "--format", "json"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                vm_info = data.get("info", {}).get(vm_name, {})
                disk_usage = vm_info.get("disk_usage", "unknown")
                if disk_usage and disk_usage != "unknown":
                    return disk_usage
                
                # Try alternative field names
                for field in ["disk_used", "disk_size", "used"]:
                    if field in vm_info and vm_info[field]:
                        return str(vm_info[field])
        
        elif platform_name == "virtualbox":
            import subprocess
            # Get VM UUID first
            list_result = subprocess.run(
                ["vboxmanage", "list", "vms"],
                capture_output=True, text=True, timeout=10
            )
            if list_result.returncode == 0:
                for line in list_result.stdout.split('\n'):
                    if f'"{vm_name}"' in line:
                        # Extract UUID
                        import re
                        match = re.search(r'\{([^}]+)\}', line)
                        if match:
                            uuid = match.group(1)
                            # Get VM info
                            info_result = subprocess.run(
                                ["vboxmanage", "showvminfo", uuid, "--machinereadable"],
                                capture_output=True, text=True, timeout=10
                            )
                            if info_result.returncode == 0:
                                for info_line in info_result.stdout.split('\n'):
                                    if info_line.startswith('CfgFile='):
                                        cfg_path = info_line.split('=')[1].strip('"')
                                        try:
                                            cfg_dir = os.path.dirname(cfg_path)
                                            total_size = 0
                                            for root, dirs, files in os.walk(cfg_dir):
                                                for file in files:
                                                    file_path = os.path.join(root, file)
                                                    if os.path.exists(file_path):
                                                        total_size += os.path.getsize(file_path)
                                            
                                            # Convert to human readable
                                            if total_size > 1024**3:
                                                return f"{total_size / (1024**3):.1f}GB"
                                            elif total_size > 1024**2:
                                                return f"{total_size / (1024**2):.1f}MB"
                                            else:
                                                return f"{total_size / 1024:.1f}KB"
                                        except:
                                            pass
                            break
        
        return "unknown"
    except Exception:
        return "unknown"


def get_snapshot_size_estimate(vm_name: str, snapshot_name: str, platform_name: str) -> str:
    """Get estimated snapshot size (experimental)."""
    try:
        if platform_name == "multipass":
            # For Multipass, snapshots are typically incremental
            # We can estimate based on VM size, but actual snapshot size varies
            vm_size = get_vm_size_estimate(vm_name, platform_name)
            if vm_size != "unknown" and vm_size:
                # Estimate snapshot as 10-30% of VM size (very rough estimate)
                try:
                    if "GB" in vm_size:
                        size_num = float(vm_size.replace("GB", ""))
                        estimated = size_num * 0.2  # 20% estimate
                        if estimated > 1:
                            return f"~{estimated:.1f}GB"
                        else:
                            return f"~{estimated * 1024:.0f}MB"
                    elif "MB" in vm_size:
                        size_num = float(vm_size.replace("MB", ""))
                        estimated = size_num * 0.2
                        return f"~{estimated:.0f}MB"
                except:
                    pass
            
            return "~unknown"
        
        return "~unknown"
    except:
        return "~unknown"


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
    """MinBackup - VM Snapshot Management Tool.
    
    Lightweight VM snapshot automation with retention management.
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
@click.option('--example', '-e', type=click.Choice(['server', 'development']),
              help='Create example configuration')
@click.pass_context
def init(ctx, example: Optional[str]):
    """Initialize MinBackup configuration."""
    config_obj = ctx.obj['config']
    notifier_obj = ctx.obj['notifier']
    
    try:
        # Save configuration
        config_file = "minbackup.yaml"
        if example:
            config_file = f"minbackup-{example}.yaml"
            # Load example configuration if available
            example_config_path = Path(__file__).parent.parent.parent / "config" / "examples" / f"{example}.yaml"
            if example_config_path.exists():
                import yaml
                with open(example_config_path, 'r') as f:
                    example_config = yaml.safe_load(f)
                for key, value in example_config.items():
                    config_obj._config[key] = value
        
        config_obj.save(config_file)
        
        notifier_obj.success("MinBackup initialized successfully!")
        click.echo(f"Configuration saved to: {config_file}")
        
        # Check VM platforms
        vm_manager = VMManager(config_obj, notifier_obj)
        if vm_manager.available_platforms:
            click.echo(f"Available VM platforms: {', '.join(vm_manager.available_platforms.keys())}")
        else:
            click.echo("No VM platforms detected. Install multipass, VirtualBox, or VMware for VM snapshot support.")
        
    except Exception as e:
        notifier_obj.error(f"Initialization failed: {str(e)}")
        sys.exit(1)


@cli.command('list')
@click.option('--platform', '-p', help='Specific VM platform')
@click.option('--show-sizes', is_flag=True, help='Show VM disk usage')
@click.pass_context
def vm_list(ctx, platform: Optional[str], show_sizes: bool):
    """List all VMs and their snapshots with sizes."""
    config_obj = ctx.obj['config']
    notifier_obj = ctx.obj['notifier']
    
    try:
        vm_manager = VMManager(config_obj, notifier_obj)
        
        if not vm_manager.available_platforms:
            click.echo("No VM platforms available.")
            return
        
        click.echo(f"\n{format_status_icon('vm')} Virtual Machines & Snapshots")
        click.echo("=" * 80)
        
        all_vms = vm_manager.list_all_vms()
        
        for platform_name, vms in all_vms.items():
            if platform and platform != platform_name:
                continue
                
            click.echo(f"\n{platform_name.upper()}:")
            if not vms:
                click.echo("  No VMs found")
                continue
            
            for vm in vms:
                vm_icon = "[VM]" if not get_unicode_support() else "📱"
                vm_line = f"  {vm_icon} {vm['name']} ({vm.get('state', 'unknown')})"
                
                # Add VM size if requested
                if show_sizes:
                    vm_size = get_vm_size_estimate(vm['name'], platform_name)
                    vm_line += f" - Size: {vm_size}"
                
                click.echo(vm_line)
                
                # List snapshots
                try:
                    snapshots = vm_manager.list_snapshots(vm['name'], platform_name)
                    if snapshots:
                        click.echo(f"     📸 Snapshots: {len(snapshots)}")
                        
                        # Sort snapshots by date (newest first)
                        snapshots.sort(key=lambda x: parse_datetime(x.get('created_at', '')), reverse=True)
                        
                        for i, snapshot in enumerate(snapshots[:5]):  # Show first 5
                            created = extract_clean_timestamp(snapshot.get('created_at', 'unknown'))
                            
                            prefix = "       -"
                            if snapshot['name'].startswith('minbackup') or snapshot['name'].startswith('backup'):
                                prefix = "       📦"  # MinBackup snapshot
                            
                            click.echo(f"{prefix} {snapshot['name']} ({created})")
                        
                        if len(snapshots) > 5:
                            click.echo(f"       ... and {len(snapshots) - 5} more")
                    else:
                        click.echo("     No snapshots")
                        
                except Exception as e:
                    click.echo(f"     Snapshots: error - {str(e)}")
        
        # Summary
        total_vms = sum(len(vms) for vms in all_vms.values())
        total_snapshots = 0
        for platform_name, platform in vm_manager.available_platforms.items():
            for vm in all_vms.get(platform_name, []):
                try:
                    snapshots = vm_manager.list_snapshots(vm['name'], platform_name)
                    total_snapshots += len(snapshots)
                except:
                    pass
        
        click.echo(f"\n{format_status_icon('info')} Summary: {total_vms} VMs, {total_snapshots} snapshots")
        
    except Exception as e:
        notifier_obj.error(f"Failed to list VMs: {str(e)}")
        sys.exit(1)


@cli.command('snapshots')
@click.argument('vm_name')
@click.option('--platform', '-p', help='Specific VM platform')
@click.option('--sort', '-s', type=click.Choice(['name', 'date']), default='date',
              help='Sort snapshots by name or date')
@click.option('--details', is_flag=True, help='Show detailed snapshot information')
@click.option('--format', '-f', type=click.Choice(['table', 'json']), default='table',
              help='Output format')
@click.option('--show-sizes', is_flag=True, help='Show estimated snapshot sizes')
@click.pass_context
def vm_snapshots(ctx, vm_name: str, platform: Optional[str], sort: str, details: bool, 
                format: str, show_sizes: bool):
    """List snapshots for a specific VM with advanced options."""
    config_obj = ctx.obj['config']
    notifier_obj = ctx.obj['notifier']
    
    try:
        vm_manager = VMManager(config_obj, notifier_obj)
        snapshots = vm_manager.list_snapshots(vm_name, platform)
        
        if not snapshots:
            click.echo(f"No snapshots found for VM: {vm_name}")
            return
        
        # Get platform name for size estimation
        platform_name = platform
        if not platform_name:
            platform_obj = vm_manager._find_vm_platform(vm_name)
            if platform_obj:
                platform_name = platform_obj.platform_name
        
        # Sort snapshots
        if sort == 'date':
            snapshots.sort(key=lambda x: parse_datetime(x.get('created_at', '')), reverse=True)
        else:  # sort by name
            snapshots.sort(key=lambda x: x.get('name', ''))
        
        if format == 'json':
            click.echo(json.dumps(snapshots, indent=2))
            return
        
        # Table format
        click.echo(f"\n{format_status_icon('snapshot')} Snapshots for VM: {vm_name}")
        click.echo("=" * 90)
        
        if details:
            for i, snapshot in enumerate(snapshots, 1):
                # Updated icon logic for three types
                if snapshot['name'].startswith('auto'):
                    icon = "🤖"  # Robot for automatic
                    snap_type_full = "Automatic"
                elif snapshot['name'].startswith(('minbackup', 'backup')):
                    icon = "📦"  # Box for MinBackup
                    snap_type_full = "MinBackup"
                else:
                    icon = "📸"  # Camera for manual
                    snap_type_full = "Manual"
                
                click.echo(f"\n{i}. {icon} {snapshot['name']}")
                
                created = extract_clean_timestamp(snapshot.get('created_at', 'unknown'))
                click.echo(f"   Created: {created}")
                click.echo(f"   Platform: {snapshot.get('platform', 'unknown')}")
                click.echo(f"   Type: {snap_type_full}")
                
                if show_sizes and platform_name:
                    size_est = get_snapshot_size_estimate(vm_name, snapshot['name'], platform_name)
                    click.echo(f"   Est. Size: {size_est}")
        else:
            # Compact table format
            if show_sizes:
                header = f"{'#':<3} {'Type':<4} {'Name':<20} {'Created':<20} {'Est. Size':<10}"
                separator = "-" * 90
            else:
                header = f"{'#':<3} {'Type':<4} {'Name':<25} {'Created':<20}"
                separator = "-" * 70
            
            click.echo(header)
            click.echo(separator)
            
            for i, snapshot in enumerate(snapshots, 1):
                # Updated type logic for three types
                if snapshot['name'].startswith('auto'):
                    snap_type = "AUTO"
                elif snapshot['name'].startswith(('minbackup', 'backup')):
                    snap_type = "MB"
                else:
                    snap_type = "MAN"
                
                name = snapshot['name'][:19] if show_sizes else snapshot['name'][:24]
                created = extract_clean_timestamp(snapshot.get('created_at', 'unknown'))[:19]
                
                if show_sizes and platform_name:
                    size_est = get_snapshot_size_estimate(vm_name, snapshot['name'], platform_name)[:9]
                    row = f"{i:<3} {snap_type:<4} {name:<20} {created:<20} {size_est:<10}"
                else:
                    row = f"{i:<3} {snap_type:<4} {name:<25} {created:<20}"
                
                click.echo(row)
        
        click.echo(f"\nTotal snapshots: {len(snapshots)}")
        
        # Updated counts for three types
        auto_count = len([s for s in snapshots if s['name'].startswith('auto')])
        minbackup_count = len([s for s in snapshots if s['name'].startswith(('minbackup', 'backup'))])
        manual_count = len(snapshots) - auto_count - minbackup_count
        
        click.echo(f"Automatic snapshots: {auto_count}")
        click.echo(f"MinBackup snapshots: {minbackup_count}")
        click.echo(f"Manual snapshots: {manual_count}")
        
        if show_sizes:
            click.echo("\nNote: Snapshot sizes are estimates and may not reflect actual disk usage.")
        
    except Exception as e:
        notifier_obj.error(f"Failed to list snapshots: {str(e)}")
        sys.exit(1)

@cli.command('snapshot')
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
            click.echo(f"{format_status_icon('success')} Snapshot created for VM: {vm_name}")
        else:
            click.echo(f"{format_status_icon('error')} Failed to create snapshot for VM: {vm_name}")
            sys.exit(1)
            
    except Exception as e:
        notifier_obj.error(f"Snapshot creation failed: {str(e)}")
        sys.exit(1)


@cli.command('delete-snapshot')
@click.argument('vm_name')
@click.argument('snapshot_names', nargs=-1, required=True)
@click.option('--platform', '-p', help='Specific VM platform')
@click.option('--confirm', is_flag=True, help='Skip confirmation prompt')
@click.option('--no-purge', is_flag=True, help='Delete without purging (Multipass only)')
@click.pass_context
def vm_delete_snapshot(ctx, vm_name: str, snapshot_names: tuple, platform: Optional[str], 
                      confirm: bool, no_purge: bool):
    """Delete one or more VM snapshots."""
    config_obj = ctx.obj['config']
    notifier_obj = ctx.obj['notifier']
    
    try:
        vm_manager = VMManager(config_obj, notifier_obj)
        
        # Handle special keywords
        if len(snapshot_names) == 1 and snapshot_names[0].lower() == "all":
            # Delete all snapshots
            existing_snapshots = vm_manager.list_snapshots(vm_name, platform)
            
            if not existing_snapshots:
                click.echo(f"No snapshots found for VM: {vm_name}")
                return
            
            # Show what will be deleted
            click.echo(f"\n{format_status_icon('delete')} ALL snapshots to delete from VM '{vm_name}':")
            for snapshot in existing_snapshots:
                created = extract_clean_timestamp(snapshot.get('created_at', 'unknown'))
                click.echo(f"  - {snapshot['name']} (created: {created})")
            
            # Confirm deletion
            if not confirm:
                if not click.confirm(f"\nAre you sure you want to delete ALL {len(existing_snapshots)} snapshot(s)?"):
                    click.echo("Deletion cancelled.")
                    return
            
            # Delete all snapshots
            deleted_count = vm_manager.delete_all_snapshots(vm_name, platform, not no_purge)
            click.echo(f"\n{format_status_icon('info')} Deleted {deleted_count} of {len(existing_snapshots)} snapshots.")
            return
        
        # Delete specific snapshots
        existing_snapshots = vm_manager.list_snapshots(vm_name, platform)
        existing_names = [s['name'] for s in existing_snapshots]
        
        snapshots_to_delete = []
        for snapshot_name in snapshot_names:
            if snapshot_name in existing_names:
                snapshots_to_delete.append(snapshot_name)
            else:
                click.echo(f"{format_status_icon('warning')} Snapshot not found: {snapshot_name}")
        
        if not snapshots_to_delete:
            click.echo("No valid snapshots to delete.")
            return
        
        # Show what will be deleted
        click.echo(f"\n{format_status_icon('delete')} Snapshots to delete from VM '{vm_name}':")
        for snapshot_name in snapshots_to_delete:
            snapshot_info = next(s for s in existing_snapshots if s['name'] == snapshot_name)
            created = extract_clean_timestamp(snapshot_info.get('created_at', 'unknown'))
            click.echo(f"  - {snapshot_name} (created: {created})")
        
        # Confirm deletion
        if not confirm:
            action = "delete" if no_purge else "delete and purge"
            if not click.confirm(f"\nAre you sure you want to {action} {len(snapshots_to_delete)} snapshot(s)?"):
                click.echo("Deletion cancelled.")
                return
        
        # Delete snapshots
        deleted_count = 0
        for snapshot_name in snapshots_to_delete:
            success = vm_manager.delete_snapshot(vm_name, snapshot_name, platform, not no_purge)
            
            if success:
                deleted_count += 1
                action = "Deleted" if no_purge else "Deleted and purged"
                click.echo(f"{format_status_icon('success')} {action}: {snapshot_name}")
            else:
                click.echo(f"{format_status_icon('error')} Failed to delete: {snapshot_name}")
        
        click.echo(f"\n{format_status_icon('info')} Deleted {deleted_count} of {len(snapshots_to_delete)} snapshots.")
        
    except Exception as e:
        notifier_obj.error(f"Snapshot deletion failed: {str(e)}")
        sys.exit(1)


@cli.command('cleanup')
@click.option('--dry-run', is_flag=True, help='Show what would be deleted without actually deleting')
@click.pass_context
def vm_cleanup(ctx, dry_run: bool):
    """Clean up old VM snapshots based on retention policy."""
    config_obj = ctx.obj['config']
    notifier_obj = ctx.obj['notifier']
    
    try:
        vm_manager = VMManager(config_obj, notifier_obj)
        retention_count = config_obj.vm_snapshot_retention
        
        if dry_run:
            click.echo(f"{format_status_icon('info')} Dry run - showing what snapshots would be deleted:")
            click.echo(f"Retention policy: Keep last {retention_count} MinBackup snapshots per VM")
            click.echo("-" * 70)
            
            total_would_delete = 0
            
            for platform_name, platform in vm_manager.available_platforms.items():
                vms = platform.list_vms()
                platform_deletions = 0
                
                for vm in vms:
                    vm_name = vm["name"]
                    snapshots = platform.list_snapshots(vm_name)
                    
                    # Filter MinBackup snapshots
                    minbackup_snapshots = [
                        s for s in snapshots 
                        if s["name"].startswith("minbackup") or s["name"].startswith("backup")
                    ]
                    
                    if len(minbackup_snapshots) > retention_count:
                        try:
                            minbackup_snapshots.sort(key=lambda x: x.get("timestamp") or datetime.min, reverse=True)
                        except:
                            minbackup_snapshots.sort(key=lambda x: x.get("name", ""), reverse=True)
                        
                        old_snapshots = minbackup_snapshots[retention_count:]
                        
                        if old_snapshots:
                            click.echo(f"\n  VM: {vm_name} ({platform_name})")
                            click.echo(f"    Total MinBackup snapshots: {len(minbackup_snapshots)}")
                            click.echo(f"    Would keep: {retention_count}")
                            click.echo(f"    Would delete: {len(old_snapshots)}")
                            
                            for snapshot in old_snapshots:
                                created = extract_clean_timestamp(snapshot.get('created_at', 'unknown'))
                                click.echo(f"      📦 {snapshot['name']} (created: {created})")
                            
                            platform_deletions += len(old_snapshots)
                
                if platform_deletions > 0:
                    click.echo(f"\n  {platform_name.upper()}: {platform_deletions} snapshots would be deleted")
                    total_would_delete += platform_deletions
            
            click.echo(f"\n{format_status_icon('info')} Total snapshots that would be deleted: {total_would_delete}")
            
            if total_would_delete == 0:
                click.echo("No old MinBackup snapshots found that exceed retention policy.")
        else:
            click.echo(f"{format_status_icon('cleanup')} Starting VM snapshot cleanup...")
            click.echo(f"Retention policy: Keep last {retention_count} MinBackup snapshots per VM")
            
            cleanup_summary = vm_manager.cleanup_old_snapshots()
            
            click.echo(f"\n{format_status_icon('cleanup')} Cleanup Summary:")
            click.echo(f"VMs processed: {cleanup_summary['vms_processed']}")
            click.echo(f"Snapshots deleted: {cleanup_summary['total_deleted']}")
            
            if cleanup_summary['errors']:
                click.echo(f"Errors: {len(cleanup_summary['errors'])}")
                for error in cleanup_summary['errors']:
                    click.echo(f"  - {error}")
            
            if cleanup_summary['total_deleted'] == 0:
                click.echo(f"{format_status_icon('success')} No cleanup needed - all snapshots within retention limits.")
            else:
                click.echo(f"{format_status_icon('success')} VM snapshot cleanup completed successfully.")
        
    except Exception as e:
        notifier_obj.error(f"VM cleanup failed: {str(e)}")
        sys.exit(1)


@cli.command()
@click.option('--json', 'output_json', is_flag=True, help='Output in JSON format')
@click.pass_context
def status(ctx, output_json: bool):
    """Show VM snapshot status and statistics."""
    config_obj = ctx.obj['config']
    notifier_obj = ctx.obj['notifier']
    
    try:
        vm_manager = VMManager(config_obj, notifier_obj)
        
        # Get VM status with snapshot info
        vm_status = {
            "available_platforms": list(vm_manager.available_platforms.keys()),
            "total_vms": 0,
            "total_snapshots": 0,
            "minbackup_snapshots": 0,
            "vm_details": []
        }
        
        # Collect detailed VM and snapshot information
        for platform_name, platform in vm_manager.available_platforms.items():
            vms = platform.list_vms()
            vm_status["total_vms"] += len(vms)
            
            for vm in vms:
                snapshots = platform.list_snapshots(vm["name"])
                vm_status["total_snapshots"] += len(snapshots)
                
                minbackup_count = len([s for s in snapshots if s["name"].startswith("minbackup") or s["name"].startswith("backup")])
                vm_status["minbackup_snapshots"] += minbackup_count
                
                vm_detail = {
                    "name": vm["name"],
                    "platform": platform_name,
                    "state": vm.get("state", "unknown"),
                    "snapshot_count": len(snapshots),
                    "minbackup_snapshots": minbackup_count
                }
                
                vm_status["vm_details"].append(vm_detail)
        
        # Combined status
        status_info = {
            "vm": vm_status,
            "config": {
                "vm_snapshot_retention": config_obj.vm_snapshot_retention
            }
        }
        
        if output_json:
            click.echo(json.dumps(status_info, indent=2))
        else:
            click.echo(f"\n{format_status_icon('vm')} MinBackup VM Status")
            click.echo("=" * 50)
            
            # VM info
            click.echo(f"\n{format_status_icon('snapshot')} Virtual Machines:")
            click.echo(f"  Available Platforms: {', '.join(vm_status['available_platforms']) or 'None'}")
            click.echo(f"  Total VMs: {vm_status['total_vms']}")
            click.echo(f"  Total Snapshots: {vm_status['total_snapshots']}")
            click.echo(f"  MinBackup Snapshots: {vm_status['minbackup_snapshots']}")
            click.echo(f"  Snapshot Retention: Keep last {config_obj.vm_snapshot_retention}")
            
            if vm_status['vm_details']:
                click.echo(f"\n{format_status_icon('info')} VM Details:")
                for vm_detail in vm_status['vm_details']:
                    click.echo(f"    📱 {vm_detail['name']} ({vm_detail['platform']}):")
                    click.echo(f"      State: {vm_detail['state']}")
                    click.echo(f"      Snapshots: {vm_detail['snapshot_count']} total, {vm_detail['minbackup_snapshots']} MinBackup")
            
            click.echo(f"\n{format_status_icon('success')} System ready for VM snapshot management")
        
    except Exception as e:
        notifier_obj.error(f"Status check failed: {str(e)}")
        sys.exit(1)

@cli.group('auto')
@click.pass_context
def auto(ctx):
    """Automatic snapshot management commands."""
    pass

@auto.command('enable')
@click.argument('interval')
@click.pass_context
def auto_enable(ctx, interval: str):
    """Enable automatic snapshots with specified interval.
    
    INTERVAL: Time between snapshots (e.g., 10m, 2h, 1d)
    
    Examples:
      minbackup auto enable 30m    # Every 30 minutes
      minbackup auto enable 4h     # Every 4 hours  
      minbackup auto enable 1d     # Every day
    """
    config_obj = ctx.obj['config']
    notifier_obj = ctx.obj['notifier']
    
    try:
        scheduler = SnapshotScheduler(config_obj, notifier_obj)
        scheduler.enable(interval)
        
        click.echo(f"{format_status_icon('success')} Automatic snapshots enabled!")
        click.echo(f"Interval: {interval}")
        click.echo(f"Use 'minbackup auto start' to start the scheduler daemon.")
        
    except Exception as e:
        notifier_obj.error(f"Failed to enable automatic snapshots: {str(e)}")
        sys.exit(1)

@auto.command('disable')
@click.pass_context
def auto_disable(ctx):
    """Disable automatic snapshots."""
    config_obj = ctx.obj['config']
    notifier_obj = ctx.obj['notifier']
    
    try:
        scheduler = SnapshotScheduler(config_obj, notifier_obj)
        scheduler.disable()
        
        click.echo(f"{format_status_icon('success')} Automatic snapshots disabled!")
        
    except Exception as e:
        notifier_obj.error(f"Failed to disable automatic snapshots: {str(e)}")
        sys.exit(1)

@auto.command('start')
@click.pass_context
def auto_start(ctx):
    """Start the automatic snapshot scheduler daemon."""
    config_obj = ctx.obj['config']
    notifier_obj = ctx.obj['notifier']
    
    try:
        scheduler = SnapshotScheduler(config_obj, notifier_obj)
        
        if not scheduler.is_enabled():
            click.echo(f"{format_status_icon('error')} Automatic snapshots are not enabled.")
            click.echo("Use 'minbackup auto enable <interval>' first.")
            sys.exit(1)
        
        click.echo(f"{format_status_icon('info')} Starting scheduler daemon...")
        click.echo("Press Ctrl+C to stop the daemon.")
        
        try:
            scheduler.start_daemon()
            
            # Keep the main thread alive while daemon runs
            while scheduler.running:
                time.sleep(1)
                
        except KeyboardInterrupt:
            click.echo(f"\n{format_status_icon('info')} Stopping scheduler...")
            scheduler.stop_daemon()
            click.echo(f"{format_status_icon('success')} Scheduler stopped.")
        
    except Exception as e:
        notifier_obj.error(f"Failed to start scheduler: {str(e)}")
        sys.exit(1)

@auto.command('stop')
@click.pass_context
def auto_stop(ctx):
    """Stop the automatic snapshot scheduler daemon."""
    config_obj = ctx.obj['config']
    notifier_obj = ctx.obj['notifier']
    
    try:
        # For now, this is mainly for status - the daemon stops when you Ctrl+C
        click.echo(f"{format_status_icon('info')} To stop the daemon, use Ctrl+C in the terminal where it's running.")
        
    except Exception as e:
        notifier_obj.error(f"Failed to stop scheduler: {str(e)}")
        sys.exit(1)

@auto.command('status')
@click.option('--json', 'output_json', is_flag=True, help='Output in JSON format')
@click.pass_context
def auto_status(ctx, output_json: bool):
    """Show automatic snapshot scheduler status."""
    config_obj = ctx.obj['config']
    notifier_obj = ctx.obj['notifier']
    
    try:
        scheduler = SnapshotScheduler(config_obj, notifier_obj)
        status = scheduler.get_status()
        
        if output_json:
            click.echo(json.dumps(status, indent=2))
            return
        
        click.echo(f"\n{format_status_icon('info')} Automatic Snapshot Status")
        click.echo("=" * 50)
        
        # Status
        enabled_icon = "✅" if status["enabled"] else "❌"
        running_icon = "🟢" if status["running"] else "🔴"
        
        click.echo(f"\nEnabled: {enabled_icon} {status['enabled']}")
        click.echo(f"Daemon Running: {running_icon} {status['running']}")
        click.echo(f"Interval: {status['interval']}")
        
        # Timing
        if status["last_run"]:
            last_run = status["last_run"][:19].replace('T', ' ')
            click.echo(f"Last Run: {last_run}")
        else:
            click.echo("Last Run: Never")
        
        if status["next_run"]:
            next_run = status["next_run"][:19].replace('T', ' ')
            click.echo(f"Next Run: {next_run}")
        else:
            click.echo("Next Run: Not scheduled")
        
        # System info
        click.echo(f"\nVMs Monitored: {status['vm_count']}")
        click.echo(f"Total Snapshots: {status['total_snapshots']}")
        
        # Instructions
        if not status["enabled"]:
            click.echo(f"\n{format_status_icon('info')} To enable automatic snapshots:")
            click.echo("  minbackup auto enable <interval>")
            click.echo("  Example: minbackup auto enable 4h")
        elif not status["running"]:
            click.echo(f"\n{format_status_icon('info')} To start the scheduler:")
            click.echo("  minbackup auto start")
        else:
            click.echo(f"\n{format_status_icon('success')} Scheduler is running!")
        
    except Exception as e:
        notifier_obj.error(f"Failed to get scheduler status: {str(e)}")
        sys.exit(1)

@auto.command('run-now')
@click.pass_context
def auto_run_now(ctx):
    """Run automatic snapshots immediately (one-time)."""
    config_obj = ctx.obj['config']
    notifier_obj = ctx.obj['notifier']
    
    try:
        scheduler = SnapshotScheduler(config_obj, notifier_obj)
        
        if not scheduler.is_enabled():
            click.echo(f"{format_status_icon('error')} Automatic snapshots are not enabled.")
            click.echo("Use 'minbackup auto enable <interval>' first.")
            sys.exit(1)
        
        click.echo(f"{format_status_icon('info')} Running automatic snapshots now...")
        scheduler.run_now()
        click.echo(f"{format_status_icon('success')} Automatic snapshot run completed!")
        
    except Exception as e:
        notifier_obj.error(f"Failed to run automatic snapshots: {str(e)}")
        sys.exit(1)
        
def get_snapshot_type(snapshot_name: str) -> str:
    """Get snapshot type indicator."""
    if snapshot_name.startswith("auto"):
        return "AUTO"
    elif snapshot_name.startswith(("minbackup", "backup")):
        return "MB"
    else:
        return "MAN"

def get_snapshot_type_full(snapshot_name: str) -> str:
    """Get full snapshot type name."""
    if snapshot_name.startswith("auto"):
        return "Automatic"
    elif snapshot_name.startswith(("minbackup", "backup")):
        return "MinBackup"
    else:
        return "Manual"

def main():
    """Main entry point for CLI."""
    cli()


if __name__ == '__main__':
    main()