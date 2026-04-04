"""
Tests for plugins/trading212_plugin.py — validation, parsing, edge cases.
"""
import csv
import os
import pytest

from plugins import trading212_plugin as t212


class TestValidation:

    def test_valid_csv(self, sample_t212_csv):
        ok, msg = t212.validate(sample_t212_csv)
        assert ok is True

    def test_invalid_csv_missing_columns(self, bogus_csv):
        ok, msg = t212.validate(bogus_csv)
        assert ok is False
        assert 'Missing' in msg or 'not appear' in msg

    def test_nonexistent_file(self):
        ok, msg = t212.validate('/nonexistent/file.csv')
        assert ok is False
        assert 'Error' in msg

    def test_empty_csv_with_headers(self, sample_t212_csv_empty):
        ok, msg = t212.validate(sample_t212_csv_empty)
        assert ok is True

    def test_html_file_rejected(self, tmp_path):
        f = tmp_path / "test.html"
        f.write_text("<html><body>Not a CSV</body></html>")
        ok, msg = t212.validate(str(f))
        assert ok is False


class TestParsing:

    def test_parse_returns_tuple(self, sample_t212_csv):
        result = t212.parse(sample_t212_csv)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_execution_count(self, sample_t212_csv):
        executions, events = t212.parse(sample_t212_csv)
        buys = [e for e in executions if e['action'] == 'buy']
        sells = [e for e in executions if e['action'] == 'sell']
        # AAPL: 2 buys + 1 sell, VUAA: 2 buys, MSFT: 1 buy + 1 sell, TEST: 1 buy + 2 sells
        assert len(buys) == 6
        assert len(sells) == 4

    def test_balance_event_count(self, sample_t212_csv):
        _, events = t212.parse(sample_t212_csv)
        types = [e['event_type'] for e in events]
        assert types.count('deposit') == 1
        assert types.count('interest') == 1
        assert types.count('dividend') == 1

    def test_buy_execution_fields(self, sample_t212_csv):
        executions, _ = t212.parse(sample_t212_csv)
        buy1 = next(e for e in executions if e['broker_order_id'] == 'BUY001')
        assert buy1['action'] == 'buy'
        assert buy1['symbol'] == 'AAPL'
        assert buy1['shares'] == 10.0
        assert buy1['price'] == 180.0
        assert buy1['price_currency'] == 'USD'
        assert buy1['exchange_rate'] == 1.10
        assert buy1['commission'] == 0.50
        assert buy1['broker_result'] is None  # buys have no Result

    def test_sell_execution_fields(self, sample_t212_csv):
        executions, _ = t212.parse(sample_t212_csv)
        sell1 = next(e for e in executions if e['broker_order_id'] == 'SELL001')
        assert sell1['action'] == 'sell'
        assert sell1['symbol'] == 'AAPL'
        assert sell1['shares'] == 15.0
        assert sell1['price'] == 200.0
        assert sell1['broker_result'] == 250.0

    def test_deposit_event(self, sample_t212_csv):
        _, events = t212.parse(sample_t212_csv)
        dep = next(e for e in events if e['event_type'] == 'deposit')
        assert dep['amount'] == 1000.0
        assert dep['broker_ticket_id'] == 'DEP001'

    def test_interest_event(self, sample_t212_csv):
        _, events = t212.parse(sample_t212_csv)
        interest = next(e for e in events if e['event_type'] == 'interest')
        assert interest['amount'] == 0.12

    def test_dividend_event(self, sample_t212_csv):
        _, events = t212.parse(sample_t212_csv)
        div = next(e for e in events if e['event_type'] == 'dividend')
        assert div['amount'] == 1.50
        assert 'Withholding: 0.30' in div['description']

    def test_empty_csv_parses_to_empty(self, sample_t212_csv_empty):
        executions, events = t212.parse(sample_t212_csv_empty)
        assert len(executions) == 0
        assert len(events) == 0


class TestInstrumentDetection:

    def test_etf_by_name_keywords(self):
        assert t212._detect_instrument_type('', '', 'Vanguard S&P 500 UCITS ETF (Acc)') == 'etf'
        assert t212._detect_instrument_type('', '', 'iShares MSCI World') == 'etf'
        assert t212._detect_instrument_type('', '', 'SPDR Gold Trust') == 'etf'

    def test_isin_alone_does_not_classify_as_etf(self):
        """ISIN prefix alone is unreliable — Irish/Luxembourg stocks exist."""
        assert t212._detect_instrument_type('IE00BK5BQT80', '', 'Some Fund') == 'stock'
        assert t212._detect_instrument_type('LU0000000001', '', 'Some Fund') == 'stock'
        # But name keywords still work
        assert t212._detect_instrument_type('IE00BK5BQT80', '', 'iShares Core Fund') == 'etf'

    def test_stock_default(self):
        assert t212._detect_instrument_type('US0378331005', 'AAPL', 'Apple Inc') == 'stock'


class TestPluginMetadata:

    def test_plugin_name(self):
        assert t212.PLUGIN_NAME == 'trading212_csv'

    def test_extensions(self):
        assert '.csv' in t212.SUPPORTED_EXTENSIONS

    def test_import_mode(self):
        assert t212.IMPORT_MODE == 'executions'

    def test_default_asset_type(self):
        assert t212.DEFAULT_ASSET_TYPE == 'stocks'

    def test_file_hash(self, sample_t212_csv):
        h = t212.file_hash(sample_t212_csv)
        assert isinstance(h, str)
        assert len(h) == 64  # SHA256 hex
        # Same file = same hash
        assert t212.file_hash(sample_t212_csv) == h
