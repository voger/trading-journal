"""
Integration tests using a real MT4 Detailed Statement HTML export.
Skipped automatically if the file is not provided.

Run with:
    pytest tests/ -q --real-mt4=/path/to/statement.htm

These tests verify structural correctness of the MT4 import pipeline.
After running against your real file for the first time, fill in the
exact expected counts marked with TODO below.
"""
import pytest

import database as db
from import_manager import run_import, detect_plugin
from plugins.mt4_plugin import parse, parse_account_info, validate


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def imported_mt4(conn, forex_account, real_mt4):
    """Import the real MT4 statement and return (conn, account_id)."""
    result = run_import(conn, forex_account, real_mt4)
    assert result['success'], f"Import failed: {result.get('message')}"
    return conn, forex_account


# ── Validation & Detection ────────────────────────────────────────────────────

class TestMT4Detection:

    def test_plugin_detected(self, real_mt4):
        plugin = detect_plugin(real_mt4)
        assert plugin is not None, "MT4 plugin should be detected for this file"
        assert plugin.PLUGIN_NAME == 'mt4_detailed_statement'

    def test_file_validates(self, real_mt4):
        ok, msg = validate(real_mt4)
        assert ok, f"validate() returned False: {msg}"

    def test_account_info_parsed(self, real_mt4):
        info = parse_account_info(real_mt4)
        # Should extract at least something from the header
        assert isinstance(info, dict)
        assert len(info) > 0, "parse_account_info returned empty dict"


# ── Parse-level checks (no DB) ────────────────────────────────────────────────

class TestMT4Parse:

    def test_parse_returns_trades_and_events(self, real_mt4):
        trades, balance_events = parse(real_mt4)
        assert isinstance(trades, list)
        assert isinstance(balance_events, list)

    def test_parse_yields_trades(self, real_mt4):
        trades, _ = parse(real_mt4)
        assert len(trades) > 0, "Expected at least one trade in the statement"

    def test_trade_required_fields(self, real_mt4):
        trades, _ = parse(real_mt4)
        required = {'broker_ticket_id', 'symbol', 'direction', 'entry_date',
                    'entry_price', 'position_size', 'status', 'pnl_account_currency'}
        for t in trades:
            missing = required - t.keys()
            assert not missing, f"Trade {t.get('broker_ticket_id')} missing fields: {missing}"

    def test_directions_valid(self, real_mt4):
        trades, _ = parse(real_mt4)
        for t in trades:
            assert t['direction'] in ('long', 'short'), \
                f"Invalid direction '{t['direction']}' for ticket {t['broker_ticket_id']}"

    def test_status_valid(self, real_mt4):
        trades, _ = parse(real_mt4)
        for t in trades:
            assert t['status'] in ('open', 'closed'), \
                f"Invalid status '{t['status']}' for ticket {t['broker_ticket_id']}"

    def test_closed_trades_have_exit(self, real_mt4):
        trades, _ = parse(real_mt4)
        for t in trades:
            if t['status'] == 'closed':
                assert t.get('exit_price') is not None, \
                    f"Closed trade {t['broker_ticket_id']} missing exit_price"
                assert t.get('exit_date') is not None, \
                    f"Closed trade {t['broker_ticket_id']} missing exit_date"

    def test_no_duplicate_ticket_ids(self, real_mt4):
        trades, _ = parse(real_mt4)
        ids = [t['broker_ticket_id'] for t in trades]
        assert len(ids) == len(set(ids)), "Duplicate broker_ticket_ids in parsed output"


# ── Import pipeline ───────────────────────────────────────────────────────────

class TestMT4Import:

    def test_import_succeeds(self, conn, forex_account, real_mt4):
        result = run_import(conn, forex_account, real_mt4)
        assert result['success'] is True
        assert result['import_log_id'] is not None

    def test_import_creates_trades(self, imported_mt4):
        conn, aid = imported_mt4
        count = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE account_id=?", (aid,)).fetchone()[0]
        assert count > 0

    def test_trades_have_valid_status(self, imported_mt4):
        conn, aid = imported_mt4
        rows = conn.execute(
            "SELECT status FROM trades WHERE account_id=?", (aid,)).fetchall()
        for row in rows:
            assert row['status'] in ('open', 'closed')

    def test_closed_trades_have_pnl(self, imported_mt4):
        conn, aid = imported_mt4
        rows = conn.execute(
            "SELECT pnl_account_currency FROM trades WHERE account_id=? AND status='closed'",
            (aid,)).fetchall()
        assert len(rows) > 0
        for row in rows:
            assert row['pnl_account_currency'] is not None

    def test_import_log_created(self, conn, forex_account, real_mt4):
        result = run_import(conn, forex_account, real_mt4)
        logs = db.get_import_logs(conn, account_id=forex_account)
        assert len(logs) == 1
        assert logs[0]['plugin_name'] == 'mt4_detailed_statement'

    def test_import_log_counts_match(self, conn, forex_account, real_mt4):
        result = run_import(conn, forex_account, real_mt4)
        logs = db.get_import_logs(conn, account_id=forex_account)
        log = logs[0]
        assert log['trades_imported'] == result['trades_imported']
        assert log['trades_skipped'] == result['trades_skipped']


# ── Deduplication ─────────────────────────────────────────────────────────────

class TestMT4Dedup:

    def test_reimport_no_duplicate_trades(self, conn, forex_account, real_mt4):
        run_import(conn, forex_account, real_mt4)
        count1 = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE account_id=?", (forex_account,)).fetchone()[0]

        run_import(conn, forex_account, real_mt4)
        count2 = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE account_id=?", (forex_account,)).fetchone()[0]

        assert count1 == count2

    def test_reimport_skips_all(self, conn, forex_account, real_mt4):
        r1 = run_import(conn, forex_account, real_mt4)
        r2 = run_import(conn, forex_account, real_mt4)
        assert r2['trades_imported'] == 0
        assert r2['trades_skipped'] == r1['trades_imported']


# ── Exact counts (fill in after first run) ────────────────────────────────────
#
# Run:  pytest tests/test_integration_real_mt4.py -v --real-mt4=/path/to/statement.htm
# Then check the output and update the values below.
#
# class TestMT4ExactCounts:
#
#     def test_trade_count(self, imported_mt4):
#         conn, aid = imported_mt4
#         count = conn.execute(
#             "SELECT COUNT(*) FROM trades WHERE account_id=?", (aid,)).fetchone()[0]
#         assert count == TODO  # fill in after first run
#
#     def test_closed_count(self, imported_mt4):
#         conn, aid = imported_mt4
#         count = conn.execute(
#             "SELECT COUNT(*) FROM trades WHERE account_id=? AND status='closed'",
#             (aid,)).fetchone()[0]
#         assert count == TODO
#
#     def test_total_pnl(self, imported_mt4):
#         conn, aid = imported_mt4
#         row = conn.execute(
#             "SELECT SUM(pnl_account_currency) FROM trades WHERE account_id=? AND status='closed'",
#             (aid,)).fetchone()
#         assert abs(row[0] - TODO) < 0.01
