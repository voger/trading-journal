"""
Trading Journal — SetupDialog.
"""
import os
from datetime import datetime

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QFormLayout, QDialogButtonBox,
    QLineEdit, QDoubleSpinBox,
    QLabel, QPushButton, QFileDialog, QMessageBox,
    QPlainTextEdit, QGroupBox,
    QListWidget, QListWidgetItem, QMenu,
)
from PyQt6.QtCore import Qt

from database import get_setup_rules, get_setup_charts
from dialogs_widgets import ImageViewer, SETUP_CHARTS_DIR


# ═══════════════════════════════════════════════════════════════
# SETUP DIALOG (unchanged)
# ═══════════════════════════════════════════════════════════════

class SetupDialog(QDialog):
    """Dialog for creating/editing a setup with rules."""
    def __init__(self, parent, conn, setup=None):
        super().__init__(parent)
        self.conn = conn; self.setup = setup
        self.setWindowTitle("Edit Setup" if setup else "New Setup")
        self.setMinimumSize(600, 550)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.desc_edit = QPlainTextEdit(); self.desc_edit.setMaximumHeight(80)
        self.tf_edit = QLineEdit(); self.tf_edit.setPlaceholderText("e.g. Weekly, Daily, H4")
        self.risk_spin = QDoubleSpinBox()
        self.risk_spin.setRange(0, 10); self.risk_spin.setDecimals(2); self.risk_spin.setSuffix("%")
        self.rr_spin = QDoubleSpinBox()
        self.rr_spin.setRange(0, 20); self.rr_spin.setDecimals(1); self.rr_spin.setPrefix("1:")
        form.addRow("Name:", self.name_edit)
        form.addRow("Description:", self.desc_edit)
        form.addRow("Timeframes:", self.tf_edit)
        form.addRow("Default Risk:", self.risk_spin)
        form.addRow("Target R:R:", self.rr_spin)
        layout.addLayout(form)

        eg = QGroupBox("Entry Rules (checklist items)")
        el = QVBoxLayout(eg)
        self.entry_list = QListWidget(); el.addWidget(self.entry_list)
        eb = QHBoxLayout()
        self.entry_input = QLineEdit(); self.entry_input.setPlaceholderText("Add entry rule...")
        btn_add_e = QPushButton("+"); btn_add_e.setMaximumWidth(40)
        btn_add_e.clicked.connect(lambda: self._add_rule('entry'))
        self.entry_input.returnPressed.connect(lambda: self._add_rule('entry'))
        btn_del_e = QPushButton("-"); btn_del_e.setMaximumWidth(40)
        btn_del_e.clicked.connect(lambda: self._del_rule('entry'))
        eb.addWidget(self.entry_input); eb.addWidget(btn_add_e); eb.addWidget(btn_del_e)
        el.addLayout(eb); layout.addWidget(eg)

        xg = QGroupBox("Exit Rules (checklist items)")
        xl = QVBoxLayout(xg)
        self.exit_list = QListWidget(); xl.addWidget(self.exit_list)
        xb = QHBoxLayout()
        self.exit_input = QLineEdit(); self.exit_input.setPlaceholderText("Add exit rule...")
        btn_add_x = QPushButton("+"); btn_add_x.setMaximumWidth(40)
        btn_add_x.clicked.connect(lambda: self._add_rule('exit'))
        self.exit_input.returnPressed.connect(lambda: self._add_rule('exit'))
        btn_del_x = QPushButton("-"); btn_del_x.setMaximumWidth(40)
        btn_del_x.clicked.connect(lambda: self._del_rule('exit'))
        xb.addWidget(self.exit_input); xb.addWidget(btn_add_x); xb.addWidget(btn_del_x)
        xl.addLayout(xb); layout.addWidget(xg)

        cg = QGroupBox("Example Charts")
        cl = QVBoxLayout(cg)
        self.chart_list = QListWidget(); self.chart_list.setMaximumHeight(80)
        self.chart_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.chart_list.customContextMenuRequested.connect(self._chart_ctx)
        self.chart_list.doubleClicked.connect(self._chart_view)
        cl.addWidget(self.chart_list)
        cb_row = QHBoxLayout()
        b = QPushButton("Attach Chart..."); b.clicked.connect(self._chart_attach); cb_row.addWidget(b)
        b = QPushButton("Paste Clipboard"); b.clicked.connect(self._chart_paste); cb_row.addWidget(b)
        cl.addLayout(cb_row); layout.addWidget(cg)
        self.pending_charts = []; self.delete_chart_ids = []

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        if setup: self._populate(setup)

    def _populate(self, s):
        self.name_edit.setText(s['name'])
        self.desc_edit.setPlainText(s['description'] or '')
        self.tf_edit.setText(s['timeframes'] or '')
        self.risk_spin.setValue(s['default_risk_percent'] or 0)
        self.rr_spin.setValue(s['target_rr_ratio'] or 0)
        for r in get_setup_rules(self.conn, s['id'], 'entry'):
            item = QListWidgetItem(r['rule_text'])
            item.setData(Qt.ItemDataRole.UserRole, r['id'])
            self.entry_list.addItem(item)
        for r in get_setup_rules(self.conn, s['id'], 'exit'):
            item = QListWidgetItem(r['rule_text'])
            item.setData(Qt.ItemDataRole.UserRole, r['id'])
            self.exit_list.addItem(item)
        for c in get_setup_charts(self.conn, s['id']):
            item = QListWidgetItem(f"[Saved] {c['caption'] or os.path.basename(c['file_path'])}")
            item.setData(Qt.ItemDataRole.UserRole, ('existing', c['id'], c['file_path']))
            self.chart_list.addItem(item)

    def _chart_attach(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Attach Charts", "",
            "Images (*.png *.jpg *.jpeg *.gif *.bmp);;All (*.*)")
        for f in files:
            self.pending_charts.append(f)
            item = QListWidgetItem(os.path.basename(f))
            item.setData(Qt.ItemDataRole.UserRole, ('pending', f))
            self.chart_list.addItem(item)

    def _chart_paste(self):
        from PyQt6.QtWidgets import QApplication
        img = QApplication.clipboard().image()
        if img.isNull():
            QMessageBox.information(self, "Clipboard", "No image in clipboard."); return
        fname = f"setup_clip_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        tp = os.path.join(SETUP_CHARTS_DIR, fname)
        if not img.save(tp, "PNG"):
            QMessageBox.warning(self, "Clipboard", f"Could not save clipboard image to:\n{tp}")
            return
        self.pending_charts.append(tp)
        item = QListWidgetItem(f"[Pasted] {fname}")
        item.setData(Qt.ItemDataRole.UserRole, ('pending', tp))
        self.chart_list.addItem(item)

    def _chart_ctx(self, pos):
        item = self.chart_list.itemAt(pos)
        if not item: return
        menu = QMenu()
        rm = menu.addAction("Remove")
        vw = menu.addAction("View")
        action = menu.exec(self.chart_list.mapToGlobal(pos))
        if action == rm:
            row = self.chart_list.row(item)
            data = item.data(Qt.ItemDataRole.UserRole)
            self.chart_list.takeItem(row)
            if data and data[0] == 'existing':
                self.delete_chart_ids.append(data[1])
            elif data and data[0] == 'pending':
                try:
                    self.pending_charts.remove(data[1])
                except ValueError:
                    pass
        elif action == vw:
            self._chart_view()

    def _chart_view(self):
        item = self.chart_list.currentItem()
        if not item: return
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data: return
        if data[0] == 'existing':
            path = data[2]
        elif data[0] == 'pending':
            path = data[1]
        else:
            return
        if os.path.exists(path):
            ImageViewer.open(path)

    def get_pending_charts(self): return self.pending_charts
    def get_delete_chart_ids(self): return self.delete_chart_ids

    def _add_rule(self, rtype):
        inp = self.entry_input if rtype == 'entry' else self.exit_input
        lst = self.entry_list if rtype == 'entry' else self.exit_list
        text = inp.text().strip()
        if text:
            lst.addItem(QListWidgetItem(text)); inp.clear()

    def _del_rule(self, rtype):
        lst = self.entry_list if rtype == 'entry' else self.exit_list
        row = lst.currentRow()
        if row >= 0: lst.takeItem(row)

    def get_values(self):
        return dict(
            name=self.name_edit.text().strip(),
            description=self.desc_edit.toPlainText().strip() or None,
            timeframes=self.tf_edit.text().strip() or None,
            default_risk_percent=self.risk_spin.value() or None,
            target_rr_ratio=self.rr_spin.value() or None,
        )

    def get_entry_rules(self):
        return [self.entry_list.item(i).text() for i in range(self.entry_list.count())]

    def get_exit_rules(self):
        return [self.exit_list.item(i).text() for i in range(self.exit_list.count())]
