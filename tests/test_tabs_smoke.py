"""
Offscreen-Qt smoke tests for the tab/dialog layer after the Journal migration
(issue #6). These construct each tab with a Journal (not a raw conn) and call
refresh(), exercising the migrated crud/analytics/queries call sites end to end.

Thin coverage by design — they catch construction- and refresh-time breakage,
which is exactly the risk when threading `conn` is replaced by a Journal.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication

import database as db
from db.journal import Journal


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def journal(conn):
    return Journal(conn)


@pytest.fixture
def seeded(journal):
    """A Journal with one stocks account selected."""
    aid = journal.create_account(name='Smoke', broker='B', currency='EUR',
                                 asset_type='stocks')
    return journal, (lambda: aid), (lambda *a, **k: None)


def test_trades_tab(qapp, seeded):
    j, aid_fn, status = seeded
    from tabs.trades import TradesTab
    tab = TradesTab(j, aid_fn, status)
    tab.refresh()


def test_journal_tab(qapp, seeded):
    j, aid_fn, status = seeded
    from tabs.journal import JournalTab
    tab = JournalTab(j, aid_fn, status)
    tab.refresh()


def test_setups_tab(qapp, seeded):
    j, aid_fn, _ = seeded
    from tabs.setups import SetupsTab
    tab = SetupsTab(j, aid_fn)
    tab.refresh()


def test_watchlist_tab(qapp, seeded):
    j, aid_fn, status = seeded
    from tabs.watchlist import WatchlistTab
    tab = WatchlistTab(j, aid_fn, status)
    tab.refresh()


def test_equity_tab(qapp, seeded):
    j, aid_fn, _ = seeded
    from tabs.equity import EquityTab
    tab = EquityTab(j, aid_fn)
    tab.show()        # force render path instead of dirty-defer
    tab.refresh()


def test_stats_tab(qapp, seeded):
    j, aid_fn, _ = seeded
    from tabs.stats import StatsTab
    tab = StatsTab(j, aid_fn)
    tab.refresh()


def test_imports_tab(qapp, seeded):
    j, aid_fn, _ = seeded
    from tabs.imports import ImportsTab
    tab = ImportsTab(j, aid_fn)
    tab.refresh()


# ── Dialogs (opened on user action, so not reached by tab.refresh) ──

def test_setup_dialog_constructs(qapp, seeded):
    j, _, _ = seeded
    from PyQt6.QtWidgets import QWidget
    from dialogs_setup import SetupDialog
    SetupDialog(QWidget(), j)  # exercises journal-based __init__


def test_trade_dialog_constructs(qapp, seeded):
    j, aid_fn, _ = seeded
    from PyQt6.QtWidgets import QWidget
    from dialogs_trade import TradeDialog
    # _build() calls get_accounts / get_setup_types via the Journal and
    # constructs the chart widget with journal.conn.
    TradeDialog(QWidget(), j, default_account_id=aid_fn())
