"""
Tests for db.journal — the Journal repository seam (issue #6).

A Journal wraps one sqlite3.Connection and exposes every conn-first
crud/analytics/queries function as a method with the connection injected,
so callers stop threading `conn` through the stack.
"""
import sqlite3

import pytest

import database as db
from db.journal import Journal


class TestJournalConstruction:
    def test_wraps_connection(self, conn):
        j = Journal(conn)
        assert j.conn is conn

    def test_exported_from_database_shim(self, conn):
        # Callers import it the same way they import everything else.
        assert db.Journal is Journal


class TestDelegation:
    def test_delegates_crud_create_and_read(self, conn):
        j = Journal(conn)
        aid = j.create_account(name='J Test', broker='B', currency='EUR',
                               asset_type='stocks')
        assert isinstance(aid, int)
        row = j.get_account(aid)
        assert row['name'] == 'J Test'

    def test_delegates_settings_roundtrip(self, conn):
        j = Journal(conn)
        j.set_setting('dark_mode', '1')
        assert j.get_setting('dark_mode') == '1'

    def test_delegates_queries(self, conn):
        j = Journal(conn)
        aid = j.create_account(name='Q', broker='B', asset_type='forex')
        # Should not raise and should return a list.
        assert isinstance(j.get_trades_all_filtered(account_id=aid), list)

    def test_delegates_analytics(self, conn):
        j = Journal(conn)
        aid = j.create_account(name='A', broker='B', asset_type='forex')
        # Delegated call must return exactly what the direct call would
        # (None here — no closed trades — proves the conn is threaded through).
        assert j.get_trade_stats(account_id=aid) == \
            db.get_trade_stats(conn, account_id=aid)

    def test_delegated_result_matches_direct_call(self, conn):
        j = Journal(conn)
        j.create_account(name='M', broker='B', asset_type='forex')
        # Same connection, same query -> identical rows.
        via_journal = [dict(r) for r in j.get_tags()]
        via_direct = [dict(r) for r in db.get_tags(conn)]
        assert via_journal == via_direct


class TestSeamPrecision:
    """The seam injects conn ONLY where conn belongs."""

    def test_unknown_attribute_raises(self, conn):
        j = Journal(conn)
        with pytest.raises(AttributeError):
            j.no_such_function

    def test_pure_helper_not_delegated(self, conn):
        # effective_pnl(t) takes a trade, NOT a conn — must not be proxied,
        # otherwise journal.effective_pnl(t) would call effective_pnl(conn, t).
        j = Journal(conn)
        with pytest.raises(AttributeError):
            j.effective_pnl


class TestLifecycle:
    def test_close_closes_connection(self, db_path):
        conn = db.get_connection(db_path)
        j = Journal(conn)
        j.close()
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")
