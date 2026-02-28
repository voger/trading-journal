"""
Trading Journal — Theme
Apply dark mode: app.setStyleSheet(get_stylesheet()); set_dark(True)
Clear (light mode): app.setStyleSheet(""); set_dark(False)
"""
import os as _os, sys as _sys

# Resource dir: _MEIPASS in frozen build, else the project directory
if getattr(_sys, 'frozen', False) and hasattr(_sys, '_MEIPASS'):
    _RESOURCE_DIR = _sys._MEIPASS
else:
    _RESOURCE_DIR = _os.path.dirname(_os.path.abspath(__file__))

_ARROW_PATH    = _os.path.join(_RESOURCE_DIR, 'icons', 'arrow_down.svg').replace('\\', '/')
_ARROW_UP_PATH = _os.path.join(_RESOURCE_DIR, 'icons', 'arrow_up.svg').replace('\\', '/')

# ── Dark state ────────────────────────────────────────────────────────────
_dark = False

def is_dark():
    return _dark

def set_dark(value: bool):
    global _dark
    _dark = value


# ── Colour palette (neutral dark gray — no color tint) ────────────────────
BG_DARK  = "#111111"   # near-pure black — main window background
BG_MID   = "#1a1a1a"   # panels, cards, table background
BG_LIGHT = "#222222"   # input fields, alternate table rows
BG_HOVER = "#2c2c2c"   # hover / selection highlight
BORDER   = "#2e2e2e"   # subtle borders
BORDER_FOCUS = "#3d7cf4"

TEXT      = "#e8e8e8"  # primary text
TEXT_DIM  = "#666666"  # secondary / placeholder
TEXT_BRIGHT = "#ffffff"

GREEN    = "#6bbc9a"   # profit — pale sage-green  (for UI text, badges, stats)
GREEN_BG = "#0d2b1f"
GREEN_VIV = "#00c896"  # profit — vivid teal-green (for chart candles)
RED      = "#d97580"   # loss   — pale pinkish-red  (for UI text, badges, stats)
RED_BG   = "#2a0d14"
RED_VIV  = "#ff4757"   # loss   — vivid red          (for chart candles)
ACCENT   = "#3d7cf4"   # buttons, links, focus — medium blue
ACCENT_HOVER = "#5d96f6"


# ── QSS stylesheet ────────────────────────────────────────────────────────

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
    QMenu::separator {{
        height: 1px;
        background: {BORDER};
        margin: 3px 8px;
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
    QLineEdit::placeholder {{ color: {TEXT_DIM}; }}
    QSpinBox::up-button, QDoubleSpinBox::up-button, QDateTimeEdit::up-button {{
        border-left: 1px solid {BORDER};
        background: {BG_HOVER};
        width: 16px;
    }}
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow, QDateTimeEdit::up-arrow {{
        image: url({_ARROW_UP_PATH});
        width: 8px; height: 5px;
    }}
    QSpinBox::down-button, QDoubleSpinBox::down-button, QDateTimeEdit::down-button {{
        border-left: 1px solid {BORDER};
        background: {BG_HOVER};
        width: 16px;
    }}
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow, QDateTimeEdit::down-arrow {{
        image: url({_ARROW_PATH});
        width: 8px; height: 5px;
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
    QComboBox:hover {{ border-color: {BORDER_FOCUS}; }}
    QComboBox::drop-down {{
        border-left: 1px solid {BORDER};
        background: {BG_HOVER};
        width: 20px;
    }}
    QComboBox::down-arrow {{
        image: url("{_ARROW_PATH}");
        width: 10px;
        height: 6px;
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
        padding: 4px 3px;
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
        padding: 5px 6px;
        font-weight: bold;
        font-size: 12px;
    }}
    QHeaderView::section:hover {{ color: {TEXT_BRIGHT}; }}

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

    /* ── Scroll bars ── */
    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{
        background: {BG_DARK}; width: 10px; border: none;
    }}
    QScrollBar::handle:vertical {{
        background: {BORDER}; border-radius: 5px; min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {TEXT_DIM}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
    QScrollBar:horizontal {{
        background: {BG_DARK}; height: 10px; border: none;
    }}
    QScrollBar::handle:horizontal {{
        background: {BORDER}; border-radius: 5px; min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{ background: {TEXT_DIM}; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}

    /* ── Check boxes ── */
    QCheckBox {{ color: {TEXT}; spacing: 8px; }}
    QCheckBox::indicator {{
        width: 16px; height: 16px;
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
        outline: none;
    }}
    QListWidget::item {{ padding: 8px 12px; border-bottom: 1px solid {BORDER}; }}
    QListWidget::item:selected {{ background-color: {ACCENT}; color: {TEXT_BRIGHT}; }}
    QListWidget::item:hover:!selected {{ background-color: {BG_HOVER}; }}

    /* ── Splitter ── */
    QSplitter::handle {{ background-color: {BORDER}; }}
    QSplitter::handle:horizontal {{ width: 3px; }}
    QSplitter::handle:vertical {{ height: 3px; }}

    /* ── Status bar ── */
    QStatusBar {{
        background-color: {BG_MID};
        color: {TEXT_DIM};
        border-top: 1px solid {BORDER};
    }}

    /* ── Frames (VLine/HLine separators) ── */
    QFrame[frameShape="4"],
    QFrame[frameShape="5"] {{
        color: {BORDER};
    }}

    /* ── KPI Cards ── */
    KPICard {{
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 6px;
    }}

    /* ── Dialog button box ── */
    QDialogButtonBox QPushButton {{ min-width: 80px; }}

    /* ── Tooltips ── */
    QToolTip {{
        background-color: {BG_MID};
        color: {TEXT};
        border: 1px solid {BORDER};
        padding: 4px;
    }}

    /* ── Text browser (stats overview) ── */
    QTextBrowser {{
        background-color: {BG_MID};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: 4px;
        padding: 6px;
    }}

    /* ── Calendar popup ── */
    QCalendarWidget {{ background-color: {BG_MID}; color: {TEXT}; }}
    QCalendarWidget QTableView {{
        alternate-background-color: {BG_LIGHT};
        selection-background-color: {ACCENT};
    }}
    """


# ── Matplotlib helpers ────────────────────────────────────────────────────

def apply_mpl_dark(fig, *axes):
    """Apply dark theme to a matplotlib Figure and its axes."""
    fig.patch.set_facecolor(BG_MID)
    for ax in axes:
        ax.set_facecolor(BG_LIGHT)
        ax.tick_params(colors=TEXT, labelsize=8)
        ax.xaxis.label.set_color(TEXT)
        ax.yaxis.label.set_color(TEXT)
        if ax.get_title():
            ax.title.set_color(TEXT)
        for spine in ax.spines.values():
            spine.set_color(BORDER)
        ax.grid(True, color=BORDER, alpha=0.5)


def make_mpf_style():
    """Return an mplfinance style matching the current theme."""
    import mplfinance as mpf
    if _dark:
        mc = mpf.make_marketcolors(
            up=GREEN_VIV, down=RED_VIV,
            edge={'up': '#00a87e', 'down': '#e03040'},
            wick={'up': '#00a87e', 'down': '#e03040'})
        return mpf.make_mpf_style(
            marketcolors=mc,
            facecolor=BG_MID,
            gridstyle='-', gridcolor=BORDER,
            y_on_right=True,
            rc={
                'axes.labelcolor': TEXT,
                'xtick.color': TEXT,
                'ytick.color': TEXT,
                'axes.edgecolor': BORDER,
                'figure.facecolor': BG_DARK,
                'axes.facecolor': BG_MID,
            })
    else:
        mc = mpf.make_marketcolors(
            up='#26a69a', down='#ef5350',
            edge={'up': '#1b7a6e', 'down': '#c62828'},
            wick={'up': '#1b7a6e', 'down': '#c62828'})
        return mpf.make_mpf_style(
            marketcolors=mc, facecolor='#fafafa',
            gridstyle='-', gridcolor='#e8e8e8',
            y_on_right=True)


# ── Colour constants for use in code ─────────────────────────────────────
PROFIT_COLOR   = GREEN
LOSS_COLOR     = RED
PROFIT_BG_COLOR = GREEN_BG
LOSS_BG_COLOR  = RED_BG
NEUTRAL_COLOR  = TEXT_DIM
