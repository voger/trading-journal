"""
Tests for import_manager.py — plugin loading, import pipeline, dedup, errors.
"""
import os
import pytest

import database as db
from import_manager import (
    PLUGINS, get_available_plugins, detect_plugin, run_import,
)


class TestPluginLoading:

    def test_plugins_loaded(self):
        """BUG PREVENTION: plugins must load without crashing the app."""
        assert len(PLUGINS) >= 1, "No plugins loaded!"

    def test_trading212_registered(self):
        assert 'trading212_csv' in PLUGINS

    def test_mt4_registered(self):
        assert 'mt4_detailed_statement' in PLUGINS

    def test_get_available_plugins_format(self):
        plugins = get_available_plugins()
        assert len(plugins) >= 2
        for name, display, exts in plugins:
            assert isinstance(name, str)
            assert isinstance(display, str)
            assert isinstance(exts, list)
            assert all(e.startswith('.') for e in exts)

    def test_all_plugins_have_required_attributes(self):
        """Every plugin must have the minimal interface."""
        for name, mod in PLUGINS.items():
            assert hasattr(mod, 'PLUGIN_NAME')
            assert hasattr(mod, 'DISPLAY_NAME')
            assert hasattr(mod, 'SUPPORTED_EXTENSIONS')
            assert hasattr(mod, 'validate')
            assert hasattr(mod, 'parse')
            assert callable(mod.validate)
            assert callable(mod.parse)


class TestPluginDetection:

    def test_detect_trading212_csv(self, sample_t212_csv):
        plugin = detect_plugin(sample_t212_csv)
        assert plugin is not None
        assert plugin.PLUGIN_NAME == 'trading212_csv'

    def test_detect_returns_none_for_unknown(self, bogus_csv):
        plugin = detect_plugin(bogus_csv)
        assert plugin is None

    def test_detect_returns_none_for_nonexistent(self):
        plugin = detect_plugin('/nonexistent/file.xyz')
        assert plugin is None

    def test_detect_by_extension_and_content(self, tmp_path):
        """A .csv that doesn't match T212 format should not be detected."""
        f = tmp_path / "random.csv"
        f.write_text("X,Y,Z\n1,2,3\n")
        plugin = detect_plugin(str(f))
        assert plugin is None


class TestImportExecutionMode:

    def test_basic_import(self, conn, stock_account, sample_t212_csv):
        result = run_import(conn, stock_account, sample_t212_csv)
        assert result['success'] is True
        assert result['trades_imported'] > 0
        assert result['import_log_id'] is not None

    def test_import_creates_executions(self, conn, stock_account, sample_t212_csv):
        run_import(conn, stock_account, sample_t212_csv)
        count = conn.execute(
            "SELECT COUNT(*) FROM executions WHERE account_id=?",
            (stock_account,)).fetchone()[0]
        assert count == 10  # 6 buys + 4 sells from sample CSV

    def test_import_creates_trades(self, conn, stock_account, sample_t212_csv):
        run_import(conn, stock_account, sample_t212_csv)
        trades = conn.execute(
            "SELECT * FROM trades WHERE account_id=?",
            (stock_account,)).fetchall()
        assert len(trades) == 4  # AAPL, VUAA, MSFT, TEST

    def test_import_creates_balance_events(self, conn, stock_account, sample_t212_csv):
        result = run_import(conn, stock_account, sample_t212_csv)
        events = db.get_account_events(conn, stock_account)
        types = [e['event_type'] for e in events]
        assert 'deposit' in types
        assert 'interest' in types
        assert 'dividend' in types

    def test_import_creates_lot_consumptions(self, conn, stock_account, sample_t212_csv):
        run_import(conn, stock_account, sample_t212_csv)
        lots = conn.execute("SELECT COUNT(*) FROM lot_consumptions").fetchone()[0]
        assert lots > 0

    def test_import_creates_import_log(self, conn, stock_account, sample_t212_csv):
        result = run_import(conn, stock_account, sample_t212_csv)
        log = conn.execute(
            "SELECT * FROM import_logs WHERE id=?",
            (result['import_log_id'],)).fetchone()
        assert log is not None
        assert log['plugin_name'] == 'trading212_csv'
        assert log['trades_imported'] > 0


class TestImportDeduplication:

    def test_reimport_skips_all_executions(self, conn, stock_account, sample_t212_csv):
        """BUG PREVENTION: importing same file twice should skip all duplicates."""
        r1 = run_import(conn, stock_account, sample_t212_csv)
        r2 = run_import(conn, stock_account, sample_t212_csv)

        assert r2['trades_imported'] == 0
        assert r2['trades_skipped'] == r1['trades_imported']

    def test_no_duplicate_executions(self, conn, stock_account, sample_t212_csv):
        run_import(conn, stock_account, sample_t212_csv)
        count1 = conn.execute("SELECT COUNT(*) FROM executions").fetchone()[0]

        run_import(conn, stock_account, sample_t212_csv)
        count2 = conn.execute("SELECT COUNT(*) FROM executions").fetchone()[0]

        assert count1 == count2

    def test_no_duplicate_trades(self, conn, stock_account, sample_t212_csv):
        run_import(conn, stock_account, sample_t212_csv)
        count1 = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]

        run_import(conn, stock_account, sample_t212_csv)
        count2 = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]

        assert count1 == count2


class TestImportErrorHandling:

    def test_unknown_plugin_name(self, conn, stock_account, sample_t212_csv):
        result = run_import(conn, stock_account, sample_t212_csv, plugin_name='nonexistent')
        assert result['success'] is False
        assert 'Unknown plugin' in result['message']

    def test_invalid_file_format(self, conn, stock_account, bogus_csv):
        result = run_import(conn, stock_account, bogus_csv)
        assert result['success'] is False

    def test_nonexistent_file(self, conn, stock_account):
        result = run_import(conn, stock_account, '/no/such/file.csv')
        assert result['success'] is False

    def test_empty_file_succeeds(self, conn, stock_account, sample_t212_csv_empty):
        result = run_import(conn, stock_account, sample_t212_csv_empty)
        assert result['success'] is True
        assert result['trades_imported'] == 0

    def test_missing_broker_order_id_skipped(self, conn, stock_account, tmp_path):
        """Executions without IDs should be skipped, not crash."""
        import csv
        csv_path = str(tmp_path / "noid.csv")
        headers = [
            'Action', 'Time', 'ISIN', 'Ticker', 'Name', 'No. of shares',
            'Price / share', 'Currency (Price / share)', 'Exchange rate',
            'Result', 'Total', 'Currency (Total)', 'Withholding tax',
            'Currency (Withholding tax)', 'ID', 'Currency conversion fee', 'Notes',
        ]
        row = ['Market buy', '2025-01-01', 'US000', 'XX', 'Test', '10', '100',
               'USD', '1.1', '', '-909', 'EUR', '', '', '', '0', '']
        with open(csv_path, 'w', newline='') as f:
            w = csv.writer(f); w.writerow(headers); w.writerow(row)

        result = run_import(conn, stock_account, csv_path)
        assert result['success'] is True
        assert result['trades_skipped'] == 1


class TestImportTradeMode:
    """Ensure legacy trade-based import still works (MT4 path)."""

    def test_trade_mode_attribute(self):
        mt4 = PLUGINS.get('mt4_detailed_statement')
        if mt4:
            mode = getattr(mt4, 'IMPORT_MODE', 'trades')
            assert mode == 'trades'

    def test_execution_mode_attribute(self):
        t212 = PLUGINS.get('trading212_csv')
        assert getattr(t212, 'IMPORT_MODE', 'trades') == 'executions'


class TestImportSpecificCases:

    def test_aapl_closed_position(self, conn, stock_account, sample_t212_csv):
        """AAPL: 2 buys + 1 sell = closed position."""
        run_import(conn, stock_account, sample_t212_csv)
        trade = conn.execute(
            """SELECT t.* FROM trades t
               JOIN instruments i ON t.instrument_id = i.id
               WHERE i.symbol = 'AAPL' AND t.account_id = ?""",
            (stock_account,)).fetchone()
        assert trade['status'] == 'closed'
        assert trade['pnl_account_currency'] == 250.0

    def test_vuaa_open_position(self, conn, stock_account, sample_t212_csv):
        """VUAA: 2 buys + 0 sells = open position with 2 lots."""
        run_import(conn, stock_account, sample_t212_csv)
        trade = conn.execute(
            """SELECT t.* FROM trades t
               JOIN instruments i ON t.instrument_id = i.id
               WHERE i.symbol = 'VUAA' AND t.account_id = ?""",
            (stock_account,)).fetchone()
        assert trade['status'] == 'open'
        assert trade['position_size'] == 7.0  # 4 + 3

    def test_msft_partial_close(self, conn, stock_account, sample_t212_csv):
        """MSFT: buy 2, sell 1 = still open with 1 share."""
        run_import(conn, stock_account, sample_t212_csv)
        trade = conn.execute(
            """SELECT t.* FROM trades t
               JOIN instruments i ON t.instrument_id = i.id
               WHERE i.symbol = 'MSFT' AND t.account_id = ?""",
            (stock_account,)).fetchone()
        assert trade['status'] == 'open'

    def test_split_sell_one_trade(self, conn, stock_account, sample_t212_csv):
        """BUG PREVENTION: TEST (split sell pattern) = 1 trade, not 2."""
        run_import(conn, stock_account, sample_t212_csv)
        trades = conn.execute(
            """SELECT t.* FROM trades t
               JOIN instruments i ON t.instrument_id = i.id
               WHERE i.symbol = 'TEST' AND t.account_id = ?""",
            (stock_account,)).fetchall()
        assert len(trades) == 1
        assert trades[0]['status'] == 'closed'


class TestImportAccountCreationClosure:
    """Regression: QPushButton.clicked emits bool, must not overwrite `info`."""

    def test_ac_closure_signature(self):
        """BUG PREVENTION: _ac closure must accept checked=bool as first param.

        The bug: def _ac(info=info, ...) — when connected to
        QPushButton.clicked, the signal passes False as the first
        positional argument, overwriting `info` with False.

        Fix: def _ac(checked=False, info=info, ...)
        """
        import ast, inspect, textwrap
        from tabs.trades import TradesTab
        source = inspect.getsource(TradesTab._on_import)
        tree = ast.parse(textwrap.dedent(source))

        # Find all inner function defs named _ac
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == '_ac':
                args = node.args
                # First parameter must be 'checked' (not 'info')
                all_args = [a.arg for a in args.args]
                assert len(all_args) >= 1, "_ac must have at least one parameter"
                assert all_args[0] == 'checked', (
                    f"_ac first param must be 'checked', got '{all_args[0]}'. "
                    f"QPushButton.clicked passes a bool that will overwrite it."
                )
                return
        pytest.fail("Could not find _ac function def in TradesTab._on_import")
