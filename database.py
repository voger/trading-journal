"""
Trading Journal - Database Layer
SQLite database initialization, schema creation, and data access functions.
"""

import sqlite3
import os
import sys
from datetime import datetime
from pathlib import Path

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


def get_db_path(app_data_dir: str = None) -> str:
    if app_data_dir:
        return os.path.join(app_data_dir, DB_NAME)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_NAME)


def get_connection(db_path: str = None) -> sqlite3.Connection:
    if db_path is None:
        db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


SCHEMA_SQL = """
-- Accounts
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    broker TEXT NOT NULL,
    account_number TEXT,
    account_type TEXT NOT NULL DEFAULT 'live',
    asset_type TEXT NOT NULL DEFAULT 'forex',
    currency TEXT NOT NULL DEFAULT 'EUR',
    initial_balance REAL NOT NULL DEFAULT 0,
    description TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Instruments
CREATE TABLE IF NOT EXISTS instruments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    instrument_type TEXT NOT NULL DEFAULT 'forex',
    exchange TEXT,
    pip_size REAL,
    tick_size REAL,
    tradingview_symbol TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Setup types
CREATE TABLE IF NOT EXISTS setup_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    timeframes TEXT,
    default_risk_percent REAL,
    target_rr_ratio REAL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Tags
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    color TEXT DEFAULT '#808080'
);

-- Trades
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    instrument_id INTEGER NOT NULL,
    direction TEXT NOT NULL,
    setup_type_id INTEGER,
    entry_date TEXT NOT NULL,
    entry_price REAL NOT NULL,
    position_size REAL NOT NULL,
    stop_loss_price REAL,
    take_profit_price REAL,
    exit_date TEXT,
    exit_price REAL,
    exit_reason TEXT,
    pnl_pips REAL,
    pnl_account_currency REAL,
    pnl_percent REAL,
    commission REAL DEFAULT 0,
    swap REAL DEFAULT 0,
    risk_percent REAL,
    risk_amount REAL,
    r_multiple REAL,
    timeframes_used TEXT,
    confidence_rating INTEGER,
    execution_grade TEXT,
    pre_trade_notes TEXT,
    post_trade_notes TEXT,
    broker_ticket_id TEXT,
    import_log_id INTEGER,
    status TEXT NOT NULL DEFAULT 'open',
    chart_data TEXT,
    is_excluded INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (account_id) REFERENCES accounts(id),
    FOREIGN KEY (instrument_id) REFERENCES instruments(id),
    FOREIGN KEY (setup_type_id) REFERENCES setup_types(id),
    FOREIGN KEY (import_log_id) REFERENCES import_logs(id),
    UNIQUE(account_id, broker_ticket_id)
);

-- Trade tags junction
CREATE TABLE IF NOT EXISTS trade_tags (
    trade_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (trade_id, tag_id),
    FOREIGN KEY (trade_id) REFERENCES trades(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

-- Trade charts
CREATE TABLE IF NOT EXISTS trade_charts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER NOT NULL,
    chart_type TEXT NOT NULL,
    timeframe TEXT,
    file_path TEXT NOT NULL,
    caption TEXT,
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (trade_id) REFERENCES trades(id) ON DELETE CASCADE
);

-- Watchlist items
CREATE TABLE IF NOT EXISTS watchlist_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER,
    instrument_id INTEGER NOT NULL,
    bias_weekly TEXT,
    bias_daily TEXT,
    bias_h4 TEXT,
    key_levels TEXT,
    notes TEXT,
    alert_notes TEXT,
    sort_order INTEGER DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (account_id) REFERENCES accounts(id),
    FOREIGN KEY (instrument_id) REFERENCES instruments(id),
    UNIQUE(account_id, instrument_id)
);

-- Import logs
CREATE TABLE IF NOT EXISTS import_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    plugin_name TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_hash TEXT,
    trades_found INTEGER NOT NULL DEFAULT 0,
    trades_imported INTEGER NOT NULL DEFAULT 0,
    trades_skipped INTEGER NOT NULL DEFAULT 0,
    trades_updated INTEGER NOT NULL DEFAULT 0,
    errors TEXT,
    imported_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);

-- Daily journal
CREATE TABLE IF NOT EXISTS daily_journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER,
    journal_date TEXT NOT NULL,
    market_conditions TEXT,
    emotional_state TEXT,
    followed_plan INTEGER,
    observations TEXT,
    lessons_learned TEXT,
    plan_for_tomorrow TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (account_id) REFERENCES accounts(id),
    UNIQUE(account_id, journal_date)
);

-- Formula definitions
CREATE TABLE IF NOT EXISTS formula_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_key TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    formula_text TEXT NOT NULL,
    description TEXT NOT NULL,
    interpretation TEXT,
    category TEXT NOT NULL
);

-- App settings
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Setup rules (checklist items for each setup)
CREATE TABLE IF NOT EXISTS setup_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    setup_type_id INTEGER NOT NULL,
    rule_type TEXT NOT NULL DEFAULT 'entry',
    rule_text TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (setup_type_id) REFERENCES setup_types(id) ON DELETE CASCADE
);

-- Trade rule compliance (which rules were followed per trade)
CREATE TABLE IF NOT EXISTS trade_rule_checks (
    trade_id INTEGER NOT NULL,
    rule_id INTEGER NOT NULL,
    was_met INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (trade_id, rule_id),
    FOREIGN KEY (trade_id) REFERENCES trades(id) ON DELETE CASCADE,
    FOREIGN KEY (rule_id) REFERENCES setup_rules(id) ON DELETE CASCADE
);

-- Account events (deposits, withdrawals)
CREATE TABLE IF NOT EXISTS account_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    amount REAL NOT NULL,
    event_date TEXT NOT NULL,
    description TEXT,
    broker_ticket_id TEXT,
    import_log_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
    UNIQUE(account_id, broker_ticket_id)
);

-- Setup example charts
CREATE TABLE IF NOT EXISTS setup_charts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    setup_type_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    caption TEXT,
    sort_order INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (setup_type_id) REFERENCES setup_types(id) ON DELETE CASCADE
);

-- Executions (raw buy/sell orders for lot-tracked instruments)
CREATE TABLE IF NOT EXISTS executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    instrument_id INTEGER NOT NULL,
    trade_id INTEGER,
    broker_order_id TEXT,
    action TEXT NOT NULL,
    shares REAL NOT NULL,
    price REAL NOT NULL,
    price_currency TEXT,
    exchange_rate REAL,
    total_account_currency REAL,
    commission REAL DEFAULT 0,
    broker_result REAL,
    executed_at TEXT NOT NULL,
    import_log_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
    FOREIGN KEY (instrument_id) REFERENCES instruments(id),
    FOREIGN KEY (trade_id) REFERENCES trades(id) ON DELETE SET NULL,
    FOREIGN KEY (import_log_id) REFERENCES import_logs(id),
    UNIQUE(account_id, broker_order_id)
);

-- Lot consumptions (FIFO matching: which buy lots were consumed by which sells)
CREATE TABLE IF NOT EXISTS lot_consumptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER NOT NULL,
    buy_execution_id INTEGER NOT NULL,
    sell_execution_id INTEGER NOT NULL,
    shares_consumed REAL NOT NULL,
    buy_price REAL NOT NULL,
    sell_price REAL NOT NULL,
    buy_exchange_rate REAL,
    sell_exchange_rate REAL,
    pnl_computed REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (trade_id) REFERENCES trades(id) ON DELETE CASCADE,
    FOREIGN KEY (buy_execution_id) REFERENCES executions(id),
    FOREIGN KEY (sell_execution_id) REFERENCES executions(id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_trades_account ON trades(account_id);
CREATE INDEX IF NOT EXISTS idx_trades_instrument ON trades(instrument_id);
CREATE INDEX IF NOT EXISTS idx_trades_entry_date ON trades(entry_date);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_dedup ON trades(account_id, broker_ticket_id);
CREATE INDEX IF NOT EXISTS idx_trades_account_status ON trades(account_id, status);
CREATE INDEX IF NOT EXISTS idx_watchlist_account ON watchlist_items(account_id);
CREATE INDEX IF NOT EXISTS idx_import_logs_account ON import_logs(account_id);
CREATE INDEX IF NOT EXISTS idx_trade_charts_trade ON trade_charts(trade_id);
CREATE INDEX IF NOT EXISTS idx_daily_journal_date ON daily_journal(journal_date);
CREATE INDEX IF NOT EXISTS idx_daily_journal_account ON daily_journal(account_id);
CREATE INDEX IF NOT EXISTS idx_setup_rules_setup ON setup_rules(setup_type_id);
CREATE INDEX IF NOT EXISTS idx_trade_rule_checks_trade ON trade_rule_checks(trade_id);
CREATE INDEX IF NOT EXISTS idx_account_events_account ON account_events(account_id);
CREATE INDEX IF NOT EXISTS idx_account_events_date ON account_events(event_date);
CREATE INDEX IF NOT EXISTS idx_setup_charts_setup ON setup_charts(setup_type_id);
CREATE INDEX IF NOT EXISTS idx_executions_account ON executions(account_id);
CREATE INDEX IF NOT EXISTS idx_executions_instrument ON executions(instrument_id);
CREATE INDEX IF NOT EXISTS idx_executions_trade ON executions(trade_id);
CREATE INDEX IF NOT EXISTS idx_executions_dedup ON executions(account_id, broker_order_id);
CREATE INDEX IF NOT EXISTS idx_executions_date ON executions(executed_at);
CREATE INDEX IF NOT EXISTS idx_lot_consumptions_trade ON lot_consumptions(trade_id);
CREATE INDEX IF NOT EXISTS idx_lot_consumptions_buy ON lot_consumptions(buy_execution_id);
CREATE INDEX IF NOT EXISTS idx_lot_consumptions_sell ON lot_consumptions(sell_execution_id);
CREATE INDEX IF NOT EXISTS idx_trades_account_entry_date ON trades(account_id, entry_date);
CREATE INDEX IF NOT EXISTS idx_trades_account_exit_date ON trades(account_id, exit_date);
"""

SEED_SQL = """
-- Default setup types
INSERT OR IGNORE INTO setup_types (name, description, timeframes, default_risk_percent, target_rr_ratio) VALUES
    ('Daily Trend Pullback to MA', 'Daily timeframe trend pullback to moving average zone', 'Weekly, Daily', 1.0, 3.0),
    ('Weekly Trend Pullback + Daily Reversal', 'Weekly trend pullback with daily reversal entry confirmation', 'Weekly, Daily', 1.0, 3.0),
    ('Range Trade', 'Trading within identified support/resistance range', 'Daily, H4', 1.0, 2.0);

-- Default app settings
INSERT OR IGNORE INTO app_settings (key, value) VALUES
    ('default_account_id', NULL),
    ('chart_data_provider', '"yahoo"'),
    ('chart_lookback_days', '90'),
    ('chart_post_exit_days', '30'),
    ('auto_backup_on_launch', 'true'),
    ('backup_directory', NULL),
    ('theme', '"light"');

-- Formula definitions
INSERT OR IGNORE INTO formula_definitions (metric_key, display_name, formula_text, description, interpretation, category) VALUES
    ('win_rate', 'Win Rate',
     '(Winning Trades ÷ Total Closed Trades) × 100',
     'Percentage of trades that were profitable.',
     'Above 50% is good for most strategies, but win rate alone is meaningless without considering risk:reward. A 30% win rate with 3:1 R:R is very profitable.',
     'performance'),
    ('expectancy', 'Expectancy (per trade)',
     '(Win Rate × Avg Win) − (Loss Rate × Avg Loss)',
     'The average amount you expect to gain or lose per trade over time.',
     'Must be positive for a profitable system. Higher is better. A negative expectancy means the system loses money long-term regardless of luck.',
     'performance'),
    ('profit_factor', 'Profit Factor',
     'Gross Profit ÷ Gross Loss',
     'Ratio of total money won to total money lost.',
     'Above 1.0 = profitable. Above 1.5 = good. Above 2.0 = excellent. Below 1.0 = losing system.',
     'performance'),
    ('avg_r_multiple', 'Average R-Multiple',
     'Sum of all R-multiples ÷ Number of trades',
     'Average return per trade expressed as a multiple of risk.',
     'Positive = profitable system. Above 0.5R is solid.',
     'performance'),
    ('risk_of_ruin', 'Risk of Ruin',
     '((1 − Edge) ÷ (1 + Edge)) ^ Capital_Units',
     'Probability of losing your entire account given your current stats and risk per trade.',
     'Below 1% is the goal. Above 5% means reduce position size or improve edge.',
     'risk'),
    ('max_drawdown', 'Maximum Drawdown',
     '(Peak Balance − Trough Balance) ÷ Peak Balance × 100',
     'The largest peak-to-trough decline in your account.',
     'Under 20% is manageable. Over 30% is psychologically very difficult to recover from.',
     'risk'),
    ('sharpe_ratio', 'Sharpe Ratio (simplified)',
     'Average Return ÷ Standard Deviation of Returns',
     'Measures risk-adjusted return.',
     'Above 1.0 is acceptable. Above 2.0 is very good.',
     'consistency');
"""


def init_database(db_path: str = None) -> str:
    """Initialize the database with schema and seed data. Returns the db_path used."""
    if db_path is None:
        db_path = get_db_path()
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.executescript(SEED_SQL)
        # Create asset module extra tables
        from asset_modules import get_extra_tables_sql
        for sql in get_extra_tables_sql():
            conn.execute(sql)
        # Migrations for existing databases
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()
    return db_path


def _migrate(conn):
    """Apply schema migrations for existing databases."""
    # Add chart_data column if missing
    cols = [r[1] for r in conn.execute("PRAGMA table_info(trades)").fetchall()]
    if 'chart_data' not in cols:
        conn.execute("ALTER TABLE trades ADD COLUMN chart_data TEXT")

    # Create executions table if missing (v2: FIFO lot tracking)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if 'executions' not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                instrument_id INTEGER NOT NULL,
                trade_id INTEGER,
                broker_order_id TEXT,
                action TEXT NOT NULL,
                shares REAL NOT NULL,
                price REAL NOT NULL,
                price_currency TEXT,
                exchange_rate REAL,
                total_account_currency REAL,
                commission REAL DEFAULT 0,
                broker_result REAL,
                executed_at TEXT NOT NULL,
                import_log_id INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
                FOREIGN KEY (instrument_id) REFERENCES instruments(id),
                FOREIGN KEY (trade_id) REFERENCES trades(id) ON DELETE SET NULL,
                FOREIGN KEY (import_log_id) REFERENCES import_logs(id),
                UNIQUE(account_id, broker_order_id)
            );
            CREATE TABLE IF NOT EXISTS lot_consumptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id INTEGER NOT NULL,
                buy_execution_id INTEGER NOT NULL,
                sell_execution_id INTEGER NOT NULL,
                shares_consumed REAL NOT NULL,
                buy_price REAL NOT NULL,
                sell_price REAL NOT NULL,
                buy_exchange_rate REAL,
                sell_exchange_rate REAL,
                pnl_computed REAL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (trade_id) REFERENCES trades(id) ON DELETE CASCADE,
                FOREIGN KEY (buy_execution_id) REFERENCES executions(id),
                FOREIGN KEY (sell_execution_id) REFERENCES executions(id)
            );
            CREATE INDEX IF NOT EXISTS idx_executions_account ON executions(account_id);
            CREATE INDEX IF NOT EXISTS idx_executions_instrument ON executions(instrument_id);
            CREATE INDEX IF NOT EXISTS idx_executions_trade ON executions(trade_id);
            CREATE INDEX IF NOT EXISTS idx_executions_dedup ON executions(account_id, broker_order_id);
            CREATE INDEX IF NOT EXISTS idx_executions_date ON executions(executed_at);
            CREATE INDEX IF NOT EXISTS idx_lot_consumptions_trade ON lot_consumptions(trade_id);
            CREATE INDEX IF NOT EXISTS idx_lot_consumptions_buy ON lot_consumptions(buy_execution_id);
            CREATE INDEX IF NOT EXISTS idx_lot_consumptions_sell ON lot_consumptions(sell_execution_id);
        """)

    # Composite index for the most common stats filter (account + status)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trades_account_status ON trades(account_id, status)"
    )
    # Composite index for queries that filter+sort by account+entry_date
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trades_account_entry_date ON trades(account_id, entry_date)"
    )
    # Composite index for stats queries that filter by account+exit_date
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trades_account_exit_date ON trades(account_id, exit_date)"
    )


# ── Data Access Functions ──────────────────────────────────────────────

# Accounts
def get_accounts(conn: sqlite3.Connection, active_only=True):
    sql = "SELECT * FROM accounts"
    if active_only:
        sql += " WHERE is_active = 1"
    sql += " ORDER BY name"
    return conn.execute(sql).fetchall()


def get_account(conn: sqlite3.Connection, account_id: int):
    return conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()


def create_account(conn: sqlite3.Connection, name, broker, currency='EUR',
                   account_number=None, account_type='live', asset_type='forex',
                   initial_balance=0, description=None):
    cur = conn.execute(
        """INSERT INTO accounts (name, broker, account_number, account_type, asset_type,
           currency, initial_balance, description) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, broker, account_number, account_type, asset_type, currency, initial_balance, description))
    conn.commit()
    return cur.lastrowid


def update_account(conn: sqlite3.Connection, account_id, **kwargs):
    allowed = {'name', 'broker', 'account_number', 'account_type', 'asset_type',
               'currency', 'initial_balance', 'description', 'is_active'}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    fields['updated_at'] = datetime.now().isoformat()
    set_clause = ', '.join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [account_id]
    conn.execute(f"UPDATE accounts SET {set_clause} WHERE id = ?", values)
    conn.commit()


# Instruments
def get_or_create_instrument(conn: sqlite3.Connection, symbol: str,
                             display_name: str = None, instrument_type: str = 'forex',
                             pip_size: float = None):
    symbol_clean = symbol.strip().upper()
    row = conn.execute("SELECT * FROM instruments WHERE symbol = ?", (symbol_clean,)).fetchone()
    if row:
        return row['id']
    if display_name is None:
        display_name = symbol_clean
    cur = conn.execute(
        "INSERT INTO instruments (symbol, display_name, instrument_type, pip_size) VALUES (?, ?, ?, ?)",
        (symbol_clean, display_name, instrument_type, pip_size))
    conn.commit()
    return cur.lastrowid


def get_instruments(conn: sqlite3.Connection):
    return conn.execute("SELECT * FROM instruments ORDER BY symbol").fetchall()


def get_instrument(conn: sqlite3.Connection, instrument_id: int):
    return conn.execute("SELECT * FROM instruments WHERE id = ?", (instrument_id,)).fetchone()


# Trades
def get_trades(conn: sqlite3.Connection, account_id=None, status=None,
               instrument_id=None, limit=500, offset=0, order_by='entry_date DESC'):
    sql = """SELECT t.*, a.name as account_name, a.currency as account_currency,
                    i.symbol, i.display_name as instrument_name, i.instrument_type,
                    st.name as setup_name
             FROM trades t
             JOIN accounts a ON t.account_id = a.id
             JOIN instruments i ON t.instrument_id = i.id
             LEFT JOIN setup_types st ON t.setup_type_id = st.id
             WHERE 1=1"""
    params = []
    if account_id is not None:
        sql += " AND t.account_id = ?"
        params.append(account_id)
    if status is not None:
        sql += " AND t.status = ?"
        params.append(status)
    if instrument_id is not None:
        sql += " AND t.instrument_id = ?"
        params.append(instrument_id)
    sql += f" ORDER BY {order_by} LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return conn.execute(sql, params).fetchall()


def get_trade(conn: sqlite3.Connection, trade_id: int):
    return conn.execute(
        """SELECT t.*, a.name as account_name, a.currency as account_currency,
                  i.symbol, i.display_name as instrument_name, i.instrument_type, i.pip_size,
                  st.name as setup_name
           FROM trades t
           JOIN accounts a ON t.account_id = a.id
           JOIN instruments i ON t.instrument_id = i.id
           LEFT JOIN setup_types st ON t.setup_type_id = st.id
           WHERE t.id = ?""", (trade_id,)).fetchone()


def create_trade(conn: sqlite3.Connection, **kwargs):
    columns = ', '.join(kwargs.keys())
    placeholders = ', '.join('?' * len(kwargs))
    cur = conn.execute(
        f"INSERT INTO trades ({columns}) VALUES ({placeholders})",
        list(kwargs.values()))
    conn.commit()
    return cur.lastrowid


def update_trade(conn: sqlite3.Connection, trade_id: int, **kwargs):
    if not kwargs:
        return
    kwargs['updated_at'] = datetime.now().isoformat()
    set_clause = ', '.join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [trade_id]
    conn.execute(f"UPDATE trades SET {set_clause} WHERE id = ?", values)
    conn.commit()


def delete_trade(conn: sqlite3.Connection, trade_id: int):
    # Collect file paths of attached screenshots/charts before deleting rows
    charts = conn.execute(
        "SELECT file_path FROM trade_charts WHERE trade_id = ?", (trade_id,)
    ).fetchall()
    for c in charts:
        fpath = c['file_path'] if isinstance(c, sqlite3.Row) else c[0]
        if fpath and os.path.exists(fpath):
            try: os.remove(fpath)
            except OSError: pass
    # Unlink executions (don't delete — they're raw data)
    conn.execute("UPDATE executions SET trade_id = NULL WHERE trade_id = ?", (trade_id,))
    # Clean up lot consumptions (CASCADE handles this, but be explicit)
    conn.execute("DELETE FROM lot_consumptions WHERE trade_id = ?", (trade_id,))
    # CASCADE will handle trade_charts, trade_tags, trade_rule_checks rows
    conn.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
    conn.commit()


def trade_exists(conn: sqlite3.Connection, account_id: int, broker_ticket_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM trades WHERE account_id = ? AND broker_ticket_id = ?",
        (account_id, broker_ticket_id)).fetchone()
    return row is not None


# Setup types
def get_setup_types(conn: sqlite3.Connection, active_only=True):
    sql = "SELECT * FROM setup_types"
    if active_only:
        sql += " WHERE is_active = 1"
    sql += " ORDER BY name"
    return conn.execute(sql).fetchall()


def create_setup_type(conn: sqlite3.Connection, name, description=None):
    cur = conn.execute("INSERT INTO setup_types (name, description) VALUES (?, ?)",
                       (name, description))
    conn.commit()
    return cur.lastrowid


# Tags
def get_tags(conn: sqlite3.Connection):
    return conn.execute("SELECT * FROM tags ORDER BY name").fetchall()


def get_trade_tags(conn: sqlite3.Connection, trade_id: int):
    return conn.execute(
        "SELECT t.* FROM tags t JOIN trade_tags tt ON t.id = tt.tag_id WHERE tt.trade_id = ?",
        (trade_id,)).fetchall()


def set_trade_tags(conn: sqlite3.Connection, trade_id: int, tag_ids: list):
    conn.execute("DELETE FROM trade_tags WHERE trade_id = ?", (trade_id,))
    for tag_id in tag_ids:
        conn.execute("INSERT INTO trade_tags (trade_id, tag_id) VALUES (?, ?)",
                     (trade_id, tag_id))
    conn.commit()


# Import logs
def create_import_log(conn: sqlite3.Connection, **kwargs):
    columns = ', '.join(kwargs.keys())
    placeholders = ', '.join('?' * len(kwargs))
    cur = conn.execute(
        f"INSERT INTO import_logs ({columns}) VALUES ({placeholders})",
        list(kwargs.values()))
    conn.commit()
    return cur.lastrowid


def get_import_logs(conn: sqlite3.Connection, account_id=None, limit=500):
    sql = """SELECT il.*, a.name as account_name
             FROM import_logs il JOIN accounts a ON il.account_id = a.id"""
    params = []
    if account_id is not None:
        sql += " WHERE il.account_id = ?"
        params.append(account_id)
    sql += " ORDER BY il.imported_at DESC LIMIT ?"
    params.append(limit)
    return conn.execute(sql, params).fetchall()


_EXECUTIONS_MODE_PLUGINS = {'trading212_csv'}  # fallback for environments where plugins can't be imported


def _plugin_is_executions_mode(plugin_name: str) -> bool:
    """Return True if the named plugin uses 'executions' import mode.

    Checks the plugin's IMPORT_MODE attribute dynamically so new plugins
    don't require a manual update here.  Falls back to the known set if the
    plugin module can't be imported (e.g. test environments).
    """
    try:
        from importlib import import_module
        mod = import_module(f'plugins.{plugin_name}')
        return getattr(mod, 'IMPORT_MODE', 'trades') == 'executions'
    except Exception:
        return plugin_name in _EXECUTIONS_MODE_PLUGINS


def delete_import_log(conn: sqlite3.Connection, log_id: int):
    """Delete an import log and all data imported with it.

    For executions-mode imports: deletes the raw executions linked to this log,
    then deletes all FIFO-built trades for the affected instruments so the caller
    can re-run FIFO on the remaining executions.

    For trades-mode imports: deletes trades linked to this log (cascades to
    lot_consumptions, trade_tags, trade_charts, trade_rule_checks).

    Returns (plugin_name, account_id, affected_instrument_ids) so the caller can
    trigger FIFO re-matching for executions-mode logs.  Returns (None, None, set())
    if the log does not exist.
    """
    log = conn.execute("SELECT * FROM import_logs WHERE id = ?", (log_id,)).fetchone()
    if not log:
        return None, None, set()

    plugin_name = log['plugin_name']
    account_id = log['account_id']
    affected_instruments = set()

    if _plugin_is_executions_mode(plugin_name):
        rows = conn.execute(
            "SELECT DISTINCT instrument_id FROM executions WHERE import_log_id = ?",
            (log_id,)
        ).fetchall()
        affected_instruments = {r['instrument_id'] for r in rows}

        # Delete FIFO-generated trades for affected instruments; the caller will
        # re-run FIFO on the remaining executions to rebuild correct trades.
        # Cascades: lot_consumptions, trade_tags, trade_charts, trade_rule_checks.
        for inst_id in affected_instruments:
            conn.execute(
                "DELETE FROM trades WHERE account_id = ? AND instrument_id = ?",
                (account_id, inst_id)
            )

        # Delete the raw executions for this log
        conn.execute("DELETE FROM executions WHERE import_log_id = ?", (log_id,))
    else:
        # Trades mode — delete trades directly (cascades to related rows)
        conn.execute("DELETE FROM trades WHERE import_log_id = ?", (log_id,))

    # Remove any balance events (deposits/withdrawals) tagged with this log
    conn.execute("DELETE FROM account_events WHERE import_log_id = ?", (log_id,))
    conn.execute("DELETE FROM import_logs WHERE id = ?", (log_id,))
    conn.commit()

    return plugin_name, account_id, affected_instruments


# Daily journal
def get_journal_entry(conn: sqlite3.Connection, journal_date: str, account_id=None):
    if account_id is not None:
        return conn.execute(
            "SELECT * FROM daily_journal WHERE journal_date = ? AND account_id = ?",
            (journal_date, account_id)).fetchone()
    return conn.execute(
        "SELECT * FROM daily_journal WHERE journal_date = ? AND account_id IS NULL",
        (journal_date,)).fetchone()


def save_journal_entry(conn: sqlite3.Connection, journal_date: str, account_id=None, **kwargs):
    existing = get_journal_entry(conn, journal_date, account_id)
    kwargs['updated_at'] = datetime.now().isoformat()
    if existing:
        set_clause = ', '.join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [existing['id']]
        conn.execute(f"UPDATE daily_journal SET {set_clause} WHERE id = ?", values)
    else:
        kwargs['journal_date'] = journal_date
        kwargs['account_id'] = account_id
        columns = ', '.join(kwargs.keys())
        placeholders = ', '.join('?' * len(kwargs))
        conn.execute(f"INSERT INTO daily_journal ({columns}) VALUES ({placeholders})",
                     list(kwargs.values()))
    conn.commit()


# Stats helpers
def get_trade_stats(conn: sqlite3.Connection, account_id=None,
                    date_from=None, date_to=None):
    """Get summary statistics for closed trades, plus open trade count."""
    sql = "SELECT * FROM trades WHERE status = 'closed' AND is_excluded = 0"
    open_sql = "SELECT COUNT(*) AS cnt FROM trades WHERE status = 'open' AND is_excluded = 0"
    params = []
    open_params = []
    if account_id is not None:
        sql += " AND account_id = ?"
        open_sql += " AND account_id = ?"
        params.append(account_id)
        open_params.append(account_id)
    if date_from is not None:
        sql += " AND exit_date >= ?"
        params.append(str(date_from))
    if date_to is not None:
        sql += " AND exit_date <= ?"
        params.append(str(date_to) + 'T23:59:59')
    trades = conn.execute(sql, params).fetchall()
    open_count = conn.execute(open_sql, open_params).fetchone()['cnt']

    if not trades:
        return None

    result = _compute_stats(trades)
    result['open_trades'] = open_count
    return result


def effective_pnl(t):
    """Return the true P/L for a trade: pnl + swap + commission.

    swap and commission are broker-reported costs/credits stored separately
    from the raw trade profit (e.g. MT4 plugin stores them apart). Including
    them here ensures win/loss classification and totals match broker statements.
    """
    return ((t['pnl_account_currency'] or 0)
            + (t['swap'] or 0)
            + (t['commission'] or 0))


def _compute_stats(trades):
    """Compute stats dict from a list of trade rows. Shared by summary and breakdowns."""
    total = len(trades)
    if total == 0:
        return None

    winners = [t for t in trades if effective_pnl(t) > 0]
    losers = [t for t in trades if effective_pnl(t) < 0]
    breakeven = [t for t in trades if effective_pnl(t) == 0]

    gross_profit = sum(effective_pnl(t) for t in winners)
    gross_loss = abs(sum(effective_pnl(t) for t in losers))
    net_pnl = sum(effective_pnl(t) for t in trades)

    avg_win = gross_profit / len(winners) if winners else 0
    avg_loss = gross_loss / len(losers) if losers else 0
    win_rate = len(winners) / total * 100 if total else 0

    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    expectancy = (win_rate / 100 * avg_win) - ((1 - win_rate / 100) * avg_loss)

    return {
        'total_trades': total,
        'winners': len(winners),
        'losers': len(losers),
        'breakeven': len(breakeven),
        'win_rate': win_rate,
        'gross_profit': gross_profit,
        'gross_loss': gross_loss,
        'net_pnl': net_pnl,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor,
        'expectancy': expectancy,
    }


# ── Session definitions for time-of-day grouping ──
# Based on standard forex market sessions (UTC)
TRADING_SESSIONS = {
    'Asian':   (0, 8),    # 00:00 - 07:59 UTC
    'London':  (8, 13),   # 08:00 - 12:59 UTC
    'New York': (13, 17), # 13:00 - 16:59 UTC
    'Late NY': (17, 21),  # 17:00 - 20:59 UTC
    'Off-hours': (21, 24), # 21:00 - 23:59 UTC
}


def _get_session(hour):
    """Map an hour (0-23) to a trading session name."""
    for name, (start, end) in TRADING_SESSIONS.items():
        if start <= hour < end:
            return name
    return 'Off-hours'


# ── Day-of-week names ──
_DOW_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def get_trade_breakdowns(conn: sqlite3.Connection, account_id: int, group_by: str,
                         date_from=None, date_to=None):
    """Get per-group performance stats for closed trades.

    group_by: 'instrument', 'setup', 'day_of_week', 'session', 'exit_reason',
              'direction', 'month'

    Returns: list of dicts, each with 'group_name' + all stats keys,
             sorted by net_pnl descending.
    """
    sql = """SELECT t.*, i.symbol, i.display_name as instrument_name,
                    st.name as setup_name
             FROM trades t
             JOIN instruments i ON t.instrument_id = i.id
             LEFT JOIN setup_types st ON t.setup_type_id = st.id
             WHERE t.status = 'closed' AND t.is_excluded = 0 AND t.account_id = ?"""
    params = [account_id]
    if date_from is not None:
        sql += " AND t.exit_date >= ?"
        params.append(str(date_from))
    if date_to is not None:
        sql += " AND t.exit_date <= ?"
        params.append(str(date_to) + 'T23:59:59')
    trades = conn.execute(sql, params).fetchall()

    if not trades:
        return []

    # Group trades by the requested dimension
    from collections import defaultdict
    from datetime import datetime as _dt
    groups = defaultdict(list)

    for t in trades:
        if group_by == 'instrument':
            key = t['symbol'] or '?'
        elif group_by == 'setup':
            key = t['setup_name'] or '(no setup)'
        elif group_by == 'day_of_week':
            try:
                dt = _dt.fromisoformat(t['entry_date'][:19])
                key = _DOW_NAMES[dt.weekday()]
            except (ValueError, TypeError):
                key = '?'
        elif group_by == 'session':
            try:
                dt = _dt.fromisoformat(t['entry_date'][:19])
                key = _get_session(dt.hour)
            except (ValueError, TypeError):
                key = '?'
        elif group_by == 'exit_reason':
            key = t['exit_reason'] or '(none)'
        elif group_by == 'direction':
            key = (t['direction'] or 'long').capitalize()
        elif group_by == 'month':
            try:
                key = t['exit_date'][:7]  # YYYY-MM — group by when P&L was realized
            except (TypeError, IndexError):
                key = '?'
        else:
            key = '?'
        groups[key].append(t)

    # Compute stats per group
    results = []
    for group_name, group_trades in groups.items():
        stats = _compute_stats(group_trades)
        if stats:
            stats['group_name'] = group_name
            results.append(stats)

    # Sort: for day_of_week preserve weekday order, for month preserve chronological
    if group_by == 'day_of_week':
        day_order = {name: i for i, name in enumerate(_DOW_NAMES)}
        results.sort(key=lambda r: day_order.get(r['group_name'], 99))
    elif group_by == 'month':
        results.sort(key=lambda r: r['group_name'])
    else:
        results.sort(key=lambda r: r['net_pnl'], reverse=True)

    return results


# ── Advanced Performance Metrics ─────────────────────────────────────────

def get_advanced_stats(conn: sqlite3.Connection, account_id=None,
                       date_from=None, date_to=None):
    """
    Compute advanced trading metrics from closed, non-excluded trades.

    Returns dict with:
        max_drawdown_pct: Maximum peak-to-trough % drawdown
        max_drawdown_abs: Maximum peak-to-trough absolute drawdown
        max_consecutive_wins: Longest winning streak
        max_consecutive_losses: Longest losing streak
        current_streak: +N for win streak, -N for loss streak, 0 for breakeven
        best_trade_pnl: Largest single-trade profit
        worst_trade_pnl: Largest single-trade loss
        avg_trade_duration_days: Average holding period for closed trades
        sharpe_ratio: Simplified Sharpe (mean return / stdev of returns)
        total_trades: count used for computation

    Returns None if no closed trades.
    """
    sql = """SELECT * FROM trades
             WHERE status = 'closed' AND is_excluded = 0"""
    params = []
    if account_id is not None:
        sql += " AND account_id = ?"
        params.append(account_id)
    if date_from is not None:
        sql += " AND exit_date >= ?"
        params.append(str(date_from))
    if date_to is not None:
        sql += " AND exit_date <= ?"
        params.append(str(date_to) + 'T23:59:59')
    sql += " ORDER BY exit_date, entry_date"

    trades = conn.execute(sql, params).fetchall()
    if not trades:
        return None

    pnls = [effective_pnl(t) for t in trades]
    n = len(pnls)

    # Use the account's initial balance as the equity starting point so that
    # drawdown percentages are relative to real capital, not just cumulative P/L.
    # Without this, a tiny early profit (e.g. +9.69) becomes the peak denominator
    # and produces absurd percentages like 4500%.
    initial_balance = 0.0
    if account_id is not None:
        acct_row = conn.execute(
            "SELECT initial_balance FROM accounts WHERE id = ?",
            (account_id,)).fetchone()
        if acct_row:
            initial_balance = float(acct_row['initial_balance'] or 0)

    # ── Streaks ──
    max_wins = 0
    max_losses = 0
    cur_wins = 0
    cur_losses = 0
    for p in pnls:
        if p > 0:
            cur_wins += 1
            cur_losses = 0
            max_wins = max(max_wins, cur_wins)
        elif p < 0:
            cur_losses += 1
            cur_wins = 0
            max_losses = max(max_losses, cur_losses)
        else:
            cur_wins = 0
            cur_losses = 0

    # Current streak: positive = wins, negative = losses
    current_streak = 0
    for p in reversed(pnls):
        if p > 0:
            if current_streak < 0:
                break
            current_streak += 1
        elif p < 0:
            if current_streak > 0:
                break
            current_streak -= 1
        else:
            break

    # ── Drawdown ──
    # Start from initial_balance so percentages are relative to real capital.
    # If initial_balance is 0 (not set), the peak will still be updated
    # correctly once equity goes positive.
    equity = initial_balance
    peak = initial_balance
    max_dd_abs = 0.0
    max_dd_pct = 0.0
    for p in pnls:
        equity += p
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd_abs:
            max_dd_abs = dd
        if peak > 0:
            dd_pct = dd / peak * 100
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

    # ── Best / Worst trade ──
    best_pnl = max(pnls)
    worst_pnl = min(pnls)

    # ── Average trade duration ──
    durations = []
    for t in trades:
        if t['entry_date'] and t['exit_date']:
            try:
                # Handle both datetime and date-only formats
                entry_str = t['entry_date'][:10]  # YYYY-MM-DD
                exit_str = t['exit_date'][:10]
                from datetime import datetime as dt
                entry_d = dt.strptime(entry_str, '%Y-%m-%d')
                exit_d = dt.strptime(exit_str, '%Y-%m-%d')
                days = (exit_d - entry_d).days
                if days >= 0:
                    durations.append(days)
            except (ValueError, TypeError):
                pass
    avg_duration = sum(durations) / len(durations) if durations else 0.0

    # ── Sharpe ratio (simplified: mean / stdev) ──
    mean_pnl = sum(pnls) / n
    if n > 1:
        variance = sum((p - mean_pnl) ** 2 for p in pnls) / (n - 1)
        stdev = variance ** 0.5
        sharpe = mean_pnl / stdev if stdev > 0 else float('inf')
    else:
        sharpe = 0.0

    return {
        'max_drawdown_pct': round(max_dd_pct, 2),
        'max_drawdown_abs': round(max_dd_abs, 2),
        'max_consecutive_wins': max_wins,
        'max_consecutive_losses': max_losses,
        'current_streak': current_streak,
        'best_trade_pnl': round(best_pnl, 2),
        'worst_trade_pnl': round(worst_pnl, 2),
        'avg_trade_duration_days': round(avg_duration, 1),
        'sharpe_ratio': round(sharpe, 3),
        'total_trades': n,
    }


# Formula definitions
def get_formula(conn: sqlite3.Connection, metric_key: str):
    return conn.execute("SELECT * FROM formula_definitions WHERE metric_key = ?",
                        (metric_key,)).fetchone()


def get_all_formulas(conn: sqlite3.Connection):
    return conn.execute("SELECT * FROM formula_definitions ORDER BY category, display_name").fetchall()


def update_formula(conn: sqlite3.Connection, metric_key: str, **kwargs):
    """Update a formula definition. Only allows editing text fields."""
    allowed = {'formula_text', 'description', 'interpretation', 'display_name', 'category'}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    set_clause = ', '.join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [metric_key]
    conn.execute(f"UPDATE formula_definitions SET {set_clause} WHERE metric_key = ?", values)
    conn.commit()


def reset_formulas_to_defaults(conn: sqlite3.Connection):
    """Delete all formula definitions and re-insert defaults from SEED_SQL."""
    conn.execute("DELETE FROM formula_definitions")
    # Re-run only the formula INSERT part of seed data
    conn.executescript(SEED_SQL)
    conn.commit()


# Setup management
def get_setup_type(conn: sqlite3.Connection, setup_id: int):
    return conn.execute("SELECT * FROM setup_types WHERE id = ?", (setup_id,)).fetchone()


def update_setup_type(conn: sqlite3.Connection, setup_id: int, **kwargs):
    allowed = {'name', 'description', 'timeframes', 'default_risk_percent', 'target_rr_ratio', 'is_active'}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    fields['updated_at'] = datetime.now().isoformat()
    set_clause = ', '.join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [setup_id]
    conn.execute(f"UPDATE setup_types SET {set_clause} WHERE id = ?", values)
    conn.commit()


def delete_setup_type(conn: sqlite3.Connection, setup_id: int):
    conn.execute("UPDATE trades SET setup_type_id = NULL WHERE setup_type_id = ?", (setup_id,))
    conn.execute("DELETE FROM setup_types WHERE id = ?", (setup_id,))
    conn.commit()


# Setup rules (checklists)
def get_setup_rules(conn: sqlite3.Connection, setup_id: int, rule_type: str = None):
    sql = "SELECT * FROM setup_rules WHERE setup_type_id = ?"
    params = [setup_id]
    if rule_type:
        sql += " AND rule_type = ?"
        params.append(rule_type)
    sql += " ORDER BY rule_type, sort_order"
    return conn.execute(sql, params).fetchall()


def add_setup_rule(conn: sqlite3.Connection, setup_id: int, rule_type: str, rule_text: str, sort_order: int = 0):
    cur = conn.execute(
        "INSERT INTO setup_rules (setup_type_id, rule_type, rule_text, sort_order) VALUES (?, ?, ?, ?)",
        (setup_id, rule_type, rule_text, sort_order))
    conn.commit()
    return cur.lastrowid


def update_setup_rule(conn: sqlite3.Connection, rule_id: int, rule_text: str):
    conn.execute("UPDATE setup_rules SET rule_text = ? WHERE id = ?", (rule_text, rule_id))
    conn.commit()


def delete_setup_rule(conn: sqlite3.Connection, rule_id: int):
    conn.execute("DELETE FROM setup_rules WHERE id = ?", (rule_id,))
    conn.commit()


# Trade rule checks
def get_trade_rule_checks(conn: sqlite3.Connection, trade_id: int):
    return conn.execute(
        """SELECT trc.*, sr.rule_text, sr.rule_type
           FROM trade_rule_checks trc
           JOIN setup_rules sr ON trc.rule_id = sr.id
           WHERE trc.trade_id = ?
           ORDER BY sr.rule_type, sr.sort_order""",
        (trade_id,)).fetchall()


def save_trade_rule_checks(conn: sqlite3.Connection, trade_id: int, checks: dict):
    """checks = {rule_id: was_met_bool, ...}"""
    conn.execute("DELETE FROM trade_rule_checks WHERE trade_id = ?", (trade_id,))
    for rule_id, was_met in checks.items():
        conn.execute(
            "INSERT INTO trade_rule_checks (trade_id, rule_id, was_met) VALUES (?, ?, ?)",
            (trade_id, rule_id, 1 if was_met else 0))
    conn.commit()


# Trade charts / screenshots
def add_trade_chart(conn: sqlite3.Connection, trade_id: int, chart_type: str,
                    file_path: str, timeframe: str = None, caption: str = None):
    cur = conn.execute(
        "INSERT INTO trade_charts (trade_id, chart_type, file_path, timeframe, caption) VALUES (?, ?, ?, ?, ?)",
        (trade_id, chart_type, file_path, timeframe, caption))
    conn.commit()
    return cur.lastrowid


def get_trade_charts(conn: sqlite3.Connection, trade_id: int):
    return conn.execute(
        "SELECT * FROM trade_charts WHERE trade_id = ? ORDER BY generated_at", (trade_id,)).fetchall()


def get_trade_chart_counts(conn: sqlite3.Connection, account_id=None):
    """Return {trade_id: count} for all trades. Single query instead of per-row."""
    sql = """SELECT tc.trade_id, COUNT(*) as cnt FROM trade_charts tc"""
    params = []
    if account_id is not None:
        sql += " JOIN trades t ON tc.trade_id = t.id WHERE t.account_id = ?"
        params.append(account_id)
    sql += " GROUP BY tc.trade_id"
    rows = conn.execute(sql, params).fetchall()
    return {r['trade_id']: r['cnt'] for r in rows}


def delete_trade_chart(conn: sqlite3.Connection, chart_id: int):
    chart = conn.execute("SELECT file_path FROM trade_charts WHERE id = ?", (chart_id,)).fetchone()
    conn.execute("DELETE FROM trade_charts WHERE id = ?", (chart_id,))
    conn.commit()
    return chart['file_path'] if chart else None


# Setup performance stats
def get_setup_stats(conn: sqlite3.Connection, setup_id: int, account_id=None):
    sql = """SELECT * FROM trades
             WHERE setup_type_id = ? AND status = 'closed' AND is_excluded = 0"""
    params = [setup_id]
    if account_id is not None:
        sql += " AND account_id = ?"
        params.append(account_id)
    trades = conn.execute(sql, params).fetchall()
    if not trades:
        return None
    stats = _compute_stats(trades)
    if stats is None:
        return None
    # Backward-compat: setups tab uses 'total' not 'total_trades'
    stats['total'] = stats['total_trades']
    return stats


# Account events (deposits/withdrawals)
def add_account_event(conn: sqlite3.Connection, account_id: int, event_type: str,
                      amount: float, event_date: str, description: str = None,
                      broker_ticket_id: str = None, import_log_id: int = None):
    cur = conn.execute(
        """INSERT OR IGNORE INTO account_events
           (account_id, event_type, amount, event_date, description, broker_ticket_id, import_log_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (account_id, event_type, amount, event_date, description, broker_ticket_id, import_log_id))
    conn.commit()
    return cur.lastrowid


def get_account_events(conn: sqlite3.Connection, account_id: int):
    return conn.execute(
        "SELECT * FROM account_events WHERE account_id = ? ORDER BY event_date",
        (account_id,)).fetchall()


def account_event_exists(conn: sqlite3.Connection, account_id: int, broker_ticket_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM account_events WHERE account_id = ? AND broker_ticket_id = ?",
        (account_id, broker_ticket_id)).fetchone()
    return row is not None


# Account delete
def delete_account(conn: sqlite3.Connection, account_id: int):
    """Delete an account and all associated data."""
    conn.execute("DELETE FROM trades WHERE account_id = ?", (account_id,))
    conn.execute("DELETE FROM account_events WHERE account_id = ?", (account_id,))
    conn.execute("DELETE FROM watchlist_items WHERE account_id = ?", (account_id,))
    conn.execute("DELETE FROM import_logs WHERE account_id = ?", (account_id,))
    conn.execute("DELETE FROM daily_journal WHERE account_id = ?", (account_id,))
    conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    conn.commit()


# Setup charts (example images)
def add_setup_chart(conn: sqlite3.Connection, setup_id: int, file_path: str,
                    caption: str = None, sort_order: int = 0):
    cur = conn.execute(
        "INSERT INTO setup_charts (setup_type_id, file_path, caption, sort_order) VALUES (?, ?, ?, ?)",
        (setup_id, file_path, caption, sort_order))
    conn.commit()
    return cur.lastrowid


def get_setup_charts(conn: sqlite3.Connection, setup_id: int):
    return conn.execute(
        "SELECT * FROM setup_charts WHERE setup_type_id = ? ORDER BY sort_order",
        (setup_id,)).fetchall()


def delete_setup_chart(conn: sqlite3.Connection, chart_id: int):
    chart = conn.execute("SELECT file_path FROM setup_charts WHERE id = ?", (chart_id,)).fetchone()
    conn.execute("DELETE FROM setup_charts WHERE id = ?", (chart_id,))
    conn.commit()
    return chart['file_path'] if chart else None


# ── Executions (for lot-tracked stock trades) ────────────────────────
def create_execution(conn: sqlite3.Connection, **kwargs):
    """Insert a raw execution (buy or sell order)."""
    columns = ', '.join(kwargs.keys())
    placeholders = ', '.join('?' * len(kwargs))
    cur = conn.execute(
        f"INSERT INTO executions ({columns}) VALUES ({placeholders})",
        list(kwargs.values()))
    conn.commit()
    return cur.lastrowid


def execution_exists(conn: sqlite3.Connection, account_id: int, broker_order_id: str) -> bool:
    """Check if an execution with this broker order ID already exists."""
    row = conn.execute(
        "SELECT 1 FROM executions WHERE account_id = ? AND broker_order_id = ?",
        (account_id, broker_order_id)).fetchone()
    return row is not None


def get_execution_count_for_trade(conn: sqlite3.Connection, trade_id: int) -> int:
    """Quick count of executions linked to a trade."""
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM executions WHERE trade_id = ?",
        (trade_id,)).fetchone()
    return row['cnt'] if row else 0


# Equity curve with events
def get_equity_curve_data(conn: sqlite3.Connection, account_id=None):
    """Return trades for equity curve, ordered by exit_date."""
    sql = """SELECT t.exit_date, t.pnl_account_currency, t.swap, t.commission,
                    a.initial_balance, a.currency as account_currency
             FROM trades t
             JOIN accounts a ON t.account_id = a.id
             WHERE t.status = 'closed' AND t.is_excluded = 0 AND t.exit_date IS NOT NULL"""
    params = []
    if account_id is not None:
        sql += " AND t.account_id = ?"
        params.append(account_id)
    sql += " ORDER BY t.exit_date"
    return conn.execute(sql, params).fetchall()


# ── Watchlist ──────────────────────────────────────────────────────────

def get_watchlist(conn: sqlite3.Connection, account_id=None):
    """Get watchlist items, optionally filtered by account."""
    sql = """SELECT w.*, i.symbol, i.display_name as instrument_name, i.instrument_type
             FROM watchlist_items w
             JOIN instruments i ON w.instrument_id = i.id
             WHERE w.is_active = 1"""
    params = []
    if account_id is not None:
        sql += " AND (w.account_id = ? OR w.account_id IS NULL)"
        params.append(account_id)
    sql += " ORDER BY w.sort_order, i.symbol"
    return conn.execute(sql, params).fetchall()


def get_watchlist_item(conn: sqlite3.Connection, item_id: int):
    return conn.execute(
        """SELECT w.*, i.symbol, i.display_name as instrument_name, i.instrument_type
           FROM watchlist_items w
           JOIN instruments i ON w.instrument_id = i.id
           WHERE w.id = ?""", (item_id,)).fetchone()


def add_watchlist_item(conn: sqlite3.Connection, instrument_id: int,
                       account_id=None, **kwargs):
    kwargs['instrument_id'] = instrument_id
    kwargs['account_id'] = account_id
    kwargs['updated_at'] = datetime.now().isoformat()
    columns = ', '.join(kwargs.keys())
    placeholders = ', '.join('?' * len(kwargs))
    cur = conn.execute(
        f"INSERT INTO watchlist_items ({columns}) VALUES ({placeholders})",
        list(kwargs.values()))
    conn.commit()
    return cur.lastrowid


def update_watchlist_item(conn: sqlite3.Connection, item_id: int, **kwargs):
    if not kwargs:
        return
    kwargs['updated_at'] = datetime.now().isoformat()
    set_clause = ', '.join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [item_id]
    conn.execute(f"UPDATE watchlist_items SET {set_clause} WHERE id = ?", values)
    conn.commit()


def delete_watchlist_item(conn: sqlite3.Connection, item_id: int):
    conn.execute("DELETE FROM watchlist_items WHERE id = ?", (item_id,))
    conn.commit()


def reorder_watchlist(conn: sqlite3.Connection, item_ids: list):
    """Set sort_order based on position in the list."""
    for i, item_id in enumerate(item_ids):
        conn.execute("UPDATE watchlist_items SET sort_order = ? WHERE id = ?", (i, item_id))
    conn.commit()


def get_equity_events(conn: sqlite3.Connection, account_id=None):
    """Return deposits/withdrawals for equity curve overlay."""
    sql = "SELECT * FROM account_events WHERE 1=1"
    params = []
    if account_id is not None:
        sql += " AND account_id = ?"
        params.append(account_id)
    sql += " ORDER BY event_date"
    return conn.execute(sql, params).fetchall()


# ── CSV Export ───────────────────────────────────────────────────────────

def get_trades_for_export(conn: sqlite3.Connection, account_id: int,
                          status_filter: str = None,
                          date_from: str = None, date_to: str = None):
    """Retrieve trades with joined info, ready for CSV export.

    Returns list of sqlite3.Row with flat columns including:
    account_name, currency, symbol, instrument_name, setup_name,
    plus all trades columns.

    Args:
        account_id: required account filter
        status_filter: 'open', 'closed', or None for all
        date_from: ISO date string, inclusive lower bound on entry_date
        date_to: ISO date string, inclusive upper bound on entry_date
    """
    sql = """SELECT t.*,
                    a.name as account_name, a.currency as account_currency,
                    i.symbol, i.display_name as instrument_name,
                    i.instrument_type,
                    st.name as setup_name
             FROM trades t
             JOIN accounts a ON t.account_id = a.id
             JOIN instruments i ON t.instrument_id = i.id
             LEFT JOIN setup_types st ON t.setup_type_id = st.id
             WHERE t.account_id = ?"""
    params = [account_id]

    if status_filter:
        sql += " AND t.status = ?"
        params.append(status_filter)
    if date_from:
        sql += " AND t.entry_date >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND t.entry_date <= ?"
        params.append(date_to + 'T23:59:59')

    sql += " ORDER BY t.entry_date"
    return conn.execute(sql, params).fetchall()


# Column definitions for CSV export
EXPORT_COLUMNS = [
    ('entry_date',              'Entry Date'),
    ('exit_date',               'Exit Date'),
    ('symbol',                  'Symbol'),
    ('instrument_name',         'Instrument'),
    ('direction',               'Direction'),
    ('entry_price',             'Entry Price'),
    ('exit_price',              'Exit Price'),
    ('position_size',           'Size'),
    ('stop_loss_price',         'Stop Loss'),
    ('take_profit_price',       'Take Profit'),
    ('pnl_account_currency',    'P&L'),
    ('pnl_pips',                'P&L Pips'),
    ('pnl_percent',             'P&L %'),
    ('commission',              'Commission'),
    ('swap',                    'Swap'),
    ('risk_percent',            'Risk %'),
    ('risk_amount',             'Risk Amount'),
    ('r_multiple',              'R Multiple'),
    ('setup_name',              'Setup'),
    ('exit_reason',             'Exit Reason'),
    ('execution_grade',         'Grade'),
    ('confidence_rating',       'Confidence'),
    ('status',                  'Status'),
    ('pre_trade_notes',         'Pre-Trade Notes'),
    ('post_trade_notes',        'Post-Trade Notes'),
    ('timeframes_used',         'Timeframes'),
    ('account_name',            'Account'),
    ('account_currency',        'Currency'),
    ('broker_ticket_id',        'Ticket ID'),
]
