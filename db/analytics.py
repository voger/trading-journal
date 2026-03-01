"""
db.analytics — Trading statistics and analytics functions.
"""

import sqlite3
from collections import defaultdict
from datetime import datetime


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


_VALID_GROUP_BY = frozenset({
    'instrument', 'setup', 'day_of_week', 'session',
    'exit_reason', 'direction', 'month', 'hour_of_day',
})


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
        params.append(str(date_to)[:10] + 'T23:59:59')
    trades = conn.execute(sql, params).fetchall()
    open_count = conn.execute(open_sql, open_params).fetchone()['cnt']

    if not trades:
        return None

    result = _compute_stats(trades)
    result['open_trades'] = open_count
    return result


def get_trade_breakdowns(conn: sqlite3.Connection, account_id: int, group_by: str,
                         date_from=None, date_to=None):
    """Get per-group performance stats for closed trades.

    group_by: 'instrument', 'setup', 'day_of_week', 'session', 'exit_reason',
              'direction', 'month'

    Returns: list of dicts, each with 'group_name' + all stats keys,
             sorted by net_pnl descending.
    """
    if group_by not in _VALID_GROUP_BY:
        raise ValueError(f"group_by must be one of {sorted(_VALID_GROUP_BY)}, got {group_by!r}")
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
        params.append(str(date_to)[:10] + 'T23:59:59')
    trades = conn.execute(sql, params).fetchall()

    if not trades:
        return []

    # Group trades by the requested dimension
    groups = defaultdict(list)

    for t in trades:
        if group_by == 'instrument':
            key = t['symbol'] or '?'
        elif group_by == 'setup':
            key = t['setup_name'] or '(no setup)'
        elif group_by == 'day_of_week':
            try:
                date_str = t['exit_date'] or t['entry_date']
                dt = datetime.fromisoformat(date_str[:19])
                key = _DOW_NAMES[dt.weekday()]
            except (ValueError, TypeError):
                key = '?'
        elif group_by == 'session':
            try:
                date_str = t['exit_date'] or t['entry_date']
                dt = datetime.fromisoformat(date_str[:19])
                key = _get_session(dt.hour)
            except (ValueError, TypeError):
                key = '?'
        elif group_by == 'exit_reason':
            key = t['exit_reason'] or '(none)'
        elif group_by == 'direction':
            key = (t['direction'] or 'long').capitalize()
        elif group_by == 'month':
            try:
                date_str = t['exit_date'] or t['entry_date']
                key = date_str[:7] if date_str else '?'
            except (TypeError, IndexError):
                key = '?'
        elif group_by == 'hour_of_day':
            try:
                date_str = t['exit_date'] or t['entry_date']
                dt = datetime.fromisoformat(date_str[:19])
                key = dt.hour
            except (ValueError, TypeError):
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
    elif group_by == 'hour_of_day':
        results.sort(key=lambda r: r['group_name'] if isinstance(r['group_name'], int) else 24)
    else:
        results.sort(key=lambda r: r['net_pnl'], reverse=True)

    return results


def get_daily_pnl(conn: sqlite3.Connection, account_id: int,
                  year: int, month: int) -> dict:
    """Get daily P&L totals for a given month.

    Returns: dict mapping day int → {'net_pnl': float, 'trade_count': int}
    Only includes days with at least one closed, non-excluded trade.
    Uses effective_pnl (pnl + swap + commission).
    """
    sql = """SELECT t.exit_date,
                    t.pnl_account_currency, t.swap, t.commission
             FROM trades t
             WHERE t.account_id = ?
               AND t.status = 'closed'
               AND t.is_excluded = 0
               AND t.exit_date IS NOT NULL
               AND strftime('%Y', t.exit_date) = ?
               AND strftime('%m', t.exit_date) = ?"""
    rows = conn.execute(sql, [account_id, str(year), f'{month:02d}']).fetchall()
    result = {}
    for row in rows:
        day = int(row['exit_date'][8:10])
        epnl = effective_pnl(row)
        if day not in result:
            result[day] = {'net_pnl': 0.0, 'trade_count': 0}
        result[day]['net_pnl'] += epnl
        result[day]['trade_count'] += 1
    return result


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
        params.append(str(date_to)[:10] + 'T23:59:59')
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
    winner_durations = []
    loser_durations  = []
    for t, p in zip(trades, pnls):
        if t['entry_date'] and t['exit_date']:
            try:
                entry_d = datetime.strptime(t['entry_date'][:10], '%Y-%m-%d')
                exit_d = datetime.strptime(t['exit_date'][:10], '%Y-%m-%d')
                days = (exit_d - entry_d).days
                if days >= 0:
                    durations.append(days)
                    if p > 0:
                        winner_durations.append(days)
                    elif p < 0:
                        loser_durations.append(days)
            except (ValueError, TypeError):
                pass
    avg_duration = sum(durations) / len(durations) if durations else 0.0
    avg_winner_duration = sum(winner_durations) / len(winner_durations) if winner_durations else 0.0
    avg_loser_duration  = sum(loser_durations)  / len(loser_durations)  if loser_durations  else 0.0

    # ── Sharpe ratio (simplified: mean / stdev) ──
    mean_pnl = sum(pnls) / n
    if n > 1:
        variance = sum((p - mean_pnl) ** 2 for p in pnls) / (n - 1)
        stdev = variance ** 0.5
        sharpe = mean_pnl / stdev if stdev > 0 else float('inf')
    else:
        sharpe = 0.0

    # ── Sortino ratio (downside deviation, MAR = 0) ──
    downside = [p for p in pnls if p < 0]
    if downside and n > 0:
        downside_var = sum(p ** 2 for p in downside) / n
        sortino = mean_pnl / (downside_var ** 0.5) if downside_var > 0 else float('inf')
    else:
        sortino = float('inf') if mean_pnl > 0 else 0.0

    # ── Calmar ratio (net P&L / max absolute drawdown) ──
    net_pnl_total = sum(pnls)
    if max_dd_abs > 0:
        calmar = net_pnl_total / max_dd_abs
    elif net_pnl_total > 0:
        calmar = float('inf')  # positive P&L with no drawdown → ∞ (like Sharpe/Sortino)
    else:
        calmar = 0.0

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
        'sortino_ratio': round(sortino, 3),
        'calmar_ratio': round(calmar, 3),
        'avg_winner_duration': round(avg_winner_duration, 1),
        'avg_loser_duration': round(avg_loser_duration, 1),
        'total_trades': n,
    }


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


def get_equity_events(conn: sqlite3.Connection, account_id=None):
    """Return deposits/withdrawals for equity curve overlay."""
    sql = "SELECT * FROM account_events WHERE 1=1"
    params = []
    if account_id is not None:
        sql += " AND account_id = ?"
        params.append(account_id)
    sql += " ORDER BY event_date"
    return conn.execute(sql, params).fetchall()


# ── Setup performance & R distribution ───────────────────────────────────

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


def get_setup_performance(conn: sqlite3.Connection, account_id: int,
                          date_from=None, date_to=None):
    """Per-setup stats for closed, non-excluded trades.

    Returns a list of dicts (sorted by net_pnl descending), each with:
        setup_name, total_trades, win_rate, net_pnl, avg_pnl,
        avg_r (None if no r_multiple recorded), avg_duration (None if no dates)
    """
    sql = """SELECT t.*, st.name as setup_name
             FROM trades t
             LEFT JOIN setup_types st ON t.setup_type_id = st.id
             WHERE t.status = 'closed' AND t.is_excluded = 0 AND t.account_id = ?"""
    params = [account_id]
    if date_from:
        sql += " AND t.exit_date >= ?"
        params.append(str(date_from))
    if date_to:
        sql += " AND t.exit_date <= ?"
        params.append(str(date_to)[:10] + 'T23:59:59')

    trades = conn.execute(sql, params).fetchall()
    if not trades:
        return []

    groups = defaultdict(list)
    for t in trades:
        key = t['setup_name'] or '(no setup)'
        groups[key].append(t)

    results = []
    for setup_name, group_trades in groups.items():
        n = len(group_trades)
        pnls = [effective_pnl(t) for t in group_trades]
        winners = sum(1 for p in pnls if p > 0)
        win_rate = winners / n * 100
        net_pnl = sum(pnls)
        avg_pnl = net_pnl / n

        r_vals = [t['r_multiple'] for t in group_trades if t['r_multiple'] is not None]
        avg_r = sum(r_vals) / len(r_vals) if r_vals else None

        durations = []
        for t in group_trades:
            if t['entry_date'] and t['exit_date']:
                try:
                    ed = datetime.strptime(t['entry_date'][:10], '%Y-%m-%d')
                    xd = datetime.strptime(t['exit_date'][:10], '%Y-%m-%d')
                    days = (xd - ed).days
                    if days >= 0:
                        durations.append(days)
                except (ValueError, TypeError):
                    pass
        avg_duration = sum(durations) / len(durations) if durations else None

        results.append({
            'setup_name': setup_name,
            'total_trades': n,
            'win_rate': win_rate,
            'net_pnl': net_pnl,
            'avg_pnl': avg_pnl,
            'avg_r': avg_r,
            'avg_duration': avg_duration,
        })

    results.sort(key=lambda r: r['net_pnl'], reverse=True)
    return results


def get_r_multiple_distribution(conn: sqlite3.Connection, account_id: int,
                                date_from=None, date_to=None):
    """Collect R multiples for closed, non-excluded trades.

    Returns (r_values, excluded_count) where:
        r_values:       list of float R multiples (trades with r_multiple set)
        excluded_count: number of closed trades without r_multiple recorded
    """
    sql = """SELECT t.r_multiple
             FROM trades t
             WHERE t.status = 'closed' AND t.is_excluded = 0 AND t.account_id = ?"""
    params = [account_id]
    if date_from:
        sql += " AND t.exit_date >= ?"
        params.append(str(date_from))
    if date_to:
        sql += " AND t.exit_date <= ?"
        params.append(str(date_to)[:10] + 'T23:59:59')

    rows = conn.execute(sql, params).fetchall()
    r_values = [float(r['r_multiple']) for r in rows if r['r_multiple'] is not None]
    excluded = len(rows) - len(r_values)
    return r_values, excluded
