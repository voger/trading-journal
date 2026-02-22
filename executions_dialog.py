"""
Executions & FIFO Lot Detail — Dedicated read-only dialog.
Opened from the summary bar in TradeDialog for stock trades.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QDialogButtonBox, QGroupBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont


class ExecutionsDialog(QDialog):
    """Full-size read-only view of executions and FIFO lot matching."""

    def __init__(self, parent, conn, trade_id, symbol=''):
        super().__init__(parent)
        self.setWindowTitle(f"Executions — {symbol}" if symbol else "Executions & FIFO Detail")
        self.setMinimumSize(800, 500)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.conn = conn
        self.trade_id = trade_id
        self._build()
        self._populate()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # ── Executions table ──
        exec_group = QGroupBox("Executions")
        exec_lay = QVBoxLayout(exec_group)
        self.exec_table = QTableWidget()
        self.exec_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.exec_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.exec_table.setAlternatingRowColors(True)
        self.exec_table.verticalHeader().setDefaultSectionSize(26)
        exec_lay.addWidget(self.exec_table)
        layout.addWidget(exec_group, 2)

        # ── Lot matching table ──
        self.lot_group = QGroupBox("FIFO Lot Matching")
        lot_lay = QVBoxLayout(self.lot_group)
        self.lot_table = QTableWidget()
        self.lot_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.lot_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.lot_table.setAlternatingRowColors(True)
        self.lot_table.verticalHeader().setDefaultSectionSize(26)
        lot_lay.addWidget(self.lot_table)
        layout.addWidget(self.lot_group, 2)

        # ── Summary ──
        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("font-weight: bold; font-size: 14px; padding: 8px;")
        layout.addWidget(self.summary_label)

        # ── Close button ──
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _populate(self):
        from fifo_engine import (
            get_executions_for_trade,
            get_lot_consumptions_for_trade,
            get_open_lots_for_trade,
        )

        buy_color = QColor(0, 130, 0)
        sell_color = QColor(200, 0, 0)

        # ── Executions ──
        execs = get_executions_for_trade(self.conn, self.trade_id)
        headers = ['Action', 'Date', 'Shares', 'Price', 'Currency', 'XRate',
                    'Total (acct)', 'Commission', 'Result']
        self.exec_table.setColumnCount(len(headers))
        self.exec_table.setHorizontalHeaderLabels(headers)
        self.exec_table.setRowCount(len(execs))

        for row, e in enumerate(execs):
            is_buy = e['action'] == 'buy'
            color = buy_color if is_buy else sell_color
            cells = [
                e['action'].upper(),
                (e['executed_at'] or '')[:16],
                f"{e['shares']:.6f}",
                f"{e['price']:.4f}",
                e['price_currency'] or '',
                f"{e['exchange_rate']:.4f}" if e['exchange_rate'] else '',
                f"{e['total_account_currency']:.2f}" if e['total_account_currency'] else '',
                f"{e['commission']:.2f}" if e['commission'] else '',
                f"{e['broker_result']:.2f}" if e['broker_result'] else '',
            ]
            for col, val in enumerate(cells):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 0:
                    item.setForeground(color)
                    item.setFont(QFont("", -1, QFont.Weight.Bold))
                self.exec_table.setItem(row, col, item)

        self.exec_table.resizeColumnsToContents()
        h = self.exec_table.horizontalHeader()
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        # ── Lot consumptions ──
        lots = get_lot_consumptions_for_trade(self.conn, self.trade_id)
        open_lots = get_open_lots_for_trade(self.conn, self.trade_id)

        if lots:
            self.lot_group.setTitle("FIFO Lot Matching")
            lot_headers = ['Buy Date', 'Buy Price', '→', 'Sell Date', 'Sell Price',
                           'Shares', 'P&L (computed)']
            self.lot_table.setColumnCount(len(lot_headers))
            self.lot_table.setHorizontalHeaderLabels(lot_headers)
            self.lot_table.setRowCount(len(lots))

            for row, l in enumerate(lots):
                pnl = l['pnl_computed'] or 0
                pnl_color = buy_color if pnl > 0 else sell_color if pnl < 0 else QColor(100, 100, 100)
                cells = [
                    (l['buy_date'] or '')[:10],
                    f"{l['buy_price']:.4f}",
                    '→',
                    (l['sell_date'] or '')[:10],
                    f"{l['sell_price']:.4f}",
                    f"{l['shares_consumed']:.6f}",
                    f"€{pnl:+.2f}",
                ]
                for col, val in enumerate(cells):
                    item = QTableWidgetItem(val)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    if col == 6:
                        item.setForeground(pnl_color)
                        item.setFont(QFont("", -1, QFont.Weight.Bold))
                    self.lot_table.setItem(row, col, item)

            self.lot_table.resizeColumnsToContents()

        elif open_lots:
            self.lot_group.setTitle("Open Lots (FIFO order)")
            lot_headers = ['Date', 'Price', 'Currency', 'Original', 'Remaining', 'Cost (acct)']
            self.lot_table.setColumnCount(len(lot_headers))
            self.lot_table.setHorizontalHeaderLabels(lot_headers)
            self.lot_table.setRowCount(len(open_lots))

            for row, ol in enumerate(open_lots):
                cells = [
                    (ol['date'] or '')[:10],
                    f"{ol['price']:.4f}",
                    ol.get('price_currency', '') or '',
                    f"{ol['original_shares']:.6f}",
                    f"{ol['remaining_shares']:.6f}",
                    f"€{ol['cost_account']:.2f}" if ol.get('cost_account') else '',
                ]
                for col, val in enumerate(cells):
                    item = QTableWidgetItem(val)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.lot_table.setItem(row, col, item)

            self.lot_table.resizeColumnsToContents()
        else:
            self.lot_group.setVisible(False)

        # ── Summary ──
        buys = [e for e in execs if e['action'] == 'buy']
        sells = [e for e in execs if e['action'] == 'sell']
        total_bought = sum(e['shares'] for e in buys)
        total_sold = sum(e['shares'] for e in sells)

        parts = [f"{len(buys)} buy{'s' if len(buys) != 1 else ''}"]
        if sells:
            parts.append(f"{len(sells)} sell{'s' if len(sells) != 1 else ''}")

        broker_pnl = sum(e['broker_result'] or 0 for e in execs)
        parts.append(f"Broker P&L: €{broker_pnl:+.2f}")

        if lots:
            computed_pnl = sum(l['pnl_computed'] or 0 for l in lots)
            parts.append(f"Computed P&L: €{computed_pnl:+.2f}")

        remaining = total_bought - total_sold
        if abs(remaining) > 1e-9:
            parts.append(f"Remaining: {remaining:.6f} shares")

        self.summary_label.setText("  |  ".join(parts))


def get_execution_summary(conn, trade_id):
    """Return a short summary string for the executions bar, or None if no executions."""
    from database import get_execution_count_for_trade
    count = get_execution_count_for_trade(conn, trade_id)
    if count == 0:
        return None

    from fifo_engine import get_executions_for_trade
    execs = get_executions_for_trade(conn, trade_id)
    buys = [e for e in execs if e['action'] == 'buy']
    sells = [e for e in execs if e['action'] == 'sell']
    broker_pnl = sum(e['broker_result'] or 0 for e in execs)

    parts = [f"{len(buys)} buy{'s' if len(buys) != 1 else ''}"]
    if sells:
        parts.append(f"{len(sells)} sell{'s' if len(sells) != 1 else ''}")
    parts.append(f"Broker P&L: €{broker_pnl:+.2f}")
    return "  |  ".join(parts)
