# UI skill

Reference for UI architecture, theming conventions, and known design decisions.

## Tabs (`tabs/`)

Each tab is a `QWidget` with `refresh()`, receives `(conn, get_account_id_fn, status_fn)`. Tabs communicate via `MainWindow` signals (`data_changed` → `_on_trades_changed`, `_on_setups_changed`). No shared state except the SQLite connection.

- `StatsTab` has inner sub-tabs; widgets in `stats_widgets.py`, formula editor in `stats_formula.py`, calendar heatmap in `stats_calendar.py`.
- `TradesTab` uses mixins: `trades_preview.py`, `trades_actions.py`, `trades_widgets.py`.
- `dialogs.py` is a shim; real classes in `dialogs_widgets.py`, `dialogs_account.py`, `dialogs_trade.py`, `dialogs_setup.py`.

## Asset modules (`asset_modules/`)

`AssetModule` subclasses define per-asset-type behaviour (table columns, trade dialog fields, stats HTML). Registered in `asset_modules/__init__.py`. Selected at runtime via `get_module(account.asset_type)`.

## Chart providers (`chart_providers/`)

Subclasses registered in `chart_providers/__init__.py`. API keys stored in `app_settings` DB table. `yfinance_provider.py` uses `auto_adjust=False` (raw/unadjusted prices to match recorded trade prices).

## Theming (`theme.py`)

- **Unified P&L palette** — `pos_color()`, `neg_color()`, `neu_color()`, `pnl_color(val)` return theme-aware hex strings. Use these everywhere for P&L coloring (HTML panels, `QLabel` rich text, `QColor` for table cells). Never hardcode `#008200`/`#c80000`/`QColor(0,130,0)` etc.
- Dark palette: muted `#6bbc9a` / `#d97580`. Light palette: darker `#1e7a4c` / `#b53b3b` for contrast on white.
- `is_dark()` — only use for non-P&L theme differences (backgrounds, borders, badge colors).
- Direction badges (▲ LONG / ▼ SHORT) and status badges (WIN/LOSS) keep bright fixed backgrounds — they are not P&L indicators.
- ODS export colors are spreadsheet colors (external app, white background) — do not use dark-mode palette there.

## Intentional design decisions (do not change)

- **Equity Curve requires a specific account** — "All Accounts" shows a prompt by design. No combined multi-account curve.
- **Watchlist and Journal clear on "All Accounts"** — items are always account-scoped.
- **`dates.insert(0, dates[0])` in `equity.py`** — intentional anchor so `balances[0]` aligns with initial balance on step plots.
- **`_saving` flag in `watchlist.py._on_save()` uses `try/finally`** — intentional, resets even on exception.
- **Font embedding was tried and reverted** — loading via `QFontDatabase` bypasses OS sub-pixel rendering (FreeType/ClearType), producing fuzzy text. Not fixable without a custom style engine.
- **Splitter initial sizing on Windows is a known issue** — proportions wrong on first launch, can be dragged. No reliable fix found.
- **QCompleter**: `setModel()` must be called *after* `setFilterMode()` — passing model to constructor before configuring filter silently reverts `MatchContains` to `MatchStartsWith`.
- **Calendar `_make_cell()` dark mode** — intensity-ramped near-black base → vivid green/red. Light mode uses near-white base. Do not unify; they are intentionally different ramps.
- **`_overview_css()` in `stats.py`** — called on every `refresh()` by design; generates dynamic CSS so theme changes are picked up immediately. Not a static constant.
