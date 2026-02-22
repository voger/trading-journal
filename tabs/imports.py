"""Import History tab."""
from PyQt6.QtWidgets import (
    QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView,
)
from PyQt6.QtCore import Qt
from tabs import BaseTab
from database import get_import_logs


class ImportsTab(BaseTab):
    def __init__(self, conn, get_aid_fn):
        super().__init__(conn, get_aid_fn)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        self.table = QTableWidget(); self.table.setAlternatingRowColors(True)
        cols = ['Date','Account','Plugin','File','Found','Imported','Skipped','Errors']
        self.table.setColumnCount(len(cols)); self.table.setHorizontalHeaderLabels(cols)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

    def refresh(self):
        logs = get_import_logs(self.conn, account_id=self.aid())
        self.table.setRowCount(len(logs))
        for row, log in enumerate(logs):
            err_count = 0
            if log['errors']:
                try: err_count = len(log['errors'].split('\n'))
                except: pass
            items = [
                (log['imported_at'] or '')[:16], log['account_name'] or '',
                log['plugin_name'] or '', log['file_name'] or '',
                str(log['trades_found'] or 0), str(log['trades_imported'] or 0),
                str(log['trades_skipped'] or 0), str(err_count),
            ]
            for col, val in enumerate(items):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, col, item)
