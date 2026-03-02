"""
FIFO Lot Matching Engine for Stock Trades.

Takes raw executions (buys/sells) for an instrument and:
1. Matches sells to buys using FIFO (oldest lots consumed first)
2. Creates/updates the parent trade record (position summary)
3. Records lot_consumptions for per-lot P&L tracking

Designed for stocks only — forex trades bypass this entirely.
"""

import sqlite3
import warnings
from collections import deque


def run_fifo_matching(conn: sqlite3.Connection, account_id: int, instrument_id: int):
    """
    Run FIFO matching for all executions of a given instrument in an account.

    Splits executions into round trips: each time the position fully closes
    (remaining shares → 0), the next buy starts a new round trip that maps
    to a separate trade.  This ensures buy→sell-all→buy-again produces two
    distinct journal entries rather than reopening the old one.

    Clears previous lot_consumptions and trade links, then rebuilds from
    scratch.  Idempotent — safe to re-run after adding new executions.

    Returns a list of trade_ids (one per round trip).
    """
    # Get all executions for this instrument, sorted chronologically
    execs = conn.execute(
        """SELECT * FROM executions
           WHERE account_id = ? AND instrument_id = ?
           ORDER BY executed_at, id""",
        (account_id, instrument_id)
    ).fetchall()

    if not execs:
        return []

    try:
        return _run_fifo_matching_inner(conn, account_id, instrument_id, execs)
    except Exception:
        conn.rollback()
        raise


def _run_fifo_matching_inner(conn, account_id, instrument_id, execs):
    # ── Split executions into round trips ──
    # A round trip ends when remaining shares hit 0 after a sell.
    round_trips = []
    current_trip = []
    remaining = 0.0

    for e in execs:
        current_trip.append(e)
        if e['action'] == 'buy':
            remaining += e['shares']
        else:  # sell
            remaining -= e['shares']

        # Position fully closed — end this round trip
        if remaining < 1e-10 and any(x['action'] == 'sell' for x in current_trip):
            round_trips.append(current_trip)
            current_trip = []
            remaining = 0.0

    # Leftover executions (open position) = final round trip
    if current_trip:
        buys_in_trip = [e for e in current_trip if e['action'] == 'buy']
        if buys_in_trip:
            round_trips.append(current_trip)

    if not round_trips:
        return []

    # ── Clear old links for this instrument (full rebuild) ──
    exec_ids = [e['id'] for e in execs]
    placeholders = ','.join('?' * len(exec_ids))
    conn.execute(
        f"UPDATE executions SET trade_id = NULL WHERE id IN ({placeholders})",
        exec_ids
    )
    # Delete old lot consumptions for any trades linked to these executions
    old_trade_ids = conn.execute(
        """SELECT DISTINCT id FROM trades
           WHERE account_id = ? AND instrument_id = ?
             AND broker_ticket_id LIKE 'EXEC!_FIFO!_%' ESCAPE '!'""",
        (account_id, instrument_id)
    ).fetchall()
    for row in old_trade_ids:
        conn.execute("DELETE FROM lot_consumptions WHERE trade_id = ?", (row['id'],))

    # ── Process each round trip ──
    trade_ids = []
    for trip_idx, trip_execs in enumerate(round_trips):
        buys = [e for e in trip_execs if e['action'] == 'buy']
        sells = [e for e in trip_execs if e['action'] == 'sell']

        if not buys:
            continue

        # Find or create a trade for this round trip
        trade_id = _get_or_create_trade(
            conn, account_id, instrument_id, buys[0], trip_idx, len(round_trips)
        )
        trade_ids.append(trade_id)

        # Link executions to this trade
        trip_exec_ids = [e['id'] for e in trip_execs]
        conn.execute(
            f"UPDATE executions SET trade_id = ? "
            f"WHERE id IN ({','.join('?' * len(trip_exec_ids))})",
            [trade_id] + trip_exec_ids
        )

        # Build FIFO queue from buys
        lot_queue = deque()
        for b in buys:
            lot_queue.append({
                'exec_id': b['id'],
                'remaining': b['shares'],
                'original': b['shares'],
                'price': b['price'],
                'xrate': b['exchange_rate'] or 1.0,
            })

        # Process sells in chronological order
        total_broker_pnl = 0.0
        total_computed_pnl = 0.0
        lot_records = []

        for s in sells:
            shares_to_sell = s['shares']
            sell_price = s['price']
            sell_xrate = s['exchange_rate'] or 1.0
            broker_result = s['broker_result']

            if broker_result is not None:
                total_broker_pnl += broker_result

            while shares_to_sell > 1e-10 and lot_queue:
                lot = lot_queue[0]
                consumed = min(shares_to_sell, lot['remaining'])

                buy_cost_acc = consumed * lot['price'] / lot['xrate']
                sell_proceeds_acc = consumed * sell_price / sell_xrate
                lot_pnl = sell_proceeds_acc - buy_cost_acc

                total_computed_pnl += lot_pnl

                lot_records.append({
                    'trade_id': trade_id,
                    'buy_execution_id': lot['exec_id'],
                    'sell_execution_id': s['id'],
                    'shares_consumed': consumed,
                    'buy_price': lot['price'],
                    'sell_price': sell_price,
                    'buy_exchange_rate': lot['xrate'],
                    'sell_exchange_rate': sell_xrate,
                    'pnl_computed': round(lot_pnl, 4),
                })

                lot['remaining'] -= consumed
                shares_to_sell -= consumed

                if lot['remaining'] < 1e-10:
                    lot_queue.popleft()

            if shares_to_sell > 1e-10:
                warnings.warn(
                    f"FIFO oversell: {shares_to_sell:.6f} shares unmatched after exhausting lot queue",
                    stacklevel=2,
                )

        # Insert lot consumption records
        for rec in lot_records:
            conn.execute(
                """INSERT INTO lot_consumptions
                   (trade_id, buy_execution_id, sell_execution_id,
                    shares_consumed, buy_price, sell_price,
                    buy_exchange_rate, sell_exchange_rate, pnl_computed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (rec['trade_id'], rec['buy_execution_id'],
                 rec['sell_execution_id'], rec['shares_consumed'],
                 rec['buy_price'], rec['sell_price'],
                 rec['buy_exchange_rate'], rec['sell_exchange_rate'],
                 rec['pnl_computed'])
            )

        # Update the trade summary
        _update_trade_summary(conn, trade_id, buys, sells, lot_queue,
                              total_broker_pnl, total_computed_pnl)

    # Delete orphaned FIFO trades that no longer have executions
    for row in old_trade_ids:
        if row['id'] not in trade_ids:
            has_execs = conn.execute(
                "SELECT 1 FROM executions WHERE trade_id = ? LIMIT 1",
                (row['id'],)
            ).fetchone()
            if not has_execs:
                conn.execute("DELETE FROM trades WHERE id = ?", (row['id'],))

    conn.commit()
    return trade_ids


def _get_or_create_trade(conn, account_id, instrument_id, first_buy,
                         trip_index, total_trips):
    """Find existing trade for this round trip or create one.

    Uses broker_ticket_id 'EXEC_FIFO_{account}_{instrument}_{trip}'
    to match trades to specific round trips.
    """
    ticket = f"EXEC_FIFO_{account_id}_{instrument_id}_{trip_index}"

    # Exact match by round-trip ticket
    row = conn.execute(
        "SELECT id FROM trades WHERE broker_ticket_id = ? LIMIT 1",
        (ticket,)
    ).fetchone()
    if row:
        return row['id']

    # Migration: if trip_index == 0 and there's an old-style ticket without
    # the suffix, adopt it (so existing single-trip trades keep their id).
    if trip_index == 0:
        old_ticket = f"EXEC_FIFO_{account_id}_{instrument_id}"
        row = conn.execute(
            "SELECT id FROM trades WHERE broker_ticket_id = ? LIMIT 1",
            (old_ticket,)
        ).fetchone()
        if row:
            # If total_trips > 1, rename the ticket so it doesn't collide
            conn.execute(
                "UPDATE trades SET broker_ticket_id = ? WHERE id = ?",
                (ticket, row['id'])
            )
            return row['id']

    # Create new trade
    cur = conn.execute(
        """INSERT INTO trades
           (account_id, instrument_id, direction, entry_date, entry_price,
            position_size, status, broker_ticket_id)
           VALUES (?, ?, 'long', ?, 0, 0, 'open', ?)""",
        (account_id, instrument_id, first_buy['executed_at'], ticket)
    )
    return cur.lastrowid


def _update_trade_summary(conn, trade_id, buys, sells, remaining_lots,
                          total_broker_pnl, total_computed_pnl):
    """Update the trade record with computed position summary."""
    total_bought = sum(b['shares'] for b in buys)
    total_sold = sum(s['shares'] for s in sells)
    remaining_shares = sum(lot['remaining'] for lot in remaining_lots)

    # Weighted average entry price across ALL buy executions
    wavg_entry = (sum(b['shares'] * b['price'] for b in buys) / total_bought
                  if total_bought else 0.0)

    # Total commission across all executions
    total_commission = sum((b['commission'] or 0) for b in buys) + \
                       sum((s['commission'] or 0) for s in sells)

    # Entry date = first buy, exit date = last sell (if fully closed)
    entry_date = buys[0]['executed_at']
    last_sell_date = sells[-1]['executed_at'] if sells else None

    # Status
    is_closed = remaining_shares < 1e-10 and sells
    status = 'closed' if is_closed else 'open'

    # P&L: use broker P&L as official, store computed for transparency
    pnl_official = total_broker_pnl if sells else None

    update = {
        'entry_date': entry_date,
        'entry_price': round(wavg_entry, 6),
        'position_size': round(total_bought, 10),
        'commission': round(total_commission, 4),
        'status': status,
        'pnl_account_currency': pnl_official,
    }

    if is_closed and last_sell_date:
        # Exit price = weighted avg of all sell executions
        wavg_exit = (sum(s['shares'] * s['price'] for s in sells) / total_sold
                     if total_sold else 0.0)
        update['exit_date'] = last_sell_date
        update['exit_price'] = round(wavg_exit, 6)
    else:
        update['exit_date'] = None
        update['exit_price'] = None

    set_clause = ', '.join(f"{k} = ?" for k in update)
    values = list(update.values()) + [trade_id]
    conn.execute(f"UPDATE trades SET {set_clause} WHERE id = ?", values)


def get_executions_for_trade(conn: sqlite3.Connection, trade_id: int):
    """Get all executions linked to a trade, sorted chronologically."""
    return conn.execute(
        """SELECT e.*, i.symbol, i.display_name as instrument_name
           FROM executions e
           JOIN instruments i ON e.instrument_id = i.id
           WHERE e.trade_id = ?
           ORDER BY e.executed_at, e.id""",
        (trade_id,)
    ).fetchall()


def get_lot_consumptions_for_trade(conn: sqlite3.Connection, trade_id: int):
    """Get FIFO lot consumption records for a trade."""
    return conn.execute(
        """SELECT lc.*,
                  be.executed_at as buy_date, be.shares as buy_total_shares,
                  se.executed_at as sell_date, se.shares as sell_total_shares
           FROM lot_consumptions lc
           JOIN executions be ON lc.buy_execution_id = be.id
           JOIN executions se ON lc.sell_execution_id = se.id
           WHERE lc.trade_id = ?
           ORDER BY se.executed_at, be.executed_at""",
        (trade_id,)
    ).fetchall()


def get_open_lots_for_trade(conn: sqlite3.Connection, trade_id: int):
    """
    Get remaining open lots for a trade (buy executions with unconsumed shares).
    Returns list of dicts with buy details and remaining shares.
    """
    # Total bought per execution
    buys = conn.execute(
        """SELECT id, executed_at, shares, price, price_currency,
                  exchange_rate, total_account_currency, commission
           FROM executions
           WHERE trade_id = ? AND action = 'buy'
           ORDER BY executed_at, id""",
        (trade_id,)
    ).fetchall()

    # Total consumed per buy execution
    consumed = {}
    rows = conn.execute(
        """SELECT buy_execution_id, SUM(shares_consumed) as total_consumed
           FROM lot_consumptions
           WHERE trade_id = ?
           GROUP BY buy_execution_id""",
        (trade_id,)
    ).fetchall()
    for r in rows:
        consumed[r['buy_execution_id']] = r['total_consumed']

    open_lots = []
    for b in buys:
        used = consumed.get(b['id'], 0)
        remaining = b['shares'] - used
        if remaining > 1e-10:
            open_lots.append({
                'execution_id': b['id'],
                'date': b['executed_at'],
                'original_shares': b['shares'],
                'remaining_shares': remaining,
                'price': b['price'],
                'price_currency': b['price_currency'],
                'exchange_rate': b['exchange_rate'],
                'cost_account': b['total_account_currency'],
                'commission': b['commission'],
            })

    return open_lots


def execution_exists(conn: sqlite3.Connection, account_id: int, broker_order_id: str) -> bool:
    """Check if an execution with this broker order ID already exists."""
    row = conn.execute(
        "SELECT 1 FROM executions WHERE account_id = ? AND broker_order_id = ?",
        (account_id, broker_order_id)
    ).fetchone()
    return row is not None


# ── FIFO Audit / Integrity Validation ────────────────────────────────────

def audit_trade_integrity(conn: sqlite3.Connection, trade_id: int):
    """
    Verify FIFO data integrity invariants for a single trade.

    Returns a dict with:
        'ok': bool — True if all invariants hold
        'errors': list of str — description of each violated invariant
        'details': dict — computed values used in checks

    Invariants checked:
    1. All executions linked to this trade belong to the same instrument
    2. Total shares bought >= total shares sold
    3. Sum of lot_consumptions.shares_consumed == total shares sold
    4. Each lot_consumption references valid buy and sell executions
    5. No buy lot is over-consumed (consumed <= bought)
    6. Trade status matches position: closed iff remaining == 0 and has sells
    7. Weighted avg entry price matches manually computed value
    8. Weighted avg exit price matches (for closed trades)
    9. Commission equals sum of all execution commissions
    10. No negative P&L computation artifacts (lot pnl vs price diff)
    """
    errors = []
    details = {}

    trade = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
    if not trade:
        return {'ok': False, 'errors': ['Trade not found'], 'details': {}}

    execs = conn.execute(
        "SELECT * FROM executions WHERE trade_id = ? ORDER BY executed_at, id",
        (trade_id,)
    ).fetchall()

    buys = [e for e in execs if e['action'] == 'buy']
    sells = [e for e in execs if e['action'] == 'sell']

    lots = conn.execute(
        "SELECT * FROM lot_consumptions WHERE trade_id = ?",
        (trade_id,)
    ).fetchall()

    # ── Invariant 1: Same instrument ──
    instruments = set(e['instrument_id'] for e in execs)
    if len(instruments) > 1:
        errors.append(f"INV1: Executions span multiple instruments: {instruments}")
    details['instrument_ids'] = instruments

    # ── Invariant 2: Bought >= Sold ──
    total_bought = sum(b['shares'] for b in buys)
    total_sold = sum(s['shares'] for s in sells)
    details['total_bought'] = total_bought
    details['total_sold'] = total_sold
    details['remaining'] = total_bought - total_sold

    if total_sold - total_bought > 1e-10:
        errors.append(
            f"INV2: Oversold — bought {total_bought}, sold {total_sold}"
        )

    # ── Invariant 3: Lot consumptions sum to total sold ──
    total_consumed = sum(lc['shares_consumed'] for lc in lots)
    details['total_lot_consumed'] = total_consumed
    if abs(total_consumed - total_sold) > 1e-6:
        errors.append(
            f"INV3: Lot consumption mismatch — consumed {total_consumed}, "
            f"sold {total_sold}, diff {total_consumed - total_sold}"
        )

    # ── Invariant 4: Lot consumption FK references ──
    buy_exec_ids = {b['id'] for b in buys}
    sell_exec_ids = {s['id'] for s in sells}
    for lc in lots:
        if lc['buy_execution_id'] not in buy_exec_ids:
            errors.append(
                f"INV4: lot_consumption references missing buy exec {lc['buy_execution_id']}"
            )
        if lc['sell_execution_id'] not in sell_exec_ids:
            errors.append(
                f"INV4: lot_consumption references missing sell exec {lc['sell_execution_id']}"
            )

    # ── Invariant 5: No over-consumed lots ──
    consumed_per_buy = {}
    for lc in lots:
        consumed_per_buy[lc['buy_execution_id']] = \
            consumed_per_buy.get(lc['buy_execution_id'], 0) + lc['shares_consumed']
    for b in buys:
        used = consumed_per_buy.get(b['id'], 0)
        if used - b['shares'] > 1e-6:
            errors.append(
                f"INV5: Buy exec {b['id']} over-consumed — "
                f"bought {b['shares']}, consumed {used}"
            )
    details['consumed_per_buy'] = consumed_per_buy

    # ── Invariant 6: Status consistency ──
    remaining = total_bought - total_sold
    expected_closed = remaining < 1e-10 and len(sells) > 0
    expected_status = 'closed' if expected_closed else 'open'
    if trade['status'] != expected_status:
        errors.append(
            f"INV6: Status mismatch — trade says '{trade['status']}', "
            f"expected '{expected_status}' (remaining={remaining:.6f})"
        )
    details['expected_status'] = expected_status

    # ── Invariant 7: Weighted avg entry price ──
    if buys and total_bought:
        expected_entry = sum(b['shares'] * b['price'] for b in buys) / total_bought
        if trade['entry_price'] is not None and abs(trade['entry_price'] - round(expected_entry, 6)) > 1e-4:
            errors.append(
                f"INV7: Entry price mismatch — trade has {trade['entry_price']}, "
                f"expected {expected_entry:.6f}"
            )
        details['expected_entry_price'] = expected_entry

    # ── Invariant 8: Weighted avg exit price (closed only) ──
    if expected_closed and sells and total_sold:
        expected_exit = sum(s['shares'] * s['price'] for s in sells) / total_sold
        if trade['exit_price'] is not None:
            if abs(trade['exit_price'] - round(expected_exit, 6)) > 1e-4:
                errors.append(
                    f"INV8: Exit price mismatch — trade has {trade['exit_price']}, "
                    f"expected {expected_exit:.6f}"
                )
        else:
            errors.append("INV8: Closed trade has NULL exit_price")
        details['expected_exit_price'] = expected_exit

    # ── Invariant 9: Commission sum ──
    expected_commission = sum((e['commission'] or 0) for e in execs)
    if trade['commission'] is not None:
        if abs(trade['commission'] - round(expected_commission, 4)) > 0.01:
            errors.append(
                f"INV9: Commission mismatch — trade has {trade['commission']}, "
                f"expected {expected_commission:.4f}"
            )
    details['expected_commission'] = expected_commission

    # ── Invariant 10: Lot P&L sign consistency ──
    for lc in lots:
        buy_xrate = lc['buy_exchange_rate'] or 1.0
        sell_xrate = lc['sell_exchange_rate'] or 1.0
        expected_sign = (lc['sell_price'] / sell_xrate) - (lc['buy_price'] / buy_xrate)
        if expected_sign > 0 and lc['pnl_computed'] < -0.01:
            errors.append(
                f"INV10: Lot P&L sign wrong — buy@{lc['buy_price']}, "
                f"sell@{lc['sell_price']}, pnl={lc['pnl_computed']}"
            )
        elif expected_sign < 0 and lc['pnl_computed'] > 0.01:
            errors.append(
                f"INV10: Lot P&L sign wrong — buy@{lc['buy_price']}, "
                f"sell@{lc['sell_price']}, pnl={lc['pnl_computed']}"
            )

    return {
        'ok': len(errors) == 0,
        'errors': errors,
        'details': details,
    }


def audit_instrument_integrity(conn: sqlite3.Connection, account_id: int,
                                instrument_id: int):
    """
    Audit all FIFO trades for an instrument.
    Returns dict with 'ok', list of per-trade results, and aggregate stats.
    """
    trade_ids = conn.execute(
        """SELECT id FROM trades
           WHERE account_id = ? AND instrument_id = ?
             AND broker_ticket_id LIKE 'EXEC!_FIFO!_%' ESCAPE '!'
           ORDER BY entry_date""",
        (account_id, instrument_id)
    ).fetchall()

    results = []
    all_ok = True
    for row in trade_ids:
        result = audit_trade_integrity(conn, row['id'])
        result['trade_id'] = row['id']
        results.append(result)
        if not result['ok']:
            all_ok = False

    # Check no execution is orphaned (linked to no trade)
    orphans = conn.execute(
        """SELECT id FROM executions
           WHERE account_id = ? AND instrument_id = ? AND trade_id IS NULL""",
        (account_id, instrument_id)
    ).fetchall()

    orphan_errors = []
    if orphans:
        orphan_errors.append(
            f"GLOBAL: {len(orphans)} orphaned executions not linked to any trade"
        )
        all_ok = False

    return {
        'ok': all_ok,
        'trade_results': results,
        'orphan_errors': orphan_errors,
        'total_trades': len(trade_ids),
    }
