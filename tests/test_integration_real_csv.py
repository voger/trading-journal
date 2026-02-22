"""
Integration tests using the real Trading212 CSV export.
Skipped automatically if the real CSV file is not available.

These tests verify the EXACT numbers from the real import:
  - 127 executions (75 buys + 52 sells)
  - 52 instruments / positions
  - 51 closed, 1 open (VUAA)
  - Total broker P&L: €-21.99
  - 104 balance events
"""
import pytest

import database as db
from import_manager import run_import
from fifo_engine import (
    get_executions_for_trade,
    get_lot_consumptions_for_trade,
    get_open_lots_for_trade,
)


@pytest.fixture
def imported_db(conn, stock_account, real_csv):
    """Import the real CSV and return (conn, account_id)."""
    result = run_import(conn, stock_account, real_csv)
    assert result['success']
    return conn, stock_account


class TestRealImportCounts:

    def test_execution_count(self, imported_db):
        conn, aid = imported_db
        count = conn.execute(
            "SELECT COUNT(*) FROM executions WHERE account_id=?", (aid,)).fetchone()[0]
        assert count == 127

    def test_buy_sell_split(self, imported_db):
        conn, aid = imported_db
        buys = conn.execute(
            "SELECT COUNT(*) FROM executions WHERE account_id=? AND action='buy'",
            (aid,)).fetchone()[0]
        sells = conn.execute(
            "SELECT COUNT(*) FROM executions WHERE account_id=? AND action='sell'",
            (aid,)).fetchone()[0]
        assert buys == 75
        assert sells == 52

    def test_trade_count(self, imported_db):
        conn, aid = imported_db
        count = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE account_id=?", (aid,)).fetchone()[0]
        assert count == 52

    def test_open_closed_split(self, imported_db):
        conn, aid = imported_db
        open_count = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE account_id=? AND status='open'",
            (aid,)).fetchone()[0]
        closed_count = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE account_id=? AND status='closed'",
            (aid,)).fetchone()[0]
        assert open_count == 1
        assert closed_count == 51

    def test_balance_event_count(self, imported_db):
        conn, aid = imported_db
        count = conn.execute(
            "SELECT COUNT(*) FROM account_events WHERE account_id=?",
            (aid,)).fetchone()[0]
        assert count == 104


class TestRealPnL:

    def test_total_broker_pnl(self, imported_db):
        conn, aid = imported_db
        row = conn.execute(
            """SELECT SUM(pnl_account_currency) as total
               FROM trades WHERE account_id=? AND status='closed'""",
            (aid,)).fetchone()
        assert abs(row['total'] - (-21.99)) < 0.01

    def test_total_computed_pnl_matches_broker(self, imported_db):
        """Computed FIFO P&L should closely match broker reported P&L."""
        conn, aid = imported_db
        broker_total = conn.execute(
            "SELECT SUM(pnl_account_currency) FROM trades WHERE account_id=? AND status='closed'",
            (aid,)).fetchone()[0]
        computed_total = conn.execute(
            "SELECT SUM(pnl_computed) FROM lot_consumptions").fetchone()[0]
        # Allow small rounding difference
        assert abs(broker_total - computed_total) < 0.05


class TestRealVUAA:
    """VUAA: 11 DCA buys, no sells — the key use case for FIFO tracking."""

    def _get_vuaa_trade(self, conn, aid):
        return conn.execute(
            """SELECT t.* FROM trades t
               JOIN instruments i ON t.instrument_id = i.id
               WHERE i.symbol = 'VUAA' AND t.account_id = ?""",
            (aid,)).fetchone()

    def test_vuaa_open(self, imported_db):
        conn, aid = imported_db
        trade = self._get_vuaa_trade(conn, aid)
        assert trade['status'] == 'open'

    def test_vuaa_share_count(self, imported_db):
        conn, aid = imported_db
        trade = self._get_vuaa_trade(conn, aid)
        assert abs(trade['position_size'] - 53.643293) < 0.001

    def test_vuaa_eleven_executions(self, imported_db):
        conn, aid = imported_db
        trade = self._get_vuaa_trade(conn, aid)
        execs = get_executions_for_trade(conn, trade['id'])
        assert len(execs) == 11
        assert all(e['action'] == 'buy' for e in execs)

    def test_vuaa_eleven_open_lots(self, imported_db):
        conn, aid = imported_db
        trade = self._get_vuaa_trade(conn, aid)
        lots = get_open_lots_for_trade(conn, trade['id'])
        assert len(lots) == 11
        total_shares = sum(l['remaining_shares'] for l in lots)
        assert abs(total_shares - 53.643293) < 0.001

    def test_vuaa_no_lot_consumptions(self, imported_db):
        conn, aid = imported_db
        trade = self._get_vuaa_trade(conn, aid)
        lots = get_lot_consumptions_for_trade(conn, trade['id'])
        assert len(lots) == 0


class TestRealAKBA:
    """AKBA: 2 buys at different prices → 1 sell → FIFO lot matching."""

    def _get_akba_trade(self, conn, aid):
        return conn.execute(
            """SELECT t.* FROM trades t
               JOIN instruments i ON t.instrument_id = i.id
               WHERE i.symbol = 'AKBA' AND t.account_id = ?""",
            (aid,)).fetchone()

    def test_akba_closed(self, imported_db):
        conn, aid = imported_db
        trade = self._get_akba_trade(conn, aid)
        assert trade['status'] == 'closed'

    def test_akba_pnl(self, imported_db):
        conn, aid = imported_db
        trade = self._get_akba_trade(conn, aid)
        assert abs(trade['pnl_account_currency'] - (-3.38)) < 0.01

    def test_akba_two_fifo_lots(self, imported_db):
        conn, aid = imported_db
        trade = self._get_akba_trade(conn, aid)
        lots = get_lot_consumptions_for_trade(conn, trade['id'])
        assert len(lots) == 2
        # First lot (bought at $3.99) should lose money (sold at $3.71)
        assert lots[0]['pnl_computed'] < 0
        # Second lot (bought at $3.60) should make money
        assert lots[1]['pnl_computed'] > 0


class TestRealSGHC:
    """SGHC: multiple buys → 2 split sells at same time."""

    def _get_sghc_trade(self, conn, aid):
        return conn.execute(
            """SELECT t.* FROM trades t
               JOIN instruments i ON t.instrument_id = i.id
               WHERE i.symbol = 'SGHC' AND t.account_id = ?""",
            (aid,)).fetchone()

    def test_sghc_one_trade(self, imported_db):
        """BUG PREVENTION: should be ONE trade, not split into two."""
        conn, aid = imported_db
        trades = conn.execute(
            """SELECT t.* FROM trades t
               JOIN instruments i ON t.instrument_id = i.id
               WHERE i.symbol = 'SGHC' AND t.account_id = ?""",
            (aid,)).fetchall()
        assert len(trades) == 1

    def test_sghc_closed(self, imported_db):
        conn, aid = imported_db
        trade = self._get_sghc_trade(conn, aid)
        assert trade['status'] == 'closed'

    def test_sghc_pnl(self, imported_db):
        conn, aid = imported_db
        trade = self._get_sghc_trade(conn, aid)
        assert abs(trade['pnl_account_currency'] - 5.75) < 0.01

    def test_sghc_nine_executions(self, imported_db):
        conn, aid = imported_db
        trade = self._get_sghc_trade(conn, aid)
        execs = get_executions_for_trade(conn, trade['id'])
        assert len(execs) == 9  # 7 buys + 2 sells


class TestRealDedup:
    """Re-import should not create duplicates."""

    def test_reimport_no_duplicate_executions(self, conn, stock_account, real_csv):
        run_import(conn, stock_account, real_csv)
        count1 = conn.execute("SELECT COUNT(*) FROM executions").fetchone()[0]

        run_import(conn, stock_account, real_csv)
        count2 = conn.execute("SELECT COUNT(*) FROM executions").fetchone()[0]

        assert count1 == count2 == 127

    def test_reimport_no_duplicate_trades(self, conn, stock_account, real_csv):
        run_import(conn, stock_account, real_csv)
        count1 = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]

        run_import(conn, stock_account, real_csv)
        count2 = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]

        assert count1 == count2 == 52


class TestRealBalanceEvents:

    def test_deposit_total(self, imported_db):
        conn, aid = imported_db
        row = conn.execute(
            "SELECT SUM(amount) FROM account_events WHERE account_id=? AND event_type='deposit'",
            (aid,)).fetchone()
        assert abs(row[0] - 6428.0) < 0.01

    def test_dividend_total(self, imported_db):
        conn, aid = imported_db
        row = conn.execute(
            "SELECT SUM(amount) FROM account_events WHERE account_id=? AND event_type='dividend'",
            (aid,)).fetchone()
        assert abs(row[0] - 3.44) < 0.01

    def test_interest_count(self, imported_db):
        conn, aid = imported_db
        count = conn.execute(
            "SELECT COUNT(*) FROM account_events WHERE account_id=? AND event_type='interest'",
            (aid,)).fetchone()[0]
        assert count == 83
