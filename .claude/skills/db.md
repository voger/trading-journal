# DB skill

Reference for database architecture, data flow, and SQL conventions.

## Key modules

- **`database.py`** — star-import shim only; real code in `db/`
  - `db/connection.py` — `get_app_data_dir()`, `get_connection()`. Data dir: `~/.local/share/TradingJournal` (Linux), `%APPDATA%\TradingJournal` (Windows), `~/Library/Application Support/TradingJournal` (macOS).
  - `db/schema.py` — `init_database()`, `_migrate()`
  - `db/crud.py` — all entity CRUD
  - `db/analytics.py` — `effective_pnl()`, `get_trade_stats()`, `get_trade_breakdowns()`, `get_advanced_stats()`, `get_daily_pnl()`
  - `db/queries.py` — `get_trades_paged()`, `get_trades_all_filtered()`, `EXPORT_COLUMNS`
- **`fifo_engine.py`** — stocks only; forex bypasses it entirely
- **`import_manager.py`** — plugin selection → validate → parse → `_import_trades` or `_import_executions`

## Data flow

**MT4** (`trades` mode): `import_manager._import_trades()` → one trade row per parsed row, dedup by `broker_ticket_id`.

**Trading212** (`executions` mode): `import_manager._import_executions()` → raw executions table → `fifo_engine.run_fifo_matching()` per instrument → writes `trades` + `lot_consumptions`. FIFO is idempotent.

## SQL style

- SQL strings must be **plain readable literals** — never assembled by concatenating Python variables or constants together. Readability of the query as a whole matters more than DRY.
- Dynamic WHERE clauses (built from filter lists like `clauses`) are the one acceptable exception, since the conditions are genuinely runtime-variable.
- `_TRADES_BASE_SQL` in `db/queries.py` is a single literal string. `count_trades_filtered()` repeats the FROM/JOIN block intentionally — do not extract it.

## Intentional design decisions (do not change)

- **`sqlite3.Row` has no `.get()`** — always pass `dict(row)` to `TradeDialog` and any code expecting a dict. Callers in `trades_actions.py`, `stats_calendar.py` all do this unconditionally.
- **`stocks.py` dividends `if v` not `if v is not None`** — zero means "no dividend data injected", shown as empty. Intentional; covered by `test_dividends_zero`.
