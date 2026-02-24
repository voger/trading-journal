"""
Tests for analytics breakdowns and _compute_stats — database layer.
Covers: get_trade_breakdowns by instrument/setup/day/session/exit_reason/
        direction/month, _compute_stats edge cases, _get_session mapping.
"""
import pytest
from datetime import datetime

import database as db
from database import (
    get_trade_stats, get_trade_breakdowns, _compute_stats, effective_pnl,
    get_advanced_stats,
    _get_session, _DOW_NAMES, TRADING_SESSIONS,
)


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_trade(conn, aid, symbol, pnl, direction='long', status='closed',
                entry_date='2025-01-15 10:00:00', exit_date=None,
                exit_reason=None, setup_id=None):
    """Create a closed trade with a given instrument and P&L."""
    iid = db.get_or_create_instrument(conn, symbol)
    if exit_date is None and status == 'closed':
        exit_date = '2025-02-01 10:00:00'
    return db.create_trade(conn,
        account_id=aid, instrument_id=iid, direction=direction,
        entry_date=entry_date, entry_price=100, position_size=1,
        exit_date=exit_date,
        exit_price=100 + pnl if status == 'closed' else None,
        status=status, pnl_account_currency=pnl,
        exit_reason=exit_reason, setup_type_id=setup_id)


# ── _compute_stats ────────────────────────────────────────────────────────

class TestComputeStats:
    """Test the shared _compute_stats helper."""

    def test_empty_list(self):
        assert _compute_stats([]) is None

    def test_single_winner(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 50)
        trades = conn.execute(
            "SELECT * FROM trades WHERE account_id=? AND status='closed'",
            (forex_account,)).fetchall()
        stats = _compute_stats(trades)
        assert stats['total_trades'] == 1
        assert stats['winners'] == 1
        assert stats['losers'] == 0
        assert stats['win_rate'] == 100.0
        assert stats['net_pnl'] == 50
        assert stats['profit_factor'] == float('inf')

    def test_mixed_trades(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 100)
        _make_trade(conn, forex_account, 'GBPUSD', -40)
        _make_trade(conn, forex_account, 'AUDUSD', 0)
        trades = conn.execute(
            "SELECT * FROM trades WHERE account_id=? AND status='closed'",
            (forex_account,)).fetchall()
        stats = _compute_stats(trades)
        assert stats['total_trades'] == 3
        assert stats['winners'] == 1
        assert stats['losers'] == 1
        assert stats['breakeven'] == 1
        assert stats['net_pnl'] == 60
        assert abs(stats['profit_factor'] - 2.5) < 0.01

    def test_expectancy_formula(self, conn, forex_account):
        """Expectancy = (WR * AvgWin) - (LR * AvgLoss)."""
        _make_trade(conn, forex_account, 'EURUSD', 30)
        _make_trade(conn, forex_account, 'GBPUSD', 20)
        _make_trade(conn, forex_account, 'AUDUSD', -10)
        _make_trade(conn, forex_account, 'USDJPY', -15)
        trades = conn.execute(
            "SELECT * FROM trades WHERE account_id=? AND status='closed'",
            (forex_account,)).fetchall()
        stats = _compute_stats(trades)
        # WR=50%, AvgWin=25, AvgLoss=12.5
        # Expectancy = 0.5*25 - 0.5*12.5 = 6.25
        assert abs(stats['expectancy'] - 6.25) < 0.01


# ── Session mapping ──────────────────────────────────────────────────────

class TestSessionMapping:

    def test_asian_session(self):
        assert _get_session(0) == 'Asian'
        assert _get_session(3) == 'Asian'
        assert _get_session(7) == 'Asian'

    def test_london_session(self):
        assert _get_session(8) == 'London'
        assert _get_session(10) == 'London'
        assert _get_session(12) == 'London'

    def test_ny_session(self):
        assert _get_session(13) == 'New York'
        assert _get_session(15) == 'New York'
        assert _get_session(16) == 'New York'

    def test_late_ny(self):
        assert _get_session(17) == 'Late NY'
        assert _get_session(20) == 'Late NY'

    def test_off_hours(self):
        assert _get_session(21) == 'Off-hours'
        assert _get_session(23) == 'Off-hours'

    def test_all_hours_covered(self):
        """Every hour 0-23 maps to a known session."""
        for h in range(24):
            session = _get_session(h)
            assert session in TRADING_SESSIONS, f"Hour {h} mapped to unknown session: {session}"


# ── Breakdowns by instrument ─────────────────────────────────────────────

class TestBreakdownByInstrument:

    def test_no_trades_empty(self, conn, forex_account):
        result = get_trade_breakdowns(conn, forex_account, 'instrument')
        assert result == []

    def test_open_trades_excluded(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 10, status='open')
        result = get_trade_breakdowns(conn, forex_account, 'instrument')
        assert result == []

    def test_single_instrument(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 50)
        _make_trade(conn, forex_account, 'EURUSD', -20)
        result = get_trade_breakdowns(conn, forex_account, 'instrument')
        assert len(result) == 1
        assert result[0]['group_name'] == 'EURUSD'
        assert result[0]['total_trades'] == 2
        assert result[0]['net_pnl'] == 30

    def test_multiple_instruments_sorted_by_pnl(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 50)
        _make_trade(conn, forex_account, 'GBPUSD', -30)
        _make_trade(conn, forex_account, 'AUDUSD', 100)
        result = get_trade_breakdowns(conn, forex_account, 'instrument')
        assert len(result) == 3
        # Sorted by net_pnl descending
        assert result[0]['group_name'] == 'AUDUSD'
        assert result[0]['net_pnl'] == 100
        assert result[1]['group_name'] == 'EURUSD'
        assert result[2]['group_name'] == 'GBPUSD'

    def test_per_instrument_stats_correct(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 50)
        _make_trade(conn, forex_account, 'EURUSD', 30)
        _make_trade(conn, forex_account, 'EURUSD', -20)
        result = get_trade_breakdowns(conn, forex_account, 'instrument')
        eu = result[0]
        assert eu['total_trades'] == 3
        assert eu['winners'] == 2
        assert eu['losers'] == 1
        assert eu['net_pnl'] == 60
        assert eu['gross_profit'] == 80
        assert eu['gross_loss'] == 20
        assert abs(eu['win_rate'] - 66.67) < 0.1


# ── Breakdowns by setup ──────────────────────────────────────────────────

class TestBreakdownBySetup:

    def test_setup_grouping(self, conn, forex_account):
        sid = db.create_setup_type(conn, name='Pullback', description='')
        _make_trade(conn, forex_account, 'EURUSD', 50, setup_id=sid)
        _make_trade(conn, forex_account, 'GBPUSD', -10, setup_id=sid)
        _make_trade(conn, forex_account, 'AUDUSD', 20, setup_id=None)
        result = get_trade_breakdowns(conn, forex_account, 'setup')
        assert len(result) == 2
        names = {r['group_name'] for r in result}
        assert 'Pullback' in names
        assert '(no setup)' in names

    def test_no_setup_label(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 10)
        result = get_trade_breakdowns(conn, forex_account, 'setup')
        assert result[0]['group_name'] == '(no setup)'


# ── Breakdowns by day of week ────────────────────────────────────────────

class TestBreakdownByDayOfWeek:

    def test_weekday_grouping(self, conn, forex_account):
        # 2025-01-13 = Monday, 2025-01-14 = Tuesday, 2025-01-15 = Wednesday
        _make_trade(conn, forex_account, 'EURUSD', 50,
                    entry_date='2025-01-13 10:00:00')
        _make_trade(conn, forex_account, 'GBPUSD', -20,
                    entry_date='2025-01-14 14:00:00')
        _make_trade(conn, forex_account, 'AUDUSD', 30,
                    entry_date='2025-01-13 15:00:00')
        result = get_trade_breakdowns(conn, forex_account, 'day_of_week')
        assert len(result) == 2
        # Should be sorted by weekday order: Monday first, then Tuesday
        assert result[0]['group_name'] == 'Monday'
        assert result[0]['total_trades'] == 2
        assert result[0]['net_pnl'] == 80
        assert result[1]['group_name'] == 'Tuesday'

    def test_all_weekdays_valid(self):
        """All _DOW_NAMES are valid datetime weekday names."""
        assert len(_DOW_NAMES) == 7
        assert _DOW_NAMES[0] == 'Monday'
        assert _DOW_NAMES[6] == 'Sunday'


# ── Breakdowns by session ────────────────────────────────────────────────

class TestBreakdownBySession:

    def test_session_grouping(self, conn, forex_account):
        # 03:00 = Asian, 10:00 = London, 15:00 = New York
        _make_trade(conn, forex_account, 'USDJPY', 40,
                    entry_date='2025-01-15 03:00:00')
        _make_trade(conn, forex_account, 'EURUSD', -10,
                    entry_date='2025-01-15 10:00:00')
        _make_trade(conn, forex_account, 'GBPUSD', 20,
                    entry_date='2025-01-15 15:00:00')
        result = get_trade_breakdowns(conn, forex_account, 'session')
        names = {r['group_name'] for r in result}
        assert 'Asian' in names
        assert 'London' in names
        assert 'New York' in names


# ── Breakdowns by exit reason ────────────────────────────────────────────

class TestBreakdownByExitReason:

    def test_exit_reason_grouping(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 50, exit_reason='target_hit')
        _make_trade(conn, forex_account, 'GBPUSD', -30, exit_reason='stop_loss')
        _make_trade(conn, forex_account, 'AUDUSD', 10, exit_reason='target_hit')
        _make_trade(conn, forex_account, 'USDJPY', -5, exit_reason=None)
        result = get_trade_breakdowns(conn, forex_account, 'exit_reason')
        names = {r['group_name'] for r in result}
        assert 'target_hit' in names
        assert 'stop_loss' in names
        assert '(none)' in names


# ── Breakdowns by direction ──────────────────────────────────────────────

class TestBreakdownByDirection:

    def test_long_short_split(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 50, direction='long')
        _make_trade(conn, forex_account, 'GBPUSD', -20, direction='short')
        _make_trade(conn, forex_account, 'AUDUSD', 30, direction='long')
        result = get_trade_breakdowns(conn, forex_account, 'direction')
        assert len(result) == 2
        longs = [r for r in result if r['group_name'] == 'Long'][0]
        shorts = [r for r in result if r['group_name'] == 'Short'][0]
        assert longs['total_trades'] == 2
        assert longs['net_pnl'] == 80
        assert shorts['total_trades'] == 1
        assert shorts['net_pnl'] == -20


# ── Breakdowns by month ─────────────────────────────────────────────────

class TestBreakdownByMonth:

    def test_month_grouping_chronological(self, conn, forex_account):
        # Grouping must use exit_date (when P&L is realized), not entry_date
        _make_trade(conn, forex_account, 'EURUSD', 50,
                    entry_date='2025-03-15 10:00:00',
                    exit_date='2025-03-28 10:00:00')
        _make_trade(conn, forex_account, 'GBPUSD', -20,
                    entry_date='2025-01-10 10:00:00',
                    exit_date='2025-01-25 10:00:00')
        _make_trade(conn, forex_account, 'AUDUSD', 30,
                    entry_date='2025-03-20 10:00:00',
                    exit_date='2025-03-30 10:00:00')
        result = get_trade_breakdowns(conn, forex_account, 'month')
        assert len(result) == 2
        # Sorted chronologically by exit month
        assert result[0]['group_name'] == '2025-01'
        assert result[1]['group_name'] == '2025-03'
        assert result[1]['total_trades'] == 2
        assert result[1]['net_pnl'] == 80

    def test_month_grouping_uses_exit_date_not_entry_date(self, conn, forex_account):
        """A trade entered in December but exited in January belongs in January."""
        _make_trade(conn, forex_account, 'EURUSD', 100,
                    entry_date='2024-12-28 10:00:00',
                    exit_date='2025-01-05 10:00:00')
        result = get_trade_breakdowns(conn, forex_account, 'month')
        assert len(result) == 1
        assert result[0]['group_name'] == '2025-01'  # exit month, not entry month


# ── Cross-account isolation ──────────────────────────────────────────────

class TestBreakdownAccountIsolation:

    def test_other_account_excluded(self, conn, forex_account):
        other_aid = db.create_account(conn, name='Other', broker='X',
                                       currency='EUR', asset_type='forex')
        _make_trade(conn, forex_account, 'EURUSD', 50)
        _make_trade(conn, other_aid, 'EURUSD', 100)
        result = get_trade_breakdowns(conn, forex_account, 'instrument')
        assert len(result) == 1
        assert result[0]['net_pnl'] == 50


# ── get_trade_stats uses _compute_stats ──────────────────────────────────

class TestGetTradeStatsRefactored:
    """Verify get_trade_stats still works after refactoring to use _compute_stats."""

    def test_returns_none_no_data(self, conn, forex_account):
        assert get_trade_stats(conn, account_id=forex_account) is None

    def test_basic_stats(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 50)
        _make_trade(conn, forex_account, 'GBPUSD', -30)
        stats = get_trade_stats(conn, account_id=forex_account)
        assert stats is not None
        assert stats['total_trades'] == 2
        assert stats['net_pnl'] == 20

    def test_excluded_trades_filtered(self, conn, forex_account):
        tid = _make_trade(conn, forex_account, 'EURUSD', 50)
        _make_trade(conn, forex_account, 'GBPUSD', -10)
        # Exclude the winner
        conn.execute("UPDATE trades SET is_excluded = 1 WHERE id = ?", (tid,))
        conn.commit()
        stats = get_trade_stats(conn, account_id=forex_account)
        assert stats['total_trades'] == 1
        assert stats['net_pnl'] == -10


# ── Effective P&L (swap + commission included) ────────────────────────────

class TestEffectivePnl:
    """effective_pnl should include pnl + swap + commission."""

    def test_pnl_only(self, conn, forex_account):
        tid = _make_trade(conn, forex_account, 'EURUSD', 10)
        t = conn.execute("SELECT * FROM trades WHERE id=?", (tid,)).fetchone()
        assert effective_pnl(t) == 10

    def test_pnl_plus_swap(self, conn, forex_account):
        tid = _make_trade(conn, forex_account, 'EURUSD', 10)
        conn.execute("UPDATE trades SET swap=-3 WHERE id=?", (tid,))
        conn.commit()
        t = conn.execute("SELECT * FROM trades WHERE id=?", (tid,)).fetchone()
        assert effective_pnl(t) == 7

    def test_swap_flips_winner_to_loser(self, conn, forex_account):
        """A trade with pnl=+2 but swap=-5 is a loser in effective terms."""
        tid = _make_trade(conn, forex_account, 'EURUSD', 2)
        conn.execute("UPDATE trades SET swap=-5 WHERE id=?", (tid,))
        conn.commit()
        trades = conn.execute(
            "SELECT * FROM trades WHERE account_id=? AND status='closed'",
            (forex_account,)).fetchall()
        stats = _compute_stats(trades)
        assert stats['winners'] == 0
        assert stats['losers'] == 1
        assert abs(stats['net_pnl'] - (-3)) < 0.001

    def test_net_pnl_includes_swap_and_commission(self, conn, forex_account):
        tid1 = _make_trade(conn, forex_account, 'EURUSD', 100)
        _make_trade(conn, forex_account, 'GBPUSD', -40)
        # Add swap and commission to first trade
        conn.execute(
            "UPDATE trades SET swap=-5, commission=-2 WHERE id=?", (tid1,))
        conn.commit()
        trades = conn.execute(
            "SELECT * FROM trades WHERE account_id=? AND status='closed'",
            (forex_account,)).fetchall()
        stats = _compute_stats(trades)
        # net = (100 - 5 - 2) + (-40) = 53
        assert abs(stats['net_pnl'] - 53) < 0.001


# ── Drawdown with initial_balance ─────────────────────────────────────────

class TestDrawdownWithInitialBalance:
    """Drawdown percentage must be relative to account initial capital, not
    cumulative P/L peak, to avoid nonsensical values > 1000%."""

    def test_drawdown_pct_bounded_by_initial_balance(self, conn):
        """With initial_balance=1000, a 100-unit drawdown = 10%, not thousands %."""
        aid = db.create_account(conn, name='DD Test', broker='B',
                                currency='EUR', asset_type='forex',
                                initial_balance=1000)
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        # One small winner (+5) then a big loser (-100)
        db.create_trade(conn, account_id=aid, instrument_id=iid,
                        direction='long', entry_date='2025-01-01 10:00:00',
                        entry_price=1.0, position_size=1,
                        exit_date='2025-01-02 10:00:00', exit_price=1.05,
                        status='closed', pnl_account_currency=5)
        db.create_trade(conn, account_id=aid, instrument_id=iid,
                        direction='long', entry_date='2025-01-03 10:00:00',
                        entry_price=1.0, position_size=1,
                        exit_date='2025-01-04 10:00:00', exit_price=0.9,
                        status='closed', pnl_account_currency=-100)
        adv = get_advanced_stats(conn, account_id=aid)
        # Peak equity = 1000 + 5 = 1005; trough = 1005 - 100 = 905
        # dd_abs = 100, dd_pct = 100/1005 * 100 ≈ 9.95%
        assert adv['max_drawdown_abs'] == pytest.approx(100, abs=0.01)
        assert adv['max_drawdown_pct'] == pytest.approx(9.95, abs=0.1)

    def test_drawdown_pct_without_initial_balance_still_works(self, conn, forex_account):
        """With initial_balance=0, drawdown still computed once equity goes positive."""
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        db.create_trade(conn, account_id=forex_account, instrument_id=iid,
                        direction='long', entry_date='2025-01-01 10:00:00',
                        entry_price=1.0, position_size=1,
                        exit_date='2025-01-02 10:00:00', exit_price=1.1,
                        status='closed', pnl_account_currency=100)
        db.create_trade(conn, account_id=forex_account, instrument_id=iid,
                        direction='long', entry_date='2025-01-03 10:00:00',
                        entry_price=1.0, position_size=1,
                        exit_date='2025-01-04 10:00:00', exit_price=0.5,
                        status='closed', pnl_account_currency=-60)
        adv = get_advanced_stats(conn, account_id=forex_account)
        # Peak=100, trough=40, dd_abs=60, dd_pct=60%
        assert adv['max_drawdown_abs'] == pytest.approx(60, abs=0.01)
        assert adv['max_drawdown_pct'] == pytest.approx(60.0, abs=0.1)


# ── Calmar ratio edge cases ───────────────────────────────────────────────

class TestCalmarRatio:
    """Calmar ratio = net P&L / max drawdown. Edge cases when drawdown is zero."""

    def _make_winner(self, conn, aid, pnl):
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        return db.create_trade(conn, account_id=aid, instrument_id=iid,
                               direction='long', entry_date='2025-01-01 10:00:00',
                               entry_price=1.0, position_size=1,
                               exit_date='2025-01-02 10:00:00', exit_price=1.1,
                               status='closed', pnl_account_currency=pnl)

    def test_calmar_with_drawdown(self, conn):
        """Normal case: positive P&L with a drawdown."""
        aid = db.create_account(conn, name='C1', broker='B',
                                currency='EUR', asset_type='forex',
                                initial_balance=1000)
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        db.create_trade(conn, account_id=aid, instrument_id=iid,
                        direction='long', entry_date='2025-01-01',
                        entry_price=1.0, position_size=1,
                        exit_date='2025-01-02', exit_price=1.1,
                        status='closed', pnl_account_currency=200)
        db.create_trade(conn, account_id=aid, instrument_id=iid,
                        direction='long', entry_date='2025-01-03',
                        entry_price=1.0, position_size=1,
                        exit_date='2025-01-04', exit_price=0.9,
                        status='closed', pnl_account_currency=-100)
        adv = get_advanced_stats(conn, account_id=aid)
        # net_pnl=100, max_dd_abs=100 → calmar=1.0
        assert adv['calmar_ratio'] == pytest.approx(1.0, abs=0.01)

    def test_calmar_no_drawdown_positive_pnl_is_infinity(self, conn):
        """With no drawdown and positive P&L, Calmar should be infinity, not 0."""
        aid = db.create_account(conn, name='C2', broker='B',
                                currency='EUR', asset_type='forex',
                                initial_balance=1000)
        self._make_winner(conn, aid, 100)
        self._make_winner(conn, aid, 50)
        adv = get_advanced_stats(conn, account_id=aid)
        assert adv['max_drawdown_abs'] == pytest.approx(0.0, abs=0.001)
        assert adv['calmar_ratio'] == float('inf')

    def test_calmar_no_drawdown_zero_pnl_is_zero(self, conn):
        """With no drawdown and zero net P&L, Calmar should be 0."""
        aid = db.create_account(conn, name='C3', broker='B',
                                currency='EUR', asset_type='forex',
                                initial_balance=1000)
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        db.create_trade(conn, account_id=aid, instrument_id=iid,
                        direction='long', entry_date='2025-01-01',
                        entry_price=1.0, position_size=1,
                        exit_date='2025-01-02', exit_price=1.0,
                        status='closed', pnl_account_currency=0)
        adv = get_advanced_stats(conn, account_id=aid)
        assert adv['calmar_ratio'] == pytest.approx(0.0, abs=0.001)
