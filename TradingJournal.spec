# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['plugins', 'plugins.trading212_plugin', 'plugins.mt4_plugin', 'asset_modules', 'asset_modules.forex', 'asset_modules.stocks', 'chart_providers', 'chart_providers.base', 'chart_providers.twelvedata_provider', 'chart_providers.yfinance_provider', 'tabs', 'tabs.trades', 'tabs.journal', 'tabs.setups', 'tabs.equity', 'tabs.stats', 'tabs.imports', 'tabs.watchlist', 'database', 'dialogs', 'executions_dialog', 'chart_widget', 'fifo_engine', 'import_manager', 'backup_manager', 'mplfinance', 'matplotlib', 'matplotlib.backends.backend_qtagg']
hiddenimports += collect_submodules('mplfinance')
hiddenimports += collect_submodules('matplotlib')
hiddenimports += collect_submodules('PyQt6')


a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[('icons', 'icons'), ('requirements.txt', '.')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'pytest'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TradingJournal',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TradingJournal',
)
