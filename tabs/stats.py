"""Summary Stats tab — overview + analytics breakdowns + formula editor."""
from datetime import timedelta, date as _date

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QWidget, QLabel,
    QComboBox, QAbstractItemView, QMessageBox, QPlainTextEdit,
    QFormLayout, QGroupBox, QSizePolicy, QFrame, QDialog,
    QDialogButtonBox, QLineEdit,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

from tabs import BaseTab
from database import (
    get_account, get_trade_stats, get_all_formulas, get_trade_breakdowns,
    update_formula, reset_formulas_to_defaults, get_formula,
    get_advanced_stats,
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
            calmar_s  = f"{adv['calmar_ratio']:.2f}"

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
