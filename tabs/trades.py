"""Trades tab — KPI cards, split-pane table+preview, filters, CRUD actions."""
import csv
import os, shutil
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QMessageBox, QApplication, QDialog,
    QDialogButtonBox, QFileDialog, QFrame, QSplitter,
    QLineEdit, QGridLayout, QSizePolicy, QGroupBox,
    QPlainTextEdit, QProgressDialog,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QShortcut, QKeySequence, QPalette

from tabs import BaseTab
from dialogs import TradeDialog
from database import (
    get_accounts, get_account, get_trades, get_trade, create_trade,
    update_trade, delete_trade, get_trade_chart_counts,
    get_account_events, add_trade_chart, delete_trade_chart,
    get_setup_types, save_trade_rule_checks, create_account,
    get_import_logs,
    get_trade_rule_checks, get_trades_for_export, EXPORT_COLUMNS,
    get_app_data_dir, effective_pnl,
    get_tags, get_trade_tags, set_trade_tags, get_or_create_tag,
    get_trades_paged, get_trades_all_filtered,
)

_PAGE_SIZE = 500
from asset_modules import get_module

SCREENSHOTS_DIR = os.path.join(get_app_data_dir(), 'screenshots')
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)


class _NumItem(QTableWidgetItem):
    """QTableWidgetItem that sorts numerically when the cell text is a number."""
    def __lt__(self, other):
        try:
            return float(self.text().replace('+', '').replace(',', '')) < \
                   float(other.text().replace('+', '').replace(',', ''))
        except (ValueError, AttributeError):
            return self.text() < other.text()


# ── KPI Card Widget ──────────────────────────────────────────────────────

class KPICard(QFrame):
    """Compact metric card for the KPI bar."""
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "KPICard { border: 1px solid #ccc; border-radius: 6px; padding: 6px; }"
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(60)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(0)
        self._title = QLabel(title)
        self._title.setStyleSheet("color: #666; font-size: 10px; font-weight: bold;")
        self._value = QLabel("—")
        self._value.setStyleSheet("font-size: 16px; font-weight: bold;")
        self._value.setAlignment(Qt.AlignmentFlag.AlignRight)
        lay.addWidget(self._title)
        lay.addWidget(self._value)

    def set_value(self, text, color="#333"):
        self._value.setText(text)
        self._value.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: bold;")


# ── Main TradesTab ────────────────────────────────────────────────────────

class TradesTab(BaseTab):
    def __init__(self, conn, get_aid_fn, status_bar_fn):
        super().__init__(conn, get_aid_fn)
        self._status = status_bar_fn
        self._selected_trade_id = None
        self._visible_trades = []
        self._page = 0
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # ── Toolbar ──
        tb = QHBoxLayout()
        for text, slot in [("+ New Trade", self._on_new), ("Edit", self._on_edit),
                           ("Delete", self._on_delete), ("Refresh", self.refresh)]:
            b = QPushButton(text); b.clicked.connect(slot); tb.addWidget(b)
        tb.addStretch()
        b = QPushButton("Export CSV..."); b.clicked.connect(self._on_export); tb.addWidget(b)
        b = QPushButton("Import..."); b.clicked.connect(self._on_import); tb.addWidget(b)
        layout.addLayout(tb)

        # ── Keyboard shortcuts ──
        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(self._on_new)
        QShortcut(QKeySequence("Return"),  self).activated.connect(self._on_edit)
        QShortcut(QKeySequence("Delete"),  self).activated.connect(self._on_delete)
        QShortcut(QKeySequence("F5"),      self).activated.connect(self.refresh)

        # ── KPI Bar ──
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        self.kpi_trades = KPICard("TRADES")
        self.kpi_winrate = KPICard("WIN RATE")
        self.kpi_pnl = KPICard("NET P&L")
        self.kpi_expectancy = KPICard("EXPECTANCY")
        self.kpi_pf = KPICard("PROFIT FACTOR")
        for card in [self.kpi_trades, self.kpi_winrate, self.kpi_pnl,
                     self.kpi_expectancy, self.kpi_pf]:
            kpi_row.addWidget(card)
        layout.addLayout(kpi_row)

        # ── Filter bar (pagination first, then filters) ──
        filt = QHBoxLayout()
        filt.setSpacing(4)

        # Pagination group at the left
        self.btn_prev = QPushButton("◀")
        self.btn_prev.setFixedSize(28, 24)
        self.btn_prev.setEnabled(False)
        self.btn_prev.setToolTip("Previous page")
        self.btn_prev.clicked.connect(self._on_prev_page)
        self.lbl_page = QLabel("Page 1 of 1 · 0 trades")
        self.lbl_page.setStyleSheet(
            "font-size: 11px; font-weight: bold; padding: 0 4px;"
        )
        self.btn_next = QPushButton("▶")
        self.btn_next.setFixedSize(28, 24)
        self.btn_next.setEnabled(False)
        self.btn_next.setToolTip("Next page")
        self.btn_next.clicked.connect(self._on_next_page)
        filt.addWidget(self.btn_prev)
        filt.addWidget(self.lbl_page)
        filt.addWidget(self.btn_next)

        # Vertical separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        filt.addWidget(sep)

        # Filters
        filt.addWidget(QLabel("Filters:"))
        self.flt_setup = QComboBox(); self.flt_setup.addItem("All Setups", None)
        self.flt_setup.setMinimumWidth(120); filt.addWidget(self.flt_setup)
        self.flt_direction = QComboBox()
        self.flt_direction.addItems(["All Dirs", "Long", "Short"]); filt.addWidget(self.flt_direction)
        self.flt_status = QComboBox()
        self.flt_status.addItems(["All Status", "Open", "Closed"]); filt.addWidget(self.flt_status)
        self.flt_grade = QComboBox()
        self.flt_grade.addItems(["All Grades", "A", "B", "C", "D", "F"]); filt.addWidget(self.flt_grade)
        self.flt_period = QComboBox()
        self.flt_period.addItems([
            "All Time", "This Month", "Last Month",
            "This Year", "Last 30 Days", "Last 90 Days",
        ])
        filt.addWidget(self.flt_period)
        self.flt_search = QLineEdit()
        self.flt_search.setPlaceholderText("Search symbol…")
        self.flt_search.setMaximumWidth(160)
        self.flt_search.setClearButtonEnabled(True)
        self.flt_search.textChanged.connect(self.refresh)
        filt.addWidget(self.flt_search)
        self.flt_exit = QComboBox()
        for label, val in [("All Exits", None), ("Target Hit", "target_hit"),
                           ("Trailing Stop", "trailing_stop"), ("Manual", "manual"),
                           ("Stop Loss", "stop_loss"), ("Time Exit", "time_exit"),
                           ("Stop Out", "stop_out")]:
            self.flt_exit.addItem(label, val)
        filt.addWidget(self.flt_exit)
        self.flt_outcome = QComboBox()
        self.flt_outcome.addItems(["All P&L", "Winners", "Losers", "Breakeven"]); filt.addWidget(self.flt_outcome)
        self.flt_tag = QComboBox(); self.flt_tag.addItem("All Tags", None)
        self.flt_tag.setMinimumWidth(100); filt.addWidget(self.flt_tag)
        btn_clear = QPushButton("Clear"); btn_clear.clicked.connect(self._clear_filters)
        filt.addWidget(btn_clear)
        filt.addStretch()
        layout.addLayout(filt)
        for w in [self.flt_setup, self.flt_direction, self.flt_status,
                  self.flt_grade, self.flt_exit, self.flt_outcome, self.flt_period,
                  self.flt_tag]:
            w.currentIndexChanged.connect(self._on_filter_changed)
        self.flt_search.textChanged.disconnect(self.refresh)
        self.flt_search.textChanged.connect(self._on_filter_changed)

        # ── Split pane: Table (left) | Preview (right) ──
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(self.splitter, 1)  # stretch

        # Left: trade table
        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        # Keep selection highlight colour consistent when the table loses focus
        # (e.g. when the user clicks "Fetch Chart" in the preview panel).
        # Qt's Fusion theme uses a separate Inactive palette group for unfocused
        # widgets, which renders the selected row in a washed-out gray.
        # The correct, theme-aware fix is to copy the Active Highlight colours
        # into the Inactive group so the row stays visually selected regardless
        # of which widget currently has keyboard focus.
        _pal = self.table.palette()
        _pal.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight,
                      _pal.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight))
        _pal.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.HighlightedText,
                      _pal.color(QPalette.ColorGroup.Active, QPalette.ColorRole.HighlightedText))
        self.table.setPalette(_pal)
        self.table.doubleClicked.connect(self._on_edit)
        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self.splitter.addWidget(self.table)

        # Right: preview panel
        self._build_preview_panel()

        self._splitter_sized = False

    def showEvent(self, event):
        super().showEvent(event)
        if not self._splitter_sized:
            # Defer one event-loop tick so the window is fully laid out and
            # sum(splitter.sizes()) reflects the real available width.
            # resizeEvent fired too early on Windows (before maximise completes),
            # producing wrong proportions at some DPI-scaling settings.
            QTimer.singleShot(0, self._set_initial_split)

    def _set_initial_split(self):
        total = sum(self.splitter.sizes())
        if total > 0:
            self._splitter_sized = True
            self.splitter.setSizes([int(total * 0.58), int(total * 0.42)])

    def _build_preview_panel(self):
        """Build the persistent read-only trade preview panel."""
        outer = QWidget()
        outer.setMinimumWidth(320)
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.setSpacing(0)

        vsplit = QSplitter(Qt.Orientation.Vertical)
        outer_lay.addWidget(vsplit)

        # Top pane: metrics and info
        metrics_widget = QWidget()
        metrics_lay = QVBoxLayout(metrics_widget)
        metrics_lay.setContentsMargins(12, 8, 12, 4)
        metrics_lay.setSpacing(4)

        # Header
        self.pv_header = QLabel("Select a trade")
        self.pv_header.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.pv_header.setWordWrap(True)
        metrics_lay.addWidget(self.pv_header)

        # Status/direction badges
        self.pv_badges = QLabel("")
        self.pv_badges.setStyleSheet("font-size: 14px;")
        metrics_lay.addWidget(self.pv_badges)

        # Separator
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        metrics_lay.addWidget(sep)

        # P&L hero — large, prominent P&L display
        self.pv_pnl_hero = QLabel("")
        self.pv_pnl_hero.setTextFormat(Qt.TextFormat.RichText)
        self.pv_pnl_hero.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pv_pnl_hero.setStyleSheet("font-size: 22px; font-weight: bold; padding: 6px 0;")
        metrics_lay.addWidget(self.pv_pnl_hero)

        # Metrics grid
        self.pv_metrics = QLabel("")
        self.pv_metrics.setTextFormat(Qt.TextFormat.RichText)
        self.pv_metrics.setWordWrap(True)
        self.pv_metrics.setStyleSheet("font-size: 12px; line-height: 1.6;")
        metrics_lay.addWidget(self.pv_metrics)

        # Notes
        self.pv_notes_label = QLabel("")
        self.pv_notes_label.setTextFormat(Qt.TextFormat.RichText)
        self.pv_notes_label.setWordWrap(True)
        self.pv_notes_label.setStyleSheet("font-size: 11px;")
        metrics_lay.addWidget(self.pv_notes_label)

        # Rule checks
        self.pv_rules_label = QLabel("")
        self.pv_rules_label.setTextFormat(Qt.TextFormat.RichText)
        self.pv_rules_label.setWordWrap(True)
        self.pv_rules_label.setStyleSheet("font-size: 11px;")
        metrics_lay.addWidget(self.pv_rules_label)

        # Edit button
        self.pv_edit_btn = QPushButton("Edit Trade...")
        self.pv_edit_btn.setStyleSheet("font-size: 13px; padding: 8px;")
        self.pv_edit_btn.clicked.connect(self._on_edit)
        self.pv_edit_btn.setVisible(False)
        metrics_lay.addWidget(self.pv_edit_btn)

        metrics_lay.addStretch()
        vsplit.addWidget(metrics_widget)

        # Bottom pane: chart widget (renders cached OHLC data)
        from chart_widget import TradeChartWidget
        self.pv_chart = TradeChartWidget(parent=outer, conn=self.conn)
        self.pv_chart.setMinimumHeight(150)
        vsplit.addWidget(self.pv_chart)

        vsplit.setSizes([260, 320])
        vsplit.setStretchFactor(0, 0)
        vsplit.setStretchFactor(1, 1)

        self.splitter.addWidget(outer)

    # ── Preview panel update ──

    def _on_selection_changed(self, selected, deselected):
        """Update preview when a row is clicked."""
        indexes = selected.indexes()
        if not indexes:
            self._clear_preview()
            return
        row = indexes[0].row()
        id_item = self.table.item(row, 0)
        if not id_item or not id_item.text():
            self._show_event_preview(row)
            return
        try:
            tid = int(id_item.text())
        except ValueError:
            self._clear_preview()
            return
        self._show_trade_preview(tid)

    def _clear_preview(self):
        self.pv_header.setText("Select a trade")
        self.pv_badges.setText("")
        self.pv_pnl_hero.setText("")
        self.pv_metrics.setText("")
        self.pv_notes_label.setText("")
        self.pv_rules_label.setText("")
        self.pv_chart._show_placeholder()
        self.pv_edit_btn.setVisible(False)
        self._selected_trade_id = None

    def _show_event_preview(self, row):
        """Show preview for a deposit/withdrawal event."""
        instr_item = self.table.item(row, 2)
        pnl_col = getattr(self, '_pnl_col_idx', None)
        pnl_item = self.table.item(row, pnl_col) if pnl_col is not None else None
        self.pv_header.setText(instr_item.text() if instr_item else "Event")
        self.pv_badges.setText("")
        self.pv_pnl_hero.setText("")
        self.pv_metrics.setText(
            f"<b>Amount:</b> {pnl_item.text()}" if pnl_item else ""
        )
        self.pv_notes_label.setText("")
        self.pv_rules_label.setText("")
        self.pv_chart._show_placeholder()
        self.pv_edit_btn.setVisible(False)
        self._selected_trade_id = None

    def _show_trade_preview(self, trade_id):
        """Populate the preview panel with trade details."""
        t = get_trade(self.conn, trade_id)
        if not t:
            self._clear_preview()
            return
        self._selected_trade_id = trade_id

        # Header
        symbol = t['symbol'] or '?'
        self.pv_header.setText(symbol)

        # Badges
        direction = (t['direction'] or 'long').upper()
        status = t['status'] or 'open'
        epnl = effective_pnl(t)

        if direction == 'LONG':
            dir_html = '<span style="color:#fff;background:#16a34a;padding:2px 8px;border-radius:3px;font-weight:bold;">▲ LONG</span>'
        else:
            dir_html = '<span style="color:#fff;background:#dc2626;padding:2px 8px;border-radius:3px;font-weight:bold;">▼ SHORT</span>'

        if status == 'open':
            st_html = '<span style="color:#fff;background:#3b82f6;padding:2px 8px;border-radius:3px;font-weight:bold;">OPEN</span>'
        elif epnl > 0:
            st_html = '<span style="color:#fff;background:#16a34a;padding:2px 8px;border-radius:3px;font-weight:bold;">WIN</span>'
        elif epnl < 0:
            st_html = '<span style="color:#fff;background:#dc2626;padding:2px 8px;border-radius:3px;font-weight:bold;">LOSS</span>'
        else:
            st_html = '<span style="color:#fff;background:#6b7280;padding:2px 8px;border-radius:3px;font-weight:bold;">B/E</span>'

        self.pv_badges.setTextFormat(Qt.TextFormat.RichText)
        self.pv_badges.setText(f"{dir_html}&nbsp;&nbsp;{st_html}")

        # P&L Hero (effective P&L: includes swap + commission)
        pc = '#008200' if epnl > 0 else '#c80000' if epnl < 0 else '#666'
        self.pv_pnl_hero.setText(f"<span style='color:{pc}'>{epnl:+.2f}</span>")

        # Metrics
        entry = t['entry_price'] or 0
        exit_p = t['exit_price']
        sl = t['stop_loss_price']
        tp = t['take_profit_price']
        size = t['position_size'] or 0
        currency = t['account_currency'] or '€'
        risk_pct = t['risk_percent']
        grade = t['execution_grade'] or '—'
        conf = t['confidence_rating']
        setup = t['setup_name'] or '—'

        lines = []
        lines.append(f"<b>Account:</b> {t['account_name']}")
        lines.append(f"<b>Entry:</b> {(t['entry_date'] or '')[:16]} @ {entry:.5g}")
        if exit_p:
            lines.append(f"<b>Exit:</b> {(t['exit_date'] or '')[:16]} @ {exit_p:.5g}")
        lines.append(f"<b>Size:</b> {size:.4g}")
        if sl: lines.append(f"<b>SL:</b> {sl:.5g}")
        if tp: lines.append(f"<b>TP:</b> {tp:.5g}")

        # R:R and R Multiple
        if entry > 0 and sl and sl > 0 and entry != sl:
            risk_dist = abs(entry - sl)
            if tp and tp > 0:
                reward_dist = abs(tp - entry)
                rr = reward_dist / risk_dist if risk_dist > 0 else 0
                lines.append(f"<b>R:R:</b> <span style='color:#3b82f6'>1:{rr:.1f}</span>")
            if exit_p and exit_p > 0:
                actual = (exit_p - entry) if direction == 'LONG' else (entry - exit_p)
                r_mult = actual / risk_dist if risk_dist > 0 else 0
                rc = '#008200' if r_mult > 0 else '#c80000' if r_mult < 0 else '#666'
                lines.append(f"<b>R Multiple:</b> <span style='color:{rc}'>{r_mult:+.2f}R</span>")

        if risk_pct: lines.append(f"<b>Risk:</b> {risk_pct:.2f}%")

        # Holding duration
        if t['entry_date'] and t['exit_date']:
            try:
                from datetime import datetime as _dt
                ed = _dt.strptime(t['entry_date'][:10], '%Y-%m-%d')
                xd = _dt.strptime(t['exit_date'][:10], '%Y-%m-%d')
                days = (xd - ed).days
                if days >= 0:
                    lines.append(f"<b>Duration:</b> {days} day{'s' if days != 1 else ''}")
            except (ValueError, TypeError):
                pass

        lines.append("")
        lines.append(f"<b>Setup:</b> {setup}")
        if t['exit_reason']: lines.append(f"<b>Exit Reason:</b> {t['exit_reason']}")
        lines.append(f"<b>Grade:</b> {grade}")
        if conf: lines.append(f"<b>Confidence:</b> {'★' * conf}{'☆' * (5 - conf)}")

        tags = get_trade_tags(self.conn, trade_id)
        if tags:
            chips = ' '.join(
                f'<span style="background:#e0e7ff;color:#3730a3;padding:1px 6px;'
                f'border-radius:3px;font-size:11px;">{_esc(tag["name"])}</span>'
                for tag in tags
            )
            lines.append(f"<b>Tags:</b> {chips}")

        self.pv_metrics.setText("<br>".join(lines))

        # Notes
        notes_parts = []
        if t['pre_trade_notes']:
            notes_parts.append(f"<b>Pre-trade:</b><br><i>{_esc(t['pre_trade_notes'])}</i>")
        if t['post_trade_notes']:
            notes_parts.append(f"<b>Post-trade:</b><br><i>{_esc(t['post_trade_notes'])}</i>")
        self.pv_notes_label.setText("<br><br>".join(notes_parts) if notes_parts else "")

        # Rule checks
        checks = get_trade_rule_checks(self.conn, trade_id)
        if checks:
            rc_lines = ["<b>Rule Checklist:</b>"]
            for c in checks:
                icon = "✅" if c['was_met'] else "❌"
                rc_lines.append(f"&nbsp;&nbsp;{icon} {_esc(c['rule_text'])}")
            self.pv_rules_label.setText("<br>".join(rc_lines))
        else:
            self.pv_rules_label.setText("")

        # Chart — load from cached OHLC data
        chart_data = {
            'id': t['id'],
            'symbol': t['symbol'] or '', 'direction': t['direction'],
            'entry_date': t['entry_date'], 'exit_date': t['exit_date'],
            'entry_price': t['entry_price'], 'exit_price': t['exit_price'],
            'stop_loss': t['stop_loss_price'], 'take_profit': t['take_profit_price'],
            'pnl_account_currency': t['pnl_account_currency'],
        }
        acct = get_account(self.conn, t['account_id']) if t['account_id'] else None
        self.pv_chart.asset_type = (acct['asset_type'] if acct else 'forex')
        self.pv_chart.set_trade(chart_data)
        cached = t['chart_data'] if 'chart_data' in t.keys() else None
        if cached:
            self.pv_chart.load_cached_data(cached)
        else:
            self.pv_chart._show_placeholder()

        self.pv_edit_btn.setVisible(True)

    # ── Filter helpers ──

    def _clear_filters(self):
        for w in [self.flt_setup, self.flt_direction, self.flt_status,
                  self.flt_grade, self.flt_exit, self.flt_outcome, self.flt_period,
                  self.flt_tag]:
            w.blockSignals(True); w.setCurrentIndex(0); w.blockSignals(False)
        self.flt_search.blockSignals(True)
        self.flt_search.clear()
        self.flt_search.blockSignals(False)
        self._page = 0
        self.refresh()

    def refresh_setup_filter(self):
        self.flt_setup.blockSignals(True)
        cur = self.flt_setup.currentData()
        self.flt_setup.clear(); self.flt_setup.addItem("All Setups", None)
        for s in get_setup_types(self.conn): self.flt_setup.addItem(s['name'], s['id'])
        if cur is not None:
            idx = self.flt_setup.findData(cur)
            if idx >= 0: self.flt_setup.setCurrentIndex(idx)
        self.flt_setup.blockSignals(False)

    def refresh_tag_filter(self):
        self.flt_tag.blockSignals(True)
        cur = self.flt_tag.currentData()
        self.flt_tag.clear()
        self.flt_tag.addItem("All Tags", None)
        for tag in get_tags(self.conn):
            self.flt_tag.addItem(tag['name'], tag['id'])
        idx = self.flt_tag.findData(cur)
        if idx >= 0:
            self.flt_tag.setCurrentIndex(idx)
        self.flt_tag.blockSignals(False)

    def _on_filter_changed(self):
        """Reset to page 0 and refresh whenever any filter changes."""
        self._page = 0
        self.refresh()

    def _on_prev_page(self):
        if self._page > 0:
            self._page -= 1
            self.refresh()

    def _on_next_page(self):
        self._page += 1
        self.refresh()

    def _get_period_range(self):
        """Return (period_from, period_to) date objects based on flt_period."""
        today = datetime.now().date()
        flt_period = self.flt_period.currentText()
        period_from = period_to = None
        if flt_period == "This Month":
            period_from = today.replace(day=1)
        elif flt_period == "Last Month":
            first_this = today.replace(day=1)
            period_from = (first_this - timedelta(days=1)).replace(day=1)
            period_to = first_this - timedelta(days=1)
        elif flt_period == "This Year":
            period_from = today.replace(month=1, day=1)
        elif flt_period == "Last 30 Days":
            period_from = today - timedelta(days=30)
        elif flt_period == "Last 90 Days":
            period_from = today - timedelta(days=90)
        return period_from, period_to

    def _build_filter_kwargs(self):
        """Translate UI filter state into kwargs for get_trades_paged / get_trades_all_filtered."""
        period_from, period_to = self._get_period_range()
        flt_dir = self.flt_direction.currentText()
        flt_status = self.flt_status.currentText()
        flt_outcome = self.flt_outcome.currentText()

        kwargs = {}
        setup_id = self.flt_setup.currentData()
        if setup_id is not None:
            kwargs['setup_id'] = setup_id
        if flt_dir == 'Long':
            kwargs['direction'] = 'long'
        elif flt_dir == 'Short':
            kwargs['direction'] = 'short'
        if flt_status == 'Open':
            kwargs['status'] = 'open'
        elif flt_status == 'Closed':
            kwargs['status'] = 'closed'
        grade = self.flt_grade.currentText()
        if grade not in ('All Grades',):
            kwargs['grade'] = grade
        exit_reason = self.flt_exit.currentData()
        if exit_reason is not None:
            kwargs['exit_reason'] = exit_reason
        if flt_outcome == 'Winners':
            kwargs['outcome'] = 'winners'
        elif flt_outcome == 'Losers':
            kwargs['outcome'] = 'losers'
        elif flt_outcome == 'Breakeven':
            kwargs['outcome'] = 'breakeven'
        tag_id = self.flt_tag.currentData()
        if tag_id is not None:
            kwargs['tag_id'] = tag_id
        sym = self.flt_search.text().strip()
        if sym:
            kwargs['symbol_search'] = sym
        if period_from is not None:
            kwargs['date_from'] = str(period_from)
        if period_to is not None:
            kwargs['date_to'] = str(period_to)
        return kwargs

    def _get_module(self):
        aid = self.aid()
        if aid:
            acct = get_account(self.conn, aid)
            if acct: return get_module(acct['asset_type'])
        return get_module('forex')

    # ── KPI update ──

    def _update_kpi(self, filtered_trades):
        """Update KPI cards from the already-filtered trade list."""
        closed = [t for t in filtered_trades if (t['status'] or '') == 'closed']
        _blank = [self.kpi_trades, self.kpi_winrate, self.kpi_pnl,
                  self.kpi_expectancy, self.kpi_pf]
        if not closed:
            for card in _blank:
                card.set_value("—", "#666")
            return

        winners = [t for t in closed if effective_pnl(t) > 0]
        losers  = [t for t in closed if effective_pnl(t) < 0]
        total = len(closed)
        gross_profit = sum(effective_pnl(t) for t in winners)
        gross_loss   = abs(sum(effective_pnl(t) for t in losers))
        net_pnl = sum(effective_pnl(t) for t in closed)
        avg_win  = gross_profit / len(winners) if winners else 0
        avg_loss = gross_loss  / len(losers)  if losers  else 0
        win_rate = len(winners) / total * 100
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        expectancy = (win_rate / 100 * avg_win) - ((1 - win_rate / 100) * avg_loss)

        self.kpi_trades.set_value(
            f"{total}  ({len(winners)}W / {len(losers)}L)", "#333")

        self.kpi_winrate.set_value(
            f"{win_rate:.1f}%", "#008200" if win_rate >= 50 else "#c80000")

        self.kpi_pnl.set_value(
            f"{net_pnl:+.2f}", "#008200" if net_pnl > 0 else "#c80000" if net_pnl < 0 else "#666")

        self.kpi_expectancy.set_value(
            f"{expectancy:+.2f}", "#008200" if expectancy > 0 else "#c80000" if expectancy < 0 else "#666")

        pfs = f"{profit_factor:.2f}" if profit_factor != float('inf') else "∞"
        self.kpi_pf.set_value(
            pfs, "#008200" if profit_factor > 1 else "#c80000" if profit_factor < 1 else "#666")

    # ── Table refresh ──

    def refresh(self):
        aid = self.aid()
        mod = self._get_module()
        filters = self._build_filter_kwargs()

        # All matching trades — for KPI and export (no LIMIT)
        all_trades = get_trades_all_filtered(self.conn, account_id=aid, **filters)
        total = len(all_trades)

        # Clamp page to valid range
        page_count = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
        if self._page >= page_count:
            self._page = max(0, page_count - 1)

        # Current page — for the table display
        page_trades = get_trades_paged(
            self.conn, account_id=aid, page=self._page,
            page_size=_PAGE_SIZE, **filters
        )

        # Update pagination controls
        self.btn_prev.setEnabled(self._page > 0)
        self.btn_next.setEnabled(self._page < page_count - 1)
        self.lbl_page.setText(
            f"Page {self._page + 1} of {page_count} · {total} trades"
        )

        chart_counts = get_trade_chart_counts(self.conn, aid)
        events = get_account_events(self.conn, aid) if aid else []
        period_from, period_to = self._get_period_range()

        # Build columns dynamically
        mod_cols = mod.trade_columns() if mod else []
        mod_type = mod.ASSET_TYPE if mod else None
        _N_PREFIX = 4   # fixed columns before mod_cols
        _columns_changed = not hasattr(self, '_mod_type') or self._mod_type != mod_type
        if _columns_changed:
            self._mod_type = mod_type
            headers = ['ID', 'Date', 'Instrument', 'Dir']
            headers += [c['header'] for c in mod_cols]
            headers += ['P&L', 'Setup', 'Pics', 'Status']
            self.table.setColumnCount(len(headers))
            self.table.setHorizontalHeaderLabels(headers)
            self.table.setColumnHidden(0, True)
            h = self.table.horizontalHeader()
            self._setup_col_idx = _N_PREFIX + len(mod_cols) + 1
            h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            h.setStretchLastSection(False)

        # Column layout: ID(hidden) | Date | Instrument | Dir | <mod_cols> | P&L | Setup | Pics | Status
        instr_idx  = 2
        pnl_idx    = _N_PREFIX + len(mod_cols)
        setup_idx  = pnl_idx + 1  # noqa: F841
        pics_idx   = pnl_idx + 2  # noqa: F841
        status_idx = pnl_idx + 3
        self._pnl_col_idx = pnl_idx  # stored for use in _show_event_preview

        # Build rows: current page trades + date-filtered events (interleaved by date)
        rows_data = []
        for t in page_trades:
            rows_data.append((t['entry_date'] or '', 'trade', t))
        for ev in events:
            ev_date = (ev['event_date'] or '')[:10]
            if period_from is not None and ev_date < str(period_from): continue
            if period_to is not None and ev_date > str(period_to): continue
            rows_data.append((ev_date, 'event', ev))
        rows_data.sort(key=lambda x: x[0], reverse=True)

        self.table.setUpdatesEnabled(False)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows_data))

        dep_bg = QColor(230, 245, 230)
        wd_bg = QColor(250, 235, 235)
        profit_fg = QColor(0, 130, 0)
        loss_fg = QColor(200, 0, 0)
        neutral_fg = QColor(100, 100, 100)
        long_fg = QColor(0, 100, 180)
        short_fg = QColor(180, 80, 0)

        # Status badge colors
        status_colors = {
            'win':  (QColor(255, 255, 255), QColor(22, 163, 106)),   # white on green
            'loss': (QColor(255, 255, 255), QColor(220, 38, 38)),    # white on red
            'open': (QColor(255, 255, 255), QColor(59, 130, 246)),   # white on blue
            'be':   (QColor(255, 255, 255), QColor(107, 114, 128)),  # white on gray
        }

        for row, (_, rtype, data) in enumerate(rows_data):
            if rtype == 'trade':
                t = data
                epnl = effective_pnl(t)
                raw_pnl = t['pnl_account_currency'] or 0
                pc = profit_fg if epnl > 0 else loss_fg if epnl < 0 else neutral_fg
                cc = chart_counts.get(t['id'], 0)

                # Determine status display (use effective P&L for WIN/LOSS classification)
                status = t['status'] or 'open'
                if status == 'closed':
                    if epnl > 0:
                        status_text, status_key = 'WIN', 'win'
                    elif epnl < 0:
                        status_text, status_key = 'LOSS', 'loss'
                    else:
                        status_text, status_key = 'B/E', 'be'
                else:
                    status_text, status_key = 'OPEN', 'open'

                dir_val = t['direction'] or ''
                dir_text = 'Long' if dir_val == 'long' else 'Short' if dir_val == 'short' else dir_val.capitalize()
                cells = [str(t['id']), (t['entry_date'] or '')[:16], t['symbol'] or '', dir_text]
                for c in mod_cols:
                    cells.append(mod.format_trade_cell(t, c['key']) if mod else '')
                cells += [f"{raw_pnl:+.2f}", t['setup_name'] or '', str(cc) if cc else '',
                          status_text]

                for col, val in enumerate(cells):
                    item = _NumItem(val)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    if col == pnl_idx:
                        item.setForeground(pc)
                        item.setFont(QFont("", -1, QFont.Weight.Bold))
                    if col == 3:  # Direction
                        item.setForeground(long_fg if val == 'Long' else short_fg)
                    if col == status_idx:  # Status badge
                        fg_c, bg_c = status_colors.get(status_key, status_colors['open'])
                        item.setForeground(fg_c)
                        item.setBackground(bg_c)
                        item.setFont(QFont("", -1, QFont.Weight.Bold))
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.table.setItem(row, col, item)
            else:
                ev = data; amt = ev['amount']
                bg = dep_bg if amt > 0 else wd_bg
                etype = (ev['event_type'] or 'UNKNOWN').upper()
                cells = ['', (ev['event_date'] or '')[:16], f"\U0001f4b0 {etype}", '']
                cells += [''] * len(mod_cols)
                cells += [f"{amt:+.2f}", ev['description'] or '', '', '']
                for col, val in enumerate(cells):
                    item = _NumItem(val)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    item.setBackground(bg)
                    if col == instr_idx:
                        item.setFont(QFont("", -1, QFont.Weight.Bold))
                        item.setForeground(profit_fg if amt > 0 else loss_fg)
                    if col == pnl_idx:
                        item.setForeground(profit_fg if amt > 0 else loss_fg)
                        item.setFont(QFont("", -1, QFont.Weight.Bold))
                    self.table.setItem(row, col, item)

        self.table.setUpdatesEnabled(True)
        if _columns_changed:
            self.table.resizeColumnsToContents()
            w = self.table.columnWidth(self._setup_col_idx)
            self.table.setColumnWidth(self._setup_col_idx, max(60, min(w, 130)))
        self.table.setSortingEnabled(True)

        event_count = sum(1 for _, rt, _ in rows_data if rt == 'event')
        msg = f"Loaded {total} trades"
        if event_count: msg += f", {event_count} deposits/withdrawals"
        self._status(msg)

        # All filtered trades: used for KPI (across all pages) and for export
        self._visible_trades = list(all_trades)

        # Update KPI cards from the complete filtered trade set
        self._update_kpi(self._visible_trades)

        # Re-select previously selected trade if still in current page
        if self._selected_trade_id:
            self._reselect_trade(self._selected_trade_id)

    def _reselect_trade(self, trade_id):
        """Try to re-select the previously selected trade after refresh."""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.text() == str(trade_id):
                self.table.selectRow(row)
                return
        self._clear_preview()

    # ── CRUD ──

    def _validate_trade(self, v) -> str:
        """Return an error message string if v has invalid fields, else ''."""
        errors = []
        if not v.get('instrument_id'):
            errors.append("Instrument is required.")
        if not v.get('entry_date'):
            errors.append("Entry Date is required.")
        if (v.get('entry_price') or 0) <= 0:
            errors.append("Entry Price must be greater than zero.")
        if (v.get('position_size') or 0) <= 0:
            errors.append("Position Size must be greater than zero.")
        if v.get('exit_date') and v.get('entry_date') and v['exit_date'] < v['entry_date']:
            errors.append("Exit Date cannot be before Entry Date.")
        return "\n".join(errors)

    def _on_new(self):
        if not get_accounts(self.conn):
            QMessageBox.warning(self, "No Accounts", "Create an account first."); return
        dlg = TradeDialog(self, self.conn, default_account_id=self.aid())
        if dlg.exec():
            v = dlg.get_values()
            err = self._validate_trade(v)
            if err:
                QMessageBox.warning(self, "Validation Error", err); return
            try:
                tid = create_trade(self.conn, **v)
                self._save_screenshots(tid, dlg)
                checks = dlg.get_rule_checks()
                if checks: save_trade_rule_checks(self.conn, tid, checks)
                tag_names = dlg.get_tag_names()
                tag_ids = [get_or_create_tag(self.conn, n) for n in tag_names]
                set_trade_tags(self.conn, tid, tag_ids)
                self.refresh_tag_filter()
                self.data_changed.emit()
            except Exception as e: QMessageBox.critical(self, "Error", str(e))

    def _on_edit(self):
        r = self.table.currentRow()
        if r < 0: return
        id_item = self.table.item(r, 0)
        if not id_item: return
        id_text = id_item.text()
        if not id_text: return
        tid = int(id_text)
        trade = get_trade(self.conn, tid)
        if not trade: return
        dlg = TradeDialog(self, self.conn, trade=trade)
        if dlg.exec():
            try:
                vals = dlg.get_values()
                err = self._validate_trade(vals)
                if err:
                    QMessageBox.warning(self, "Validation Error", err); return
                chart_json = dlg.chart_widget.get_cached_data_json()
                if chart_json: vals['chart_data'] = chart_json
                update_trade(self.conn, tid, **vals)
                for cid in dlg.get_delete_chart_ids():
                    fpath = delete_trade_chart(self.conn, cid)
                    if fpath and os.path.exists(fpath):
                        try: os.remove(fpath)
                        except OSError: pass
                self._save_screenshots(tid, dlg)
                checks = dlg.get_rule_checks()
                if checks: save_trade_rule_checks(self.conn, tid, checks)
                tag_names = dlg.get_tag_names()
                tag_ids = [get_or_create_tag(self.conn, n) for n in tag_names]
                set_trade_tags(self.conn, tid, tag_ids)
                self.refresh_tag_filter()
                self._selected_trade_id = tid
                self.data_changed.emit()
            except Exception as e: QMessageBox.critical(self, "Error", str(e))

    def _on_delete(self):
        r = self.table.currentRow()
        if r < 0: return
        id_item = self.table.item(r, 0)
        if not id_item: return
        id_text = id_item.text()
        if not id_text: return
        tid = int(id_text)
        if QMessageBox.question(self, "Delete", f"Delete trade #{tid}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            delete_trade(self.conn, tid); self.data_changed.emit()

    def _save_screenshots(self, trade_id, dlg):
        for src_type, src_path in dlg.get_pending_screenshots():
            ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            ext = os.path.splitext(src_path)[1] or '.png'
            dest = os.path.join(SCREENSHOTS_DIR, f"trade_{trade_id}_{ts}{ext}")
            if src_type == 'file': shutil.copy2(src_path, dest)
            elif src_type == 'clipboard':
                if src_path != dest: shutil.move(src_path, dest)
            add_trade_chart(self.conn, trade_id, 'screenshot', dest, caption=os.path.basename(src_path))

    # ── Export ──

    def _on_export(self):
        """Export the currently visible (filtered) trades to a CSV file.

        Exports exactly the trades shown in the table, respecting all active
        filters (account, status, direction, period, grade, exit reason,
        outcome, symbol search). Includes a computed 'Net P&L' column
        (pnl + swap + commission) in addition to the raw DB columns.
        """
        if not self._visible_trades:
            QMessageBox.information(self, "Export", "No trades to export.")
            return

        aid = self.aid()
        acct = get_account(self.conn, aid) if aid else None
        acct_name = acct['name'].replace(' ', '_') if acct else 'trades'
        default_name = f"{acct_name}_export_{datetime.now().strftime('%Y%m%d')}.csv"

        fp, _ = QFileDialog.getSaveFileName(
            self, "Export Trades", default_name,
            "CSV Files (*.csv);;All Files (*.*)")
        if not fp:
            return

        try:
            with open(fp, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                # Header: all DB columns + computed Net P&L
                writer.writerow([label for _, label in EXPORT_COLUMNS] + ['Net P&L'])
                for t in self._visible_trades:
                    row = []
                    for key, _ in EXPORT_COLUMNS:
                        val = t[key] if key in t.keys() else ''
                        row.append('' if val is None else val)
                    row.append(round(effective_pnl(t), 8))
                    writer.writerow(row)

            count = len(self._visible_trades)
            self._status(f"Exported {count} trades to {os.path.basename(fp)}")
            QMessageBox.information(self, "Export Complete",
                f"Exported {count} trades to:\n{fp}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", str(e))

    # ── Import ──

    def _on_import(self):
        from import_manager import get_available_plugins, run_import, detect_plugin

        plugins = get_available_plugins()
        filters = []
        all_exts = []
        for _name, display, exts in plugins:
            ext_glob = ' '.join(f'*{e}' for e in exts)
            filters.append(f"{display} ({ext_glob})")
            all_exts.extend(f'*{e}' for e in exts)
        all_glob = ' '.join(all_exts)
        filters.insert(0, f"All Supported ({all_glob})")
        filters.append("All Files (*.*)")
        filter_str = ';;'.join(filters)

        fp, _ = QFileDialog.getOpenFileName(self, "Import Trades", "", filter_str)
        if not fp: return

        accounts = get_accounts(self.conn)
        aid = self.aid()

        if aid is None:
            dlg = QDialog(self); dlg.setWindowTitle("Select Account")
            from PyQt6.QtWidgets import QVBoxLayout as VL
            lay = VL(dlg)
            combo = QComboBox()
            if accounts:
                lay.addWidget(QLabel("Import into which account?"))
                for a in accounts: combo.addItem(f"{a['name']} ({a['currency']})", a['id'])
            else:
                lay.addWidget(QLabel("No accounts yet — create one from the statement, "
                                     "or cancel and create one manually."))
            lay.addWidget(combo)

            plugin = detect_plugin(fp)
            if plugin and hasattr(plugin, 'parse_account_info'):
                try:
                    info = plugin.parse_account_info(fp)
                    if info.get('broker'):
                        asset_type = getattr(plugin, 'DEFAULT_ASSET_TYPE', 'forex')
                        btn = QPushButton(f"+ Create from statement: "
                                          f"{info.get('account_number','')} @ {info['broker']}")
                        def _ac(checked=False, info=info, asset_type=asset_type):
                            base_name = f"{info.get('broker','?')} - {info.get('account_number','New')}"
                            name = base_name; suffix = 2
                            while True:
                                existing = self.conn.execute(
                                    "SELECT id FROM accounts WHERE name = ?", (name,)).fetchone()
                                if not existing: break
                                name = f"{base_name} ({suffix})"; suffix += 1
                            try:
                                nid = create_account(self.conn, name=name,
                                    broker=info.get('broker','?'),
                                    account_number=info.get('account_number'),
                                    currency=info.get('currency','EUR'),
                                    asset_type=asset_type)
                                combo.addItem(f"NEW: {name} ({info.get('currency','EUR')})", nid)
                                combo.setCurrentIndex(combo.count()-1)
                                btn.setEnabled(False); btn.setText(f"Created: {name}")
                                self.data_changed.emit()
                            except Exception as e:
                                QMessageBox.critical(dlg, "Error", str(e))
                        btn.clicked.connect(_ac); lay.addWidget(btn)
                except Exception:
                    pass

            bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject); lay.addWidget(bb)
            if not dlg.exec(): return
            aid = combo.currentData()

        if aid is None:
            QMessageBox.warning(self, "No Account", "No account selected."); return

        prog = QProgressDialog("Importing…", None, 0, 100, self)
        prog.setWindowTitle("Import")
        prog.setMinimumDuration(400)
        prog.setWindowModality(Qt.WindowModality.WindowModal)

        def _progress(current, total):
            if total > 0:
                prog.setValue(int(current / total * 95))
            QApplication.processEvents()

        self._status("Importing..."); QApplication.processEvents()
        result = run_import(self.conn, aid, fp, progress_cb=_progress)
        prog.setValue(100)
        msg = result['message']
        if result['errors']: msg += "\n\nErrors:\n" + "\n".join(result['errors'][:10])
        if result['success']: QMessageBox.information(self, "Import Complete", msg)
        else: QMessageBox.critical(self, "Import Failed", msg)
        self.data_changed.emit()


def _esc(text):
    """Escape HTML special characters for safe display."""
    if not text: return ''
    return (text.replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('\n', '<br>'))
