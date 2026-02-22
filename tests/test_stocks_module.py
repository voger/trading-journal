"""
Tests for asset_modules/stocks.py — formatting, sqlite3.Row compatibility.

BUG HISTORY:
  - format_trade_cell() crashed on sqlite3.Row because .get() is not supported.
    Fixed with try/except (KeyError, IndexError).
  - Fractional shares (0.026578) were rounded to integers. Fixed formatting.
"""
import sqlite3
import pytest

import database as db
from asset_modules.stocks import StocksModule


@pytest.fixture
def mod():
    return StocksModule()


class TestFormatTradeCell:
    """Test cell formatting with both dict and sqlite3.Row inputs."""

    def test_size_integer_shares(self, mod):
        trade = {'position_size': 100.0}
        assert mod.format_trade_cell(trade, 'size') == '100'

    def test_size_fractional_small(self, mod):
        """BUG PREVENTION: fractional shares < 1 should show 6 decimals."""
        trade = {'position_size': 0.026578}
        result = mod.format_trade_cell(trade, 'size')
        assert result == '0.026578'

    def test_size_fractional_large(self, mod):
        """BUG PREVENTION: fractional shares > 1 should show up to 4 decimals."""
        trade = {'position_size': 53.6433}
        result = mod.format_trade_cell(trade, 'size')
        assert result == '53.6433'

    def test_size_fractional_trailing_zeros_stripped(self, mod):
        trade = {'position_size': 10.5000}
        result = mod.format_trade_cell(trade, 'size')
        assert result == '10.5'

    def test_size_none(self, mod):
        trade = {'position_size': None}
        assert mod.format_trade_cell(trade, 'size') == ''

    def test_size_zero(self, mod):
        trade = {'position_size': 0}
        assert mod.format_trade_cell(trade, 'size') == ''

    def test_entry_price(self, mod):
        trade = {'entry_price': 150.1234}
        assert mod.format_trade_cell(trade, 'entry_price') == '150.12'

    def test_exit_price_none(self, mod):
        trade = {'exit_price': None}
        assert mod.format_trade_cell(trade, 'exit_price') == ''

    def test_commission(self, mod):
        trade = {'commission': 1.50}
        assert mod.format_trade_cell(trade, 'commission') == '1.50'

    def test_commission_zero(self, mod):
        trade = {'commission': 0}
        assert mod.format_trade_cell(trade, 'commission') == ''

    def test_exit_reason_none(self, mod):
        trade = {'exit_reason': None}
        assert mod.format_trade_cell(trade, 'exit_reason') == ''

    def test_exit_reason_value(self, mod):
        trade = {'exit_reason': 'stop_loss'}
        assert mod.format_trade_cell(trade, 'exit_reason') == 'stop_loss'

    def test_unknown_column(self, mod):
        trade = {}
        assert mod.format_trade_cell(trade, 'nonexistent') == ''


class TestDividendsColumnWithSqliteRow:
    """
    BUG PREVENTION: The dividends column accesses trade['_dividends_sum']
    which is a virtual field injected by the caller. sqlite3.Row objects
    don't support .get() and raise IndexError (not KeyError) for missing columns.
    """

    def test_dividends_with_dict(self, mod):
        """Dict with _dividends_sum works."""
        trade = {'_dividends_sum': 3.44}
        assert mod.format_trade_cell(trade, 'dividends') == '3.44'

    def test_dividends_dict_missing_key(self, mod):
        """Dict without _dividends_sum should return '' not crash."""
        trade = {}
        assert mod.format_trade_cell(trade, 'dividends') == ''

    def test_dividends_with_sqlite_row(self, mod, conn):
        """
        BUG PREVENTION: sqlite3.Row raises IndexError (not KeyError) for
        missing columns. format_trade_cell must handle this.
        """
        # Create a real sqlite3.Row from a query
        iid = db.get_or_create_instrument(conn, 'AAPL')
        aid = db.create_account(conn, name='Test', broker='B', asset_type='stocks')
        tid = db.create_trade(conn, account_id=aid, instrument_id=iid,
                              direction='long', entry_date='2025-01-01',
                              entry_price=150.0, position_size=10, status='open')
        row = db.get_trade(conn, tid)

        # This is a sqlite3.Row — accessing '_dividends_sum' should NOT crash
        assert isinstance(row, sqlite3.Row)
        result = mod.format_trade_cell(row, 'dividends')
        assert result == ''

    def test_dividends_with_sqlite_row_none_value(self, mod):
        """Even if _dividends_sum exists but is None, should return ''."""
        trade = {'_dividends_sum': None}
        assert mod.format_trade_cell(trade, 'dividends') == ''

    def test_dividends_zero(self, mod):
        trade = {'_dividends_sum': 0}
        assert mod.format_trade_cell(trade, 'dividends') == ''


class TestTradeColumns:

    def test_has_all_expected_columns(self, mod):
        cols = mod.trade_columns()
        keys = [c['key'] for c in cols]
        assert 'size' in keys
        assert 'entry_price' in keys
        assert 'exit_price' in keys
        assert 'commission' in keys
        assert 'dividends' in keys

    def test_column_dicts_have_required_keys(self, mod):
        for col in mod.trade_columns():
            assert 'key' in col
            assert 'header' in col


class TestModuleMetadata:

    def test_asset_type(self, mod):
        assert mod.ASSET_TYPE == 'stocks'

    def test_display_name(self, mod):
        assert mod.DISPLAY_NAME == 'Stocks & ETFs'

    def test_default_instrument_type(self, mod):
        assert mod.default_instrument_type() == 'stock'

    def test_size_label(self, mod):
        assert mod.size_label() == 'Shares'

    def test_event_types(self, mod):
        types = mod.event_types()
        assert 'dividend' in types
        assert 'interest' in types


class TestStatsHtml:

    def test_empty_stats(self, mod):
        assert mod.format_stats_html({}, 'EUR') == ''

    def test_dividends_in_html(self, mod):
        html = mod.format_stats_html({'total_dividends': 42.50}, 'EUR')
        assert '42.50' in html
        assert 'EUR' in html

    def test_commission_in_html(self, mod):
        html = mod.format_stats_html({'total_commission': -15.0}, 'EUR')
        assert '15.00' in html


class TestExtraTables:

    def test_dividends_table_created(self, conn):
        """The stocks module should create a dividends table."""
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert 'dividends' in tables

    def test_dividends_table_columns(self, conn):
        cols = {r[1] for r in conn.execute("PRAGMA table_info(dividends)").fetchall()}
        expected = {'id', 'account_id', 'instrument_id', 'trade_id',
                    'amount', 'currency', 'pay_date', 'ex_date',
                    'description', 'created_at'}
        missing = expected - cols
        assert not missing, f"Missing columns: {missing}"
