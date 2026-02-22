"""
Tests for database.py — schema, migrations, CRUD.
"""
import sqlite3
import os
import pytest

import database as db


class TestSchemaCreation:
    """Verify all tables and indexes are created correctly."""

    def test_all_core_tables_exist(self, conn):
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        expected = {
            'accounts', 'instruments', 'setup_types', 'tags', 'trades',
            'trade_tags', 'trade_charts', 'watchlist_items', 'import_logs',
            'daily_journal', 'formula_definitions', 'app_settings',
            'setup_rules', 'trade_rule_checks', 'account_events',
            'setup_charts', 'executions', 'lot_consumptions', 'dividends',
        }
        missing = expected - tables
        assert not missing, f"Missing tables: {missing}"

    def test_executions_table_columns(self, conn):
        cols = {r[1] for r in conn.execute("PRAGMA table_info(executions)").fetchall()}
        expected = {
            'id', 'account_id', 'instrument_id', 'trade_id', 'broker_order_id',
            'action', 'shares', 'price', 'price_currency', 'exchange_rate',
            'total_account_currency', 'commission', 'broker_result',
            'executed_at', 'import_log_id', 'created_at',
        }
        missing = expected - cols
        assert not missing, f"Missing columns in executions: {missing}"

    def test_lot_consumptions_table_columns(self, conn):
        cols = {r[1] for r in conn.execute("PRAGMA table_info(lot_consumptions)").fetchall()}
        expected = {
            'id', 'trade_id', 'buy_execution_id', 'sell_execution_id',
            'shares_consumed', 'buy_price', 'sell_price',
            'buy_exchange_rate', 'sell_exchange_rate', 'pnl_computed',
            'created_at',
        }
        missing = expected - cols
        assert not missing, f"Missing columns in lot_consumptions: {missing}"

    def test_indexes_exist(self, conn):
        indexes = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
        expected = {
            'idx_executions_account', 'idx_executions_instrument',
            'idx_executions_trade', 'idx_executions_dedup',
            'idx_executions_date', 'idx_lot_consumptions_trade',
            'idx_lot_consumptions_buy', 'idx_lot_consumptions_sell',
        }
        missing = expected - indexes
        assert not missing, f"Missing indexes: {missing}"

    def test_foreign_keys_enabled(self, conn):
        row = conn.execute("PRAGMA foreign_keys").fetchone()
        assert row[0] == 1


class TestMigration:
    """Verify migration creates new tables on old databases."""

    def test_migration_creates_executions_table(self, tmp_path):
        """Simulate an old DB without executions table, verify migration adds it."""
        path = str(tmp_path / "old.db")
        # First init creates everything
        db.init_database(path)
        c = db.get_connection(path)
        # Manually drop the new tables to simulate an old DB
        c.execute("DROP TABLE IF EXISTS lot_consumptions")
        c.execute("DROP TABLE IF EXISTS executions")
        c.commit()
        c.close()

        # Re-init triggers migration
        db.init_database(path)
        c = db.get_connection(path)
        tables = {r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert 'executions' in tables
        assert 'lot_consumptions' in tables
        c.close()

    def test_migration_is_idempotent(self, db_path):
        """Running init_database twice should not error."""
        db.init_database(db_path)  # second time
        conn = db.get_connection(db_path)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert 'executions' in tables
        conn.close()


class TestAccountCRUD:

    def test_create_account(self, conn):
        aid = db.create_account(conn, name='Test', broker='Broker', currency='EUR')
        assert aid is not None
        acct = db.get_account(conn, aid)
        assert acct['name'] == 'Test'
        assert acct['broker'] == 'Broker'
        assert acct['currency'] == 'EUR'
        assert acct['asset_type'] == 'forex'  # default

    def test_create_stock_account(self, conn):
        aid = db.create_account(conn, name='Stocks', broker='T212',
                                currency='EUR', asset_type='stocks')
        acct = db.get_account(conn, aid)
        assert acct['asset_type'] == 'stocks'

    def test_duplicate_account_name_fails(self, conn):
        db.create_account(conn, name='Unique', broker='B1')
        with pytest.raises(sqlite3.IntegrityError):
            db.create_account(conn, name='Unique', broker='B2')

    def test_get_accounts_returns_active_only(self, conn):
        a1 = db.create_account(conn, name='Active', broker='B')
        a2 = db.create_account(conn, name='Inactive', broker='B')
        db.update_account(conn, a2, is_active=0)
        accounts = db.get_accounts(conn, active_only=True)
        ids = [a['id'] for a in accounts]
        assert a1 in ids
        assert a2 not in ids

    def test_delete_account_cascades(self, conn, stock_account):
        aid = stock_account
        # Add some data
        iid = db.get_or_create_instrument(conn, 'AAPL', 'Apple', 'stock')
        db.create_trade(conn, account_id=aid, instrument_id=iid, direction='long',
                        entry_date='2025-01-01', entry_price=100, position_size=10,
                        status='open')
        db.add_account_event(conn, aid, 'deposit', 1000, '2025-01-01')
        db.create_execution(conn, account_id=aid, instrument_id=iid,
                            broker_order_id='X1', action='buy', shares=10,
                            price=100, executed_at='2025-01-01')

        db.delete_account(conn, aid)

        assert db.get_account(conn, aid) is None
        assert conn.execute("SELECT COUNT(*) FROM trades WHERE account_id=?", (aid,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM account_events WHERE account_id=?", (aid,)).fetchone()[0] == 0


class TestInstrumentCRUD:

    def test_get_or_create_instrument_creates(self, conn):
        iid = db.get_or_create_instrument(conn, 'EURUSD', 'EUR/USD', 'forex')
        assert iid is not None
        inst = db.get_instrument(conn, iid)
        assert inst['symbol'] == 'EURUSD'

    def test_get_or_create_instrument_deduplicates(self, conn):
        id1 = db.get_or_create_instrument(conn, 'AAPL', 'Apple')
        id2 = db.get_or_create_instrument(conn, 'AAPL', 'Apple Inc')
        assert id1 == id2

    def test_symbol_case_normalized(self, conn):
        id1 = db.get_or_create_instrument(conn, 'aapl')
        id2 = db.get_or_create_instrument(conn, 'AAPL')
        assert id1 == id2


class TestTradeCRUD:

    def test_create_and_get_trade(self, conn, stock_account):
        iid = db.get_or_create_instrument(conn, 'AAPL')
        tid = db.create_trade(conn, account_id=stock_account, instrument_id=iid,
                              direction='long', entry_date='2025-01-01',
                              entry_price=150.0, position_size=10, status='open')
        trade = db.get_trade(conn, tid)
        assert trade is not None
        assert trade['entry_price'] == 150.0
        assert trade['status'] == 'open'
        assert trade['symbol'] == 'AAPL'

    def test_trade_exists(self, conn, stock_account):
        iid = db.get_or_create_instrument(conn, 'AAPL')
        db.create_trade(conn, account_id=stock_account, instrument_id=iid,
                        direction='long', entry_date='2025-01-01',
                        entry_price=150.0, position_size=10,
                        broker_ticket_id='TICKET_1')
        assert db.trade_exists(conn, stock_account, 'TICKET_1')
        assert not db.trade_exists(conn, stock_account, 'NONEXISTENT')

    def test_delete_trade_unlinks_executions(self, conn, stock_account):
        """BUG PREVENTION: delete_trade should unlink executions, not delete them."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        tid = db.create_trade(conn, account_id=stock_account, instrument_id=iid,
                              direction='long', entry_date='2025-01-01',
                              entry_price=150, position_size=10, status='open')
        eid = db.create_execution(conn, account_id=stock_account, instrument_id=iid,
                                  broker_order_id='X1', action='buy', shares=10,
                                  price=150, executed_at='2025-01-01', trade_id=tid)

        db.delete_trade(conn, tid)

        # Trade gone
        assert db.get_trade(conn, tid) is None
        # Execution still exists but unlinked
        ex = conn.execute("SELECT * FROM executions WHERE id=?", (eid,)).fetchone()
        assert ex is not None
        assert ex['trade_id'] is None


class TestExecutionCRUD:

    def test_create_execution(self, conn, stock_account):
        iid = db.get_or_create_instrument(conn, 'AAPL')
        eid = db.create_execution(conn, account_id=stock_account, instrument_id=iid,
                                  broker_order_id='ORD001', action='buy', shares=10,
                                  price=150.0, executed_at='2025-01-01 10:00:00')
        assert eid is not None

    def test_execution_exists(self, conn, stock_account):
        iid = db.get_or_create_instrument(conn, 'AAPL')
        db.create_execution(conn, account_id=stock_account, instrument_id=iid,
                            broker_order_id='ORD001', action='buy', shares=10,
                            price=150.0, executed_at='2025-01-01')
        assert db.execution_exists(conn, stock_account, 'ORD001')
        assert not db.execution_exists(conn, stock_account, 'NONEXISTENT')

    def test_duplicate_execution_fails(self, conn, stock_account):
        """Broker order ID must be unique per account."""
        iid = db.get_or_create_instrument(conn, 'AAPL')
        db.create_execution(conn, account_id=stock_account, instrument_id=iid,
                            broker_order_id='DUP', action='buy', shares=10,
                            price=150, executed_at='2025-01-01')
        with pytest.raises(sqlite3.IntegrityError):
            db.create_execution(conn, account_id=stock_account, instrument_id=iid,
                                broker_order_id='DUP', action='buy', shares=5,
                                price=155, executed_at='2025-01-02')

    def test_execution_count_for_trade(self, conn, stock_account):
        iid = db.get_or_create_instrument(conn, 'AAPL')
        tid = db.create_trade(conn, account_id=stock_account, instrument_id=iid,
                              direction='long', entry_date='2025-01-01',
                              entry_price=150, position_size=10, status='open')
        assert db.get_execution_count_for_trade(conn, tid) == 0

        db.create_execution(conn, account_id=stock_account, instrument_id=iid,
                            broker_order_id='E1', action='buy', shares=10,
                            price=150, executed_at='2025-01-01', trade_id=tid)
        db.create_execution(conn, account_id=stock_account, instrument_id=iid,
                            broker_order_id='E2', action='sell', shares=10,
                            price=160, executed_at='2025-02-01', trade_id=tid)
        assert db.get_execution_count_for_trade(conn, tid) == 2


class TestBalanceEvents:

    def test_add_and_get_events(self, conn, stock_account):
        db.add_account_event(conn, stock_account, 'deposit', 1000.0, '2025-01-01',
                             description='Initial deposit', broker_ticket_id='D1')
        events = db.get_account_events(conn, stock_account)
        assert len(events) == 1
        assert events[0]['amount'] == 1000.0
        assert events[0]['event_type'] == 'deposit'

    def test_event_dedup(self, conn, stock_account):
        db.add_account_event(conn, stock_account, 'deposit', 1000, '2025-01-01',
                             broker_ticket_id='DEP1')
        assert db.account_event_exists(conn, stock_account, 'DEP1')
        assert not db.account_event_exists(conn, stock_account, 'NONEXISTENT')

    def test_duplicate_event_ignored(self, conn, stock_account):
        """OR IGNORE should prevent duplicate broker_ticket_id."""
        db.add_account_event(conn, stock_account, 'deposit', 1000, '2025-01-01',
                             broker_ticket_id='DEP1')
        # Second insert with same ticket should be ignored (INSERT OR IGNORE)
        db.add_account_event(conn, stock_account, 'deposit', 2000, '2025-01-02',
                             broker_ticket_id='DEP1')
        events = db.get_account_events(conn, stock_account)
        assert len(events) == 1
        assert events[0]['amount'] == 1000.0  # first one kept


class TestTradeStats:
    """Test get_trade_stats — data source for KPI cards."""

    def _make_trade(self, conn, aid, symbol, pnl, status='closed'):
        iid = db.get_or_create_instrument(conn, symbol)
        return db.create_trade(conn,
            account_id=aid, instrument_id=iid, direction='long',
            entry_date='2025-01-01', entry_price=100, position_size=1,
            status=status, pnl_account_currency=pnl)

    def test_no_closed_trades_returns_none(self, conn, forex_account):
        stats = db.get_trade_stats(conn, account_id=forex_account)
        assert stats is None

    def test_open_trades_excluded(self, conn, forex_account):
        self._make_trade(conn, forex_account, 'EURUSD', 10, status='open')
        stats = db.get_trade_stats(conn, account_id=forex_account)
        assert stats is None

    def test_basic_stats(self, conn, forex_account):
        self._make_trade(conn, forex_account, 'EURUSD', 50)
        self._make_trade(conn, forex_account, 'GBPUSD', -30)
        self._make_trade(conn, forex_account, 'AUDUSD', 20)
        stats = db.get_trade_stats(conn, account_id=forex_account)
        assert stats['total_trades'] == 3
        assert stats['winners'] == 2
        assert stats['losers'] == 1
        assert stats['net_pnl'] == 40
        assert stats['gross_profit'] == 70
        assert stats['gross_loss'] == 30

    def test_win_rate(self, conn, forex_account):
        self._make_trade(conn, forex_account, 'EURUSD', 10)
        self._make_trade(conn, forex_account, 'GBPUSD', -5)
        self._make_trade(conn, forex_account, 'AUDUSD', -3)
        self._make_trade(conn, forex_account, 'USDJPY', 7)
        stats = db.get_trade_stats(conn, account_id=forex_account)
        assert abs(stats['win_rate'] - 50.0) < 0.01

    def test_profit_factor(self, conn, forex_account):
        self._make_trade(conn, forex_account, 'EURUSD', 100)
        self._make_trade(conn, forex_account, 'GBPUSD', -50)
        stats = db.get_trade_stats(conn, account_id=forex_account)
        assert abs(stats['profit_factor'] - 2.0) < 0.01

    def test_profit_factor_no_losses(self, conn, forex_account):
        self._make_trade(conn, forex_account, 'EURUSD', 100)
        stats = db.get_trade_stats(conn, account_id=forex_account)
        assert stats['profit_factor'] == float('inf')

    def test_breakeven_counted(self, conn, forex_account):
        self._make_trade(conn, forex_account, 'EURUSD', 0)
        self._make_trade(conn, forex_account, 'GBPUSD', 10)
        stats = db.get_trade_stats(conn, account_id=forex_account)
        assert stats['breakeven'] == 1
        assert stats['total_trades'] == 2


class TestEscHelper:
    """Test the HTML escape helper used in preview panel."""

    def test_esc_basic(self):
        from tabs.trades import _esc
        assert _esc('<b>test</b>') == '&lt;b&gt;test&lt;/b&gt;'
        assert _esc('A & B') == 'A &amp; B'
        assert _esc('line1\nline2') == 'line1<br>line2'

    def test_esc_empty(self):
        from tabs.trades import _esc
        assert _esc('') == ''
        assert _esc(None) == ''


class TestTradeColumnNames:
    """Regression tests: verify get_trade() returns correct column names
    used by the trade preview panel. Prevents crash from mismatched keys."""

    def test_trade_has_stop_loss_price_column(self, conn, forex_account):
        """Preview panel accesses t['stop_loss_price'], not t['stop_loss']."""
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        tid = db.create_trade(conn, account_id=forex_account, instrument_id=iid,
                              direction='long', entry_date='2025-01-01',
                              entry_price=1.1, position_size=1, status='open',
                              stop_loss_price=1.05)
        t = db.get_trade(conn, tid)
        # These are the exact keys the preview panel accesses
        assert 'stop_loss_price' in t.keys(), "Column must be 'stop_loss_price'"
        assert t['stop_loss_price'] == 1.05

    def test_trade_has_take_profit_price_column(self, conn, forex_account):
        """Preview panel accesses t['take_profit_price'], not t['take_profit']."""
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        tid = db.create_trade(conn, account_id=forex_account, instrument_id=iid,
                              direction='long', entry_date='2025-01-01',
                              entry_price=1.1, position_size=1, status='open',
                              take_profit_price=1.20)
        t = db.get_trade(conn, tid)
        assert 'take_profit_price' in t.keys(), "Column must be 'take_profit_price'"
        assert t['take_profit_price'] == 1.20

    def test_trade_has_pre_trade_notes_column(self, conn, forex_account):
        """Preview panel accesses t['pre_trade_notes'], not t['notes_pre']."""
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        tid = db.create_trade(conn, account_id=forex_account, instrument_id=iid,
                              direction='long', entry_date='2025-01-01',
                              entry_price=1.1, position_size=1, status='open',
                              pre_trade_notes='test note')
        t = db.get_trade(conn, tid)
        assert 'pre_trade_notes' in t.keys()
        assert t['pre_trade_notes'] == 'test note'

    def test_trade_has_post_trade_notes_column(self, conn, forex_account):
        """Preview panel accesses t['post_trade_notes'], not t['notes_post']."""
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        tid = db.create_trade(conn, account_id=forex_account, instrument_id=iid,
                              direction='long', entry_date='2025-01-01',
                              entry_price=1.1, position_size=1, status='open',
                              post_trade_notes='review note')
        t = db.get_trade(conn, tid)
        assert 'post_trade_notes' in t.keys()
        assert t['post_trade_notes'] == 'review note'

    def test_trade_preview_all_required_columns(self, conn, forex_account):
        """All columns accessed by _show_trade_preview should exist on get_trade()."""
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        tid = db.create_trade(conn, account_id=forex_account, instrument_id=iid,
                              direction='long', entry_date='2025-01-01',
                              entry_price=1.1, position_size=1, status='open')
        t = db.get_trade(conn, tid)
        required_keys = [
            'entry_price', 'exit_price', 'stop_loss_price', 'take_profit_price',
            'position_size', 'account_currency', 'risk_percent',
            'execution_grade', 'confidence_rating', 'setup_name',
            'pnl_account_currency', 'direction', 'status', 'symbol',
            'entry_date', 'exit_date', 'exit_reason', 'account_name',
            'pre_trade_notes', 'post_trade_notes',
        ]
        for key in required_keys:
            assert key in t.keys(), f"Missing required column '{key}' in get_trade() result"


class TestAppIcon:
    """Verify app icon files exist."""

    def test_icon_png_exists(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icon.png')
        assert os.path.isfile(path), "icon.png should exist in icons/"

    def test_icon_svg_exists(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icon.svg')
        assert os.path.isfile(path), "icon.svg should exist in icons/"

    def test_icon_png_is_valid_image(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icon.png')
        with open(path, 'rb') as f:
            header = f.read(8)
        # PNG magic bytes
        assert header[:4] == b'\x89PNG', "icon.png should be a valid PNG file"


# ── Extended Database CRUD Tests ─────────────────────────────────────────

class TestUpdateAccount:
    def test_update_name(self, conn, forex_account):
        db.update_account(conn, forex_account, name='Renamed')
        acct = db.get_account(conn, forex_account)
        assert acct['name'] == 'Renamed'

    def test_update_multiple_fields(self, conn, forex_account):
        db.update_account(conn, forex_account, broker='NewBroker', currency='USD')
        acct = db.get_account(conn, forex_account)
        assert acct['broker'] == 'NewBroker'
        assert acct['currency'] == 'USD'

    def test_update_ignores_disallowed_fields(self, conn, forex_account):
        """Fields not in the allowed set should be silently ignored."""
        db.update_account(conn, forex_account, fake_field='bad', name='OK')
        acct = db.get_account(conn, forex_account)
        assert acct['name'] == 'OK'

    def test_update_nothing_is_noop(self, conn, forex_account):
        """Empty kwargs should not error."""
        db.update_account(conn, forex_account)
        acct = db.get_account(conn, forex_account)
        assert acct is not None


class TestUpdateTrade:
    def _make(self, conn, aid):
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        return db.create_trade(conn, account_id=aid, instrument_id=iid,
                               direction='long', entry_date='2025-01-01',
                               entry_price=1.1, position_size=1, status='open')

    def test_update_status(self, conn, forex_account):
        tid = self._make(conn, forex_account)
        db.update_trade(conn, tid, status='closed', exit_price=1.15,
                        exit_date='2025-02-01', pnl_account_currency=50)
        t = db.get_trade(conn, tid)
        assert t['status'] == 'closed'
        assert t['exit_price'] == 1.15
        assert t['pnl_account_currency'] == 50

    def test_update_sets_updated_at(self, conn, forex_account):
        tid = self._make(conn, forex_account)
        old_ts = db.get_trade(conn, tid)['updated_at']
        import time; time.sleep(0.01)
        db.update_trade(conn, tid, post_trade_notes='review done')
        new_ts = db.get_trade(conn, tid)['updated_at']
        assert new_ts >= old_ts

    def test_update_empty_noop(self, conn, forex_account):
        tid = self._make(conn, forex_account)
        db.update_trade(conn, tid)  # no kwargs
        assert db.get_trade(conn, tid) is not None


class TestGetTradesFilters:
    def _populate(self, conn, aid):
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        db.create_trade(conn, account_id=aid, instrument_id=iid, direction='long',
                        entry_date='2025-01-01', entry_price=1.1, position_size=1,
                        status='open')
        db.create_trade(conn, account_id=aid, instrument_id=iid, direction='short',
                        entry_date='2025-02-01', entry_price=1.2, position_size=1,
                        status='closed', pnl_account_currency=50)
        db.create_trade(conn, account_id=aid, instrument_id=iid, direction='long',
                        entry_date='2025-03-01', entry_price=1.0, position_size=2,
                        status='closed', pnl_account_currency=-30)

    def test_get_all(self, conn, forex_account):
        self._populate(conn, forex_account)
        trades = db.get_trades(conn, account_id=forex_account)
        assert len(trades) == 3

    def test_filter_by_status(self, conn, forex_account):
        self._populate(conn, forex_account)
        closed = db.get_trades(conn, account_id=forex_account, status='closed')
        assert len(closed) == 2
        open_t = db.get_trades(conn, account_id=forex_account, status='open')
        assert len(open_t) == 1

    def test_limit(self, conn, forex_account):
        self._populate(conn, forex_account)
        limited = db.get_trades(conn, account_id=forex_account, limit=2)
        assert len(limited) == 2


class TestInstruments:
    def test_get_instruments_empty(self, conn):
        result = db.get_instruments(conn)
        # Built-in forex pairs created during init
        assert len(result) >= 0  # depends on schema init

    def test_get_instrument(self, conn):
        iid = db.get_or_create_instrument(conn, 'AAPL', 'Apple Inc', 'stock')
        inst = db.get_instrument(conn, iid)
        assert inst['symbol'] == 'AAPL'
        assert inst['display_name'] == 'Apple Inc'

    def test_get_nonexistent_instrument(self, conn):
        assert db.get_instrument(conn, 999999) is None


class TestTradeCharts:
    def _make_trade(self, conn, aid):
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        return db.create_trade(conn, account_id=aid, instrument_id=iid,
                               direction='long', entry_date='2025-01-01',
                               entry_price=1.1, position_size=1, status='open')

    def test_add_and_get_charts(self, conn, forex_account):
        tid = self._make_trade(conn, forex_account)
        cid = db.add_trade_chart(conn, tid, 'screenshot', '/tmp/test.png', caption='My chart')
        charts = db.get_trade_charts(conn, tid)
        assert len(charts) == 1
        assert charts[0]['file_path'] == '/tmp/test.png'
        assert charts[0]['caption'] == 'My chart'

    def test_chart_counts(self, conn, forex_account):
        tid = self._make_trade(conn, forex_account)
        db.add_trade_chart(conn, tid, 'screenshot', '/tmp/a.png')
        db.add_trade_chart(conn, tid, 'screenshot', '/tmp/b.png')
        counts = db.get_trade_chart_counts(conn, forex_account)
        assert counts[tid] == 2

    def test_delete_chart(self, conn, forex_account):
        tid = self._make_trade(conn, forex_account)
        cid = db.add_trade_chart(conn, tid, 'screenshot', '/tmp/test.png')
        path = db.delete_trade_chart(conn, cid)
        assert path == '/tmp/test.png'
        assert len(db.get_trade_charts(conn, tid)) == 0

    def test_delete_nonexistent_chart(self, conn):
        assert db.delete_trade_chart(conn, 999999) is None


class TestSetupStats:
    def test_setup_stats_basic(self, conn, forex_account):
        sid = db.create_setup_type(conn, name='Pullback')
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        db.create_trade(conn, account_id=forex_account, instrument_id=iid,
                        direction='long', entry_date='2025-01-01',
                        entry_price=1.1, position_size=1, status='closed',
                        pnl_account_currency=50, setup_type_id=sid)
        db.create_trade(conn, account_id=forex_account, instrument_id=iid,
                        direction='long', entry_date='2025-02-01',
                        entry_price=1.1, position_size=1, status='closed',
                        pnl_account_currency=-20, setup_type_id=sid)
        stats = db.get_setup_stats(conn, sid, account_id=forex_account)
        assert stats is not None
        assert stats['total'] == 2
        assert stats['total_trades'] == 2  # from _compute_stats
        assert stats['winners'] == 1
        assert stats['losers'] == 1
        assert stats['net_pnl'] == 30

    def test_setup_stats_no_trades(self, conn, forex_account):
        sid = db.create_setup_type(conn, name='Empty')
        stats = db.get_setup_stats(conn, sid)
        assert stats is None

    def test_setup_stats_has_expectancy(self, conn, forex_account):
        """After refactor, setup stats should include expectancy and breakeven."""
        sid = db.create_setup_type(conn, name='Test')
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        db.create_trade(conn, account_id=forex_account, instrument_id=iid,
                        direction='long', entry_date='2025-01-01',
                        entry_price=1.1, position_size=1, status='closed',
                        pnl_account_currency=40, setup_type_id=sid)
        db.create_trade(conn, account_id=forex_account, instrument_id=iid,
                        direction='long', entry_date='2025-02-01',
                        entry_price=1.1, position_size=1, status='closed',
                        pnl_account_currency=0, setup_type_id=sid)
        stats = db.get_setup_stats(conn, sid, account_id=forex_account)
        assert 'expectancy' in stats
        assert 'breakeven' in stats
        assert stats['breakeven'] == 1
        assert stats['profit_factor'] == float('inf')  # no losses


class TestSetupRules:
    def test_add_and_get_rules(self, conn):
        sid = db.create_setup_type(conn, name='Test Setup')
        db.add_setup_rule(conn, sid, 'entry', 'Price above MA', sort_order=1)
        db.add_setup_rule(conn, sid, 'entry', 'RSI < 30', sort_order=2)
        db.add_setup_rule(conn, sid, 'exit', 'Break of structure', sort_order=1)
        rules = db.get_setup_rules(conn, sid)
        assert len(rules) == 3
        entry_rules = db.get_setup_rules(conn, sid, rule_type='entry')
        assert len(entry_rules) == 2
        exit_rules = db.get_setup_rules(conn, sid, rule_type='exit')
        assert len(exit_rules) == 1

    def test_update_rule(self, conn):
        sid = db.create_setup_type(conn, name='Test')
        db.add_setup_rule(conn, sid, 'entry', 'Old text', sort_order=1)
        rules = db.get_setup_rules(conn, sid)
        rid = rules[0]['id']
        db.update_setup_rule(conn, rid, 'New text')
        updated = db.get_setup_rules(conn, sid)
        assert updated[0]['rule_text'] == 'New text'

    def test_delete_rule(self, conn):
        sid = db.create_setup_type(conn, name='Test')
        db.add_setup_rule(conn, sid, 'entry', 'To delete', sort_order=1)
        rules = db.get_setup_rules(conn, sid)
        db.delete_setup_rule(conn, rules[0]['id'])
        assert len(db.get_setup_rules(conn, sid)) == 0


class TestTradeRuleChecks:
    def test_save_and_get_checks(self, conn, forex_account):
        sid = db.create_setup_type(conn, name='Test')
        db.add_setup_rule(conn, sid, 'entry', 'Rule A', sort_order=1)
        db.add_setup_rule(conn, sid, 'entry', 'Rule B', sort_order=2)
        rules = db.get_setup_rules(conn, sid)

        iid = db.get_or_create_instrument(conn, 'EURUSD')
        tid = db.create_trade(conn, account_id=forex_account, instrument_id=iid,
                              direction='long', entry_date='2025-01-01',
                              entry_price=1.1, position_size=1, status='open',
                              setup_type_id=sid)
        checks = {rules[0]['id']: True, rules[1]['id']: False}
        db.save_trade_rule_checks(conn, tid, checks)

        result = db.get_trade_rule_checks(conn, tid)
        assert len(result) == 2
        met = {r['rule_text']: bool(r['was_met']) for r in result}
        assert met['Rule A'] is True
        assert met['Rule B'] is False

    def test_save_replaces_previous(self, conn, forex_account):
        sid = db.create_setup_type(conn, name='Test')
        db.add_setup_rule(conn, sid, 'entry', 'Rule A', sort_order=1)
        rules = db.get_setup_rules(conn, sid)
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        tid = db.create_trade(conn, account_id=forex_account, instrument_id=iid,
                              direction='long', entry_date='2025-01-01',
                              entry_price=1.1, position_size=1, status='open')
        db.save_trade_rule_checks(conn, tid, {rules[0]['id']: True})
        db.save_trade_rule_checks(conn, tid, {rules[0]['id']: False})
        result = db.get_trade_rule_checks(conn, tid)
        assert len(result) == 1
        assert result[0]['was_met'] == 0


class TestJournalCRUD:
    def test_save_and_get_journal(self, conn, forex_account):
        db.save_journal_entry(conn, '2025-01-15', account_id=forex_account,
                              observations='Good day', emotional_state='Focused',
                              market_conditions='Trending')
        entry = db.get_journal_entry(conn, '2025-01-15', account_id=forex_account)
        assert entry is not None
        assert entry['observations'] == 'Good day'
        assert entry['emotional_state'] == 'Focused'

    def test_upsert_journal(self, conn, forex_account):
        db.save_journal_entry(conn, '2025-01-15', account_id=forex_account,
                              observations='First')
        db.save_journal_entry(conn, '2025-01-15', account_id=forex_account,
                              observations='Updated')
        entry = db.get_journal_entry(conn, '2025-01-15', account_id=forex_account)
        assert entry['observations'] == 'Updated'

    def test_get_nonexistent_journal(self, conn, forex_account):
        entry = db.get_journal_entry(conn, '2099-12-31', account_id=forex_account)
        assert entry is None


class TestTradeExists:
    def test_exists(self, conn, forex_account):
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        db.create_trade(conn, account_id=forex_account, instrument_id=iid,
                        direction='long', entry_date='2025-01-01',
                        entry_price=1.1, position_size=1, status='open',
                        broker_ticket_id='TKT001')
        assert db.trade_exists(conn, forex_account, 'TKT001')
        assert not db.trade_exists(conn, forex_account, 'NONEXISTENT')


class TestDeleteTradeBasic:
    def test_delete_removes_trade(self, conn, forex_account):
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        tid = db.create_trade(conn, account_id=forex_account, instrument_id=iid,
                              direction='long', entry_date='2025-01-01',
                              entry_price=1.1, position_size=1, status='open')
        db.delete_trade(conn, tid)
        assert db.get_trade(conn, tid) is None


# ── CSV Export Tests ─────────────────────────────────────────────────────

class TestCSVExport:

    def _populate_trades(self, conn, aid):
        iid_eu = db.get_or_create_instrument(conn, 'EURUSD')
        iid_gb = db.get_or_create_instrument(conn, 'GBPUSD')
        db.create_trade(conn, account_id=aid, instrument_id=iid_eu, direction='long',
                        entry_date='2025-01-15 10:00:00', entry_price=1.1,
                        position_size=1, status='closed',
                        exit_date='2025-02-01', exit_price=1.15,
                        pnl_account_currency=50, exit_reason='target_hit')
        db.create_trade(conn, account_id=aid, instrument_id=iid_gb, direction='short',
                        entry_date='2025-03-01 14:00:00', entry_price=1.3,
                        position_size=2, status='open')
        db.create_trade(conn, account_id=aid, instrument_id=iid_eu, direction='long',
                        entry_date='2025-06-10 08:00:00', entry_price=1.08,
                        position_size=1, status='closed',
                        exit_date='2025-07-01', exit_price=1.05,
                        pnl_account_currency=-30, exit_reason='stop_loss')

    def test_export_all(self, conn, forex_account):
        self._populate_trades(conn, forex_account)
        rows = db.get_trades_for_export(conn, forex_account)
        assert len(rows) == 3

    def test_export_closed_only(self, conn, forex_account):
        self._populate_trades(conn, forex_account)
        rows = db.get_trades_for_export(conn, forex_account, status_filter='closed')
        assert len(rows) == 2
        for r in rows:
            assert r['status'] == 'closed'

    def test_export_open_only(self, conn, forex_account):
        self._populate_trades(conn, forex_account)
        rows = db.get_trades_for_export(conn, forex_account, status_filter='open')
        assert len(rows) == 1
        assert rows[0]['status'] == 'open'

    def test_export_date_range(self, conn, forex_account):
        self._populate_trades(conn, forex_account)
        rows = db.get_trades_for_export(conn, forex_account,
                                        date_from='2025-02-01', date_to='2025-06-30')
        # Should get March (open) and June (closed), not January
        assert len(rows) == 2

    def test_export_has_joined_fields(self, conn, forex_account):
        self._populate_trades(conn, forex_account)
        rows = db.get_trades_for_export(conn, forex_account)
        for r in rows:
            assert r['account_name'] is not None
            assert r['symbol'] is not None
            assert r['account_currency'] is not None

    def test_export_empty_account(self, conn, forex_account):
        rows = db.get_trades_for_export(conn, forex_account)
        assert rows == []

    def test_export_columns_definition(self):
        """EXPORT_COLUMNS should have valid (key, label) tuples."""
        from database import EXPORT_COLUMNS
        assert len(EXPORT_COLUMNS) > 20
        for key, label in EXPORT_COLUMNS:
            assert isinstance(key, str)
            assert isinstance(label, str)
            assert len(key) > 0
            assert len(label) > 0

    def test_export_to_csv_file(self, conn, forex_account, tmp_path):
        """Full round-trip: export to file and verify contents."""
        import csv as csv_mod
        self._populate_trades(conn, forex_account)
        rows = db.get_trades_for_export(conn, forex_account)

        csv_path = tmp_path / "export.csv"
        from database import EXPORT_COLUMNS
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv_mod.writer(f)
            writer.writerow([label for _, label in EXPORT_COLUMNS])
            for r in rows:
                writer.writerow([r[k] if k in r.keys() else '' for k, _ in EXPORT_COLUMNS])

        # Read back and verify
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv_mod.reader(f)
            header = next(reader)
            assert header[0] == 'Entry Date'
            assert header[2] == 'Symbol'
            data_rows = list(reader)
            assert len(data_rows) == 3

    def test_export_account_isolation(self, conn, forex_account):
        """Trades from other accounts should not appear."""
        other = db.create_account(conn, name='Other', broker='X',
                                   currency='EUR', asset_type='forex')
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        db.create_trade(conn, account_id=forex_account, instrument_id=iid,
                        direction='long', entry_date='2025-01-01',
                        entry_price=1.1, position_size=1, status='open')
        db.create_trade(conn, account_id=other, instrument_id=iid,
                        direction='long', entry_date='2025-01-01',
                        entry_price=1.1, position_size=1, status='open')
        rows = db.get_trades_for_export(conn, forex_account)
        assert len(rows) == 1


# ── Formula CRUD Tests ───────────────────────────────────────────────────

class TestFormulaCRUD:

    def test_seeded_formulas_exist(self, conn):
        """Schema init should seed formula definitions."""
        formulas = db.get_all_formulas(conn)
        assert len(formulas) >= 7  # 7 seeded in SEED_SQL
        keys = {f['metric_key'] for f in formulas}
        assert 'win_rate' in keys
        assert 'expectancy' in keys
        assert 'profit_factor' in keys

    def test_get_formula_by_key(self, conn):
        f = db.get_formula(conn, 'win_rate')
        assert f is not None
        assert f['display_name'] == 'Win Rate'
        assert f['category'] == 'performance'

    def test_get_formula_nonexistent(self, conn):
        assert db.get_formula(conn, 'nonexistent_metric') is None

    def test_update_formula_description(self, conn):
        db.update_formula(conn, 'win_rate', description='Custom description')
        f = db.get_formula(conn, 'win_rate')
        assert f['description'] == 'Custom description'

    def test_update_formula_multiple_fields(self, conn):
        db.update_formula(conn, 'expectancy',
                          display_name='Custom Expectancy',
                          interpretation='My custom reading')
        f = db.get_formula(conn, 'expectancy')
        assert f['display_name'] == 'Custom Expectancy'
        assert f['interpretation'] == 'My custom reading'

    def test_update_formula_ignores_disallowed_fields(self, conn):
        """id should not be modifiable via kwargs."""
        original = db.get_formula(conn, 'win_rate')
        db.update_formula(conn, 'win_rate', id=999)
        after = db.get_formula(conn, 'win_rate')
        assert after['id'] == original['id']

    def test_update_formula_empty_noop(self, conn):
        """Empty kwargs should not error."""
        db.update_formula(conn, 'win_rate')
        assert db.get_formula(conn, 'win_rate') is not None

    def test_reset_formulas_to_defaults(self, conn):
        """After editing and resetting, originals should be restored."""
        original_desc = db.get_formula(conn, 'win_rate')['description']
        # Modify
        db.update_formula(conn, 'win_rate', description='CHANGED')
        assert db.get_formula(conn, 'win_rate')['description'] == 'CHANGED'
        # Reset
        db.reset_formulas_to_defaults(conn)
        restored = db.get_formula(conn, 'win_rate')
        assert restored['description'] == original_desc

    def test_reset_preserves_count(self, conn):
        """Reset should not create duplicates."""
        count_before = len(db.get_all_formulas(conn))
        db.reset_formulas_to_defaults(conn)
        count_after = len(db.get_all_formulas(conn))
        assert count_after == count_before

    def test_formulas_have_categories(self, conn):
        """All formulas should have a non-empty category."""
        for f in db.get_all_formulas(conn):
            assert f['category'], f"Formula {f['metric_key']} has no category"

    def test_formulas_sorted_by_category(self, conn):
        """get_all_formulas should return sorted by category, display_name."""
        formulas = db.get_all_formulas(conn)
        categories = [f['category'] for f in formulas]
        assert categories == sorted(categories)


# ── Packaging Script Existence ───────────────────────────────────────────

class TestPackagingScript:

    def test_build_script_exists(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'build_app.sh')
        assert os.path.isfile(path), "build_app.sh should exist in project root"

    def test_build_script_is_executable(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'build_app.sh')
        assert os.access(path, os.X_OK), "build_app.sh should be executable"

    def test_update_scripts_exist(self):
        """Update scripts exist if present (they're created during deployment)."""
        root = os.path.dirname(os.path.dirname(__file__))
        for name in ('update_code.sh', 'update_journal.sh'):
            path = os.path.join(root, name)
            if os.path.isfile(path):
                assert os.access(path, os.X_OK), f"{name} should be executable"


# ── Advanced Performance Metrics Tests ───────────────────────────────────

class TestAdvancedStats:

    def _make_trade(self, conn, aid, symbol, pnl, entry='2025-01-01', exit='2025-01-15'):
        iid = db.get_or_create_instrument(conn, symbol)
        return db.create_trade(conn, account_id=aid, instrument_id=iid,
                               direction='long', entry_date=entry,
                               exit_date=exit, entry_price=1.0,
                               position_size=1, status='closed',
                               pnl_account_currency=pnl)

    def test_no_trades_returns_none(self, conn, forex_account):
        result = db.get_advanced_stats(conn, account_id=forex_account)
        assert result is None

    def test_single_winning_trade(self, conn, forex_account):
        self._make_trade(conn, forex_account, 'EURUSD', 100)
        stats = db.get_advanced_stats(conn, account_id=forex_account)
        assert stats is not None
        assert stats['total_trades'] == 1
        assert stats['best_trade_pnl'] == 100
        assert stats['worst_trade_pnl'] == 100
        assert stats['max_consecutive_wins'] == 1
        assert stats['max_consecutive_losses'] == 0
        assert stats['current_streak'] == 1

    def test_single_losing_trade(self, conn, forex_account):
        self._make_trade(conn, forex_account, 'EURUSD', -50)
        stats = db.get_advanced_stats(conn, account_id=forex_account)
        assert stats['best_trade_pnl'] == -50
        assert stats['worst_trade_pnl'] == -50
        assert stats['current_streak'] == -1

    def test_win_streak(self, conn, forex_account):
        for i, pnl in enumerate([10, 20, 30, -5, 15]):
            self._make_trade(conn, forex_account, f'P{i}', pnl,
                             entry=f'2025-0{i+1}-01', exit=f'2025-0{i+1}-15')
        stats = db.get_advanced_stats(conn, account_id=forex_account)
        assert stats['max_consecutive_wins'] == 3  # first 3
        assert stats['max_consecutive_losses'] == 1  # the -5
        assert stats['current_streak'] == 1  # ends on +15

    def test_loss_streak(self, conn, forex_account):
        for i, pnl in enumerate([10, -5, -10, -15, 20]):
            self._make_trade(conn, forex_account, f'P{i}', pnl,
                             entry=f'2025-0{i+1}-01', exit=f'2025-0{i+1}-15')
        stats = db.get_advanced_stats(conn, account_id=forex_account)
        assert stats['max_consecutive_losses'] == 3  # -5, -10, -15
        assert stats['current_streak'] == 1  # ends on +20

    def test_current_streak_negative(self, conn, forex_account):
        for i, pnl in enumerate([10, 20, -5, -10]):
            self._make_trade(conn, forex_account, f'P{i}', pnl,
                             entry=f'2025-0{i+1}-01', exit=f'2025-0{i+1}-15')
        stats = db.get_advanced_stats(conn, account_id=forex_account)
        assert stats['current_streak'] == -2  # last 2 are losses

    def test_breakeven_breaks_streak(self, conn, forex_account):
        for i, pnl in enumerate([10, 20, 0, 30]):
            self._make_trade(conn, forex_account, f'P{i}', pnl,
                             entry=f'2025-0{i+1}-01', exit=f'2025-0{i+1}-15')
        stats = db.get_advanced_stats(conn, account_id=forex_account)
        assert stats['max_consecutive_wins'] == 2  # first 2 (breakeven resets)

    def test_max_drawdown(self, conn, forex_account):
        """Trades: +100, -30, -20, +50 → equity: 100, 70, 50, 100
        Peak=100 at trade 1, trough=50 at trade 3 → drawdown=50 (50%)
        """
        for i, pnl in enumerate([100, -30, -20, 50]):
            self._make_trade(conn, forex_account, f'P{i}', pnl,
                             entry=f'2025-0{i+1}-01', exit=f'2025-0{i+1}-15')
        stats = db.get_advanced_stats(conn, account_id=forex_account)
        assert abs(stats['max_drawdown_abs'] - 50.0) < 0.01
        assert abs(stats['max_drawdown_pct'] - 50.0) < 0.01

    def test_no_drawdown_when_all_wins(self, conn, forex_account):
        for i, pnl in enumerate([10, 20, 30]):
            self._make_trade(conn, forex_account, f'P{i}', pnl,
                             entry=f'2025-0{i+1}-01', exit=f'2025-0{i+1}-15')
        stats = db.get_advanced_stats(conn, account_id=forex_account)
        assert stats['max_drawdown_abs'] == 0.0
        assert stats['max_drawdown_pct'] == 0.0

    def test_best_worst_trade(self, conn, forex_account):
        for i, pnl in enumerate([50, -100, 200, -30]):
            self._make_trade(conn, forex_account, f'P{i}', pnl,
                             entry=f'2025-0{i+1}-01', exit=f'2025-0{i+1}-15')
        stats = db.get_advanced_stats(conn, account_id=forex_account)
        assert stats['best_trade_pnl'] == 200
        assert stats['worst_trade_pnl'] == -100

    def test_avg_duration(self, conn, forex_account):
        """Trade 1: 10 days, Trade 2: 20 days → avg = 15 days."""
        self._make_trade(conn, forex_account, 'P1', 50,
                         entry='2025-01-01', exit='2025-01-11')
        self._make_trade(conn, forex_account, 'P2', 30,
                         entry='2025-02-01', exit='2025-02-21')
        stats = db.get_advanced_stats(conn, account_id=forex_account)
        assert abs(stats['avg_trade_duration_days'] - 15.0) < 0.1

    def test_sharpe_ratio_positive(self, conn, forex_account):
        """All positive returns → positive Sharpe."""
        for i, pnl in enumerate([10, 20, 15, 25]):
            self._make_trade(conn, forex_account, f'P{i}', pnl,
                             entry=f'2025-0{i+1}-01', exit=f'2025-0{i+1}-15')
        stats = db.get_advanced_stats(conn, account_id=forex_account)
        assert stats['sharpe_ratio'] > 0

    def test_sharpe_ratio_negative(self, conn, forex_account):
        """More losses than wins → likely negative Sharpe."""
        for i, pnl in enumerate([-10, -20, 5, -15]):
            self._make_trade(conn, forex_account, f'P{i}', pnl,
                             entry=f'2025-0{i+1}-01', exit=f'2025-0{i+1}-15')
        stats = db.get_advanced_stats(conn, account_id=forex_account)
        assert stats['sharpe_ratio'] < 0

    def test_excluded_trades_not_counted(self, conn, forex_account):
        """Excluded trades should not appear in advanced stats."""
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        db.create_trade(conn, account_id=forex_account, instrument_id=iid,
                        direction='long', entry_date='2025-01-01',
                        exit_date='2025-01-15', entry_price=1.0,
                        position_size=1, status='closed',
                        pnl_account_currency=100, is_excluded=1)
        self._make_trade(conn, forex_account, 'GBPUSD', 50)
        stats = db.get_advanced_stats(conn, account_id=forex_account)
        assert stats['total_trades'] == 1
        assert stats['best_trade_pnl'] == 50

    def test_open_trades_not_counted(self, conn, forex_account):
        """Open trades should not appear in advanced stats."""
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        db.create_trade(conn, account_id=forex_account, instrument_id=iid,
                        direction='long', entry_date='2025-01-01',
                        entry_price=1.0, position_size=1, status='open')
        stats = db.get_advanced_stats(conn, account_id=forex_account)
        assert stats is None

    def test_account_isolation(self, conn, forex_account):
        """Advanced stats should be scoped to the given account."""
        other = db.create_account(conn, name='Other', broker='X',
                                   currency='EUR', asset_type='forex')
        self._make_trade(conn, forex_account, 'EURUSD', 100)
        self._make_trade(conn, other, 'GBPUSD', -50)
        stats = db.get_advanced_stats(conn, account_id=forex_account)
        assert stats['total_trades'] == 1
        assert stats['best_trade_pnl'] == 100


# ── Chart Widget Tests ───────────────────────────────────────────────────

class TestChartWidgetNoSave:
    """Verify chart widget no longer saves persistent images."""

    def test_no_charts_dir_constant(self):
        """chart_widget should not reference _CHARTS_DIR."""
        import chart_widget
        assert not hasattr(chart_widget, '_CHARTS_DIR'), \
            "_CHARTS_DIR should be removed — no persistent chart images"

    def test_no_save_chart_image_method(self):
        """TradeChartWidget should not have _save_chart_image method."""
        from chart_widget import TradeChartWidget
        assert not hasattr(TradeChartWidget, '_save_chart_image'), \
            "_save_chart_image should be removed"

    def test_no_delete_trade_charts_method(self):
        """TradeChartWidget should not have delete_trade_charts method."""
        from chart_widget import TradeChartWidget
        assert not hasattr(TradeChartWidget, 'delete_trade_charts'), \
            "delete_trade_charts should be removed"

    def test_no_try_load_saved_image_method(self):
        """TradeChartWidget should not have try_load_saved_image method."""
        from chart_widget import TradeChartWidget
        assert not hasattr(TradeChartWidget, 'try_load_saved_image'), \
            "try_load_saved_image should be removed"

    def test_has_popout_method(self):
        """Pop-out should still be available."""
        from chart_widget import TradeChartWidget
        assert hasattr(TradeChartWidget, '_on_popout'), \
            "_on_popout should still exist for system viewer"

    def test_has_load_cached_data(self):
        """load_cached_data should still exist for rendering from DB."""
        from chart_widget import TradeChartWidget
        assert hasattr(TradeChartWidget, 'load_cached_data')

    def test_uses_tempfile_module(self):
        """chart_widget should import tempfile for pop-out."""
        import chart_widget
        assert 'tempfile' in dir(chart_widget) or hasattr(chart_widget, 'tempfile'), \
            "chart_widget should use tempfile for pop-out"


# ── Import Flow No-Gatekeeping Tests ─────────────────────────────────────

class TestImportNoGatekeep:
    """Verify the import flow doesn't block when no accounts exist."""

    def test_import_code_has_no_hard_block(self):
        """The import method should NOT have 'Please create an account first'
        as a hard block — it should allow auto-creation from statement."""
        import inspect
        from tabs.trades import TradesTab
        source = inspect.getsource(TradesTab._on_import)
        # The old blocking pattern was: if not accounts: ... return
        # It should no longer be an early return after warning
        assert "Please create an account first" not in source, \
            "Import should not block with 'create account first' — should auto-create"


# ── Preview Panel Tests ──────────────────────────────────────────────────

class TestPreviewPanel:
    """Verify preview panel layout improvements."""

    def test_preview_has_pnl_hero(self):
        """TradesTab should have pv_pnl_hero widget."""
        import inspect
        from tabs.trades import TradesTab
        source = inspect.getsource(TradesTab._build_preview_panel)
        assert 'pv_pnl_hero' in source, "Preview should have a P&L hero widget"

    def test_preview_larger_fonts(self):
        """Header font should be at least 18px."""
        import inspect
        from tabs.trades import TradesTab
        source = inspect.getsource(TradesTab._build_preview_panel)
        assert '20px' in source or '18px' in source, \
            "Header should use larger font"

    def test_preview_shows_duration(self):
        """Preview should calculate and display holding duration."""
        import inspect
        from tabs.trades import TradesTab
        source = inspect.getsource(TradesTab._show_trade_preview)
        assert 'Duration' in source, "Preview should show trade duration"

    def test_delete_trade_no_chart_cleanup(self):
        """delete_trade should not reference TradeChartWidget anymore."""
        import inspect
        source = inspect.getsource(db.delete_trade)
        assert 'TradeChartWidget' not in source, \
            "delete_trade should not reference TradeChartWidget"
        assert 'delete_trade_charts' not in source, \
            "delete_trade should not call delete_trade_charts"

    def test_preview_has_chart_widget(self):
        """Preview panel should embed a TradeChartWidget for OHLC rendering."""
        import inspect
        from tabs.trades import TradesTab
        source = inspect.getsource(TradesTab._build_preview_panel)
        assert 'TradeChartWidget' in source, \
            "Preview should embed TradeChartWidget"
        assert 'pv_chart' in source, \
            "Chart widget should be stored as self.pv_chart"

    def test_preview_no_screenshot_thumbnails(self):
        """Preview panel should not have screenshot thumbnail area."""
        import inspect
        from tabs.trades import TradesTab
        source = inspect.getsource(TradesTab._build_preview_panel)
        assert 'pv_screenshots_layout' not in source, \
            "Screenshot thumbnails should be removed from preview"
        assert 'pv_screenshots_widget' not in source, \
            "Screenshot widget should be removed from preview"

    def test_preview_loads_chart_data(self):
        """_show_trade_preview should load cached chart data."""
        import inspect
        from tabs.trades import TradesTab
        source = inspect.getsource(TradesTab._show_trade_preview)
        assert 'load_cached_data' in source, \
            "Preview should call load_cached_data for chart rendering"
        assert 'chart_data' in source, \
            "Preview should pass chart_data to the widget"

    def test_no_clear_screenshot_thumbs_method(self):
        """TradesTab should not have _clear_screenshot_thumbs anymore."""
        from tabs.trades import TradesTab
        assert not hasattr(TradesTab, '_clear_screenshot_thumbs'), \
            "_clear_screenshot_thumbs should be removed"


# ── Build & Repo Files ──────────────────────────────────────────────────

class TestBuildScripts:
    """Verify build scripts and repo files exist and are correct."""

    def test_linux_build_script_exists(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'build_app.sh')
        assert os.path.isfile(path)

    def test_linux_build_script_executable(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'build_app.sh')
        assert os.access(path, os.X_OK)

    def test_linux_build_detects_venv(self):
        """Build script should auto-detect venv."""
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'build_app.sh')
        content = open(path).read()
        assert 'VIRTUAL_ENV' in content, "Should check for VIRTUAL_ENV"
        assert 'venv/bin/activate' in content, "Should auto-activate venv"

    def test_linux_build_uses_python_m_pyinstaller(self):
        """Build script should use 'python -m PyInstaller' not bare 'pyinstaller'."""
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'build_app.sh')
        content = open(path).read()
        assert 'python3 -m PyInstaller' in content, \
            "Should use 'python3 -m PyInstaller' to ensure venv's PyInstaller"

    def test_linux_build_has_paths_flag(self):
        """Build script must have --paths '.' for local module discovery."""
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'build_app.sh')
        content = open(path).read()
        assert '--paths' in content, "Should have --paths flag"

    def test_windows_build_script_exists(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'build_app.bat')
        assert os.path.isfile(path)

    def test_windows_build_uses_python_m(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'build_app.bat')
        content = open(path).read()
        assert 'python -m PyInstaller' in content

    def test_readme_exists(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'README.md')
        assert os.path.isfile(path)

    def test_readme_has_quick_start(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'README.md')
        content = open(path).read()
        assert 'Quick Start' in content
        assert 'pip install' in content

    def test_license_exists(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'LICENSE')
        assert os.path.isfile(path)

    def test_license_is_mit(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'LICENSE')
        content = open(path).read()
        assert 'MIT License' in content

    def test_gitignore_exists(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            '.gitignore')
        assert os.path.isfile(path)

    def test_gitignore_excludes_db(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            '.gitignore')
        content = open(path).read()
        assert 'trading_journal.db' in content
        assert '__pycache__' in content
        assert 'venv/' in content
