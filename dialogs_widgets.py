"""
Trading Journal — Shared dialog widget helpers.
SCREENSHOTS_DIR, SETUP_CHARTS_DIR, ImageViewer, MetricCard, StatusBadge,
TradeChartsDialog.
"""
import os
import shutil

import theme as _theme
from PyQt6.QtWidgets import (
    QDialog, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy,
    QListWidget, QListWidgetItem, QPushButton, QDialogButtonBox,
    QFileDialog, QMessageBox,
)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices

from database import get_app_data_dir, get_trade_charts, add_trade_chart, delete_trade_chart

SCREENSHOTS_DIR = os.path.join(get_app_data_dir(), 'screenshots')
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
SETUP_CHARTS_DIR = os.path.join(get_app_data_dir(), 'setup_charts')
os.makedirs(SETUP_CHARTS_DIR, exist_ok=True)


class ImageViewer:
    """Open image in system default viewer."""
    @staticmethod
    def open(file_path):
        if os.path.exists(file_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(file_path)))


# ═══════════════════════════════════════════════════════════════
# HELPER WIDGETS
# ═══════════════════════════════════════════════════════════════

class MetricCard(QFrame):
    """A small read-only metric display: label + value."""
    def __init__(self, label_text, initial_value="—", parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(2)
        self._label = QLabel(label_text)
        lbl_color = '#aaa' if _theme.is_dark() else '#666'
        self._label.setStyleSheet(f"color: {lbl_color}; font-size: 11px; font-weight: bold;")
        self._value = QLabel(initial_value)
        self._value.setStyleSheet("font-size: 18px; font-weight: bold;")
        self._value.setAlignment(Qt.AlignmentFlag.AlignRight)
        lay.addWidget(self._label)
        lay.addWidget(self._value)

    def set_value(self, text, color=None):
        c = color or _theme.neu_color()
        self._value.setText(text)
        self._value.setStyleSheet(f"color: {c}; font-size: 18px; font-weight: bold;")


class StatusBadge(QLabel):
    """Color-coded trade status badge."""
    STYLES = {
        'open': ("OPEN", "#ffffff", "#3b82f6"),
        'win':  ("WIN",  "#ffffff", "#16a34a"),
        'loss': ("LOSS", "#ffffff", "#dc2626"),
        'be':   ("B/E",  "#ffffff", "#6b7280"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(28)
        self.setMinimumWidth(60)
        self.set_status('open')

    def set_status(self, status_key):
        text, fg, bg = self.STYLES.get(status_key, self.STYLES['open'])
        self.setText(text)
        self.setStyleSheet(
            f"color: {fg}; background-color: {bg}; border-radius: 4px; "
            f"font-weight: bold; font-size: 12px; padding: 4px 12px;"
        )


class TradeChartsDialog(QDialog):
    """Lightweight screenshot manager for a single trade."""

    def __init__(self, parent, conn, trade_id: int):
        super().__init__(parent)
        self.conn = conn
        self.trade_id = trade_id
        self.setWindowTitle("Trade Screenshots")
        self.resize(480, 360)
        lay = QVBoxLayout(self)

        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        lay.addWidget(self.list)

        btn_row = QHBoxLayout()
        self.btn_add  = QPushButton("Add Screenshot")
        self.btn_open = QPushButton("Open")
        self.btn_del  = QPushButton("Delete")
        for b in [self.btn_add, self.btn_open, self.btn_del]:
            btn_row.addWidget(b)
        lay.addLayout(btn_row)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self.btn_add.clicked.connect(self._on_add)
        self.btn_open.clicked.connect(self._on_open)
        self.btn_del.clicked.connect(self._on_delete)
        self.list.doubleClicked.connect(self._on_open)

        self._refresh()

    def _refresh(self):
        self.list.clear()
        self._charts = get_trade_charts(self.conn, self.trade_id)
        for c in self._charts:
            label = c['caption'] or os.path.basename(c['file_path'])
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, c['id'])
            self.list.addItem(item)

    def _selected_chart(self):
        item = self.list.currentItem()
        if not item:
            return None
        cid = item.data(Qt.ItemDataRole.UserRole)
        return next((c for c in self._charts if c['id'] == cid), None)

    def _on_add(self):
        fp, _ = QFileDialog.getOpenFileName(
            self, "Add Screenshot", "",
            "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp)")
        if not fp:
            return
        dest_dir = os.path.join(get_app_data_dir(), 'screenshots')
        os.makedirs(dest_dir, exist_ok=True)
        fname = f"trade_{self.trade_id}_{os.path.basename(fp)}"
        dest = os.path.join(dest_dir, fname)
        shutil.copy2(fp, dest)
        add_trade_chart(self.conn, self.trade_id, 'screenshot', dest)
        self._refresh()

    def _on_open(self):
        chart = self._selected_chart()
        if chart and os.path.exists(chart['file_path']):
            QDesktopServices.openUrl(QUrl.fromLocalFile(chart['file_path']))

    def _on_delete(self):
        chart = self._selected_chart()
        if not chart:
            return
        if QMessageBox.question(self, "Delete", "Delete this screenshot?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        fp = delete_trade_chart(self.conn, chart['id'])
        if fp and os.path.exists(fp):
            try:
                os.remove(fp)
            except OSError:
                pass
        self._refresh()
