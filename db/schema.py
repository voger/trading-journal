"""
db.schema — Database schema SQL, seed data, init_database(), and _migrate().
"""

import sqlite3

from db.connection import DB_NAME, get_app_data_dir, get_db_path, get_connection

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

-- Custom SQL analytics queries (user-saved)
CREATE TABLE IF NOT EXISTS custom_queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    sql_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
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

# Only the formula INSERT — used by reset_formulas_to_defaults so it does not
# accidentally re-seed setup_types or app_settings that the user may have modified.
FORMULA_SEED_SQL = """
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


def init_database(db_path: str) -> str:
    """Initialize the database with schema and seed data. Returns the db_path used."""
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
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return db_path


def _migrate(conn):
    """Apply schema migrations for existing databases.

    Only contains migrations that cannot be expressed as CREATE TABLE IF NOT EXISTS
    (e.g. ALTER TABLE). All table and index creation lives in SCHEMA_SQL, which
    always runs before this function via executescript().
    """
    # Add chart_data column if missing (ALTER TABLE has no IF NOT EXISTS in SQLite)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(trades)").fetchall()]
    if 'chart_data' not in cols:
        conn.execute("ALTER TABLE trades ADD COLUMN chart_data TEXT")
