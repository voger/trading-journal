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
- `TradingJournal.spec` is checked in and kept in sync with the build scripts. It is the PyInstaller source of truth for CI or manual builds (`pyinstaller TradingJournal.spec`).

### Testing

- `tests/conftest.py` provides `db_path`, `conn`, `stock_account`, `forex_account`, `sample_t212_csv` fixtures plus the optional `real_csv` / `real_mt4` fixtures (skipped if paths not provided).
- Integration tests in `test_integration_real_csv.py` and `test_integration_real_mt4.py` pin exact counts from real broker exports and are the main regression guard for the import pipeline.
- Tests never import PyQt6 — all UI code is excluded from the test surface.
