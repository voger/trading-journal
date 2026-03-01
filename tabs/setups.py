"""Setups tab — setup types, rules, example charts."""
import os, shutil
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QTextEdit, QScrollArea,
    QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPixmap, QIcon

from tabs import BaseTab
from dialogs import SetupDialog, ImageViewer
from database import (
    get_setup_types, get_setup_type, create_setup_type, update_setup_type,
    delete_setup_type, get_setup_rules, add_setup_rule, delete_setup_rule,
    get_setup_charts, add_setup_chart, delete_setup_chart, get_setup_stats,
)

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETUP_CHARTS_DIR = os.path.join(PROJECT_DIR, 'setup_charts')
os.makedirs(SETUP_CHARTS_DIR, exist_ok=True)


class SetupsTab(BaseTab):
    def __init__(self, conn, get_aid_fn):
        super().__init__(conn, get_aid_fn)
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        left = QVBoxLayout()
        self.setup_list = QListWidget(); self.setup_list.currentRowChanged.connect(self._on_selected)
        left.addWidget(QLabel("Setups:")); left.addWidget(self.setup_list)
        sb = QHBoxLayout()
        b = QPushButton("+ New"); b.clicked.connect(self._on_new); sb.addWidget(b)
        b = QPushButton("Edit"); b.clicked.connect(self._on_edit); sb.addWidget(b)
        b = QPushButton("Delete"); b.clicked.connect(self._on_delete); sb.addWidget(b)
        left.addLayout(sb)
        layout.addLayout(left, 1)
        right = QVBoxLayout()
        self.detail = QTextEdit(); self.detail.setReadOnly(True)
        right.addWidget(self.detail)
        right.addWidget(QLabel("Example Charts:"))
        self.thumb_area = QWidget()
        self.thumb_layout = QHBoxLayout(self.thumb_area)
        self.thumb_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        thumb_scroll = QScrollArea(); thumb_scroll.setWidgetResizable(True)
        thumb_scroll.setWidget(self.thumb_area); thumb_scroll.setMaximumHeight(150)
        right.addWidget(thumb_scroll)
        layout.addLayout(right, 2)

    def _clear_thumbs(self):
        while self.thumb_layout.count():
            w = self.thumb_layout.takeAt(0).widget()
            if w: w.deleteLater()

    def refresh(self):
        self.setup_list.clear()
        for s in get_setup_types(self.conn, active_only=False):
            item = QListWidgetItem(s['name']); item.setData(Qt.ItemDataRole.UserRole, s['id'])
            if not s['is_active']: item.setForeground(QColor(150,150,150))
            self.setup_list.addItem(item)
        self.detail.clear(); self._clear_thumbs()

    def _on_selected(self, row):
        self._clear_thumbs()
        if row < 0: self.detail.clear(); return
        sid = self.setup_list.item(row).data(Qt.ItemDataRole.UserRole)
        s = get_setup_type(self.conn, sid)
        if not s: return
        rules = get_setup_rules(self.conn, sid)
        entry_rules = [r for r in rules if r['rule_type'] == 'entry']
        exit_rules = [r for r in rules if r['rule_type'] == 'exit']
        stats = get_setup_stats(self.conn, sid, self.aid())

        html = f"<h2>{s['name']}</h2>"
        if s['description']: html += f"<p>{s['description']}</p>"
        html += "<table cellpadding='4' style='font-size:10pt;'>"
        if s['timeframes']: html += f"<tr><td><b>Timeframes:</b></td><td>{s['timeframes']}</td></tr>"
        if s['default_risk_percent']: html += f"<tr><td><b>Default Risk:</b></td><td>{s['default_risk_percent']:.1f}%</td></tr>"
        if s['target_rr_ratio']: html += f"<tr><td><b>Target R:R:</b></td><td>1:{s['target_rr_ratio']:.1f}</td></tr>"
        html += "</table>"
        if entry_rules:
            html += "<h3>Entry Rules</h3><ul>"
            for r in entry_rules: html += f"<li>{r['rule_text']}</li>"
            html += "</ul>"
        if exit_rules:
            html += "<h3>Exit Rules</h3><ul>"
            for r in exit_rules: html += f"<li>{r['rule_text']}</li>"
            html += "</ul>"
        if stats:
            wr_c = '#008200' if stats['win_rate'] > 50 else '#c80000'
            pf = stats['profit_factor']; pfs = f"{pf:.2f}" if pf != float('inf') else "Inf"
            html += f"""<h3>Performance</h3>
            <table cellpadding='4' style='font-size:10pt;'>
            <tr><td><b>Trades:</b></td><td>{stats['total']}</td>
                <td><b>Win Rate:</b></td><td style='color:{wr_c}'>{stats['win_rate']:.1f}%</td></tr>
            <tr><td><b>Net P&L:</b></td><td>{stats['net_pnl']:+.2f}</td>
                <td><b>PF:</b></td><td>{pfs}</td></tr>
            <tr><td><b>Avg Win:</b></td><td>{stats['avg_win']:.2f}</td>
                <td><b>Avg Loss:</b></td><td>{stats['avg_loss']:.2f}</td></tr></table>"""
        else:
            html += "<p><i>No trades recorded with this setup yet.</i></p>"
        self.detail.setHtml(html)
        for c in get_setup_charts(self.conn, sid):
            if os.path.exists(c['file_path']):
                thumb = QPushButton(); thumb.setCursor(Qt.CursorShape.PointingHandCursor)
                thumb.setFixedSize(144, 104)
                pix = QPixmap(c['file_path']).scaled(140, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                thumb.setIcon(QIcon(pix)); thumb.setIconSize(pix.size())
                thumb.setToolTip(c['caption'] or os.path.basename(c['file_path']))
                thumb.setStyleSheet("border:1px solid #ccc; padding:2px; background:white;")
                path = str(c['file_path']); caption = str(c['caption'] or '')
                thumb.clicked.connect(lambda checked=False, p=path, cap=caption: ImageViewer.open(p))
                self.thumb_layout.addWidget(thumb)

    # ── CRUD ──

    def _on_new(self):
        dlg = SetupDialog(self, self.conn)
        if dlg.exec():
            v = dlg.get_values()
            if not v['name']: QMessageBox.warning(self, "Error", "Name required."); return
            try:
                sid = create_setup_type(self.conn, v.pop('name'), v.pop('description', None))
                update_setup_type(self.conn, sid, **v)
                for i, rule in enumerate(dlg.get_entry_rules()):
                    add_setup_rule(self.conn, sid, 'entry', rule, i)
                for i, rule in enumerate(dlg.get_exit_rules()):
                    add_setup_rule(self.conn, sid, 'exit', rule, i)
                self._save_charts(sid, dlg)
                self.data_changed.emit()
            except Exception as e: QMessageBox.critical(self, "Error", str(e))

    def _on_edit(self):
        row = self.setup_list.currentRow()
        if row < 0: return
        sid = self.setup_list.item(row).data(Qt.ItemDataRole.UserRole)
        s = get_setup_type(self.conn, sid)
        if not s: return
        dlg = SetupDialog(self, self.conn, setup=s)
        if dlg.exec():
            v = dlg.get_values()
            try:
                update_setup_type(self.conn, sid, **v)
                for r in get_setup_rules(self.conn, sid): delete_setup_rule(self.conn, r['id'])
                for i, rule in enumerate(dlg.get_entry_rules()): add_setup_rule(self.conn, sid, 'entry', rule, i)
                for i, rule in enumerate(dlg.get_exit_rules()): add_setup_rule(self.conn, sid, 'exit', rule, i)
                for cid in dlg.get_delete_chart_ids():
                    fp = delete_setup_chart(self.conn, cid)
                    if fp and os.path.exists(fp):
                        try: os.remove(fp)
                        except OSError: pass
                self._save_charts(sid, dlg)
                self.data_changed.emit()
            except Exception as e: QMessageBox.critical(self, "Error", str(e))

    def _on_delete(self):
        row = self.setup_list.currentRow()
        if row < 0: return
        sid = self.setup_list.item(row).data(Qt.ItemDataRole.UserRole)
        name = self.setup_list.item(row).text()
        if QMessageBox.question(self, "Delete Setup", f"Delete '{name}'?\nTrades using it will be unlinked.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            delete_setup_type(self.conn, sid); self.data_changed.emit()

    def _save_charts(self, setup_id, dlg):
        for i, src_path in enumerate(dlg.get_pending_charts()):
            ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            ext = os.path.splitext(src_path)[1] or '.png'
            dest = os.path.join(SETUP_CHARTS_DIR, f"setup_{setup_id}_{ts}{ext}")
            try:
                shutil.copy2(src_path, dest)
            except OSError as e:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Chart Save Error",
                    f"Could not save chart '{os.path.basename(src_path)}':\n{e}")
                continue
            add_setup_chart(self.conn, setup_id, dest, caption=os.path.basename(src_path), sort_order=i)
