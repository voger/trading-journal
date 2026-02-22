#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# build_app.sh — Package Trading Journal as a standalone application
#
# Usage:
#   source venv/bin/activate   # MUST activate venv first!
#   bash build_app.sh
#
# Or let the script auto-detect the venv:
#   bash build_app.sh          # auto-finds ./venv or ./.venv
#
# Produces:
#   dist/TradingJournal/         (folder with executable + deps)
#   dist/TradingJournal.tar.gz   (Linux portable archive)
#   dist/TradingJournal.zip      (Windows portable archive)
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="TradingJournal"

echo "═══════════════════════════════════════════"
echo "  Building $APP_NAME standalone package"
echo "═══════════════════════════════════════════"

# ── Auto-activate venv if not already in one ──
if [ -z "${VIRTUAL_ENV:-}" ]; then
    for vdir in venv .venv; do
        if [ -f "$vdir/bin/activate" ]; then
            echo "[*] Activating $vdir..."
            source "$vdir/bin/activate"
            break
        elif [ -f "$vdir/Scripts/activate" ]; then
            echo "[*] Activating $vdir (Windows)..."
            source "$vdir/Scripts/activate"
            break
        fi
    done
fi

if [ -z "${VIRTUAL_ENV:-}" ]; then
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║  ERROR: No virtual environment found or activated!       ║"
    echo "║                                                          ║"
    echo "║  Please either:                                          ║"
    echo "║    1. Activate your venv first:                          ║"
    echo "║       source venv/bin/activate && bash build_app.sh      ║"
    echo "║                                                          ║"
    echo "║    2. Or create one:                                     ║"
    echo "║       python3 -m venv venv                               ║"
    echo "║       source venv/bin/activate                           ║"
    echo "║       pip install -r requirements.txt                    ║"
    echo "║       bash build_app.sh                                  ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    exit 1
fi

echo "[*] Using Python: $(which python3)"
echo "[*] Virtual env:  $VIRTUAL_ENV"

# ── Verify key dependencies ──
echo "[0/4] Checking dependencies..."
MISSING=""
python3 -c "import PyQt6" 2>/dev/null || MISSING="$MISSING PyQt6"
python3 -c "import mplfinance" 2>/dev/null || MISSING="$MISSING mplfinance"
python3 -c "import matplotlib" 2>/dev/null || MISSING="$MISSING matplotlib"

if [ -n "$MISSING" ]; then
    echo "  Missing packages:$MISSING"
    echo "  Installing from requirements.txt..."
    pip install -r requirements.txt
fi

# ── Ensure pyinstaller is installed (in venv) ──
if ! python3 -m PyInstaller --version &>/dev/null 2>&1; then
    echo "  Installing PyInstaller into venv..."
    pip install pyinstaller
fi

# ── Clean previous builds ──
echo "[1/4] Cleaning previous builds..."
rm -rf build/ dist/ *.spec

# ── Run PyInstaller ──
echo "[2/4] Running PyInstaller (this may take a minute)..."
python3 -m PyInstaller \
    --name "$APP_NAME" \
    --onedir \
    --windowed \
    --noconfirm \
    --clean \
    --paths "." \
    --add-data "icon.png:." \
    --add-data "icon.svg:." \
    --add-data "requirements.txt:." \
    --hidden-import "plugins" \
    --hidden-import "plugins.trading212_plugin" \
    --hidden-import "plugins.mt4_plugin" \
    --hidden-import "asset_modules" \
    --hidden-import "asset_modules.forex" \
    --hidden-import "asset_modules.stocks" \
    --hidden-import "chart_providers" \
    --hidden-import "chart_providers.base" \
    --hidden-import "chart_providers.twelvedata_provider" \
    --hidden-import "chart_providers.yfinance_provider" \
    --hidden-import "tabs" \
    --hidden-import "tabs.trades" \
    --hidden-import "tabs.journal" \
    --hidden-import "tabs.setups" \
    --hidden-import "tabs.equity" \
    --hidden-import "tabs.stats" \
    --hidden-import "tabs.imports" \
    --hidden-import "tabs.watchlist" \
    --hidden-import "database" \
    --hidden-import "dialogs" \
    --hidden-import "executions_dialog" \
    --hidden-import "chart_widget" \
    --hidden-import "fifo_engine" \
    --hidden-import "import_manager" \
    --hidden-import "backup_manager" \
    --hidden-import "mplfinance" \
    --hidden-import "matplotlib" \
    --hidden-import "matplotlib.backends.backend_qtagg" \
    --collect-submodules "mplfinance" \
    --collect-submodules "matplotlib" \
    --collect-submodules "PyQt6" \
    --exclude-module "tkinter" \
    --exclude-module "pytest" \
    main.py

# ── Verify the build ──
echo "[3/4] Verifying build..."
EXECUTABLE=""
if [ -f "dist/$APP_NAME/$APP_NAME" ]; then
    EXECUTABLE="dist/$APP_NAME/$APP_NAME"
elif [ -f "dist/$APP_NAME/${APP_NAME}.exe" ]; then
    EXECUTABLE="dist/$APP_NAME/${APP_NAME}.exe"
fi

if [ -z "$EXECUTABLE" ]; then
    echo "  ✗ Build failed — executable not found"
    exit 1
fi
echo "  ✓ Executable found: $EXECUTABLE"

# ── Create portable archive ──
echo "[4/4] Creating portable archive..."
cd dist
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
    if command -v 7z &>/dev/null; then
        7z a "${APP_NAME}_windows.zip" "$APP_NAME/" > /dev/null
        echo "  ✓ Created dist/${APP_NAME}_windows.zip"
    else
        echo "  ⚠ 7z not found — folder is ready at dist/$APP_NAME/"
    fi
else
    tar -czf "${APP_NAME}_linux.tar.gz" "$APP_NAME/"
    echo "  ✓ Created dist/${APP_NAME}_linux.tar.gz"
fi
cd ..

echo ""
echo "═══════════════════════════════════════════"
echo "  Build complete!"
echo ""
echo "  Run:  $EXECUTABLE"
echo "═══════════════════════════════════════════"
