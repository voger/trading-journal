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
    --add-data "icons:icons" \
    --add-data "fonts:fonts" \
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
echo "[3/5] Verifying build..."
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

# ── Generate Linux desktop integration script ──
if [[ "$OSTYPE" != "msys" && "$OSTYPE" != "cygwin" && "$OSTYPE" != "win32" ]]; then
    echo "[4/5] Generating Linux desktop integration script..."
    cat > "dist/$APP_NAME/install.sh" << 'INSTALL_SCRIPT'
#!/usr/bin/env bash
# Trading Journal — Linux desktop integration
#
# Usage:
#   bash install.sh            # install (register icon + launcher entry)
#   bash install.sh uninstall  # remove desktop integration files
#
# NOTE: If you move this folder after installing, re-run this script
#       so the launcher paths are updated.

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXECUTABLE="$APP_DIR/TradingJournal"
DESKTOP_ID="trading-journal"
ICON_NAME="$DESKTOP_ID"
ICON_SRC="$APP_DIR/icons/icon.png"
ICON_DEST="$HOME/.local/share/icons/hicolor/256x256/apps/${DESKTOP_ID}.png"
DESKTOP_DEST="$HOME/.local/share/applications/${DESKTOP_ID}.desktop"

_refresh_caches() {
    command -v update-desktop-database &>/dev/null \
        && update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
    command -v gtk-update-icon-cache &>/dev/null \
        && gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
}

do_install() {
    if [ ! -f "$EXECUTABLE" ]; then
        echo "ERROR: Executable not found at $EXECUTABLE"
        exit 1
    fi
    if [ ! -f "$ICON_SRC" ]; then
        echo "ERROR: icon.png not found at $ICON_SRC"
        exit 1
    fi

    echo "Installing Trading Journal desktop integration..."

    # Install icon into hicolor theme
    mkdir -p "$(dirname "$ICON_DEST")"
    cp "$ICON_SRC" "$ICON_DEST"
    echo "  ✓ Icon installed to $ICON_DEST"

    # Write .desktop file
    mkdir -p "$(dirname "$DESKTOP_DEST")"
    cat > "$DESKTOP_DEST" << EOF
[Desktop Entry]
Name=Trading Journal
Comment=Personal trading journal and performance analytics
Exec=$EXECUTABLE
Icon=$ICON_NAME
Type=Application
Categories=Finance;Office;
Terminal=false
StartupWMClass=TradingJournal
EOF
    echo "  ✓ Launcher entry written to $DESKTOP_DEST"

    _refresh_caches

    echo ""
    echo "Done. Trading Journal should now appear in your application launcher."
    echo ""
    echo "NOTE: If you move the app folder, re-run this script to update the paths."
}

do_uninstall() {
    echo "Removing Trading Journal desktop integration..."
    local removed=0

    if [ -f "$ICON_DEST" ]; then
        rm -f "$ICON_DEST"
        echo "  ✓ Removed icon ($ICON_DEST)"
        removed=1
    fi
    if [ -f "$DESKTOP_DEST" ]; then
        rm -f "$DESKTOP_DEST"
        echo "  ✓ Removed launcher entry ($DESKTOP_DEST)"
        removed=1
    fi

    if [ "$removed" -eq 0 ]; then
        echo "  Nothing to remove (integration was not installed from this location)."
    else
        _refresh_caches
        echo ""
        echo "Done. You can now delete the TradingJournal folder."
    fi
}

case "${1:-install}" in
    uninstall|remove) do_uninstall ;;
    install|*)        do_install ;;
esac
INSTALL_SCRIPT

    chmod +x "dist/$APP_NAME/install.sh"
    echo "  ✓ install.sh generated (run with 'uninstall' argument to reverse)"
fi

# ── Create portable archive ──
echo "[5/6] Creating portable archive..."
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

# ── Build AppImage (Linux only) ──
if [[ "$OSTYPE" != "msys" && "$OSTYPE" != "cygwin" && "$OSTYPE" != "win32" ]]; then
    echo "[6/6] Building AppImage..."
    if command -v appimagetool &>/dev/null; then
        bash build_installer_linux.sh
    else
        echo "  ⚠ appimagetool not found — skipping AppImage"
        echo "     Install with:"
        echo "       wget -q https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage -O /tmp/appimagetool"
        echo "       chmod +x /tmp/appimagetool && sudo mv /tmp/appimagetool /usr/local/bin/appimagetool"
        echo "       sudo apt install libfuse2"
    fi
fi

echo ""
echo "═══════════════════════════════════════════"
echo "  Build complete!"
echo ""
echo "  Run:      $EXECUTABLE"
if [[ "$OSTYPE" != "msys" && "$OSTYPE" != "cygwin" && "$OSTYPE" != "win32" ]]; then
echo "  Install:  bash dist/$APP_NAME/install.sh"
echo "  Remove:   bash dist/$APP_NAME/install.sh uninstall"
echo "  AppImage: dist/${APP_NAME}.AppImage"
fi
echo "═══════════════════════════════════════════"
