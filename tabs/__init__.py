"""Base class for all tab widgets."""
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import pyqtSignal


class BaseTab(QWidget):
    """Base class for tab widgets. Provides shared access patterns."""
    data_changed = pyqtSignal()  # Emitted when this tab modifies data

    def __init__(self, conn, get_aid_fn):
        super().__init__()
        self.conn = conn
        self._get_aid = get_aid_fn  # callable returning current account ID or None

    def aid(self):
        return self._get_aid()

    def refresh(self):
        """Override in subclasses to refresh tab content."""
        pass
