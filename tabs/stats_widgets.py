"""Summary Stats tab — standalone breakdown and chart widgets."""
import theme as _theme

from PyQt6.QtWidgets import (
    QVBoxLayout, QWidget, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QSizePolicy,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

# Force English month names regardless of system locale
_MONTH_NAMES = [
    '', 'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
]

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
                    item.setData(Qt.ItemDataRole.UserRole, float(val))
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
        self._fig.patch.set_facecolor(_theme.BG_MID if _theme.is_dark() else 'white')
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
        if _theme.is_dark():
            _theme.apply_mpl_dark(self._fig, ax)
        self._fig.tight_layout(pad=1.2)

        note_parts = [f"{len(r_values)} trades plotted"]
        if excluded_count:
            note_parts.append(f"{excluded_count} excluded (no risk % set)")
        self._note.setText(" — ".join(note_parts))
        self._canvas.draw()


class HourOfDayWidget(QWidget):
    """Net P&L bar chart grouped by exit hour (0–23)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)

        self._canvas = None
        self._fig = None
        try:
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
            from matplotlib.figure import Figure
            self._fig = Figure(figsize=(10, 4), dpi=100)
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
        lay.addWidget(self._note)

    def populate(self, breakdowns, currency=''):
        if self._fig is None:
            return

        self._fig.clear()
        self._fig.patch.set_facecolor(_theme.BG_MID if _theme.is_dark() else 'white')
        ax = self._fig.add_subplot(111)

        # Build hour→{pnl, trades} lookup; fill zeros for all 24 hours
        by_hour = {h: {'net_pnl': 0.0, 'total_trades': 0} for h in range(24)}
        for row in breakdowns:
            h = row['group_name']
            if isinstance(h, int) and 0 <= h <= 23:
                by_hour[h]['net_pnl'] = row['net_pnl']
                by_hour[h]['total_trades'] = row['total_trades']

        hours  = list(range(24))
        pnls   = [by_hour[h]['net_pnl'] for h in hours]
        counts = [by_hour[h]['total_trades'] for h in hours]
        colors = [
            (_theme.GREEN_VIV if _theme.is_dark() else '#26a69a') if p > 0
            else (_theme.RED_VIV if _theme.is_dark() else '#ef5350') if p < 0
            else '#888888'
            for p in pnls
        ]

        if not any(c > 0 for c in counts):
            ax.text(0.5, 0.5, 'No closed trades to display.',
                    ha='center', va='center', fontsize=12, color='#888',
                    transform=ax.transAxes)
            ax.set_axis_off()
            self._note.setText("")
            self._canvas.draw()
            return

        bars = ax.bar(hours, pnls, color=colors, edgecolor='#555', linewidth=0.5, width=0.7)

        # Trade count labels above/below each non-zero bar
        y_scale = max((abs(p) for p in pnls if p != 0), default=1)
        for bar, count, pnl in zip(bars, counts, pnls):
            if count > 0:
                offset = y_scale * 0.02
                va = 'bottom' if pnl >= 0 else 'top'
                y = pnl + (offset if pnl >= 0 else -offset)
                ax.text(bar.get_x() + bar.get_width() / 2, y,
                        str(count), ha='center', va=va, fontsize=7)

        ax.axhline(0, color='#666', linewidth=0.8, linestyle='--')
        ax.set_xticks(hours)
        ax.set_xticklabels([f"{h:02d}h" for h in hours], fontsize=7, rotation=45, ha='right')
        ax.set_ylabel(f'Net P&L ({currency})' if currency else 'Net P&L', fontsize=10)
        ax.set_xlabel('Hour of Day (UTC)', fontsize=10)
        ax.set_title('P&L by Hour of Day', fontsize=11)
        ax.tick_params(axis='y', labelsize=8)
        ax.grid(axis='y', alpha=0.3)

        if _theme.is_dark():
            _theme.apply_mpl_dark(self._fig, ax)
        self._fig.tight_layout(pad=1.2)

        total = sum(counts)
        self._note.setText(f"{total} closed trade{'s' if total != 1 else ''} plotted")
        self._canvas.draw()
