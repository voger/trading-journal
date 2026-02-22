# Trading Journal

A desktop trading journal application for stock and forex traders. Track your trades, analyze performance with FIFO lot matching, and review your strategy with detailed statistics.

![Python](https://img.shields.io/badge/Python-3.10+-blue) ![License](https://img.shields.io/badge/License-MIT-green) ![Tests](https://img.shields.io/badge/Tests-425-brightgreen)

## Features

- **FIFO Lot Matching Engine** — Automatically matches sells to buys using FIFO ordering, supports fractional shares, multiple round trips, and computes per-lot P&L
- **Multi-Account** — Manage separate accounts (stocks, forex) with different brokers and currencies
- **CSV Import** — Import trades from broker statements (Trading212 supported, extensible plugin system)
- **Analytics Dashboard** — Win rate, profit factor, expectancy, Sharpe ratio, max drawdown, consecutive win/loss streaks, and breakdowns by instrument, setup, day of week, session, exit reason, direction, and month
- **Chart Integration** — Fetch candlestick charts from TwelveData or Yahoo Finance with trade entry/exit markers
- **Trade Journal** — Daily journal entries with linked trades
- **Setup Management** — Define and track your trading setups with example charts
- **Watchlist** — Monitor instruments with weekly/daily bias notes
- **Equity Curve** — Visual equity progression over time
- **Editable Formulas** — Customize how performance metrics are calculated
- **Backup/Restore** — Full database backup to ZIP with one-click restore

## Screenshots

_Coming soon_

---

## Quick Start (Run from Source)

### Prerequisites
- Python 3.10 or newer
- pip

### 1. Clone the repository
```bash
git clone https://github.com/YOUR_USERNAME/trading-journal.git
cd trading-journal
```

### 2. Create a virtual environment
```bash
# Linux / macOS
python3 -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the application
```bash
python main.py
```

Your database (`trading_journal.db`) is created automatically in the project folder.

---

## Building Standalone Executables

You can build a self-contained executable that doesn't require Python installed.

### Linux / macOS

```bash
source venv/bin/activate
bash build_app.sh
```

This creates:
- `dist/TradingJournal/TradingJournal` — the executable
- `dist/TradingJournal_linux.tar.gz` — portable archive

Run it:
```bash
./dist/TradingJournal/TradingJournal
```

### Windows

```cmd
venv\Scripts\activate
build_app.bat
```

This creates:
- `dist\TradingJournal\TradingJournal.exe` — the executable
- `dist\TradingJournal_windows.zip` — portable archive (if 7-Zip is installed)

Run it:
```cmd
dist\TradingJournal\TradingJournal.exe
```

### Build Troubleshooting

| Problem | Solution |
|---------|----------|
| `No module named 'PyQt6'` | Make sure you activated the venv **before** running the build script |
| `Hidden import not found` | Run `pip install -r requirements.txt` inside the venv |
| Build is very large | Normal — PyQt6 and matplotlib are large libraries (~200-400MB) |
| App crashes on start | Check the terminal output for the actual error message |

---

## Importing Trades

1. Click **Import...** in the toolbar (or File → Import Trades)
2. Select your broker CSV file
3. The app auto-detects the broker plugin and can create an account from the statement
4. Trades are imported, FIFO lot matching runs automatically

### Supported Brokers
- **Trading212** — Full support for detailed statements (stocks)
- More plugins can be added in the `plugins/` directory

---

## Running Tests

```bash
source venv/bin/activate
python -m pytest tests/ -q
```

Current: **425 test functions** (401 pass, 24 skipped for integration tests requiring real CSV data).

---

## Project Structure

```
trading_journal/
├── main.py              # Application entry point
├── database.py          # SQLite schema, CRUD, analytics
├── fifo_engine.py       # FIFO lot matching engine + audit
├── chart_widget.py      # Candlestick chart (mplfinance)
├── dialogs.py           # Trade edit dialog, account dialog
├── import_manager.py    # Plugin-based CSV import system
├── backup_manager.py    # Backup/restore to ZIP
├── tabs/                # UI tabs (trades, journal, stats, etc.)
├── plugins/             # Broker import plugins
├── asset_modules/       # Asset-type logic (forex, stocks)
├── chart_providers/     # OHLC data providers (TwelveData, Yahoo)
├── tests/               # Pytest test suite
├── build_app.sh         # Linux/macOS build script
├── build_app.bat        # Windows build script
├── requirements.txt     # Python dependencies
├── icons/               # Application icons (PNG sizes + SVG)
└── install.ps1          # Windows desktop integration script
```

---

## Configuration

- **Database**: `trading_journal.db` is created in the application folder
- **Chart API Keys**: Set via the chart widget dropdown in the trade edit dialog
- **Backups**: Stored in `~/.trading_journal/backups/` (or platform equivalent)

---

## License

MIT License — see [LICENSE](LICENSE) for details.

You are free to use, modify, and distribute this software.
