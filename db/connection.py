"""
db.connection — Database connection helpers.
DB_NAME, get_app_data_dir(), get_db_path(), get_connection()
"""

import sqlite3
import os
import sys

DB_NAME = "trading_journal.db"


def get_app_data_dir() -> str:
    """Return the platform-appropriate user data directory for Trading Journal.

    Linux:   $XDG_DATA_HOME/TradingJournal  (~/.local/share/TradingJournal)
    macOS:   ~/Library/Application Support/TradingJournal
    Windows: %APPDATA%\\TradingJournal
    """
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA', os.path.expanduser('~'))
    elif sys.platform == 'darwin':
        base = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support')
    else:
        base = os.environ.get('XDG_DATA_HOME',
                               os.path.join(os.path.expanduser('~'), '.local', 'share'))
    return os.path.join(base, 'TradingJournal')


def get_db_path(app_data_dir: str) -> str:
    return os.path.join(app_data_dir, DB_NAME)


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
