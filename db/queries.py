"""
db.queries — Paginated and filtered trade query helpers, plus CSV export definitions.
"""

import sqlite3

from db.analytics import effective_pnl  # noqa: F401 — re-exported for callers


_TRADES_BASE_SQL = """SELECT t.*, a.name as account_name, a.currency as account_currency,
                    i.symbol, i.display_name as instrument_name, i.instrument_type,
                    st.name as setup_name
             FROM trades t
             JOIN accounts a ON t.account_id = a.id
             JOIN instruments i ON t.instrument_id = i.id
             LEFT JOIN setup_types st ON t.setup_type_id = st.id"""


def _build_trade_filters(account_id=None, setup_id=None, direction=None,
                         status=None, grade=None, exit_reason=None, outcome=None,
                         date_from=None, date_to=None, symbol_search=None,
                         tag_id=None):
    """Build SQL WHERE clauses and params list for trade queries.

    Returns (clauses, params) where clauses is a list of SQL fragments
    (joined with AND) and params is the corresponding list of bind values.
    """
    clauses = ["1=1"]
    params = []

    if account_id is not None:
        clauses.append("t.account_id = ?")
        params.append(account_id)

    if setup_id is not None:
        clauses.append("t.setup_type_id = ?")
        params.append(setup_id)

    if direction in ('long', 'short'):
        clauses.append("t.direction = ?")
        params.append(direction)

    if status in ('open', 'closed'):
        clauses.append("t.status = ?")
        params.append(status)

    if grade:
        clauses.append("COALESCE(t.execution_grade, '') = ?")
        params.append(grade)

    if exit_reason is not None:
        clauses.append("COALESCE(t.exit_reason, '') = ?")
        params.append(exit_reason)

    _epnl = ("(COALESCE(t.pnl_account_currency, 0)"
             " + COALESCE(t.swap, 0)"
             " + COALESCE(t.commission, 0))")
    if outcome == 'winners':
        clauses.append(f"{_epnl} > 0")
    elif outcome == 'losers':
        clauses.append(f"{_epnl} < 0")
    elif outcome == 'breakeven':
        clauses.append(f"{_epnl} = 0")

    if date_from:
        clauses.append("t.entry_date >= ?")
        params.append(str(date_from))

    if date_to:
        clauses.append("t.entry_date <= ?")
        params.append(str(date_to)[:10] + 'T23:59:59')

    if symbol_search:
        clauses.append("UPPER(i.symbol) LIKE ?")
        params.append(f'%{symbol_search.upper()}%')

    if tag_id is not None:
        clauses.append(
            "EXISTS (SELECT 1 FROM trade_tags tt WHERE tt.trade_id = t.id AND tt.tag_id = ?)"
        )
        params.append(tag_id)

    return clauses, params


def get_trades_paged(conn: sqlite3.Connection, account_id=None,
                     page: int = 0, page_size: int = 500, **filters):
    """Return one page of trades matching filters, ordered entry_date DESC."""
    clauses, params = _build_trade_filters(account_id=account_id, **filters)
    sql = _TRADES_BASE_SQL + " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY t.entry_date DESC LIMIT ? OFFSET ?"
    params.extend([page_size, page * page_size])
    return conn.execute(sql, params).fetchall()


def count_trades_filtered(conn: sqlite3.Connection, account_id=None, **filters) -> int:
    """Return total count of trades matching filters (no LIMIT)."""
    clauses, params = _build_trade_filters(account_id=account_id, **filters)
    sql = ("""SELECT COUNT(*) as cnt
              FROM trades t
              JOIN accounts a ON t.account_id = a.id
              JOIN instruments i ON t.instrument_id = i.id
              LEFT JOIN setup_types st ON t.setup_type_id = st.id
              WHERE """ + " AND ".join(clauses))
    return conn.execute(sql, params).fetchone()['cnt']


def get_trades_all_filtered(conn: sqlite3.Connection, account_id=None, **filters):
    """Return ALL trades matching filters (no LIMIT), for KPI and export."""
    clauses, params = _build_trade_filters(account_id=account_id, **filters)
    sql = _TRADES_BASE_SQL + " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY t.entry_date DESC"
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
        params.append(str(date_to)[:10] + 'T23:59:59')

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
