"""
Trading212 CSV Export Import Plugin

Parses the CSV export from Trading212 ("Account" → "Statements" → date range).
Returns raw executions (buys/sells) which are then matched by the FIFO engine.

Handles:
  - Market buy / Stop buy / Limit buy  →  buy executions
  - Market sell / Stop sell / Limit sell → sell executions
  - Deposits, Interest on cash, Dividends  → balance events
"""

import csv
import hashlib
from pathlib import Path


PLUGIN_NAME = "trading212_csv"
DISPLAY_NAME = "Trading212 CSV Export"
SUPPORTED_EXTENSIONS = [".csv"]
DEFAULT_ASSET_TYPE = "stocks"

# This plugin returns raw executions, not pre-matched trades.
# The import manager uses the FIFO engine to build trades from these.
IMPORT_MODE = "executions"

# Action classification
_BUY_ACTIONS = {'Market buy', 'Stop buy', 'Limit buy'}
_SELL_ACTIONS = {'Market sell', 'Stop sell', 'Limit sell'}
_DEPOSIT_ACTIONS = {'Deposit'}
_WITHDRAWAL_ACTIONS = {'Withdrawal'}
_INTEREST_ACTIONS = {'Interest on cash'}


# ── Helpers ──────────────────────────────────────────────────────────────

def file_hash(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def _safe_float(val: str, default=0.0) -> float:
    if not val or not val.strip():
        return default
    try:
        return float(val.strip())
    except (ValueError, TypeError):
        return default


def _detect_instrument_type(isin: str, ticker: str, name: str) -> str:
    name_lower = (name or '').lower()
    etf_keywords = ('etf', 'vanguard', 'ishares', 'spdr', 'amundi',
                    'xtrackers', 'lyxor', 'invesco', '(acc)', '(dist)')
    if any(kw in name_lower for kw in etf_keywords):
        return 'etf'
    if isin and (isin.startswith('IE') or isin.startswith('LU')):
        return 'etf'
    return 'stock'


# ── Validation ───────────────────────────────────────────────────────────

def validate(file_path: str) -> tuple:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []

        required = {'Action', 'Time', 'ID'}
        if not required.issubset(set(headers)):
            return False, (
                f"Missing required columns. Expected {required}, "
                f"got: {', '.join(headers[:8])}..."
            )

        t212_markers = {'ISIN', 'No. of shares', 'Price / share',
                        'Currency (Price / share)', 'Exchange rate'}
        if t212_markers.issubset(set(headers)):
            return True, "Valid Trading212 CSV export detected."

        return False, "CSV does not appear to be a Trading212 export."
    except Exception as e:
        return False, f"Error reading file: {e}"


# ── Parsing ──────────────────────────────────────────────────────────────

def parse(file_path: str) -> tuple:
    """
    Parse a Trading212 CSV export.

    Returns (executions, balance_events) where:
      - executions: list of raw buy/sell execution dicts
      - balance_events: list of deposit/dividend/interest dicts
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    executions = []
    balance_events = []

    for row in rows:
        action = (row.get('Action') or '').strip()
        row_id = (row.get('ID') or '').strip()
        time_str = (row.get('Time') or '').strip()

        if not time_str:
            continue

        # ── Deposits / Withdrawals ──
        if action in _DEPOSIT_ACTIONS or action in _WITHDRAWAL_ACTIONS:
            amount = _safe_float(row.get('Total'))
            if action in _WITHDRAWAL_ACTIONS:
                amount = -abs(amount)
            balance_events.append({
                'broker_ticket_id': row_id,
                'event_type': 'deposit' if amount >= 0 else 'withdrawal',
                'amount': amount,
                'event_date': time_str,
                'description': f"Trading212 {action}",
            })
            continue

        # ── Interest ──
        if action in _INTEREST_ACTIONS:
            amount = _safe_float(row.get('Total'))
            if amount:
                balance_events.append({
                    'broker_ticket_id': row_id,
                    'event_type': 'interest',
                    'amount': amount,
                    'event_date': time_str,
                    'description': 'Interest on cash',
                })
            continue

        # ── Dividends ──
        if 'Dividend' in action:
            amount = _safe_float(row.get('Total'))
            ticker = (row.get('Ticker') or '').strip()
            name = (row.get('Name') or '').strip()
            withholding = _safe_float(row.get('Withholding tax'))
            wh_currency = (row.get('Currency (Withholding tax)') or '').strip()
            desc_parts = [f"Dividend: {name} ({ticker})" if name else f"Dividend: {ticker}"]
            desc_parts.append(action)
            if withholding:
                desc_parts.append(f"Withholding: {withholding:.2f} {wh_currency}")
            balance_events.append({
                'broker_ticket_id': row_id,
                'event_type': 'dividend',
                'amount': amount,
                'event_date': time_str,
                'description': ' | '.join(desc_parts),
            })
            continue

        # ── Buy / Sell executions ──
        if action in _BUY_ACTIONS or action in _SELL_ACTIONS:
            ticker = (row.get('Ticker') or '').strip()
            name = (row.get('Name') or '').strip()
            isin = (row.get('ISIN') or '').strip()
            shares = _safe_float(row.get('No. of shares'))
            price = _safe_float(row.get('Price / share'))
            price_currency = (row.get('Currency (Price / share)') or '').strip()
            xrate = _safe_float(row.get('Exchange rate'), 1.0)
            total = _safe_float(row.get('Total'))
            conv_fee = _safe_float(row.get('Currency conversion fee'))
            result_str = (row.get('Result') or '').strip()
            result = _safe_float(result_str) if result_str else None

            is_sell = action in _SELL_ACTIONS

            executions.append({
                'broker_order_id': row_id,
                'action': 'sell' if is_sell else 'buy',
                'symbol': ticker,
                'display_name': f"{name} ({ticker})" if name else ticker,
                'instrument_type': _detect_instrument_type(isin, ticker, name),
                'isin': isin,
                'shares': shares,
                'price': price,
                'price_currency': price_currency,
                'exchange_rate': xrate,
                'total_account_currency': total,
                'commission': conv_fee,
                'broker_result': result,
                'executed_at': time_str,
            })

    return executions, balance_events
