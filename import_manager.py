"""
Import Manager
Orchestrates the import process: plugin selection, parsing, deduplication, and database insertion.
Supports two import modes:
  - "trades" (legacy): plugin returns pre-matched trade dicts (MT4)
  - "executions" (new): plugin returns raw buy/sell executions → FIFO engine builds trades
"""

import os
import json
from pathlib import Path

try:
    from . import database as db
except ImportError:
    import database as db

# Import plugins robustly — missing plugins are skipped, not fatal
PLUGINS = {}

def _try_import_plugin(name):
    """Try to import a plugin module, return None if not available."""
    try:
        import importlib
        return importlib.import_module(f'plugins.{name}')
    except Exception:
        return None

for _name in ['mt4_plugin', 'trading212_plugin']:
    _mod = _try_import_plugin(_name)
    if _mod and hasattr(_mod, 'PLUGIN_NAME'):
        PLUGINS[_mod.PLUGIN_NAME] = _mod


def get_available_plugins() -> list:
    """Return list of (plugin_name, display_name, extensions) tuples."""
    return [(name, mod.DISPLAY_NAME, mod.SUPPORTED_EXTENSIONS)
            for name, mod in PLUGINS.items()]


def detect_plugin(file_path: str):
    """Auto-detect which plugin can handle this file."""
    ext = Path(file_path).suffix.lower()
    for name, mod in PLUGINS.items():
        if ext in mod.SUPPORTED_EXTENSIONS:
            ok, msg = mod.validate(file_path)
            if ok:
                return mod
    return None


def run_import(conn, account_id: int, file_path: str, plugin_name: str = None,
               progress_cb=None) -> dict:
    """
    Import trades from a file into the database.

    Returns dict with:
        success: bool
        message: str
        trades_found / trades_imported / trades_skipped: int
        errors: list[str]
        import_log_id: int
    """
    result = {
        'success': False,
        'message': '',
        'trades_found': 0,
        'trades_imported': 0,
        'trades_skipped': 0,
        'errors': [],
        'import_log_id': None,
    }

    # Select plugin
    if plugin_name:
        plugin = PLUGINS.get(plugin_name)
        if not plugin:
            result['message'] = f"Unknown plugin: {plugin_name}"
            return result
    else:
        plugin = detect_plugin(file_path)
        if not plugin:
            result['message'] = "Could not detect file format. Please select the import format manually."
            return result

    # Validate file
    ok, msg = plugin.validate(file_path)
    if not ok:
        result['message'] = f"Validation failed: {msg}"
        return result

    # Parse
    try:
        parse_result = plugin.parse(file_path)
        if isinstance(parse_result, tuple):
            raw_data, balance_events = parse_result
        else:
            raw_data = parse_result
            balance_events = []
    except Exception as e:
        result['message'] = f"Parse error: {e}"
        result['errors'].append(str(e))
        return result

    # Determine import mode
    import_mode = getattr(plugin, 'IMPORT_MODE', 'trades')

    if import_mode == 'executions':
        return _import_executions(conn, account_id, file_path, plugin, raw_data, balance_events, result, progress_cb)
    else:
        return _import_trades(conn, account_id, file_path, plugin, raw_data, balance_events, result, progress_cb)


# ── Legacy trade-based import (MT4 etc.) ─────────────────────────────────

def _import_trades(conn, account_id, file_path, plugin, raw_trades, balance_events, result, progress_cb=None):
    """Import pre-matched trade records (one row per trade)."""
    result['trades_found'] = len(raw_trades)

    if not raw_trades:
        result['message'] = "No trades found in file."
        result['success'] = True
        return result

    fhash = plugin.file_hash(file_path) if hasattr(plugin, 'file_hash') else None
    errors = []
    imported = 0
    skipped = 0

    total = len(raw_trades)
    for i, trade_data in enumerate(raw_trades):
        if progress_cb:
            progress_cb(i, total)
        try:
            ticket = trade_data.get('broker_ticket_id')
            if not ticket:
                errors.append(f"Trade {i+1}: missing broker_ticket_id, skipped.")
                skipped += 1
                continue

            if db.trade_exists(conn, account_id, str(ticket)):
                skipped += 1
                continue

            if not (trade_data.get('symbol') or '').strip():
                errors.append(f"Trade {i+1}: missing symbol, skipped.")
                skipped += 1
                continue

            instrument_id = db.get_or_create_instrument(
                conn,
                symbol=trade_data['symbol'],
                display_name=trade_data.get('display_name'),
                instrument_type=trade_data.get('instrument_type', 'forex'),
                pip_size=trade_data.get('pip_size'),
            )

            trade_record = {
                'account_id': account_id,
                'instrument_id': instrument_id,
                'direction': trade_data['direction'],
                'entry_date': trade_data['entry_date'],
                'entry_price': trade_data['entry_price'],
                'position_size': trade_data['position_size'],
                'stop_loss_price': trade_data.get('stop_loss_price'),
                'take_profit_price': trade_data.get('take_profit_price'),
                'exit_date': trade_data.get('exit_date'),
                'exit_price': trade_data.get('exit_price'),
                'exit_reason': trade_data.get('exit_reason'),
                'pnl_pips': trade_data.get('pnl_pips'),
                'pnl_account_currency': trade_data.get('pnl_account_currency'),
                'commission': trade_data.get('commission', 0),
                'swap': trade_data.get('swap', 0),
                'broker_ticket_id': str(ticket),
                'status': trade_data.get('status', 'closed'),
            }

            db.create_trade(conn, **trade_record)
            imported += 1

        except Exception as e:
            errors.append(f"Trade {i+1} (ticket {trade_data.get('broker_ticket_id', '?')}): {e}")

    # Create import log first so balance events can be linked to it
    log_id = db.create_import_log(conn,
        account_id=account_id,
        plugin_name=plugin.PLUGIN_NAME,
        file_name=os.path.basename(file_path),
        file_hash=fhash,
        trades_found=len(raw_trades),
        trades_imported=0,
        trades_skipped=0,
        trades_updated=0,
        errors=None,
    )

    # Import balance events (linked to this log so delete_import_log can clean them up)
    events_imported = _import_balance_events(conn, account_id, balance_events, errors, log_id)

    # Update log with final counts
    conn.execute(
        """UPDATE import_logs SET trades_imported = ?, trades_skipped = ?, errors = ?
           WHERE id = ?""",
        (imported, skipped, json.dumps(errors) if errors else None, log_id)
    )
    conn.commit()

    result['success'] = True
    result['trades_imported'] = imported
    result['trades_skipped'] = skipped
    result['events_imported'] = events_imported
    result['errors'] = errors
    result['import_log_id'] = log_id
    result['message'] = f"Imported {imported} trades, skipped {skipped} duplicates."
    if events_imported:
        result['message'] += f" {events_imported} balance events imported."
    if errors:
        result['message'] += f" {len(errors)} errors."
    return result


# ── Execution-based import (Trading212 etc.) ─────────────────────────────

def _import_executions(conn, account_id, file_path, plugin, raw_executions, balance_events, result, progress_cb=None):
    """
    Import raw executions, then run FIFO engine to build/update trades.
    Each execution (buy/sell) is stored individually.
    The FIFO engine groups them by instrument and creates trade records.
    """
    from fifo_engine import run_fifo_matching

    result['trades_found'] = len(raw_executions)

    if not raw_executions:
        result['message'] = "No executions found in file."
        result['success'] = True
        return result

    fhash = plugin.file_hash(file_path) if hasattr(plugin, 'file_hash') else None
    errors = []
    imported = 0
    skipped = 0

    # Create import log first (we need the ID for linking)
    log_id = db.create_import_log(conn,
        account_id=account_id,
        plugin_name=plugin.PLUGIN_NAME,
        file_name=os.path.basename(file_path),
        file_hash=fhash,
        trades_found=len(raw_executions),
        trades_imported=0,
        trades_skipped=0,
        trades_updated=0,
        errors=None,
    )

    # Track which instruments got new executions (need FIFO re-run)
    affected_instruments = set()

    # Insert raw executions
    total_ex = len(raw_executions)
    for i, ex in enumerate(raw_executions):
        if progress_cb:
            progress_cb(i, total_ex)
        try:
            order_id = ex.get('broker_order_id')
            if not order_id:
                errors.append(f"Execution {i+1}: missing broker_order_id, skipped.")
                skipped += 1
                continue

            # Deduplicate by broker order ID
            if db.execution_exists(conn, account_id, str(order_id)):
                skipped += 1
                continue

            if not (ex.get('symbol') or '').strip():
                errors.append(f"Execution {i+1}: missing symbol, skipped.")
                skipped += 1
                continue

            # Get or create instrument
            instrument_id = db.get_or_create_instrument(
                conn,
                symbol=ex['symbol'],
                display_name=ex.get('display_name'),
                instrument_type=ex.get('instrument_type', 'stock'),
            )

            # Insert execution
            db.create_execution(conn,
                account_id=account_id,
                instrument_id=instrument_id,
                broker_order_id=str(order_id),
                action=ex['action'],
                shares=ex['shares'],
                price=ex['price'],
                price_currency=ex.get('price_currency'),
                exchange_rate=ex.get('exchange_rate'),
                total_account_currency=ex.get('total_account_currency'),
                commission=ex.get('commission', 0),
                broker_result=ex.get('broker_result'),
                executed_at=ex['executed_at'],
                import_log_id=log_id,
            )

            affected_instruments.add(instrument_id)
            imported += 1

        except Exception as e:
            errors.append(f"Execution {i+1} (order {ex.get('broker_order_id', '?')}): {e}")

    # Run FIFO matching for each affected instrument
    trades_created = 0
    fifo_failed = False
    for instrument_id in affected_instruments:
        try:
            trade_ids = run_fifo_matching(conn, account_id, instrument_id)
            trades_created += len(trade_ids) if trade_ids else 0
        except Exception as e:
            fifo_failed = True
            errors.append(f"FIFO matching error for instrument {instrument_id}: {e}")

    # Import balance events (linked to this log so delete_import_log can clean them up)
    events_imported = _import_balance_events(conn, account_id, balance_events, errors, log_id)

    # Update import log with final counts
    conn.execute(
        """UPDATE import_logs SET trades_imported = ?, trades_skipped = ?, errors = ?
           WHERE id = ?""",
        (imported, skipped, json.dumps(errors) if errors else None, log_id)
    )
    conn.commit()

    result['success'] = not fifo_failed or trades_created > 0
    result['trades_imported'] = imported
    result['trades_skipped'] = skipped
    result['trades_created'] = trades_created
    result['events_imported'] = events_imported
    result['errors'] = errors
    result['import_log_id'] = log_id
    result['message'] = (
        f"Imported {imported} executions ({skipped} duplicates skipped) "
        f"→ {trades_created} positions created/updated."
    )
    if events_imported:
        result['message'] += f" {events_imported} balance events imported."
    if errors:
        result['message'] += f" {len(errors)} errors."
    return result


# ── Shared helpers ───────────────────────────────────────────────────────

def _import_balance_events(conn, account_id, balance_events, errors, log_id=None):
    """Import deposit/withdrawal/interest/dividend events. Returns count imported."""
    count = 0
    for evt in balance_events:
        try:
            ticket = evt.get('broker_ticket_id')
            if ticket and db.account_event_exists(conn, account_id, str(ticket)):
                continue
            db.add_account_event(conn,
                account_id=account_id,
                event_type=evt['event_type'],
                amount=evt['amount'],
                event_date=evt['event_date'],
                description=evt.get('description'),
                broker_ticket_id=str(ticket) if ticket else None,
                import_log_id=log_id,
            )
            count += 1
        except Exception as e:
            errors.append(f"Balance event (ticket {evt.get('broker_ticket_id', '?')}): {e}")
    return count
