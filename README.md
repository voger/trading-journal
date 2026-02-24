# Trading Journal

A desktop trading journal application for stock and forex traders. Track your trades, analyse performance with FIFO lot matching, and review your strategy with detailed statistics.

![Python](https://img.shields.io/badge/Python-3.10+-blue) ![License](https://img.shields.io/badge/License-MIT-green) ![Tests](https://img.shields.io/badge/Tests-483-brightgreen) ![Version](https://img.shields.io/badge/Version-2.5.2-blue)

## Features

- **FIFO Lot Matching Engine** — Automatically matches sells to buys using FIFO ordering, supports fractional shares, multiple round trips, and computes per-lot P&L
- **Multi-Account Sidebar** — Left-panel account switcher; manage separate accounts (stocks, forex) across different brokers and currencies
- **Broker Import** — Import trades from broker statements (Trading212, MT4 supported; extensible plugin system)
- **Analytics Dashboard** — Win rate, profit factor, expectancy, Sharpe / Sortino / Calmar ratios, max drawdown, consecutive win/loss streaks, and breakdowns by instrument, setup, day of week, session, exit reason, direction, and month
- **Accurate Metrics** — All calculations include swap and commission (not just raw profit), matching broker statement totals. Drawdown % anchored to account initial balance.
- **Chart Integration** — Fetch candlestick charts from TwelveData or Yahoo Finance with trade entry/exit markers; supports broker symbol suffixes (`.raw`, `.ecn`, `mini`, etc.)
- **Trade Journal** — Daily journal entries linked to your trades
- **Setup Management** — Define and track your trading setups with example charts and entry/exit rule checklists
- **Watchlist** — Monitor instruments with weekly/daily bias notes and price levels
- **Equity Curve** — Visual equity progression with two modes: Balance (includes deposits/withdrawals) and Cumulative P&L (trade-only, starts at 0)
- **Backup / Restore** — Full database backup to ZIP with one-click restore

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

Your database is created automatically in the platform data directory:
- **Linux**: `~/.local/share/TradingJournal/`
- **macOS**: `~/Library/Application Support/TradingJournal/`
- **Windows**: `%APPDATA%\TradingJournal\`

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

To install a `.desktop` launcher and hicolor icon:
```bash
bash dist/TradingJournal/install.sh
# Uninstall:
bash dist/TradingJournal/install.sh uninstall
```

### Windows

```cmd
venv\Scripts\activate
build_app.bat
```

This creates:
- `dist\TradingJournal\TradingJournal.exe` — the executable
- `dist\TradingJournal_windows.zip` — portable archive (if 7-Zip is installed)

To add a Start Menu shortcut and desktop icon:
```powershell
.\dist\TradingJournal\install.ps1
# Uninstall:
.\dist\TradingJournal\install.ps1 -Uninstall
```

### Build Troubleshooting

| Problem | Solution |
|---------|----------|
| `No module named 'PyQt6'` | Activate the venv **before** running the build script |
| `Hidden import not found` | Run `pip install -r requirements.txt` inside the venv |
| Build is very large | Normal — PyQt6 and matplotlib are large libraries (~200–400 MB) |
| App crashes on start | Check terminal output for the actual error message |

---

## Importing Trades

1. Go to **File → Import Trades…** (or the Import History tab)
2. Select your broker CSV / HTM file
3. The app auto-detects the broker plugin
4. Trades are inserted; FIFO lot matching runs automatically for stocks

### Supported Brokers
- **Trading212** — Full support for detailed statements (stocks & ETFs)
- **MT4** — Detailed statement HTML (forex)
- Additional plugins can be added in the `plugins/` directory — see the plugin system docs in `CLAUDE.md`

---

## Running Tests

```bash
source venv/bin/activate
python -m pytest tests/ -q
```

Current: **483 passed, 42 skipped** (integration tests require real broker CSV / HTM files and are skipped by default).

```bash
# Integration tests (provide your own files)
python -m pytest tests/ -q --real-csv=/path/to/t212.csv
python -m pytest tests/ -q --real-mt4=/path/to/DetailedStatement.htm
```

---

## Project Structure

```
trading-journal/
├── main.py              # Application entry point, font & style setup
├── database.py          # SQLite schema, CRUD, analytics queries
├── fifo_engine.py       # FIFO lot matching engine
├── chart_widget.py      # Candlestick chart widget (mplfinance)
├── dialogs.py           # Trade edit dialog, account dialog, image viewer
├── import_manager.py    # Plugin-based import orchestration
├── backup_manager.py    # Backup / restore to ZIP
├── executions_dialog.py # Execution detail viewer (T212 lot breakdown)
├── theme.py             # Dark theme QSS stylesheet (opt-in)
├── tabs/                # UI tabs: trades, journal, stats, equity, watchlist…
├── plugins/             # Broker import plugins (Trading212, MT4)
├── asset_modules/       # Per-asset-type behaviour (forex, stocks)
├── chart_providers/     # OHLC data providers (TwelveData, Yahoo Finance)
├── tests/               # Pytest test suite (483 tests)
├── build_app.sh         # Linux / macOS PyInstaller build
├── build_app.bat        # Windows PyInstaller build
├── requirements.txt     # Python dependencies
├── icons/               # Application icons (PNG sizes + SVG)
└── install.ps1          # Windows desktop integration script
```

---

## Configuration

- **Database** — Created automatically in the platform data directory (see Quick Start)
- **Chart API Keys** — Set via the 🔑 button in the chart widget; stored in the database, not in files
- **Backups** — File → Backup…; restore from the same menu

---

## Roadmap

Planned features (not yet implemented):

- **Dark mode toggle** — A revised dark palette (deep charcoal / purple-tinted, inspired by modern trading UIs) selectable from the View menu; `theme.py` already contains the stylesheet skeleton
- **Calendar heatmap** — Monthly P&L grid view (green / red cells per day) in the Stats tab; at-a-glance view of trading consistency
- **Unlimited trade list** — Remove the current 2 000-row soft cap; replace with a proper paginator or virtual/lazy row loading so very large accounts are fully browsable
- **Tags** — Surface the existing DB tags structure in the UI: tag trades from the edit dialog, filter by tag in the trades table
- **Setup performance stats** — Per-setup breakdown in the Stats tab: win rate, avg R-multiple, avg duration, number of trades per setup
- **R-multiple distribution** — Histogram of R multiples across all closed trades
- **Time-of-day / day-of-week heatmap** — Bar charts showing performance by session and weekday
- **CSV / ODS export** — Export the visible trade list to a comma-separated or OpenDocument Spreadsheet file

---

## License

MIT License — see [LICENSE](LICENSE) for details.

You are free to use, modify, and distribute this software.
