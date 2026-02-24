# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Activate venv (required before anything else)
source venv/bin/activate

# Run all tests
python -m pytest tests/ -q

# Run a single test file
python -m pytest tests/test_fifo_engine.py -q

# Run a single test by name
python -m pytest tests/test_fifo_engine.py::TestFIFOEngine::test_basic_buy_sell -q

# Run integration tests (skipped by default unless files are provided)
python -m pytest tests/ -q --real-csv=/home/voger/VMSHARED/from_2025-05-22_to_2026-02-15_MTc3MTE1NTA4MjgyNg.csv
python -m pytest tests/ -q --real-mt4=/home/voger/VMSHARED/DetailedStatement.htm

# Build standalone executable (Linux/macOS)
bash build_app.sh

# Build standalone executable (Windows)
build_app.bat

# Run the app
python main.py
```

## Architecture

### Data flow

**MT4 import** (legacy `trades` mode):
`build_app.bat` / `build_app.sh` → `import_manager._import_trades()` → inserts one trade row per parsed row, deduplication by `broker_ticket_id`.

**Trading212 import** (`executions` mode):
`import_manager._import_executions()` → inserts raw buy/sell rows into `executions` table → calls `fifo_engine.run_fifo_matching()` per instrument → FIFO engine writes/rewrites `trades` and `lot_consumptions`. Re-running FIFO is idempotent (rebuilds from scratch).

The import mode is selected by `IMPORT_MODE` on the plugin module (`'trades'` or `'executions'`).

### Key modules

- **`database.py`** — All SQLite access. Single connection per session (`sqlite3.Row` factory, WAL mode, FK enforcement). Schema in `SCHEMA_SQL` constant; `init_database()` is idempotent. `get_app_data_dir()` returns the platform data directory (`~/.local/share/TradingJournal` on Linux, `%APPDATA%\TradingJournal` on Windows, `~/Library/Application Support/TradingJournal` on macOS).
- **`fifo_engine.py`** — Stocks-only. Reads all executions for an (account, instrument) pair, splits them into round trips (a round trip ends when shares reach 0), writes `trades` + `lot_consumptions`. Forex trades bypass this entirely.
- **`import_manager.py`** — Orchestrates import: plugin selection → validate → parse → `_import_trades` or `_import_executions`. Plugins are loaded dynamically via `importlib` at startup.
- **`main.py`** — App entry point. Wires tabs together, handles account CRUD and backup/restore. On first run, migrates the database from the old project-directory location to the XDG data directory automatically.

### Plugin system (`plugins/`)

Each plugin module must expose:
- `PLUGIN_NAME`, `DISPLAY_NAME`, `SUPPORTED_EXTENSIONS`
- `IMPORT_MODE` — `'trades'` (MT4) or `'executions'` (Trading212)
- `validate(file_path) -> (bool, str)`
- `parse(file_path) -> list | (list, list)` — returns trades or `(executions, balance_events)`
- `file_hash(file_path) -> str` — for deduplication at file level

New plugins go in `plugins/` and are auto-discovered by `import_manager.py` — **also add them to `--hidden-import` in both build scripts**.

### Asset module system (`asset_modules/`)

`AssetModule` subclasses define per-asset-type behaviour: which columns appear in the trade table, what fields the trade dialog shows, how stats HTML is formatted. Registered in `asset_modules/__init__.py`. The `account.asset_type` field selects the module at runtime via `get_module(asset_type)`.

### UI structure (`tabs/`)

Each tab is a `QWidget` subclass with a `refresh()` method and receives `(conn, get_account_id_fn, status_fn)` at construction. Tabs communicate via signals on `MainWindow` (`data_changed` → `_on_trades_changed`, `_on_setups_changed`). There is no shared state between tabs other than the SQLite connection.

### Intentional design decisions (do not suggest changing these)

- **Equity Curve requires a specific account to be selected.** Showing "Please select an account" when "All Accounts" is active is by design — a combined multi-account equity curve is not a goal. Do not recommend adding one.

### Chart providers (`chart_providers/`)

`ChartProvider` subclasses registered in `chart_providers/__init__.py`. Each exposes `fetch_ohlc()`, `display_timeframes()`, `normalize_symbol()`, and `requires_api_key`. API keys are stored in the `app_settings` DB table, not in files.

Note: `yfinance_provider.py` fetches with `auto_adjust=False` to return raw (unadjusted) OHLC prices, matching the actual traded prices recorded in the database.

### Icons (`icons/`)

All icon assets live in `icons/`: `icon.png`, `icon.svg`, and pre-sized PNGs (`icon_32.png`, `icon_48.png`, `icon_64.png`, `icon_128.png`, `icon_256.png`). The Windows build generates `icons/icon.ico` from these at build time (gitignored).

### Build notes

- `build_app.sh` / `build_app.bat` use PyInstaller `--onedir`. PyInstaller version is **6.x** — `--add-data` uses `:` as separator on all platforms (not `;`).
- Icons are bundled with `--add-data "icons:icons"` (the whole folder, not individual files).
- Both scripts include `--hidden-import` entries for all dynamically loaded modules (plugins, asset modules, chart providers, `executions_dialog`).
- `build_app.sh` (Linux) generates `dist/TradingJournal/install.sh` for desktop integration (`.desktop` file + hicolor icon). Run with `uninstall` argument to reverse.
- `build_app.bat` (Windows) generates `icons/icon.ico` and copies `install.ps1` to the dist folder. Run with `-Uninstall` to reverse.
- The `.spec` file is auto-generated on each build and gitignored; the build scripts are the source of truth.

### Testing

- `tests/conftest.py` provides `db_path`, `conn`, `stock_account`, `forex_account`, `sample_t212_csv` fixtures plus the optional `real_csv` / `real_mt4` fixtures (skipped if paths not provided).
- Integration tests in `test_integration_real_csv.py` and `test_integration_real_mt4.py` pin exact counts from real broker exports and are the main regression guard for the import pipeline.
- Tests never import PyQt6 — all UI code is excluded from the test surface.
- Current baseline: **483 passed, 42 skipped** across `test_database.py`, `test_fifo_engine.py`, `test_coverage_gaps.py`, `test_analytics.py`.

## Recent changes (v2.5.2)

### Bug fix — table selection colour goes gray on focus-loss (`tabs/trades.py`)
- Qt's Fusion theme uses a separate `Inactive` palette group for unfocused widgets, rendering the selected row in washed-out gray when focus moves to the preview panel (e.g. clicking "Fetch Chart").
- **Wrong fix (reverted)**: QSS `::item:selected:!active { background: #1565c0 }` — hardcoded a slightly different shade of blue, still visually inconsistent.
- **Correct fix**: copy `Active` → `Inactive` for `QPalette.ColorRole.Highlight` and `HighlightedText` on the table. Qt then uses the exact same colour for both focused and unfocused selection states. Theme-aware — works with Fusion, dark theme, and Windows accent colours.

### Bug fix — splitter initial sizing fragile on Windows (`tabs/trades.py`)
- `resizeEvent` once-flag fired before the window was fully laid out at some DPI-scaling settings on Windows, so `sum(splitter.sizes())` returned unreliable minimum-size values and the 58 %/42 % split was applied incorrectly.
- Fix: replaced `resizeEvent` with `showEvent + QTimer.singleShot(0, ...)` which defers one event-loop tick until layout is complete, guaranteeing real widget dimensions when `setSizes()` is called.

## Recent changes (v2.5.1)

### Bug fix — `twelvedata_provider.py` `normalize_symbol` suffix stripping
- Dots were removed from the symbol **before** checking broker suffixes, making `.RAW`, `.ECN`, `.PRO`, `.STD` dead code: `'EURUSD.RAW'` became `'EURUSDRAW'` with no suffix match, returning the wrong ticker.
- Suffix order also had `'M'` before `'MINI'`, risking partial matches.
- Fix (matching `yfinance_provider.py`): strip suffixes **before** dot removal; add `break` after first match; reorder to `['.RAW', '.ECN', '.PRO', '.STD', 'MINI', 'M']`.
- 10 new tests added in `test_coverage_gaps.py::TestNormalizeSymbol`.

### Bug fix — `dialogs.py` `TradeDialog._populate()` crash on NULL direction
- `self.dir_combo.setCurrentText(t['direction'])` raised `TypeError` in PyQt6 when `t['direction']` was `None` (e.g. corrupted or legacy imported trade).
- Fix: `self.dir_combo.setCurrentText(t['direction'] or 'long')`.

### Bug fixes — `tabs/trades.py`, `database.py` (v2.5.0 fixes committed separately)
- WIN/LOSS badge inconsistency: table row, preview panel, and KPI filter now all use `effective_pnl()` for classification.
- Calmar ratio returns `float('inf')` (not `0.0`) when P&L is positive but drawdown is zero.
- `tabs/stats.py`: Calmar display guard added for `float('inf')` → "∞".
- `chart_providers/twelvedata_provider.py`: `rstrip(suffix)` → `[:-len(suffix)]` for exact suffix removal (same fix as yfinance).
- `APP_VERSION` bumped to `"2.5.0"`.

## Recent changes (v2.5.0)

### Equity curve mode toggle (`tabs/equity.py`)
- Added "Balance" / "Cumulative P&L" toggle buttons at the top of the Equity Curve tab.
- **Balance mode**: unchanged — shows account balance including deposits/withdrawals.
- **Cumulative P&L mode**: starts at 0, plots trade P&L only (no deposit jumps), matching Trademetria-style curves.
- `_populate_deposits_table()` extracted as a shared helper called by both modes.
- `_set_mode()` updates button checked state and re-renders.

### New statistics (`database.py`, `tabs/stats.py`)
- **Sortino Ratio**: downside deviation with MAR=0; displayed after Sharpe Ratio.
- **Calmar Ratio**: net P&L / max absolute drawdown; displayed after Sortino.
- **Avg Duration split**: single "Avg Duration" row expanded to three rows — overall, Winners (green), Losers (red).
- `get_advanced_stats()` duration loop now uses `zip(trades, pnls)` to track winner/loser durations separately.

### Bug fix — month breakdown discarding open trades (`database.py`)
- `get_trade_breakdowns()` month branch: `exit_date` is NULL for open trades; `None[:7]` raised TypeError and silently grouped them under key `'?'`. Fixed to fall back to `entry_date`: `key = (t['exit_date'] or t['entry_date'] or '')[:7]`.

### Chart widget overhaul (`chart_widget.py`)
- Price axis moved to the right side (`y_on_right=True`); "Price" ylabel removed.
- Chart fills the full panel — `tight_layout=False` + `ax.set_position([0.005, 0.09, 0.935, 0.895])` bypasses mplfinance's internal GridSpec (which overrides `subplots_adjust`).
- In-axes compact title (symbol, timeframe, direction) replaces the large figure title.
- Denser y-axis scale: `MaxNLocator(nbins=10)`.
- Smaller axis tick labels (6px).
- Entry/exit annotations: vertical arrows, `annotation_clip=False`; entry in blue/purple, exit in dark-cyan/amber depending on win/loss.
- Connecting line between entry and exit in amber (`#ff9800`) to stand out from candle colours.
- `_smart_vert_offset()`: places labels on the side with less candle mass in a ±5-bar window.
- `_clamped_offset()`: flips placement if within 10% of y-axis edge.
- `_fmt_price()`: formats prices with appropriate decimal places.
- Canvas `setSizePolicy(Expanding, Expanding)` so it fills the Qt widget.

### App startup (`main.py`)
- `w.showMaximized()` — app now starts maximized.

### Trades tab splitter initial sizing (`tabs/trades.py`)
- `resizeEvent` with a `_splitter_sized` once-flag: sets 58%/42% split on the first resize (when real dimensions are available). With both stretch factors at Qt default (0), proportions are preserved on subsequent resizes. Manual dragging still works freely.

## Recent changes (v2.4.0)

### UI — sidebar account switcher (`main.py`)
- Replaced top `QComboBox` with a left `QListWidget` sidebar inside a `QSplitter(Horizontal)`.
- "All Accounts" item is bold; each account shows name, currency, and asset type on two lines.
- `_aid()` reads `Qt.ItemDataRole.UserRole` from the selected item (returns `None` for All Accounts).
- `_refresh_account_list()` replaces `_refresh_account_filter()` — preserves prior selection across refreshes.

### UI — trades tab improvements (`tabs/trades.py`)
- **Symbol search**: `QLineEdit` filter added to the filter bar; filters by symbol substring instantly.
- **Preview panel**: rebuilt as `QSplitter(Vertical)` — text metrics on top, chart on bottom, no scrollbars. Font sizes reduced (header 16px, P&L hero 22px) to keep metrics pane compact.
- **Column widths**: Instrument column no longer stretches; Setup column capped at 130px via `resizeColumnsToContents()`.
- **Truncation warning**: fetches 2001 rows; if >2000 exist, slices to 2000 and shows an amber label in the KPI bar.
- **Effective P&L**: `_update_kpi()` and the Winners/Losers/Breakeven outcome filter now use `effective_pnl(t)` (pnl + swap + commission), consistent with the Stats tab.
- **`_pnl_col_idx`** stored during `refresh()` and used in `_show_event_preview` instead of the brittle `columnCount() - 4` magic offset.

### UI — chart widget (`chart_widget.py`)
- "Fetch Chart" and "Open Image" buttons moved to a second row so they don't clip when the preview pane is narrow.
- `fetch_ohlc()` call now passes `norm_sym` (the normalized symbol) instead of the raw `symbol` — symbol normalization was previously computed but silently ignored.

### Metrics fixes (`database.py`, `tabs/stats.py`)
- `effective_pnl(t)` (public) — returns `pnl_account_currency + swap + commission`. Used in all win/loss/total calculations in `_compute_stats()` and `get_advanced_stats()`.
- Max drawdown % fixed: equity and peak now start at `accounts.initial_balance` instead of 0 (was producing thousands-of-percent nonsense on accounts with small early gains).
- Max drawdown display: removed confusing `+` sign; added currency and "peak-to-trough" label.

### `chart_providers/yfinance_provider.py` bug fixes
- `normalize_symbol()` now strips broker suffixes (`.RAW`, `.ECN`, `.PRO`, `.STD`, `MINI`, `M`) **before** dot removal — previously dot-containing suffixes were dead code since dots were stripped first. Uses `[:-len(suffix)]` instead of `rstrip(chars)` for exact suffix removal.
- NaN rows filtered with `dropna(subset=['Open','High','Low','Close'])` after the optional 4h resample — prevents NaN bars reaching the chart renderer and corrupting entry/exit marker positioning.

### `database.py` — dynamic executions mode detection
- `_plugin_is_executions_mode(plugin_name)` — dynamically imports the plugin and reads its `IMPORT_MODE` attribute. `delete_import_log` uses this instead of a hardcoded set, so new executions-mode plugins work automatically. Falls back to the known set if the plugin can't be imported.

### Tests (`tests/test_analytics.py`)
- `TestEffectivePnl` — 4 tests covering pnl-only, pnl+swap, swap flipping a winner to loser, and net_pnl including all components.
- `TestDrawdownWithInitialBalance` — verifies drawdown % is bounded by initial_balance (not inflated when early equity is near zero).

### Known intentional design decisions
- `dates.insert(0, dates[0])` in `equity.py._render()` is intentional — creates the starting anchor point so `balances[0]` (initial balance) aligns correctly for matplotlib step plots.
- `_saving` flag in `watchlist.py._on_save()` uses `try/finally` — correctly resets even on exception.
- Watchlist and Journal tabs clear when "All Accounts" is selected — items are always account-scoped.
- Equity Curve requires a specific account (see Intentional design decisions above).
