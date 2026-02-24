"""
Tests for CSV export: get_trades_for_export DB query and the CSV writing
logic used by TradesTab._on_export().
"""
import csv
import io
import os

import pytest

import database as db
from database import (
    get_trades_for_export, EXPORT_COLUMNS, effective_pnl,
)


# ── Helpers ───────────────────────────────────────────────────────────────

def _make_trade(conn, aid, symbol, pnl, swap=0.0, commission=0.0,
                status='closed', direction='long',
                entry_date='2025-03-10 09:00:00',
                exit_date='2025-03-11 15:00:00',
                exit_reason=None):
    iid = db.get_or_create_instrument(conn, symbol)
    return db.create_trade(
        conn, account_id=aid, instrument_id=iid, direction=direction,
        entry_date=entry_date, entry_price=100, position_size=1,
        exit_date=exit_date if status == 'closed' else None,
        exit_price=100 + pnl if status == 'closed' else None,
        status=status,
        pnl_account_currency=pnl,
        swap=swap, commission=commission,
        exit_reason=exit_reason,
    )


def _write_csv(trades):
    """Simulate the CSV writing logic from TradesTab._on_export().

    Returns the parsed CSV as a list of dicts (DictReader style).
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([label for _, label in EXPORT_COLUMNS] + ['Net P&L'])
    for t in trades:
        row = []
        for key, _ in EXPORT_COLUMNS:
            val = t[key] if key in t.keys() else ''
            row.append('' if val is None else val)
        row.append(round(effective_pnl(t), 8))
        writer.writerow(row)

    buf.seek(0)
    return list(csv.DictReader(buf))


# ── get_trades_for_export (DB layer) ──────────────────────────────────────

class TestGetTradesForExport:

    def test_returns_all_trades_for_account(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 50.0)
        _make_trade(conn, forex_account, 'GBPUSD', -20.0)
        rows = get_trades_for_export(conn, forex_account)
        assert len(rows) == 2

    def test_isolates_by_account(self, conn, forex_account):
        other = db.create_account(conn, name='Other', broker='B',
                                  currency='USD', asset_type='forex',
                                  initial_balance=0)
        _make_trade(conn, forex_account, 'EURUSD', 50.0)
        _make_trade(conn, other, 'USDJPY', 100.0)
        rows = get_trades_for_export(conn, forex_account)
        assert len(rows) == 1
        assert rows[0]['symbol'] == 'EURUSD'

    def test_status_filter_closed(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 50.0, status='closed')
        _make_trade(conn, forex_account, 'GBPUSD', 0.0, status='open')
        rows = get_trades_for_export(conn, forex_account, status_filter='closed')
        assert len(rows) == 1
        assert rows[0]['status'] == 'closed'

    def test_status_filter_open(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 50.0, status='closed')
        _make_trade(conn, forex_account, 'GBPUSD', 0.0, status='open')
        rows = get_trades_for_export(conn, forex_account, status_filter='open')
        assert len(rows) == 1
        assert rows[0]['status'] == 'open'

    def test_status_filter_none_returns_all(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 50.0, status='closed')
        _make_trade(conn, forex_account, 'GBPUSD', 0.0, status='open')
        rows = get_trades_for_export(conn, forex_account, status_filter=None)
        assert len(rows) == 2

    def test_date_from_filter(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 10.0,
                    entry_date='2025-01-05 10:00:00', exit_date='2025-01-06 10:00:00')
        _make_trade(conn, forex_account, 'GBPUSD', 20.0,
                    entry_date='2025-03-10 10:00:00', exit_date='2025-03-11 10:00:00')
        rows = get_trades_for_export(conn, forex_account, date_from='2025-03-01')
        assert len(rows) == 1
        assert rows[0]['symbol'] == 'GBPUSD'

    def test_date_to_filter(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 10.0,
                    entry_date='2025-01-05 10:00:00', exit_date='2025-01-06 10:00:00')
        _make_trade(conn, forex_account, 'GBPUSD', 20.0,
                    entry_date='2025-03-10 10:00:00', exit_date='2025-03-11 10:00:00')
        rows = get_trades_for_export(conn, forex_account, date_to='2025-01-31')
        assert len(rows) == 1
        assert rows[0]['symbol'] == 'EURUSD'

    def test_joined_columns_present(self, conn, forex_account):
        """Rows include joined columns: symbol, instrument_name, account_name, setup_name."""
        _make_trade(conn, forex_account, 'EURUSD', 50.0)
        rows = get_trades_for_export(conn, forex_account)
        r = rows[0]
        assert r['symbol'] == 'EURUSD'
        assert r['account_name'] is not None
        assert r['account_currency'] is not None

    def test_empty_account_returns_empty_list(self, conn, forex_account):
        rows = get_trades_for_export(conn, forex_account)
        assert rows == []

    def test_ordered_by_entry_date_ascending(self, conn, forex_account):
        _make_trade(conn, forex_account, 'GBPUSD', 20.0,
                    entry_date='2025-06-10 10:00:00', exit_date='2025-06-11 10:00:00')
        _make_trade(conn, forex_account, 'EURUSD', 10.0,
                    entry_date='2025-01-05 10:00:00', exit_date='2025-01-06 10:00:00')
        rows = get_trades_for_export(conn, forex_account)
        dates = [r['entry_date'][:10] for r in rows]
        assert dates == sorted(dates)


# ── CSV writing logic ─────────────────────────────────────────────────────

class TestCsvOutput:

    def test_header_row_matches_export_columns_plus_net_pnl(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 50.0)
        trades = get_trades_for_export(conn, forex_account)
        parsed = _write_csv(trades)
        expected_headers = [label for _, label in EXPORT_COLUMNS] + ['Net P&L']
        assert list(parsed[0].keys()) == expected_headers

    def test_net_pnl_raw_pnl_only(self, conn, forex_account):
        """Net P&L equals raw pnl when swap and commission are 0."""
        _make_trade(conn, forex_account, 'EURUSD', 75.0, swap=0.0, commission=0.0)
        trades = get_trades_for_export(conn, forex_account)
        parsed = _write_csv(trades)
        assert float(parsed[0]['Net P&L']) == pytest.approx(75.0)

    def test_net_pnl_includes_swap_and_commission(self, conn, forex_account):
        """Net P&L = pnl + swap + commission (all three summed)."""
        _make_trade(conn, forex_account, 'EURUSD', 100.0, swap=-8.0, commission=-2.0)
        trades = get_trades_for_export(conn, forex_account)
        parsed = _write_csv(trades)
        assert float(parsed[0]['Net P&L']) == pytest.approx(90.0)

    def test_net_pnl_negative_trade_with_costs(self, conn, forex_account):
        """Net P&L correctly negative when pnl and costs are all negative."""
        _make_trade(conn, forex_account, 'EURUSD', -50.0, swap=-3.0, commission=-1.0)
        trades = get_trades_for_export(conn, forex_account)
        parsed = _write_csv(trades)
        assert float(parsed[0]['Net P&L']) == pytest.approx(-54.0)

    def test_none_values_written_as_empty_string(self, conn, forex_account):
        """Null DB values become '' in the CSV, not 'None'."""
        _make_trade(conn, forex_account, 'EURUSD', 50.0)
        trades = get_trades_for_export(conn, forex_account)
        parsed = _write_csv(trades)
        # exit_date is NULL for open trades; at minimum pnl_pips/r_multiple may be NULL
        for key, label in EXPORT_COLUMNS:
            cell = parsed[0][label]
            assert cell != 'None', f"Column '{label}' written as 'None' instead of ''"

    def test_row_count_matches_trade_count(self, conn, forex_account):
        for sym in ('EURUSD', 'GBPUSD', 'USDJPY'):
            _make_trade(conn, forex_account, sym, 10.0)
        trades = get_trades_for_export(conn, forex_account)
        parsed = _write_csv(trades)
        assert len(parsed) == 3

    def test_empty_trades_produces_header_only(self):
        """Exporting an empty list writes only the header, no data rows."""
        parsed = _write_csv([])
        assert parsed == []

    def test_symbol_and_direction_present(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 50.0, direction='short')
        trades = get_trades_for_export(conn, forex_account)
        parsed = _write_csv(trades)
        assert parsed[0]['Symbol'] == 'EURUSD'
        assert parsed[0]['Direction'] == 'short'

    def test_open_trade_has_empty_exit_fields(self, conn, forex_account):
        """Open trades have no exit_date or exit_price — written as ''."""
        _make_trade(conn, forex_account, 'EURUSD', 0.0, status='open')
        trades = get_trades_for_export(conn, forex_account)
        parsed = _write_csv(trades)
        assert parsed[0]['Exit Date'] == ''
        assert parsed[0]['Exit Price'] == ''

    def test_multiple_trades_correct_net_pnl_each(self, conn, forex_account):
        """Each row has its own Net P&L, not a sum across all rows."""
        _make_trade(conn, forex_account, 'EURUSD', 100.0, swap=-5.0, commission=-2.0)
        _make_trade(conn, forex_account, 'GBPUSD', -30.0, swap=-1.0, commission=-1.0)
        trades = get_trades_for_export(conn, forex_account)
        parsed = _write_csv(trades)
        net_pnls = [float(r['Net P&L']) for r in parsed]
        assert pytest.approx(93.0) in net_pnls
        assert pytest.approx(-32.0) in net_pnls
