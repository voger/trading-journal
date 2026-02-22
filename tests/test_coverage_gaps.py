"""
Tests for previously untested database CRUD and utility functions.

Covers: watchlist, tags, setup types/charts, import logs, equity curve,
        backup/restore, migration, get_equity_events.
"""
import os
import json
import zipfile
import pytest

import database as db
from backup_manager import create_backup, restore_backup, list_backups, get_app_data_dir


# ── Watchlist CRUD ───────────────────────────────────────────────────────

class TestWatchlistCRUD:

    def test_add_watchlist_item(self, conn, forex_account):
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        wid = db.add_watchlist_item(conn, iid, account_id=forex_account,
                                    bias_weekly='bullish', notes='Watch MA')
        assert wid is not None
        assert wid > 0

    def test_get_watchlist_item(self, conn, forex_account):
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        wid = db.add_watchlist_item(conn, iid, account_id=forex_account,
                                    bias_daily='bearish')
        item = db.get_watchlist_item(conn, wid)
        assert item is not None
        assert item['instrument_id'] == iid
        assert item['bias_daily'] == 'bearish'
        assert item['symbol'] == 'EURUSD'

    def test_get_watchlist_item_nonexistent(self, conn):
        assert db.get_watchlist_item(conn, 999999) is None

    def test_get_watchlist_empty(self, conn, forex_account):
        items = db.get_watchlist(conn, account_id=forex_account)
        assert items == []

    def test_get_watchlist_returns_active_only(self, conn, forex_account):
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        wid1 = db.add_watchlist_item(conn, iid, account_id=forex_account)
        iid2 = db.get_or_create_instrument(conn, 'GBPUSD')
        wid2 = db.add_watchlist_item(conn, iid2, account_id=forex_account)
        # Deactivate one
        db.update_watchlist_item(conn, wid2, is_active=0)
        items = db.get_watchlist(conn, account_id=forex_account)
        assert len(items) == 1
        assert items[0]['id'] == wid1

    def test_get_watchlist_filtered_by_account(self, conn, forex_account):
        other = db.create_account(conn, name='Other', broker='X',
                                   currency='EUR', asset_type='forex')
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        db.add_watchlist_item(conn, iid, account_id=forex_account)
        iid2 = db.get_or_create_instrument(conn, 'GBPUSD')
        db.add_watchlist_item(conn, iid2, account_id=other)
        items = db.get_watchlist(conn, account_id=forex_account)
        assert len(items) == 1

    def test_update_watchlist_item(self, conn, forex_account):
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        wid = db.add_watchlist_item(conn, iid, account_id=forex_account,
                                    notes='Old note')
        db.update_watchlist_item(conn, wid, notes='New note', bias_h4='bullish')
        item = db.get_watchlist_item(conn, wid)
        assert item['notes'] == 'New note'
        assert item['bias_h4'] == 'bullish'

    def test_update_watchlist_item_empty_noop(self, conn, forex_account):
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        wid = db.add_watchlist_item(conn, iid, account_id=forex_account)
        db.update_watchlist_item(conn, wid)  # no kwargs
        assert db.get_watchlist_item(conn, wid) is not None

    def test_delete_watchlist_item(self, conn, forex_account):
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        wid = db.add_watchlist_item(conn, iid, account_id=forex_account)
        db.delete_watchlist_item(conn, wid)
        assert db.get_watchlist_item(conn, wid) is None

    def test_reorder_watchlist(self, conn, forex_account):
        iid1 = db.get_or_create_instrument(conn, 'EURUSD')
        iid2 = db.get_or_create_instrument(conn, 'GBPUSD')
        iid3 = db.get_or_create_instrument(conn, 'USDJPY')
        w1 = db.add_watchlist_item(conn, iid1, account_id=forex_account)
        w2 = db.add_watchlist_item(conn, iid2, account_id=forex_account)
        w3 = db.add_watchlist_item(conn, iid3, account_id=forex_account)
        # Reorder: w3, w1, w2
        db.reorder_watchlist(conn, [w3, w1, w2])
        items = db.get_watchlist(conn, account_id=forex_account)
        ids = [i['id'] for i in items]
        assert ids == [w3, w1, w2]


# ── Tags CRUD ────────────────────────────────────────────────────────────

class TestTagsCRUD:

    def _create_tag(self, conn, name, color='#FF0000'):
        cur = conn.execute(
            "INSERT INTO tags (name, color) VALUES (?, ?)", (name, color))
        conn.commit()
        return cur.lastrowid

    def test_get_tags_empty(self, conn):
        tags = db.get_tags(conn)
        assert tags == []

    def test_get_tags_returns_all(self, conn):
        self._create_tag(conn, 'trend')
        self._create_tag(conn, 'reversal')
        self._create_tag(conn, 'breakout')
        tags = db.get_tags(conn)
        assert len(tags) == 3
        names = [t['name'] for t in tags]
        # Sorted by name
        assert names == sorted(names)

    def test_set_and_get_trade_tags(self, conn, forex_account):
        t1 = self._create_tag(conn, 'trend')
        t2 = self._create_tag(conn, 'A-grade')
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        tid = db.create_trade(conn, account_id=forex_account, instrument_id=iid,
                              direction='long', entry_date='2025-01-01',
                              entry_price=1.1, position_size=1, status='open')
        db.set_trade_tags(conn, tid, [t1, t2])
        tags = db.get_trade_tags(conn, tid)
        assert len(tags) == 2
        tag_names = {t['name'] for t in tags}
        assert tag_names == {'trend', 'A-grade'}

    def test_set_trade_tags_replaces_previous(self, conn, forex_account):
        t1 = self._create_tag(conn, 'old-tag')
        t2 = self._create_tag(conn, 'new-tag')
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        tid = db.create_trade(conn, account_id=forex_account, instrument_id=iid,
                              direction='long', entry_date='2025-01-01',
                              entry_price=1.1, position_size=1, status='open')
        db.set_trade_tags(conn, tid, [t1])
        assert len(db.get_trade_tags(conn, tid)) == 1
        db.set_trade_tags(conn, tid, [t2])
        tags = db.get_trade_tags(conn, tid)
        assert len(tags) == 1
        assert tags[0]['name'] == 'new-tag'

    def test_set_trade_tags_empty_clears_all(self, conn, forex_account):
        t1 = self._create_tag(conn, 'tag1')
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        tid = db.create_trade(conn, account_id=forex_account, instrument_id=iid,
                              direction='long', entry_date='2025-01-01',
                              entry_price=1.1, position_size=1, status='open')
        db.set_trade_tags(conn, tid, [t1])
        db.set_trade_tags(conn, tid, [])
        assert db.get_trade_tags(conn, tid) == []

    def test_get_trade_tags_no_tags(self, conn, forex_account):
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        tid = db.create_trade(conn, account_id=forex_account, instrument_id=iid,
                              direction='long', entry_date='2025-01-01',
                              entry_price=1.1, position_size=1, status='open')
        assert db.get_trade_tags(conn, tid) == []


# ── Setup Types Extended ─────────────────────────────────────────────────

class TestSetupTypesCRUD:

    def test_get_setup_types_includes_seeded(self, conn):
        types = db.get_setup_types(conn)
        # Schema seeds 3 default setup types
        assert len(types) >= 3

    def test_create_and_get_setup_types(self, conn):
        count_before = len(db.get_setup_types(conn))
        db.create_setup_type(conn, name='Pullback Custom')
        db.create_setup_type(conn, name='Breakout Custom')
        types = db.get_setup_types(conn)
        assert len(types) == count_before + 2
        names = {t['name'] for t in types}
        assert 'Pullback Custom' in names
        assert 'Breakout Custom' in names

    def test_get_setup_type_by_id(self, conn):
        sid = db.create_setup_type(conn, name='Pullback', description='Trend PB')
        st = db.get_setup_type(conn, sid)
        assert st is not None
        assert st['name'] == 'Pullback'
        assert st['description'] == 'Trend PB'

    def test_get_setup_type_nonexistent(self, conn):
        assert db.get_setup_type(conn, 999999) is None

    def test_update_setup_type(self, conn):
        sid = db.create_setup_type(conn, name='Old Name')
        db.update_setup_type(conn, sid, name='New Name', description='Updated')
        st = db.get_setup_type(conn, sid)
        assert st['name'] == 'New Name'
        assert st['description'] == 'Updated'

    def test_update_setup_type_ignores_disallowed(self, conn):
        sid = db.create_setup_type(conn, name='Test')
        db.update_setup_type(conn, sid, fake_field='bad')
        assert db.get_setup_type(conn, sid)['name'] == 'Test'

    def test_delete_setup_type(self, conn, forex_account):
        sid = db.create_setup_type(conn, name='ToDelete')
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        # Create a trade linked to this setup
        tid = db.create_trade(conn, account_id=forex_account, instrument_id=iid,
                              direction='long', entry_date='2025-01-01',
                              entry_price=1.1, position_size=1, status='open',
                              setup_type_id=sid)
        db.delete_setup_type(conn, sid)
        assert db.get_setup_type(conn, sid) is None
        # Trade should still exist but with NULL setup
        t = db.get_trade(conn, tid)
        assert t is not None
        assert t['setup_type_id'] is None

    def test_get_setup_types_active_filter(self, conn):
        count_before = len(db.get_setup_types(conn, active_only=True))
        s1 = db.create_setup_type(conn, name='Active Custom')
        s2 = db.create_setup_type(conn, name='Inactive Custom')
        db.update_setup_type(conn, s2, is_active=0)
        active = db.get_setup_types(conn, active_only=True)
        assert len(active) == count_before + 1
        all_types = db.get_setup_types(conn, active_only=False)
        assert len(all_types) == count_before + 2


# ── Setup Charts ─────────────────────────────────────────────────────────

class TestSetupCharts:

    def test_add_and_get_setup_charts(self, conn):
        sid = db.create_setup_type(conn, name='Test')
        cid = db.add_setup_chart(conn, sid, '/tmp/example.png',
                                  caption='Perfect entry', sort_order=1)
        assert cid > 0
        charts = db.get_setup_charts(conn, sid)
        assert len(charts) == 1
        assert charts[0]['file_path'] == '/tmp/example.png'
        assert charts[0]['caption'] == 'Perfect entry'

    def test_setup_charts_sorted_by_sort_order(self, conn):
        sid = db.create_setup_type(conn, name='Test')
        db.add_setup_chart(conn, sid, '/tmp/b.png', sort_order=2)
        db.add_setup_chart(conn, sid, '/tmp/a.png', sort_order=1)
        db.add_setup_chart(conn, sid, '/tmp/c.png', sort_order=3)
        charts = db.get_setup_charts(conn, sid)
        paths = [c['file_path'] for c in charts]
        assert paths == ['/tmp/a.png', '/tmp/b.png', '/tmp/c.png']

    def test_delete_setup_chart(self, conn):
        sid = db.create_setup_type(conn, name='Test')
        cid = db.add_setup_chart(conn, sid, '/tmp/del.png')
        path = db.delete_setup_chart(conn, cid)
        assert path == '/tmp/del.png'
        assert db.get_setup_charts(conn, sid) == []

    def test_delete_nonexistent_setup_chart(self, conn):
        assert db.delete_setup_chart(conn, 999999) is None

    def test_setup_charts_empty(self, conn):
        sid = db.create_setup_type(conn, name='Empty')
        assert db.get_setup_charts(conn, sid) == []


# ── Import Logs ──────────────────────────────────────────────────────────

class TestImportLogs:

    def test_create_and_get_import_log(self, conn, stock_account):
        log_id = db.create_import_log(conn,
            account_id=stock_account,
            plugin_name='trading212_csv',
            file_name='test.csv',
            file_hash='abc123',
            trades_found=10,
            trades_imported=8,
            trades_skipped=2)
        assert log_id > 0
        logs = db.get_import_logs(conn, account_id=stock_account)
        assert len(logs) == 1
        assert logs[0]['plugin_name'] == 'trading212_csv'
        assert logs[0]['trades_found'] == 10
        assert logs[0]['trades_imported'] == 8

    def test_get_import_logs_ordered_desc(self, conn, stock_account):
        db.create_import_log(conn, account_id=stock_account,
                             plugin_name='test', file_name='first.csv',
                             trades_found=1, trades_imported=1, trades_skipped=0,
                             imported_at='2025-01-01 10:00:00')
        db.create_import_log(conn, account_id=stock_account,
                             plugin_name='test', file_name='second.csv',
                             trades_found=2, trades_imported=2, trades_skipped=0,
                             imported_at='2025-02-01 10:00:00')
        logs = db.get_import_logs(conn, account_id=stock_account)
        # Most recent first
        assert logs[0]['file_name'] == 'second.csv'
        assert logs[1]['file_name'] == 'first.csv'

    def test_get_import_logs_with_limit(self, conn, stock_account):
        for i in range(5):
            db.create_import_log(conn, account_id=stock_account,
                                 plugin_name='test', file_name=f'file_{i}.csv',
                                 trades_found=1, trades_imported=1, trades_skipped=0)
        logs = db.get_import_logs(conn, account_id=stock_account, limit=3)
        assert len(logs) == 3

    def test_get_import_logs_no_logs(self, conn, stock_account):
        logs = db.get_import_logs(conn, account_id=stock_account)
        assert logs == []

    def test_get_import_logs_account_filter(self, conn, stock_account):
        other = db.create_account(conn, name='Other', broker='X',
                                   currency='EUR', asset_type='stocks')
        db.create_import_log(conn, account_id=stock_account,
                             plugin_name='test', file_name='mine.csv',
                             trades_found=1, trades_imported=1, trades_skipped=0)
        db.create_import_log(conn, account_id=other,
                             plugin_name='test', file_name='theirs.csv',
                             trades_found=1, trades_imported=1, trades_skipped=0)
        logs = db.get_import_logs(conn, account_id=stock_account)
        assert len(logs) == 1
        assert logs[0]['file_name'] == 'mine.csv'


# ── Equity Curve Data ────────────────────────────────────────────────────

class TestEquityCurveData:

    def _make_closed_trade(self, conn, aid, exit_date, pnl,
                           commission=0, swap=0):
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        return db.create_trade(conn, account_id=aid, instrument_id=iid,
                               direction='long', entry_date='2025-01-01',
                               entry_price=1.1, position_size=1,
                               status='closed', exit_date=exit_date,
                               exit_price=1.15,
                               pnl_account_currency=pnl,
                               commission=commission, swap=swap)

    def test_equity_curve_empty(self, conn, forex_account):
        data = db.get_equity_curve_data(conn, account_id=forex_account)
        assert data == []

    def test_equity_curve_excludes_open_trades(self, conn, forex_account):
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        db.create_trade(conn, account_id=forex_account, instrument_id=iid,
                        direction='long', entry_date='2025-01-01',
                        entry_price=1.1, position_size=1, status='open')
        data = db.get_equity_curve_data(conn, account_id=forex_account)
        assert data == []

    def test_equity_curve_returns_closed_trades(self, conn, forex_account):
        self._make_closed_trade(conn, forex_account, '2025-01-15', 50)
        self._make_closed_trade(conn, forex_account, '2025-02-15', -20)
        data = db.get_equity_curve_data(conn, account_id=forex_account)
        assert len(data) == 2

    def test_equity_curve_ordered_by_exit_date(self, conn, forex_account):
        self._make_closed_trade(conn, forex_account, '2025-03-01', 10)
        self._make_closed_trade(conn, forex_account, '2025-01-01', 30)
        self._make_closed_trade(conn, forex_account, '2025-02-01', 20)
        data = db.get_equity_curve_data(conn, account_id=forex_account)
        dates = [d['exit_date'] for d in data]
        assert dates == sorted(dates)

    def test_equity_curve_excludes_excluded_trades(self, conn, forex_account):
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        tid = db.create_trade(conn, account_id=forex_account, instrument_id=iid,
                              direction='long', entry_date='2025-01-01',
                              entry_price=1.1, position_size=1,
                              status='closed', exit_date='2025-02-01',
                              exit_price=1.15, pnl_account_currency=50)
        db.update_trade(conn, tid, is_excluded=1)
        data = db.get_equity_curve_data(conn, account_id=forex_account)
        assert data == []

    def test_equity_curve_has_balance_and_pnl(self, conn, forex_account):
        self._make_closed_trade(conn, forex_account, '2025-01-15', 50,
                                commission=2.5, swap=-0.5)
        data = db.get_equity_curve_data(conn, account_id=forex_account)
        assert data[0]['pnl_account_currency'] == 50
        assert data[0]['commission'] == 2.5
        assert data[0]['swap'] == -0.5


# ── Equity Events ────────────────────────────────────────────────────────

class TestEquityEvents:

    def test_get_equity_events_empty(self, conn, forex_account):
        events = db.get_equity_events(conn, account_id=forex_account)
        assert events == []

    def test_get_equity_events_returns_all(self, conn, forex_account):
        db.add_account_event(conn, forex_account, 'deposit', 1000,
                             event_date='2025-01-01',
                             broker_ticket_id='DEP1')
        db.add_account_event(conn, forex_account, 'withdrawal', -200,
                             event_date='2025-02-01',
                             broker_ticket_id='WD1')
        events = db.get_equity_events(conn, account_id=forex_account)
        assert len(events) == 2

    def test_get_equity_events_ordered_by_date(self, conn, forex_account):
        db.add_account_event(conn, forex_account, 'deposit', 500,
                             event_date='2025-03-01',
                             broker_ticket_id='DEP2')
        db.add_account_event(conn, forex_account, 'deposit', 1000,
                             event_date='2025-01-01',
                             broker_ticket_id='DEP1')
        events = db.get_equity_events(conn, account_id=forex_account)
        assert events[0]['event_date'] <= events[1]['event_date']


# ── Backup / Restore ────────────────────────────────────────────────────

class TestBackupRestore:

    def test_get_app_data_dir(self, tmp_path):
        paths = get_app_data_dir(str(tmp_path))
        assert 'db' in paths
        assert 'charts' in paths
        assert 'screenshots' in paths
        assert 'backups' in paths
        assert paths['db'].endswith('trading_journal.db')

    def test_create_backup(self, tmp_path):
        app_dir = str(tmp_path / 'app')
        os.makedirs(app_dir)
        # Create a fake DB
        db_path = os.path.join(app_dir, 'trading_journal.db')
        with open(db_path, 'w') as f:
            f.write('fake db')
        # Create a fake screenshot
        ss_dir = os.path.join(app_dir, 'screenshots')
        os.makedirs(ss_dir)
        with open(os.path.join(ss_dir, 'shot.png'), 'w') as f:
            f.write('fake image')

        backup_dir = str(tmp_path / 'backups')
        path = create_backup(app_dir, backup_dir=backup_dir)
        assert os.path.isfile(path)
        assert path.endswith('.zip')

        # Verify zip contents
        with zipfile.ZipFile(path, 'r') as zf:
            names = zf.namelist()
            assert 'trading_journal.db' in names
            assert 'manifest.json' in names
            assert any('screenshots' in n for n in names)
            manifest = json.loads(zf.read('manifest.json'))
            assert 'backup_date' in manifest

    def test_restore_backup(self, tmp_path):
        # Create backup
        app_dir = str(tmp_path / 'app')
        os.makedirs(app_dir)
        db_path = os.path.join(app_dir, 'trading_journal.db')
        with open(db_path, 'w') as f:
            f.write('original db content')
        backup_path = create_backup(app_dir, str(tmp_path / 'backups'))

        # Corrupt the db
        with open(db_path, 'w') as f:
            f.write('corrupted')

        # Restore
        result = restore_backup(backup_path, app_dir)
        assert result['success'] is True

        # Verify DB restored
        with open(db_path, 'r') as f:
            assert f.read() == 'original db content'

    def test_restore_nonexistent_file(self, tmp_path):
        result = restore_backup('/nonexistent/path.zip', str(tmp_path))
        assert result['success'] is False
        assert 'not found' in result['message']

    def test_restore_invalid_zip(self, tmp_path):
        bad_file = str(tmp_path / 'bad.zip')
        with open(bad_file, 'w') as f:
            f.write('not a zip file')
        result = restore_backup(bad_file, str(tmp_path))
        assert result['success'] is False
        assert 'not a zip' in result['message']

    def test_restore_zip_without_db(self, tmp_path):
        zip_path = str(tmp_path / 'no_db.zip')
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('manifest.json', '{}')
        result = restore_backup(zip_path, str(tmp_path))
        assert result['success'] is False
        assert 'database' in result['message'].lower()

    def test_list_backups_empty(self, tmp_path):
        backups = list_backups(str(tmp_path / 'nonexistent'))
        assert backups == []

    def test_list_backups(self, tmp_path):
        app_dir = str(tmp_path / 'app')
        os.makedirs(app_dir)
        db_path = os.path.join(app_dir, 'trading_journal.db')
        with open(db_path, 'w') as f:
            f.write('db')
        backup_dir = str(tmp_path / 'backups')
        # Create two backups with different names
        p1 = create_backup(app_dir, backup_dir)
        # Manually create a second one with different name
        import shutil
        p2 = p1.replace('.zip', '_copy.zip')
        shutil.copy(p1, p2)
        # Rename to match expected pattern
        p2_proper = os.path.join(backup_dir, 'trading_journal_backup_2099-01-01_000000.zip')
        os.rename(p2, p2_proper)
        backups = list_backups(backup_dir)
        assert len(backups) == 2
        for b in backups:
            assert 'filename' in b
            assert 'path' in b
            assert 'size_mb' in b

    def test_backup_restore_round_trip_with_real_db(self, tmp_path):
        """Full round trip: create DB with trades → backup → delete → restore → verify."""
        app_dir = str(tmp_path / 'app')
        os.makedirs(app_dir)
        real_db_path = os.path.join(app_dir, 'trading_journal.db')
        db.init_database(real_db_path)
        conn = db.get_connection(real_db_path)
        aid = db.create_account(conn, name='Test', broker='B',
                                currency='EUR', asset_type='forex')
        iid = db.get_or_create_instrument(conn, 'EURUSD')
        db.create_trade(conn, account_id=aid, instrument_id=iid,
                        direction='long', entry_date='2025-01-01',
                        entry_price=1.1, position_size=1, status='open')
        conn.close()

        backup_path = create_backup(app_dir, str(tmp_path / 'backups'))
        assert os.path.isfile(backup_path)

        # Delete the db
        os.remove(real_db_path)
        assert not os.path.exists(real_db_path)

        # Restore
        result = restore_backup(backup_path, app_dir)
        assert result['success'] is True
        assert os.path.exists(real_db_path)

        # Verify data survived
        conn2 = db.get_connection(real_db_path)
        trades = db.get_trades(conn2, account_id=aid)
        assert len(trades) == 1
        conn2.close()


# ── Migration ────────────────────────────────────────────────────────────

class TestMigration:

    def test_migration_idempotent(self, db_path):
        """Running init_database twice should not error."""
        db.init_database(db_path)
        db.init_database(db_path)
        conn = db.get_connection(db_path)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert 'trades' in tables
        assert 'executions' in tables
        conn.close()

    def test_get_db_path_returns_string(self):
        path = db.get_db_path()
        assert isinstance(path, str)
        assert 'trading_journal.db' in path
