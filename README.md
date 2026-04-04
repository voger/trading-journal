# Trading Journal

A desktop trading journal application for stock and forex traders. Track your trades, analyse performance with FIFO lot matching, and review your strategy with detailed statistics.

![Python](https://img.shields.io/badge/Python-3.10+-blue) ![License](https://img.shields.io/badge/License-MIT-green) ![Tests](https://img.shields.io/badge/Tests-609-brightgreen) ![Version](https://img.shields.io/badge/Version-3.3.0-blue)

## Download

Pre-built binaries are available on the [Releases page](https://github.com/voger/trading-journal/releases) — no Python required.

| Platform | Installer | Portable archive |
|----------|-----------|-----------------|
| Linux (x86_64) | `TradingJournal.AppImage` | `TradingJournal_linux.tar.gz` |
| Windows (x64) | `TradingJournal_Setup.exe` | `TradingJournal_windows.zip` |

### Linux — AppImage (recommended)

```bash
chmod +x TradingJournal.AppImage
./TradingJournal.AppImage
```

### Linux — Portable archive

```bash
tar -xzf TradingJournal_linux.tar.gz
cd TradingJournal

# Optional: register a desktop launcher and icon
bash install.sh
# To remove:
bash install.sh uninstall
```

### Windows — Installer (recommended)

Run `TradingJournal_Setup.exe` and follow the wizard. It will:
- Install to `Program Files\Trading Journal`
- Optionally create Start Menu shortcuts and a Desktop icon
- Show the MIT license before installing
- Add an entry to **Add/Remove Programs** for clean uninstall

### Windows — Portable archive

Extract `TradingJournal_windows.zip` and run `TradingJournal.exe`.

```powershell
# Optional: add a Start Menu shortcut and desktop icon
.\install.ps1
# To remove:
.\install.ps1 -Uninstall
```

---

## Features

- **FIFO Lot Matching Engine** — Automatically matches sells to buys using FIFO ordering, supports fractional shares, multiple round trips, and computes per-lot P&L
- **Multi-Account Sidebar** — Left-panel account switcher; manage separate accounts (stocks, forex) across different brokers and currencies
- **Broker Import** — Import trades from broker statements (Trading212, MT4 supported; extensible plugin system)
- **Analytics Dashboard** — Win rate, profit factor, expectancy, Sharpe / Sortino / Calmar ratios, max drawdown, consecutive win/loss streaks, and breakdowns by instrument, setup, day of week, session, exit reason, direction, and month
- **Custom SQL Console** — Write and save any SELECT query against your live data; syntax-highlighted editor (JetBrains Mono, Monokai palette), cheat sheet, schema browser, and CSV export
- **Accurate Metrics** — All calculations include swap and commission (not just raw profit), matching broker statement totals. Drawdown % anchored to account initial balance.
- **Chart Integration** — Fetch candlestick charts from TwelveData or Yahoo Finance with trade entry/exit markers; supports broker symbol suffixes (`.raw`, `.ecn`, `mini`, etc.)
- **Trade Journal** — Daily journal entries linked to your trades
- **Setup Management** — Define and track your trading setups with example charts and entry/exit rule checklists
- **Watchlist** — Monitor instruments with weekly/daily bias notes and price levels
- **Equity Curve** — Visual equity progression with two modes: Balance (includes deposits/withdrawals) and Cumulative P&L (trade-only, starts at 0)
- **Calendar Heatmap** — Monthly P&L grid; click any day to see the trades behind it; full dark-mode support
- **Tags & Pagination** — Tag trades for quick filtering; paginated trade list handles large accounts
- **Dark Mode** — Toggle from the View menu; consistent muted P&L colour palette across all panels (matches TradingView / Webull conventions)
- **ODS / CSV Export** — Export the current filtered view to a spreadsheet
- **Right-click Context Menu** — Copy cell, copy row, edit, delete, duplicate, jump to journal, add/view chart, export row
- **Backup / Restore** — Full database backup to ZIP with one-click restore

---

## Quick Start (Run from Source)

### Prerequisites
- Python 3.10 or newer
- pip

### 1. Clone the repository
```bash
git clone https://github.com/voger/trading-journal.git
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

### Linux

```bash
source venv/bin/activate
bash build_app.sh
```

This creates:
- `dist/TradingJournal/TradingJournal` — the executable
- `dist/TradingJournal_linux.tar.gz` — portable archive
- `dist/TradingJournal.AppImage` — single-file AppImage (requires `appimagetool`)

### Windows

```cmd
venv\Scripts\activate
build_app.bat
```

This creates:
- `dist\TradingJournal\TradingJournal.exe` — the executable
- `dist\TradingJournal_windows.zip` — portable archive (requires 7-Zip)
- `dist\TradingJournal_Setup.exe` — installer (requires [NSIS](https://nsis.sourceforge.io/))

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
- Additional plugins can be added in the `plugins/` directory — see `CLAUDE.md`

---

## Running Tests

```bash
source venv/bin/activate
python -m pytest tests/ -q
```

Current: **614 passed, 42 skipped** (integration tests require real broker files and are skipped by default).

```bash
# Integration tests (provide your own files)
python -m pytest tests/ -q --real-csv=/path/to/t212.csv
python -m pytest tests/ -q --real-mt4=/path/to/DetailedStatement.htm
```

---

## Project Structure

```
trading-journal/
├── main.py              # Application entry point
├── database.py          # Star-import shim (real code in db/)
├── db/
│   ├── connection.py    # DB path, get_connection()
│   ├── schema.py        # Schema, migrations
│   ├── crud.py          # All entity CRUD
│   ├── analytics.py     # Stats, P&L, breakdowns
│   └── queries.py       # Paged/filtered trade queries, EXPORT_COLUMNS
├── fifo_engine.py       # FIFO lot matching engine
├── chart_widget.py      # Candlestick chart widget (mplfinance)
├── import_manager.py    # Plugin-based import orchestration
├── backup_manager.py    # Backup / restore to ZIP
├── executions_dialog.py # Execution detail viewer (T212 lot breakdown)
├── theme.py             # Dark theme QSS + P&L colour palette (pos/neg/neu helpers)
├── fonts/               # Bundled JetBrains Mono (OFL 1.1) for the SQL console
├── tabs/                # UI tabs: trades, journal, stats, equity, watchlist…
├── plugins/             # Broker import plugins (Trading212, MT4)
├── asset_modules/       # Per-asset-type behaviour (forex, stocks)
├── chart_providers/     # OHLC data providers (TwelveData, Yahoo Finance)
├── tests/               # Pytest test suite (614 tests)
├── build_app.sh                  # Linux PyInstaller build + AppImage
├── build_app.bat                 # Windows PyInstaller build + NSIS installer
├── build_installer_linux.sh      # AppImage creation script (called by build_app.sh)
├── build_installer_windows.nsi   # NSIS installer script (called by build_app.bat)
├── requirements.txt              # Python dependencies
├── icons/                        # Application icons
├── install.sh                    # Linux desktop integration script
└── install.ps1                   # Windows desktop integration script
```

---

## Configuration

- **Database** — Created automatically in the platform data directory (see Quick Start)
- **Chart API Keys** — Set via the 🔑 button in the chart widget; stored in the database, not in files
- **Backups** — File → Backup…; restore from the same menu

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

---

## License

MIT License — see [LICENSE](LICENSE) for details.

You are free to use, modify, and distribute this software.
