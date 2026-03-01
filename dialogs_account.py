"""
Trading Journal — AccountDialog.
"""
from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QDialogButtonBox,
    QComboBox, QLineEdit, QDoubleSpinBox, QMessageBox,
)

from database import get_accounts
from asset_modules import get_module_choices


# ═══════════════════════════════════════════════════════════════
# DIALOGS
# ═══════════════════════════════════════════════════════════════

class AccountDialog(QDialog):
    def __init__(self, parent=None, account=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Account" if account else "New Account")
        self.setMinimumWidth(420)
        layout = QFormLayout(self)
        self.name_edit = QLineEdit()
        self.broker_edit = QLineEdit()
        self.acct_num_edit = QLineEdit()
        self.type_combo = QComboBox(); self.type_combo.addItems(['live', 'demo'])
        self.asset_combo = QComboBox()
        for atype, dname in get_module_choices():
            self.asset_combo.addItem(dname, atype)
        self.currency_edit = QLineEdit(); self.currency_edit.setPlaceholderText("EUR")
        self.balance_spin = QDoubleSpinBox()
        self.balance_spin.setRange(0, 999999999); self.balance_spin.setDecimals(2)
        self.desc_edit = QLineEdit()
        layout.addRow("Name:", self.name_edit)
        layout.addRow("Broker:", self.broker_edit)
        layout.addRow("Account #:", self.acct_num_edit)
        layout.addRow("Type:", self.type_combo)
        layout.addRow("Asset Class:", self.asset_combo)
        layout.addRow("Currency:", self.currency_edit)
        layout.addRow("Initial Balance:", self.balance_spin)
        layout.addRow("Description:", self.desc_edit)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._validate_and_accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)
        if account:
            self.name_edit.setText(account['name'])
            self.broker_edit.setText(account['broker'])
            self.acct_num_edit.setText(account['account_number'] or '')
            self.type_combo.setCurrentText(account['account_type'])
            idx = self.asset_combo.findData(account['asset_type'])
            if idx >= 0: self.asset_combo.setCurrentIndex(idx)
            self.currency_edit.setText(account['currency'])
            self.balance_spin.setValue(account['initial_balance'])
            self.desc_edit.setText(account['description'] or '')

    def _validate_and_accept(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Validation", "Account name is required.")
            return
        self.accept()

    def get_values(self):
        return dict(
            name=self.name_edit.text().strip(),
            broker=self.broker_edit.text().strip(),
            account_number=self.acct_num_edit.text().strip() or None,
            account_type=self.type_combo.currentText(),
            asset_type=self.asset_combo.currentData(),
            currency=self.currency_edit.text().strip() or 'EUR',
            initial_balance=self.balance_spin.value(),
            description=self.desc_edit.text().strip() or None,
        )
