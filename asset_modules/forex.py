"""Forex asset module — pips, lots, swap, leverage."""
from .base import AssetModule


class ForexModule(AssetModule):
    ASSET_TYPE = "forex"
    DISPLAY_NAME = "Forex"

    def extra_tables_sql(self):
        return []  # Forex uses the base trades table fields (swap, pnl_pips already exist)

    def event_types(self):
        return []  # Forex only has deposit/withdrawal

    def trade_columns(self):
        return [
            {'key': 'size', 'header': 'Lots'},
            {'key': 'entry_price', 'header': 'Entry'},
            {'key': 'exit_price', 'header': 'Exit'},
            {'key': 'sl', 'header': 'SL'},
            {'key': 'tp', 'header': 'TP'},
            {'key': 'pips', 'header': 'Pips'},
            {'key': 'swap', 'header': 'Swap'},
            {'key': 'exit_reason', 'header': 'Exit Reason'},
        ]

    def format_trade_cell(self, trade, column_key):
        if column_key == 'size':
            return f"{trade['position_size']:.2f}" if trade['position_size'] is not None else ''
        elif column_key == 'entry_price':
            return f"{trade['entry_price']:.5f}" if trade['entry_price'] else ''
        elif column_key == 'exit_price':
            return f"{trade['exit_price']:.5f}" if trade['exit_price'] else ''
        elif column_key == 'sl':
            return f"{trade['stop_loss_price']:.5f}" if trade['stop_loss_price'] else ''
        elif column_key == 'tp':
            return f"{trade['take_profit_price']:.5f}" if trade['take_profit_price'] else ''
        elif column_key == 'pips':
            return f"{trade['pnl_pips']:+.1f}" if trade['pnl_pips'] is not None else ''
        elif column_key == 'swap':
            return f"{trade['swap']:.2f}" if trade['swap'] is not None else ''
        elif column_key == 'exit_reason':
            return trade['exit_reason'] or ''
        return ''

    def trade_form_fields(self):
        return [
            {'key': 'stop_loss_price', 'label': 'Stop Loss', 'type': 'float',
             'decimals': 5, 'range': (0, 999999), 'special_value': 'Not set'},
            {'key': 'take_profit_price', 'label': 'Take Profit', 'type': 'float',
             'decimals': 5, 'range': (0, 999999), 'special_value': 'Not set'},
            {'key': 'swap', 'label': 'Swap', 'type': 'float',
             'decimals': 2, 'range': (-99999, 99999)},
            {'key': 'commission', 'label': 'Commission', 'type': 'float',
             'decimals': 2, 'range': (-99999, 99999)},
        ]

    def format_stats_html(self, stats, currency):
        if not stats.get('avg_pips_win') and not stats.get('avg_pips_loss'):
            return ""
        return f"""<h3>Forex Stats</h3>
        <table cellpadding='4' style='font-size:11pt;'>
        <tr><td><b>Avg Pips Win:</b></td><td>{stats.get('avg_pips_win', 0):.1f}</td>
            <td><b>Avg Pips Loss:</b></td><td>{stats.get('avg_pips_loss', 0):.1f}</td></tr>
        <tr><td><b>Total Swap:</b></td><td>{stats.get('total_swap', 0):+.2f} {currency}</td></tr></table>"""

    def default_instrument_type(self):
        return "forex"

    def size_label(self):
        return "Lots"

    def size_decimals(self):
        return 2

    def price_decimals(self):
        return 5
