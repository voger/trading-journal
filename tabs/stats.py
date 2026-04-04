"""Summary Stats tab — overview + analytics breakdowns + formula editor."""
from datetime import timedelta, date as _date

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QTextBrowser, QTabWidget,
    QWidget, QLabel, QComboBox, QMessageBox,
)
from PyQt6.QtGui import QFont

from tabs import BaseTab
from database import (
    get_account, get_trade_stats, get_all_formulas, get_trade_breakdowns,
    get_advanced_stats, get_r_multiple_distribution, get_setup_performance,
)
from tabs.stats_widgets import BreakdownTable, SetupPerformanceWidget, RMultipleHistogramWidget, HourOfDayWidget
from tabs.stats_formula import FormulaEditorWidget
from tabs.stats_calendar import CalendarHeatmapWidget
from tabs.stats_query import SqlQueryWidget
import theme as _theme_mod


def _overview_css() -> str:
    """Build the stats overview stylesheet using the current theme's P&L palette."""
    return f"""<style>
body  {{ font-size: 11pt; }}
.pos  {{ color: {_theme_mod.pos_color()}; }}
.neg  {{ color: {_theme_mod.neg_color()}; }}
.neu  {{ color: {_theme_mod.neu_color()}; }}
.open {{ color: #3b82f6; }}
a.info-icon {{ color: #4a90d9; text-decoration: none; font-size: 14px; }}
table {{ font-size: 11pt; }}
</style>"""


def _pc(val, threshold=0):
    """Return 'pos' or 'neg' CSS class based on value vs threshold."""
    return 'pos' if val > threshold else 'neg'


def _ratio_cls(val, threshold=1):
    """Format a ratio value and return (text, css_class)."""
    text = f"{val:.2f}" if val != float('inf') else "∞"
    if val > threshold:
        cls = 'pos'
    elif val < 0:
        cls = 'neg'
    else:
        cls = 'neu'
    return text, cls


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

        # Hour-of-day P&L histogram sub-tab
        self.hour_hist = HourOfDayWidget()
        self.tabs.addTab(self.hour_hist, "By Hour")

        # Calendar heatmap sub-tab
        self.calendar_heatmap = CalendarHeatmapWidget(self.conn, self.aid)
        self.tabs.addTab(self.calendar_heatmap, "Calendar")

        # Formula editor sub-tab
        self.formula_editor = FormulaEditorWidget(self.conn)
        self.tabs.addTab(self.formula_editor, "Formulas")

        # Custom SQL analytics console sub-tab
        self.sql_console = SqlQueryWidget(self.conn, self.aid)
        self.tabs.addTab(self.sql_console, "Custom Query")


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
            self.hour_hist.populate([])
            self.calendar_heatmap.refresh(self.conn)
            self.sql_console.refresh_account(None)
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
            self.hour_hist.populate([])
            self.calendar_heatmap.refresh(self.conn)
            self.sql_console.refresh_account(aid)
            return

        acct = get_account(self.conn, aid)
        acct_label = f"{acct['name']} ({acct['currency']})" if acct else "?"

        formulas = self._formulas

        def info_icon(key):
            f = formulas.get(key)
            if not f:
                return ''
            return f' <a href="info://{key}" class="info-icon">ⓘ</a>'

        pf = stats['profit_factor']
        pfs = f"{pf:.2f}" if pf != float('inf') else "∞"
        open_trades = stats.get('open_trades', 0)
        open_txt = (f" &nbsp;<span class='open'>+{open_trades} open</span>"
                    if open_trades else "")
        html = _overview_css() + f"""<h2>Performance Summary — {acct_label}</h2>
        <table cellpadding="6">
        <tr><td><b>Closed:</b> {stats['total_trades']}{open_txt}</td>
        <td class="pos"><b>Won:</b> {stats['winners']}</td>
        <td class="neg"><b>Lost:</b> {stats['losers']}</td>
        <td><b>BE:</b> {stats['breakeven']}</td></tr></table>
        <h3>Win Rate{info_icon('win_rate')}: <span class="{_pc(stats['win_rate']-50)}">{stats['win_rate']:.1f}%</span></h3>
        <h3>Profit Factor{info_icon('profit_factor')}: <span class="{_pc(pf-1)}">{pfs}</span></h3>
        <h3>Expectancy{info_icon('expectancy')}: <span class="{_pc(stats['expectancy'])}">{stats['expectancy']:+.2f}</span> per trade</h3>
        <h3>Net P&L: <span class="{_pc(stats['net_pnl'])}">{stats['net_pnl']:+.2f}</span></h3>
        <table cellpadding="4">
        <tr><td><b>Gross Profit:</b></td><td class="pos">{stats['gross_profit']:+.2f}</td></tr>
        <tr><td><b>Gross Loss:</b></td><td class="neg">{-stats['gross_loss']:+.2f}</td></tr>
        <tr><td><b>Avg Win:</b></td><td>{stats['avg_win']:.2f}</td><td><b>Avg Loss:</b></td><td>{stats['avg_loss']:.2f}</td></tr></table>"""

        # Advanced stats section
        adv = get_advanced_stats(self.conn, account_id=aid,
                                 date_from=date_from, date_to=date_to)
        if adv:
            streak_val = adv['current_streak']
            if streak_val > 0:
                streak_txt = f"<span class='pos'>W{streak_val}</span>"
            elif streak_val < 0:
                streak_txt = f"<span class='neg'>L{abs(streak_val)}</span>"
            else:
                streak_txt = "—"

            sharpe_s, sharpe_c = _ratio_cls(adv['sharpe_ratio'])
            sortino_s, sortino_c = _ratio_cls(adv['sortino_ratio'])
            calmar_s, calmar_c = _ratio_cls(adv['calmar_ratio'], threshold=0)

            html += f"""
            <hr>
            <h3>Risk & Consistency</h3>
            <table cellpadding="4">
            <tr><td><b>Max Drawdown{info_icon('max_drawdown')}:</b></td>
                <td class="neg">{adv['max_drawdown_pct']:.1f}%</td>
                <td>({adv['max_drawdown_abs']:.2f} {acct['currency'] if acct else ''} peak-to-trough)</td></tr>
            <tr><td><b>Sharpe Ratio{info_icon('sharpe_ratio')}:</b></td>
                <td class="{sharpe_c}">{sharpe_s}</td></tr>
            <tr><td><b>Sortino Ratio:</b></td>
                <td class="{sortino_c}">{sortino_s}</td></tr>
            <tr><td><b>Calmar Ratio:</b></td>
                <td class="{calmar_c}">{calmar_s}</td></tr>
            <tr><td><b>Avg Duration:</b></td>
                <td>{adv['avg_trade_duration_days']:.0f} days</td></tr>
            <tr><td><b>&nbsp;&nbsp;Winners:</b></td>
                <td class="pos">{adv['avg_winner_duration']:.0f} days</td></tr>
            <tr><td><b>&nbsp;&nbsp;Losers:</b></td>
                <td class="neg">{adv['avg_loser_duration']:.0f} days</td></tr>
            </table>
            <h3>Streaks</h3>
            <table cellpadding="4">
            <tr><td><b>Max Wins in a Row:</b></td>
                <td class="pos">{adv['max_consecutive_wins']}</td>
                <td><b>Max Losses in a Row:</b></td>
                <td class="neg">{adv['max_consecutive_losses']}</td></tr>
            <tr><td><b>Current Streak:</b></td><td>{streak_txt}</td></tr>
            </table>
            <h3>Extremes</h3>
            <table cellpadding="4">
            <tr><td><b>Best Trade:</b></td>
                <td class="pos">{adv['best_trade_pnl']:+.2f}</td>
                <td><b>Worst Trade:</b></td>
                <td class="neg">{adv['worst_trade_pnl']:+.2f}</td></tr>
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

        # Hour-of-day histogram
        hour_data = get_trade_breakdowns(self.conn, aid, 'hour_of_day',
                                         date_from=date_from, date_to=date_to)
        self.hour_hist.populate(hour_data, currency=currency)

        # Calendar heatmap (pass conn so it stays current after a restore)
        self.calendar_heatmap.refresh(self.conn)

        # Update account label in SQL console
        acct_name = acct['name'] if acct else None
        self.sql_console.refresh_account(acct_name)

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
