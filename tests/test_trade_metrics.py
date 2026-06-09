"""
Issue #10: a headless, Qt-free trade_metrics module owns the math.

These tests assert the math DIRECTLY — no Qt event loop, no widgets — which is
the whole point of the issue: the metric formulas had their only test surface
behind QWidgets. Boundaries covered: zero risk, missing SL/TP/exit, breakeven,
infinite profit factor, direction case-insensitivity.
"""
import subprocess
import sys

import pytest

import trade_metrics


# ── effective_pnl ─────────────────────────────────────────────────────────

class TestEffectivePnl:

    def test_sums_pnl_swap_commission(self):
        t = {'pnl_account_currency': 100.0, 'swap': -2.0, 'commission': -3.0}
        assert trade_metrics.effective_pnl(t) == 95.0

    def test_treats_none_as_zero(self):
        t = {'pnl_account_currency': None, 'swap': None, 'commission': None}
        assert trade_metrics.effective_pnl(t) == 0


# ── aggregate (the former _compute_stats) ──────────────────────────────────

def _trade(pnl, swap=0.0, commission=0.0):
    return {'pnl_account_currency': pnl, 'swap': swap, 'commission': commission}


class TestAggregate:

    def test_empty_returns_none(self):
        assert trade_metrics.aggregate([]) is None

    def test_known_mix(self):
        trades = [_trade(100), _trade(-50), _trade(200), _trade(-30), _trade(0)]
        s = trade_metrics.aggregate(trades)
        assert s['total_trades'] == 5
        assert s['winners'] == 2
        assert s['losers'] == 2
        assert s['breakeven'] == 1
        assert s['gross_profit'] == 300
        assert s['gross_loss'] == 80
        assert s['net_pnl'] == 220
        assert s['avg_win'] == 150
        assert s['avg_loss'] == 40
        assert s['win_rate'] == 40.0
        assert s['profit_factor'] == pytest.approx(3.75)
        # expectancy = 0.4*150 - 0.6*40 = 60 - 24
        assert s['expectancy'] == pytest.approx(36.0)

    def test_swap_and_commission_flip_classification(self):
        """A nominal winner whose costs push it negative is counted a loser."""
        s = trade_metrics.aggregate([_trade(10, swap=-6, commission=-6)])  # eff = -2
        assert s['winners'] == 0
        assert s['losers'] == 1

    def test_all_winners_profit_factor_is_infinite(self):
        s = trade_metrics.aggregate([_trade(10), _trade(20)])
        assert s['gross_loss'] == 0
        assert s['profit_factor'] == float('inf')

    def test_all_losers(self):
        s = trade_metrics.aggregate([_trade(-10), _trade(-30)])
        assert s['gross_profit'] == 0
        assert s['win_rate'] == 0
        assert s['profit_factor'] == 0.0
        assert s['expectancy'] == pytest.approx(-20.0)

    def test_single_breakeven_trade(self):
        """No winners, no losers: PF stays infinite (gross_loss not > 0)."""
        s = trade_metrics.aggregate([_trade(0)])
        assert s['breakeven'] == 1
        assert s['win_rate'] == 0
        assert s['profit_factor'] == float('inf')

    def test_win_rate_boundary_one_of_three(self):
        s = trade_metrics.aggregate([_trade(5), _trade(-5), _trade(-5)])
        assert s['win_rate'] == pytest.approx(100 / 3)


# ── r_multiple ──────────────────────────────────────────────────────────────

class TestRMultiple:

    def test_long_win(self):
        assert trade_metrics.r_multiple(100, 90, 120, 'long') == pytest.approx(2.0)

    def test_long_loss(self):
        assert trade_metrics.r_multiple(100, 90, 95, 'long') == pytest.approx(-0.5)

    def test_short_win(self):
        assert trade_metrics.r_multiple(100, 110, 80, 'short') == pytest.approx(2.0)

    def test_short_loss(self):
        assert trade_metrics.r_multiple(100, 110, 105, 'short') == pytest.approx(-0.5)

    def test_direction_is_case_insensitive(self):
        assert (trade_metrics.r_multiple(100, 90, 120, 'LONG')
                == trade_metrics.r_multiple(100, 90, 120, 'long'))

    def test_non_long_direction_treated_as_short(self):
        # garbage direction behaves like short (mirrors the preview's `== 'LONG'`)
        assert trade_metrics.r_multiple(100, 110, 80, None) == pytest.approx(2.0)

    def test_breakeven_exit_is_zero(self):
        assert trade_metrics.r_multiple(100, 90, 100, 'long') == 0.0

    def test_zero_risk_returns_none(self):
        assert trade_metrics.r_multiple(100, 100, 120, 'long') is None

    def test_missing_exit_returns_none(self):
        assert trade_metrics.r_multiple(100, 90, 0, 'long') is None
        assert trade_metrics.r_multiple(100, 90, None, 'long') is None

    def test_missing_stop_returns_none(self):
        assert trade_metrics.r_multiple(100, 0, 120, 'long') is None
        assert trade_metrics.r_multiple(100, None, 120, 'long') is None

    def test_missing_entry_returns_none(self):
        assert trade_metrics.r_multiple(0, 90, 120, 'long') is None


# ── risk_reward ──────────────────────────────────────────────────────────────

class TestRiskReward:

    def test_basic(self):
        assert trade_metrics.risk_reward(100, 90, 130) == pytest.approx(3.0)

    def test_direction_independent(self):
        # |tp-entry| / |entry-sl| regardless of long/short
        assert trade_metrics.risk_reward(100, 110, 70) == pytest.approx(3.0)

    def test_missing_tp_returns_none(self):
        assert trade_metrics.risk_reward(100, 90, 0) is None
        assert trade_metrics.risk_reward(100, 90, None) is None

    def test_missing_stop_returns_none(self):
        assert trade_metrics.risk_reward(100, 0, 130) is None

    def test_zero_risk_returns_none(self):
        assert trade_metrics.risk_reward(100, 100, 130) is None


# ── Single source of truth: analytics reuses the module ──────────────────────

class TestSingleSourceOfTruth:

    def test_analytics_compute_stats_is_aggregate(self):
        from db import analytics
        assert analytics._compute_stats is trade_metrics.aggregate

    def test_database_effective_pnl_is_module_effective_pnl(self):
        import database
        assert database.effective_pnl is trade_metrics.effective_pnl


# ── Headless: importable without Qt ──────────────────────────────────────────

class TestHeadless:

    def test_importing_does_not_pull_in_qt(self):
        """trade_metrics must import in a process where PyQt6 is never loaded."""
        code = (
            "import sys; import trade_metrics; "
            "assert 'PyQt6' not in sys.modules, sorted(m for m in sys.modules if 'PyQt' in m)"
        )
        result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
