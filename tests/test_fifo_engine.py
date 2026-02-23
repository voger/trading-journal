"""
Tests for fifo_engine.py — FIFO lot matching, P&L, edge cases.
"""
import pytest

import database as db
from fifo_engine import (
    run_fifo_matching,
    get_executions_for_trade,
    get_lot_consumptions_for_trade,
    get_open_lots_for_trade,
    execution_exists,
    audit_trade_integrity,
    audit_instrument_integrity,
)


# ── Helpers ──────────────────────────────────────────────────────────────

def _add_exec(conn, aid, iid, order_id, action, shares, price,
              xrate=1.0, commission=0.0, broker_result=None,
              dt='2025-01-01 10:00:00', currency='USD'):
    """Shorthand to insert an execution."""
    return db.create_execution(conn,
        account_id=aid, instrument_id=iid,
        broker_order_id=order_id, action=action,
        shares=shares, price=price, price_currency=currency,
        exchange_rate=xrate, total_account_currency=None,
        commission=commission, broker_result=broker_result,
        executed_at=dt)


def _fifo_one(conn, aid, iid):
    """Run FIFO matching and return the first trade_id (for single-trip tests)."""
    result = run_fifo_matching(conn, aid, iid)
    assert result, "Expected at least one trade from FIFO matching"
    return result[0]


# ── Test Classes ─────────────────────────────────────────────────────────

class TestFIFOBasicMatching:

    def test_single_buy_sell(self, conn, stock_account):
        """Simplest case: 1 buy → 1 sell → fully closed."""
        iid = db.get_or_create_instrument(conn, 'AAPL', 'Apple', 'stock')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100.0, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 110.0, dt='2025-02-01',
                  broker_result=90.91)

        tid = _fifo_one(conn, stock_account, iid)
        trade = db.get_trade(conn, tid)

        assert trade['status'] == 'closed'
        assert trade['position_size'] == 10
        assert trade['entry_price'] == 100.0
        assert trade['exit_price'] == 110.0
        assert trade['pnl_account_currency'] == 90.91

    def test_buy_only_stays_open(self, conn, stock_account):
        """Buy with no sell = open position."""
        iid = db.get_or_create_instrument(conn, 'AAPL', 'Apple', 'stock')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100.0)

        tid = _fifo_one(conn, stock_account, iid)
        trade = db.get_trade(conn, tid)

        assert trade['status'] == 'open'
        assert trade['exit_date'] is None
        assert trade['exit_price'] is None
        assert trade['pnl_account_currency'] is None

    def test_no_executions_returns_none(self, conn, stock_account):
        iid = db.get_or_create_instrument(conn, 'AAPL')
        result = run_fifo_matching(conn, stock_account, iid)
        assert result == []

    def test_sells_only_returns_none(self, conn, stock_account):
        """Sells without buys should return None (defensive)."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 100.0)
        result = run_fifo_matching(conn, stock_account, iid)
        assert result == []


class TestFIFOMultipleLots:

    def test_two_buys_one_sell_fifo_order(self, conn, stock_account):
        """
        BUG PREVENTION: FIFO must consume oldest lot first.
        Buy 10 @ $100, Buy 5 @ $120, Sell 12 → consumes all of lot1 + 2 from lot2.
        """
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100.0, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 120.0, dt='2025-02-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 12, 110.0, dt='2025-03-01',
                  broker_result=100.0)

        tid = _fifo_one(conn, stock_account, iid)
        lots = get_lot_consumptions_for_trade(conn, tid)

        assert len(lots) == 2
        # First lot: all 10 shares from Buy1 @ 100
        assert lots[0]['buy_price'] == 100.0
        assert lots[0]['shares_consumed'] == 10.0
        # Second lot: 2 shares from Buy2 @ 120
        assert lots[1]['buy_price'] == 120.0
        assert lots[1]['shares_consumed'] == 2.0

        # 3 shares remain open
        open_lots = get_open_lots_for_trade(conn, tid)
        assert len(open_lots) == 1
        assert abs(open_lots[0]['remaining_shares'] - 3.0) < 1e-6

    def test_dca_position_eleven_buys_no_sell(self, conn, stock_account):
        """VUAA pattern: multiple DCA buys, all open."""
        iid = db.get_or_create_instrument(conn, 'VUAA')
        prices = [100, 99, 101, 106, 105, 111, 110, 114, 113, 113, 113]
        for i, p in enumerate(prices):
            _add_exec(conn, stock_account, iid, f'B{i}', 'buy', 4.0, p,
                      xrate=1.0, dt=f'2025-{i+1:02d}-01')

        tid = _fifo_one(conn, stock_account, iid)
        trade = db.get_trade(conn, tid)

        assert trade['status'] == 'open'
        assert trade['position_size'] == 44.0  # 11 × 4
        lots = get_lot_consumptions_for_trade(conn, tid)
        assert len(lots) == 0
        open_lots = get_open_lots_for_trade(conn, tid)
        assert len(open_lots) == 11

    def test_split_sell_pattern(self, conn, stock_account):
        """
        BUG PREVENTION: SGHC pattern — one buy, two sells at same time.
        Should be ONE trade, not two.
        """
        iid = db.get_or_create_instrument(conn, 'SGHC')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 100, 10.0, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 99, 11.0, dt='2025-02-01',
                  broker_result=89.0)
        _add_exec(conn, stock_account, iid, 'S2', 'sell', 1, 11.0, dt='2025-02-01 00:00:14',
                  broker_result=0.91)

        tid = _fifo_one(conn, stock_account, iid)
        trade = db.get_trade(conn, tid)

        assert trade['status'] == 'closed'
        execs = get_executions_for_trade(conn, tid)
        assert len(execs) == 3  # 1 buy + 2 sells, all in one trade
        lots = get_lot_consumptions_for_trade(conn, tid)
        assert len(lots) == 2
        total_consumed = sum(l['shares_consumed'] for l in lots)
        assert abs(total_consumed - 100.0) < 1e-6

    def test_partial_sell_leaves_remainder_open(self, conn, stock_account):
        """MSFT pattern: buy 2, sell 1 → 1 open lot remains."""
        iid = db.get_or_create_instrument(conn, 'MSFT')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 2, 420.0, dt='2025-06-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 1, 440.0, dt='2025-07-01',
                  broker_result=17.43)

        tid = _fifo_one(conn, stock_account, iid)
        trade = db.get_trade(conn, tid)

        assert trade['status'] == 'open'
        open_lots = get_open_lots_for_trade(conn, tid)
        assert len(open_lots) == 1
        assert abs(open_lots[0]['remaining_shares'] - 1.0) < 1e-6
        assert open_lots[0]['price'] == 420.0  # same lot, partially consumed


class TestFIFOPnlComputation:

    def test_pnl_same_currency(self, conn, stock_account):
        """EUR→EUR: xrate=1.0, simple math."""
        iid = db.get_or_create_instrument(conn, 'VUAA')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100.0, xrate=1.0, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 120.0, xrate=1.0, dt='2025-02-01',
                  broker_result=200.0)

        tid = _fifo_one(conn, stock_account, iid)
        lots = get_lot_consumptions_for_trade(conn, tid)

        assert len(lots) == 1
        # P&L = 10 * (120/1 - 100/1) = 200
        assert abs(lots[0]['pnl_computed'] - 200.0) < 0.01

    def test_pnl_with_exchange_rate(self, conn, stock_account):
        """USD→EUR with exchange rates: P&L = proceeds_eur - cost_eur."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        # Buy 10 @ $100, xrate 1.10 → cost = 10 * 100 / 1.10 = 909.09 EUR
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100.0, xrate=1.10, dt='2025-01-01')
        # Sell 10 @ $120, xrate 1.05 → proceeds = 10 * 120 / 1.05 = 1142.86 EUR
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 120.0, xrate=1.05, dt='2025-02-01',
                  broker_result=233.77)

        tid = _fifo_one(conn, stock_account, iid)
        lots = get_lot_consumptions_for_trade(conn, tid)

        expected_pnl = (10 * 120.0 / 1.05) - (10 * 100.0 / 1.10)
        assert abs(lots[0]['pnl_computed'] - expected_pnl) < 0.01

    def test_pnl_losing_trade(self, conn, stock_account):
        """P&L should be negative when sell < buy."""
        iid = db.get_or_create_instrument(conn, 'AKBA')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 5.0, xrate=1.0, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 3.0, xrate=1.0, dt='2025-02-01',
                  broker_result=-20.0)

        tid = _fifo_one(conn, stock_account, iid)
        lots = get_lot_consumptions_for_trade(conn, tid)
        assert lots[0]['pnl_computed'] < 0
        assert abs(lots[0]['pnl_computed'] - (-20.0)) < 0.01

    def test_mixed_pnl_lots(self, conn, stock_account):
        """
        AKBA pattern: Buy @ $3.99, Buy @ $3.60, Sell all @ $3.71.
        First lot loses, second lot gains.
        """
        iid = db.get_or_create_instrument(conn, 'AKBA')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 11.4454, 3.99,
                  xrate=1.14, dt='2025-06-09')
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5.2463, 3.60,
                  xrate=1.16, dt='2025-06-16')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 16.6917, 3.71,
                  xrate=1.17, dt='2025-06-26', broker_result=-3.38)

        tid = _fifo_one(conn, stock_account, iid)
        lots = get_lot_consumptions_for_trade(conn, tid)

        assert len(lots) == 2
        assert lots[0]['pnl_computed'] < 0  # bought at 3.99, sold at 3.71
        assert lots[1]['pnl_computed'] > 0  # bought at 3.60, sold at 3.71

    def test_broker_pnl_stored_on_trade(self, conn, stock_account):
        """The official broker P&L should be stored on the trade record."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 110, dt='2025-02-01',
                  broker_result=42.50)

        tid = _fifo_one(conn, stock_account, iid)
        trade = db.get_trade(conn, tid)
        assert trade['pnl_account_currency'] == 42.50


class TestFIFOIdempotency:

    def test_rerun_produces_same_result(self, conn, stock_account):
        """Running FIFO twice should give identical results."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 110, dt='2025-02-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 12, 120, dt='2025-03-01',
                  broker_result=200.0)

        tid1 = _fifo_one(conn, stock_account, iid)
        lots1 = get_lot_consumptions_for_trade(conn, tid1)
        trade1_pnl = db.get_trade(conn, tid1)['pnl_account_currency']

        tid2 = _fifo_one(conn, stock_account, iid)
        lots2 = get_lot_consumptions_for_trade(conn, tid2)
        trade2_pnl = db.get_trade(conn, tid2)['pnl_account_currency']

        assert tid1 == tid2
        assert len(lots1) == len(lots2)
        assert trade1_pnl == trade2_pnl
        for l1, l2 in zip(lots1, lots2):
            assert l1['shares_consumed'] == l2['shares_consumed']
            assert l1['pnl_computed'] == l2['pnl_computed']

    def test_no_duplicate_lot_records(self, conn, stock_account):
        """Re-running FIFO should not duplicate lot_consumptions rows."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 110, dt='2025-02-01',
                  broker_result=100.0)

        run_fifo_matching(conn, stock_account, iid)
        count1 = conn.execute("SELECT COUNT(*) FROM lot_consumptions").fetchone()[0]

        run_fifo_matching(conn, stock_account, iid)
        count2 = conn.execute("SELECT COUNT(*) FROM lot_consumptions").fetchone()[0]

        assert count1 == count2 == 1


class TestFIFOFractionalShares:

    def test_fractional_shares_close_fully(self, conn, stock_account):
        """BUG PREVENTION: floating point residuals shouldn't leave position open."""
        iid = db.get_or_create_instrument(conn, 'VUAA')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 4.171218, 100.69, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 4.171218, 110.0, dt='2025-02-01',
                  broker_result=38.82)

        tid = _fifo_one(conn, stock_account, iid)
        trade = db.get_trade(conn, tid)

        assert trade['status'] == 'closed'
        open_lots = get_open_lots_for_trade(conn, tid)
        assert len(open_lots) == 0

    def test_tiny_fractional_remainder(self, conn, stock_account):
        """Even very small remainders (< 1e-10) should count as closed."""
        iid = db.get_or_create_instrument(conn, 'TEST')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 1.0 / 3.0, 100.0, dt='2025-01-01')
        # Sell the exact same amount — but floating point division may cause residual
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 1.0 / 3.0, 110.0, dt='2025-02-01',
                  broker_result=3.33)

        tid = _fifo_one(conn, stock_account, iid)
        trade = db.get_trade(conn, tid)
        assert trade['status'] == 'closed'


class TestFIFOTradeCreation:

    def test_creates_one_trade_per_instrument(self, conn, stock_account):
        """All executions for same instrument → one trade."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        for i in range(5):
            _add_exec(conn, stock_account, iid, f'B{i}', 'buy', 2, 100 + i,
                      dt=f'2025-0{i+1}-01')
        run_fifo_matching(conn, stock_account, iid)

        trades = conn.execute(
            "SELECT * FROM trades WHERE account_id=? AND instrument_id=?",
            (stock_account, iid)).fetchall()
        assert len(trades) == 1

    def test_different_instruments_separate_trades(self, conn, stock_account):
        """Different instruments → separate trades."""
        iid1 = db.get_or_create_instrument(conn, 'AAPL')
        iid2 = db.get_or_create_instrument(conn, 'MSFT')
        _add_exec(conn, stock_account, iid1, 'B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid2, 'B2', 'buy', 5, 200, dt='2025-01-01')
        run_fifo_matching(conn, stock_account, iid1)
        run_fifo_matching(conn, stock_account, iid2)

        trades = conn.execute(
            "SELECT * FROM trades WHERE account_id=?", (stock_account,)).fetchall()
        assert len(trades) == 2

    def test_round_trip_creates_separate_trades(self, conn, stock_account):
        """BUG FIX: buy→sell-all→buy-again → 2 distinct trades, not 1."""
        iid = db.get_or_create_instrument(conn, 'MSFT')

        # Round trip 1: buy 10, sell 10
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 110, dt='2025-02-01',
                  broker_result=10.0)

        # Round trip 2: buy 5, sell 5
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 120, dt='2025-03-01')
        _add_exec(conn, stock_account, iid, 'S2', 'sell', 5, 130, dt='2025-04-01',
                  broker_result=5.0)

        trade_ids = run_fifo_matching(conn, stock_account, iid)
        assert len(trade_ids) == 2

        t1 = db.get_trade(conn, trade_ids[0])
        t2 = db.get_trade(conn, trade_ids[1])

        assert t1['status'] == 'closed'
        assert t2['status'] == 'closed'
        assert t1['entry_price'] == 100.0
        assert t2['entry_price'] == 120.0
        assert t1['exit_price'] == 110.0
        assert t2['exit_price'] == 130.0
        assert t1['pnl_account_currency'] == 10.0
        assert t2['pnl_account_currency'] == 5.0

    def test_round_trip_last_open(self, conn, stock_account):
        """buy→sell-all→buy-again (no sell) → 2 trades: closed + open."""
        iid = db.get_or_create_instrument(conn, 'MSFT')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 110, dt='2025-02-01',
                  broker_result=10.0)
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 120, dt='2025-03-01')

        trade_ids = run_fifo_matching(conn, stock_account, iid)
        assert len(trade_ids) == 2

        t1 = db.get_trade(conn, trade_ids[0])
        t2 = db.get_trade(conn, trade_ids[1])
        assert t1['status'] == 'closed'
        assert t2['status'] == 'open'
        assert t2['position_size'] == 5

    def test_round_trip_three_cycles(self, conn, stock_account):
        """Three complete round trips → 3 trades."""
        iid = db.get_or_create_instrument(conn, 'TSLA')
        for i in range(3):
            m = i * 2 + 1
            _add_exec(conn, stock_account, iid, f'B{i}', 'buy', 10, 100 + i * 10,
                      dt=f'2025-{m:02d}-01')
            _add_exec(conn, stock_account, iid, f'S{i}', 'sell', 10, 110 + i * 10,
                      dt=f'2025-{m+1:02d}-01', broker_result=10.0)

        trade_ids = run_fifo_matching(conn, stock_account, iid)
        assert len(trade_ids) == 3
        for tid in trade_ids:
            assert db.get_trade(conn, tid)['status'] == 'closed'

    def test_round_trip_idempotent(self, conn, stock_account):
        """Re-running FIFO on round trips produces same results."""
        iid = db.get_or_create_instrument(conn, 'MSFT')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 110, dt='2025-02-01',
                  broker_result=10.0)
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 120, dt='2025-03-01')

        ids1 = run_fifo_matching(conn, stock_account, iid)
        ids2 = run_fifo_matching(conn, stock_account, iid)
        assert len(ids1) == len(ids2) == 2
        # Trade IDs should be the same after re-run
        assert ids1[0] == ids2[0]
        assert ids1[1] == ids2[1]

    def test_single_trip_no_sell_still_one_trade(self, conn, stock_account):
        """Multiple buys of same instrument with no sell = 1 open trade."""
        iid = db.get_or_create_instrument(conn, 'NVDA')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 5, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 3, 110, dt='2025-02-01')
        _add_exec(conn, stock_account, iid, 'B3', 'buy', 2, 120, dt='2025-03-01')

        trade_ids = run_fifo_matching(conn, stock_account, iid)
        assert len(trade_ids) == 1
        assert db.get_trade(conn, trade_ids[0])['status'] == 'open'

    def test_weighted_average_entry_price(self, conn, stock_account):
        """Entry price = weighted average of all buy executions."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100.0, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 120.0, dt='2025-02-01')

        tid = _fifo_one(conn, stock_account, iid)
        trade = db.get_trade(conn, tid)

        expected = (10 * 100 + 5 * 120) / 15  # 106.67
        assert abs(trade['entry_price'] - expected) < 0.01

    def test_commission_aggregated(self, conn, stock_account):
        """Commission totals all buy + sell commissions."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, commission=0.50, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 110, commission=0.75,
                  dt='2025-02-01', broker_result=95.0)

        tid = _fifo_one(conn, stock_account, iid)
        trade = db.get_trade(conn, tid)
        assert abs(trade['commission'] - 1.25) < 0.01

    def test_all_executions_linked_to_trade(self, conn, stock_account):
        """Every execution should have trade_id set after FIFO run."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 110, dt='2025-02-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 15, 120, dt='2025-03-01',
                  broker_result=250)

        tid = _fifo_one(conn, stock_account, iid)
        execs = get_executions_for_trade(conn, tid)
        assert len(execs) == 3
        for e in execs:
            assert e['trade_id'] == tid


class TestFIFOHelperFunctions:

    def test_execution_exists(self, conn, stock_account):
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'ORDER_123', 'buy', 10, 100)
        assert execution_exists(conn, stock_account, 'ORDER_123')
        assert not execution_exists(conn, stock_account, 'NONEXISTENT')

    def test_get_open_lots_correct_remainder(self, conn, stock_account):
        """Open lots should show correct remaining after partial consumption."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 10, 110, dt='2025-02-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 15, 120, dt='2025-03-01',
                  broker_result=250)

        tid = _fifo_one(conn, stock_account, iid)
        open_lots = get_open_lots_for_trade(conn, tid)

        assert len(open_lots) == 1
        assert abs(open_lots[0]['remaining_shares'] - 5.0) < 1e-6
        assert open_lots[0]['price'] == 110.0  # from the second buy

    def test_get_lot_consumptions_empty_for_open(self, conn, stock_account):
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100)
        tid = _fifo_one(conn, stock_account, iid)
        lots = get_lot_consumptions_for_trade(conn, tid)
        assert len(lots) == 0


# ── FIFO Edge Cases (extended coverage) ─────────────────────────────────

class TestFIFOEdgeCases:

    def test_sells_only_no_buys(self, conn, stock_account):
        """Sell-only executions should produce no trades."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 100, dt='2025-01-01')
        result = run_fifo_matching(conn, stock_account, iid)
        assert result == []

    def test_empty_instrument(self, conn, stock_account):
        """No executions at all should return empty list."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        result = run_fifo_matching(conn, stock_account, iid)
        assert result == []

    def test_lot_ordering_fifo_not_lifo(self, conn, stock_account):
        """Verify FIFO order: oldest lot consumed first, not newest."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 5, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 200, dt='2025-02-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 5, 150, dt='2025-03-01',
                  broker_result=250)

        tid = _fifo_one(conn, stock_account, iid)
        lots = get_lot_consumptions_for_trade(conn, tid)
        assert len(lots) == 1
        # FIFO: the $100 lot should be consumed first, not the $200 lot
        assert lots[0]['buy_price'] == 100.0
        assert lots[0]['sell_price'] == 150.0
        assert lots[0]['shares_consumed'] == 5.0

    def test_lot_ordering_sell_spans_two_lots(self, conn, stock_account):
        """A single sell that spans two buy lots in FIFO order."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 3, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 7, 200, dt='2025-02-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 5, 150, dt='2025-03-01',
                  broker_result=100)

        tid = _fifo_one(conn, stock_account, iid)
        lots = get_lot_consumptions_for_trade(conn, tid)
        # Should have 2 lot consumption records
        assert len(lots) == 2
        # First: 3 shares from lot B1 @ $100
        assert lots[0]['buy_price'] == 100.0
        assert lots[0]['shares_consumed'] == 3.0
        # Second: 2 shares from lot B2 @ $200
        assert lots[1]['buy_price'] == 200.0
        assert lots[1]['shares_consumed'] == 2.0

    def test_dca_round_trip_multiple_buys_full_sell(self, conn, stock_account):
        """DCA: 4 buys → 1 sell of all → creates 1 closed trade."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 5, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 105, dt='2025-02-01')
        _add_exec(conn, stock_account, iid, 'B3', 'buy', 5, 95, dt='2025-03-01')
        _add_exec(conn, stock_account, iid, 'B4', 'buy', 5, 110, dt='2025-04-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 20, 120, dt='2025-05-01',
                  broker_result=300)

        result = run_fifo_matching(conn, stock_account, iid)
        assert len(result) == 1
        trade = db.get_trade(conn, result[0])
        assert trade['status'] == 'closed'
        assert trade['position_size'] == 20

    def test_dca_then_round_trip(self, conn, stock_account):
        """DCA builds position, sells all, buys again → 2 distinct trades."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        # Trip 1: DCA
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 5, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 105, dt='2025-02-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 120, dt='2025-03-01',
                  broker_result=175)
        # Trip 2: new entry
        _add_exec(conn, stock_account, iid, 'B3', 'buy', 3, 115, dt='2025-04-01')
        _add_exec(conn, stock_account, iid, 'B4', 'buy', 7, 118, dt='2025-05-01')

        result = run_fifo_matching(conn, stock_account, iid)
        assert len(result) == 2
        # Trip 1 closed
        t1 = db.get_trade(conn, result[0])
        assert t1['status'] == 'closed'
        assert t1['position_size'] == 10
        # Trip 2 open
        t2 = db.get_trade(conn, result[1])
        assert t2['status'] == 'open'
        assert t2['position_size'] == 10

    def test_multi_instrument_round_trips(self, conn, stock_account):
        """Two instruments each with their own round trips, processed independently."""
        aapl = db.get_or_create_instrument(conn, 'AAPL')
        msft = db.get_or_create_instrument(conn, 'MSFT')

        # AAPL: 1 round trip
        _add_exec(conn, stock_account, aapl, 'AB1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, aapl, 'AS1', 'sell', 10, 110, dt='2025-02-01',
                  broker_result=100)

        # MSFT: 2 round trips
        _add_exec(conn, stock_account, msft, 'MB1', 'buy', 5, 400, dt='2025-01-01')
        _add_exec(conn, stock_account, msft, 'MS1', 'sell', 5, 420, dt='2025-02-01',
                  broker_result=100)
        _add_exec(conn, stock_account, msft, 'MB2', 'buy', 3, 410, dt='2025-03-01')
        _add_exec(conn, stock_account, msft, 'MS2', 'sell', 3, 430, dt='2025-04-01',
                  broker_result=60)

        aapl_ids = run_fifo_matching(conn, stock_account, aapl)
        msft_ids = run_fifo_matching(conn, stock_account, msft)

        assert len(aapl_ids) == 1
        assert len(msft_ids) == 2

        # No cross-contamination
        aapl_trade = db.get_trade(conn, aapl_ids[0])
        assert aapl_trade['instrument_id'] == aapl
        for mid in msft_ids:
            assert db.get_trade(conn, mid)['instrument_id'] == msft

    def test_orphan_cleanup_on_rerun(self, conn, stock_account):
        """Re-running FIFO after removing executions should clean up orphaned trades."""
        iid = db.get_or_create_instrument(conn, 'AAPL')

        # Create 2 round trips
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 110, dt='2025-02-01',
                  broker_result=100)
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 115, dt='2025-03-01')
        _add_exec(conn, stock_account, iid, 'S2', 'sell', 5, 120, dt='2025-04-01',
                  broker_result=25)

        ids = run_fifo_matching(conn, stock_account, iid)
        assert len(ids) == 2
        old_id_2 = ids[1]

        # Remove the second round trip's executions (must clear lot_consumptions FK first)
        exec_ids = [r['id'] for r in conn.execute(
            "SELECT id FROM executions WHERE broker_order_id IN ('B2', 'S2')"
        ).fetchall()]
        for eid in exec_ids:
            conn.execute(
                "DELETE FROM lot_consumptions WHERE buy_execution_id = ? OR sell_execution_id = ?",
                (eid, eid))
        conn.execute("DELETE FROM executions WHERE broker_order_id IN ('B2', 'S2')")
        conn.commit()

        # Re-run FIFO
        ids2 = run_fifo_matching(conn, stock_account, iid)
        assert len(ids2) == 1

        # The orphaned trade should be deleted
        orphan = conn.execute("SELECT id FROM trades WHERE id = ?",
                              (old_id_2,)).fetchone()
        assert orphan is None, "Orphaned trade should have been deleted"

    def test_idempotent_pnl_stability(self, conn, stock_account):
        """Running FIFO 3 times should produce identical P&L each time."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01',
                  commission=5.0)
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 110, dt='2025-02-01',
                  commission=3.0)
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 15, 120, dt='2025-03-01',
                  broker_result=250, commission=7.0)

        pnls = []
        for _ in range(3):
            ids = run_fifo_matching(conn, stock_account, iid)
            trade = db.get_trade(conn, ids[0])
            pnls.append(trade['pnl_account_currency'])

        assert pnls[0] == pnls[1] == pnls[2], f"P&L not stable across runs: {pnls}"

    def test_round_trip_with_multiple_partial_sells(self, conn, stock_account):
        """Buy 10, sell 3, sell 4, sell 3 → one closed trade, lots consumed in order."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 3, 110, dt='2025-02-01',
                  broker_result=30)
        _add_exec(conn, stock_account, iid, 'S2', 'sell', 4, 115, dt='2025-03-01',
                  broker_result=60)
        _add_exec(conn, stock_account, iid, 'S3', 'sell', 3, 120, dt='2025-04-01',
                  broker_result=60)

        ids = run_fifo_matching(conn, stock_account, iid)
        assert len(ids) == 1
        trade = db.get_trade(conn, ids[0])
        assert trade['status'] == 'closed'

        # 3 lot consumption records (one per sell from the same buy lot)
        lots = get_lot_consumptions_for_trade(conn, ids[0])
        assert len(lots) == 3
        total_consumed = sum(l['shares_consumed'] for l in lots)
        assert abs(total_consumed - 10.0) < 1e-6

    def test_commission_tracked_across_round_trips(self, conn, stock_account):
        """Each round trip should only count commissions from its own executions."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        # Trip 1
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01',
                  commission=5.0)
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 110, dt='2025-02-01',
                  broker_result=100, commission=5.0)
        # Trip 2
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 115, dt='2025-03-01',
                  commission=3.0)
        _add_exec(conn, stock_account, iid, 'S2', 'sell', 5, 120, dt='2025-04-01',
                  broker_result=25, commission=3.0)

        ids = run_fifo_matching(conn, stock_account, iid)
        assert len(ids) == 2

        t1 = db.get_trade(conn, ids[0])
        t2 = db.get_trade(conn, ids[1])
        assert t1['commission'] == 10.0  # 5 buy + 5 sell
        assert t2['commission'] == 6.0   # 3 buy + 3 sell


# ── FIFO Deep Edge Cases ────────────────────────────────────────────────

class TestFIFODeepEdgeCases:
    """Advanced edge cases: exchange rates, migration, lot ordering, etc."""

    def test_mixed_exchange_rates_lot_pnl(self, conn, stock_account):
        """Buy at xrate 1.10, sell at xrate 1.05 — verify lot P&L computation.

        Buy 10 @ $100, xrate 1.10 → cost = 10*100/1.10 = 909.09 EUR
        Sell 10 @ $120, xrate 1.05 → proceeds = 10*120/1.05 = 1142.86 EUR
        Expected lot P&L = 1142.86 - 909.09 = 233.77 EUR (approx)
        """
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100.0,
                  xrate=1.10, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 120.0,
                  xrate=1.05, dt='2025-02-01', broker_result=233.77)

        tid = _fifo_one(conn, stock_account, iid)
        lots = get_lot_consumptions_for_trade(conn, tid)
        assert len(lots) == 1
        assert lots[0]['buy_exchange_rate'] == 1.10
        assert lots[0]['sell_exchange_rate'] == 1.05
        # Computed P&L: (10*120/1.05) - (10*100/1.10) ≈ 233.77
        assert abs(lots[0]['pnl_computed'] - 233.77) < 0.1

    def test_mixed_xrates_across_multiple_lots(self, conn, stock_account):
        """Two buys at different exchange rates, one sell."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 5, 100.0,
                  xrate=1.10, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 100.0,
                  xrate=1.20, dt='2025-02-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 110.0,
                  xrate=1.15, dt='2025-03-01', broker_result=100)

        tid = _fifo_one(conn, stock_account, iid)
        lots = get_lot_consumptions_for_trade(conn, tid)
        assert len(lots) == 2
        # Lot 1: buy xrate 1.10, Lot 2: buy xrate 1.20
        assert lots[0]['buy_exchange_rate'] == 1.10
        assert lots[1]['buy_exchange_rate'] == 1.20
        # Both sell at xrate 1.15
        assert lots[0]['sell_exchange_rate'] == 1.15
        assert lots[1]['sell_exchange_rate'] == 1.15
        # Lot 1 P&L: (5*110/1.15) - (5*100/1.10) ≈ 478.26 - 454.55 = 23.71
        # Lot 2 P&L: (5*110/1.15) - (5*100/1.20) ≈ 478.26 - 416.67 = 61.59
        assert abs(lots[0]['pnl_computed'] - 23.71) < 0.1
        assert abs(lots[1]['pnl_computed'] - 61.59) < 0.1

    def test_sell_with_no_broker_result(self, conn, stock_account):
        """If broker_result is None, official P&L should be None on trade."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 110, dt='2025-02-01',
                  broker_result=None)

        tid = _fifo_one(conn, stock_account, iid)
        trade = db.get_trade(conn, tid)
        assert trade['status'] == 'closed'
        # With no broker_result, pnl_official = total_broker_pnl = 0.0
        # (broker_result None is skipped in accumulation, so total stays 0)
        assert trade['pnl_account_currency'] == 0.0

    def test_sell_with_partial_broker_results(self, conn, stock_account):
        """Two sells: first has broker_result, second is None."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 5, 110, dt='2025-02-01',
                  broker_result=50)
        _add_exec(conn, stock_account, iid, 'S2', 'sell', 5, 120, dt='2025-03-01',
                  broker_result=None)

        tid = _fifo_one(conn, stock_account, iid)
        trade = db.get_trade(conn, tid)
        # Only first sell's broker_result counts
        assert trade['pnl_account_currency'] == 50.0

    def test_split_sell_across_three_lots(self, conn, stock_account):
        """One sell that spans across 3 buy lots."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 3, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 4, 110, dt='2025-02-01')
        _add_exec(conn, stock_account, iid, 'B3', 'buy', 3, 120, dt='2025-03-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 130, dt='2025-04-01',
                  broker_result=200)

        tid = _fifo_one(conn, stock_account, iid)
        lots = get_lot_consumptions_for_trade(conn, tid)
        assert len(lots) == 3
        # FIFO order: 3@100, 4@110, 3@120
        assert lots[0]['shares_consumed'] == 3.0
        assert lots[0]['buy_price'] == 100.0
        assert lots[1]['shares_consumed'] == 4.0
        assert lots[1]['buy_price'] == 110.0
        assert lots[2]['shares_consumed'] == 3.0
        assert lots[2]['buy_price'] == 120.0
        total_consumed = sum(l['shares_consumed'] for l in lots)
        assert abs(total_consumed - 10.0) < 1e-6

    def test_five_sequential_round_trips(self, conn, stock_account):
        """Five complete buy→sell round trips should produce 5 trades."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        for i in range(5):
            month = f"{i*2+1:02d}"
            _add_exec(conn, stock_account, iid, f'B{i}', 'buy', 10, 100+i*5,
                      dt=f'2025-{month}-01 10:00:00')
            _add_exec(conn, stock_account, iid, f'S{i}', 'sell', 10, 110+i*5,
                      dt=f'2025-{month}-15 10:00:00', broker_result=100)

        ids = run_fifo_matching(conn, stock_account, iid)
        assert len(ids) == 5
        for tid in ids:
            t = db.get_trade(conn, tid)
            assert t['status'] == 'closed'
            assert t['pnl_account_currency'] == 100.0

    def test_get_open_lots_fully_closed_is_empty(self, conn, stock_account):
        """Fully closed position should have no open lots."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 110, dt='2025-02-01',
                  broker_result=100)

        tid = _fifo_one(conn, stock_account, iid)
        open_lots = get_open_lots_for_trade(conn, tid)
        assert open_lots == []

    def test_lot_consumptions_ordered_by_sell_then_buy(self, conn, stock_account):
        """Lot consumptions should be ordered by sell date, then buy date."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 5, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 110, dt='2025-02-01')
        # First sell consumes all of B1 + part of B2
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 7, 120, dt='2025-03-01',
                  broker_result=100)
        # Second sell consumes rest of B2
        _add_exec(conn, stock_account, iid, 'S2', 'sell', 3, 125, dt='2025-04-01',
                  broker_result=45)

        tid = _fifo_one(conn, stock_account, iid)
        lots = get_lot_consumptions_for_trade(conn, tid)
        assert len(lots) == 3
        # S1 produces 2 records: B1(5@100) + B2(2@110)
        # S2 produces 1 record: B2(3@110)
        assert lots[0]['sell_price'] == 120.0  # from S1
        assert lots[0]['buy_price'] == 100.0   # from B1
        assert lots[1]['sell_price'] == 120.0  # from S1
        assert lots[1]['buy_price'] == 110.0   # from B2
        assert lots[2]['sell_price'] == 125.0  # from S2
        assert lots[2]['buy_price'] == 110.0   # from B2

    def test_execution_exists_account_isolation(self, conn, stock_account):
        """execution_exists should be scoped to account."""
        other_aid = db.create_account(conn, name='Other', broker='X',
                                       currency='EUR', asset_type='stocks')
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'ORDER_X', 'buy', 10, 100)

        assert execution_exists(conn, stock_account, 'ORDER_X')
        assert not execution_exists(conn, other_aid, 'ORDER_X')

    def test_weighted_avg_exit_price_multiple_sells(self, conn, stock_account):
        """Exit price should be weighted avg of all sell executions."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        # Sell 4 @ 110, then 6 @ 120
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 4, 110.0, dt='2025-02-01',
                  broker_result=40)
        _add_exec(conn, stock_account, iid, 'S2', 'sell', 6, 120.0, dt='2025-03-01',
                  broker_result=120)

        tid = _fifo_one(conn, stock_account, iid)
        trade = db.get_trade(conn, tid)
        # Weighted avg: (4*110 + 6*120) / 10 = (440+720)/10 = 116.0
        assert abs(trade['exit_price'] - 116.0) < 0.01

    def test_rerun_after_adding_executions_to_open(self, conn, stock_account):
        """Adding new buys to an open position and re-running updates the trade."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')

        ids1 = run_fifo_matching(conn, stock_account, iid)
        t1 = db.get_trade(conn, ids1[0])
        assert t1['position_size'] == 10
        assert t1['status'] == 'open'

        # Add more buys
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 110, dt='2025-02-01')
        ids2 = run_fifo_matching(conn, stock_account, iid)
        assert len(ids2) == 1
        assert ids2[0] == ids1[0]  # Same trade
        t2 = db.get_trade(conn, ids2[0])
        assert t2['position_size'] == 15
        assert t2['status'] == 'open'

        # Now close it
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 15, 120, dt='2025-03-01',
                  broker_result=250)
        ids3 = run_fifo_matching(conn, stock_account, iid)
        assert len(ids3) == 1
        assert ids3[0] == ids1[0]  # Still same trade
        t3 = db.get_trade(conn, ids3[0])
        assert t3['status'] == 'closed'
        assert t3['pnl_account_currency'] == 250.0

    def test_old_style_ticket_migration(self, conn, stock_account):
        """Trades with old-style tickets (no _0 suffix) should be adopted."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        # Manually insert an old-style trade
        old_ticket = f"EXEC_FIFO_{stock_account}_{iid}"
        conn.execute(
            """INSERT INTO trades
               (account_id, instrument_id, direction, entry_date, entry_price,
                position_size, status, broker_ticket_id)
               VALUES (?, ?, 'long', '2025-01-01', 100, 10, 'open', ?)""",
            (stock_account, iid, old_ticket))
        conn.commit()
        old_trade_id = conn.execute(
            "SELECT id FROM trades WHERE broker_ticket_id = ?",
            (old_ticket,)).fetchone()['id']

        # Now add executions and run FIFO
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        ids = run_fifo_matching(conn, stock_account, iid)
        assert len(ids) == 1
        # Should have adopted the old trade
        assert ids[0] == old_trade_id
        # Ticket should have been renamed
        new_ticket = conn.execute(
            "SELECT broker_ticket_id FROM trades WHERE id = ?",
            (old_trade_id,)).fetchone()['broker_ticket_id']
        assert new_ticket == f"EXEC_FIFO_{stock_account}_{iid}_0"

    def test_tiny_fractional_fully_consumed(self, conn, stock_account):
        """Shares like 0.000001 should fully close when sold."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 0.123456, 100,
                  dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 0.123456, 110,
                  dt='2025-02-01', broker_result=1.23)

        tid = _fifo_one(conn, stock_account, iid)
        trade = db.get_trade(conn, tid)
        assert trade['status'] == 'closed'
        lots = get_lot_consumptions_for_trade(conn, tid)
        assert len(lots) == 1
        assert abs(lots[0]['shares_consumed'] - 0.123456) < 1e-8

    def test_broker_pnl_accumulation_across_sells(self, conn, stock_account):
        """Total broker P&L should be sum of all sell broker_results."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 20, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 5, 110, dt='2025-02-01',
                  broker_result=50)
        _add_exec(conn, stock_account, iid, 'S2', 'sell', 5, 115, dt='2025-03-01',
                  broker_result=75)
        _add_exec(conn, stock_account, iid, 'S3', 'sell', 5, 120, dt='2025-04-01',
                  broker_result=100)
        _add_exec(conn, stock_account, iid, 'S4', 'sell', 5, 125, dt='2025-05-01',
                  broker_result=125)

        tid = _fifo_one(conn, stock_account, iid)
        trade = db.get_trade(conn, tid)
        assert trade['pnl_account_currency'] == 50 + 75 + 100 + 125

    def test_no_buys_in_trip_skipped(self, conn, stock_account):
        """A trip with only sells (edge case) should be skipped gracefully."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        # This is artificial: a sell-only sequence shouldn't happen, but
        # the engine should handle it without crashing
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 100, dt='2025-01-01')
        result = run_fifo_matching(conn, stock_account, iid)
        assert result == []


# ── End-to-End Integration: Import → FIFO → Stats → Export ──────────────

class TestEndToEndIntegration:
    """Full pipeline tests using the sample T212 CSV."""

    def _import(self, conn, stock_account, sample_t212_csv):
        from import_manager import run_import
        return run_import(conn, stock_account, sample_t212_csv, 'trading212_csv')

    def test_import_produces_correct_trade_count(self, conn, stock_account,
                                                  sample_t212_csv):
        """Sample CSV should produce expected number of trades."""
        result = self._import(conn, stock_account, sample_t212_csv)
        # AAPL: buy+buy+sell = 1 closed trade
        # VUAA: buy+buy (no sell) = 1 open trade
        # MSFT: buy+partial_sell = 1 open trade
        # TEST: buy+split_sell = 1 closed trade
        trades = db.get_trades(conn, account_id=stock_account)
        # Filter out deposit/withdrawal events
        real_trades = [t for t in trades if t['direction'] in ('long', 'short')]
        assert len(real_trades) == 4

    def test_import_then_stats_consistent(self, conn, stock_account,
                                           sample_t212_csv):
        """get_trade_stats after import should match manual count."""
        self._import(conn, stock_account, sample_t212_csv)
        stats = db.get_trade_stats(conn, account_id=stock_account)
        assert stats is not None
        # Only closed trades count: AAPL (closed) + TEST (closed) = 2
        assert stats['total_trades'] == 2

    def test_import_then_breakdown_by_instrument(self, conn, stock_account,
                                                   sample_t212_csv):
        """Breakdown by instrument should show each traded symbol."""
        self._import(conn, stock_account, sample_t212_csv)
        bds = db.get_trade_breakdowns(conn, stock_account, 'instrument')
        symbols = {bd['group_name'] for bd in bds}
        # Only closed trades in breakdowns: AAPL and TEST
        assert 'AAPL' in symbols
        assert 'TEST' in symbols

    def test_import_then_export_row_count(self, conn, stock_account,
                                           sample_t212_csv):
        """Export should contain all trades (open + closed)."""
        self._import(conn, stock_account, sample_t212_csv)
        rows = db.get_trades_for_export(conn, stock_account)
        trades = db.get_trades(conn, account_id=stock_account)
        real_trades = [t for t in trades if t['direction'] in ('long', 'short')]
        assert len(rows) == len(real_trades)

    def test_import_then_export_closed_only(self, conn, stock_account,
                                             sample_t212_csv):
        """Export with closed filter should only have closed trades."""
        self._import(conn, stock_account, sample_t212_csv)
        rows = db.get_trades_for_export(conn, stock_account, status_filter='closed')
        for r in rows:
            assert r['status'] == 'closed'
        assert len(rows) == 2  # AAPL + TEST

    def test_import_aapl_round_trip_pnl(self, conn, stock_account,
                                         sample_t212_csv):
        """AAPL closed trade should have correct P&L from broker results."""
        self._import(conn, stock_account, sample_t212_csv)
        trades = db.get_trades(conn, account_id=stock_account, status='closed')
        aapl_iid = db.get_or_create_instrument(conn, 'AAPL')
        aapl_trades = [t for t in trades if t['instrument_id'] == aapl_iid]
        assert len(aapl_trades) == 1
        assert aapl_trades[0]['pnl_account_currency'] == 250.0

    def test_import_fifo_lots_for_aapl(self, conn, stock_account,
                                        sample_t212_csv):
        """AAPL has 2 buys + 1 sell → should have 2 lot consumption records."""
        self._import(conn, stock_account, sample_t212_csv)
        aapl_iid = db.get_or_create_instrument(conn, 'AAPL')
        aapl_trades = [t for t in db.get_trades(conn, account_id=stock_account)
                       if t['instrument_id'] == aapl_iid and t['status'] == 'closed']
        assert len(aapl_trades) == 1
        lots = get_lot_consumptions_for_trade(conn, aapl_trades[0]['id'])
        assert len(lots) == 2
        # FIFO: first lot is the 10@180 buy, second is 5@190 buy
        assert lots[0]['buy_price'] == 180.0
        assert lots[0]['shares_consumed'] == 10.0
        assert lots[1]['buy_price'] == 190.0
        assert lots[1]['shares_consumed'] == 5.0

    def test_import_split_sell_produces_one_trade(self, conn, stock_account,
                                                    sample_t212_csv):
        """TEST split-sell pattern (sell 99 + sell 1) should be ONE trade."""
        self._import(conn, stock_account, sample_t212_csv)
        test_iid = db.get_or_create_instrument(conn, 'TEST')
        test_trades = [t for t in db.get_trades(conn, account_id=stock_account)
                       if t['instrument_id'] == test_iid]
        assert len(test_trades) == 1
        assert test_trades[0]['status'] == 'closed'

    def test_import_events_created(self, conn, stock_account, sample_t212_csv):
        """Deposits and interest should appear as account events."""
        self._import(conn, stock_account, sample_t212_csv)
        events = db.get_account_events(conn, stock_account)
        event_types = [e['event_type'] for e in events]
        assert 'deposit' in event_types
        assert 'interest' in event_types

    def test_reimport_idempotent(self, conn, stock_account, sample_t212_csv):
        """Importing the same file twice should not duplicate anything."""
        r1 = self._import(conn, stock_account, sample_t212_csv)
        trades_after_1 = len(db.get_trades(conn, account_id=stock_account))
        r2 = self._import(conn, stock_account, sample_t212_csv)
        trades_after_2 = len(db.get_trades(conn, account_id=stock_account))
        assert trades_after_2 == trades_after_1


# ── FIFO Internal Behavior Tests ────────────────────────────────────────

class TestFIFOInternalBehavior:
    """Tests that verify internal helper behavior via observable effects."""

    def test_trade_reuses_existing_ticket(self, conn, stock_account):
        """Running FIFO twice should reuse the same trade (same id)."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        ids1 = run_fifo_matching(conn, stock_account, iid)
        ids2 = run_fifo_matching(conn, stock_account, iid)
        assert ids1 == ids2

    def test_trade_ticket_format(self, conn, stock_account):
        """Trade broker_ticket_id should follow EXEC_FIFO_{acct}_{inst}_{trip} format."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 110, dt='2025-02-01',
                  broker_result=100)
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 115, dt='2025-03-01')

        ids = run_fifo_matching(conn, stock_account, iid)
        assert len(ids) == 2
        t0 = db.get_trade(conn, ids[0])
        t1 = db.get_trade(conn, ids[1])
        assert t0['broker_ticket_id'] == f"EXEC_FIFO_{stock_account}_{iid}_0"
        assert t1['broker_ticket_id'] == f"EXEC_FIFO_{stock_account}_{iid}_1"

    def test_open_trade_has_null_exit(self, conn, stock_account):
        """Open trade should have NULL exit_date and exit_price."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        tid = _fifo_one(conn, stock_account, iid)
        trade = db.get_trade(conn, tid)
        assert trade['exit_date'] is None
        assert trade['exit_price'] is None
        assert trade['status'] == 'open'
        assert trade['pnl_account_currency'] is None

    def test_trade_direction_always_long(self, conn, stock_account):
        """Current FIFO engine creates all trades as 'long' direction."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        tid = _fifo_one(conn, stock_account, iid)
        assert db.get_trade(conn, tid)['direction'] == 'long'

    def test_entry_date_is_first_buy(self, conn, stock_account):
        """Trade entry_date should be the first buy's execution timestamp."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 5, 100,
                  dt='2025-01-15 09:30:00')
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 110,
                  dt='2025-02-20 14:00:00')
        tid = _fifo_one(conn, stock_account, iid)
        trade = db.get_trade(conn, tid)
        assert trade['entry_date'] == '2025-01-15 09:30:00'

    def test_exit_date_is_last_sell(self, conn, stock_account):
        """Trade exit_date should be the last sell's execution timestamp."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 5, 110,
                  dt='2025-02-01 10:00:00', broker_result=50)
        _add_exec(conn, stock_account, iid, 'S2', 'sell', 5, 120,
                  dt='2025-03-15 16:30:00', broker_result=100)
        tid = _fifo_one(conn, stock_account, iid)
        trade = db.get_trade(conn, tid)
        assert trade['exit_date'] == '2025-03-15 16:30:00'

    def test_lot_consumptions_cleared_on_rerun(self, conn, stock_account):
        """Re-running FIFO should rebuild lot_consumptions from scratch."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 110, dt='2025-02-01',
                  broker_result=100)

        ids1 = run_fifo_matching(conn, stock_account, iid)
        lots1 = get_lot_consumptions_for_trade(conn, ids1[0])
        assert len(lots1) == 1

        # Rerun - should still have exactly 1 lot consumption, not 2
        ids2 = run_fifo_matching(conn, stock_account, iid)
        lots2 = get_lot_consumptions_for_trade(conn, ids2[0])
        assert len(lots2) == 1

    def test_all_executions_linked_after_fifo(self, conn, stock_account):
        """Every execution should have trade_id set after FIFO run."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 5, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 110, dt='2025-02-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 120, dt='2025-03-01',
                  broker_result=200)

        run_fifo_matching(conn, stock_account, iid)
        execs = conn.execute(
            "SELECT trade_id FROM executions WHERE account_id = ? AND instrument_id = ?",
            (stock_account, iid)).fetchall()
        for e in execs:
            assert e['trade_id'] is not None

    def test_execution_trade_id_reset_on_rerun(self, conn, stock_account):
        """Executions should be unlinked then re-linked during FIFO rebuild."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 110, dt='2025-02-01',
                  broker_result=100)

        ids1 = run_fifo_matching(conn, stock_account, iid)
        # Add a new round trip
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 115, dt='2025-03-01')
        ids2 = run_fifo_matching(conn, stock_account, iid)

        # Old trade should still have its executions
        execs_t1 = get_executions_for_trade(conn, ids2[0])
        assert len(execs_t1) == 2  # B1 + S1
        # New trade should have its execution
        execs_t2 = get_executions_for_trade(conn, ids2[1])
        assert len(execs_t2) == 1  # B2


# ── FIFO Stress Tests ───────────────────────────────────────────────────

class TestFIFOStress:

    def test_many_small_buys_one_large_sell(self, conn, stock_account):
        """20 small buys followed by one sell of everything."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        total_shares = 0
        for i in range(20):
            shares = 1 + i * 0.5
            total_shares += shares
            _add_exec(conn, stock_account, iid, f'B{i}', 'buy', shares,
                      100 + i, dt=f'2025-{(i//12)+1:02d}-{(i%28)+1:02d} 10:00:00')

        _add_exec(conn, stock_account, iid, 'S_ALL', 'sell', total_shares,
                  150, dt='2025-12-01 10:00:00', broker_result=500)

        ids = run_fifo_matching(conn, stock_account, iid)
        assert len(ids) == 1
        trade = db.get_trade(conn, ids[0])
        assert trade['status'] == 'closed'
        assert abs(trade['position_size'] - total_shares) < 1e-6

        lots = get_lot_consumptions_for_trade(conn, ids[0])
        assert len(lots) == 20  # Each buy produces one lot consumption
        total_consumed = sum(l['shares_consumed'] for l in lots)
        assert abs(total_consumed - total_shares) < 1e-6

    def test_alternating_buys_sells(self, conn, stock_account):
        """Buy-sell-buy-sell pattern without fully closing: all one trade."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 5, 110, dt='2025-02-01',
                  broker_result=50)
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 10, 105, dt='2025-03-01')
        _add_exec(conn, stock_account, iid, 'S2', 'sell', 5, 115, dt='2025-04-01',
                  broker_result=50)
        # Position is still open (10 remaining)

        ids = run_fifo_matching(conn, stock_account, iid)
        assert len(ids) == 1  # All in one trip since never fully closed
        trade = db.get_trade(conn, ids[0])
        assert trade['status'] == 'open'
        assert trade['position_size'] == 20  # 10 + 10

        open_lots = get_open_lots_for_trade(conn, ids[0])
        total_remaining = sum(l['remaining_shares'] for l in open_lots)
        assert abs(total_remaining - 10.0) < 1e-6

    def test_rapid_round_trips_same_day(self, conn, stock_account):
        """Multiple round trips on the same day, different times."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        for i in range(3):
            _add_exec(conn, stock_account, iid, f'B{i}', 'buy', 10, 100 + i,
                      dt=f'2025-01-15 {10+i*2:02d}:00:00')
            _add_exec(conn, stock_account, iid, f'S{i}', 'sell', 10, 105 + i,
                      dt=f'2025-01-15 {11+i*2:02d}:00:00', broker_result=50)

        ids = run_fifo_matching(conn, stock_account, iid)
        assert len(ids) == 3
        for tid in ids:
            trade = db.get_trade(conn, tid)
            assert trade['status'] == 'closed'
            # All on the same day
            assert '2025-01-15' in trade['entry_date']


# ── FIFO Audit / Integrity Validation Tests ──────────────────────────────

class TestFIFOAuditBasic:
    """Tests for audit_trade_integrity on well-formed data."""

    def test_audit_simple_closed_trade(self, conn, stock_account):
        """A simple buy-sell should pass all invariants."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100,
                  dt='2025-01-01', commission=5)
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 110,
                  dt='2025-02-01', broker_result=100, commission=5)
        tid = _fifo_one(conn, stock_account, iid)
        result = audit_trade_integrity(conn, tid)
        assert result['ok'], f"Audit failed: {result['errors']}"

    def test_audit_open_trade(self, conn, stock_account):
        """An open trade (buy only) should pass all invariants."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        tid = _fifo_one(conn, stock_account, iid)
        result = audit_trade_integrity(conn, tid)
        assert result['ok'], f"Audit failed: {result['errors']}"
        assert result['details']['expected_status'] == 'open'

    def test_audit_multi_lot_closed(self, conn, stock_account):
        """DCA buy + full sell should pass all invariants."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 5, 100,
                  dt='2025-01-01', commission=2.5)
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 110,
                  dt='2025-02-01', commission=2.5)
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 120,
                  dt='2025-03-01', broker_result=150, commission=5)
        tid = _fifo_one(conn, stock_account, iid)
        result = audit_trade_integrity(conn, tid)
        assert result['ok'], f"Audit failed: {result['errors']}"
        assert result['details']['total_bought'] == 10
        assert result['details']['total_sold'] == 10

    def test_audit_partial_sell_open(self, conn, stock_account):
        """Buy 10, sell 3 → open trade with correct remaining."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 3, 110,
                  dt='2025-02-01', broker_result=30)
        tid = _fifo_one(conn, stock_account, iid)
        result = audit_trade_integrity(conn, tid)
        assert result['ok'], f"Audit failed: {result['errors']}"
        assert abs(result['details']['remaining'] - 7.0) < 1e-6
        assert result['details']['expected_status'] == 'open'

    def test_audit_nonexistent_trade(self, conn):
        """Auditing a nonexistent trade ID should return error."""
        result = audit_trade_integrity(conn, 999999)
        assert not result['ok']
        assert 'Trade not found' in result['errors'][0]

    def test_audit_round_trips(self, conn, stock_account):
        """Two round trips — audit both, both should pass."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 110,
                  dt='2025-02-01', broker_result=100)
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 115, dt='2025-03-01')
        _add_exec(conn, stock_account, iid, 'S2', 'sell', 5, 125,
                  dt='2025-04-01', broker_result=50)

        ids = run_fifo_matching(conn, stock_account, iid)
        for tid in ids:
            result = audit_trade_integrity(conn, tid)
            assert result['ok'], f"Trade {tid} failed: {result['errors']}"


class TestFIFOAuditInstrumentLevel:
    """Tests for audit_instrument_integrity."""

    def test_audit_instrument_all_ok(self, conn, stock_account):
        """Full instrument audit with multiple round trips."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 110,
                  dt='2025-02-01', broker_result=100)
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 115, dt='2025-03-01')
        run_fifo_matching(conn, stock_account, iid)

        result = audit_instrument_integrity(conn, stock_account, iid)
        assert result['ok'], f"Instrument audit failed: {result}"
        assert result['total_trades'] == 2
        assert len(result['orphan_errors']) == 0

    def test_audit_instrument_no_trades(self, conn, stock_account):
        """Instrument with no FIFO trades should pass cleanly."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        result = audit_instrument_integrity(conn, stock_account, iid)
        assert result['ok']
        assert result['total_trades'] == 0


class TestFIFOAuditInvariants:
    """Tests that verify specific invariant checks detect corruption."""

    def test_invariant_entry_price_correct(self, conn, stock_account):
        """Verify weighted average entry price matches manual calculation."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        # 5 @ 100 + 3 @ 120 = (500 + 360) / 8 = 107.5
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 5, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 3, 120, dt='2025-02-01')
        tid = _fifo_one(conn, stock_account, iid)

        result = audit_trade_integrity(conn, tid)
        assert result['ok']
        assert abs(result['details']['expected_entry_price'] - 107.5) < 1e-4

        trade = db.get_trade(conn, tid)
        assert abs(trade['entry_price'] - 107.5) < 1e-4

    def test_invariant_exit_price_correct(self, conn, stock_account):
        """Verify weighted average exit price matches manual calculation."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        # Sell in two tranches: 6 @ 110 + 4 @ 115 = (660 + 460) / 10 = 112.0
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 6, 110,
                  dt='2025-02-01', broker_result=60)
        _add_exec(conn, stock_account, iid, 'S2', 'sell', 4, 115,
                  dt='2025-03-01', broker_result=60)
        tid = _fifo_one(conn, stock_account, iid)

        result = audit_trade_integrity(conn, tid)
        assert result['ok']
        assert abs(result['details']['expected_exit_price'] - 112.0) < 1e-4

    def test_invariant_commission_aggregation(self, conn, stock_account):
        """Commission should equal sum of all execution commissions."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 5, 100,
                  dt='2025-01-01', commission=4.99)
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 110,
                  dt='2025-02-01', commission=4.99)
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 120,
                  dt='2025-03-01', broker_result=150, commission=9.98)
        tid = _fifo_one(conn, stock_account, iid)

        result = audit_trade_integrity(conn, tid)
        assert result['ok']
        assert abs(result['details']['expected_commission'] - 19.96) < 0.01

    def test_invariant_lot_consumption_sum(self, conn, stock_account):
        """Lot consumptions should sum exactly to total sold shares."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 7, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 3, 110, dt='2025-02-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 8, 120,
                  dt='2025-03-01', broker_result=160)
        _add_exec(conn, stock_account, iid, 'S2', 'sell', 2, 125,
                  dt='2025-04-01', broker_result=30)
        tid = _fifo_one(conn, stock_account, iid)

        lots = get_lot_consumptions_for_trade(conn, tid)
        total_consumed = sum(lc['shares_consumed'] for lc in lots)
        assert abs(total_consumed - 10.0) < 1e-6

        result = audit_trade_integrity(conn, tid)
        assert result['ok']

    def test_invariant_no_overlot_consumption(self, conn, stock_account):
        """No single buy lot should be consumed more than its original size."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 5, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 110, dt='2025-02-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 120,
                  dt='2025-03-01', broker_result=150)
        tid = _fifo_one(conn, stock_account, iid)

        result = audit_trade_integrity(conn, tid)
        assert result['ok']
        # B1 consumed 5, B2 consumed 5 — neither exceeds original
        for buy_id, consumed in result['details']['consumed_per_buy'].items():
            assert consumed <= 5.0 + 1e-6


# ── FIFO Mathematical Correctness ────────────────────────────────────────

class TestFIFOMathematicalPnl:
    """Hand-verified P&L calculations to prove FIFO math is correct."""

    def test_simple_pnl_same_currency(self, conn, stock_account):
        """Buy 10 @ $100, sell 10 @ $110 → computed P&L = 10 * (110 - 100) = $100."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 110,
                  dt='2025-02-01', broker_result=100)
        tid = _fifo_one(conn, stock_account, iid)

        lots = get_lot_consumptions_for_trade(conn, tid)
        assert len(lots) == 1
        # P&L = 10 * 110/1 - 10 * 100/1 = 1100 - 1000 = 100
        assert abs(lots[0]['pnl_computed'] - 100.0) < 0.01

    def test_pnl_with_exchange_rate_manual(self, conn, stock_account):
        """Buy 10 @ $100 (EUR/USD 1.10), sell 10 @ $110 (EUR/USD 1.12).
        Account currency is EUR.
        Buy cost in EUR: 10 * 100 / 1.10 = 909.0909
        Sell proceeds in EUR: 10 * 110 / 1.12 = 982.1429
        P&L in EUR: 982.1429 - 909.0909 = 73.0519
        """
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100,
                  dt='2025-01-01', xrate=1.10)
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 110,
                  dt='2025-02-01', xrate=1.12, broker_result=73.05)
        tid = _fifo_one(conn, stock_account, iid)

        lots = get_lot_consumptions_for_trade(conn, tid)
        expected = (10 * 110 / 1.12) - (10 * 100 / 1.10)
        assert abs(lots[0]['pnl_computed'] - expected) < 0.01

    def test_pnl_fifo_ordering_matters(self, conn, stock_account):
        """Buying at different prices — FIFO order affects P&L per lot.
        B1: 5 @ $100, B2: 5 @ $200, S1: 5 @ $150
        FIFO matches S1 against B1 → P&L = 5 * (150 - 100) = $250
        If LIFO, would match B2 → P&L = 5 * (150 - 200) = -$250
        """
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 5, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 200, dt='2025-02-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 5, 150,
                  dt='2025-03-01', broker_result=250)
        tid = _fifo_one(conn, stock_account, iid)

        lots = get_lot_consumptions_for_trade(conn, tid)
        assert len(lots) == 1
        # FIFO: matched against $100 lot → profit
        assert lots[0]['pnl_computed'] > 0
        assert abs(lots[0]['pnl_computed'] - 250.0) < 0.01

    def test_pnl_spanning_two_lots(self, conn, stock_account):
        """Sell spans two buy lots — P&L computed per-lot.
        B1: 3 @ $100, B2: 7 @ $120, S1: 5 @ $130
        Lot 1: 3 shares from B1 → 3 * (130-100) = $90
        Lot 2: 2 shares from B2 → 2 * (130-120) = $20
        Total computed: $110
        """
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 3, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 7, 120, dt='2025-02-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 5, 130,
                  dt='2025-03-01', broker_result=110)
        tid = _fifo_one(conn, stock_account, iid)

        lots = get_lot_consumptions_for_trade(conn, tid)
        assert len(lots) == 2
        # Lot 1: 3 shares from B1 @ 100
        assert abs(lots[0]['pnl_computed'] - 90.0) < 0.01
        # Lot 2: 2 shares from B2 @ 120
        assert abs(lots[1]['pnl_computed'] - 20.0) < 0.01
        # Total
        total = sum(lc['pnl_computed'] for lc in lots)
        assert abs(total - 110.0) < 0.01

    def test_pnl_losing_trade_manual(self, conn, stock_account):
        """Buy 10 @ $100, sell 10 @ $90 → P&L = -100."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 90,
                  dt='2025-02-01', broker_result=-100)
        tid = _fifo_one(conn, stock_account, iid)

        lots = get_lot_consumptions_for_trade(conn, tid)
        assert abs(lots[0]['pnl_computed'] - (-100.0)) < 0.01

    def test_pnl_breakeven_trade(self, conn, stock_account):
        """Buy and sell at the same price → P&L = 0."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 100,
                  dt='2025-02-01', broker_result=0)
        tid = _fifo_one(conn, stock_account, iid)
        lots = get_lot_consumptions_for_trade(conn, tid)
        assert abs(lots[0]['pnl_computed']) < 0.01

    def test_pnl_mixed_xrate_per_lot(self, conn, stock_account):
        """Two buys with different exchange rates, one sell.
        B1: 5 @ $100, xrate=1.10 → cost = 5*100/1.10 = 454.5455
        B2: 5 @ $120, xrate=1.15 → cost = 5*120/1.15 = 521.7391
        S1: 10 @ $130, xrate=1.20
        Lot1: 5*130/1.20 - 454.5455 = 541.6667 - 454.5455 = 87.1212
        Lot2: 5*130/1.20 - 521.7391 = 541.6667 - 521.7391 = 19.9275
        """
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 5, 100,
                  dt='2025-01-01', xrate=1.10)
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 120,
                  dt='2025-02-01', xrate=1.15)
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 130,
                  dt='2025-03-01', xrate=1.20, broker_result=107.05)
        tid = _fifo_one(conn, stock_account, iid)

        lots = get_lot_consumptions_for_trade(conn, tid)
        assert len(lots) == 2

        expected_lot1 = (5 * 130 / 1.20) - (5 * 100 / 1.10)
        expected_lot2 = (5 * 130 / 1.20) - (5 * 120 / 1.15)
        assert abs(lots[0]['pnl_computed'] - expected_lot1) < 0.01
        assert abs(lots[1]['pnl_computed'] - expected_lot2) < 0.01


# ── FIFO Cross-Account Isolation ─────────────────────────────────────────

class TestFIFOAccountIsolation:
    """Ensure FIFO operations for one account never affect another."""

    def test_fifo_doesnt_touch_other_accounts(self, conn, stock_account):
        """FIFO for account A should not affect account B's data."""
        acct_b = db.create_account(conn, name='Account B', broker='TestBroker',
                                    currency='EUR', asset_type='stocks')
        iid = db.get_or_create_instrument(conn, 'AAPL')

        # Account A: 1 closed round trip
        _add_exec(conn, stock_account, iid, 'A_B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'A_S1', 'sell', 10, 110,
                  dt='2025-02-01', broker_result=100)

        # Account B: 1 open trade
        _add_exec(conn, acct_b, iid, 'B_B1', 'buy', 5, 200, dt='2025-01-01')

        # Run FIFO for account A
        ids_a = run_fifo_matching(conn, stock_account, iid)

        # Account B's execution should still be unlinked
        b_exec = conn.execute(
            "SELECT trade_id FROM executions WHERE broker_order_id = 'B_B1'"
        ).fetchone()
        assert b_exec['trade_id'] is None

        # Run FIFO for account B
        ids_b = run_fifo_matching(conn, acct_b, iid)

        # Both should have their own trades
        assert len(ids_a) == 1
        assert len(ids_b) == 1
        assert ids_a[0] != ids_b[0]

        # Cross-check: A's trade should not have B's executions
        a_execs = get_executions_for_trade(conn, ids_a[0])
        for e in a_execs:
            assert e['account_id'] == stock_account

    def test_audit_doesnt_see_other_account(self, conn, stock_account):
        """Instrument audit should be scoped to the given account."""
        acct_b = db.create_account(conn, name='Account B', broker='TestBroker',
                                    currency='EUR', asset_type='stocks')
        iid = db.get_or_create_instrument(conn, 'AAPL')

        _add_exec(conn, stock_account, iid, 'A_B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, acct_b, iid, 'B_B1', 'buy', 5, 200, dt='2025-01-01')
        run_fifo_matching(conn, stock_account, iid)
        run_fifo_matching(conn, acct_b, iid)

        result_a = audit_instrument_integrity(conn, stock_account, iid)
        result_b = audit_instrument_integrity(conn, acct_b, iid)
        assert result_a['total_trades'] == 1
        assert result_b['total_trades'] == 1


# ── FIFO Oversell / Boundary Behaviour ───────────────────────────────────

class TestFIFOBoundaryBehaviour:
    """Tests for boundary conditions and graceful degradation."""

    def test_oversell_is_silently_handled(self, conn, stock_account):
        """Selling more shares than bought — engine processes what it can."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 5, 100, dt='2025-01-01')
        # Sell 10 but only 5 available
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 110,
                  dt='2025-02-01', broker_result=50)
        tid = _fifo_one(conn, stock_account, iid)

        lots = get_lot_consumptions_for_trade(conn, tid)
        # Should only consume 5 (what was available)
        total_consumed = sum(lc['shares_consumed'] for lc in lots)
        assert abs(total_consumed - 5.0) < 1e-6

    def test_zero_price_buy(self, conn, stock_account):
        """Price of 0 should not crash the engine."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 0, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 50,
                  dt='2025-02-01', broker_result=500)
        tid = _fifo_one(conn, stock_account, iid)
        trade = db.get_trade(conn, tid)
        assert trade['status'] == 'closed'
        assert trade['entry_price'] == 0.0

    def test_very_small_shares(self, conn, stock_account):
        """Fractional shares like 0.001 should work correctly."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 0.001, 150,
                  dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 0.001, 160,
                  dt='2025-02-01', broker_result=0.01)
        tid = _fifo_one(conn, stock_account, iid)
        trade = db.get_trade(conn, tid)
        assert trade['status'] == 'closed'

        result = audit_trade_integrity(conn, tid)
        assert result['ok'], f"Audit failed: {result['errors']}"

    def test_very_large_position(self, conn, stock_account):
        """Large share count should not lose precision."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 1000000, 0.01,
                  dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 1000000, 0.02,
                  dt='2025-02-01', broker_result=10000)
        tid = _fifo_one(conn, stock_account, iid)
        trade = db.get_trade(conn, tid)
        assert trade['status'] == 'closed'
        assert trade['position_size'] == 1000000

        result = audit_trade_integrity(conn, tid)
        assert result['ok']

    def test_null_exchange_rate_defaults_to_one(self, conn, stock_account):
        """NULL exchange_rate should be treated as 1.0."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100,
                  dt='2025-01-01', xrate=None)
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 110,
                  dt='2025-02-01', xrate=None, broker_result=100)
        tid = _fifo_one(conn, stock_account, iid)

        lots = get_lot_consumptions_for_trade(conn, tid)
        # With xrate=1, P&L = 10*(110-100) = 100
        assert abs(lots[0]['pnl_computed'] - 100.0) < 0.01

    def test_null_commission_treated_as_zero(self, conn, stock_account):
        """NULL commission should not break aggregation."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100,
                  dt='2025-01-01', commission=None)
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 110,
                  dt='2025-02-01', broker_result=100, commission=None)
        tid = _fifo_one(conn, stock_account, iid)
        trade = db.get_trade(conn, tid)
        assert trade['commission'] == 0.0

    def test_null_broker_result_pnl_is_zero(self, conn, stock_account):
        """If all sells have NULL broker_result, official P&L should be 0."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 110,
                  dt='2025-02-01', broker_result=None)
        tid = _fifo_one(conn, stock_account, iid)
        trade = db.get_trade(conn, tid)
        # broker_result was None, so total_broker_pnl = 0.0
        assert trade['pnl_account_currency'] == 0.0


# ── FIFO Floating-Point Precision ────────────────────────────────────────

class TestFIFOFloatingPointPrecision:
    """Tests for numerical stability with floating-point edge cases."""

    def test_many_small_buys_exact_sell(self, conn, stock_account):
        """20 buys of 0.5 shares each, sell all 10.0 → should close exactly."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        for i in range(20):
            _add_exec(conn, stock_account, iid, f'B{i}', 'buy', 0.5, 100 + i,
                      dt=f'2025-01-{i+1:02d}')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10.0, 130,
                  dt='2025-02-01', broker_result=500)
        tid = _fifo_one(conn, stock_account, iid)
        trade = db.get_trade(conn, tid)
        assert trade['status'] == 'closed'

        result = audit_trade_integrity(conn, tid)
        assert result['ok'], f"Precision issue: {result['errors']}"

    def test_thirds_dont_accumulate_error(self, conn, stock_account):
        """Buy 3 × 3.333... shares, sell 9.999... → should close."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        third = 10.0 / 3.0  # 3.333...
        _add_exec(conn, stock_account, iid, 'B1', 'buy', third, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'B2', 'buy', third, 110, dt='2025-02-01')
        _add_exec(conn, stock_account, iid, 'B3', 'buy', third, 120, dt='2025-03-01')
        total = third * 3  # This is exactly 10.0 in float64
        _add_exec(conn, stock_account, iid, 'S1', 'sell', total, 130,
                  dt='2025-04-01', broker_result=300)

        ids = run_fifo_matching(conn, stock_account, iid)
        assert len(ids) == 1
        trade = db.get_trade(conn, ids[0])
        assert trade['status'] == 'closed'

    def test_penny_stock_precision(self, conn, stock_account):
        """Very small prices (sub-penny) should compute P&L accurately."""
        iid = db.get_or_create_instrument(conn, 'PENNY')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 100000, 0.0001,
                  dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 100000, 0.0002,
                  dt='2025-02-01', broker_result=10)
        tid = _fifo_one(conn, stock_account, iid)

        lots = get_lot_consumptions_for_trade(conn, tid)
        # P&L = 100000 * (0.0002 - 0.0001) = 10.0
        assert abs(lots[0]['pnl_computed'] - 10.0) < 0.01

    def test_high_price_stock_precision(self, conn, stock_account):
        """Very high prices (like BRK.A) should compute correctly."""
        iid = db.get_or_create_instrument(conn, 'BRK.A')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 1, 600000.00,
                  dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 1, 610000.00,
                  dt='2025-02-01', broker_result=10000)
        tid = _fifo_one(conn, stock_account, iid)

        lots = get_lot_consumptions_for_trade(conn, tid)
        assert abs(lots[0]['pnl_computed'] - 10000.0) < 0.01


# ── FIFO Audit After Every Scenario ──────────────────────────────────────

class TestFIFOAuditAfterComplex:
    """Run audit on trades produced by complex multi-step scenarios."""

    def test_audit_after_five_round_trips(self, conn, stock_account):
        """Five sequential round trips — all should pass audit."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        for i in range(5):
            _add_exec(conn, stock_account, iid, f'B{i}', 'buy', 10, 100 + i * 5,
                      dt=f'2025-0{i+1}-01', commission=2)
            _add_exec(conn, stock_account, iid, f'S{i}', 'sell', 10, 110 + i * 5,
                      dt=f'2025-0{i+1}-15', broker_result=100, commission=2)
        ids = run_fifo_matching(conn, stock_account, iid)
        assert len(ids) == 5

        for tid in ids:
            result = audit_trade_integrity(conn, tid)
            assert result['ok'], f"Trade {tid}: {result['errors']}"

    def test_audit_after_dca_partial_sells(self, conn, stock_account):
        """DCA into position, sell in 4 partial tranches — should pass audit."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        # Buy 25 total in 5 lots of 5
        for i in range(5):
            _add_exec(conn, stock_account, iid, f'B{i}', 'buy', 5, 100 + i * 2,
                      dt=f'2025-01-{i+1:02d}')
        # Sell in 4 partial tranches
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 8, 115,
                  dt='2025-02-01', broker_result=100)
        _add_exec(conn, stock_account, iid, 'S2', 'sell', 7, 118,
                  dt='2025-03-01', broker_result=110)
        _add_exec(conn, stock_account, iid, 'S3', 'sell', 6, 120,
                  dt='2025-04-01', broker_result=100)
        _add_exec(conn, stock_account, iid, 'S4', 'sell', 4, 122,
                  dt='2025-05-01', broker_result=80)
        tid = _fifo_one(conn, stock_account, iid)
        trade = db.get_trade(conn, tid)
        assert trade['status'] == 'closed'

        result = audit_trade_integrity(conn, tid)
        assert result['ok'], f"Audit failed: {result['errors']}"
        # Verify total consumed = 25
        assert abs(result['details']['total_lot_consumed'] - 25.0) < 1e-6

    def test_audit_after_rerun(self, conn, stock_account):
        """FIFO rerun should produce audit-clean results."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 10, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 110,
                  dt='2025-02-01', broker_result=100)

        # Run 3 times
        for _ in range(3):
            ids = run_fifo_matching(conn, stock_account, iid)
            for tid in ids:
                result = audit_trade_integrity(conn, tid)
                assert result['ok']

    def test_audit_with_exchange_rates(self, conn, stock_account):
        """Multi-lot trade with varying exchange rates — audit all invariants."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 5, 100,
                  dt='2025-01-01', xrate=1.10, commission=5)
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 110,
                  dt='2025-02-01', xrate=1.15, commission=5)
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 120,
                  dt='2025-03-01', xrate=1.20, broker_result=80, commission=10)
        tid = _fifo_one(conn, stock_account, iid)

        result = audit_trade_integrity(conn, tid)
        assert result['ok'], f"Audit failed: {result['errors']}"
        assert abs(result['details']['expected_commission'] - 20.0) < 0.01


class TestFIFODivisionGuards:
    """Guards against division-by-zero in weighted average calculations."""

    def test_zero_shares_buy_does_not_crash(self, conn, stock_account):
        """A buy execution with 0 shares is pathological but must not crash."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        # 0-share buy — total_bought = 0
        _add_exec(conn, stock_account, iid, 'B-ZERO', 'buy', 0, 150, dt='2025-01-01')
        # FIFO should handle this without ZeroDivisionError
        try:
            run_fifo_matching(conn, stock_account, iid)
        except ZeroDivisionError:
            pytest.fail("run_fifo_matching raised ZeroDivisionError on 0-share buy")

    def test_normal_buy_sell_wavg_correct(self, conn, stock_account):
        """Weighted average entry/exit prices are correct after the guard."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        _add_exec(conn, stock_account, iid, 'B1', 'buy', 5, 100, dt='2025-01-01')
        _add_exec(conn, stock_account, iid, 'B2', 'buy', 5, 110, dt='2025-01-15')
        _add_exec(conn, stock_account, iid, 'S1', 'sell', 10, 120, dt='2025-02-01',
                  broker_result=100)
        tid = _fifo_one(conn, stock_account, iid)
        trade = db.get_trade(conn, tid)
        # Weighted avg = (5*100 + 5*110) / 10 = 105
        assert abs(trade['entry_price'] - 105.0) < 1e-6
        assert abs(trade['exit_price'] - 120.0) < 1e-6
