"""Trades tab — CRUD and import/export actions mixin."""
import csv
import os
import shutil
from datetime import datetime

from PyQt6.QtWidgets import (
    QMessageBox, QApplication, QDialog,
    QDialogButtonBox, QFileDialog,
    QComboBox, QLabel, QPushButton, QProgressDialog,
    QVBoxLayout as _VL,
)
from PyQt6.QtCore import Qt

from dialogs import TradeDialog
from database import (
    get_accounts, get_account, get_trade, create_trade,
    update_trade, delete_trade,
    add_trade_chart, delete_trade_chart,
    save_trade_rule_checks, create_account,
    get_trades_for_export, EXPORT_COLUMNS,
    get_app_data_dir, effective_pnl,
    get_or_create_tag, set_trade_tags,
)

SCREENSHOTS_DIR = os.path.join(get_app_data_dir(), 'screenshots')
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)


class TradesActionsMixin:
    """Mixin providing CRUD and import/export actions for TradesTab."""

    # ── Validation ──

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

    # ── CRUD ──

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
                oserrors = []
                for cid in dlg.get_delete_chart_ids():
                    fpath = delete_trade_chart(self.conn, cid)
                    if fpath and os.path.exists(fpath):
                        try:
                            os.remove(fpath)
                        except OSError as oe:
                            oserrors.append(str(oe))
                if oserrors:
                    raise OSError("Could not delete screenshot file(s):\n" + "\n".join(oserrors))
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
        """Export the currently visible (filtered) trades to CSV or ODS.

        Exports exactly the trades shown in the table, respecting all active
        filters. Includes a computed 'Net P&L' column (pnl + swap + commission)
        in addition to the raw DB columns.
        """
        if not self._visible_trades:
            QMessageBox.information(self, "Export", "No trades to export.")
            return

        aid = self.aid()
        acct = get_account(self.conn, aid) if aid else None
        acct_name = acct['name'].replace(' ', '_') if acct else 'trades'
        stem = f"{acct_name}_export_{datetime.now().strftime('%Y%m%d')}"

        fp, selected_filter = QFileDialog.getSaveFileName(
            self, "Export Trades", f"{stem}.ods",
            "ODS Spreadsheet (*.ods);;CSV Files (*.csv);;All Files (*.*)")
        if not fp:
            return

        # Ensure correct extension when the user doesn't type one
        if '*.ods' in selected_filter and not fp.lower().endswith('.ods'):
            fp += '.ods'
        elif '*.csv' in selected_filter and not fp.lower().endswith('.csv'):
            fp += '.csv'

        headers = [label for _, label in EXPORT_COLUMNS] + ['Net P&L']
        rows = []
        for t in self._visible_trades:
            row = []
            for key, _ in EXPORT_COLUMNS:
                val = t[key] if key in t.keys() else ''
                row.append('' if val is None else val)
            row.append(round(effective_pnl(t), 8))
            rows.append(row)

        try:
            if fp.lower().endswith('.ods'):
                _write_ods(fp, headers, rows)
            else:
                with open(fp, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(headers)
                    writer.writerows(rows)

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
            lay = _VL(dlg)
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


# ── ODS writer ────────────────────────────────────────────────────────────

def _write_ods(fp, headers, rows):
    """Write trade data to an ODS spreadsheet using odfpy.

    Numeric values are stored as floats (not strings) so spreadsheet
    applications can sum/average them. The Net P&L column is color-coded
    green/red. The header row is bold with a dark-blue background.
    """
    import math
    from odf.opendocument import OpenDocumentSpreadsheet
    from odf.style import Style, TextProperties, TableCellProperties
    from odf.table import Table, TableRow, TableCell
    from odf.text import P

    doc = OpenDocumentSpreadsheet()

    # ── Styles ────────────────────────────────────────────────────────────
    def _cell_style(name, bold=False, fg=None, bg=None):
        s = Style(name=name, family="table-cell")
        tp_attrs = {}
        if bold:
            tp_attrs['fontweight'] = 'bold'
        if fg:
            tp_attrs['color'] = fg
        if tp_attrs:
            s.addElement(TextProperties(**tp_attrs))
        if bg:
            s.addElement(TableCellProperties(backgroundcolor=bg))
        doc.automaticstyles.addElement(s)
        return name

    _s_header  = _cell_style("TH",     bold=True, fg="#ffffff", bg="#1e3a5f")
    _s_default = _cell_style("TD")
    _s_profit  = _cell_style("Profit", fg="#008200")
    _s_loss    = _cell_style("Loss",   fg="#c80000")

    # ── Table ─────────────────────────────────────────────────────────────
    table = Table(name="Trades")

    # Header row
    tr = TableRow()
    for h in headers:
        tc = TableCell(stylename=_s_header, valuetype="string")
        tc.addElement(P(text=str(h)))
        tr.addElement(tc)
    table.addElement(tr)

    # Detect which column index holds Net P&L (always last)
    net_pnl_idx = len(headers) - 1

    # Data rows
    for row in rows:
        tr = TableRow()
        for col_idx, val in enumerate(row):
            if isinstance(val, (int, float)) and not (math.isinf(val) or math.isnan(val)):
                # Pick color style for the Net P&L column
                if col_idx == net_pnl_idx:
                    sname = _s_profit if val > 0 else _s_loss if val < 0 else _s_default
                else:
                    sname = _s_default
                display = str(val) if isinstance(val, int) else f"{val:.8g}"
                tc = TableCell(stylename=sname, valuetype="float", value=str(val))
                tc.addElement(P(text=display))
            else:
                tc = TableCell(stylename=_s_default, valuetype="string")
                tc.addElement(P(text=str(val) if val is not None else ''))
            tr.addElement(tc)
        table.addElement(tr)

    doc.spreadsheet.addElement(table)
    doc.save(fp)
