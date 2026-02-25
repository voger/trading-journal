"""Summary Stats tab — overview + analytics breakdowns + formula editor."""
import calendar as _calendar
from datetime import timedelta, date as _date

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QWidget, QLabel,
    QComboBox, QAbstractItemView, QMessageBox, QPlainTextEdit,
    QFormLayout, QGroupBox, QSizePolicy, QFrame, QDialog,
    QDialogButtonBox, QLineEdit, QGridLayout, QScrollArea,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

from tabs import BaseTab
from database import (
    get_account, get_trade_stats, get_all_formulas, get_trade_breakdowns,
    update_formula, reset_formulas_to_defaults, get_formula,
    get_advanced_stats, get_daily_pnl,
    get_setup_performance, get_r_multiple_distribution,
)


# ── Breakdown table columns ──────────────────────────────────────────────
_BD_COLUMNS = [
    ('group_name',    'Group',     180),
    ('total_trades',  'Trades',     60),
    ('winners',       'Wins',       50),
    ('losers',        'Losses',     55),
    ('win_rate',      'Win%',       60),
    ('net_pnl',       'Net P&L',    90),
    ('avg_win',       'Avg Win',    80),
    ('avg_loss',      'Avg Loss',   80),
    ('expectancy',    'Expect.',    80),
    ('profit_factor', 'PF',         60),
]


class BreakdownTable(QWidget):
    """Reusable sortable breakdown table for a given group_by dimension."""

    def __init__(self, group_by, group_label, parent=None):
        super().__init__(parent)
        self.group_by = group_by
        self.group_label = group_label
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("font-size: 12px; padding: 4px;")
        self.summary_label.setWordWrap(True)
        lay.addWidget(self.summary_label)

        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        headers = [c[0] for c in _BD_COLUMNS]
        labels = [c[1] for c in _BD_COLUMNS]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(labels)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i, (_, _, width) in enumerate(_BD_COLUMNS):
            if i > 0:
                self.table.setColumnWidth(i, width)
        lay.addWidget(self.table)

    def populate(self, breakdowns, currency=''):
        """Fill table with breakdown data."""
        # Update currency-bearing column headers
        cur = f" ({currency})" if currency else ''
        for col, (key, label, _) in enumerate(_BD_COLUMNS):
            suffix = cur if key in ('net_pnl', 'avg_win', 'avg_loss', 'expectancy') else ''
            self.table.setHorizontalHeaderItem(col, QTableWidgetItem(label + suffix))
        profit_fg = QColor(0, 130, 0)
        loss_fg = QColor(200, 0, 0)
        neutral_fg = QColor(100, 100, 100)
        bold = QFont("", -1, QFont.Weight.Bold)

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(breakdowns))

        best_pnl = max((b['net_pnl'] for b in breakdowns), default=0)
        worst_pnl = min((b['net_pnl'] for b in breakdowns), default=0)

        for row, bd in enumerate(breakdowns):
            for col, (key, _, _) in enumerate(_BD_COLUMNS):
                val = bd.get(key, '')

                # Format values
                if key == 'win_rate':
                    text = f"{val:.1f}%"
                elif key == 'profit_factor':
                    text = f"{val:.2f}" if val != float('inf') else "∞"
                elif key in ('net_pnl', 'avg_win', 'avg_loss', 'expectancy'):
                    text = f"{val:+.2f}" if isinstance(val, (int, float)) else str(val)
                elif key == 'group_name':
                    text = str(val)
                else:
                    text = str(val)

                item = QTableWidgetItem()
                # Store numeric value for sorting
                if isinstance(val, (int, float)) and key != 'group_name':
                    item.setData(Qt.ItemDataRole.DisplayRole, text)
                    item.setData(Qt.ItemDataRole.UserRole, float(val) if val != float('inf') else 1e10)
                else:
                    item.setText(text)

                # Color coding
                if key in ('net_pnl', 'expectancy'):
                    if isinstance(val, (int, float)):
                        item.setForeground(profit_fg if val > 0 else loss_fg if val < 0 else neutral_fg)
                        item.setFont(bold)
                elif key == 'win_rate':
                    item.setForeground(profit_fg if val >= 50 else loss_fg)
                elif key == 'profit_factor':
                    pf = val if val != float('inf') else 999
                    item.setForeground(profit_fg if pf >= 1 else loss_fg)

                # Highlight best/worst rows
                if key == 'group_name':
                    if bd['net_pnl'] == best_pnl and best_pnl > 0:
                        item.setFont(bold)
                        item.setForeground(profit_fg)
                    elif bd['net_pnl'] == worst_pnl and worst_pnl < 0:
                        item.setFont(bold)
                        item.setForeground(loss_fg)

                self.table.setItem(row, col, item)

        self.table.setSortingEnabled(True)

        # Summary text
        if breakdowns:
            total_trades = sum(b['total_trades'] for b in breakdowns)
            total_pnl = sum(b['net_pnl'] for b in breakdowns)
            best = max(breakdowns, key=lambda b: b['net_pnl'])
            worst = min(breakdowns, key=lambda b: b['net_pnl'])
            pc = '#008200' if total_pnl > 0 else '#c80000' if total_pnl < 0 else '#666'
            self.summary_label.setTextFormat(Qt.TextFormat.RichText)
            parts = [
                f"<b>{len(breakdowns)}</b> {self.group_label}s",
                f"<b>{total_trades}</b> trades",
                f"Net P&L: <b style='color:{pc}'>{total_pnl:+.2f}</b>",
            ]
            if best['net_pnl'] > 0:
                parts.append(f"Best: <b style='color:#008200'>{best['group_name']}</b> ({best['net_pnl']:+.2f})")
            if worst['net_pnl'] < 0:
                parts.append(f"Worst: <b style='color:#c80000'>{worst['group_name']}</b> ({worst['net_pnl']:+.2f})")
            self.summary_label.setText(" &nbsp;|&nbsp; ".join(parts))
        else:
            self.summary_label.setText("No data for this breakdown.")


# ── Formula Editor ────────────────────────────────────────────────────────

class FormulaEditDialog(QDialog):
    """Dialog to edit a single formula definition."""

    def __init__(self, formula_row, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit Formula — {formula_row['display_name']}")
        self.setMinimumWidth(500)
        self.formula_row = formula_row

        layout = QVBoxLayout(self)

        # Read-only key
        info = QLabel(f"<b>Metric Key:</b> {formula_row['metric_key']}")
        info.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(info)

        form = QFormLayout()

        self.display_name_edit = QLineEdit(formula_row['display_name'] or '')
        form.addRow("Display Name:", self.display_name_edit)

        self.category_edit = QLineEdit(formula_row['category'] or '')
        form.addRow("Category:", self.category_edit)

        self.formula_edit = QPlainTextEdit(formula_row['formula_text'] or '')
        self.formula_edit.setMaximumHeight(60)
        form.addRow("Formula:", self.formula_edit)

        self.desc_edit = QPlainTextEdit(formula_row['description'] or '')
        self.desc_edit.setMaximumHeight(80)
        form.addRow("Description:", self.desc_edit)

        self.interp_edit = QPlainTextEdit(formula_row['interpretation'] or '')
        self.interp_edit.setMaximumHeight(80)
        form.addRow("Interpretation:", self.interp_edit)

        layout.addLayout(form)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

    def get_data(self):
        return {
            'display_name': self.display_name_edit.text().strip(),
            'category': self.category_edit.text().strip(),
            'formula_text': self.formula_edit.toPlainText().strip(),
            'description': self.desc_edit.toPlainText().strip(),
            'interpretation': self.interp_edit.toPlainText().strip(),
        }


class FormulaEditorWidget(QWidget):
    """Table of formula definitions with edit and reset-to-defaults."""

    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.conn = conn
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)

        desc = QLabel(
            "These formulas define the metrics shown in the Overview and "
            "breakdown tables. Hover the ⓘ icons in the Overview tab to see "
            "these descriptions. Edit any formula to customise the text, "
            "or reset to defaults if needed."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("padding: 6px; font-size: 11px;")
        lay.addWidget(desc)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            'Metric', 'Category', 'Formula', 'Description', 'Interpretation',
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(self._on_edit)
        lay.addWidget(self.table)

        btn_row = QHBoxLayout()
        b_edit = QPushButton("Edit Selected...")
        b_edit.clicked.connect(self._on_edit)
        btn_row.addWidget(b_edit)
        btn_row.addStretch()
        b_reset = QPushButton("Reset All to Defaults")
        b_reset.clicked.connect(self._on_reset)
        btn_row.addWidget(b_reset)
        lay.addLayout(btn_row)

        self.populate()

    def populate(self):
        formulas = get_all_formulas(self.conn)
        self.table.setRowCount(len(formulas))
        self._formulas = formulas
        for row, f in enumerate(formulas):
            self.table.setItem(row, 0, QTableWidgetItem(f['display_name']))
            self.table.setItem(row, 1, QTableWidgetItem(f['category']))
            self.table.setItem(row, 2, QTableWidgetItem(f['formula_text']))
            self.table.setItem(row, 3, QTableWidgetItem(f['description']))
            self.table.setItem(row, 4, QTableWidgetItem(f['interpretation'] or ''))

    def _on_edit(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._formulas):
            return
        f = self._formulas[row]
        dlg = FormulaEditDialog(f, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            update_formula(self.conn, f['metric_key'], **data)
            self.populate()

    def _on_reset(self):
        reply = QMessageBox.question(
            self, "Reset Formulas",
            "Reset all formula definitions to their original defaults?\n\n"
            "Any customisations will be lost.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            reset_formulas_to_defaults(self.conn)
            self.populate()


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
            f"{_calendar.month_name[self._month]} {self._year}"
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
            trade_word = 'trade' if total_trades == 1 else 'trades'
            self._lbl_summary.setText(
                f"Month total: <b style='color:{color}'>{total_pnl:+.2f}</b>"
                f"&nbsp;&nbsp;({total_trades} {trade_word})"
            )
        else:
            self._lbl_summary.setText("No trades this month.")

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
                cell = self._make_cell(day, day_data, max_abs, is_today)
                self._grid.addWidget(cell, row_idx + 1, col_idx)

    def _make_cell(self, day, day_data, max_abs, is_today):
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

            trade_word = 'trade' if count == 1 else 'trades'
            cnt_lbl = QLabel(f"{count} {trade_word}")
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
                f"{self._year}-{self._month:02d}-{day:02d}\n"
                f"Net P&L: {pnl:+.2f}\n"
                f"Trades: {count}"
            )
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


class SetupPerformanceWidget(QWidget):
    """Per-setup performance breakdown: trades, win%, avg R, avg P&L, net P&L, avg duration."""

    _COLS = [
        ('setup_name',   'Setup',    200),
        ('total_trades', 'Trades',    60),
        ('win_rate',     'Win %',     65),
        ('avg_r',        'Avg R',     65),
        ('avg_pnl',      'Avg P&L',   80),
        ('net_pnl',      'Net P&L',   90),
        ('avg_duration', 'Avg Days',  75),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("font-size: 12px; padding: 4px;")
        self.summary_label.setWordWrap(True)
        lay.addWidget(self.summary_label)

        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setColumnCount(len(self._COLS))
        self.table.setHorizontalHeaderLabels([c[1] for c in self._COLS])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i, (_, _, w) in enumerate(self._COLS):
            if i > 0:
                self.table.setColumnWidth(i, w)
        lay.addWidget(self.table)

    def populate(self, rows, currency=''):
        cur = f" ({currency})" if currency else ''
        for col, (key, label, _) in enumerate(self._COLS):
            suffix = cur if key in ('avg_pnl', 'net_pnl') else ''
            self.table.setHorizontalHeaderItem(col, QTableWidgetItem(label + suffix))

        profit_fg = QColor(0, 130, 0)
        loss_fg   = QColor(200, 0, 0)
        neutral_fg = QColor(100, 100, 100)
        bold = QFont("", -1, QFont.Weight.Bold)

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))

        for row_idx, r in enumerate(rows):
            for col, (key, _, _) in enumerate(self._COLS):
                val = r.get(key)

                if key == 'win_rate':
                    text = f"{val:.1f}%" if val is not None else "—"
                elif key == 'avg_r':
                    text = f"{val:+.2f}R" if val is not None else "—"
                elif key in ('avg_pnl', 'net_pnl'):
                    text = f"{val:+.2f}" if val is not None else "—"
                elif key == 'avg_duration':
                    text = f"{val:.1f}" if val is not None else "—"
                else:
                    text = str(val) if val is not None else "—"

                item = QTableWidgetItem()
                if isinstance(val, (int, float)) and key != 'setup_name':
                    item.setData(Qt.ItemDataRole.DisplayRole, text)
                    item.setData(Qt.ItemDataRole.UserRole, float(val))
                else:
                    item.setText(text)

                if key == 'win_rate' and val is not None:
                    item.setForeground(profit_fg if val >= 50 else loss_fg)
                elif key == 'avg_r' and val is not None:
                    item.setForeground(profit_fg if val > 0 else loss_fg if val < 0 else neutral_fg)
                    item.setFont(bold)
                elif key in ('avg_pnl', 'net_pnl') and val is not None:
                    item.setForeground(profit_fg if val > 0 else loss_fg if val < 0 else neutral_fg)
                    item.setFont(bold)

                self.table.setItem(row_idx, col, item)

        self.table.setSortingEnabled(True)

        if rows:
            n = sum(r['total_trades'] for r in rows)
            net = sum(r['net_pnl'] for r in rows)
            pc = '#008200' if net > 0 else '#c80000' if net < 0 else '#666'
            self.summary_label.setTextFormat(Qt.TextFormat.RichText)
            self.summary_label.setText(
                f"<b>{len(rows)}</b> setups &nbsp;|&nbsp; "
                f"<b>{n}</b> trades &nbsp;|&nbsp; "
                f"Net P&L: <b style='color:{pc}'>{net:+.2f}</b>"
            )
        else:
            self.summary_label.setText(
                "No data. Close trades with a setup type assigned to see per-setup stats."
            )


class RMultipleHistogramWidget(QWidget):
    """R-multiple distribution bar chart (6 buckets: <-2, -2–-1, -1–0, 0–1, 1–2, >2)."""

    _BUCKETS = ['< -2', '-2 to -1', '-1 to 0', '0 to 1', '1 to 2', '> 2']
    _COLORS  = ['#c62828', '#e57373', '#ffcdd2', '#c8e6c9', '#66bb6a', '#2e7d32']

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)

        self._canvas = None
        self._fig = None
        try:
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
            from matplotlib.figure import Figure
            self._fig = Figure(figsize=(8, 4), dpi=100)
            self._canvas = FigureCanvasQTAgg(self._fig)
            self._canvas.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            lay.addWidget(self._canvas)
        except ImportError:
            lbl = QLabel("matplotlib is required for this chart.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(lbl)

        self._note = QLabel("")
        self._note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._note.setStyleSheet("font-size: 11px; color: #666; padding: 4px;")
        self._note.setWordWrap(True)
        lay.addWidget(self._note)

    def populate(self, r_values, excluded_count=0):
        if self._fig is None:
            return

        self._fig.clear()
        ax = self._fig.add_subplot(111)

        if not r_values:
            ax.text(0.5, 0.5,
                    'No R-multiple data.\nAdd risk % to your closed trades.',
                    ha='center', va='center', fontsize=12, color='#888',
                    transform=ax.transAxes)
            ax.set_axis_off()
            self._note.setText(
                f"{excluded_count} trades excluded (no risk % set)." if excluded_count else ""
            )
            self._canvas.draw()
            return

        buckets = [0] * 6
        for r in r_values:
            if r < -2:
                buckets[0] += 1
            elif r < -1:
                buckets[1] += 1
            elif r < 0:
                buckets[2] += 1
            elif r <= 1:
                buckets[3] += 1
            elif r <= 2:
                buckets[4] += 1
            else:
                buckets[5] += 1

        bars = ax.bar(self._BUCKETS, buckets, color=self._COLORS,
                      edgecolor='#555', linewidth=0.5)

        for bar, count in zip(bars, buckets):
            if count > 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.3,
                    str(count),
                    ha='center', va='bottom', fontsize=9, fontweight='bold',
                )

        ax.set_ylabel('Trade Count', fontsize=10)
        ax.set_xlabel('R Multiple', fontsize=10)
        ax.set_title('R-Multiple Distribution', fontsize=11)
        ax.tick_params(axis='both', labelsize=8)
        ax.grid(axis='y', alpha=0.3)
        ax.set_ylim(bottom=0)
        self._fig.tight_layout(pad=1.2)

        note_parts = [f"{len(r_values)} trades plotted"]
        if excluded_count:
            note_parts.append(f"{excluded_count} excluded (no risk % set)")
        self._note.setText(" — ".join(note_parts))
        self._canvas.draw()


class StatsTab(BaseTab):
    def __init__(self, conn, get_aid_fn):
        super().__init__(conn, get_aid_fn)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Period filter row
        period_row = QHBoxLayout()
        period_row.addWidget(QLabel("Period:"))
        self.flt_period = QComboBox()
        self.flt_period.addItems([
            "All Time", "This Month", "Last Month",
            "This Year", "Last 30 Days", "Last 90 Days",
        ])
        self.flt_period.currentIndexChanged.connect(self.refresh)
        period_row.addWidget(self.flt_period)
        period_row.addStretch()
        layout.addLayout(period_row)

        # Inner tab widget for sub-tabs
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Sub-tab 1: Overview (existing summary)
        self.overview_widget = QWidget()
        ov_lay = QVBoxLayout(self.overview_widget)
        from PyQt6.QtWidgets import QTextBrowser
        self.stats_text = QTextBrowser()
        self.stats_text.setReadOnly(True)
        self.stats_text.setFont(QFont("Consolas", 11))
        self.stats_text.setOpenLinks(False)
        self.stats_text.anchorClicked.connect(self._on_info_clicked)
        ov_lay.addWidget(self.stats_text)
        self.tabs.addTab(self.overview_widget, "Overview")

        # Sub-tabs for breakdowns
        self.bd_tables = {}
        breakdowns = [
            ('instrument',  'Instrument',  'By Instrument'),
            ('setup',       'Setup',       'By Setup'),
            ('day_of_week', 'Day',         'By Day'),
            ('session',     'Session',     'By Session'),
            ('exit_reason', 'Exit Reason', 'By Exit Reason'),
            ('direction',   'Direction',   'By Direction'),
            ('month',       'Month',       'By Month'),
        ]
        for group_by, label, tab_title in breakdowns:
            bt = BreakdownTable(group_by, label)
            self.bd_tables[group_by] = bt
            self.tabs.addTab(bt, tab_title)

        # Setup performance sub-tab
        self.setup_perf = SetupPerformanceWidget()
        self.tabs.addTab(self.setup_perf, "Setup Stats")

        # R-multiple histogram sub-tab
        self.r_hist = RMultipleHistogramWidget()
        self.tabs.addTab(self.r_hist, "R Distribution")

        # Calendar heatmap sub-tab
        self.calendar_heatmap = CalendarHeatmapWidget(self.conn, self.aid)
        self.tabs.addTab(self.calendar_heatmap, "Calendar")

        # Formula editor sub-tab
        self.formula_editor = FormulaEditorWidget(self.conn)
        self.tabs.addTab(self.formula_editor, "Formulas")


    def _get_date_range(self):
        """Return (date_from, date_to) based on the period filter, or (None, None)."""
        today = _date.today()
        flt = self.flt_period.currentText()
        if flt == "This Month":
            return today.replace(day=1), None
        elif flt == "Last Month":
            first_this = today.replace(day=1)
            return (first_this - timedelta(days=1)).replace(day=1), first_this - timedelta(days=1)
        elif flt == "This Year":
            return today.replace(month=1, day=1), None
        elif flt == "Last 30 Days":
            return today - timedelta(days=30), None
        elif flt == "Last 90 Days":
            return today - timedelta(days=90), None
        return None, None

    def refresh(self):
        aid = self.aid()
        if aid is None:
            self.stats_text.setHtml("<h3>Please select an account</h3>")
            for bt in self.bd_tables.values():
                bt.populate([])
            self.setup_perf.populate([])
            self.r_hist.populate([], 0)
            self.calendar_heatmap.refresh(self.conn)
            return

        date_from, date_to = self._get_date_range()

        # Overview
        stats = get_trade_stats(self.conn, account_id=aid,
                                date_from=date_from, date_to=date_to)
        self._formulas = {f['metric_key']: f for f in get_all_formulas(self.conn)}
        if not stats:
            period_note = f" for {self.flt_period.currentText().lower()}" \
                          if date_from else ""
            self.stats_text.setHtml(f"<h3>No closed trades to analyze{period_note}.</h3>")
            for bt in self.bd_tables.values():
                bt.populate([])
            self.setup_perf.populate([])
            self.r_hist.populate([], 0)
            return

        acct = get_account(self.conn, aid)
        acct_label = f"{acct['name']} ({acct['currency']})" if acct else "?"

        def info_icon(key):
            f = self._formulas.get(key)
            if not f: return ''
            return (f' <a href="info://{key}" style="color:#4a90d9;'
                    f'text-decoration:none;font-size:14px;">ⓘ</a>')

        pf = stats['profit_factor']
        pfs = f"{pf:.2f}" if pf != float('inf') else "∞"
        open_trades = stats.get('open_trades', 0)
        open_txt = (f" &nbsp;<span style='color:#3b82f6'>+{open_trades} open</span>"
                    if open_trades else "")
        html = f"""<h2>Performance Summary — {acct_label}</h2>
        <table cellpadding="6" style="font-size:11pt;">
        <tr><td><b>Closed:</b> {stats['total_trades']}{open_txt}</td>
        <td style="color:#008200"><b>Won:</b> {stats['winners']}</td>
        <td style="color:#c80000"><b>Lost:</b> {stats['losers']}</td>
        <td><b>BE:</b> {stats['breakeven']}</td></tr></table>
        <h3>Win Rate{info_icon('win_rate')}: <span style="color:{'#008200' if stats['win_rate']>50 else '#c80000'}">{stats['win_rate']:.1f}%</span></h3>
        <h3>Profit Factor{info_icon('profit_factor')}: <span style="color:{'#008200' if pf>1 else '#c80000'}">{pfs}</span></h3>
        <h3>Expectancy{info_icon('expectancy')}: <span style="color:{'#008200' if stats['expectancy']>0 else '#c80000'}">{stats['expectancy']:+.2f}</span> per trade</h3>
        <h3>Net P&L: <span style="color:{'#008200' if stats['net_pnl']>0 else '#c80000'}">{stats['net_pnl']:+.2f}</span></h3>
        <table cellpadding="4" style="font-size:11pt;">
        <tr><td><b>Gross Profit:</b></td><td style="color:#008200">{stats['gross_profit']:+.2f}</td></tr>
        <tr><td><b>Gross Loss:</b></td><td style="color:#c80000">{-stats['gross_loss']:+.2f}</td></tr>
        <tr><td><b>Avg Win:</b></td><td>{stats['avg_win']:.2f}</td><td><b>Avg Loss:</b></td><td>{stats['avg_loss']:.2f}</td></tr></table>"""

        # Advanced stats section
        adv = get_advanced_stats(self.conn, account_id=aid,
                                 date_from=date_from, date_to=date_to)
        if adv:
            streak_val = adv['current_streak']
            if streak_val > 0:
                streak_txt = f"<span style='color:#008200'>W{streak_val}</span>"
            elif streak_val < 0:
                streak_txt = f"<span style='color:#c80000'>L{abs(streak_val)}</span>"
            else:
                streak_txt = "—"

            sharpe_c = '#008200' if adv['sharpe_ratio'] > 1 else '#c80000' if adv['sharpe_ratio'] < 0 else '#666'
            sharpe_s = f"{adv['sharpe_ratio']:.2f}" if adv['sharpe_ratio'] != float('inf') else "∞"
            sortino_c = '#008200' if adv['sortino_ratio'] > 1 else '#c80000' if adv['sortino_ratio'] < 0 else '#666'
            sortino_s = f"{adv['sortino_ratio']:.2f}" if adv['sortino_ratio'] != float('inf') else "∞"
            calmar_c  = '#008200' if adv['calmar_ratio'] > 0 else '#c80000'
            calmar_s  = f"{adv['calmar_ratio']:.2f}" if adv['calmar_ratio'] != float('inf') else "∞"

            html += f"""
            <hr>
            <h3>Risk & Consistency</h3>
            <table cellpadding="4" style="font-size:11pt;">
            <tr><td><b>Max Drawdown{info_icon('max_drawdown')}:</b></td>
                <td style="color:#c80000">{adv['max_drawdown_pct']:.1f}%</td>
                <td>({adv['max_drawdown_abs']:.2f} {acct['currency'] if acct else ''} peak-to-trough)</td></tr>
            <tr><td><b>Sharpe Ratio{info_icon('sharpe_ratio')}:</b></td>
                <td style="color:{sharpe_c}">{sharpe_s}</td></tr>
            <tr><td><b>Sortino Ratio:</b></td>
                <td style="color:{sortino_c}">{sortino_s}</td></tr>
            <tr><td><b>Calmar Ratio:</b></td>
                <td style="color:{calmar_c}">{calmar_s}</td></tr>
            <tr><td><b>Avg Duration:</b></td>
                <td>{adv['avg_trade_duration_days']:.0f} days</td></tr>
            <tr><td><b>&nbsp;&nbsp;Winners:</b></td>
                <td style="color:#008200">{adv['avg_winner_duration']:.0f} days</td></tr>
            <tr><td><b>&nbsp;&nbsp;Losers:</b></td>
                <td style="color:#c80000">{adv['avg_loser_duration']:.0f} days</td></tr>
            </table>
            <h3>Streaks</h3>
            <table cellpadding="4" style="font-size:11pt;">
            <tr><td><b>Max Wins in a Row:</b></td>
                <td style="color:#008200">{adv['max_consecutive_wins']}</td>
                <td><b>Max Losses in a Row:</b></td>
                <td style="color:#c80000">{adv['max_consecutive_losses']}</td></tr>
            <tr><td><b>Current Streak:</b></td><td>{streak_txt}</td></tr>
            </table>
            <h3>Extremes</h3>
            <table cellpadding="4" style="font-size:11pt;">
            <tr><td><b>Best Trade:</b></td>
                <td style="color:#008200">{adv['best_trade_pnl']:+.2f}</td>
                <td><b>Worst Trade:</b></td>
                <td style="color:#c80000">{adv['worst_trade_pnl']:+.2f}</td></tr>
            </table>"""

        self.stats_text.setHtml(html)

        # Breakdown sub-tabs
        currency = acct['currency'] if acct else ''
        for group_by, bt in self.bd_tables.items():
            data = get_trade_breakdowns(self.conn, aid, group_by,
                                        date_from=date_from, date_to=date_to)
            bt.populate(data, currency=currency)

        # Setup performance sub-tab
        setup_rows = get_setup_performance(self.conn, aid,
                                           date_from=date_from, date_to=date_to)
        self.setup_perf.populate(setup_rows, currency=currency)

        # R-multiple histogram
        r_values, excluded = get_r_multiple_distribution(self.conn, aid,
                                                          date_from=date_from, date_to=date_to)
        self.r_hist.populate(r_values, excluded)

        # Calendar heatmap (pass conn so it stays current after a restore)
        self.calendar_heatmap.refresh(self.conn)

    def _on_info_clicked(self, url):
        """Handle clicks on ⓘ info icons in the overview."""
        key = url.toString().replace('info://', '')
        f = getattr(self, '_formulas', {}).get(key)
        if not f:
            return
        text = f"<h3>{f['display_name']}</h3>"
        text += f"<p><b>Formula:</b><br>{f['formula_text']}</p>"
        text += f"<p><b>What it means:</b><br>{f['description']}</p>"
        if f['interpretation']:
            text += f"<p><b>How to read it:</b><br>{f['interpretation']}</p>"
        QMessageBox.information(self, f"Formula — {f['display_name']}", text)
