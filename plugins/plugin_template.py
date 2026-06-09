"""
Import Plugin Template
Copy this file and implement the required functions to add support for a new broker.

The full, declared interface lives in ``plugins/contract.py`` (the ``ImportPlugin``
Protocol). A conforming plugin must provide:

Required:
    PLUGIN_NAME: str - unique identifier (e.g., 'trading212_csv')
    DISPLAY_NAME: str - shown in the UI (e.g., 'Trading212 CSV Export')
    SUPPORTED_EXTENSIONS: list - file extensions (e.g., ['.csv'])
    IMPORT_MODE: str - contract.IMPORT_MODE_TRADES or contract.IMPORT_MODE_EXECUTIONS
                       (declare it explicitly — there is no default)
    validate(file_path) -> (bool, str)
    parse(file_path) -> contract.ParseResult(records, balance_events)
    file_hash(file_path) -> str   (used for dedup / import logging)

Optional (reached by the app through contract accessors, never sniffed directly):
    parse_account_info(file_path) -> dict   (pre-fill account details on import)
    DEFAULT_ASSET_TYPE: str                 (asset-type hint for new accounts)

Each record dict returned by parse() must contain:
    - broker_ticket_id: str  (REQUIRED - used for deduplication)
    - symbol: str            (e.g., "EURUSD", "AAPL")
    - direction: str         ("long" or "short")
    - entry_date: str        (ISO 8601 format)
    - entry_price: float
    - position_size: float   (lots for forex, shares for stocks)
    - exit_date: str or None
    - exit_price: float or None
    - stop_loss_price: float or None
    - take_profit_price: float or None
    - commission: float
    - swap: float
    - pnl_account_currency: float or None
    - status: str            ("open" or "closed")

Optional fields:
    - display_name: str      (human-readable name, e.g., "EUR/USD")
    - instrument_type: str   ('forex', 'stock', 'etf', 'commodity', 'index', 'crypto', 'other')
    - pip_size: float        (for forex instruments)
    - pnl_pips: float
    - exit_reason: str       ('target_hit', 'trailing_stop', 'manual', 'stop_loss', 'time_exit')
"""

try:
    from . import contract
except ImportError:  # pragma: no cover - exercised only outside the package
    from plugins import contract

PLUGIN_NAME = "template"
DISPLAY_NAME = "Template Plugin (Do Not Use)"
SUPPORTED_EXTENSIONS = [".csv"]
# Declare explicitly: contract.IMPORT_MODE_TRADES for pre-matched trades, or
# contract.IMPORT_MODE_EXECUTIONS for lot-tracked stock imports (FIFO-built).
IMPORT_MODE = contract.IMPORT_MODE_TRADES


def validate(file_path: str) -> tuple:
    """Check if this file can be parsed by this plugin.
    Returns (is_valid: bool, message: str)"""
    return False, "This is a template plugin - not for actual use."


def parse(file_path: str) -> contract.ParseResult:
    """Parse the broker file and return ParseResult(records, balance_events)."""
    raise NotImplementedError("Template plugin - implement your parser here.")


def file_hash(file_path: str) -> str:
    """Return a hash of the file contents for deduplication."""
    import hashlib
    h = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()
