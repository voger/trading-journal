"""Stocks & ETFs asset module — shares, dividends, interest."""
from .base import AssetModule


class StocksModule(AssetModule):
    ASSET_TYPE = "stocks"
    DISPLAY_NAME = "Stocks & ETFs"

    def extra_tables_sql(self):
        return [
            """CREATE TABLE IF NOT EXISTS dividends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                instrument_id INTEGER,
                trade_id INTEGER,
                amount REAL NOT NULL,
                currency TEXT,
                pay_date TEXT NOT NULL,
                ex_date TEXT,
                description TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
                FOREIGN KEY (instrument_id) REFERENCES instruments(id),
                FOREIGN KEY (trade_id) REFERENCES trades(id) ON DELETE SET NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_dividends_account ON dividends(account_id)",
            "CREATE INDEX IF NOT EXISTS idx_dividends_instrument ON dividends(instrument_id)",
            "CREATE INDEX IF NOT EXISTS idx_dividends_trade ON dividends(trade_id)",
        ]

    def event_types(self):
        return ['dividend', 'interest']

    def trade_columns(self):
        return [
            {'key': 'size', 'header': 'Shares'},
            {'key': 'entry_price', 'header': 'Entry'},
            {'key': 'exit_price', 'header': 'Exit'},
            {'key': 'sl', 'header': 'SL'},
            {'key': 'tp', 'header': 'TP'},
            {'key': 'commission', 'header': 'Comm.'},
            {'key': 'dividends', 'header': 'Divs'},
            {'key': 'exit_reason', 'header': 'Exit Reason'},
        ]

    def format_trade_cell(self, trade, column_key):
        if column_key == 'size':
            v = trade['position_size']
            if not v: return ''
            # Support fractional shares (Trading212 etc.)
            if v == int(v):
                return f"{v:.0f}"
            elif v < 1:
                return f"{v:.6f}".rstrip('0').rstrip('.')
            else:
                return f"{v:.4f}".rstrip('0').rstrip('.')
        elif column_key == 'entry_price':
            return f"{trade['entry_price']:.2f}" if trade['entry_price'] else ''
        elif column_key == 'exit_price':
            return f"{trade['exit_price']:.2f}" if trade['exit_price'] else ''
        elif column_key == 'sl':
            return f"{trade['stop_loss_price']:.2f}" if trade['stop_loss_price'] else ''
        elif column_key == 'tp':
            return f"{trade['take_profit_price']:.2f}" if trade['take_profit_price'] else ''
        elif column_key == 'commission':
            return f"{trade['commission']:.2f}" if trade['commission'] else ''
        elif column_key == 'dividends':
            # Dividends sum is injected as a dict key by the caller;
            # sqlite3.Row objects won't have it, so use try/except.
            try:
                v = trade['_dividends_sum']
                return f"{v:.2f}" if v else ''
            except (KeyError, IndexError):
                return ''
        elif column_key == 'exit_reason':
            return trade['exit_reason'] or ''
        return ''

    def trade_form_fields(self):
        return [
            {'key': 'stop_loss_price', 'label': 'Stop Loss', 'type': 'float',
             'decimals': 2, 'range': (0, 999999), 'special_value': 'Not set'},
            {'key': 'take_profit_price', 'label': 'Take Profit', 'type': 'float',
             'decimals': 2, 'range': (0, 999999), 'special_value': 'Not set'},
            {'key': 'commission', 'label': 'Commission', 'type': 'float',
             'decimals': 2, 'range': (-99999, 99999)},
        ]

    def format_stats_html(self, stats, currency):
        parts = []
        if stats.get('total_dividends'):
            parts.append(f"<tr><td><b>Total Dividends:</b></td>"
                        f"<td style='color:#008200'>{stats['total_dividends']:+.2f} {currency}</td></tr>")
        if stats.get('total_interest'):
            parts.append(f"<tr><td><b>Total Interest:</b></td>"
                        f"<td style='color:#008200'>{stats['total_interest']:+.2f} {currency}</td></tr>")
        if stats.get('total_commission'):
            parts.append(f"<tr><td><b>Total Commissions:</b></td>"
                        f"<td style='color:#c80000'>{stats['total_commission']:+.2f} {currency}</td></tr>")
        if not parts:
            return ""
        return "<h3>Stocks Stats</h3><table cellpadding='4' style='font-size:11pt;'>" + "".join(parts) + "</table>"

    def default_instrument_type(self):
        return "stock"

    def size_label(self):
        return "Shares"

    def size_decimals(self):
        return 0

    def price_decimals(self):
        return 2
