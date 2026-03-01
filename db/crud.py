"""
db.crud — All CRUD data-access functions.
Accounts, instruments, trades, setups, tags, charts, watchlist,
journal, events, executions, import logs, formulas, settings.
"""

import sqlite3
import os
from datetime import datetime

from db.schema import SEED_SQL

_VALID_ORDER_BY = frozenset({
    'entry_date DESC', 'entry_date ASC',
    'exit_date DESC',  'exit_date ASC',
})


# ── Accounts ──────────────────────────────────────────────────────────────

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


def delete_account(conn: sqlite3.Connection, account_id: int):
    """Delete an account and all associated data."""
    try:
        conn.execute("DELETE FROM trades WHERE account_id = ?", (account_id,))
        conn.execute("DELETE FROM account_events WHERE account_id = ?", (account_id,))
        conn.execute("DELETE FROM watchlist_items WHERE account_id = ?", (account_id,))
        conn.execute("DELETE FROM import_logs WHERE account_id = ?", (account_id,))
        conn.execute("DELETE FROM daily_journal WHERE account_id = ?", (account_id,))
        conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# ── Instruments ───────────────────────────────────────────────────────────

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


# ── Trades ────────────────────────────────────────────────────────────────

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
    if order_by not in _VALID_ORDER_BY:
        raise ValueError(f"Invalid order_by: {order_by!r}")
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


_UPDATE_TRADE_ALLOWED = {
    'account_id', 'instrument_id', 'direction', 'setup_type_id',
    'entry_date', 'entry_price', 'position_size', 'stop_loss_price',
    'take_profit_price', 'exit_date', 'exit_price', 'exit_reason',
    'pnl_pips', 'pnl_account_currency', 'pnl_percent', 'commission',
    'swap', 'risk_percent', 'risk_amount', 'r_multiple', 'timeframes_used',
    'confidence_rating', 'execution_grade', 'pre_trade_notes',
    'post_trade_notes', 'broker_ticket_id', 'import_log_id', 'status',
    'chart_data', 'is_excluded',
}


def update_trade(conn: sqlite3.Connection, trade_id: int, **kwargs):
    fields = {k: v for k, v in kwargs.items() if k in _UPDATE_TRADE_ALLOWED}
    if not fields:
        return
    fields['updated_at'] = datetime.now().isoformat()
    set_clause = ', '.join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [trade_id]
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
    try:
        # Unlink executions (don't delete — they're raw data)
        conn.execute("UPDATE executions SET trade_id = NULL WHERE trade_id = ?", (trade_id,))
        # Clean up lot consumptions (CASCADE handles this, but be explicit)
        conn.execute("DELETE FROM lot_consumptions WHERE trade_id = ?", (trade_id,))
        # CASCADE will handle trade_charts, trade_tags, trade_rule_checks rows
        conn.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def trade_exists(conn: sqlite3.Connection, account_id: int, broker_ticket_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM trades WHERE account_id = ? AND broker_ticket_id = ?",
        (account_id, broker_ticket_id)).fetchone()
    return row is not None


# ── Setup types ───────────────────────────────────────────────────────────

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


# ── Setup rules (checklists) ──────────────────────────────────────────────

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


# ── Tags ──────────────────────────────────────────────────────────────────

def get_tags(conn: sqlite3.Connection):
    return conn.execute("SELECT * FROM tags ORDER BY name").fetchall()


def get_trade_tags(conn: sqlite3.Connection, trade_id: int):
    return conn.execute(
        "SELECT t.* FROM tags t JOIN trade_tags tt ON t.id = tt.tag_id WHERE tt.trade_id = ?",
        (trade_id,)).fetchall()


def set_trade_tags(conn: sqlite3.Connection, trade_id: int, tag_ids: list):
    try:
        conn.execute("DELETE FROM trade_tags WHERE trade_id = ?", (trade_id,))
        for tag_id in tag_ids:
            conn.execute("INSERT INTO trade_tags (trade_id, tag_id) VALUES (?, ?)",
                         (trade_id, tag_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def get_or_create_tag(conn: sqlite3.Connection, name: str) -> int:
    """Return the id for a tag, creating it if it doesn't exist."""
    name = name.strip()
    conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
    conn.commit()
    return conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()['id']


# ── Trade rule checks ─────────────────────────────────────────────────────

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
    try:
        conn.execute("DELETE FROM trade_rule_checks WHERE trade_id = ?", (trade_id,))
        for rule_id, was_met in checks.items():
            conn.execute(
                "INSERT INTO trade_rule_checks (trade_id, rule_id, was_met) VALUES (?, ?, ?)",
                (trade_id, rule_id, 1 if was_met else 0))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# ── Trade charts / screenshots ────────────────────────────────────────────

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


# ── Setup charts (example images) ────────────────────────────────────────

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


# ── Import logs ───────────────────────────────────────────────────────────

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


# ── Daily journal ─────────────────────────────────────────────────────────

def get_journal_entry(conn: sqlite3.Connection, journal_date: str, account_id=None):
    if account_id is not None:
        return conn.execute(
            "SELECT * FROM daily_journal WHERE journal_date = ? AND account_id = ?",
            (journal_date, account_id)).fetchone()
    return conn.execute(
        "SELECT * FROM daily_journal WHERE journal_date = ? AND account_id IS NULL",
        (journal_date,)).fetchone()


_JOURNAL_ALLOWED = {
    'market_conditions', 'emotional_state', 'followed_plan',
    'observations', 'lessons_learned', 'plan_for_tomorrow',
}


def save_journal_entry(conn: sqlite3.Connection, journal_date: str, account_id=None, **kwargs):
    fields = {k: v for k, v in kwargs.items() if k in _JOURNAL_ALLOWED}
    existing = get_journal_entry(conn, journal_date, account_id)
    fields['updated_at'] = datetime.now().isoformat()
    if existing:
        set_clause = ', '.join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [existing['id']]
        conn.execute(f"UPDATE daily_journal SET {set_clause} WHERE id = ?", values)
    else:
        fields['journal_date'] = journal_date
        fields['account_id'] = account_id
        columns = ', '.join(fields.keys())
        placeholders = ', '.join('?' * len(fields))
        conn.execute(f"INSERT INTO daily_journal ({columns}) VALUES ({placeholders})",
                     list(fields.values()))
    conn.commit()


# ── Account events (deposits/withdrawals) ─────────────────────────────────

def add_account_event(conn: sqlite3.Connection, account_id: int, event_type: str,
                      amount: float, event_date: str, description: str = None,
                      broker_ticket_id: str = None, import_log_id: int = None):
    cur = conn.execute(
        """INSERT OR IGNORE INTO account_events
           (account_id, event_type, amount, event_date, description, broker_ticket_id, import_log_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (account_id, event_type, amount, event_date, description, broker_ticket_id, import_log_id))
    conn.commit()
    return cur.lastrowid if cur.rowcount else None


def get_account_events(conn: sqlite3.Connection, account_id: int):
    return conn.execute(
        "SELECT * FROM account_events WHERE account_id = ? ORDER BY event_date",
        (account_id,)).fetchall()


def account_event_exists(conn: sqlite3.Connection, account_id: int, broker_ticket_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM account_events WHERE account_id = ? AND broker_ticket_id = ?",
        (account_id, broker_ticket_id)).fetchone()
    return row is not None


# ── Executions (for lot-tracked stock trades) ─────────────────────────────

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


# ── Watchlist ──────────────────────────────────────────────────────────────

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


_UPDATE_WATCHLIST_ALLOWED = {
    'bias_weekly', 'bias_daily', 'bias_h4', 'key_levels',
    'notes', 'alert_notes', 'sort_order', 'is_active',
}


def update_watchlist_item(conn: sqlite3.Connection, item_id: int, **kwargs):
    fields = {k: v for k, v in kwargs.items() if k in _UPDATE_WATCHLIST_ALLOWED}
    if not fields:
        return
    fields['updated_at'] = datetime.now().isoformat()
    set_clause = ', '.join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [item_id]
    conn.execute(f"UPDATE watchlist_items SET {set_clause} WHERE id = ?", values)
    conn.commit()


def delete_watchlist_item(conn: sqlite3.Connection, item_id: int):
    conn.execute("DELETE FROM watchlist_items WHERE id = ?", (item_id,))
    conn.commit()


def reorder_watchlist(conn: sqlite3.Connection, item_ids: list):
    """Set sort_order based on position in the list."""
    try:
        for i, item_id in enumerate(item_ids):
            conn.execute("UPDATE watchlist_items SET sort_order = ? WHERE id = ?", (i, item_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# ── Formula definitions ───────────────────────────────────────────────────

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


# ── App settings ──────────────────────────────────────────────────────────

def get_setting(conn: sqlite3.Connection, key: str, default=None):
    """Read a value from app_settings. Returns default if key not found."""
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row['value'] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value):
    """Write a value to app_settings (upsert)."""
    conn.execute(
        "INSERT OR REPLACE INTO app_settings (key, value, updated_at) "
        "VALUES (?, ?, datetime('now'))", (key, str(value)))
    conn.commit()
