# Build skill

Build the trading journal desktop app with PyInstaller.

## Commands

```bash
source venv/bin/activate

bash build_app.sh   # Linux
build_app.bat       # Windows
python main.py      # Run without building
```

## Build outputs

Running `build_app.sh` or `build_app.bat` produces:
- **Portable app**: `dist/TradingJournal/` (folder with exe + all dependencies)
- **Portable archive**: `dist/TradingJournal_linux.tar.gz` or `dist/TradingJournal_windows.zip`
- **Linux AppImage** (if `appimagetool` available): `dist/TradingJournal.AppImage`
- **Windows Installer** (if NSIS available): `dist/TradingJournal_Setup.exe`

## Installer dependencies

**Linux AppImage:**
```bash
# appimagetool is NOT in apt — download the binary directly:
wget -q https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage -O /tmp/appimagetool
chmod +x /tmp/appimagetool && sudo mv /tmp/appimagetool /usr/local/bin/appimagetool
sudo apt install libfuse2  # runtime dependency
```

**Windows NSIS Installer:**
- Download from https://nsis.sourceforge.io/
- Or: `choco install nsis` (if using Chocolatey)
- GitHub Actions installs automatically via `choco install nsis -y`

## Build notes

- PyInstaller 6.x — `--add-data` separator is `:` on all platforms.
- Both scripts include `--hidden-import` for all dynamically loaded modules: plugins, asset modules, chart providers, `executions_dialog`.
- `.spec` is auto-generated and gitignored; build scripts are the source of truth.
- When adding new plugins, asset modules, or chart providers, also add them to `--hidden-import` in **both** `build_app.sh` and `build_app.bat`.
- Installer scripts (`build_installer_linux.sh`, `build_installer_windows.nsi`) are called automatically by build scripts if dependencies are available.
- LICENSE file is bundled with installers (EULA in Windows, included in AppImage doc dir).
- Version metadata (3.3.0) is baked into installers at build time.

## Windows installer details

- **64-bit only**: Installs to `C:\Program Files\Trading Journal` (not `Program Files (x86)`)
- Architecture check: Rejects 32-bit Windows at installer launch with error message
- Registry: Writes to native 64-bit registry hive (not WOW64 redirected)
- User isolation: Each Windows user gets their own database in `%APPDATA%\TradingJournal\`
- Optional components: Start Menu shortcuts and Desktop shortcut are checked by default but optional

## GitHub Actions release workflow

Tag a commit and push to trigger automatic release:
```bash
git tag v3.3.0
git push origin v3.3.0
```

Actions will:
1. Install build dependencies (`appimagetool`, NSIS)
2. Run `build_app.sh` (Linux) and `build_app.bat` (Windows)
3. Upload all artifacts to GitHub release:
   - `TradingJournal_linux.tar.gz` (portable)
   - `TradingJournal.AppImage` (Linux single-file)
   - `TradingJournal_windows.zip` (portable)
   - `TradingJournal_Setup.exe` (Windows installer)
