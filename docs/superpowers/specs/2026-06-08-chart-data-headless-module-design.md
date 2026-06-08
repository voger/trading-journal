# Design: headless `ChartData` core (issue #5)

**Issue:** #5 — Architecture #4: Split a headless fetch/cache module out of `chart_widget`
**Date:** 2026-06-08
**Depends on:** #1 (KeyStore — CLOSED), #6 (Journal seam — MERGED)

## Problem

`chart_widget.py` `_on_fetch` interleaves four unrelated jobs in one method: compute
the date window, fetch prices over the network, recover from a 401 (bad API key),
write the OHLC cache to the DB, then render with mplfinance/Qt. None of the
fetch/cache path is testable without a Qt event loop, and rendering changes risk
breaking fetch logic and vice-versa. The 577-line widget has zero tests.

## Goal

Extract a **headless** `ChartData` core (no PyQt import) that owns fetch + 401-recovery
+ cache. The widget renders what the core returns. The core is tested with a fake
provider over the existing `journal` fixture — no Qt.

## Persistence decision

The core reaches the database **through the `Journal` seam** (issue #6), not a raw
`conn`. This continues the direction #6 established (one front door to the DB) and
makes the cache-write test trivial via the existing `journal` fixture. The only cost
is one small new function in `db/crud.py`. The 401 key-clear keeps using
`key_store.clear(journal.conn, pid)` because `key_store` deliberately stayed
conn-based in #6; the core matches that decision rather than wrapping it in Journal.

## Architecture

### 1. New module — `chart_providers/chart_data.py` (no PyQt)

Sits beside `key_store.py` and `base.py`; imports `OHLCBar` and `key_store`.

**Pure helpers (free functions, no state):**

- `compute_window(entry_dt, exit_dt, tf, bars_before, bars_after, now=None) -> (start, end, capped)`
  — the date math + `_cal_days_for_bars` + cap-at-now currently inline in `_on_fetch`.
  `now` is injectable so the cap-at-today behaviour is testable.
- `bars_to_json(bars) -> str` and `bars_from_json(json_str) -> list[OHLCBar]`
  — the serialization currently in `get_cached_data_json` / `load_cached_data`.

`_cal_days_for_bars` (currently a module-level helper in `chart_widget.py`) moves
into `chart_data.py` since `compute_window` is its only consumer.

**The core class:**

```python
@dataclass
class ChartResult:
    bars: list              # list[OHLCBar]
    normalized_symbol: str
    capped: bool            # end was clamped to now

class ChartDataError(Exception):
    """Fetch produced no usable data."""

class ChartData:
    def __init__(self, journal):
        self.journal = journal

    def fetch(self, provider, symbol, asset_type, entry_dt, exit_dt,
              tf, bars_before, bars_after, trade_id=None) -> ChartResult:
        start, end, capped = compute_window(
            entry_dt, exit_dt, tf, bars_before, bars_after)
        norm = provider.normalize_symbol(symbol, asset_type)
        try:
            bars = provider.fetch_ohlc(norm, start, end, tf)
        except Exception as e:
            if _is_auth_error(e):                       # 'Invalid API key' / '401'
                key_store.clear(self.journal.conn, provider.PROVIDER_ID)
                provider.api_key = ''
            raise
        if not bars:
            raise ChartDataError("No data returned")
        if trade_id is not None:
            self.journal.save_chart_data(trade_id, bars_to_json(bars))   # cache
        return ChartResult(bars=bars, normalized_symbol=norm, capped=capped)
```

`_is_auth_error(e)` centralizes the existing string check
(`'Invalid API key' in str(e) or '401' in str(e)`).

### 2. Journal + DB layer

One new function in `db/crud.py`, auto-exposed by the `Journal` seam (no edit to
`journal.py` — its `__getattr__` surfaces any conn-first function in
`crud`/`analytics`/`queries`):

```python
def save_chart_data(conn, trade_id, json_str):
    conn.execute("UPDATE trades SET chart_data = ? WHERE id = ?", (json_str, trade_id))
    conn.commit()
```

This replaces the raw `self.conn.execute("UPDATE trades SET chart_data ...")` block
in `_on_fetch`.

### 3. Widget changes — `chart_widget.py` (rendering only)

- **Constructor** takes `journal` instead of `conn`. Keeps `self.conn = journal.conn`
  for the existing key-prompt/manage dialogs (`_ensure_api_key`, `_prompt_api_key`,
  `_on_manage_key` — pure Qt, unchanged) and builds `self._core = ChartData(journal)`.
- **Call sites** switch `conn=self.journal.conn` → `journal=self.journal`:
  - `dialogs_trade.py:368`
  - `tabs/trades_preview.py:100`
- **`_on_fetch`** shrinks to: read combos/spinboxes → `_ensure_api_key` (dialog) →
  `result = self._core.fetch(...)` in try/except → on success: `_render` +
  `_swap_canvas` + set `self.trade['chart_data']` (in-memory) + status string
  (incl. "capped at today" when `result.capped`); on `ChartDataError`/other:
  `QMessageBox.critical` + status. Window math, fetch, 401-clear, and DB write all
  move into the core.
- **`get_cached_data_json` / `load_cached_data`** delegate to `bars_to_json` /
  `bars_from_json` (the parsing/serialization logic moves to the core; these become
  thin wrappers that keep updating widget state — `self._cached_data`, render).
- **`_render`, `_swap_canvas`, `_parse_dates`, `_find_idx`, `refresh_theme`** stay
  as-is (pure rendering / Qt).
- **`_on_popout`** unchanged — already renders from `self._cached_data` with no second
  fetch, satisfying "pop-out reuses the same core (no duplicate fetch)".

## Data flow (fetch)

```
user clicks Fetch
  -> widget reads provider/tf/bars-before/after from combos & spinboxes (Qt)
  -> widget._ensure_api_key(provider)            # Qt dialog if key missing
  -> result = core.fetch(provider, symbol, asset_type, entry, exit, tf,
                         before, after, trade_id)
        core.compute_window(...)                 # pure
        provider.normalize_symbol / fetch_ohlc   # network
        on 401: key_store.clear(journal.conn,…)  # recovery, then re-raise
        journal.save_chart_data(trade_id, json)  # cache via seam
  -> widget._render(result.bars, …) + _swap_canvas + status   # Qt
```

## Error handling

- Empty bars → `ChartDataError("No data returned")`; widget shows it via `QMessageBox`.
- Auth error (401 / "Invalid API key") → core clears the stored key and resets
  `provider.api_key`, then re-raises so the widget reports it. Next fetch re-prompts.
- Any other provider/network exception propagates unchanged; widget catches and
  displays. The core never imports Qt and never shows dialogs.

## Testing — `tests/test_chart_data.py` (no Qt)

Drive the core with a **fake provider** — a tiny object exposing `PROVIDER_ID`,
`api_key`, `normalize_symbol(symbol, asset_type)`, `fetch_ohlc(sym, start, end, tf)`
— over the existing `journal` fixture:

- **happy path** — returns bars; `ChartResult.normalized_symbol` and `capped` correct.
- **cache write** — after `fetch(..., trade_id=X)`, the trade row's `chart_data`
  round-trips via `bars_from_json`.
- **401 recovery** — fake provider raises an `Invalid API key` error → key cleared
  from `key_store`, `provider.api_key == ''`, exception propagates.
- **empty result** — `[]` → `ChartDataError`.
- **pure units** — `compute_window` (cap-at-now via injected `now`; start/end offsets)
  and `bars_to_json` / `bars_from_json` round-trip.

Existing offscreen-Qt smoke tests for the chart dialogs keep passing; the constructor
signature change is internal and both call sites are updated.

## Build sequence

1. `crud.save_chart_data` + test → green.
2. `chart_providers/chart_data.py` core (helpers + class) + `tests/test_chart_data.py`
   → green.
3. Rewire `chart_widget.py` (constructor, `_on_fetch`, serialization wrappers) and the
   two call sites.
4. Full suite green (baseline 655 passed / 42 skipped + new tests).

## Acceptance criteria (from issue #5)

- [ ] A headless module owns fetch + cache (no PyQt import).
- [ ] `chart_widget` holds rendering only; calls the core for data.
- [ ] Core tested without Qt: happy path, 401 recovery, cache write — via a fake provider.
- [ ] Pop-out path reuses the same core (no duplicate fetch).
- [ ] Full suite green.

## Out of scope

- No change to `_render` internals or chart appearance.
- No change to providers (`twelvedata_provider`, `yfinance_provider`) or `key_store`'s
  conn-based signature.
- No change to the key-prompt/manage dialogs beyond the constructor wiring.
