"""Import History tab."""
import json
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox,
)
from PyQt6.QtCore import Qt
from tabs import BaseTab
from database import get_import_logs, delete_import_log


class ImportsTab(BaseTab):
    def __init__(self, conn, get_aid_fn):
        super().__init__(conn, get_aid_fn)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)

        tb = QHBoxLayout()
        self.btn_delete = QPushButton("Delete Log")
        self.btn_delete.setEnabled(False)
        self.btn_delete.setToolTip("Delete the selected import log and all data imported with it")
        self.btn_delete.clicked.connect(self._on_delete)
        tb.addWidget(self.btn_delete)
        tb.addStretch()
        layout.addLayout(tb)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        cols = ['ID', 'Date', 'Account', 'Plugin', 'File', 'Found', 'Imported', 'Skipped', 'Errors']
        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setColumnHidden(0, True)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table)

    def refresh(self):
        self.btn_delete.setEnabled(False)
        logs = get_import_logs(self.conn, account_id=self.aid())
        self.table.setRowCount(len(logs))
        for row, log in enumerate(logs):
            err_count = 0
            if log['errors']:
                try:
                    err_count = len(json.loads(log['errors']))
                except (ValueError, TypeError):
                    err_count = 1  # unparseable but non-empty → at least 1 error
            items = [
                str(log['id']),
                (log['imported_at'] or '')[:16], log['account_name'] or '',
                log['plugin_name'] or '', log['file_name'] or '',
                str(log['trades_found'] or 0), str(log['trades_imported'] or 0),
                str(log['trades_skipped'] or 0), str(err_count),
            ]
            for col, val in enumerate(items):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, col, item)
        self.btn_delete.setEnabled(False)

    def _on_selection_changed(self):
        self.btn_delete.setEnabled(self.table.currentRow() >= 0)

    def _on_delete(self):
        row = self.table.currentRow()
        if row < 0:
            return
        id_item = self.table.item(row, 0)
        if not id_item or not id_item.text():
            return
        try:
            log_id = int(id_item.text())
        except ValueError:
            return
        file_col = self.table.item(row, 4)
        file_name = file_col.text() if file_col else ''
        reply = QMessageBox.question(
            self, "Delete Import Log",
            f"Delete import log for '{file_name}'?\n\n"
            "This will permanently remove all trades and executions imported "
            "with this log. This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            plugin_name, account_id, affected_instruments = delete_import_log(self.conn, log_id)
            # Re-run FIFO for executions-mode imports so remaining data stays consistent
            if affected_instruments:
                from fifo_engine import run_fifo_matching
                for inst_id in affected_instruments:
                    run_fifo_matching(self.conn, account_id, inst_id)
            self.data_changed.emit()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not delete log:\n{e}")
