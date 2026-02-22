@echo off
REM ──────────────────────────────────────────────────────────────
REM build_app.bat — Package Trading Journal for Windows
REM
REM Usage:
REM   1. Open Command Prompt in the project folder
REM   2. Activate your venv:  venv\Scripts\activate
REM   3. Run:  build_app.bat
REM ──────────────────────────────────────────────────────────────
setlocal

set APP_NAME=TradingJournal

echo ═══════════════════════════════════════════
echo   Building %APP_NAME% standalone package
echo ═══════════════════════════════════════════

REM ── Check if venv is active ──
if "%VIRTUAL_ENV%"=="" (
    if exist venv\Scripts\activate.bat (
        echo [*] Activating venv...
        call venv\Scripts\activate.bat
    ) else (
        echo ERROR: No virtual environment found.
        echo Please create one first:
        echo   python -m venv venv
        echo   venv\Scripts\activate
        echo   pip install -r requirements.txt
        echo   build_app.bat
        exit /b 1
    )
)

echo [*] Using Python: 
python --version
echo [*] Virtual env: %VIRTUAL_ENV%

REM ── Check deps ──
echo [0/5] Checking dependencies...
python -c "import PyQt6" 2>nul || (
    echo   Installing dependencies...
    pip install -r requirements.txt
)

python -m PyInstaller --version 2>nul || (
    echo   Installing PyInstaller...
    pip install pyinstaller
)

REM ── Clean ──
echo [1/5] Cleaning previous builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist %APP_NAME%.spec del %APP_NAME%.spec

REM ── Generate icon.ico from PNG sources ──
echo [2/5] Generating icon.ico...
python -c "from PIL import Image; imgs=[Image.open(f'icons/icon_{s}.png').resize((s,s)) for s in [256,128,64,48,32,16]]; imgs[0].save('icons/icon.ico', sizes=[(s,s) for s in [256,128,64,48,32,16]], append_images=imgs[1:])" 2>nul
if exist icons\icon.ico (
    echo   icons\icon.ico generated successfully.
    set ICON_ARG=--icon icons\icon.ico
) else (
    echo   WARNING: Could not generate icon.ico - executable will use default icon.
    set ICON_ARG=
)

REM ── Build ──
echo [3/5] Running PyInstaller...
python -m PyInstaller ^
    --name "%APP_NAME%" ^
    --onedir ^
    --windowed ^
    --noconfirm ^
    --clean ^
    --paths "." ^
    %ICON_ARG% ^
    --add-data "icons:icons" ^
    --add-data "requirements.txt:." ^
    --hidden-import "plugins" ^
    --hidden-import "plugins.trading212_plugin" ^
    --hidden-import "plugins.mt4_plugin" ^
    --hidden-import "asset_modules" ^
    --hidden-import "asset_modules.forex" ^
    --hidden-import "asset_modules.stocks" ^
    --hidden-import "chart_providers" ^
    --hidden-import "chart_providers.base" ^
    --hidden-import "chart_providers.twelvedata_provider" ^
    --hidden-import "chart_providers.yfinance_provider" ^
    --hidden-import "tabs" ^
    --hidden-import "tabs.trades" ^
    --hidden-import "tabs.journal" ^
    --hidden-import "tabs.setups" ^
    --hidden-import "tabs.equity" ^
    --hidden-import "tabs.stats" ^
    --hidden-import "tabs.imports" ^
    --hidden-import "tabs.watchlist" ^
    --hidden-import "database" ^
    --hidden-import "dialogs" ^
    --hidden-import "executions_dialog" ^
    --hidden-import "chart_widget" ^
    --hidden-import "fifo_engine" ^
    --hidden-import "import_manager" ^
    --hidden-import "backup_manager" ^
    --hidden-import "mplfinance" ^
    --hidden-import "matplotlib" ^
    --hidden-import "matplotlib.backends.backend_qtagg" ^
    --collect-submodules "mplfinance" ^
    --collect-submodules "matplotlib" ^
    --collect-submodules "PyQt6" ^
    --exclude-module "tkinter" ^
    --exclude-module "pytest" ^
    main.py

REM ── Verify ──
echo [4/5] Verifying build...
if exist "dist\%APP_NAME%\%APP_NAME%.exe" (
    echo   OK: dist\%APP_NAME%\%APP_NAME%.exe
) else (
    echo   FAILED: executable not found
    exit /b 1
)

REM ── Copy desktop integration script ──
copy /Y install.ps1 "dist\%APP_NAME%\install.ps1" >nul
echo   install.ps1 copied (run with -Uninstall to reverse).

REM ── Archive ──
echo [5/5] Creating archive...
cd dist
if exist "%ProgramFiles%\7-Zip\7z.exe" (
    "%ProgramFiles%\7-Zip\7z.exe" a "%APP_NAME%_windows.zip" "%APP_NAME%\" > nul
    echo   Created dist\%APP_NAME%_windows.zip
) else (
    echo   7-Zip not found - folder ready at dist\%APP_NAME%\
)
cd ..

echo.
echo ═══════════════════════════════════════════
echo   Build complete!
echo   Run:       dist\%APP_NAME%\%APP_NAME%.exe
echo   Install:   powershell -ExecutionPolicy Bypass -File dist\%APP_NAME%\install.ps1
echo   Uninstall: powershell -ExecutionPolicy Bypass -File dist\%APP_NAME%\install.ps1 -Uninstall
echo ═══════════════════════════════════════════
