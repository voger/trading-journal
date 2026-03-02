"""
MT4 Detailed Statement Import Plugin
Parses HTML detailed statements exported from MetaTrader 4.
"""

import hashlib
import re
from pathlib import Path
from bs4 import BeautifulSoup


PLUGIN_NAME = "mt4_detailed_statement"
DISPLAY_NAME = "MT4 Detailed Statement (HTML)"
SUPPORTED_EXTENSIONS = [".htm", ".html"]

# Symbols that are clearly not forex
CRYPTO_SYMBOLS = {'ADAUSD', 'BTCUSD', 'ETHUSD', 'XRPUSD', 'DOTUSD', 'SOLUSD', 'LTCUSD'}
COMMODITY_SYMBOLS = {'XAUUSD', 'XAGUSD', 'XPTUSD', 'XPDUSD', 'CORN', 'WHEAT', 'SOYBEAN',
                     'USOIL', 'UKOIL', 'NGAS'}
INDEX_SYMBOLS = {'US500', 'US30', 'US100', 'UK100', 'DE30', 'JP225', 'AU200'}

# JPY pairs and other 3-decimal pairs
JPY_PATTERN = re.compile(r'JPY', re.IGNORECASE)


def detect_instrument_type(symbol: str) -> str:
    sym = symbol.upper()
    if sym in CRYPTO_SYMBOLS:
        return 'crypto'
    if sym in COMMODITY_SYMBOLS:
        return 'commodity'
    if sym in INDEX_SYMBOLS:
        return 'index'
    # Most 6-char symbols ending with standard currencies are forex
    if len(sym) == 6:
        return 'forex'
    # Longer symbols might be commodities or other
    return 'other'


def detect_pip_size(symbol: str) -> float:
    """Determine pip size based on symbol."""
    sym = symbol.upper()
    if detect_instrument_type(sym) != 'forex':
        return None
    if JPY_PATTERN.search(sym):
        return 0.01
    return 0.0001


def format_display_name(symbol: str) -> str:
    """Convert MT4 symbol to display name. E.g., EURUSD -> EUR/USD"""
    sym = symbol.upper()
    itype = detect_instrument_type(sym)
    if itype == 'forex' and len(sym) == 6:
        return f"{sym[:3]}/{sym[3:]}"
    return sym


def extract_exit_reason(title_attr: str) -> str:
    """Extract exit reason from the ticket cell's title attribute."""
    if not title_attr:
        return 'manual'
    if '[sl]' in title_attr.lower():
        return 'stop_loss'
    if '[tp]' in title_attr.lower():
        return 'target_hit'
    if 'so:' in title_attr.lower():
        return 'stop_out'
    return 'manual'


def parse_mt4_datetime(dt_str: str) -> str:
    """Convert MT4 datetime format '2025.12.08 10:22:44' to ISO format."""
    dt_str = dt_str.strip()
    return dt_str.replace('.', '-', 2)


def file_hash(file_path: str) -> str:
    """Compute SHA256 hash of a file."""
    h = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def validate(file_path: str) -> tuple:
    """Check if file is a valid MT4 detailed statement."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        soup = BeautifulSoup(content, 'html.parser')
        title = soup.find('title')
        if title and 'statement' in title.text.lower():
            return True, "Valid MT4 statement detected."
        # Fallback: look for "Closed Transactions:" text
        if 'Closed Transactions:' in content or 'closed transactions' in content.lower():
            return True, "Valid MT4 statement detected."
        return False, "File does not appear to be an MT4 detailed statement."
    except Exception as e:
        return False, f"Error reading file: {e}"


def parse(file_path: str) -> tuple:
    """
    Parse an MT4 detailed statement HTML file.
    Returns a list of standardized trade dictionaries.
    """
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    soup = BeautifulSoup(content, 'html.parser')
    trades = []
    balance_events = []

    # Find all table rows
    rows = soup.find_all('tr')

    in_closed_section = False
    in_open_section = False

    for row in rows:
        cells = row.find_all('td')
        if not cells:
            continue

        # Detect section headers
        first_text = cells[0].get_text(strip=True)
        if 'Closed Transactions:' in first_text:
            in_closed_section = True
            in_open_section = False
            continue
        if 'Open Trades:' in first_text:
            in_closed_section = False
            in_open_section = True
            continue
        if 'Working Orders:' in first_text or 'Summary:' in first_text:
            in_closed_section = False
            in_open_section = False
            continue

        if not in_closed_section and not in_open_section:
            continue

        # Skip header rows
        if cells[0].get('bgcolor') == '#C0C0C0' or row.find('td', bgcolor='#C0C0C0'):
            continue

        # Need at least 14 cells for a trade row
        if len(cells) < 14:
            # Could be a balance row (deposit/withdrawal)
            if len(cells) >= 5:
                type_text = cells[2].get_text(strip=True).lower() if len(cells) > 2 else ''
                if type_text == 'balance' and in_closed_section:
                    try:
                        ticket_id = cells[0].get_text(strip=True)
                        event_date = parse_mt4_datetime(cells[1].get_text(strip=True))
                        amount = float(cells[-1].get_text(strip=True).replace(' ', ''))
                        description = cells[3].get_text(strip=True) if len(cells) > 3 else ''
                        balance_events.append({
                            'broker_ticket_id': ticket_id,
                            'event_date': event_date,
                            'amount': amount,
                            'event_type': 'deposit' if amount >= 0 else 'withdrawal',
                            'description': description,
                        })
                    except (ValueError, IndexError):
                        pass
            continue

        # Extract cell values
        try:
            ticket_cell = cells[0]
            ticket_id = ticket_cell.get_text(strip=True)
            title_attr = ticket_cell.get('title', '')

            trade_type = cells[2].get_text(strip=True).lower()

            # Skip non-trade rows (balance, credit, etc.)
            if trade_type not in ('buy', 'sell'):
                continue

            symbol = cells[4].get_text(strip=True).upper()
            if not symbol:
                continue
            size = float(cells[3].get_text(strip=True))
            open_time = parse_mt4_datetime(cells[1].get_text(strip=True))
            open_price = float(cells[5].get_text(strip=True))
            sl_price = float(cells[6].get_text(strip=True))
            tp_price = float(cells[7].get_text(strip=True))
            close_time = cells[8].get_text(strip=True)
            close_price = float(cells[9].get_text(strip=True))
            commission = float(cells[10].get_text(strip=True))
            taxes = float(cells[11].get_text(strip=True))
            swap = float(cells[12].get_text(strip=True))
            profit = float(cells[13].get_text(strip=True).replace(' ', ''))

            # Determine direction
            direction = 'long' if trade_type == 'buy' else 'short'

            # Handle zero SL/TP (means not set)
            if sl_price == 0 or sl_price == 0.0:
                sl_price = None
            if tp_price == 0 or tp_price == 0.0:
                tp_price = None

            # Determine status
            if in_open_section or not close_time.strip():
                status = 'open'
                close_time_iso = None
                close_price_val = None
                exit_reason = None
            else:
                status = 'closed'
                close_time_iso = parse_mt4_datetime(close_time)
                close_price_val = close_price
                exit_reason = extract_exit_reason(title_attr)

            # Calculate pips for forex
            pip_size = detect_pip_size(symbol)
            pnl_pips = None
            if pip_size and close_price_val is not None:
                if direction == 'long':
                    pnl_pips = round((close_price_val - open_price) / pip_size, 1)
                else:
                    pnl_pips = round((open_price - close_price_val) / pip_size, 1)

            trade = {
                'broker_ticket_id': ticket_id,
                'symbol': symbol,
                'display_name': format_display_name(symbol),
                'instrument_type': detect_instrument_type(symbol),
                'direction': direction,
                'entry_date': open_time,
                'entry_price': open_price,
                'position_size': size,
                'stop_loss_price': sl_price,
                'take_profit_price': tp_price,
                'exit_date': close_time_iso,
                'exit_price': close_price_val,
                'exit_reason': exit_reason,
                'pnl_pips': pnl_pips,
                'pnl_account_currency': profit,
                'commission': commission + taxes,  # Combine commission and taxes
                'swap': swap,
                'pip_size': pip_size,
                'status': status,
                'source_ea': (title_attr.split(']')[-1].strip() if ']' in title_attr
                             else title_attr.strip() if title_attr else None) or None,
            }
            trades.append(trade)

        except (ValueError, IndexError) as e:
            # Skip malformed rows
            continue

    return trades, balance_events


def parse_account_info(file_path: str) -> dict:
    """Extract account information from the statement header."""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    soup = BeautifulSoup(content, 'html.parser')
    info = {}

    title = soup.find('title')
    if title:
        # "Statement: 131631 - Alkis Tsamis 001"
        match = re.search(r'Statement:\s*(\d+)', title.text)
        if match:
            info['account_number'] = match.group(1)

    # Find broker name from the header div
    header_div = soup.find('div', style=lambda s: s and '20pt' in str(s))
    if header_div:
        info['broker'] = header_div.get_text(strip=True)

    # Find account details from the first table row
    first_row = soup.find('tr', align='left')
    if first_row:
        cells = first_row.find_all('td')
        for cell in cells:
            text = cell.get_text(strip=True)
            if text.startswith('Currency:'):
                info['currency'] = text.replace('Currency:', '').strip()
            if text.startswith('Account:'):
                info['account_number'] = text.replace('Account:', '').strip()
            if text.startswith('Name:'):
                info['account_name'] = text.replace('Name:', '').strip()

    return info
