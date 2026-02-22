"""
Trading Journal — Dark Theme
Apply with: app.setStyleSheet(get_stylesheet())
"""

# ── Color palette ──
BG_DARK = "#1a1a2e"       # Main background
BG_MID = "#16213e"         # Panel/card background
BG_LIGHT = "#1f2b47"       # Input fields, table rows
BG_HOVER = "#2a3a5c"       # Hover state
BORDER = "#2e3d5f"         # Borders
BORDER_FOCUS = "#4a9eff"   # Focused input border
TEXT = "#e0e0e0"           # Primary text
TEXT_DIM = "#8892a4"       # Secondary text
TEXT_BRIGHT = "#ffffff"    # Headers, emphasis
GREEN = "#26a69a"          # Profit / positive
GREEN_BG = "#1a3a2a"      # Profit background tint
RED = "#ef5350"            # Loss / negative
RED_BG = "#3a1a1a"        # Loss background tint
ACCENT = "#4a9eff"         # Buttons, links, focus
ACCENT_HOVER = "#6bb3ff"   # Button hover


def get_stylesheet():
    return f"""
    /* ── Global ── */
    QMainWindow, QDialog, QWidget {{
        background-color: {BG_DARK};
        color: {TEXT};
        font-size: 13px;
    }}

    /* ── Menu bar ── */
    QMenuBar {{
        background-color: {BG_MID};
        color: {TEXT};
        border-bottom: 1px solid {BORDER};
        padding: 2px;
    }}
    QMenuBar::item:selected {{
        background-color: {BG_HOVER};
        border-radius: 4px;
    }}
    QMenu {{
        background-color: {BG_MID};
        color: {TEXT};
        border: 1px solid {BORDER};
    }}
    QMenu::item:selected {{
        background-color: {BG_HOVER};
    }}

    /* ── Labels ── */
    QLabel {{
        color: {TEXT};
        background: transparent;
    }}

    /* ── Input fields ── */
    QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QDateTimeEdit {{
        background-color: {BG_LIGHT};
        color: {TEXT_BRIGHT};
        border: 1px solid {BORDER};
        border-radius: 4px;
        padding: 4px 6px;
        selection-background-color: {ACCENT};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
    QSpinBox:focus, QDoubleSpinBox:focus, QDateTimeEdit:focus {{
        border-color: {BORDER_FOCUS};
    }}
    QSpinBox::up-button, QDoubleSpinBox::up-button, QDateTimeEdit::up-button {{
        border-left: 1px solid {BORDER};
        background: {BG_HOVER};
        width: 16px;
    }}
    QSpinBox::down-button, QDoubleSpinBox::down-button, QDateTimeEdit::down-button {{
        border-left: 1px solid {BORDER};
        background: {BG_HOVER};
        width: 16px;
    }}

    /* ── Combo boxes ── */
    QComboBox {{
        background-color: {BG_LIGHT};
        color: {TEXT_BRIGHT};
        border: 1px solid {BORDER};
        border-radius: 4px;
        padding: 4px 8px;
        min-height: 20px;
    }}
    QComboBox:hover {{
        border-color: {BORDER_FOCUS};
    }}
    QComboBox::drop-down {{
        border-left: 1px solid {BORDER};
        background: {BG_HOVER};
        width: 20px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {BG_MID};
        color: {TEXT};
        border: 1px solid {BORDER};
        selection-background-color: {BG_HOVER};
    }}

    /* ── Buttons ── */
    QPushButton {{
        background-color: {BG_LIGHT};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: 4px;
        padding: 6px 14px;
        min-height: 18px;
    }}
    QPushButton:hover {{
        background-color: {BG_HOVER};
        border-color: {ACCENT};
        color: {TEXT_BRIGHT};
    }}
    QPushButton:pressed {{
        background-color: {ACCENT};
        color: {TEXT_BRIGHT};
    }}
    QPushButton:disabled {{
        color: {TEXT_DIM};
        background-color: {BG_DARK};
        border-color: {BORDER};
    }}

    /* Primary action button style — use with setObjectName("primaryButton") */
    QPushButton#primaryButton {{
        background-color: {ACCENT};
        color: {TEXT_BRIGHT};
        font-weight: bold;
        border: none;
    }}
    QPushButton#primaryButton:hover {{
        background-color: {ACCENT_HOVER};
    }}

    /* ── Tables ── */
    QTableWidget, QTableView {{
        background-color: {BG_MID};
        alternate-background-color: {BG_LIGHT};
        color: {TEXT};
        border: 1px solid {BORDER};
        gridline-color: {BORDER};
        selection-background-color: {BG_HOVER};
        selection-color: {TEXT_BRIGHT};
    }}
    QTableWidget::item, QTableView::item {{
        padding: 3px 6px;
    }}
    QTableWidget::item:hover, QTableView::item:hover {{
        background-color: {BG_HOVER};
        color: {TEXT_BRIGHT};
    }}
    QHeaderView::section {{
        background-color: {BG_DARK};
        color: {TEXT_DIM};
        border: none;
        border-bottom: 2px solid {BORDER};
        border-right: 1px solid {BORDER};
        padding: 5px 8px;
        font-weight: bold;
        font-size: 11px;
        text-transform: uppercase;
    }}
    QHeaderView::section:hover {{
        color: {TEXT_BRIGHT};
    }}

    /* ── Tab widget ── */
    QTabWidget::pane {{
        border: 1px solid {BORDER};
        background-color: {BG_DARK};
    }}
    QTabBar::tab {{
        background-color: {BG_MID};
        color: {TEXT_DIM};
        border: 1px solid {BORDER};
        border-bottom: none;
        padding: 8px 16px;
        margin-right: 2px;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
    }}
    QTabBar::tab:selected {{
        background-color: {BG_DARK};
        color: {TEXT_BRIGHT};
        border-bottom: 2px solid {ACCENT};
    }}
    QTabBar::tab:hover:!selected {{
        background-color: {BG_HOVER};
        color: {TEXT};
    }}

    /* ── Group boxes ── */
    QGroupBox {{
        color: {TEXT_BRIGHT};
        border: 1px solid {BORDER};
        border-radius: 6px;
        margin-top: 12px;
        padding-top: 16px;
        font-weight: bold;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
        color: {ACCENT};
    }}

    /* ── Scroll areas ── */
    QScrollArea {{
        border: none;
        background: transparent;
    }}
    QScrollBar:vertical {{
        background: {BG_DARK};
        width: 10px;
        border: none;
    }}
    QScrollBar::handle:vertical {{
        background: {BORDER};
        border-radius: 5px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {TEXT_DIM};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar:horizontal {{
        background: {BG_DARK};
        height: 10px;
        border: none;
    }}
    QScrollBar::handle:horizontal {{
        background: {BORDER};
        border-radius: 5px;
        min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {TEXT_DIM};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}

    /* ── Check boxes ── */
    QCheckBox {{
        color: {TEXT};
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid {BORDER};
        border-radius: 3px;
        background-color: {BG_LIGHT};
    }}
    QCheckBox::indicator:checked {{
        background-color: {ACCENT};
        border-color: {ACCENT};
    }}

    /* ── List widgets ── */
    QListWidget {{
        background-color: {BG_LIGHT};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: 4px;
    }}
    QListWidget::item:selected {{
        background-color: {BG_HOVER};
    }}

    /* ── Splitter ── */
    QSplitter::handle {{
        background-color: {BORDER};
    }}
    QSplitter::handle:horizontal {{
        width: 3px;
    }}
    QSplitter::handle:vertical {{
        height: 3px;
    }}

    /* ── Status bar ── */
    QStatusBar {{
        background-color: {BG_MID};
        color: {TEXT_DIM};
        border-top: 1px solid {BORDER};
    }}

    /* ── Dialog button box ── */
    QDialogButtonBox QPushButton {{
        min-width: 80px;
    }}

    /* ── Tooltip ── */
    QToolTip {{
        background-color: {BG_MID};
        color: {TEXT};
        border: 1px solid {BORDER};
        padding: 4px;
    }}

    /* ── Calendar popup ── */
    QCalendarWidget {{
        background-color: {BG_MID};
        color: {TEXT};
    }}
    QCalendarWidget QTableView {{
        alternate-background-color: {BG_LIGHT};
        selection-background-color: {ACCENT};
    }}
    """


# ── Color constants for use in code (e.g. table cell foreground) ──
PROFIT_COLOR = GREEN
LOSS_COLOR = RED
PROFIT_BG_COLOR = GREEN_BG
LOSS_BG_COLOR = RED_BG
NEUTRAL_COLOR = TEXT_DIM
