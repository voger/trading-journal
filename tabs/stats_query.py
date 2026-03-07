"""Custom SQL analytics console — write any SELECT and see results instantly."""

import re
import csv
import io

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QWidget, QLabel, QPushButton,
    QPlainTextEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QSplitter, QTabWidget, QTextBrowser,
    QComboBox, QInputDialog, QMessageBox, QFileDialog, QFrame,
)
from PyQt6.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QColor, QFont, QKeySequence,
)
from PyQt6.QtCore import Qt, QSize

from database import (
    get_custom_queries, save_custom_query, delete_custom_query,
    seed_default_queries,
)


# ── SQL Syntax Highlighter ────────────────────────────────────────────────

class SqlHighlighter(QSyntaxHighlighter):
    """Minimal but complete SQL syntax highlighter for QPlainTextEdit."""

    _KEYWORDS = frozenset({
        'SELECT', 'FROM', 'WHERE', 'JOIN', 'LEFT', 'RIGHT', 'INNER', 'OUTER',
        'FULL', 'CROSS', 'ON', 'AND', 'OR', 'NOT', 'IN', 'IS', 'NULL', 'AS',
        'BY', 'GROUP', 'ORDER', 'HAVING', 'LIMIT', 'OFFSET', 'DISTINCT',
        'UNION', 'ALL', 'EXCEPT', 'INTERSECT', 'WITH', 'RECURSIVE',
        'CASE', 'WHEN', 'THEN', 'ELSE', 'END', 'BETWEEN', 'LIKE', 'GLOB',
        'EXISTS', 'ASC', 'DESC', 'INSERT', 'UPDATE', 'DELETE', 'INTO',
        'VALUES', 'SET', 'TRUE', 'FALSE',
    })

    _FUNCTIONS = frozenset({
        'AVG', 'SUM', 'COUNT', 'MAX', 'MIN', 'TOTAL',
        'ROUND', 'ABS', 'CEIL', 'FLOOR',
        'COALESCE', 'NULLIF', 'IFNULL', 'IIF', 'ISNULL',
        'CAST', 'TYPEOF',
        'JULIANDAY', 'DATE', 'TIME', 'DATETIME', 'STRFTIME', 'UNIXEPOCH',
        'LENGTH', 'UPPER', 'LOWER', 'TRIM', 'LTRIM', 'RTRIM',
        'SUBSTR', 'SUBSTRING', 'REPLACE', 'INSTR', 'PRINTF', 'FORMAT',
        'GROUP_CONCAT',
    })

    def __init__(self, document):
        super().__init__(document)

        def _fmt(color, bold=False, italic=False):
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Weight.Bold)
            if italic:
                f.setFontItalic(True)
            return f

        # Colors chosen to be legible on both light and dark backgrounds
        self._rules = [
            # Keywords — blue, bold
            (re.compile(r'\b(' + '|'.join(self._KEYWORDS) + r')\b', re.IGNORECASE),
             _fmt('#0055dd', bold=True)),
            # Functions — purple
            (re.compile(r'\b(' + '|'.join(self._FUNCTIONS) + r')\b', re.IGNORECASE),
             _fmt('#7b3fa0')),
            # Numbers
            (re.compile(r'\b\d+\.?\d*\b'),
             _fmt('#0a7a4c')),
            # Single-quoted strings (handles '' escapes inside)
            (re.compile(r"'[^']*(?:''[^']*)*'"),
             _fmt('#b5200d')),
            # Line comments — must be last so they override everything
            (re.compile(r'--[^\n]*'),
             _fmt('#5a8a5a', italic=True)),
        ]

    def highlightBlock(self, text):
        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


# ── Reference panel content ───────────────────────────────────────────────

_CHEATSHEET_HTML = """
<style>
  body  { font-size: 12px; margin: 6px; }
  h3    { color: #0055dd; margin: 10px 0 4px 0; border-bottom: 1px solid #ccc; }
  table { border-collapse: collapse; width: 100%; margin-bottom: 6px; }
  td    { padding: 2px 6px; vertical-align: top; }
  td:first-child { white-space: nowrap; font-family: monospace; color: #333; }
  pre, code { font-size: 11px; background: #f0f0f0; padding: 4px 6px;
               border-radius: 3px; display: block; white-space: pre-wrap; }
</style>

<h3>Key Tables</h3>
<table>
<tr><td>trades</td><td>One row per trade (closed &amp; open)</td></tr>
<tr><td>instruments</td><td>Symbol definitions (symbol, display_name)</td></tr>
<tr><td>setup_types</td><td>Your trading setups (name)</td></tr>
<tr><td>accounts</td><td>Accounts (name, currency, initial_balance)</td></tr>
<tr><td>daily_journal</td><td>Journal entries per date</td></tr>
<tr><td>account_events</td><td>Deposits and withdrawals</td></tr>
</table>

<h3>trades — key columns</h3>
<table>
<tr><td>account_id</td><td>FK → accounts.id</td></tr>
<tr><td>instrument_id</td><td>FK → instruments.id</td></tr>
<tr><td>direction</td><td>'buy' or 'sell'</td></tr>
<tr><td>setup_type_id</td><td>FK → setup_types.id (may be NULL)</td></tr>
<tr><td>entry_date</td><td>YYYY-MM-DD</td></tr>
<tr><td>exit_date</td><td>YYYY-MM-DD  (NULL if still open)</td></tr>
<tr><td>entry_price / exit_price</td><td></td></tr>
<tr><td>position_size</td><td>Lots / shares</td></tr>
<tr><td>pnl_account_currency</td><td>Raw P&amp;L (before fees)</td></tr>
<tr><td>commission</td><td>Broker fee (usually negative)</td></tr>
<tr><td>swap</td><td>Overnight fee (usually negative)</td></tr>
<tr><td>r_multiple</td><td>R achieved (may be NULL)</td></tr>
<tr><td>status</td><td>'closed' or 'open'</td></tr>
<tr><td>is_excluded</td><td>1 = excluded from stats</td></tr>
</table>

<h3>Net P&amp;L formula</h3>
<code>pnl_account_currency + commission + swap</code>

<h3>Common JOINs</h3>
<pre>-- instrument symbol:
JOIN instruments i ON t.instrument_id = i.id
-- use: i.symbol

-- setup name:
JOIN setup_types s ON t.setup_type_id = s.id
-- use: s.name</pre>

<h3>Common WHERE clauses</h3>
<pre>WHERE t.account_id = :account_id   ← current account
WHERE t.status = 'closed'
WHERE t.is_excluded = 0
WHERE t.exit_date IS NOT NULL
WHERE t.direction = 'buy'</pre>

<p style="background:#fff8dc;padding:4px 6px;border-left:3px solid #e6b800;font-size:11px;">
<b>:account_id</b> is automatically set to the currently selected
account. Use it in any query to restrict results to that account.
</p>

<h3>Date functions</h3>
<pre>-- Days held:
julianday(t.exit_date) - julianday(t.entry_date)

-- Year-month (e.g. 2025-09):
strftime('%Y-%m', t.entry_date)

-- Year:
strftime('%Y', t.entry_date)

-- Day of week (0=Sun, 6=Sat):
strftime('%w', t.entry_date)</pre>

<h3>Aggregate functions</h3>
<pre>COUNT(*)           row count
AVG(x)             average
SUM(x)             total
MAX(x) / MIN(x)    extremes
ROUND(x, 2)        round to 2 decimals

-- Win rate %:
ROUND(100.0 * SUM(pnl_account_currency > 0)
      / COUNT(*), 1)</pre>

<h3>Query skeleton</h3>
<pre>SELECT ...
FROM trades t
  [JOIN instruments i ON t.instrument_id = i.id]
  [JOIN setup_types s ON t.setup_type_id = s.id]
WHERE t.account_id = :account_id
  AND t.status = 'closed'
  [AND ...]
GROUP BY ...
ORDER BY ... DESC
LIMIT 20</pre>
"""


def _build_schema_html(conn) -> str:
    """Dynamically generate schema reference from the live database."""
    SHOW_TABLES = [
        'trades', 'instruments', 'setup_types', 'accounts',
        'daily_journal', 'account_events', 'executions', 'lot_consumptions',
    ]
    parts = [
        '<style>'
        'body{font-size:12px;margin:6px}'
        'h3{color:#0055dd;margin:10px 0 3px 0;border-bottom:1px solid #ccc}'
        'table{border-collapse:collapse;width:100%;margin-bottom:6px}'
        'td{padding:2px 5px;font-family:monospace;font-size:11px;vertical-align:top}'
        'td:first-child{color:#333;white-space:nowrap}'
        'td:last-child{color:#666}'
        '</style>'
    ]
    for tbl in SHOW_TABLES:
        try:
            cols = conn.execute(f"PRAGMA table_info({tbl})").fetchall()
        except Exception:
            continue
        if not cols:
            continue
        parts.append(f'<h3>{tbl}</h3><table>')
        for col in cols:
            pk = ' <span style="color:#0055dd">PK</span>' if col['pk'] else ''
            nn = ' <span style="color:#b5200d">NOT NULL</span>' if col['notnull'] and not col['pk'] else ''
            parts.append(
                f'<tr><td>{col["name"]}</td>'
                f'<td style="color:#7b3fa0">{col["type"]}</td>'
                f'<td>{pk}{nn}</td></tr>'
            )
        parts.append('</table>')
    return ''.join(parts)


# ── Main widget ───────────────────────────────────────────────────────────

class SqlQueryWidget(QWidget):
    """Custom SQL analytics console."""

    def __init__(self, conn, get_aid_fn, parent=None):
        super().__init__(parent)
        self.conn = conn
        self._get_aid = get_aid_fn
        self._queries = []       # list of sqlite3.Row: id, name, sql_text
        self._loading = False    # guard against combo signal during rebuild

        seed_default_queries(conn)
        self._build_ui()
        self._refresh_combo()

    # ── UI construction ──────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ── Toolbar ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)

        toolbar.addWidget(QLabel("Saved:"))
        self.combo = QComboBox()
        self.combo.setMinimumWidth(220)
        self.combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.combo.currentIndexChanged.connect(self._on_combo_changed)
        toolbar.addWidget(self.combo)

        self.btn_save = QPushButton("Save…")
        self.btn_save.setToolTip("Save current query under a name")
        self.btn_save.clicked.connect(self._on_save)
        toolbar.addWidget(self.btn_save)

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setToolTip("Delete selected saved query")
        self.btn_delete.clicked.connect(self._on_delete)
        toolbar.addWidget(self.btn_delete)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        toolbar.addWidget(sep)

        self.btn_run = QPushButton("▶  Run")
        self.btn_run.setToolTip("Run query  (Ctrl+Enter)")
        self.btn_run.setShortcut(QKeySequence("Ctrl+Return"))
        self.btn_run.clicked.connect(self._on_run)
        run_font = self.btn_run.font()
        run_font.setBold(True)
        self.btn_run.setFont(run_font)
        toolbar.addWidget(self.btn_run)

        toolbar.addStretch()

        self.account_label = QLabel("No account selected")
        self.account_label.setStyleSheet("font-size:11px; color:#555; padding-right:4px;")
        toolbar.addWidget(self.account_label)

        root.addLayout(toolbar)

        # ── Main splitter (editor+ref  /  results) ──
        v_split = QSplitter(Qt.Orientation.Vertical)
        v_split.setChildrenCollapsible(False)
        root.addWidget(v_split)

        # Top: editor + reference panel side-by-side
        h_split = QSplitter(Qt.Orientation.Horizontal)
        h_split.setChildrenCollapsible(False)
        v_split.addWidget(h_split)

        # SQL editor
        editor_container = QWidget()
        ec_lay = QVBoxLayout(editor_container)
        ec_lay.setContentsMargins(0, 0, 0, 0)
        ec_lay.setSpacing(2)
        ec_lay.addWidget(QLabel("SQL:"))
        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont("Courier New", 10))
        self.editor.setTabStopDistance(28)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setPlaceholderText(
            "SELECT i.symbol, COUNT(*) AS trades\n"
            "FROM trades t\n"
            "JOIN instruments i ON t.instrument_id = i.id\n"
            "WHERE t.status = 'closed'\n"
            "GROUP BY i.symbol\n"
            "ORDER BY trades DESC"
        )
        SqlHighlighter(self.editor.document())
        ec_lay.addWidget(self.editor)
        h_split.addWidget(editor_container)

        # Reference panel
        ref_tabs = QTabWidget()
        ref_tabs.setMinimumWidth(240)

        cheatsheet = QTextBrowser()
        cheatsheet.setHtml(_CHEATSHEET_HTML)
        cheatsheet.setOpenLinks(False)
        ref_tabs.addTab(cheatsheet, "Cheat Sheet")

        self.schema_browser = QTextBrowser()
        self.schema_browser.setOpenLinks(False)
        ref_tabs.addTab(self.schema_browser, "Schema")
        ref_tabs.currentChanged.connect(self._on_ref_tab_changed)

        h_split.addWidget(ref_tabs)
        h_split.setSizes([580, 280])

        # Bottom: status + results
        results_container = QWidget()
        rc_lay = QVBoxLayout(results_container)
        rc_lay.setContentsMargins(0, 0, 0, 0)
        rc_lay.setSpacing(2)

        status_row = QHBoxLayout()
        self.status_label = QLabel("No results yet.")
        self.status_label.setStyleSheet("font-size:11px; color:#555;")
        status_row.addWidget(self.status_label)
        status_row.addStretch()
        self.btn_export = QPushButton("Export CSV")
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._on_export)
        status_row.addWidget(self.btn_export)
        rc_lay.addLayout(status_row)

        self.results = QTableWidget()
        self.results.setAlternatingRowColors(True)
        self.results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results.setSortingEnabled(True)
        h = self.results.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h.setStretchLastSection(False)
        self.results.verticalHeader().setVisible(False)
        rc_lay.addWidget(self.results)

        v_split.addWidget(results_container)
        v_split.setSizes([260, 340])

    # ── Saved queries ────────────────────────────────────────────────────

    def _refresh_combo(self):
        self._loading = True
        try:
            self._queries = list(get_custom_queries(self.conn))
            self.combo.clear()
            self.combo.addItem("— select a saved query —", userData=None)
            for q in self._queries:
                self.combo.addItem(q['name'], userData=q['id'])
        finally:
            self._loading = False
        self.btn_delete.setEnabled(False)

    def _on_combo_changed(self, index):
        if self._loading or index <= 0:
            self.btn_delete.setEnabled(False)
            return
        self.btn_delete.setEnabled(True)
        q = self._queries[index - 1]
        self.editor.setPlainText(q['sql_text'])

    def _on_save(self):
        sql = self.editor.toPlainText().strip()
        if not sql:
            QMessageBox.warning(self, "Save Query", "Editor is empty.")
            return

        # Suggest current name if one is selected
        current_idx = self.combo.currentIndex()
        suggestion = (self._queries[current_idx - 1]['name']
                      if current_idx > 0 else "")

        name, ok = QInputDialog.getText(
            self, "Save Query", "Query name:", text=suggestion)
        if not ok or not name.strip():
            return
        name = name.strip()
        save_custom_query(self.conn, name, sql)
        self._refresh_combo()
        # Re-select the just-saved query
        idx = self.combo.findText(name)
        if idx >= 0:
            self._loading = True
            self.combo.setCurrentIndex(idx)
            self._loading = False
            self.btn_delete.setEnabled(True)

    def _on_delete(self):
        idx = self.combo.currentIndex()
        if idx <= 0:
            return
        q = self._queries[idx - 1]
        reply = QMessageBox.question(
            self, "Delete Query",
            f"Delete saved query \"{q['name']}\"?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            delete_custom_query(self.conn, q['id'])
            self._refresh_combo()

    # ── Running queries ──────────────────────────────────────────────────

    def refresh_account(self, account_name: str):
        """Called by StatsTab when the active account changes."""
        if account_name:
            self.account_label.setText(f"Account: {account_name}")
        else:
            self.account_label.setText("No account selected")

    def _on_run(self):
        sql = self.editor.toPlainText().strip()
        if not sql:
            return

        aid = self._get_aid()
        if aid is None:
            self.status_label.setText("No account selected — please select an account first.")
            self.status_label.setStyleSheet("font-size:11px; color:#c80000;")
            return

        # Warn if the query may modify data
        first_word = sql.split()[0].upper()
        if first_word not in ('SELECT', 'WITH', 'EXPLAIN', 'PRAGMA'):
            reply = QMessageBox.warning(
                self, "Potentially Destructive Query",
                f"This query starts with {first_word!r}, which may modify or delete data.\n\n"
                "Run anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        try:
            # :account_id is available as a named parameter in every query
            cur = self.conn.execute(sql, {"account_id": aid})
            rows = cur.fetchall()
            col_names = [d[0] for d in cur.description] if cur.description else []
        except Exception as exc:
            self.status_label.setText(f"Error: {exc}")
            self.status_label.setStyleSheet("font-size:11px; color:#c80000;")
            self.results.setRowCount(0)
            self.results.setColumnCount(0)
            self.btn_export.setEnabled(False)
            return

        self._populate_results(col_names, rows)

    def _populate_results(self, col_names, rows):
        self.results.setSortingEnabled(False)
        self.results.setColumnCount(len(col_names))
        self.results.setHorizontalHeaderLabels(col_names)
        self.results.setRowCount(len(rows))

        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                text = '' if val is None else str(val)
                item = QTableWidgetItem()
                # Store numeric values for proper sort ordering
                if isinstance(val, (int, float)):
                    item.setData(Qt.ItemDataRole.DisplayRole, text)
                    item.setData(Qt.ItemDataRole.UserRole, float(val))
                else:
                    item.setText(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.results.setItem(r, c, item)

        self.results.setSortingEnabled(True)
        # Auto-size columns (capped at 300px to avoid one giant column)
        h = self.results.horizontalHeader()
        for i in range(len(col_names)):
            self.results.resizeColumnToContents(i)
            if self.results.columnWidth(i) > 300:
                self.results.setColumnWidth(i, 300)

        n = len(rows)
        noun = "row" if n == 1 else "rows"
        self.status_label.setText(f"{n} {noun} returned.")
        self.status_label.setStyleSheet("font-size:11px; color:#555;")
        self.btn_export.setEnabled(n > 0)
        self._last_col_names = col_names
        self._last_rows = rows

    # ── Export ───────────────────────────────────────────────────────────

    def _on_export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export to CSV", "query_results.csv",
            "CSV files (*.csv);;All files (*)")
        if not path:
            return
        try:
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(self._last_col_names)
                for row in self._last_rows:
                    writer.writerow(['' if v is None else v for v in row])
            self.status_label.setText(
                f"Exported {len(self._last_rows)} rows to {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))

    # ── Schema tab (lazy-loaded) ─────────────────────────────────────────

    def _on_ref_tab_changed(self, index):
        if index == 1 and not self.schema_browser.toPlainText():
            self.schema_browser.setHtml(_build_schema_html(self.conn))
