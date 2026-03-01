"""Summary Stats tab — formula editor dialog and widget."""
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QWidget, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QMessageBox, QPlainTextEdit,
    QFormLayout, QDialog, QDialogButtonBox, QLineEdit,
)
from PyQt6.QtCore import Qt

from database import get_all_formulas, update_formula, reset_formulas_to_defaults


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
