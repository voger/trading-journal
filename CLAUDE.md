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
- Current baseline: **349 passed, 42 skipped** across `test_database.py`, `test_fifo_engine.py`, `test_coverage_gaps.py`.

## Recent changes (last two sessions)

### Equity tab
- Click-to-highlight on the deposits table — clicking a row highlights its axvline marker on the chart (changes linewidth/linestyle, calls `canvas.draw()` without full re-render).
- Equity balance calculation now merges account events (deposits/withdrawals/interest) into the chronological trade timeline, matching MT4's DetailedStatement behaviour. Starting point is `accounts.initial_balance`.

### Stats tab
- Period filter combo added ("All Time", "This Month", "Last Month", "This Year", "Last 30/90 Days"). Passes `date_from`/`date_to` to `get_trade_stats`, `get_trade_breakdowns`, `get_advanced_stats`. Open trade count is never date-filtered.

### Import tab (`tabs/imports.py`)
- Added hidden ID column (col 0) and a **Delete Log** toolbar button. Deleting a log removes all linked trades/executions. For executions-mode imports (Trading212), FIFO is automatically re-run for affected instruments after deletion. `imports_tab.data_changed` is wired to `_on_trades_changed` in `main.py`.
- Error count in the table now uses `json.loads()` instead of `.split('\n')` — previously always showed 1 regardless of actual error count.

### Import pipeline (`import_manager.py`)
- `_import_trades` restructured to create the import log **before** importing balance events (matches `_import_executions` pattern).
- `_import_balance_events` now accepts and stores `import_log_id` on every `account_events` row, enabling `delete_import_log` to cleanly remove them.

### `database.py`
- `delete_import_log(conn, log_id)` — new function. Trades-mode: deletes trades (cascades). Executions-mode: deletes raw executions + all FIFO-built trades for affected instruments; caller re-runs FIFO. Also deletes linked `account_events`. Returns `(plugin_name, account_id, affected_instrument_ids)`.
- `get_import_logs` default limit raised 50 → 500.
- Added composite index `idx_trades_account_entry_date ON trades(account_id, entry_date)` to both `SCHEMA_SQL` and `_migrate()`.

### `fifo_engine.py`
- Guarded `wavg_entry` and `wavg_exit` weighted-average divisions against zero denominator.

### Account guards
- `tabs/journal.py`, `tabs/watchlist.py`, `tabs/imports.py` — `refresh()` returns early (clears content) when no account is selected (`self.aid() is None`). `journal._on_save()` and `watchlist._on_add()` also guard.

### MT4 plugin fix
- `detect_instrument_type` logic corrected — removed redundant loop and fixed fallthrough for symbols that are >6 chars but not in CRYPTO_SYMBOLS.

### `tabs/trades.py`
- Named column index constants (`_N_PREFIX`, `pnl_idx`, etc.) replace magic arithmetic.
- Import progress dialog (`QProgressDialog`) shown during file import.
- `ev['event_type']` null-guarded before `.upper()` call.

### Bare except fixes
- All `except:` clauses replaced with specific types (`OSError`, `AttributeError`, `ValueError`, `TypeError`) across `tabs/`, `chart_widget.py`, `database.py`.

### Known intentional design decisions
- `dates.insert(0, dates[0])` in `equity.py._render()` is intentional — creates the starting anchor point so `balances[0]` (initial balance) aligns correctly for matplotlib step plots.
- `_saving` flag in `watchlist.py._on_save()` uses `try/finally` — correctly resets even on exception.
