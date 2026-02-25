"""
Tests for get_setup_performance and get_r_multiple_distribution.
"""
import pytest

import database as db
from database import get_setup_performance, get_r_multiple_distribution


# ── Helper ───────────────────────────────────────────────────────────────────

def _make_trade(conn, aid, symbol='EURUSD', pnl=100.0, setup_id=None,
                status='closed', r_multiple=None,
                entry_date='2025-01-10 09:00:00',
                exit_date='2025-01-15 17:00:00',
                swap=0.0, commission=0.0):
    iid = db.get_or_create_instrument(conn, symbol)
    return db.create_trade(
        conn,
        account_id=aid, instrument_id=iid, direction='long',
        entry_date=entry_date, entry_price=1.10, position_size=1,
        exit_date=exit_date if status == 'closed' else None,
        exit_price=1.20 if status == 'closed' else None,
        status=status,
        pnl_account_currency=pnl,
        swap=swap, commission=commission,
        setup_type_id=setup_id,
        r_multiple=r_multiple,
    )


# ── get_setup_performance ────────────────────────────────────────────────────

class TestGetSetupPerformance:

    def test_empty_account(self, conn, forex_account):
        rows = get_setup_performance(conn, forex_account)
        assert rows == []

    def test_single_setup_single_winner(self, conn, forex_account):
        sid = db.create_setup_type(conn, name='Breakout', description='')
        _make_trade(conn, forex_account, pnl=200.0, setup_id=sid, r_multiple=2.0)
        rows = get_setup_performance(conn, forex_account)
        assert len(rows) == 1
        r = rows[0]
        assert r['setup_name'] == 'Breakout'
        assert r['total_trades'] == 1
        assert r['win_rate'] == pytest.approx(100.0)
        assert r['net_pnl'] == pytest.approx(200.0)
        assert r['avg_pnl'] == pytest.approx(200.0)
        assert r['avg_r'] == pytest.approx(2.0)

    def test_no_setup_trades_grouped_as_no_setup(self, conn, forex_account):
        _make_trade(conn, forex_account, pnl=50.0, setup_id=None)
        rows = get_setup_performance(conn, forex_account)
        assert len(rows) == 1
        assert rows[0]['setup_name'] == '(no setup)'

    def test_multiple_setups(self, conn, forex_account):
        s1 = db.create_setup_type(conn, name='Alpha', description='')
        s2 = db.create_setup_type(conn, name='Beta', description='')
        _make_trade(conn, forex_account, pnl=300.0, setup_id=s1)
        _make_trade(conn, forex_account, pnl=-100.0, setup_id=s2)
        rows = get_setup_performance(conn, forex_account)
        assert len(rows) == 2
        # Sorted by net_pnl descending
        assert rows[0]['setup_name'] == 'Alpha'
        assert rows[1]['setup_name'] == 'Beta'

    def test_win_rate_calculation(self, conn, forex_account):
        sid = db.create_setup_type(conn, name='Mixed', description='')
        _make_trade(conn, forex_account, pnl=100.0, setup_id=sid)
        _make_trade(conn, forex_account, pnl=200.0, setup_id=sid)
        _make_trade(conn, forex_account, pnl=-50.0, setup_id=sid)
        _make_trade(conn, forex_account, pnl=-80.0, setup_id=sid)
        rows = get_setup_performance(conn, forex_account)
        assert len(rows) == 1
        r = rows[0]
        assert r['total_trades'] == 4
        assert r['win_rate'] == pytest.approx(50.0)
        assert r['net_pnl'] == pytest.approx(170.0)

    def test_avg_r_none_when_no_r_multiple(self, conn, forex_account):
        sid = db.create_setup_type(conn, name='NoR', description='')
        _make_trade(conn, forex_account, pnl=100.0, setup_id=sid, r_multiple=None)
        rows = get_setup_performance(conn, forex_account)
        assert rows[0]['avg_r'] is None

    def test_avg_r_partial_coverage(self, conn, forex_account):
        """avg_r computed only from trades that have r_multiple set."""
        sid = db.create_setup_type(conn, name='Partial', description='')
        _make_trade(conn, forex_account, pnl=100.0, setup_id=sid, r_multiple=2.0)
        _make_trade(conn, forex_account, pnl=100.0, setup_id=sid, r_multiple=None)
        rows = get_setup_performance(conn, forex_account)
        assert rows[0]['avg_r'] == pytest.approx(2.0)

    def test_avg_duration_computed(self, conn, forex_account):
        sid = db.create_setup_type(conn, name='DurTest', description='')
        # entry 2025-01-10, exit 2025-01-15 → 5 days
        _make_trade(conn, forex_account, pnl=100.0, setup_id=sid,
                    entry_date='2025-01-10 09:00:00', exit_date='2025-01-15 17:00:00')
        rows = get_setup_performance(conn, forex_account)
        assert rows[0]['avg_duration'] == pytest.approx(5.0)

    def test_open_trades_excluded(self, conn, forex_account):
        sid = db.create_setup_type(conn, name='OpenEx', description='')
        _make_trade(conn, forex_account, pnl=100.0, setup_id=sid, status='open')
        rows = get_setup_performance(conn, forex_account)
        assert rows == []

    def test_effective_pnl_includes_swap_and_commission(self, conn, forex_account):
        """Net P&L should use effective_pnl (pnl + swap + commission)."""
        sid = db.create_setup_type(conn, name='EffPnl', description='')
        _make_trade(conn, forex_account, pnl=200.0, swap=-10.0, commission=-5.0,
                    setup_id=sid)
        rows = get_setup_performance(conn, forex_account)
        assert rows[0]['net_pnl'] == pytest.approx(185.0)

    def test_date_from_filter(self, conn, forex_account):
        from datetime import date
        sid = db.create_setup_type(conn, name='DateF', description='')
        _make_trade(conn, forex_account, pnl=100.0, setup_id=sid,
                    exit_date='2025-01-15 17:00:00')
        _make_trade(conn, forex_account, pnl=200.0, setup_id=sid,
                    exit_date='2025-03-01 17:00:00')
        rows = get_setup_performance(conn, forex_account,
                                     date_from=date(2025, 2, 1))
        assert len(rows) == 1
        assert rows[0]['net_pnl'] == pytest.approx(200.0)

    def test_date_to_filter(self, conn, forex_account):
        from datetime import date
        sid = db.create_setup_type(conn, name='DateT', description='')
        _make_trade(conn, forex_account, pnl=100.0, setup_id=sid,
                    exit_date='2025-01-15 17:00:00')
        _make_trade(conn, forex_account, pnl=200.0, setup_id=sid,
                    exit_date='2025-03-01 17:00:00')
        rows = get_setup_performance(conn, forex_account,
                                     date_to=date(2025, 1, 31))
        assert len(rows) == 1
        assert rows[0]['net_pnl'] == pytest.approx(100.0)

    def test_account_isolation(self, conn, forex_account, stock_account):
        sid = db.create_setup_type(conn, name='Iso', description='')
        _make_trade(conn, forex_account, pnl=999.0, setup_id=sid)
        rows = get_setup_performance(conn, stock_account)
        assert rows == []

    def test_sorted_by_net_pnl_descending(self, conn, forex_account):
        s1 = db.create_setup_type(conn, name='C', description='')
        s2 = db.create_setup_type(conn, name='A', description='')
        s3 = db.create_setup_type(conn, name='B', description='')
        _make_trade(conn, forex_account, pnl=-50.0, setup_id=s3)
        _make_trade(conn, forex_account, pnl=300.0, setup_id=s1)
        _make_trade(conn, forex_account, pnl=150.0, setup_id=s2)
        rows = get_setup_performance(conn, forex_account)
        net_pnls = [r['net_pnl'] for r in rows]
        assert net_pnls == sorted(net_pnls, reverse=True)


# ── get_r_multiple_distribution ──────────────────────────────────────────────

class TestGetRMultipleDistribution:

    def test_empty_account(self, conn, forex_account):
        r_values, excluded = get_r_multiple_distribution(conn, forex_account)
        assert r_values == []
        assert excluded == 0

    def test_all_r_multiples_present(self, conn, forex_account):
        for r in [1.5, -0.5, 2.5, -1.8]:
            _make_trade(conn, forex_account, pnl=10.0, r_multiple=r)
        r_values, excluded = get_r_multiple_distribution(conn, forex_account)
        assert len(r_values) == 4
        assert excluded == 0
        assert set(r_values) == {1.5, -0.5, 2.5, -1.8}

    def test_excluded_count_for_null_r_multiple(self, conn, forex_account):
        _make_trade(conn, forex_account, pnl=100.0, r_multiple=2.0)
        _make_trade(conn, forex_account, pnl=50.0, r_multiple=None)
        _make_trade(conn, forex_account, pnl=80.0, r_multiple=None)
        r_values, excluded = get_r_multiple_distribution(conn, forex_account)
        assert len(r_values) == 1
        assert excluded == 2

    def test_open_trades_excluded(self, conn, forex_account):
        _make_trade(conn, forex_account, pnl=100.0, r_multiple=3.0, status='open')
        r_values, excluded = get_r_multiple_distribution(conn, forex_account)
        assert r_values == []
        assert excluded == 0

    def test_date_from_filter(self, conn, forex_account):
        from datetime import date
        _make_trade(conn, forex_account, pnl=100.0, r_multiple=1.0,
                    exit_date='2025-01-15 17:00:00')
        _make_trade(conn, forex_account, pnl=100.0, r_multiple=2.0,
                    exit_date='2025-03-01 17:00:00')
        r_values, excluded = get_r_multiple_distribution(conn, forex_account,
                                                          date_from=date(2025, 2, 1))
        assert r_values == [2.0]
        assert excluded == 0

    def test_date_to_filter(self, conn, forex_account):
        from datetime import date
        _make_trade(conn, forex_account, pnl=100.0, r_multiple=1.0,
                    exit_date='2025-01-15 17:00:00')
        _make_trade(conn, forex_account, pnl=100.0, r_multiple=2.0,
                    exit_date='2025-03-01 17:00:00')
        r_values, excluded = get_r_multiple_distribution(conn, forex_account,
                                                          date_to=date(2025, 1, 31))
        assert r_values == [1.0]
        assert excluded == 0

    def test_account_isolation(self, conn, forex_account, stock_account):
        _make_trade(conn, forex_account, pnl=100.0, r_multiple=5.0)
        r_values, excluded = get_r_multiple_distribution(conn, stock_account)
        assert r_values == []
        assert excluded == 0

    def test_r_values_are_floats(self, conn, forex_account):
        _make_trade(conn, forex_account, pnl=100.0, r_multiple=1)
        r_values, _ = get_r_multiple_distribution(conn, forex_account)
        assert isinstance(r_values[0], float)

    def test_zero_r_multiple_included(self, conn, forex_account):
        _make_trade(conn, forex_account, pnl=0.0, r_multiple=0.0)
        r_values, excluded = get_r_multiple_distribution(conn, forex_account)
        assert r_values == [0.0]
        assert excluded == 0

    def test_mixed_positive_negative_r(self, conn, forex_account):
        for r in [-3.0, -1.5, -0.5, 0.5, 1.5, 3.0]:
            _make_trade(conn, forex_account, pnl=10.0, r_multiple=r)
        r_values, excluded = get_r_multiple_distribution(conn, forex_account)
        assert len(r_values) == 6
        assert excluded == 0
        assert min(r_values) == pytest.approx(-3.0)
        assert max(r_values) == pytest.approx(3.0)
