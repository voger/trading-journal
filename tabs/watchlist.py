"""Watchlist tab — track instruments with bias, key levels, and notes."""
import json
import sqlite3
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTableWidget,
    QTableWidgetItem, QHeaderView, QPushButton, QLabel, QComboBox,
    QPlainTextEdit, QLineEdit, QFormLayout, QGroupBox, QMessageBox,
    QInputDialog, QDialog, QDialogButtonBox, QListWidget, QAbstractItemView,
    QCompleter,
)
from PyQt6.QtCore import Qt, QStringListModel, QEvent
from PyQt6.QtGui import QColor, QFont
from tabs import BaseTab
from database import (
    get_watchlist, get_watchlist_item, add_watchlist_item,
    update_watchlist_item, delete_watchlist_item, reorder_watchlist,
    get_instruments, get_or_create_instrument,
    get_setting, set_setting,
)

_BIAS_CHOICES = ['', 'bullish', 'bearish', 'neutral']
_BIAS_ICONS = {'bullish': '▲', 'bearish': '▼', 'neutral': '◆', '': '—'}
_BIAS_COLORS = {
    'bullish': QColor(0, 150, 0),
    'bearish': QColor(200, 0, 0),
    'neutral': QColor(120, 120, 120),
    '': QColor(180, 180, 180),
}

_HISTORY_KEY = 'watchlist_symbol_history'
_HISTORY_MAX = 100


def _load_history(conn):
    raw = get_setting(conn, _HISTORY_KEY)
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


def _save_history(conn, symbols):
    set_setting(conn, _HISTORY_KEY, json.dumps(symbols))


def _add_to_history(conn, symbol):
    history = _load_history(conn)
    symbol = symbol.upper()
    if symbol in history:
        history.remove(symbol)
    history.insert(0, symbol)
    _save_history(conn, history[:_HISTORY_MAX])


class _ManageHistoryDialog(QDialog):
    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self._conn = conn
        self.setWindowTitle("Manage Symbol History")
        self.resize(280, 360)

        lay = QVBoxLayout(self)
        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.addItems(_load_history(conn))
        self._list.installEventFilter(self)
        lay.addWidget(self._list)

        btn_remove = QPushButton("Remove Selected")
        btn_remove.clicked.connect(self._remove)
        lay.addWidget(btn_remove)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def eventFilter(self, obj, event):
        if obj is self._list and event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Delete:
            self._remove()
            return True
        return super().eventFilter(obj, event)

    def _remove(self):
        row = self._list.currentRow()
        if row < 0:
            return
        self._list.takeItem(row)
        symbols = [self._list.item(i).text() for i in range(self._list.count())]
        _save_history(self._conn, symbols)


class _AddSymbolDialog(QDialog):
    def __init__(self, conn, instruments, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._instruments = instruments
        self.setWindowTitle("Add to Watchlist")
        self.setMinimumWidth(340)

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Enter instrument symbol (e.g., EURUSD, AAPL):"))

        self._edit = QLineEdit()
        self._edit.setPlaceholderText("Symbol")
        # Create completer WITHOUT model first so setFilterMode is applied before
        # the internal proxy filter is initialised; then set the model.
        self._completer = QCompleter(self)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._completer.setModel(self._build_model())
        self._edit.setCompleter(self._completer)
        self._edit.installEventFilter(self)
        self._completer.popup().installEventFilter(self)  # catch Esc from popup
        lay.addWidget(self._edit)

        btn_history = QPushButton("Manage History…")
        btn_history.clicked.connect(self._on_manage)
        lay.addWidget(btn_history)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self._edit.returnPressed.connect(bb.accepted)

    def _build_model(self):
        """History (MRU) first, then any known instruments not already in history."""
        history = _load_history(self._conn)
        seen = {s.upper() for s in history}
        extras = [
            i['symbol'].upper() for i in self._instruments
            if i['symbol'] and i['symbol'].upper() not in seen
        ]
        return QStringListModel(history + extras)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            if obj is self._completer.popup():
                self._completer.popup().hide()
            elif obj is self._edit:
                self.reject()
            return True
        return super().eventFilter(obj, event)

    def _on_accept(self):
        if self._edit.text().strip():
            self.accept()

    def _on_manage(self):
        _ManageHistoryDialog(self._conn, self).exec()
        self._completer.setModel(self._build_model())

    def symbol(self):
        return self._edit.text().strip().upper()


class WatchlistTab(BaseTab):
    def __init__(self, conn, get_aid_fn, status_fn=None):
        super().__init__(conn, get_aid_fn)
        self.status_fn = status_fn
        self._current_item_id = None
        self._saving = False  # prevent refresh loops during save
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        # ── LEFT: watchlist table + toolbar ──
        left = QWidget()
        left_lay = QVBoxLayout(left); left_lay.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        tb = QHBoxLayout()
        btn_add = QPushButton("+ Add"); btn_add.clicked.connect(self._on_add)
        btn_remove = QPushButton("Remove"); btn_remove.clicked.connect(self._on_remove)
        btn_up = QPushButton("▲"); btn_up.setFixedWidth(30); btn_up.clicked.connect(lambda: self._on_move(-1))
        btn_down = QPushButton("▼"); btn_down.setFixedWidth(30); btn_down.clicked.connect(lambda: self._on_move(1))
        for b in [btn_add, btn_remove, btn_up, btn_down]:
            tb.addWidget(b)
        tb.addStretch()
        left_lay.addLayout(tb)

        # Table
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        headers = ['ID', 'Symbol', 'Type', 'W', 'D', 'H4', 'Levels', 'Updated']
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setColumnHidden(0, True)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.currentItemChanged.connect(self._on_selection_changed)
        left_lay.addWidget(self.table)

        splitter.addWidget(left)

        # ── RIGHT: detail panel ──
        right = QWidget()
        right_lay = QVBoxLayout(right); right_lay.setContentsMargins(0, 0, 0, 0)

        self.detail_label = QLabel("Select an instrument")
        self.detail_label.setStyleSheet("font-size: 14pt; font-weight: bold; padding: 4px;")
        right_lay.addWidget(self.detail_label)

        # Bias group
        bias_group = QGroupBox("Bias (Multi-Timeframe)")
        bias_form = QFormLayout(bias_group)
        self.bias_weekly = QComboBox(); self.bias_weekly.addItems(_BIAS_CHOICES)
        self.bias_daily = QComboBox(); self.bias_daily.addItems(_BIAS_CHOICES)
        self.bias_h4 = QComboBox(); self.bias_h4.addItems(_BIAS_CHOICES)
        bias_form.addRow("Weekly:", self.bias_weekly)
        bias_form.addRow("Daily:", self.bias_daily)
        bias_form.addRow("H4:", self.bias_h4)
        right_lay.addWidget(bias_group)

        # Key levels
        levels_group = QGroupBox("Key Levels")
        levels_lay = QVBoxLayout(levels_group)
        levels_lay.addWidget(QLabel("One per line (e.g., 1.0850 — support)"))
        self.levels_edit = QPlainTextEdit()
        self.levels_edit.setPlaceholderText("1.0850 — weekly support\n1.0920 — resistance\n1.1000 — psychological")
        self.levels_edit.setMaximumHeight(120)
        levels_lay.addWidget(self.levels_edit)
        right_lay.addWidget(levels_group)

        # Notes
        notes_group = QGroupBox("Analysis Notes")
        notes_lay = QVBoxLayout(notes_group)
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlaceholderText("Current market structure, bias reasoning, key observations...")
        self.notes_edit.setMaximumHeight(120)
        notes_lay.addWidget(self.notes_edit)
        right_lay.addWidget(notes_group)

        # Alert notes
        alert_group = QGroupBox("Watching For")
        alert_lay = QVBoxLayout(alert_group)
        self.alert_edit = QPlainTextEdit()
        self.alert_edit.setPlaceholderText("Approaching weekly MA — watch for pullback entry\nBreak above 1.0920 could signal continuation")
        self.alert_edit.setMaximumHeight(100)
        alert_lay.addWidget(self.alert_edit)
        right_lay.addWidget(alert_group)

        # Save button
        btn_save = QPushButton("Save Changes")
        btn_save.setStyleSheet("padding: 8px; font-weight: bold;")
        btn_save.clicked.connect(self._on_save)
        right_lay.addWidget(btn_save)
        right_lay.addStretch()

        splitter.addWidget(right)
        splitter.setSizes([400, 500])

    def refresh(self):
        if self._saving:
            return
        if self.aid() is None:
            self.table.setRowCount(0)
            self._clear_detail()
            return
        items = get_watchlist(self.conn, self.aid())
        self.table.setUpdatesEnabled(False)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(items))

        for row, w in enumerate(items):
            cells = [
                str(w['id']),
                w['symbol'] or '',
                (w['instrument_type'] or '').upper()[:3],
            ]
            # Bias columns as colored arrows
            for bias_key in ['bias_weekly', 'bias_daily', 'bias_h4']:
                val = w[bias_key] or ''
                cells.append(_BIAS_ICONS.get(val, '—'))

            # Level count
            levels = (w['key_levels'] or '').strip()
            level_count = len([l for l in levels.split('\n') if l.strip()]) if levels else 0
            cells.append(str(level_count) if level_count else '')

            # Updated
            cells.append((w['updated_at'] or '')[:10])

            for col, val in enumerate(cells):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                # Color bias columns
                if 3 <= col <= 5:
                    bias_key = ['bias_weekly', 'bias_daily', 'bias_h4'][col - 3]
                    bias_val = w[bias_key] or ''
                    item.setForeground(_BIAS_COLORS.get(bias_val, QColor(180, 180, 180)))
                    item.setFont(QFont("", -1, QFont.Weight.Bold))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, col, item)

        self.table.setUpdatesEnabled(True)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        if self.status_fn:
            self.status_fn(f"Watchlist: {len(items)} instruments")

        # Restore selection
        if self._current_item_id is not None:
            for r in range(self.table.rowCount()):
                _id_item = self.table.item(r, 0)
                if _id_item and _id_item.text() == str(self._current_item_id):
                    self.table.setCurrentCell(r, 1)
                    return
        # Clear detail if no selection
        if self.table.rowCount() == 0:
            self._clear_detail()

    def _on_selection_changed(self):
        r = self.table.currentRow()
        if r < 0:
            self._clear_detail(); return
        id_text = self.table.item(r, 0)
        if not id_text or not id_text.text():
            self._clear_detail(); return
        try:
            item_id = int(id_text.text())
        except ValueError:
            self._clear_detail(); return
        self._current_item_id = item_id
        self._load_detail(item_id)

    def _load_detail(self, item_id):
        w = get_watchlist_item(self.conn, item_id)
        if not w:
            self._clear_detail(); return

        self.detail_label.setText(f"{w['symbol']}  ({w['instrument_name']})")

        # Block signals while loading to prevent accidental saves
        for combo in [self.bias_weekly, self.bias_daily, self.bias_h4]:
            combo.blockSignals(True)
        try:
            idx = self.bias_weekly.findText(w['bias_weekly'] or '')
            if idx >= 0: self.bias_weekly.setCurrentIndex(idx)
            else: self.bias_weekly.setCurrentIndex(0)

            idx = self.bias_daily.findText(w['bias_daily'] or '')
            if idx >= 0: self.bias_daily.setCurrentIndex(idx)
            else: self.bias_daily.setCurrentIndex(0)

            idx = self.bias_h4.findText(w['bias_h4'] or '')
            if idx >= 0: self.bias_h4.setCurrentIndex(idx)
            else: self.bias_h4.setCurrentIndex(0)
        finally:
            for combo in [self.bias_weekly, self.bias_daily, self.bias_h4]:
                combo.blockSignals(False)

        self.levels_edit.setPlainText(w['key_levels'] or '')
        self.notes_edit.setPlainText(w['notes'] or '')
        self.alert_edit.setPlainText(w['alert_notes'] or '')

    def _clear_detail(self):
        self._current_item_id = None
        self.detail_label.setText("Select an instrument")
        self.bias_weekly.setCurrentIndex(0)
        self.bias_daily.setCurrentIndex(0)
        self.bias_h4.setCurrentIndex(0)
        self.levels_edit.clear()
        self.notes_edit.clear()
        self.alert_edit.clear()

    def _on_save(self):
        if self._current_item_id is None:
            QMessageBox.information(self, "No Selection", "Select a watchlist item first.")
            return
        self._saving = True
        try:
            update_watchlist_item(self.conn, self._current_item_id,
                bias_weekly=self.bias_weekly.currentText() or None,
                bias_daily=self.bias_daily.currentText() or None,
                bias_h4=self.bias_h4.currentText() or None,
                key_levels=self.levels_edit.toPlainText().strip() or None,
                notes=self.notes_edit.toPlainText().strip() or None,
                alert_notes=self.alert_edit.toPlainText().strip() or None,
            )
            if self.status_fn:
                self.status_fn("Watchlist item saved.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
        finally:
            self._saving = False
        self.refresh()

    def _on_add(self):
        if self.aid() is None:
            QMessageBox.information(self, "No Account", "Select an account before adding watchlist items.")
            return
        # Show dialog: type a symbol or pick from existing instruments
        instruments = get_instruments(self.conn)
        existing_symbols = [i['symbol'] for i in instruments]

        dlg = _AddSymbolDialog(self.conn, instruments, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        symbol = dlg.symbol()
        if not symbol:
            return

        # Check if already on watchlist
        aid = self.aid()
        current = get_watchlist(self.conn, aid)
        for w in current:
            if w['symbol'] == symbol:
                QMessageBox.information(self, "Already Added",
                    f"{symbol} is already on your watchlist.")
                return

        # Get or create instrument
        # Determine type: ask if it's a new instrument
        itype = 'forex'
        if symbol not in existing_symbols:
            types = ['forex', 'stock', 'etf', 'commodity', 'index', 'crypto', 'other']
            chosen, ok2 = QInputDialog.getItem(self, "Instrument Type",
                f"'{symbol}' is new. What type is it?", types, 0, False)
            if not ok2:
                return
            itype = chosen

        try:
            instr_id = get_or_create_instrument(self.conn, symbol, instrument_type=itype)
            # Determine sort_order — append at end
            max_order = max((w['sort_order'] for w in current), default=-1)
            add_watchlist_item(self.conn, instr_id, account_id=aid,
                              sort_order=max_order + 1)
            _add_to_history(self.conn, symbol)
            self.refresh()
            # Select the newly added item
            for r in range(self.table.rowCount()):
                _new_item = self.table.item(r, 1)
                if _new_item and _new_item.text() == symbol:
                    self.table.setCurrentCell(r, 1)
                    break
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Duplicate",
                f"{symbol} is already on the watchlist for this account.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_remove(self):
        if self._current_item_id is None:
            return
        r = self.table.currentRow()
        _sym_item = self.table.item(r, 1) if r >= 0 else None
        symbol = _sym_item.text() if _sym_item else "this item"
        reply = QMessageBox.question(self, "Remove",
            f"Remove {symbol} from watchlist?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                delete_watchlist_item(self.conn, self._current_item_id)
                self._current_item_id = None
                self._clear_detail()
                self.refresh()
                if self.table.rowCount() > 0:
                    self.table.setCurrentCell(min(r, self.table.rowCount() - 1), 1)
                    self._on_selection_changed()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _on_move(self, direction):
        """Move selected item up (-1) or down (+1)."""
        r = self.table.currentRow()
        if r < 0:
            return
        target = r + direction
        if target < 0 or target >= self.table.rowCount():
            return

        # Collect current order of IDs
        ids = []
        for row in range(self.table.rowCount()):
            id_item = self.table.item(row, 0)
            if id_item and id_item.text():
                try:
                    ids.append(int(id_item.text()))
                except ValueError:
                    continue

        # Swap
        ids[r], ids[target] = ids[target], ids[r]
        try:
            reorder_watchlist(self.conn, ids)
            self.refresh()
            # Restore selection to moved item
            self.table.setCurrentCell(target, 1)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
