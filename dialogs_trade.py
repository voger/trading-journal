"""
Trading Journal — TradeDialog.

v2.0 — QSplitter layout for TradeDialog, live R:R metrics,
        executions moved to dedicated dialog.
"""
import os
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QDialog, QFormLayout, QDialogButtonBox,
    QComboBox, QLineEdit, QDoubleSpinBox, QSpinBox,
    QLabel, QPushButton, QFileDialog, QMessageBox,
    QDateTimeEdit, QPlainTextEdit, QCheckBox, QGroupBox,
    QScrollArea,
    QSplitter, QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, QDateTime
from PyQt6.QtGui import QPixmap, QIcon

from database import (
    get_accounts, get_setup_types, get_setup_rules,
    get_trade_charts, get_trade_rule_checks,
    get_or_create_instrument, get_account,
    get_trade_tags,
)
from dialogs_widgets import ImageViewer, MetricCard, StatusBadge, SCREENSHOTS_DIR


# ═══════════════════════════════════════════════════════════════
# TRADE DIALOG — QSplitter layout with live metrics
# ═══════════════════════════════════════════════════════════════

class TradeDialog(QDialog):
    """Trade entry/edit dialog with split-pane layout.

    Left panel:  all input fields + notes + screenshots + rule checklist
    Right panel: live calculated metrics + executions summary + price chart
    """

    def __init__(self, parent, conn, trade=None, default_account_id=None):
        super().__init__(parent)
        self.conn = conn
        self.trade = trade
        self.pending_screenshots = []
        self.delete_chart_ids = []
        self.setWindowTitle("Edit Trade" if trade else "New Trade")
        self.setMinimumSize(1050, 700)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        # ── HEADER BAR ──
        self._build_header(outer)

        # ── SPLITTER ──
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(self.splitter, 1)

        self._build_left_panel()
        self._build_right_panel()
        self.splitter.setSizes([600, 420])

        # ── FOOTER ──
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        outer.addWidget(btns)

        # ── Connect live calculation ──
        self._connect_live_calc()

        # ── Populate ──
        if trade:
            self._populate(trade)
        elif default_account_id:
            idx = self.account_combo.findData(default_account_id)
            if idx >= 0:
                self.account_combo.setCurrentIndex(idx)

        self._recalc_metrics()

    # ──────────────────────────────────────────
    # HEADER
    # ──────────────────────────────────────────

    def _build_header(self, parent_layout):
        hdr = QHBoxLayout()
        hdr.setSpacing(12)

        self.hdr_instrument = QLabel("NEW TRADE")
        self.hdr_instrument.setStyleSheet(
            "font-size: 18px; font-weight: bold;"
        )
        hdr.addWidget(self.hdr_instrument)

        self.hdr_direction = QLabel("")
        self.hdr_direction.setStyleSheet(
            "font-size: 14px; font-weight: bold; padding: 2px 8px; border-radius: 4px;"
        )
        hdr.addWidget(self.hdr_direction)
        hdr.addStretch()
        self.hdr_status = StatusBadge()
        hdr.addWidget(self.hdr_status)
        parent_layout.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        parent_layout.addWidget(sep)

    def _update_header(self):
        sym = self.instrument_edit.text().strip().upper() or "NEW TRADE"
        self.hdr_instrument.setText(sym)
        direction = self.dir_combo.currentText().upper()
        if direction == 'LONG':
            self.hdr_direction.setText("▲ LONG")
            self.hdr_direction.setStyleSheet(
                "color: #ffffff; font-size: 14px; font-weight: bold; "
                "padding: 2px 8px; border-radius: 4px; background-color: #16a34a;"
            )
        else:
            self.hdr_direction.setText("▼ SHORT")
            self.hdr_direction.setStyleSheet(
                "color: #ffffff; font-size: 14px; font-weight: bold; "
                "padding: 2px 8px; border-radius: 4px; background-color: #dc2626;"
            )
        is_open = self.exit_dt.dateTime() == self.exit_dt.minimumDateTime()
        if is_open:
            self.hdr_status.set_status('open')
        else:
            pnl = self.pnl_spin.value()
            if pnl > 0:
                self.hdr_status.set_status('win')
            elif pnl < 0:
                self.hdr_status.set_status('loss')
            else:
                self.hdr_status.set_status('be')

    # ──────────────────────────────────────────
    # LEFT PANEL
    # ──────────────────────────────────────────

    def _build_left_panel(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        left = QVBoxLayout(container)
        left.setSpacing(10)
        left.setContentsMargins(4, 4, 8, 4)
        scroll.setWidget(container)
        self.splitter.addWidget(scroll)

        # ── Trade identity — compact 3-column grid ──
        id_group = QGroupBox("Trade Details")
        id_lay = QHBoxLayout(id_group)
        id_lay.setSpacing(16)

        # Column 1: Identity
        col1 = QFormLayout()
        col1.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        self.account_combo = QComboBox(); self.account_combo.setMinimumWidth(180)
        for a in get_accounts(self.conn):
            self.account_combo.addItem(f"{a['name']} ({a['currency']})", a['id'])
        col1.addRow("Account:", self.account_combo)
        self.instrument_edit = QLineEdit()
        self.instrument_edit.setPlaceholderText("EURUSD, AAPL...")
        self.instrument_edit.setMaximumWidth(150)
        col1.addRow("Instrument:", self.instrument_edit)
        self.itype_combo = QComboBox()
        self.itype_combo.addItems(['forex', 'stock', 'etf', 'commodity', 'index', 'crypto', 'other'])
        col1.addRow("Type:", self.itype_combo)
        self.dir_combo = QComboBox(); self.dir_combo.addItems(['long', 'short'])
        col1.addRow("Direction:", self.dir_combo)
        self.setup_combo = QComboBox(); self.setup_combo.addItem("(none)", None)
        for s in get_setup_types(self.conn):
            self.setup_combo.addItem(s['name'], s['id'])
        col1.addRow("Setup:", self.setup_combo)
        id_lay.addLayout(col1)

        # Column 2: Entry + SL/TP
        col2 = QFormLayout()
        col2.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        self.entry_dt = QDateTimeEdit(); self.entry_dt.setCalendarPopup(True)
        self.entry_dt.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.entry_dt.setDateTime(QDateTime.currentDateTime())
        col2.addRow("Entry Date:", self.entry_dt)
        self.entry_price = QDoubleSpinBox()
        self.entry_price.setRange(0, 999999); self.entry_price.setDecimals(5)
        col2.addRow("Entry Price:", self.entry_price)
        self.size_spin = QDoubleSpinBox()
        self.size_spin.setRange(0.001, 9999999); self.size_spin.setDecimals(3)
        self.size_spin.setSingleStep(0.01)
        col2.addRow("Size:", self.size_spin)
        self.sl_spin = QDoubleSpinBox()
        self.sl_spin.setRange(0, 999999); self.sl_spin.setDecimals(5)
        self.sl_spin.setSpecialValueText("Not set")
        col2.addRow("Stop Loss:", self.sl_spin)
        self.tp_spin = QDoubleSpinBox()
        self.tp_spin.setRange(0, 999999); self.tp_spin.setDecimals(5)
        self.tp_spin.setSpecialValueText("Not set")
        col2.addRow("Take Profit:", self.tp_spin)
        id_lay.addLayout(col2)

        # Column 3: Exit + Results
        col3 = QFormLayout()
        col3.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        self.exit_dt = QDateTimeEdit(); self.exit_dt.setCalendarPopup(True)
        self.exit_dt.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.exit_dt.setSpecialValueText("Open")
        col3.addRow("Exit Date:", self.exit_dt)
        self.exit_price = QDoubleSpinBox()
        self.exit_price.setRange(0, 999999); self.exit_price.setDecimals(5)
        self.exit_price.setSpecialValueText("Not set")
        col3.addRow("Exit Price:", self.exit_price)
        self.exit_reason = QComboBox()
        self.exit_reason.addItems([
            '', 'target_hit', 'trailing_stop', 'manual', 'stop_loss', 'time_exit', 'stop_out'
        ])
        col3.addRow("Exit Reason:", self.exit_reason)
        self.pnl_spin = QDoubleSpinBox()
        self.pnl_spin.setRange(-999999, 999999); self.pnl_spin.setDecimals(2)
        col3.addRow("P&&L:", self.pnl_spin)
        self.risk_pct = QDoubleSpinBox()
        self.risk_pct.setRange(0, 100); self.risk_pct.setDecimals(2)
        self.risk_pct.setSpecialValueText("Not set")
        col3.addRow("Risk %:", self.risk_pct)
        id_lay.addLayout(col3)
        left.addWidget(id_group)

        # ── Tags ──
        tags_row = QHBoxLayout()
        tags_row.addWidget(QLabel("Tags:"))
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("tag1, tag2, tag3  (comma-separated)")
        tags_row.addWidget(self.tags_edit)
        left.addLayout(tags_row)

        # ── Notes side-by-side ──
        notes_row = QHBoxLayout()
        left.addLayout(notes_row, 1)  # stretch so notes grow

        pre_group = QGroupBox("Pre-trade Notes")
        pre_lay = QVBoxLayout(pre_group)
        self.pre_notes = QPlainTextEdit()
        self.pre_notes.setPlaceholderText("Why are you taking this trade? What's the thesis?")
        pre_lay.addWidget(self.pre_notes)
        notes_row.addWidget(pre_group)

        post_group = QGroupBox("Post-trade Notes")
        post_lay = QVBoxLayout(post_group)
        self.post_notes = QPlainTextEdit()
        self.post_notes.setPlaceholderText("Review: What went right/wrong? What would you do differently?")
        post_lay.addWidget(self.post_notes)
        notes_row.addWidget(post_group)

        # ── Screenshots ──
        ss_group = QGroupBox("Screenshots")
        ss_lay = QVBoxLayout(ss_group)
        self.screenshot_area = QWidget()
        self.screenshot_flow = QHBoxLayout(self.screenshot_area)
        self.screenshot_flow.setAlignment(Qt.AlignmentFlag.AlignLeft)
        ss_scroll = QScrollArea(); ss_scroll.setWidgetResizable(True)
        ss_scroll.setWidget(self.screenshot_area); ss_scroll.setMaximumHeight(130)
        ss_scroll.setFrameShape(QFrame.Shape.NoFrame)
        ss_lay.addWidget(ss_scroll)
        ss_btns = QHBoxLayout()
        btn_attach = QPushButton("Attach File...")
        btn_attach.clicked.connect(self._attach_screenshot)
        btn_paste = QPushButton("Paste from Clipboard")
        btn_paste.clicked.connect(self._paste_screenshot)
        ss_btns.addWidget(btn_attach); ss_btns.addWidget(btn_paste); ss_btns.addStretch()
        ss_lay.addLayout(ss_btns)
        left.addWidget(ss_group)
        self._screenshot_paths = []

        # ── Rule checklist ──
        self.rules_group = QGroupBox("Setup Rule Checklist")
        self.rules_layout = QVBoxLayout(self.rules_group)
        self.rule_checkboxes = {}
        left.addWidget(self.rules_group)
        self.rules_group.setVisible(False)
        self.setup_combo.currentIndexChanged.connect(self._on_setup_changed)

    # ──────────────────────────────────────────
    # RIGHT PANEL
    # ──────────────────────────────────────────

    def _build_right_panel(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        right = QVBoxLayout(container)
        right.setSpacing(10)
        right.setContentsMargins(8, 4, 4, 4)
        scroll.setWidget(container)
        self.splitter.addWidget(scroll)

        # ── Live Metrics ──
        metrics_group = QGroupBox("Live Metrics")
        mg_lay = QVBoxLayout(metrics_group)
        mg_lay.setSpacing(6)

        row1 = QHBoxLayout()
        self.metric_rr = MetricCard("R:R RATIO", "—")
        self.metric_r = MetricCard("R MULTIPLE", "—")
        row1.addWidget(self.metric_rr)
        row1.addWidget(self.metric_r)
        mg_lay.addLayout(row1)

        row2 = QHBoxLayout()
        self.metric_risk = MetricCard("RISK %", "—")
        self.metric_pnl = MetricCard("P&L", "—")
        row2.addWidget(self.metric_risk)
        row2.addWidget(self.metric_pnl)
        mg_lay.addLayout(row2)

        cg_row = QHBoxLayout()
        cg_row.addWidget(QLabel("Confidence:"))
        self.confidence = QSpinBox(); self.confidence.setRange(0, 5)
        self.confidence.setSpecialValueText("Not rated")
        cg_row.addWidget(self.confidence)
        cg_row.addWidget(QLabel("Grade:"))
        self.exec_grade = QComboBox()
        self.exec_grade.addItems(['', 'A', 'B', 'C', 'D', 'F'])
        cg_row.addWidget(self.exec_grade)
        mg_lay.addLayout(cg_row)
        right.addWidget(metrics_group)

        # ── Executions summary bar ──
        self.exec_bar = QGroupBox("Executions")
        exec_bar_lay = QHBoxLayout(self.exec_bar)
        exec_bar_lay.setContentsMargins(10, 6, 10, 6)
        self.exec_summary_label = QLabel("")
        self.exec_summary_label.setStyleSheet("font-weight: bold;")
        exec_bar_lay.addWidget(self.exec_summary_label, 1)
        self.exec_detail_btn = QPushButton("View Details...")
        self.exec_detail_btn.clicked.connect(self._on_view_executions)
        exec_bar_lay.addWidget(self.exec_detail_btn)
        right.addWidget(self.exec_bar)
        self.exec_bar.setVisible(False)

        # ── Price chart ──
        self.chart_group = QGroupBox("Price Chart")
        chart_lay = QVBoxLayout(self.chart_group)
        asset_type = 'forex'
        if self.trade:
            for a in get_accounts(self.conn):
                if a['id'] == self.trade['account_id']:
                    asset_type = a['asset_type'] or 'forex'; break
        from chart_widget import TradeChartWidget
        self.chart_widget = TradeChartWidget(self, conn=self.conn, trade=None, asset_type=asset_type)
        chart_lay.addWidget(self.chart_widget)
        right.addWidget(self.chart_group, 1)

    # ──────────────────────────────────────────
    # LIVE METRICS
    # ──────────────────────────────────────────

    def _connect_live_calc(self):
        self.entry_price.valueChanged.connect(self._recalc_metrics)
        self.sl_spin.valueChanged.connect(self._recalc_metrics)
        self.tp_spin.valueChanged.connect(self._recalc_metrics)
        self.exit_price.valueChanged.connect(self._recalc_metrics)
        self.pnl_spin.valueChanged.connect(self._recalc_metrics)
        self.risk_pct.valueChanged.connect(self._recalc_metrics)
        self.size_spin.valueChanged.connect(self._recalc_metrics)
        self.dir_combo.currentIndexChanged.connect(self._recalc_metrics)
        self.dir_combo.currentIndexChanged.connect(self._update_header)
        self.instrument_edit.textChanged.connect(self._update_header)
        self.exit_dt.dateTimeChanged.connect(self._update_header)
        self.account_combo.currentIndexChanged.connect(self._recalc_metrics)

    def _get_account_balance(self):
        """Get initial balance for the currently selected account."""
        aid = self.account_combo.currentData()
        if aid is None:
            return 0
        acct = get_account(self.conn, aid)
        return acct['initial_balance'] if acct else 0

    def _get_account_currency(self):
        """Get currency symbol for the currently selected account."""
        aid = self.account_combo.currentData()
        if aid is None:
            return ''
        acct = get_account(self.conn, aid)
        return acct['currency'] if acct else ''

    def _calc_r_multiple(self):
        """Compute R-multiple from entry / initial SL / exit prices.

        Only valid when the stored SL is the *initial* stop loss (fixed stops).
        Returns float or None if any required field is missing/zero.
        """
        entry = self.entry_price.value()
        sl = self.sl_spin.value()
        exit_p = self.exit_price.value()
        if entry <= 0 or sl <= 0 or exit_p <= 0:
            return None
        risk = abs(entry - sl)
        if risk < 1e-10:
            return None
        is_long = self.dir_combo.currentText() == 'long'
        actual = (exit_p - entry) if is_long else (entry - exit_p)
        return actual / risk

    def _calc_risk_percent(self):
        """Auto-calculate risk % from entry/SL/size/exit/P&L and account balance.

        Method 1 (closed trade): derive from actual P&L and price movement.
        Method 2 (any trade with SL): use SL distance proportional to P&L.
        Returns calculated risk_pct or None if insufficient data.
        """
        entry = self.entry_price.value()
        sl = self.sl_spin.value()
        exit_p = self.exit_price.value()
        pnl = self.pnl_spin.value()
        balance = self._get_account_balance()

        if entry <= 0 or sl <= 0 or balance <= 0:
            return None

        sl_distance = abs(entry - sl)
        if sl_distance < 1e-10:
            return None

        # Method 1: Closed trade with known P&L and exit price
        # risk_amount = |P&L| × (SL_distance / actual_movement)
        if exit_p > 0 and abs(pnl) > 0.001:
            actual_distance = abs(exit_p - entry)
            if actual_distance > 1e-10:
                risk_amount = abs(pnl) * sl_distance / actual_distance
                return risk_amount / balance * 100

        return None

    def _recalc_metrics(self):
        entry = self.entry_price.value()
        sl = self.sl_spin.value()
        tp = self.tp_spin.value()
        exit_p = self.exit_price.value()
        is_long = self.dir_combo.currentText() == 'long'

        # R:R Ratio
        if entry > 0 and sl > 0 and tp > 0 and entry != sl:
            risk = abs(entry - sl)
            reward = abs(tp - entry)
            rr = reward / risk if risk > 0 else 0
            self.metric_rr.set_value(f"1:{rr:.1f}", "#3b82f6")
        else:
            self.metric_rr.set_value("—")

        # R Multiple
        if entry > 0 and sl > 0 and exit_p > 0 and entry != sl:
            risk = abs(entry - sl)
            actual = (exit_p - entry) if is_long else (entry - exit_p)
            r_mult = actual / risk if risk > 0 else 0
            color = "#16a34a" if r_mult > 0 else "#dc2626" if r_mult < 0 else "#6b7280"
            self.metric_r.set_value(f"{r_mult:+.2f}R", color)
        else:
            self.metric_r.set_value("—")

        # Risk % — auto-calculate if form field is empty
        risk_val = self.risk_pct.value()
        auto_risk = self._calc_risk_percent()
        if risk_val > 0:
            self.metric_risk.set_value(f"{risk_val:.2f}%", "#3b82f6")
        elif auto_risk is not None:
            self.metric_risk.set_value(f"~{auto_risk:.2f}%", "#3b82f6")
            # Auto-fill the form field only if user is not actively editing it
            if not self.risk_pct.hasFocus():
                self.risk_pct.blockSignals(True)
                try:
                    self.risk_pct.setValue(round(auto_risk, 2))
                finally:
                    self.risk_pct.blockSignals(False)
        else:
            self.metric_risk.set_value("—")

        # P&L
        pnl = self.pnl_spin.value()
        currency = self._get_account_currency()
        if pnl != 0:
            color = "#16a34a" if pnl > 0 else "#dc2626"
            self.metric_pnl.set_value(f"{currency}{pnl:+.2f}", color)
        else:
            self.metric_pnl.set_value(f"{currency}0.00", "#6b7280")

        self._update_header()

    # ──────────────────────────────────────────
    # EXECUTIONS
    # ──────────────────────────────────────────

    def _populate_executions(self, t):
        from executions_dialog import get_execution_summary
        summary = get_execution_summary(self.conn, t['id'], currency=self._get_account_currency())
        if summary:
            self.exec_summary_label.setText(summary)
            self.exec_bar.setVisible(True)
        else:
            self.exec_bar.setVisible(False)

    def _on_view_executions(self):
        if not self.trade:
            return
        from executions_dialog import ExecutionsDialog
        sym = self.instrument_edit.text().strip().upper()
        dlg = ExecutionsDialog(self, self.conn, self.trade['id'], symbol=sym)
        dlg.exec()

    # ──────────────────────────────────────────
    # SETUP RULES
    # ──────────────────────────────────────────

    def _on_setup_changed(self):
        setup_id = self.setup_combo.currentData()
        for cb in self.rule_checkboxes.values():
            self.rules_layout.removeWidget(cb); cb.deleteLater()
        self.rule_checkboxes.clear()
        if setup_id is None:
            self.rules_group.setVisible(False); return
        rules = get_setup_rules(self.conn, setup_id)
        if not rules:
            self.rules_group.setVisible(False); return
        self.rules_group.setVisible(True)
        current_type = None
        for r in rules:
            if r['rule_type'] != current_type:
                current_type = r['rule_type']
                lbl = QLabel(f"{'Entry' if current_type == 'entry' else 'Exit'} Rules:")
                lbl.setStyleSheet("font-weight:bold; margin-top:6px;")
                self.rules_layout.addWidget(lbl)
                self.rule_checkboxes[f"_label_{current_type}"] = lbl
            cb = QCheckBox(r['rule_text']); cb.setProperty('rule_id', r['id'])
            self.rules_layout.addWidget(cb)
            self.rule_checkboxes[r['id']] = cb
        if self.trade:
            checks = get_trade_rule_checks(self.conn, self.trade['id'])
            for c in checks:
                cb = self.rule_checkboxes.get(c['rule_id'])
                if cb and isinstance(cb, QCheckBox):
                    cb.setChecked(bool(c['was_met']))

    # ──────────────────────────────────────────
    # SCREENSHOTS
    # ──────────────────────────────────────────

    def _add_thumbnail(self, file_path):
        container = QWidget(); container.setFixedSize(110, 110)
        vlay = QVBoxLayout(container); vlay.setContentsMargins(2, 2, 2, 2); vlay.setSpacing(1)
        thumb = QPushButton(); thumb.setFixedSize(104, 80)
        thumb.setCursor(Qt.CursorShape.PointingHandCursor)
        pix = QPixmap(file_path)
        if not pix.isNull():
            scaled = pix.scaled(100, 76, Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
            thumb.setIcon(QIcon(scaled)); thumb.setIconSize(scaled.size())
        else:
            thumb.setText("?")
        thumb.setStyleSheet("border:1px solid #ccc; background:#f0f0f0; padding:1px;")
        path = str(file_path)
        thumb.clicked.connect(lambda checked=False, p=path: self._view_screenshot(p))
        vlay.addWidget(thumb)
        rm = QPushButton("✕"); rm.setFixedSize(20, 20)
        rm.setStyleSheet("color:red; font-size:12px; border:none;")
        rm.setCursor(Qt.CursorShape.PointingHandCursor)
        rm.clicked.connect(lambda checked=False, w=container: self._remove_screenshot(w))
        vlay.addWidget(rm, alignment=Qt.AlignmentFlag.AlignCenter)
        self.screenshot_flow.addWidget(container)
        return container

    def _view_screenshot(self, path):
        if os.path.exists(path):
            ImageViewer.open(path)

    def _attach_screenshot(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Attach Screenshots", "",
            "Images (*.png *.jpg *.jpeg *.gif *.bmp);;All (*.*)")
        for f in files:
            item = ('file', f)
            self.pending_screenshots.append(item)
            self._screenshot_paths.append(('pending', item))
            self._add_thumbnail(f)

    def _paste_screenshot(self):
        clipboard = QApplication.clipboard()
        img = clipboard.image()
        if img.isNull():
            QMessageBox.information(self, "Clipboard", "No image found in clipboard."); return
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        fname = f"clipboard_{ts}.png"
        temp_path = os.path.join(SCREENSHOTS_DIR, fname)
        img.save(temp_path, "PNG")
        item = ('clipboard', temp_path)
        self.pending_screenshots.append(item)
        self._screenshot_paths.append(('pending', item))
        self._add_thumbnail(temp_path)

    def _remove_screenshot(self, widget):
        idx = -1
        for i in range(self.screenshot_flow.count()):
            it = self.screenshot_flow.itemAt(i)
            if it and it.widget() == widget:
                idx = i; break
        if idx < 0: return
        self.screenshot_flow.takeAt(idx); widget.deleteLater()
        if idx < len(self._screenshot_paths):
            src_type, src_val = self._screenshot_paths.pop(idx)
            if src_type == 'existing' and self.trade:
                self.delete_chart_ids.append(src_val)  # src_val is the chart ID
            elif src_type == 'pending':
                try:
                    self.pending_screenshots.remove(src_val)
                except ValueError:
                    pass

    # ──────────────────────────────────────────
    # POPULATE
    # ──────────────────────────────────────────

    def _populate(self, t):
        idx = self.account_combo.findData(t['account_id'])
        if idx >= 0: self.account_combo.setCurrentIndex(idx)
        self.instrument_edit.setText(t['symbol'] or '')
        ii = self.itype_combo.findText(t['instrument_type'] or 'forex')
        if ii >= 0: self.itype_combo.setCurrentIndex(ii)
        self.dir_combo.setCurrentText((t['direction'] or 'long').lower())

        self.setup_combo.blockSignals(True)
        try:
            if t['setup_type_id']:
                si = self.setup_combo.findData(t['setup_type_id'])
                if si >= 0: self.setup_combo.setCurrentIndex(si)
        finally:
            self.setup_combo.blockSignals(False)
        self._on_setup_changed()

        if t['entry_date']:
            self.entry_dt.setDateTime(
                QDateTime.fromString(t['entry_date'][:19], "yyyy-MM-dd HH:mm:ss"))
        self.entry_price.setValue(t['entry_price'] or 0)
        self.size_spin.setValue(t['position_size'] or 0.01)
        self.sl_spin.setValue(t['stop_loss_price'] or 0)
        self.tp_spin.setValue(t['take_profit_price'] or 0)
        if t['exit_date']:
            self.exit_dt.setDateTime(
                QDateTime.fromString(t['exit_date'][:19], "yyyy-MM-dd HH:mm:ss"))
        self.exit_price.setValue(t['exit_price'] or 0)
        if t['exit_reason']:
            ei = self.exit_reason.findText(t['exit_reason'])
            if ei >= 0: self.exit_reason.setCurrentIndex(ei)
        self.pnl_spin.setValue(t['pnl_account_currency'] or 0)
        self.risk_pct.setValue(t['risk_percent'] or 0)
        self.confidence.setValue(t['confidence_rating'] or 0)
        if t['execution_grade']:
            gi = self.exec_grade.findText(t['execution_grade'])
            if gi >= 0: self.exec_grade.setCurrentIndex(gi)
        self.pre_notes.setPlainText(t['pre_trade_notes'] or '')
        self.post_notes.setPlainText(t['post_trade_notes'] or '')

        # Screenshots
        charts = get_trade_charts(self.conn, t['id'])
        for c in charts:
            if os.path.exists(c['file_path']):
                self._screenshot_paths.append(('existing', c['id']))
                self._add_thumbnail(c['file_path'])

        # Chart widget
        chart_data = {
            'id': t['id'],
            'symbol': t['symbol'] or '', 'direction': t['direction'],
            'entry_date': t['entry_date'], 'exit_date': t['exit_date'],
            'entry_price': t['entry_price'], 'exit_price': t['exit_price'],
            'stop_loss_price': t['stop_loss_price'], 'take_profit_price': t['take_profit_price'],
            'pnl_account_currency': t['pnl_account_currency'],
        }
        self.chart_widget.set_trade(chart_data)
        cached = t.get('chart_data')
        self.chart_widget.load_saved_or_cached(cached)

        # Tags
        tags = get_trade_tags(self.conn, t['id'])
        self.tags_edit.setText(', '.join(tag['name'] for tag in tags))

        # Executions
        self._populate_executions(t)
        self._recalc_metrics()

    # ──────────────────────────────────────────
    # PUBLIC API (preserved for callers)
    # ──────────────────────────────────────────

    def get_values(self):
        exit_dt_str = self.exit_dt.dateTime().toString("yyyy-MM-dd HH:mm:ss")
        is_open = self.exit_dt.dateTime() == self.exit_dt.minimumDateTime()
        vals = dict(
            account_id=self.account_combo.currentData(),
            direction=self.dir_combo.currentText(),
            setup_type_id=self.setup_combo.currentData(),
            entry_date=self.entry_dt.dateTime().toString("yyyy-MM-dd HH:mm:ss"),
            entry_price=self.entry_price.value(),
            position_size=self.size_spin.value(),
            stop_loss_price=self.sl_spin.value() or None,
            take_profit_price=self.tp_spin.value() or None,
            exit_date=None if is_open else exit_dt_str,
            exit_price=self.exit_price.value() or None,
            exit_reason=self.exit_reason.currentText() or None,
            pnl_account_currency=self.pnl_spin.value(),
            risk_percent=self.risk_pct.value() or None,
            r_multiple=self._calc_r_multiple(),
            confidence_rating=self.confidence.value() or None,
            execution_grade=self.exec_grade.currentText() or None,
            pre_trade_notes=self.pre_notes.toPlainText().strip() or None,
            post_trade_notes=self.post_notes.toPlainText().strip() or None,
            status='open' if is_open else 'closed',
        )
        sym = self.instrument_edit.text().strip().upper()
        if sym:
            vals['instrument_id'] = get_or_create_instrument(
                self.conn, sym, instrument_type=self.itype_combo.currentText()
            )
        return vals

    def get_tag_names(self):
        """Return list of tag name strings from the tags field (stripped, non-empty)."""
        text = self.tags_edit.text().strip()
        if not text:
            return []
        return [t.strip() for t in text.split(',') if t.strip()]

    def get_rule_checks(self):
        checks = {}
        for key, cb in self.rule_checkboxes.items():
            if isinstance(cb, QCheckBox):
                rid = cb.property('rule_id')
                if rid is not None:
                    checks[rid] = cb.isChecked()
        return checks

    def get_pending_screenshots(self):
        return self.pending_screenshots

    def get_delete_chart_ids(self):
        return self.delete_chart_ids
