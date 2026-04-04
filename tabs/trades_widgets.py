"""Trades tab — standalone widget helpers."""
from PyQt6.QtWidgets import (
    QTableWidgetItem, QFrame, QVBoxLayout, QLabel, QSizePolicy,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
import theme as _theme


class _NumItem(QTableWidgetItem):
    """QTableWidgetItem that sorts numerically when the cell text is a number."""
    def __lt__(self, other):
        try:
            return float(self.text().replace('+', '').replace(',', '')) < \
                   float(other.text().replace('+', '').replace(',', ''))
        except (ValueError, AttributeError):
            return self.text() < other.text()


# ── KPI Card Widget ──────────────────────────────────────────────────────

class KPICard(QFrame):
    """Compact metric card for the KPI bar."""
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        # Border/radius handled by global QSS in dark mode; StyledPanel draws natively in light mode
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(60)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(0)
        self._title = QLabel(title)
        _t_color = '#aaa' if _theme.is_dark() else '#666'
        self._title.setStyleSheet(f"color: {_t_color}; font-size: 10px; font-weight: bold;")
        self._value = QLabel("—")
        self._value.setStyleSheet("font-size: 16px; font-weight: bold;")
        self._value.setAlignment(Qt.AlignmentFlag.AlignRight)
        lay.addWidget(self._title)
        lay.addWidget(self._value)

    def set_value(self, text, color=None):
        if color is None:
            color = '#ddd' if _theme.is_dark() else '#333'
        self._value.setText(text)
        self._value.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: bold;")
