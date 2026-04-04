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

- **`database.py`** — star-import shim; real code in `db/`
- **`fifo_engine.py`** — FIFO matching for stocks (forex bypasses it)
- **`import_manager.py`** — plugin selection → validate → parse → import
- **`main.py`** — app entry, account CRUD, backup/restore, tab wiring
- **`theme.py`** — unified P&L color palette
- **`tabs/`** — one `QWidget` per tab, each with `refresh()`
- **`plugins/`** — auto-discovered import plugins
- **`asset_modules/`** — per-asset-type behaviour (columns, dialogs, stats)
- **`chart_providers/`** — price chart backends

### Plugin interface (`plugins/`)

Must expose: `PLUGIN_NAME`, `DISPLAY_NAME`, `SUPPORTED_EXTENSIONS`, `IMPORT_MODE` (`'trades'` or `'executions'`), `validate(path) -> (bool, str)`, `parse(path) -> list | (list, list)`, `file_hash(path) -> str`.

New plugins are auto-discovered — **also add to `--hidden-import` in both build scripts**.

## Roadmap

All items shipped. No open items.
