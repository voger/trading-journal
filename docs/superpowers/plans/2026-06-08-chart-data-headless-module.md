# Headless ChartData Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract a headless `ChartData` core (no PyQt) that owns price fetch, 401-recovery, and DB cache, so `chart_widget.py` is left with rendering only and the fetch path is unit-testable without Qt.

**Architecture:** A new `chart_providers/chart_data.py` holds pure helpers (`compute_window`, `bars_to_json`, `bars_from_json`) and a `ChartData` class whose `fetch()` calls the provider, recovers from auth errors via `key_store`, and caches OHLC through the `Journal` seam (issue #6). `chart_widget` constructs `ChartData(journal)` and calls it; all DB access flows through `journal.save_chart_data(...)`, a new `db/crud.py` function auto-exposed by `Journal.__getattr__`.

**Tech Stack:** Python, PyQt6 (widget only), SQLite via the `Journal` seam, pytest. Run tests inside the venv: `source venv/bin/activate`.

---

## File structure

- **Create** `chart_providers/chart_data.py` — headless fetch/cache core + pure helpers. No PyQt import.
- **Create** `tests/test_chart_data.py` — unit tests with a fake provider over the `journal` fixture. No Qt.
- **Modify** `db/crud.py` — add `save_chart_data(conn, trade_id, json_str)`.
- **Modify** `chart_widget.py` — constructor takes `journal`; `_on_fetch` calls the core; serialization helpers delegate; remove `_cal_days_for_bars`.
- **Modify** `dialogs_trade.py:368` and `tabs/trades_preview.py:100` — pass `journal=` instead of `conn=`.

Baseline test suite: **655 passed, 42 skipped** (`python -m pytest tests/ -q`; offscreen-Qt smoke tests need `QT_QPA_PLATFORM=offscreen`).

---

## Task 1: `crud.save_chart_data` (cache write through the seam)

**Files:**
- Modify: `db/crud.py` (add function near `update_trade`, around line 172)
- Test: `tests/test_chart_data.py` (new file)

- [ ] **Step 1: Write the failing test**

Create `tests/test_chart_data.py` with this content:

```python
"""Tests for the headless ChartData core and its DB cache (issue #5)."""
import json
from datetime import datetime

import pytest

from chart_providers.base import OHLCBar
from chart_providers import key_store
from chart_providers.chart_data import (
    ChartData, ChartDataError, ChartResult,
    compute_window, bars_to_json, bars_from_json,
)


# ── helpers ────────────────────────────────────────────────────────────────

def _make_trade(journal):
    """Insert a minimal valid trade row; return its id."""
    aid = journal.create_account(name='A', broker='B', currency='EUR',
                                 asset_type='stocks')
    iid = journal.get_or_create_instrument('AAPL', instrument_type='stocks')
    return journal.create_trade(account_id=aid, instrument_id=iid,
                                direction='long', entry_date='2025-06-10',
                                entry_price=100.0, position_size=10)


def _bar(day, price=100.0):
    return OHLCBar(timestamp=datetime(2025, 6, day), open=price, high=price + 1,
                   low=price - 1, close=price, volume=1000)


class FakeProvider:
    """Stand-in for a chart provider — no network."""
    PROVIDER_ID = 'fake'

    def __init__(self, bars=None, error=None):
        self.api_key = 'KEY'
        self._bars = bars if bars is not None else []
        self._error = error
        self.normalized = None

    def normalize_symbol(self, symbol, asset_type):
        self.normalized = f'{symbol}:{asset_type}'
        return self.normalized

    def fetch_ohlc(self, sym, start, end, tf):
        if self._error:
            raise self._error
        return self._bars


# ── cache write ────────────────────────────────────────────────────────────

class TestSaveChartData:
    def test_save_chart_data_persists(self, journal):
        tid = _make_trade(journal)
        journal.save_chart_data(tid, '[{"x":1}]')
        row = journal.conn.execute(
            "SELECT chart_data FROM trades WHERE id=?", (tid,)).fetchone()
        assert row['chart_data'] == '[{"x":1}]'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source venv/bin/activate && python -m pytest tests/test_chart_data.py::TestSaveChartData -v`
Expected: collection/import error — `ModuleNotFoundError: No module named 'chart_providers.chart_data'` (the module does not exist yet).

- [ ] **Step 3: Add the crud function**

In `db/crud.py`, immediately after `update_trade` (after line 171), add:

```python
def save_chart_data(conn, trade_id, json_str):
    """Persist cached OHLC JSON for a trade (used by the chart fetch path)."""
    conn.execute("UPDATE trades SET chart_data = ? WHERE id = ?",
                 (json_str, trade_id))
    conn.commit()
```

`Journal.__getattr__` auto-exposes any `conn`-first function in `db.crud`, so this becomes `journal.save_chart_data(trade_id, json_str)` with no edit to `db/journal.py`.

- [ ] **Step 4: Create the module stub so the import resolves**

Create `chart_providers/chart_data.py` with a minimal stub (fleshed out in Task 2/3):

```python
"""Headless chart data core: fetch + 401-recovery + cache. No PyQt."""
```

- [ ] **Step 5: Run test to verify it still fails on the missing names**

Run: `source venv/bin/activate && python -m pytest tests/test_chart_data.py::TestSaveChartData -v`
Expected: still an ImportError — `cannot import name 'ChartData' from 'chart_providers.chart_data'`. (Task 2 defines those names; this task only needs `save_chart_data`, but the shared test-file imports pull in the not-yet-written core. That's fine — Task 2 makes the imports resolve. To verify *just* this task in isolation, run the inline check below.)

- [ ] **Step 6: Verify the crud function in isolation**

Run: `source venv/bin/activate && python -c "
import db.crud as c
print(callable(c.save_chart_data))
import inspect; print(list(inspect.signature(c.save_chart_data).parameters)[0] == 'conn')
"`
Expected output:
```
True
True
```
(The second `True` confirms `Journal` will auto-expose it.)

- [ ] **Step 7: Commit**

```bash
git add db/crud.py chart_providers/chart_data.py tests/test_chart_data.py
git commit -m "feat: add crud.save_chart_data; scaffold headless chart_data module (issue #5)"
```

---

## Task 2: Pure helpers — `compute_window`, `bars_to_json`, `bars_from_json`

**Files:**
- Modify: `chart_providers/chart_data.py`
- Test: `tests/test_chart_data.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_chart_data.py`:

```python
class TestPureHelpers:
    def test_compute_window_caps_at_now(self):
        entry = datetime(2025, 6, 10)
        now = datetime(2025, 6, 15)
        start, end, capped = compute_window(entry, None, '1d', 50, 100, now=now)
        assert capped is True
        assert end == now
        assert start < entry

    def test_compute_window_no_cap(self):
        entry = datetime(2025, 6, 10)
        now = datetime(2030, 1, 1)
        start, end, capped = compute_window(entry, None, '1d', 50, 10, now=now)
        assert capped is False
        assert end < now
        assert start < entry

    def test_compute_window_uses_exit_as_ref(self):
        entry = datetime(2025, 6, 10)
        exit_dt = datetime(2025, 6, 20)
        now = datetime(2030, 1, 1)
        _, end_with_exit, _ = compute_window(entry, exit_dt, '1d', 50, 10, now=now)
        _, end_no_exit, _ = compute_window(entry, None, '1d', 50, 10, now=now)
        assert end_with_exit > end_no_exit

    def test_bars_json_roundtrip(self):
        bars = [_bar(10), _bar(11, 105.0)]
        restored = bars_from_json(bars_to_json(bars))
        assert len(restored) == 2
        assert restored[1].close == 105.0
        assert restored[0].timestamp == datetime(2025, 6, 10)
        assert restored[0].volume == 1000

    def test_bars_to_json_empty(self):
        assert bars_to_json([]) is None

    def test_bars_from_json_empty(self):
        assert bars_from_json(None) == []
        assert bars_from_json('') == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_chart_data.py::TestPureHelpers -v`
Expected: ImportError — `cannot import name 'compute_window' from 'chart_providers.chart_data'`.

- [ ] **Step 3: Implement the helpers**

Replace the entire contents of `chart_providers/chart_data.py` with:

```python
"""Headless chart data core: fetch + 401-recovery + cache. No PyQt."""
import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from chart_providers.base import OHLCBar
from chart_providers import key_store


def _cal_days_for_bars(tf, n):
    """Approximate calendar days needed to contain n bars of a given timeframe."""
    if tf == '1wk':
        return n * 7 + 3
    elif tf == '1d':
        return int(n * 7 / 5) + 3
    elif tf == '4h':
        return int(max(1, n / 6) * 7 / 5) + 3
    elif tf == '1h':
        return int(max(1, n / 22) * 7 / 5) + 3
    return n + 5


def compute_window(entry_dt, exit_dt, tf, bars_before, bars_after, now=None):
    """Return (start, end, capped) for the fetch window.

    `now` is injectable for testing; end is clamped to it (capped=True) when the
    requested window runs past the present.
    """
    if now is None:
        now = datetime.now()
    start = entry_dt - timedelta(days=_cal_days_for_bars(tf, bars_before))
    ref = exit_dt or entry_dt
    end = ref + timedelta(days=_cal_days_for_bars(tf, bars_after))
    capped = end > now
    if capped:
        end = now
    return start, end, capped


def bars_to_json(bars):
    """Serialize OHLCBars to the JSON string stored in trades.chart_data."""
    if not bars:
        return None
    return json.dumps([{'timestamp': b.timestamp.isoformat(),
                        'open': b.open, 'high': b.high, 'low': b.low,
                        'close': b.close, 'volume': b.volume}
                       for b in bars])


def bars_from_json(json_str):
    """Parse the trades.chart_data JSON string back into OHLCBars."""
    if not json_str:
        return []
    return [OHLCBar(timestamp=datetime.fromisoformat(d['timestamp']),
                    open=d['open'], high=d['high'], low=d['low'],
                    close=d['close'], volume=d.get('volume', 0))
            for d in json.loads(json_str)]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source venv/bin/activate && python -m pytest tests/test_chart_data.py::TestPureHelpers -v`
Expected: all `TestPureHelpers` tests PASS. (`TestSaveChartData` now also imports cleanly — run `tests/test_chart_data.py::TestSaveChartData` too; it should PASS.)

- [ ] **Step 5: Commit**

```bash
git add chart_providers/chart_data.py tests/test_chart_data.py
git commit -m "feat: add chart_data pure helpers (compute_window, bars json) (issue #5)"
```

---

## Task 3: `ChartData` class — fetch + 401-recovery + cache

**Files:**
- Modify: `chart_providers/chart_data.py`
- Test: `tests/test_chart_data.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_chart_data.py`:

```python
class TestChartDataFetch:
    def test_happy_path_returns_result(self, journal):
        tid = _make_trade(journal)
        bars = [_bar(10), _bar(11)]
        prov = FakeProvider(bars=bars)
        core = ChartData(journal)
        result = core.fetch(prov, 'AAPL', 'stocks',
                            datetime(2025, 6, 10), datetime(2025, 6, 11),
                            '1d', 50, 10, trade_id=tid)
        assert isinstance(result, ChartResult)
        assert result.bars == bars
        assert result.normalized_symbol == 'AAPL:stocks'
        assert result.capped is False  # 2025 window, run far later

    def test_writes_cache_to_db(self, journal):
        tid = _make_trade(journal)
        bars = [_bar(10), _bar(11)]
        core = ChartData(journal)
        core.fetch(FakeProvider(bars=bars), 'AAPL', 'stocks',
                   datetime(2025, 6, 10), None, '1d', 50, 10, trade_id=tid)
        row = journal.conn.execute(
            "SELECT chart_data FROM trades WHERE id=?", (tid,)).fetchone()
        restored = bars_from_json(row['chart_data'])
        assert len(restored) == 2
        assert restored[0].close == 100.0

    def test_no_trade_id_skips_cache(self, journal):
        core = ChartData(journal)
        result = core.fetch(FakeProvider(bars=[_bar(10)]), 'AAPL', 'stocks',
                            datetime(2025, 6, 10), None, '1d', 50, 10)
        assert len(result.bars) == 1  # no crash without a trade_id

    def test_empty_result_raises(self, journal):
        core = ChartData(journal)
        with pytest.raises(ChartDataError):
            core.fetch(FakeProvider(bars=[]), 'AAPL', 'stocks',
                       datetime(2025, 6, 10), None, '1d', 50, 10)

    def test_401_clears_key_and_reraises(self, journal):
        key_store.save(journal.conn, 'fake', 'SECRET')
        prov = FakeProvider(error=ValueError('Invalid API key (401)'))
        core = ChartData(journal)
        with pytest.raises(ValueError):
            core.fetch(prov, 'AAPL', 'stocks',
                       datetime(2025, 6, 10), None, '1d', 50, 10)
        assert not key_store.get(journal.conn, 'fake')
        assert prov.api_key == ''

    def test_non_auth_error_keeps_key(self, journal):
        key_store.save(journal.conn, 'fake', 'SECRET')
        prov = FakeProvider(error=RuntimeError('network down'))
        core = ChartData(journal)
        with pytest.raises(RuntimeError):
            core.fetch(prov, 'AAPL', 'stocks',
                       datetime(2025, 6, 10), None, '1d', 50, 10)
        assert key_store.get(journal.conn, 'fake') == 'SECRET'
        assert prov.api_key == 'KEY'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_chart_data.py::TestChartDataFetch -v`
Expected: ImportError — `cannot import name 'ChartData'` (and `ChartResult`, `ChartDataError`).

- [ ] **Step 3: Implement the class**

Append to `chart_providers/chart_data.py`:

```python
@dataclass
class ChartResult:
    bars: list              # list[OHLCBar]
    normalized_symbol: str
    capped: bool            # end was clamped to now


class ChartDataError(Exception):
    """Fetch produced no usable data."""


def _is_auth_error(e):
    s = str(e)
    return 'Invalid API key' in s or '401' in s


class ChartData:
    """Headless fetch + 401-recovery + cache. Reaches the DB via a Journal."""

    def __init__(self, journal):
        self.journal = journal

    def fetch(self, provider, symbol, asset_type, entry_dt, exit_dt,
              tf, bars_before, bars_after, trade_id=None) -> 'ChartResult':
        start, end, capped = compute_window(
            entry_dt, exit_dt, tf, bars_before, bars_after)
        norm = provider.normalize_symbol(symbol, asset_type)
        try:
            bars = provider.fetch_ohlc(norm, start, end, tf)
        except Exception as e:
            if _is_auth_error(e):
                key_store.clear(self.journal.conn, provider.PROVIDER_ID)
                if hasattr(provider, 'api_key'):
                    provider.api_key = ''
            raise
        if not bars:
            raise ChartDataError("No data returned")
        if trade_id is not None:
            self.journal.save_chart_data(trade_id, bars_to_json(bars))
        return ChartResult(bars=bars, normalized_symbol=norm, capped=capped)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source venv/bin/activate && python -m pytest tests/test_chart_data.py -v`
Expected: every test in the file PASSES (TestSaveChartData, TestPureHelpers, TestChartDataFetch).

- [ ] **Step 5: Commit**

```bash
git add chart_providers/chart_data.py tests/test_chart_data.py
git commit -m "feat: add ChartData core (fetch + 401-recovery + cache) (issue #5)"
```

---

## Task 4: Rewire `chart_widget.py` to render only

**Files:**
- Modify: `chart_widget.py` (imports, `__init__`, `_on_fetch`, `get_cached_data_json`, `load_cached_data`; remove `_cal_days_for_bars`)
- Modify: `dialogs_trade.py:368`
- Modify: `tabs/trades_preview.py:100`
- Test: existing `tests/test_tabs_smoke.py` (offscreen-Qt) + full suite

- [ ] **Step 1: Update imports and remove the moved helper**

In `chart_widget.py`, add to the `chart_providers` imports block (after line 22):

```python
from chart_providers.chart_data import ChartData, bars_to_json, bars_from_json
```

Then DELETE the `_cal_days_for_bars` function (current lines 26-36) — it now lives in `chart_data.py`.

- [ ] **Step 2: Update the constructor**

Replace the signature and the first lines of `__init__` (current lines 53-57):

```python
    def __init__(self, parent=None, journal=None, trade=None, asset_type='forex'):
        super().__init__(parent)
        self.journal = journal
        self.conn = journal.conn if journal is not None else None
        self._core = ChartData(journal) if journal is not None else None
        self.trade = trade
        self.asset_type = asset_type
```

(`self.conn` is retained because the key-prompt/manage dialogs `_ensure_api_key`, `_prompt_api_key`, `_on_manage_key` still call `key_store.get/save/clear(self.conn, ...)` — leave those methods unchanged.)

- [ ] **Step 3: Replace `_on_fetch` with the core-delegating version**

Replace the whole `_on_fetch` method (current lines 233-310) with:

```python
    def _on_fetch(self):
        if not self.trade:
            QMessageBox.warning(self, "No Trade", "Save the trade first."); return
        pid = self.provider_combo.currentData()
        provider = get_provider(pid)
        if not provider:
            QMessageBox.warning(self, "No Provider", "No chart provider available."); return
        if not self._ensure_api_key(provider):
            return

        symbol = self.trade.get('symbol') or self.trade.get('instrument_symbol', '')
        entry_str = self.trade.get('entry_date', '')
        if not symbol or not entry_str:
            QMessageBox.warning(self, "Missing", "Trade needs symbol and entry date."); return

        try: entry_dt = datetime.strptime(entry_str[:10], '%Y-%m-%d')
        except ValueError: QMessageBox.warning(self, "Bad Date", f"Cannot parse: {entry_str}"); return

        exit_dt = None
        exit_str = self.trade.get('exit_date', '')
        if exit_str:
            try: exit_dt = datetime.strptime(exit_str[:10], '%Y-%m-%d')
            except ValueError: pass

        tf = self.tf_combo.currentData() or '1d'
        trade_id = self.trade.get('id') if isinstance(self.trade, dict) else None

        self.fetch_btn.setEnabled(False); self.fetch_btn.setText("Fetching...")
        self.status_label.setText(f"Fetching {symbol}..."); QApplication.processEvents()

        try:
            result = self._core.fetch(
                provider, symbol, self.asset_type, entry_dt, exit_dt, tf,
                self.bars_before.value(), self.bars_after.value(), trade_id=trade_id)
            bars = result.bars
            self._cached_data = bars
            self._last_symbol = symbol; self._last_tf = tf
            canvas, fig = self._render(bars, symbol, tf, entry_dt, exit_dt, (10, 5))
            self._swap_canvas(canvas)
            self.popout_btn.setEnabled(True)

            import matplotlib.pyplot as plt
            plt.close(fig)

            if isinstance(self.trade, dict) and trade_id:
                self.trade['chart_data'] = bars_to_json(bars)

            status = (f"{len(bars)} bars  {result.normalized_symbol} ({tf})  "
                      f"{bars[0].timestamp:%Y-%m-%d} → {bars[-1].timestamp:%Y-%m-%d}")
            if result.capped:
                status += "  (capped at today)"
            self.status_label.setText(status)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            self.status_label.setText(f"Error: {e}")
        finally:
            self.fetch_btn.setEnabled(True); self.fetch_btn.setText("Fetch Chart")
```

The 401-recovery, DB cache write, and window math are gone from here — the core owns them.

- [ ] **Step 4: Delegate the serialization helpers**

Replace `get_cached_data_json` (current lines 528-533):

```python
    def get_cached_data_json(self):
        return bars_to_json(self._cached_data)
```

Replace the body of `load_cached_data` (current lines 535-556) so parsing comes from the core, keeping the render/state behaviour:

```python
    def load_cached_data(self, json_str):
        if not json_str: return
        try:
            self._cached_data = bars_from_json(json_str)
            if self._cached_data and self.trade:
                entry_dt, exit_dt = self._parse_dates()
                sym = self.trade.get('symbol', '?')
                self._last_symbol = sym; self._last_tf = '1d'
                canvas, fig = self._render(self._cached_data, sym, '1d',
                                           entry_dt, exit_dt, (10, 5))
                self._swap_canvas(canvas)
                self.popout_btn.setEnabled(True)
                import matplotlib.pyplot as plt
                plt.close(fig)
                self.status_label.setText(f"Cached chart ({len(self._cached_data)} bars)")
        except Exception as e:
            self.status_label.setText(f"Cache load failed: {e}")
```

(`from chart_providers.base import OHLCBar` inside the old body is removed — `bars_from_json` builds the bars now.)

- [ ] **Step 5: Update the two construction sites**

In `dialogs_trade.py` line 368, change:

```python
        self.chart_widget = TradeChartWidget(self, conn=self.journal.conn, trade=None, asset_type=asset_type)
```
to:
```python
        self.chart_widget = TradeChartWidget(self, journal=self.journal, trade=None, asset_type=asset_type)
```

In `tabs/trades_preview.py` line 100, change:

```python
        self.pv_chart = TradeChartWidget(parent=outer, conn=self.journal.conn)
```
to:
```python
        self.pv_chart = TradeChartWidget(parent=outer, journal=self.journal)
```

- [ ] **Step 6: Run the offscreen smoke tests**

Run: `source venv/bin/activate && QT_QPA_PLATFORM=offscreen python -m pytest tests/test_tabs_smoke.py -v`
Expected: all PASS — these construct `ExecutionsDialog`/`TradeChartsDialog` through the `Journal`, which build the chart widget with the new `journal=` wiring.

- [ ] **Step 7: Confirm no stray `conn=` construction and no leftover helper in the widget**

Run: `source venv/bin/activate && grep -rn "TradeChartWidget(.*conn=" --include="*.py" . ; grep -n "_cal_days_for_bars" chart_widget.py`
Expected: no output from either grep. (The `_cal_days_for_bars` definition now lives only in `chart_providers/chart_data.py`; it must no longer appear in `chart_widget.py`, and no caller constructs the widget with `conn=`.)

- [ ] **Step 8: Run the full suite**

Run: `source venv/bin/activate && QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q`
Expected: green — baseline **655 passed, 42 skipped** plus the new `tests/test_chart_data.py` cases (≈14 more passed). No failures.

- [ ] **Step 9: Commit**

```bash
git add chart_widget.py dialogs_trade.py tabs/trades_preview.py
git commit -m "refactor: chart_widget delegates fetch/cache to ChartData core (issue #5)"
```

---

## Task 5: Docs + issue wrap-up

**Files:**
- Modify: `CLAUDE.md` (architecture overview)
- Modify: `/home/voger/.claude/projects/-home-voger-projects-trading-journal/memory/MEMORY.md` (module structure)

- [ ] **Step 1: Note the new module in CLAUDE.md**

In `CLAUDE.md`, under "Architecture overview", add a bullet after the `chart_providers/` mention:

```markdown
- **`chart_providers/chart_data.py`** — headless `ChartData` core (fetch + 401-recovery + cache via `Journal`); `chart_widget.py` renders what it returns (issue #5)
```

- [ ] **Step 2: Update MEMORY.md module structure**

Add under the module structure list:

```markdown
- `chart_providers/chart_data.py` — headless `ChartData` (fetch/401-recovery/cache via Journal); `chart_widget` renders only (issue #5)
```

Update the test baseline line to the new count printed by Task 4 Step 8.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document headless ChartData module (issue #5)"
```

- [ ] **Step 4: Push and open the PR**

```bash
git push -u origin refactor/chart-data-headless-module
gh pr create --fill --base main \
  --title "Headless ChartData module: split fetch/cache out of chart_widget (issue #5)" \
  --body "Closes #5. Extracts a headless \`ChartData\` core (fetch + 401-recovery + cache via the Journal seam); \`chart_widget\` is rendering-only. New no-Qt tests cover happy path, cache write, 401 recovery, empty result, and the pure helpers."
```

---

## Acceptance criteria (issue #5)

- [ ] A headless module owns fetch + cache (no PyQt import) — `chart_providers/chart_data.py` (Tasks 2-3).
- [ ] `chart_widget` holds rendering only; calls the core for data — Task 4.
- [ ] Core tested without Qt: happy path, 401 recovery, cache write — `tests/test_chart_data.py` (Tasks 1-3).
- [ ] Pop-out path reuses the same core (no duplicate fetch) — `_on_popout` renders from `self._cached_data`; unchanged, no second fetch.
- [ ] Full suite green — Task 4 Step 8.
