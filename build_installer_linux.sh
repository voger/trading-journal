#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# build_installer_linux.sh — Create Linux AppImage for Trading Journal
#
# Usage:
#   bash build_app.sh              # Build the app first
#   bash build_installer_linux.sh  # Create AppImage
#
# Produces:
#   dist/TradingJournal.AppImage   (Portable Linux executable)
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="TradingJournal"
DIST_DIR="$SCRIPT_DIR/dist"
BUILD_DIR="$DIST_DIR/appimage_build"
APP_DIR="$BUILD_DIR/$APP_NAME.AppDir"

echo "═══════════════════════════════════════════"
echo "  Creating $APP_NAME AppImage"
echo "═══════════════════════════════════════════"

# Check if PyInstaller output exists
if [ ! -d "$DIST_DIR/$APP_NAME" ]; then
    echo "ERROR: PyInstaller output not found at $DIST_DIR/$APP_NAME"
    echo "Please run: bash build_app.sh"
    exit 1
fi

# Check for appimagetool
if ! command -v appimagetool &> /dev/null; then
    echo "ERROR: appimagetool not found. Install it with:"
    echo "  sudo apt install appimagetool  # Debian/Ubuntu"
    echo "  Or download from: https://github.com/AppImage/AppImageKit/releases"
    exit 1
fi

# Create AppDir structure
echo "[*] Creating AppDir structure..."
rm -rf "$BUILD_DIR"
mkdir -p "$APP_DIR/usr/bin"
mkdir -p "$APP_DIR/usr/share/applications"
mkdir -p "$APP_DIR/usr/share/icons/hicolor/256x256/apps"

# Copy app files
echo "[*] Copying application files..."
cp -r "$DIST_DIR/$APP_NAME"/* "$APP_DIR/usr/bin/"

# Create launcher script
cat > "$APP_DIR/AppRun" << 'EOF'
#!/bin/bash
APPDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$APPDIR/usr/bin/TradingJournal" "$@"
EOF
chmod +x "$APP_DIR/AppRun"

# Create .desktop file
cat > "$APP_DIR/usr/share/applications/TradingJournal.desktop" << 'EOF'
[Desktop Entry]
Name=Trading Journal
Comment=Trade analysis and journaling application
Exec=TradingJournal
Icon=trading-journal
Type=Application
Categories=Finance;Office;
Terminal=false
EOF

# Create a simple icon (256x256 placeholder)
# In production, replace with actual icon
python3 << 'PYTHON_ICON'
try:
    from PIL import Image, ImageDraw
    img = Image.new('RGB', (256, 256), color=(70, 130, 180))  # Steel blue
    d = ImageDraw.Draw(img)
    d.text((80, 110), "TJ", fill=(255, 255, 255))
    img.save('/tmp/tj_icon.png')
    print("[*] Created placeholder icon")
except ImportError:
    print("[!] PIL not available, skipping icon")
PYTHON_ICON

if [ -f /tmp/tj_icon.png ]; then
    cp /tmp/tj_icon.png "$APP_DIR/usr/share/icons/hicolor/256x256/apps/trading-journal.png"
fi

# Create AppImage
echo "[*] Creating AppImage..."
appimagetool \
    --comp=gzip \
    --sign \
    "$APP_DIR" \
    "$DIST_DIR/${APP_NAME}.AppImage"

# Make AppImage executable
chmod +x "$DIST_DIR/${APP_NAME}.AppImage"

# Cleanup
rm -rf "$BUILD_DIR"

echo ""
echo "✓ AppImage created successfully!"
echo "  Location: $DIST_DIR/${APP_NAME}.AppImage"
echo ""
echo "To install:"
echo "  1. chmod +x dist/${APP_NAME}.AppImage"
echo "  2. ./dist/${APP_NAME}.AppImage"
echo ""
echo "Or move it to your PATH and run from anywhere"
