# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
source venv/bin/activate

python -m pytest tests/ -q
python -m pytest tests/test_fifo_engine.py::TestFIFOEngine::test_basic_buy_sell -q

# Integration tests (skipped unless files provided)
python -m pytest tests/ -q --real-csv=/home/voger/VMSHARED/from_2025-05-22_to_2026-02-15_MTc3MTE1NTA4MjgyNg.csv
python -m pytest tests/ -q --real-mt4=/home/voger/VMSHARED/DetailedStatement.htm

bash build_app.sh   # Linux
build_app.bat       # Windows
python main.py
```

## Architecture

### Data flow

**MT4** (`trades` mode): `import_manager._import_trades()` → one trade row per parsed row, dedup by `broker_ticket_id`.

**Trading212** (`executions` mode): `import_manager._import_executions()` → raw executions table → `fifo_engine.run_fifo_matching()` per instrument → writes `trades` + `lot_consumptions`. FIFO is idempotent.

### Key modules

- **`database.py`** — star-import shim only; real code in `db/`
  - `db/connection.py` — `get_app_data_dir()`, `get_connection()`. Data dir: `~/.local/share/TradingJournal` (Linux), `%APPDATA%\TradingJournal` (Windows), `~/Library/Application Support/TradingJournal` (macOS).
  - `db/schema.py` — `init_database()`, `_migrate()`
  - `db/crud.py` — all entity CRUD
  - `db/analytics.py` — `effective_pnl()`, `get_trade_stats()`, `get_trade_breakdowns()`, `get_advanced_stats()`, `get_daily_pnl()`
  - `db/queries.py` — `get_trades_paged()`, `get_trades_all_filtered()`, `EXPORT_COLUMNS`
- **`fifo_engine.py`** — stocks only; forex bypasses it entirely
- **`import_manager.py`** — plugin selection → validate → parse → `_import_trades` or `_import_executions`
- **`main.py`** — app entry, account CRUD, backup/restore, tab wiring

### Plugin interface (`plugins/`)

Must expose: `PLUGIN_NAME`, `DISPLAY_NAME`, `SUPPORTED_EXTENSIONS`, `IMPORT_MODE` (`'trades'` or `'executions'`), `validate(path) -> (bool, str)`, `parse(path) -> list | (list, list)`, `file_hash(path) -> str`.

New plugins are auto-discovered — **also add to `--hidden-import` in both build scripts**.

### Asset modules (`asset_modules/`)

`AssetModule` subclasses define per-asset-type behaviour (table columns, trade dialog fields, stats HTML). Registered in `asset_modules/__init__.py`. Selected at runtime via `get_module(account.asset_type)`.

### UI (`tabs/`)

Each tab is a `QWidget` with `refresh()`, receives `(conn, get_account_id_fn, status_fn)`. Tabs communicate via `MainWindow` signals (`data_changed` → `_on_trades_changed`, `_on_setups_changed`). No shared state except the SQLite connection.

- `StatsTab` has inner sub-tabs; widgets in `stats_widgets.py`, formula editor in `stats_formula.py`, calendar heatmap in `stats_calendar.py`.
- `TradesTab` uses mixins: `trades_preview.py`, `trades_actions.py`, `trades_widgets.py`.
- `dialogs.py` is a shim; real classes in `dialogs_widgets.py`, `dialogs_account.py`, `dialogs_trade.py`, `dialogs_setup.py`.

### Chart providers (`chart_providers/`)

Subclasses registered in `chart_providers/__init__.py`. API keys stored in `app_settings` DB table. `yfinance_provider.py` uses `auto_adjust=False` (raw/unadjusted prices to match recorded trade prices).

### Build notes

- PyInstaller 6.x — `--add-data` separator is `:` on all platforms.
- Both scripts include `--hidden-import` for all dynamically loaded modules (plugins, asset modules, chart providers, `executions_dialog`).
- `.spec` is auto-generated and gitignored; build scripts are the source of truth.

### Testing

- Fixtures in `tests/conftest.py`: `db_path`, `conn`, `stock_account`, `forex_account`, `sample_t212_csv`.
- Tests never import PyQt6 — all UI code is excluded from the test surface.
- Baseline: **614 passed, 42 skipped**.

## Intentional design decisions (do not change)

- **Equity Curve requires a specific account** — "All Accounts" shows a prompt by design. No combined multi-account curve.
- **Watchlist and Journal clear on "All Accounts"** — items are always account-scoped.
- **`dates.insert(0, dates[0])` in `equity.py`** — intentional anchor so `balances[0]` aligns with initial balance on step plots.
- **`_saving` flag in `watchlist.py._on_save()` uses `try/finally`** — intentional, resets even on exception.
- **Font embedding was tried and reverted** — loading via `QFontDatabase` bypasses OS sub-pixel rendering (FreeType/ClearType), producing fuzzy text. Not fixable without a custom style engine.
- **Splitter initial sizing on Windows is a known issue** — proportions wrong on first launch, can be dragged. No reliable fix found.
- **QCompleter**: `setModel()` must be called *after* `setFilterMode()` — passing model to constructor before configuring filter silently reverts `MatchContains` to `MatchStartsWith`.
- **`stocks.py` dividends `if v` not `if v is not None`** — zero means "no dividend data injected", shown as empty. Intentional; covered by `test_dividends_zero`.

## Roadmap

All items shipped. No open items.
