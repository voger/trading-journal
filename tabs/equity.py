"""Equity Curve tab — matplotlib chart with deposit markers."""
from datetime import datetime

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

from tabs import BaseTab
from database import get_account, get_equity_curve_data, get_equity_events
import theme as _theme


class EquityTab(BaseTab):
    def __init__(self, conn, get_aid_fn):
        super().__init__(conn, get_aid_fn)
        self._dirty = True
        self._mode = 'balance'
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        self.account_label = QLabel(""); self.account_label.setFont(QFont("", 11, QFont.Weight.Bold))
        layout.addWidget(self.account_label)

        # Mode toggle
        mode_row = QHBoxLayout()
        self._btn_balance = QPushButton("Balance")
        self._btn_pnl     = QPushButton("Cumulative P&L")
        for btn in (self._btn_balance, self._btn_pnl):
            btn.setCheckable(True)
            btn.setFixedHeight(26)
        self._btn_balance.setChecked(True)
        mode_row.addWidget(self._btn_balance)
        mode_row.addWidget(self._btn_pnl)
        mode_row.addStretch()
        layout.addLayout(mode_row)
        self._btn_balance.clicked.connect(lambda: self._set_mode('balance'))
        self._btn_pnl.clicked.connect(lambda: self._set_mode('pnl'))

        try:
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
            from matplotlib.figure import Figure
            self.fig = Figure(figsize=(10,4), dpi=100)
            self.canvas = FigureCanvasQTAgg(self.fig)
            layout.addWidget(self.canvas)
        except ImportError:
            layout.addWidget(QLabel("matplotlib not installed. Run: pip install matplotlib"))
            self.canvas = None
        self.info_label = QLabel(""); self.info_label.setStyleSheet("padding:4px;")
        layout.addWidget(self.info_label)
        layout.addWidget(QLabel("Deposits / Withdrawals:"))
        self.deposits_table = QTableWidget(); self.deposits_table.setAlternatingRowColors(True)
        self.deposits_table.setMaximumHeight(150)
        cols = ['Date', 'Type', 'Amount', 'Description']
        self.deposits_table.setColumnCount(len(cols)); self.deposits_table.setHorizontalHeaderLabels(cols)
        h = self.deposits_table.horizontalHeader(); h.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.deposits_table)
        b = QPushButton("Refresh"); b.clicked.connect(self.force_refresh); layout.addWidget(b)
        self._event_lines = []  # parallel to events list; None for events with no chart marker
        self.deposits_table.itemSelectionChanged.connect(self._on_event_selected)

    def _set_mode(self, mode):
        self._mode = mode
        self._btn_balance.setChecked(mode == 'balance')
        self._btn_pnl.setChecked(mode == 'pnl')
        self._render()
        self._dirty = False

    def _populate_deposits_table(self, events, currency):
        self.deposits_table.setRowCount(len(events))
        for row, ev in enumerate(events):
            color = QColor(0, 130, 0) if ev['amount'] > 0 else QColor(200, 0, 0)
            items = [ev['event_date'][:16], ev['event_type'].title(),
                     f"{ev['amount']:+.2f} {currency}", ev['description'] or '']
            for col, val in enumerate(items):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 2: item.setForeground(color)
                self.deposits_table.setItem(row, col, item)

    def mark_dirty(self):
        self._dirty = True

    def refresh(self):
        """Called by MainWindow — only render if visible, otherwise mark dirty."""
        if self.canvas is None: return
        self._dirty = True  # always mark dirty, render on demand

    def try_render_if_visible(self):
        """Called when this tab becomes visible."""
        if self._dirty:
            self._dirty = False
            self._render()

    def force_refresh(self):
        self._dirty = False
        self._render()

    def _render(self):
        if self.canvas is None: return
        self.fig.clear()
        aid = self.aid()

        if aid is None:
            ax = self.fig.add_subplot(111)
            ax.text(0.5, 0.5, 'Please select an account', ha='center', va='center', fontsize=14, color='gray')
            ax.set_axis_off(); self.canvas.draw()
            self.deposits_table.setRowCount(0)
            self.account_label.setText(""); self.info_label.setText(""); return

        acct = get_account(self.conn, aid)
        currency = acct['currency'] if acct else '?'
        self.account_label.setText(f"{acct['name']} — {currency}" if acct else "")

        data = get_equity_curve_data(self.conn, aid)
        events = get_equity_events(self.conn, aid)

        if not data and not events:
            ax = self.fig.add_subplot(111)
            ax.text(0.5, 0.5, 'No closed trades yet', ha='center', va='center', fontsize=14, color='gray')
            ax.set_axis_off(); self.canvas.draw()
            self.deposits_table.setRowCount(0); self.info_label.setText(""); return

        initial = acct['initial_balance'] if acct else 0

        if _theme.is_dark():
            profit_color = _theme.GREEN
            loss_color   = _theme.RED
            line_color   = _theme.ACCENT
        else:
            profit_color = '#2e7d32'
            loss_color   = '#c62828'
            line_color   = '#1565c0'  # dark blue

        # ── Cumulative P&L mode ──
        if self._mode == 'pnl':
            self._event_lines = []
            pnl_running = 0.0
            dates = []
            balances = [0.0]
            for t in data:
                pnl = (t['pnl_account_currency'] or 0) + (t['swap'] or 0) + (t['commission'] or 0)
                try:
                    d = datetime.strptime(t['exit_date'][:10], '%Y-%m-%d')
                    pnl_running += pnl
                    dates.append(d)
                    balances.append(pnl_running)
                except (ValueError, TypeError):
                    continue

            if not dates:
                ax = self.fig.add_subplot(111)
                ax.text(0.5, 0.5, 'No closed trades yet', ha='center', va='center',
                        fontsize=14, color='gray')
                ax.set_axis_off(); self.canvas.draw()
                self._populate_deposits_table(events, currency)
                self.info_label.setText(""); return

            dates.insert(0, dates[0])
            ax = self.fig.add_subplot(111)
            ax.fill_between(dates, balances, 0,
                            where=[b >= 0 for b in balances],
                            alpha=0.18, color=profit_color, interpolate=True)
            ax.fill_between(dates, balances, 0,
                            where=[b < 0 for b in balances],
                            alpha=0.18, color=loss_color, interpolate=True)
            ax.plot(dates, balances, color=line_color, linewidth=1.5)
            ax.axhline(y=0, color='gray', linestyle='--', linewidth=0.8, alpha=0.5)
            ax.set_title(f'Cumulative P&L ({currency})', fontsize=13, fontweight='bold')
            ax.set_ylabel(f'P&L ({currency})')
            ax.grid(True, alpha=0.3)
            if _theme.is_dark():
                _theme.apply_mpl_dark(self.fig, ax)
            self.fig.autofmt_xdate(); self.fig.tight_layout(); self.canvas.draw()

            net_pnl = balances[-1]
            pnl_color = '#008200' if net_pnl >= 0 else '#c80000'
            sign = '+' if net_pnl >= 0 else ''
            self.info_label.setTextFormat(Qt.TextFormat.RichText)
            self.info_label.setText(
                f"<b>Net P&L:</b> <span style='color:{pnl_color}'>{sign}{net_pnl:,.2f} {currency}</span>"
                f" &nbsp;|&nbsp; <b>Trades:</b> {len(data)}"
            )
            self._populate_deposits_table(events, currency)
            return

        # ── Balance mode (default) ──
        # Build a merged chronological timeline of trades and account events so
        # that deposits/withdrawals shift the running balance at the right point,
        # matching the way MT4's detailed statement renders the equity curve.
        # Each entry: (date, amount, event_row_or_None)
        timeline = []
        for t in data:
            pnl = (t['pnl_account_currency'] or 0) + (t['swap'] or 0) + (t['commission'] or 0)
            try:
                d = datetime.strptime(t['exit_date'][:10], '%Y-%m-%d')
                timeline.append((d, pnl, None))
            except (ValueError, TypeError): continue
        for ev in events:
            try:
                d = datetime.strptime(ev['event_date'][:10], '%Y-%m-%d')
                timeline.append((d, ev['amount'], ev))
            except (ValueError, TypeError): continue
        timeline.sort(key=lambda x: x[0])

        if not timeline:
            ax = self.fig.add_subplot(111)
            ax.text(0.5, 0.5, 'No closed trades yet', ha='center', va='center',
                    fontsize=14, color='gray')
            ax.set_axis_off(); self.canvas.draw()
            self._populate_deposits_table(events, currency)
            self.info_label.setText(""); return

        balance = initial; dates = []; balances = [initial]
        for d, amount, _ in timeline:
            balance += amount
            dates.append(d); balances.append(balance)
        dates.insert(0, dates[0])

        ax = self.fig.add_subplot(111)

        # Colour the fill above/below the starting balance differently
        ax.fill_between(dates, balances, initial,
                        where=[b >= initial for b in balances],
                        alpha=0.18, color=profit_color, interpolate=True)
        ax.fill_between(dates, balances, initial,
                        where=[b < initial for b in balances],
                        alpha=0.18, color=loss_color, interpolate=True)
        ax.plot(dates, balances, color=line_color, linewidth=1.5)
        ax.axhline(y=initial, color='gray', linestyle='--', linewidth=0.8, alpha=0.5)

        self._event_lines = []
        for ev in events:
            # Interest payments are included in the balance but not marked on
            # the chart — they're too frequent and too small to be useful.
            if (ev['event_type'] or '').lower() == 'interest':
                self._event_lines.append(None)
                continue
            try:
                d = datetime.strptime(ev['event_date'][:10], '%Y-%m-%d')
                amt = ev['amount']
                color = profit_color if amt > 0 else loss_color
                label = f"+{amt:.0f}" if amt > 0 else f"{amt:.0f}"
                vline = ax.axvline(x=d, color=color, linestyle=':', linewidth=1.2, alpha=0.7)
                self._event_lines.append(vline)
                ylim = ax.get_ylim()
                ax.annotate(label, xy=(d, ylim[1] - (ylim[1]-ylim[0])*0.05),
                           fontsize=8, color=color, ha='center', fontweight='bold')
            except (ValueError, TypeError):
                self._event_lines.append(None)

        ax.set_title(f'Equity Curve ({currency})', fontsize=13, fontweight='bold')
        ax.set_ylabel(f'Balance ({currency})')
        ax.grid(True, alpha=0.3)
        if _theme.is_dark():
            _theme.apply_mpl_dark(self.fig, ax)
        self.fig.autofmt_xdate(); self.fig.tight_layout(); self.canvas.draw()

        self._populate_deposits_table(events, currency)

        # Summary metrics
        current_balance = balances[-1]
        gain_abs = current_balance - initial
        gain_pct = (gain_abs / initial * 100) if initial else 0
        gain_color = '#008200' if gain_abs >= 0 else '#c80000'
        sign = '+' if gain_abs >= 0 else ''
        self.info_label.setTextFormat(Qt.TextFormat.RichText)
        self.info_label.setText(
            f"<b>Balance:</b> {current_balance:,.2f} {currency} &nbsp;|&nbsp; "
            f"<b>Gain:</b> <span style='color:{gain_color}'>{sign}{gain_abs:,.2f} ({sign}{gain_pct:.1f}%)</span> &nbsp;|&nbsp; "
            f"<b>Starting:</b> {initial:,.2f} {currency}"
        )

    def _on_event_selected(self):
        if self.canvas is None:
            return
        # Reset all event lines to default style
        for line in self._event_lines:
            if line is not None:
                line.set_linewidth(1.2)
                line.set_alpha(0.7)
                line.set_linestyle(':')
        # Highlight the selected row's line
        selected = self.deposits_table.selectedItems()
        if selected:
            row = self.deposits_table.row(selected[0])
            if 0 <= row < len(self._event_lines) and self._event_lines[row] is not None:
                line = self._event_lines[row]
                line.set_linewidth(2.5)
                line.set_alpha(1.0)
                line.set_linestyle('-')
        self.canvas.draw()
