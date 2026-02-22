"""Equity Curve tab — matplotlib chart with deposit markers."""
from datetime import datetime

from PyQt6.QtWidgets import (
    QVBoxLayout, QPushButton, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

from tabs import BaseTab
from database import get_account, get_equity_curve_data, get_equity_events


class EquityTab(BaseTab):
    def __init__(self, conn, get_aid_fn):
        super().__init__(conn, get_aid_fn)
        self._dirty = True
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        self.account_label = QLabel(""); self.account_label.setFont(QFont("", 11, QFont.Weight.Bold))
        layout.addWidget(self.account_label)
        try:
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
            from matplotlib.figure import Figure
            self.fig = Figure(figsize=(10,4), dpi=100)
            self.canvas = FigureCanvasQTAgg(self.fig)
            layout.addWidget(self.canvas)
        except ImportError:
            layout.addWidget(QLabel("matplotlib not installed. Run: pip install matplotlib"))
            self.canvas = None
        self.info_label = QLabel(""); self.info_label.setStyleSheet("padding:4px; color:#333;")
        layout.addWidget(self.info_label)
        layout.addWidget(QLabel("Deposits / Withdrawals:"))
        self.deposits_table = QTableWidget(); self.deposits_table.setAlternatingRowColors(True)
        self.deposits_table.setMaximumHeight(150)
        cols = ['Date', 'Type', 'Amount', 'Description']
        self.deposits_table.setColumnCount(len(cols)); self.deposits_table.setHorizontalHeaderLabels(cols)
        h = self.deposits_table.horizontalHeader(); h.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.deposits_table)
        b = QPushButton("Refresh"); b.clicked.connect(self.force_refresh); layout.addWidget(b)

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
        if not data:
            ax = self.fig.add_subplot(111)
            ax.text(0.5, 0.5, 'No closed trades yet', ha='center', va='center', fontsize=14, color='gray')
            ax.set_axis_off(); self.canvas.draw()
            self.deposits_table.setRowCount(0); self.info_label.setText(""); return

        initial = data[0]['initial_balance'] if data else 0
        balance = initial; dates = []; balances = [initial]
        for t in data:
            pnl = (t['pnl_account_currency'] or 0) + (t['swap'] or 0) + (t['commission'] or 0)
            balance += pnl
            try:
                d = datetime.strptime(t['exit_date'][:10], '%Y-%m-%d')
                dates.append(d); balances.append(balance)
            except: continue
        if len(dates) < 1: return
        dates.insert(0, dates[0])

        ax = self.fig.add_subplot(111)
        ax.fill_between(dates, balances, initial, alpha=0.12, color='#4a90d9')
        ax.plot(dates, balances, color='#2563eb', linewidth=1.5)
        ax.axhline(y=initial, color='gray', linestyle='--', linewidth=0.8, alpha=0.5)

        events = get_equity_events(self.conn, aid)
        for ev in events:
            try:
                d = datetime.strptime(ev['event_date'][:10], '%Y-%m-%d')
                amt = ev['amount']
                color = '#2e7d32' if amt > 0 else '#c62828'
                label = f"+{amt:.0f}" if amt > 0 else f"{amt:.0f}"
                ax.axvline(x=d, color=color, linestyle=':', linewidth=1.2, alpha=0.7)
                ylim = ax.get_ylim()
                ax.annotate(label, xy=(d, ylim[1] - (ylim[1]-ylim[0])*0.05),
                           fontsize=8, color=color, ha='center', fontweight='bold')
            except: pass

        ax.set_title(f'Equity Curve ({currency})', fontsize=13, fontweight='bold')
        ax.set_ylabel(f'Balance ({currency})')
        ax.grid(True, alpha=0.3)
        self.fig.autofmt_xdate(); self.fig.tight_layout(); self.canvas.draw()

        self.deposits_table.setRowCount(len(events))
        for row, ev in enumerate(events):
            color = QColor(0,130,0) if ev['amount'] > 0 else QColor(200,0,0)
            items = [ev['event_date'][:16], ev['event_type'].title(),
                     f"{ev['amount']:+.2f} {currency}", ev['description'] or '']
            for col, val in enumerate(items):
                item = QTableWidgetItem(val); item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 2: item.setForeground(color)
                self.deposits_table.setItem(row, col, item)
        self.info_label.setText("")
