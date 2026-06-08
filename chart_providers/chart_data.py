"""Headless chart data core: fetch + 401-recovery + cache. No PyQt."""
import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from chart_providers.base import OHLCBar
from chart_providers import key_store


def _cal_days_for_bars(tf, n):
    """Approximate calendar days needed to contain n bars of a given timeframe."""
    if tf == '1wk':
        return n * 7 + 3
    elif tf == '1d':
        return int(n * 7 / 5) + 3
    elif tf == '4h':
        return int(max(1, n / 6) * 7 / 5) + 3
    elif tf == '1h':
        return int(max(1, n / 22) * 7 / 5) + 3
    return n + 5


def compute_window(entry_dt, exit_dt, tf, bars_before, bars_after, now=None):
    """Return (start, end, capped) for the fetch window.

    `now` is injectable for testing; end is clamped to it (capped=True) when the
    requested window runs past the present.
    """
    if now is None:
        now = datetime.now()
    start = entry_dt - timedelta(days=_cal_days_for_bars(tf, bars_before))
    ref = exit_dt or entry_dt
    end = ref + timedelta(days=_cal_days_for_bars(tf, bars_after))
    capped = end > now
    if capped:
        end = now
    return start, end, capped


def bars_to_json(bars):
    """Serialize OHLCBars to the JSON string stored in trades.chart_data."""
    if not bars:
        return None
    return json.dumps([{'timestamp': b.timestamp.isoformat(),
                        'open': b.open, 'high': b.high, 'low': b.low,
                        'close': b.close, 'volume': b.volume}
                       for b in bars])


def bars_from_json(json_str):
    """Parse the trades.chart_data JSON string back into OHLCBars."""
    if not json_str:
        return []
    return [OHLCBar(timestamp=datetime.fromisoformat(d['timestamp']),
                    open=d['open'], high=d['high'], low=d['low'],
                    close=d['close'], volume=d.get('volume', 0))
            for d in json.loads(json_str)]


@dataclass
class ChartResult:
    bars: list              # list[OHLCBar]
    normalized_symbol: str
    capped: bool            # end was clamped to now
    chart_json: str         # bars serialized once (same string cached to the DB)


class ChartDataError(Exception):
    """Fetch produced no usable data."""


def _is_auth_error(e):
    s = str(e)
    return 'Invalid API key' in s or '401' in s


class ChartData:
    """Headless fetch + 401-recovery + cache. Reaches the DB via a Journal."""

    def __init__(self, journal):
        self.journal = journal

    def fetch(self, provider, symbol, asset_type, entry_dt, exit_dt,
              tf, bars_before, bars_after, trade_id=None) -> 'ChartResult':
        start, end, capped = compute_window(
            entry_dt, exit_dt, tf, bars_before, bars_after)
        norm = provider.normalize_symbol(symbol, asset_type)
        try:
            bars = provider.fetch_ohlc(norm, start, end, tf)
        except Exception as e:
            if _is_auth_error(e):
                key_store.clear(self.journal.conn, provider.PROVIDER_ID)
                if hasattr(provider, 'api_key'):
                    provider.api_key = ''
            raise
        if not bars:
            raise ChartDataError("No data returned")
        chart_json = bars_to_json(bars)
        if trade_id is not None:
            self.journal.save_chart_data(trade_id, chart_json)
        return ChartResult(bars=bars, normalized_symbol=norm, capped=capped,
                           chart_json=chart_json)
