"""Twelve Data chart provider — uses free-tier REST API (800 req/day).

Sign up for a free API key at https://twelvedata.com (takes 30 seconds).
Symbol format: EUR/USD, GBP/JPY, AAPL, etc.
"""
import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from typing import List

from chart_providers.base import ChartProvider, OHLCBar

_BASE_URL = 'https://api.twelvedata.com'

# Journal symbol → Twelve Data symbol (TD uses slash for forex)
_FOREX_MAP = {
    'EURUSD': 'EUR/USD', 'GBPUSD': 'GBP/USD', 'USDJPY': 'USD/JPY',
    'USDCHF': 'USD/CHF', 'AUDUSD': 'AUD/USD', 'NZDUSD': 'NZD/USD',
    'USDCAD': 'USD/CAD', 'EURGBP': 'EUR/GBP', 'EURJPY': 'EUR/JPY',
    'GBPJPY': 'GBP/JPY', 'EURAUD': 'EUR/AUD', 'EURNZD': 'EUR/NZD',
    'EURCAD': 'EUR/CAD', 'EURCHF': 'EUR/CHF', 'AUDCAD': 'AUD/CAD',
    'AUDNZD': 'AUD/NZD', 'AUDJPY': 'AUD/JPY', 'GBPAUD': 'GBP/AUD',
    'GBPCAD': 'GBP/CAD', 'GBPCHF': 'GBP/CHF', 'GBPNZD': 'GBP/NZD',
    'NZDJPY': 'NZD/JPY', 'CADJPY': 'CAD/JPY', 'CADCHF': 'CAD/CHF',
    'CHFJPY': 'CHF/JPY', 'NZDCAD': 'NZD/CAD', 'NZDCHF': 'NZD/CHF',
    # Metals
    'XAUUSD': 'XAU/USD', 'XAGUSD': 'XAG/USD',
}

# Twelve Data interval mapping
_TF_MAP = {
    '1h': '1h',
    '4h': '4h',
    '1d': '1day',
    '1wk': '1week',
    '1mo': '1month',
}


class TwelveDataProvider(ChartProvider):
    PROVIDER_ID = 'twelvedata'
    DISPLAY_NAME = 'Twelve Data'

    def __init__(self):
        super().__init__()
        self.api_key = ''

    @property
    def requires_api_key(self) -> bool:
        return True

    @property
    def api_key_instructions(self) -> str:
        return (
            'Twelve Data requires a free API key.\n\n'
            '1. Go to https://twelvedata.com\n'
            '2. Sign up (free — takes 30 seconds)\n'
            '3. Copy your API key from the dashboard\n'
            '4. Paste it below\n\n'
            'Free tier: 800 requests/day, 8/minute.\n'
            'More than enough for a trading journal.'
        )

    def fetch_ohlc(self, symbol: str, start_date: datetime, end_date: datetime,
                   timeframe: str = '1d') -> List[OHLCBar]:
        if not self.api_key:
            raise ValueError(
                'Twelve Data API key not configured.\n'
                'Select Twelve Data as provider and click Fetch — '
                'you will be prompted to enter your free API key.'
            )

        td_symbol = self.normalize_symbol(symbol)
        td_interval = _TF_MAP.get(timeframe, '1day')

        # Calculate outputsize — request generously (max 5000 on free tier)
        # Better to over-request and let the API return what's available
        days_span = (end_date - start_date).days + 1
        if timeframe == '1h':
            est_bars = days_span * 24
        elif timeframe == '4h':
            est_bars = days_span * 6
        elif timeframe == '1d':
            est_bars = int(days_span * 5 / 7) + 10
        elif timeframe == '1wk':
            est_bars = days_span // 7 + 10
        else:
            est_bars = days_span
        # Always request at least 200, cap at 5000
        outputsize = min(max(est_bars, 200), 5000)

        params = {
            'symbol': td_symbol,
            'interval': td_interval,
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
            'outputsize': str(outputsize),
            'order': 'ASC',  # oldest first
            'apikey': self.api_key,
        }

        query = '&'.join(f'{k}={urllib.request.quote(str(v))}' for k, v in params.items())
        url = f'{_BASE_URL}/time_series?{query}'

        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'TradingJournal/1.0'})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='replace')
            raise ConnectionError(
                f'Twelve Data API error (HTTP {e.code}): {body[:200]}'
            )
        except urllib.error.URLError as e:
            raise ConnectionError(f'Network error: {e.reason}')

        # Check for API-level errors
        if data.get('status') == 'error':
            msg = data.get('message', 'Unknown error')
            code = data.get('code', 0)
            if code == 401:
                raise ValueError(f'Invalid API key. Please check your Twelve Data key.\n{msg}')
            elif code == 429:
                raise ValueError(f'Rate limit exceeded. Wait a minute and try again.\n{msg}')
            raise ValueError(f'Twelve Data error: {msg}')

        values = data.get('values', [])
        if not values:
            raise ValueError(
                f'No data returned for {td_symbol} ({symbol}).\n'
                f'Interval: {td_interval}, Range: {start_date:%Y-%m-%d} to {end_date:%Y-%m-%d}'
            )

        bars = []
        for v in values:
            try:
                dt_str = v['datetime']
                # Daily/weekly: "2025-01-15", Intraday: "2025-01-15 14:00:00"
                if len(dt_str) <= 10:
                    ts = datetime.strptime(dt_str, '%Y-%m-%d')
                else:
                    ts = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')

                bars.append(OHLCBar(
                    timestamp=ts,
                    open=float(v['open']),
                    high=float(v['high']),
                    low=float(v['low']),
                    close=float(v['close']),
                    volume=0.0,  # Forex volume not meaningful from TD
                ))
            except (KeyError, ValueError) as e:
                continue  # Skip malformed bars

        if not bars:
            raise ValueError(f'All data points were malformed for {td_symbol}')

        # Ensure chronological order (we requested ASC but verify)
        bars.sort(key=lambda b: b.timestamp)
        return bars

    def normalize_symbol(self, symbol: str, asset_type: str = 'forex') -> str:
        clean = symbol.upper().replace('.', '').replace(' ', '').replace('#', '')

        # Check forex map
        if clean in _FOREX_MAP:
            return _FOREX_MAP[clean]

        # Strip common MT4 suffixes (use exact substring removal, not rstrip which strips chars)
        for suffix in ['M', '.RAW', '.ECN', '.PRO', '.STD', 'MINI']:
            stripped = clean[:-len(suffix)] if clean.endswith(suffix) else clean
            if stripped in _FOREX_MAP:
                return _FOREX_MAP[stripped]

        # Auto-detect 6-char forex pair and insert slash
        if len(clean) == 6 and clean.isalpha() and asset_type == 'forex':
            return f'{clean[:3]}/{clean[3:]}'

        # Stocks — return as-is
        return clean

    def supported_timeframes(self) -> List[str]:
        return ['1h', '4h', '1d', '1wk']
