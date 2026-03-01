"""
Backup and Restore Manager
Handles creating and restoring zip backups of the database and associated files.
"""

import os
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path


def get_app_data_dir(base_dir: str) -> dict:
    """Return paths to key app data locations."""
    return {
        'db': os.path.join(base_dir, 'trading_journal.db'),
        'charts': os.path.join(base_dir, 'charts'),
        'screenshots': os.path.join(base_dir, 'screenshots'),
        'backups': os.path.join(base_dir, 'backups'),
    }


def create_backup(app_dir: str, backup_dir: str = None) -> str:
    """
    Create a zip backup of the database and all associated files.
    Returns the path to the backup file.
    """
    paths = get_app_data_dir(app_dir)

    if backup_dir is None:
        backup_dir = paths['backups']
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    backup_name = f"trading_journal_backup_{timestamp}.zip"
    backup_path = os.path.join(backup_dir, backup_name)

    manifest = {
        'backup_date': datetime.now().isoformat(),
        'backup_name': backup_name,
    }

    with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Database
        db_path = paths['db']
        if os.path.exists(db_path):
            zf.write(db_path, 'trading_journal.db')

        # Charts folder
        charts_dir = paths['charts']
        if os.path.exists(charts_dir):
            for root, dirs, files in os.walk(charts_dir):
                for file in files:
                    full_path = os.path.join(root, file)
                    arc_path = os.path.join('charts', os.path.relpath(full_path, charts_dir))
                    zf.write(full_path, arc_path)

        # Screenshots folder
        ss_dir = paths['screenshots']
        if os.path.exists(ss_dir):
            for root, dirs, files in os.walk(ss_dir):
                for file in files:
                    full_path = os.path.join(root, file)
                    arc_path = os.path.join('screenshots', os.path.relpath(full_path, ss_dir))
                    zf.write(full_path, arc_path)

        # Manifest
        zf.writestr('manifest.json', json.dumps(manifest, indent=2))

    return backup_path


def restore_backup(backup_path: str, app_dir: str) -> dict:
    """
    Restore a backup zip to the app data directory.
    Returns dict with success status and message.
    """
    result = {'success': False, 'message': ''}

    if not os.path.exists(backup_path):
        result['message'] = f"Backup file not found: {backup_path}"
        return result

    if not zipfile.is_zipfile(backup_path):
        result['message'] = "Invalid backup file (not a zip)."
        return result

    try:
        with zipfile.ZipFile(backup_path, 'r') as zf:
            # Verify it contains a database
            names = zf.namelist()
            if 'trading_journal.db' not in names:
                result['message'] = "Backup does not contain a database file."
                return result

            # Validate member paths to prevent path traversal attacks
            app_dir_real = os.path.realpath(app_dir)
            for member in zf.infolist():
                dest = os.path.realpath(os.path.join(app_dir, member.filename))
                if not dest.startswith(app_dir_real + os.sep) and dest != app_dir_real:
                    result['message'] = f"Backup contains unsafe path: {member.filename}"
                    return result

            # Extract everything to app_dir
            zf.extractall(app_dir)

        result['success'] = True
        result['message'] = "Backup restored successfully."
    except Exception as e:
        result['message'] = f"Restore failed: {e}"

    return result


def list_backups(backup_dir: str) -> list:
    """List available backups sorted by date (newest first)."""
    if not os.path.exists(backup_dir):
        return []

    backups = []
    for f in os.listdir(backup_dir):
        if f.endswith('.zip') and f.startswith('trading_journal_backup_'):
            full_path = os.path.join(backup_dir, f)
            stat = os.stat(full_path)
            backups.append({
                'filename': f,
                'path': full_path,
                'size_mb': round(stat.st_size / 1024 / 1024, 2),
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })

    backups.sort(key=lambda x: x['modified'], reverse=True)
    return backups
