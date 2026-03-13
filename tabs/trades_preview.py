"""Trades tab — preview panel mixin."""
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel,
    QFrame, QSplitter,
)
from PyQt6.QtCore import Qt

import theme as _theme
from database import (
    get_trade, get_account, effective_pnl,
    get_trade_tags, get_trade_rule_checks,
)


def _esc(text):
    """Escape HTML special characters for safe display."""
    if not text: return ''
    return (text.replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('\n', '<br>'))


class TradesPreviewMixin:
    """Mixin providing the read-only trade preview panel for TradesTab."""

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

        if _theme.is_dark():
            _bg_long  = _theme.GREEN;  _bg_short = _theme.RED
            _bg_win   = _theme.GREEN;  _bg_loss  = _theme.RED
            _bg_open  = _theme.ACCENT; _bg_be    = _theme.BG_HOVER
            _badge_fg = _theme.BG_DARK
        else:
            _bg_long  = '#16a34a';  _bg_short = '#dc2626'
            _bg_win   = '#16a34a';  _bg_loss  = '#dc2626'
            _bg_open  = '#3b82f6';  _bg_be    = '#6b7280'
            _badge_fg = '#fff'

        _bs = f"color:{_badge_fg};padding:2px 8px;border-radius:3px;font-weight:bold;"
        if direction == 'LONG':
            dir_html = f'<span style="{_bs}background:{_bg_long};">▲ LONG</span>'
        else:
            dir_html = f'<span style="{_bs}background:{_bg_short};">▼ SHORT</span>'

        if status == 'open':
            st_html = f'<span style="{_bs}background:{_bg_open};">OPEN</span>'
        elif epnl > 0:
            st_html = f'<span style="{_bs}background:{_bg_win};">WIN</span>'
        elif epnl < 0:
            st_html = f'<span style="{_bs}background:{_bg_loss};">LOSS</span>'
        else:
            st_html = f'<span style="{_bs}background:{_bg_be};">B/E</span>'

        self.pv_badges.setTextFormat(Qt.TextFormat.RichText)
        self.pv_badges.setText(f"{dir_html}&nbsp;&nbsp;{st_html}")

        # P&L Hero (effective P&L: includes swap + commission)
        self.pv_pnl_hero.setText(
            f"<span style='color:{_theme.pnl_color(epnl)}'>{epnl:+.2f}</span>"
        )

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
                _rr_col = _theme.ACCENT if _theme.is_dark() else '#3b82f6'
                lines.append(f"<b>R:R:</b> <span style='color:{_rr_col}'>1:{rr:.1f}</span>")
            if exit_p and exit_p > 0:
                actual = (exit_p - entry) if direction == 'LONG' else (entry - exit_p)
                r_mult = actual / risk_dist if risk_dist > 0 else 0
                rc = _theme.pos_color() if r_mult > 0 else _theme.neg_color() if r_mult < 0 else _theme.neu_color()
                lines.append(f"<b>R Multiple:</b> <span style='color:{rc}'>{r_mult:+.2f}R</span>")

        if risk_pct: lines.append(f"<b>Risk:</b> {risk_pct:.2f}%")

        # Holding duration
        if t['entry_date'] and t['exit_date']:
            try:
                ed = datetime.strptime(t['entry_date'][:10], '%Y-%m-%d')
                xd = datetime.strptime(t['exit_date'][:10], '%Y-%m-%d')
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
        cached = t['chart_data'] if 'chart_data' in t else None
        if cached:
            self.pv_chart.load_cached_data(cached)
        else:
            self.pv_chart._show_placeholder()

        self.pv_edit_btn.setVisible(True)
