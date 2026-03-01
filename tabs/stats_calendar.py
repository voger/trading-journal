"""Summary Stats tab — calendar heatmap and day detail dialog."""
import calendar as _calendar
from datetime import date as _date

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QWidget, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QFrame, QDialog, QDialogButtonBox,
    QScrollArea, QGridLayout,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

from database import get_daily_pnl, get_account, effective_pnl

# Force English month names regardless of system locale
_MONTH_NAMES = [
    '', 'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
]


class DayDetailDialog(QDialog):
    """Shows individual trade details for a clicked calendar day."""

    def __init__(self, date_str, trades, currency, conn, parent=None):
        super().__init__(parent)
        from datetime import datetime as _dt
        self._conn = conn
        self._trades = trades
        self.setWindowTitle(f"Closed trades — {date_str}")
        self.setMinimumSize(680, 320)
        self.resize(760, 400)

        lay = QVBoxLayout(self)

        # Summary line
        total_pnl = sum(effective_pnl(t) for t in trades)
        cur = f" {currency}" if currency else ''
        color = '#008200' if total_pnl > 0 else '#c80000' if total_pnl < 0 else '#666'
        n = len(trades)
        summary = QLabel(
            f"<b>{n}</b> closed trade{'s' if n != 1 else ''} &nbsp;|&nbsp; "
            f"Net P&L: <b style='color:{color}'>{total_pnl:+.2f}{cur}</b>"
        )
        summary.setTextFormat(Qt.TextFormat.RichText)
        summary.setStyleSheet("padding: 4px 2px; font-size: 12px;")
        lay.addWidget(summary)

        # Trade table
        cols = ['Symbol', 'Dir', 'Setup', 'Entry', 'Exit', 'Duration', f'P&L{cur}']
        tbl = QTableWidget(len(trades), len(cols))
        tbl.setHorizontalHeaderLabels(cols)
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tbl.setAlternatingRowColors(True)
        tbl.setSortingEnabled(True)
        h = tbl.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)

        profit_fg = QColor(0, 130, 0)
        loss_fg   = QColor(200, 0, 0)
        bold = QFont("", -1, QFont.Weight.Bold)

        tbl.setSortingEnabled(False)
        for row, t in enumerate(trades):
            pnl = effective_pnl(t)

            # Duration
            dur_str = '—'
            try:
                entry_dt = _dt.strptime(t['entry_date'][:19], '%Y-%m-%d %H:%M:%S')
                exit_dt  = _dt.strptime(t['exit_date'][:19],  '%Y-%m-%d %H:%M:%S')
                delta = exit_dt - entry_dt
                d, s = delta.days, delta.seconds
                h_part, m_part = s // 3600, (s % 3600) // 60
                if d > 0:
                    dur_str = f"{d}d {h_part}h"
                else:
                    dur_str = f"{h_part}h {m_part}m"
            except (ValueError, TypeError):
                pass

            # Entry label: show date+time if different day from exit date
            entry_label = '—'
            try:
                entry_d = t['entry_date'][:10]
                entry_label = (t['entry_date'][11:16]
                               if entry_d == date_str
                               else f"{entry_d} {t['entry_date'][11:16]}")
            except (TypeError, IndexError):
                pass

            exit_label = t['exit_date'][11:16] if t['exit_date'] else '—'

            cells = [
                t['symbol'] or '—',
                (t['direction'] or '—').capitalize(),
                t['setup_name'] or '—',
                entry_label,
                exit_label,
                dur_str,
                f"{pnl:+.2f}",
            ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 0:  # store trade ID for double-click lookup
                    item.setData(Qt.ItemDataRole.UserRole, t['id'])
                if col == len(cells) - 1:  # P&L column
                    item.setForeground(profit_fg if pnl > 0 else loss_fg if pnl < 0 else QColor(100, 100, 100))
                    item.setFont(bold)
                tbl.setItem(row, col, item)

        tbl.setSortingEnabled(True)
        tbl.doubleClicked.connect(self._on_row_double_clicked)
        hint = QLabel("Double-click a row to open full trade details.")
        hint.setStyleSheet("font-size: 10px; color: #888; padding: 2px;")
        lay.addWidget(tbl)
        lay.addWidget(hint)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _on_row_double_clicked(self, index):
        from dialogs import TradeDialog
        from database import get_trade
        id_item = self.sender().item(index.row(), 0)
        if id_item is None:
            return
        tid = id_item.data(Qt.ItemDataRole.UserRole)
        if tid is None:
            return
        trade = get_trade(self._conn, tid)
        if trade is None:
            return
        dlg = TradeDialog(self, self._conn, trade=trade)
        dlg.exec()


class CalendarHeatmapWidget(QWidget):
    """Monthly P&L calendar heatmap.

    Displays a grid of day cells coloured green/red by net P&L for the
    selected month. Navigate with Prev/Next buttons. Requires a specific
    account to be selected (not All Accounts).
    """

    def __init__(self, conn, get_aid_fn, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._get_aid = get_aid_fn
        today = _date.today()
        self._year = today.year
        self._month = today.month
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 8, 12, 8)
        outer.setSpacing(6)

        # Navigation bar
        nav = QHBoxLayout()
        self._btn_prev = QPushButton("◀ Prev")
        self._btn_next = QPushButton("Next ▶")
        for btn in (self._btn_prev, self._btn_next):
            btn.setFixedWidth(80)
        self._lbl_month = QLabel()
        self._lbl_month.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_month.setFont(QFont("", 13, QFont.Weight.Bold))
        nav.addWidget(self._btn_prev)
        nav.addStretch()
        nav.addWidget(self._lbl_month)
        nav.addStretch()
        nav.addWidget(self._btn_next)
        outer.addLayout(nav)

        # Monthly summary label
        self._lbl_summary = QLabel("")
        self._lbl_summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_summary.setTextFormat(Qt.TextFormat.RichText)
        self._lbl_summary.setStyleSheet("font-size: 12px; padding: 2px;")
        outer.addWidget(self._lbl_summary)

        # Scrollable calendar area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._cal_container = QWidget()
        self._grid = QGridLayout(self._cal_container)
        self._grid.setSpacing(3)
        scroll.setWidget(self._cal_container)
        outer.addWidget(scroll, stretch=1)

        self._btn_prev.clicked.connect(self._prev_month)
        self._btn_next.clicked.connect(self._next_month)

    def _prev_month(self):
        if self._month == 1:
            self._month = 12
            self._year -= 1
        else:
            self._month -= 1
        self._rebuild()

    def _next_month(self):
        if self._month == 12:
            self._month = 1
            self._year += 1
        else:
            self._month += 1
        self._rebuild()

    def refresh(self, conn=None):
        if conn is not None:
            self._conn = conn
        self._rebuild()

    def _rebuild(self):
        # Clear existing grid cells
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._lbl_month.setText(
            f"{_MONTH_NAMES[self._month]} {self._year}"
        )

        aid = self._get_aid()
        if aid is None:
            lbl = QLabel("Select an account to view the calendar.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color: #888; font-size: 12px;")
            self._grid.addWidget(lbl, 0, 0)
            self._lbl_summary.setText("")
            return

        daily = get_daily_pnl(self._conn, aid, self._year, self._month)

        # Monthly totals
        if daily:
            total_pnl = sum(d['net_pnl'] for d in daily.values())
            total_trades = sum(d['trade_count'] for d in daily.values())
            color = '#008200' if total_pnl > 0 else '#c80000' if total_pnl < 0 else '#666'
            closed_word = 'closed trade' if total_trades == 1 else 'closed trades'
            self._lbl_summary.setText(
                f"Month total: <b style='color:{color}'>{total_pnl:+.2f}</b>"
                f"&nbsp;&nbsp;({total_trades} {closed_word})"
            )
        else:
            self._lbl_summary.setText("No closed trades this month.")

        # Day-of-week headers (Monday-first)
        day_headers = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        for col, name in enumerate(day_headers):
            lbl = QLabel(name)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFont(QFont("", -1, QFont.Weight.Bold))
            lbl.setStyleSheet("color: #555; padding-bottom: 4px;")
            self._grid.addWidget(lbl, 0, col)

        # Color scale: intensity relative to the month's max |P&L|
        pnl_values = [d['net_pnl'] for d in daily.values()]
        max_abs = max((abs(v) for v in pnl_values), default=1) or 1

        today = _date.today()
        cal_weeks = _calendar.monthcalendar(self._year, self._month)

        for row_idx, week in enumerate(cal_weeks):
            for col_idx, day in enumerate(week):
                if day == 0:
                    # Empty slot before/after month
                    placeholder = QFrame()
                    placeholder.setStyleSheet(
                        "QFrame { background: transparent; border: none; }"
                    )
                    placeholder.setMinimumSize(70, 60)
                    self._grid.addWidget(placeholder, row_idx + 1, col_idx)
                    continue

                is_today = (
                    self._year == today.year
                    and self._month == today.month
                    and day == today.day
                )
                day_data = daily.get(day)
                date_str = f"{self._year}-{self._month:02d}-{day:02d}"
                cell = self._make_cell(day, day_data, max_abs, is_today, date_str)
                self._grid.addWidget(cell, row_idx + 1, col_idx)

    def _on_day_clicked(self, date_str):
        """Show detailed trade list for the clicked day."""
        aid = self._get_aid()
        if aid is None:
            return
        rows = self._conn.execute(
            """SELECT t.*, i.symbol, st.name as setup_name
               FROM trades t
               JOIN instruments i ON t.instrument_id = i.id
               LEFT JOIN setup_types st ON t.setup_type_id = st.id
               WHERE t.account_id = ? AND t.status = 'closed'
                 AND t.is_excluded = 0 AND DATE(t.exit_date) = ?
               ORDER BY t.exit_date""",
            [aid, date_str]
        ).fetchall()
        if not rows:
            return
        acct = get_account(self._conn, aid)
        currency = acct['currency'] if acct else ''
        dlg = DayDetailDialog(date_str, rows, currency, self._conn, self)
        dlg.exec()

    def _make_cell(self, day, day_data, max_abs, is_today, date_str):
        """Build a single day cell."""
        cell = QFrame()
        cell.setFrameShape(QFrame.Shape.StyledPanel)
        cell.setMinimumSize(70, 60)

        lay = QVBoxLayout(cell)
        lay.setContentsMargins(5, 4, 5, 4)
        lay.setSpacing(1)

        # Day number
        day_lbl = QLabel(str(day))
        day_weight = QFont.Weight.Bold if is_today else QFont.Weight.Normal
        day_lbl.setFont(QFont("", 9, day_weight))
        day_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        lay.addWidget(day_lbl)

        if day_data:
            pnl = day_data['net_pnl']
            count = day_data['trade_count']

            pnl_lbl = QLabel(f"{pnl:+.2f}")
            pnl_lbl.setFont(QFont("", 10, QFont.Weight.Bold))
            pnl_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(pnl_lbl)

            cnt_lbl = QLabel(f"{count} closed")
            cnt_lbl.setFont(QFont("", 7))
            cnt_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(cnt_lbl)

            # Background colour proportional to |P&L| / max_abs
            intensity = min(abs(pnl) / max_abs, 1.0)
            if pnl > 0:
                r = int(232 - intensity * 160)
                g = int(245 - intensity * 105)
                b = int(233 - intensity * 180)
                border_col = '#2e7d32' if intensity > 0.3 else '#81c784'
            elif pnl < 0:
                r = int(255 - intensity * 110)
                g = int(235 - intensity * 215)
                b = int(238 - intensity * 220)
                border_col = '#c62828' if intensity > 0.3 else '#e57373'
            else:
                r, g, b = 240, 240, 240
                border_col = '#aaa'

            text_color = '#fff' if intensity > 0.65 else '#000'
            bg = f'#{r:02x}{g:02x}{b:02x}'

            pnl_lbl.setStyleSheet(f"color: {text_color};")
            cnt_lbl.setStyleSheet(f"color: {text_color};")
            day_lbl.setStyleSheet(f"color: {text_color};")

            border_width = '2px' if is_today else '1px'
            border_color = '#1565c0' if is_today else border_col
            cell.setStyleSheet(
                f"QFrame {{ background-color: {bg}; "
                f"border: {border_width} solid {border_color}; "
                f"border-radius: 4px; }}"
            )

            cell.setToolTip(
                f"{date_str}\n"
                f"Net P&L: {pnl:+.2f}\n"
                f"Closed trades: {count}\n"
                f"Click for details"
            )
            cell.setCursor(Qt.CursorShape.PointingHandCursor)
            cell.mousePressEvent = lambda e, d=date_str: self._on_day_clicked(d)
        else:
            # No trades that day
            if is_today:
                cell.setStyleSheet(
                    "QFrame { background-color: #fff; "
                    "border: 2px solid #1565c0; border-radius: 4px; }"
                )
            else:
                cell.setStyleSheet(
                    "QFrame { background-color: #fafafa; "
                    "border: 1px solid #e0e0e0; border-radius: 4px; }"
                )
            day_lbl.setStyleSheet("color: #aaa;")

        return cell
