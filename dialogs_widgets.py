"""
Trading Journal — Shared dialog widget helpers.
SCREENSHOTS_DIR, SETUP_CHARTS_DIR, ImageViewer, MetricCard, StatusBadge.
"""
import os

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QSizePolicy,
)
from PyQt6.QtCore import Qt

from database import get_app_data_dir

SCREENSHOTS_DIR = os.path.join(get_app_data_dir(), 'screenshots')
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
SETUP_CHARTS_DIR = os.path.join(get_app_data_dir(), 'setup_charts')
os.makedirs(SETUP_CHARTS_DIR, exist_ok=True)


class ImageViewer:
    """Open image in system default viewer."""
    @staticmethod
    def open(file_path):
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices
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
        self._label.setStyleSheet("color: #666; font-size: 11px; font-weight: bold;")
        self._value = QLabel(initial_value)
        self._value.setStyleSheet("font-size: 18px; font-weight: bold;")
        self._value.setAlignment(Qt.AlignmentFlag.AlignRight)
        lay.addWidget(self._label)
        lay.addWidget(self._value)

    def set_value(self, text, color=None):
        c = color or "#333"
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
