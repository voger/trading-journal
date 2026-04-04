# Build skill

Build the trading journal desktop app with PyInstaller.

## Commands

```bash
source venv/bin/activate

bash build_app.sh   # Linux
build_app.bat       # Windows
python main.py      # Run without building
```

## Build notes

- PyInstaller 6.x — `--add-data` separator is `:` on all platforms.
- Both scripts include `--hidden-import` for all dynamically loaded modules: plugins, asset modules, chart providers, `executions_dialog`.
- `.spec` is auto-generated and gitignored; build scripts are the source of truth.
- When adding new plugins, asset modules, or chart providers, also add them to `--hidden-import` in **both** `build_app.sh` and `build_app.bat`.
