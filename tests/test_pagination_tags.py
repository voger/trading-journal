"""
Tests for paginated trade queries and tag functionality.

Covers:
  - get_or_create_tag
  - get_trades_paged / get_trades_all_filtered with all filter dimensions
  - Tag filtering (tag_id kwarg in _build_trade_filters)
  - set_trade_tags / get_trade_tags round-trip
"""
import pytest

import database as db
from database import (
    get_or_create_tag, get_tags, get_trade_tags, set_trade_tags,
    get_trades_paged, get_trades_all_filtered,
)


# ── Helpers ───────────────────────────────────────────────────────────────

def _make_trade(conn, aid, symbol, pnl=0.0, swap=0.0, commission=0.0,
                status='closed', direction='long',
                entry_date='2025-03-10 09:00:00',
                exit_date='2025-03-11 15:00:00',
                grade=None, exit_reason=None, setup_id=None):
    iid = db.get_or_create_instrument(conn, symbol)
    return db.create_trade(
        conn, account_id=aid, instrument_id=iid, direction=direction,
        entry_date=entry_date, entry_price=100, position_size=1,
        exit_date=exit_date if status == 'closed' else None,
        exit_price=100 + pnl if status == 'closed' else None,
        status=status,
        pnl_account_currency=pnl,
        swap=swap, commission=commission,
        execution_grade=grade,
        exit_reason=exit_reason,
        setup_type_id=setup_id,
    )


# ── get_or_create_tag ────────────────────────────────────────────────────

class TestGetOrCreateTag:

    def test_creates_new_tag(self, conn):
        tid = get_or_create_tag(conn, 'breakout')
        assert isinstance(tid, int)
        assert tid > 0

    def test_returns_same_id_for_existing(self, conn):
        id1 = get_or_create_tag(conn, 'trend')
        id2 = get_or_create_tag(conn, 'trend')
        assert id1 == id2

    def test_strips_whitespace(self, conn):
        id1 = get_or_create_tag(conn, 'reversal')
        id2 = get_or_create_tag(conn, '  reversal  ')
        assert id1 == id2

    def test_different_names_different_ids(self, conn):
        id1 = get_or_create_tag(conn, 'scalp')
        id2 = get_or_create_tag(conn, 'swing')
        assert id1 != id2

    def test_tag_appears_in_get_tags(self, conn):
        get_or_create_tag(conn, 'momentum')
        names = [t['name'] for t in get_tags(conn)]
        assert 'momentum' in names


# ── set_trade_tags / get_trade_tags ──────────────────────────────────────

class TestTradeTagsRoundTrip:

    def test_set_and_get_tags(self, conn, forex_account):
        tid = _make_trade(conn, forex_account, 'EURUSD', 50.0)
        tag1 = get_or_create_tag(conn, 'breakout')
        tag2 = get_or_create_tag(conn, 'london')
        set_trade_tags(conn, tid, [tag1, tag2])
        tags = get_trade_tags(conn, tid)
        assert {t['name'] for t in tags} == {'breakout', 'london'}

    def test_replace_tags(self, conn, forex_account):
        tid = _make_trade(conn, forex_account, 'EURUSD', 50.0)
        tag1 = get_or_create_tag(conn, 'old')
        tag2 = get_or_create_tag(conn, 'new')
        set_trade_tags(conn, tid, [tag1])
        set_trade_tags(conn, tid, [tag2])
        tags = get_trade_tags(conn, tid)
        assert [t['name'] for t in tags] == ['new']

    def test_clear_tags_with_empty_list(self, conn, forex_account):
        tid = _make_trade(conn, forex_account, 'EURUSD', 50.0)
        tag1 = get_or_create_tag(conn, 'temp')
        set_trade_tags(conn, tid, [tag1])
        set_trade_tags(conn, tid, [])
        assert get_trade_tags(conn, tid) == []

    def test_no_tags_returns_empty(self, conn, forex_account):
        tid = _make_trade(conn, forex_account, 'EURUSD', 50.0)
        assert get_trade_tags(conn, tid) == []


# ── get_trades_all_filtered (no LIMIT) ──────────────────────────────────

class TestGetTradesAllFiltered:

    def test_returns_all_trades_no_filter(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 10.0)
        _make_trade(conn, forex_account, 'GBPUSD', 20.0)
        rows = get_trades_all_filtered(conn, account_id=forex_account)
        assert len(rows) == 2

    def test_account_filter(self, conn, forex_account):
        other = db.create_account(conn, name='Other', broker='B',
                                  currency='USD', asset_type='forex',
                                  initial_balance=0)
        _make_trade(conn, forex_account, 'EURUSD', 10.0)
        _make_trade(conn, other, 'USDJPY', 20.0)
        rows = get_trades_all_filtered(conn, account_id=forex_account)
        assert len(rows) == 1
        assert rows[0]['symbol'] == 'EURUSD'

    def test_direction_filter(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 10.0, direction='long')
        _make_trade(conn, forex_account, 'GBPUSD', 10.0, direction='short')
        rows = get_trades_all_filtered(conn, account_id=forex_account, direction='long')
        assert len(rows) == 1
        assert rows[0]['direction'] == 'long'

    def test_status_filter(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 10.0, status='closed')
        _make_trade(conn, forex_account, 'GBPUSD', 0.0, status='open')
        rows = get_trades_all_filtered(conn, account_id=forex_account, status='open')
        assert len(rows) == 1
        assert rows[0]['status'] == 'open'

    def test_grade_filter(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 10.0, grade='A')
        _make_trade(conn, forex_account, 'GBPUSD', 10.0, grade='B')
        _make_trade(conn, forex_account, 'USDJPY', 10.0, grade=None)
        rows = get_trades_all_filtered(conn, account_id=forex_account, grade='A')
        assert len(rows) == 1
        assert rows[0]['symbol'] == 'EURUSD'

    def test_exit_reason_filter(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 50.0, exit_reason='target_hit')
        _make_trade(conn, forex_account, 'GBPUSD', -10.0, exit_reason='stop_loss')
        rows = get_trades_all_filtered(conn, account_id=forex_account,
                                       exit_reason='target_hit')
        assert len(rows) == 1
        assert rows[0]['symbol'] == 'EURUSD'

    def test_outcome_winners(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 50.0)
        _make_trade(conn, forex_account, 'GBPUSD', -10.0)
        _make_trade(conn, forex_account, 'USDJPY', 0.0)
        rows = get_trades_all_filtered(conn, account_id=forex_account, outcome='winners')
        assert len(rows) == 1
        assert rows[0]['symbol'] == 'EURUSD'

    def test_outcome_losers(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 50.0)
        _make_trade(conn, forex_account, 'GBPUSD', -10.0)
        rows = get_trades_all_filtered(conn, account_id=forex_account, outcome='losers')
        assert len(rows) == 1
        assert rows[0]['symbol'] == 'GBPUSD'

    def test_outcome_breakeven(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 50.0)
        _make_trade(conn, forex_account, 'GBPUSD', 0.0)
        rows = get_trades_all_filtered(conn, account_id=forex_account, outcome='breakeven')
        assert len(rows) == 1
        assert rows[0]['symbol'] == 'GBPUSD'

    def test_outcome_uses_effective_pnl(self, conn, forex_account):
        """A trade with positive raw P&L but negative swap+commission is a loser."""
        _make_trade(conn, forex_account, 'EURUSD', pnl=10.0, swap=-8.0, commission=-5.0)
        winners = get_trades_all_filtered(conn, account_id=forex_account, outcome='winners')
        losers = get_trades_all_filtered(conn, account_id=forex_account, outcome='losers')
        assert len(winners) == 0
        assert len(losers) == 1

    def test_date_from_filter(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 10.0,
                    entry_date='2025-01-05 10:00:00', exit_date='2025-01-06 10:00:00')
        _make_trade(conn, forex_account, 'GBPUSD', 20.0,
                    entry_date='2025-06-10 10:00:00', exit_date='2025-06-11 10:00:00')
        rows = get_trades_all_filtered(conn, account_id=forex_account,
                                       date_from='2025-06-01')
        assert len(rows) == 1
        assert rows[0]['symbol'] == 'GBPUSD'

    def test_date_to_filter(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 10.0,
                    entry_date='2025-01-05 10:00:00', exit_date='2025-01-06 10:00:00')
        _make_trade(conn, forex_account, 'GBPUSD', 20.0,
                    entry_date='2025-06-10 10:00:00', exit_date='2025-06-11 10:00:00')
        rows = get_trades_all_filtered(conn, account_id=forex_account,
                                       date_to='2025-03-01')
        assert len(rows) == 1
        assert rows[0]['symbol'] == 'EURUSD'

    def test_symbol_search_filter(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 10.0)
        _make_trade(conn, forex_account, 'GBPUSD', 10.0)
        _make_trade(conn, forex_account, 'USDJPY', 10.0)
        # Search 'EUR' matches only EURUSD
        rows = get_trades_all_filtered(conn, account_id=forex_account,
                                       symbol_search='EUR')
        symbols = {r['symbol'] for r in rows}
        assert 'EURUSD' in symbols
        assert 'GBPUSD' not in symbols
        assert 'USDJPY' not in symbols

    def test_symbol_search_case_insensitive(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 10.0)
        rows = get_trades_all_filtered(conn, account_id=forex_account,
                                       symbol_search='eur')
        assert len(rows) == 1

    def test_tag_id_filter(self, conn, forex_account):
        tid1 = _make_trade(conn, forex_account, 'EURUSD', 10.0)
        tid2 = _make_trade(conn, forex_account, 'GBPUSD', 20.0)
        tag_id = get_or_create_tag(conn, 'london')
        set_trade_tags(conn, tid1, [tag_id])
        rows = get_trades_all_filtered(conn, account_id=forex_account, tag_id=tag_id)
        assert len(rows) == 1
        assert rows[0]['symbol'] == 'EURUSD'

    def test_no_tag_match_returns_empty(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 10.0)
        unused_tag = get_or_create_tag(conn, 'unused')
        rows = get_trades_all_filtered(conn, account_id=forex_account, tag_id=unused_tag)
        assert rows == []

    def test_combined_filters(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 50.0, direction='long',
                    entry_date='2025-06-10 09:00:00', exit_date='2025-06-11 09:00:00')
        _make_trade(conn, forex_account, 'GBPUSD', -20.0, direction='short',
                    entry_date='2025-06-10 09:00:00', exit_date='2025-06-11 09:00:00')
        _make_trade(conn, forex_account, 'USDJPY', 30.0, direction='long',
                    entry_date='2025-01-05 09:00:00', exit_date='2025-01-06 09:00:00')
        rows = get_trades_all_filtered(
            conn, account_id=forex_account,
            direction='long', outcome='winners', date_from='2025-06-01'
        )
        assert len(rows) == 1
        assert rows[0]['symbol'] == 'EURUSD'

    def test_ordered_entry_date_desc(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 10.0,
                    entry_date='2025-01-01 09:00:00', exit_date='2025-01-02 09:00:00')
        _make_trade(conn, forex_account, 'GBPUSD', 10.0,
                    entry_date='2025-06-01 09:00:00', exit_date='2025-06-02 09:00:00')
        rows = get_trades_all_filtered(conn, account_id=forex_account)
        dates = [r['entry_date'][:10] for r in rows]
        assert dates == sorted(dates, reverse=True)

    def test_no_filters_returns_all_accounts(self, conn, forex_account):
        """When account_id=None, returns trades for all accounts."""
        other = db.create_account(conn, name='Other2', broker='B',
                                  currency='USD', asset_type='forex',
                                  initial_balance=0)
        _make_trade(conn, forex_account, 'EURUSD', 10.0)
        _make_trade(conn, other, 'USDJPY', 10.0)
        rows = get_trades_all_filtered(conn, account_id=None)
        assert len(rows) == 2


# ── get_trades_paged ─────────────────────────────────────────────────────

class TestGetTradesPaged:

    def _make_n_trades(self, conn, aid, n):
        """Create n closed trades with sequential entry dates."""
        ids = []
        for i in range(n):
            date = f'2025-{(i % 12) + 1:02d}-{(i % 28) + 1:02d} 09:00:00'
            exit_date = f'2025-{(i % 12) + 1:02d}-{(i % 28) + 1:02d} 17:00:00'
            tid = _make_trade(conn, aid, f'SYM{i:03d}', pnl=float(i),
                              entry_date=date, exit_date=exit_date)
            ids.append(tid)
        return ids

    def test_page_zero_returns_first_n(self, conn, forex_account):
        self._make_n_trades(conn, forex_account, 10)
        rows = get_trades_paged(conn, account_id=forex_account, page=0, page_size=5)
        assert len(rows) == 5

    def test_page_one_returns_next_n(self, conn, forex_account):
        self._make_n_trades(conn, forex_account, 10)
        page0 = get_trades_paged(conn, account_id=forex_account, page=0, page_size=5)
        page1 = get_trades_paged(conn, account_id=forex_account, page=1, page_size=5)
        ids0 = {r['id'] for r in page0}
        ids1 = {r['id'] for r in page1}
        assert ids0.isdisjoint(ids1), "Pages must not overlap"

    def test_pages_cover_all_trades(self, conn, forex_account):
        self._make_n_trades(conn, forex_account, 13)
        page0 = get_trades_paged(conn, account_id=forex_account, page=0, page_size=5)
        page1 = get_trades_paged(conn, account_id=forex_account, page=1, page_size=5)
        page2 = get_trades_paged(conn, account_id=forex_account, page=2, page_size=5)
        all_ids = {r['id'] for r in page0} | {r['id'] for r in page1} | {r['id'] for r in page2}
        assert len(all_ids) == 13

    def test_beyond_last_page_returns_empty(self, conn, forex_account):
        self._make_n_trades(conn, forex_account, 5)
        rows = get_trades_paged(conn, account_id=forex_account, page=99, page_size=5)
        assert rows == []

    def test_filters_applied_before_pagination(self, conn, forex_account):
        _make_trade(conn, forex_account, 'EURUSD', 10.0, direction='long')
        _make_trade(conn, forex_account, 'GBPUSD', 10.0, direction='short')
        _make_trade(conn, forex_account, 'USDJPY', 10.0, direction='long')
        rows = get_trades_paged(conn, account_id=forex_account,
                                page=0, page_size=10, direction='long')
        assert len(rows) == 2
        assert all(r['direction'] == 'long' for r in rows)

    def test_empty_db_returns_empty(self, conn, forex_account):
        rows = get_trades_paged(conn, account_id=forex_account, page=0, page_size=10)
        assert rows == []

    def test_page_size_one(self, conn, forex_account):
        self._make_n_trades(conn, forex_account, 3)
        rows = get_trades_paged(conn, account_id=forex_account, page=0, page_size=1)
        assert len(rows) == 1

    def test_paged_and_all_same_total(self, conn, forex_account):
        """Sum of all pages equals get_trades_all_filtered total."""
        self._make_n_trades(conn, forex_account, 7)
        all_rows = get_trades_all_filtered(conn, account_id=forex_account)
        paged_ids = set()
        for page in range(4):
            for r in get_trades_paged(conn, account_id=forex_account,
                                      page=page, page_size=3):
                paged_ids.add(r['id'])
        assert {r['id'] for r in all_rows} == paged_ids
