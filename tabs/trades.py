"""Trades tab — KPI cards, split-pane table+preview, filters, CRUD actions."""
import os
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QTableWidget, QHeaderView,
    QAbstractItemView, QApplication, QFrame, QSplitter,
    QLineEdit,
)
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QShortcut, QKeySequence, QPalette

from tabs import BaseTab
import theme as _theme
from database import (
    get_account, get_trade_chart_counts,
    get_account_events,
    get_setup_types,
    get_app_data_dir, effective_pnl,
    get_tags, get_trade_tags,
    get_trades_paged, get_trades_all_filtered,
)

from tabs.trades_widgets import _NumItem, KPICard
from tabs.trades_preview import TradesPreviewMixin, _esc  # noqa: F401 (re-exported for tests)
from tabs.trades_actions import TradesActionsMixin

_PAGE_SIZE = 500
from asset_modules import get_module

SCREENSHOTS_DIR = os.path.join(get_app_data_dir(), 'screenshots')
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)


# ── Main TradesTab ────────────────────────────────────────────────────────

class TradesTab(TradesPreviewMixin, TradesActionsMixin, BaseTab):
    jump_to_journal = pyqtSignal(str)   # emits YYYY-MM-DD date string

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
        b = QPushButton("Export..."); b.clicked.connect(self._on_export); tb.addWidget(b)
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
        self.btn_prev = QPushButton()
        self.btn_prev.setIcon(QIcon(_theme._ARROW_LEFT_PATH))
        self.btn_prev.setIconSize(QSize(8, 12))
        self.btn_prev.setFixedSize(28, 24)
        self.btn_prev.setEnabled(False)
        self.btn_prev.setToolTip("Previous page")
        self.btn_prev.clicked.connect(self._on_prev_page)
        self.lbl_page = QLabel("Page 1 of 1 · 0 trades")
        self.lbl_page.setStyleSheet(
            "font-size: 11px; font-weight: bold; padding: 0 4px;"
        )
        self.btn_next = QPushButton()
        self.btn_next.setIcon(QIcon(_theme._ARROW_RIGHT_PATH))
        self.btn_next.setIconSize(QSize(8, 12))
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

        # ── Search bar — directly above the table ──
        search_row = QHBoxLayout()
        search_row.setSpacing(4)
        self.flt_search = QLineEdit()
        self.flt_search.setPlaceholderText("Filter by instrument…")
        self.flt_search.setMaximumWidth(320)
        self.flt_search.setClearButtonEnabled(True)
        self.flt_search.textChanged.connect(self._on_filter_changed)
        search_row.addWidget(self.flt_search)
        search_row.addStretch()
        layout.addLayout(search_row)

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
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
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

    def refresh_chart_theme(self):
        """Re-render the preview chart with the new theme colours."""
        self.pv_chart.refresh_theme()

    def refresh_setup_filter(self):
        self.flt_setup.blockSignals(True)
        try:
            cur = self.flt_setup.currentData()
            self.flt_setup.clear(); self.flt_setup.addItem("All Setups", None)
            for s in get_setup_types(self.conn): self.flt_setup.addItem(s['name'], s['id'])
            if cur is not None:
                idx = self.flt_setup.findData(cur)
                if idx >= 0: self.flt_setup.setCurrentIndex(idx)
        finally:
            self.flt_setup.blockSignals(False)

    def refresh_tag_filter(self):
        self.flt_tag.blockSignals(True)
        try:
            cur = self.flt_tag.currentData()
            self.flt_tag.clear()
            self.flt_tag.addItem("All Tags", None)
            for tag in get_tags(self.conn):
                self.flt_tag.addItem(tag['name'], tag['id'])
            idx = self.flt_tag.findData(cur)
            if idx >= 0:
                self.flt_tag.setCurrentIndex(idx)
        finally:
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
        if grade != 'All Grades':
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

        _p = _theme.GREEN if _theme.is_dark() else "#008200"
        _n = _theme.RED   if _theme.is_dark() else "#c80000"
        _z = _theme.TEXT_DIM if _theme.is_dark() else "#666"

        self.kpi_trades.set_value(
            f"{total}  ({len(winners)}W / {len(losers)}L)",
            _theme.TEXT_DIM if _theme.is_dark() else "#333")

        self.kpi_winrate.set_value(
            f"{win_rate:.1f}%", _p if win_rate >= 50 else _n)

        self.kpi_pnl.set_value(
            f"{net_pnl:+.2f}", _p if net_pnl > 0 else _n if net_pnl < 0 else _z)

        self.kpi_expectancy.set_value(
            f"{expectancy:+.2f}", _p if expectancy > 0 else _n if expectancy < 0 else _z)

        pfs = f"{profit_factor:.2f}" if profit_factor != float('inf') else "∞"
        self.kpi_pf.set_value(
            pfs, _p if profit_factor > 1 else _n if profit_factor < 1 else _z)

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
        status_idx = pnl_idx + 3
        self._pnl_col_idx = pnl_idx  # stored for use in _show_event_preview

        # Build rows: current page trades + date-filtered events (interleaved by date).
        # Events have no instrument symbol, so suppress them when a symbol search is active.
        rows_data = []
        for t in page_trades:
            rows_data.append((t['entry_date'] or '', 'trade', t))
        if not filters.get('symbol_search'):
            for ev in events:
                ev_date = (ev['event_date'] or '')[:10]
                if period_from is not None and ev_date < str(period_from): continue
                if period_to is not None and ev_date > str(period_to): continue
                rows_data.append((ev_date, 'event', ev))
        rows_data.sort(key=lambda x: x[0], reverse=True)

        self.table.setUpdatesEnabled(False)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows_data))

        if _theme.is_dark():
            dep_bg = QColor(_theme.GREEN_BG)
            wd_bg = QColor(_theme.RED_BG)
            profit_fg = QColor(_theme.GREEN)
            loss_fg = QColor(_theme.RED)
            neutral_fg = QColor(_theme.TEXT_DIM)
            long_fg = QColor(_theme.ACCENT)
            short_fg = QColor("#c8804a")
            status_colors = {
                'win':  (QColor(_theme.BG_DARK), QColor(_theme.GREEN)),
                'loss': (QColor(_theme.BG_DARK), QColor(_theme.RED)),
                'open': (QColor(_theme.TEXT_BRIGHT), QColor(_theme.ACCENT)),
                'be':   (QColor(_theme.TEXT_DIM), QColor(_theme.BG_HOVER)),
            }
        else:
            dep_bg = QColor(230, 245, 230)
            wd_bg = QColor(250, 235, 235)
            profit_fg = QColor(0, 130, 0)
            loss_fg = QColor(200, 0, 0)
            neutral_fg = QColor(100, 100, 100)
            long_fg = QColor(0, 100, 180)
            short_fg = QColor(180, 80, 0)
            status_colors = {
                'win':  (QColor(255, 255, 255), QColor(22, 163, 106)),
                'loss': (QColor(255, 255, 255), QColor(220, 38, 38)),
                'open': (QColor(255, 255, 255), QColor(59, 130, 246)),
                'be':   (QColor(255, 255, 255), QColor(107, 114, 128)),
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
                if dir_val == 'long':
                    dir_text = 'Long'
                elif dir_val == 'short':
                    dir_text = 'Short'
                else:
                    dir_text = dir_val.capitalize()
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
                ev = data; amt = ev['amount'] or 0
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
