"""
Trading Journal v2.3.0 — Main Application
"""
import sys, os, shutil
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    # Running as PyInstaller bundle: resources are in _MEIPASS (_internal/)
    _resource_dir = sys._MEIPASS
    _install_dir = os.path.dirname(sys.executable)
else:
    _install_dir = os.path.dirname(os.path.abspath(__file__))
    _resource_dir = _install_dir
sys.path.insert(0, _install_dir)

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QComboBox, QLabel, QPushButton, QMessageBox,
    QFileDialog,
)
from PyQt6.QtGui import QAction, QIcon


from database import (
    init_database, get_connection, get_app_data_dir,
    get_accounts, get_account, create_account, update_account, delete_account,
)
from dialogs import AccountDialog
from asset_modules import get_module
from backup_manager import create_backup, restore_backup

APP_VERSION = "2.3.0"
ICON_PATH = os.path.join(_resource_dir, 'icon.png')


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Trading Journal v{APP_VERSION}")
        self.setMinimumSize(1100, 700); self.resize(1350, 850)
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        # User data goes in the XDG/platform data directory, not beside the source
        self.app_dir = get_app_data_dir()
        os.makedirs(self.app_dir, exist_ok=True)

        # One-time migration: copy DB (and screenshots/charts) from old location
        _old_db = os.path.join(_install_dir, 'trading_journal.db')
        _new_db = os.path.join(self.app_dir, 'trading_journal.db')
        if not os.path.exists(_new_db) and os.path.exists(_old_db):
            shutil.copy2(_old_db, _new_db)
            for _sub in ('screenshots', 'charts'):
                _src = os.path.join(_install_dir, _sub)
                _dst = os.path.join(self.app_dir, _sub)
                if os.path.exists(_src) and not os.path.exists(_dst):
                    shutil.copytree(_src, _dst)

        self.db_path = init_database(os.path.join(self.app_dir, 'trading_journal.db'))
        self.conn = get_connection(self.db_path)
        self._build_ui()
        self._refresh_all()

    # ── UI ──

    def _build_ui(self):
        mb = self.menuBar()
        fm = mb.addMenu("&File")
        for text, slot in [("&Import Trades...", lambda: self.trades_tab._on_import()),
                           ("&Backup...", self._on_backup), ("&Restore...", self._on_restore)]:
            a = QAction(text, self); a.triggered.connect(slot); fm.addAction(a)

        am = mb.addMenu("&Account")
        for text, slot in [("&New Account...", self._on_new_account),
                           ("&Edit Account...", self._on_edit_account),
                           ("&Delete Account", self._on_delete_account)]:
            a = QAction(text, self); a.triggered.connect(slot); am.addAction(a)

        cw = QWidget(); self.setCentralWidget(cw); ml = QVBoxLayout(cw)

        # Account filter bar
        af = QHBoxLayout(); af.addWidget(QLabel("Account:"))
        self.account_filter = QComboBox(); self.account_filter.setMinimumWidth(250)
        self.account_filter.currentIndexChanged.connect(self._on_account_changed)
        af.addWidget(self.account_filter); af.addStretch()
        ml.addLayout(af)

        self.tabs = QTabWidget(); ml.addWidget(self.tabs)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # Create tab widgets
        from tabs.trades import TradesTab
        from tabs.journal import JournalTab
        from tabs.setups import SetupsTab
        from tabs.equity import EquityTab
        from tabs.stats import StatsTab
        from tabs.imports import ImportsTab
        from tabs.watchlist import WatchlistTab

        self.trades_tab = TradesTab(self.conn, self._aid, self._status)
        self.journal_tab = JournalTab(self.conn, self._aid, self._status)
        self.setups_tab = SetupsTab(self.conn, self._aid)
        self.watchlist_tab = WatchlistTab(self.conn, self._aid, self._status)
        self.equity_tab = EquityTab(self.conn, self._aid)
        self.stats_tab = StatsTab(self.conn, self._aid)
        self.imports_tab = ImportsTab(self.conn, self._aid)

        self.tabs.addTab(self.trades_tab, "Trades")
        self.tabs.addTab(self.watchlist_tab, "Watchlist")
        self.tabs.addTab(self.journal_tab, "Daily Journal")
        self.tabs.addTab(self.setups_tab, "Setups")
        self.tabs.addTab(self.equity_tab, "Equity Curve")
        self.tabs.addTab(self.stats_tab, "Summary Stats")
        self.tabs.addTab(self.imports_tab, "Import History")

        # Wire data_changed signals for cross-tab coordination
        self.trades_tab.data_changed.connect(self._on_trades_changed)
        self.setups_tab.data_changed.connect(self._on_setups_changed)

    # ── Helpers ──

    def _aid(self):
        return self.account_filter.currentData()

    def _status(self, msg):
        self.statusBar().showMessage(msg)

    # ── Cross-tab coordination ──

    def _on_trades_changed(self):
        """Trades were added/edited/deleted or imported."""
        self.trades_tab.refresh()
        self.stats_tab.refresh()
        self.equity_tab.refresh()
        self.imports_tab.refresh()
        self._refresh_account_filter()

    def _on_setups_changed(self):
        """Setups were added/edited/deleted."""
        self.setups_tab.refresh()
        self.trades_tab.refresh_setup_filter()

    def _on_account_changed(self):
        """Account filter changed."""
        self.trades_tab.refresh()
        self.stats_tab.refresh()
        self.imports_tab.refresh()
        self.equity_tab.refresh()
        self.watchlist_tab.refresh()

    def _on_tab_changed(self, index):
        if self.tabs.widget(index) == self.equity_tab:
            self.equity_tab.try_render_if_visible()

    # ── Refresh ──

    def _refresh_all(self):
        self._refresh_account_filter()
        self.trades_tab.refresh()
        self.stats_tab.refresh()
        self.journal_tab.refresh()
        self.setups_tab.refresh()
        self.watchlist_tab.refresh()
        self.equity_tab.refresh()
        self.imports_tab.refresh()
        self.trades_tab.refresh_setup_filter()

    def _refresh_account_filter(self):
        self.account_filter.blockSignals(True)
        cd = self.account_filter.currentData()
        self.account_filter.clear(); self.account_filter.addItem("All Accounts", None)
        for a in get_accounts(self.conn):
            mod = get_module(a['asset_type'])
            mod_label = f" [{mod.DISPLAY_NAME}]" if mod else ""
            self.account_filter.addItem(f"{a['name']} ({a['currency']}){mod_label}", a['id'])
        if cd is not None:
            idx = self.account_filter.findData(cd)
            if idx >= 0: self.account_filter.setCurrentIndex(idx)
        self.account_filter.blockSignals(False)

    # ── Account CRUD ──

    def _on_new_account(self):
        dlg = AccountDialog(self)
        if dlg.exec():
            try: create_account(self.conn, **dlg.get_values()); self._refresh_account_filter()
            except Exception as e: QMessageBox.critical(self, "Error", str(e))

    def _on_edit_account(self):
        aid = self._aid()
        if aid is None: QMessageBox.information(self, "Select", "Select a specific account first."); return
        acct = get_account(self.conn, aid)
        if not acct: return
        dlg = AccountDialog(self, account=acct)
        if dlg.exec():
            try: update_account(self.conn, aid, **dlg.get_values()); self._refresh_account_filter()
            except Exception as e: QMessageBox.critical(self, "Error", str(e))

    def _on_delete_account(self):
        aid = self._aid()
        if aid is None: QMessageBox.information(self, "Select", "Select a specific account first."); return
        acct = get_account(self.conn, aid)
        if not acct: return
        if QMessageBox.warning(self, "Delete Account",
            f"Delete '{acct['name']}' and ALL its trades, journals, and history?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            delete_account(self.conn, aid); self.account_filter.setCurrentIndex(0); self._refresh_all()

    # ── Backup / Restore ──

    def _on_backup(self):
        d = QFileDialog.getExistingDirectory(self, "Backup Directory")
        if not d: return
        try:
            p = create_backup(self.app_dir, d)
            QMessageBox.information(self, "Backup", f"Saved to:\n{p}")
        except Exception as e: QMessageBox.critical(self, "Error", str(e))

    def _on_restore(self):
        fp, _ = QFileDialog.getOpenFileName(self, "Restore Backup", "", "Zip (*.zip)")
        if not fp: return
        if QMessageBox.warning(self, "Restore", "This REPLACES your current data. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes: return
        try:
            self.conn.close()
            restore_backup(fp, self.app_dir)
            self.conn = get_connection(self.db_path)
            for tab in [self.trades_tab, self.journal_tab, self.setups_tab,
                        self.equity_tab, self.stats_tab, self.imports_tab,
                        self.watchlist_tab]:
                tab.conn = self.conn
            self._refresh_all()
            QMessageBox.information(self, "Restored", "Backup restored successfully.")
        except Exception as e: QMessageBox.critical(self, "Error", str(e))

    def closeEvent(self, event):
        self.conn.close(); event.accept()


def main():
    app = QApplication(sys.argv)
    if os.path.exists(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))
    w = MainWindow(); w.show(); sys.exit(app.exec())

if __name__ == '__main__':
    main()
