# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick reference

- Run tests: see `.claude/skills/test.md` (or invoke `/test`)
- Build app: see `.claude/skills/build.md` (or invoke `/build`)
- DB architecture & SQL style: `.claude/skills/db.md` (or invoke `/db`)
- UI architecture & theming: `.claude/skills/ui.md` (or invoke `/ui`)

## Commands

```bash
source venv/bin/activate
python main.py
```

## Architecture overview

Python + PyQt6 desktop app, SQLite backend.

- **`database.py`** — star-import shim; real code in `db/` (incl. `db/journal.py` — the `Journal` repository seam the UI uses instead of threading `conn`; see `/db` skill)
- **`fifo_engine.py`** — FIFO matching for stocks (forex bypasses it)
- **`import_manager.py`** — plugin selection → validate → parse → import
- **`main.py`** — app entry, account CRUD, backup/restore, tab wiring
- **`theme.py`** — unified P&L color palette
- **`tabs/`** — one `QWidget` per tab, each with `refresh()`
- **`plugins/`** — auto-discovered import plugins (incl. `plugins/contract.py` — the declared `ImportPlugin` Protocol + `ParseResult` shape + accessors that `import_manager`/UI use instead of `hasattr`/`getattr` sniffing; issue #4)
- **`asset_modules/`** — per-asset-type behaviour (columns, dialogs, stats)
- **`chart_providers/`** — price chart backends (incl. `chart_data.py` — headless `ChartData` core: fetch + 401-recovery + cache via `Journal`; `chart_widget.py` renders what it returns)

### Plugin interface (`plugins/`)

The contract is declared in `plugins/contract.py` (the `ImportPlugin` Protocol). A conforming plugin **must** expose: `PLUGIN_NAME`, `DISPLAY_NAME`, `SUPPORTED_EXTENSIONS`, `IMPORT_MODE` (explicit — `contract.IMPORT_MODE_TRADES`/`IMPORT_MODE_EXECUTIONS`, never defaulted), `validate(path) -> (bool, str)`, `parse(path) -> contract.ParseResult(records, balance_events)`, `file_hash(path) -> str`. `file_hash` is normally just `file_hash = contract.default_file_hash` (the shared SHA-256 helper) rather than a re-copied implementation. Optional members (`parse_account_info`, `DEFAULT_ASSET_TYPE`) are reached via contract accessors (`contract.account_info`, `contract.default_asset_type`) — callers never sniff with `hasattr`/`getattr`. Import-mode classification also lives in one place: `contract.is_executions_mode(plugin)` instead of comparing `IMPORT_MODE` to literals. Discovery skips non-conforming modules via `contract.conforms`.

New plugins are auto-discovered — **also add to `--hidden-import` in both build scripts** (and keep `plugins.contract` there).

## Roadmap

All items shipped. No open items.
