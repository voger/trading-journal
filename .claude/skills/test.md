# Test skill

Run the trading journal test suite.

## Commands

```bash
source venv/bin/activate

# Full suite
python -m pytest tests/ -q

# Single test
python -m pytest tests/test_fifo_engine.py::TestFIFOEngine::test_basic_buy_sell -q

# Integration tests (skipped unless files provided)
python -m pytest tests/ -q --real-csv=/home/voger/VMSHARED/from_2025-05-22_to_2026-02-15_MTc3MTE1NTA4MjgyNg.csv
python -m pytest tests/ -q --real-mt4=/home/voger/VMSHARED/DetailedStatement.htm
```

## Test conventions

- Fixtures in `tests/conftest.py`: `db_path`, `conn`, `stock_account`, `forex_account`, `sample_t212_csv`.
- Tests never import PyQt6 — all UI code is excluded from the test surface.
- Baseline: **614 passed, 42 skipped**.
