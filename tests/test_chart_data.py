"""Tests for the headless ChartData core and its DB cache (issue #5)."""
import json
from datetime import datetime

import pytest

from chart_providers.base import OHLCBar
from chart_providers import key_store
from chart_providers.chart_data import (
    ChartData, ChartDataError, ChartResult,
    compute_window, bars_to_json, bars_from_json,
)


# ── helpers ────────────────────────────────────────────────────────────────

def _make_trade(journal):
    """Insert a minimal valid trade row; return its id."""
    aid = journal.create_account(name='A', broker='B', currency='EUR',
                                 asset_type='stocks')
    iid = journal.get_or_create_instrument('AAPL', instrument_type='stocks')
    return journal.create_trade(account_id=aid, instrument_id=iid,
                                direction='long', entry_date='2025-06-10',
                                entry_price=100.0, position_size=10)


def _bar(day, price=100.0):
    return OHLCBar(timestamp=datetime(2025, 6, day), open=price, high=price + 1,
                   low=price - 1, close=price, volume=1000)


class FakeProvider:
    """Stand-in for a chart provider — no network."""
    PROVIDER_ID = 'fake'

    def __init__(self, bars=None, error=None):
        self.api_key = 'KEY'
        self._bars = bars if bars is not None else []
        self._error = error
        self.normalized = None

    def normalize_symbol(self, symbol, asset_type):
        self.normalized = f'{symbol}:{asset_type}'
        return self.normalized

    def fetch_ohlc(self, sym, start, end, tf):
        if self._error:
            raise self._error
        return self._bars


# ── cache write ────────────────────────────────────────────────────────────

class TestSaveChartData:
    def test_save_chart_data_persists(self, journal):
        tid = _make_trade(journal)
        journal.save_chart_data(tid, '[{"x":1}]')
        row = journal.conn.execute(
            "SELECT chart_data FROM trades WHERE id=?", (tid,)).fetchone()
        assert row['chart_data'] == '[{"x":1}]'


# ── pure helpers ───────────────────────────────────────────────────────────

class TestPureHelpers:
    def test_compute_window_caps_at_now(self):
        entry = datetime(2025, 6, 10)
        now = datetime(2025, 6, 15)
        start, end, capped = compute_window(entry, None, '1d', 50, 100, now=now)
        assert capped is True
        assert end == now
        assert start < entry

    def test_compute_window_no_cap(self):
        entry = datetime(2025, 6, 10)
        now = datetime(2030, 1, 1)
        start, end, capped = compute_window(entry, None, '1d', 50, 10, now=now)
        assert capped is False
        assert end < now
        assert start < entry

    def test_compute_window_uses_exit_as_ref(self):
        entry = datetime(2025, 6, 10)
        exit_dt = datetime(2025, 6, 20)
        now = datetime(2030, 1, 1)
        _, end_with_exit, _ = compute_window(entry, exit_dt, '1d', 50, 10, now=now)
        _, end_no_exit, _ = compute_window(entry, None, '1d', 50, 10, now=now)
        assert end_with_exit > end_no_exit

    def test_bars_json_roundtrip(self):
        bars = [_bar(10), _bar(11, 105.0)]
        restored = bars_from_json(bars_to_json(bars))
        assert len(restored) == 2
        assert restored[1].close == 105.0
        assert restored[0].timestamp == datetime(2025, 6, 10)
        assert restored[0].volume == 1000

    def test_bars_to_json_empty(self):
        assert bars_to_json([]) is None

    def test_bars_from_json_empty(self):
        assert bars_from_json(None) == []
        assert bars_from_json('') == []


# ── fetch ──────────────────────────────────────────────────────────────────

class TestChartDataFetch:
    def test_happy_path_returns_result(self, journal):
        tid = _make_trade(journal)
        bars = [_bar(10), _bar(11)]
        prov = FakeProvider(bars=bars)
        core = ChartData(journal)
        result = core.fetch(prov, 'AAPL', 'stocks',
                            datetime(2025, 6, 10), datetime(2025, 6, 11),
                            '1d', 50, 10, trade_id=tid)
        assert isinstance(result, ChartResult)
        assert result.bars == bars
        assert result.normalized_symbol == 'AAPL:stocks'
        assert result.capped is False  # 2025 window, run far later

    def test_writes_cache_to_db(self, journal):
        tid = _make_trade(journal)
        bars = [_bar(10), _bar(11)]
        core = ChartData(journal)
        core.fetch(FakeProvider(bars=bars), 'AAPL', 'stocks',
                   datetime(2025, 6, 10), None, '1d', 50, 10, trade_id=tid)
        row = journal.conn.execute(
            "SELECT chart_data FROM trades WHERE id=?", (tid,)).fetchone()
        restored = bars_from_json(row['chart_data'])
        assert len(restored) == 2
        assert restored[0].close == 100.0

    def test_no_trade_id_skips_cache(self, journal):
        core = ChartData(journal)
        result = core.fetch(FakeProvider(bars=[_bar(10)]), 'AAPL', 'stocks',
                            datetime(2025, 6, 10), None, '1d', 50, 10)
        assert len(result.bars) == 1  # no crash without a trade_id

    def test_empty_result_raises(self, journal):
        core = ChartData(journal)
        with pytest.raises(ChartDataError):
            core.fetch(FakeProvider(bars=[]), 'AAPL', 'stocks',
                       datetime(2025, 6, 10), None, '1d', 50, 10)

    def test_401_clears_key_and_reraises(self, journal):
        key_store.save(journal.conn, 'fake', 'SECRET')
        prov = FakeProvider(error=ValueError('Invalid API key (401)'))
        core = ChartData(journal)
        with pytest.raises(ValueError):
            core.fetch(prov, 'AAPL', 'stocks',
                       datetime(2025, 6, 10), None, '1d', 50, 10)
        assert not key_store.get(journal.conn, 'fake')
        assert prov.api_key == ''

    def test_non_auth_error_keeps_key(self, journal):
        key_store.save(journal.conn, 'fake', 'SECRET')
        prov = FakeProvider(error=RuntimeError('network down'))
        core = ChartData(journal)
        with pytest.raises(RuntimeError):
            core.fetch(prov, 'AAPL', 'stocks',
                       datetime(2025, 6, 10), None, '1d', 50, 10)
        assert key_store.get(journal.conn, 'fake') == 'SECRET'
        assert prov.api_key == 'KEY'
