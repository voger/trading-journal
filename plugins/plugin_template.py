"""
Import Plugin Template
Copy this file and implement the required functions to add support for a new broker.

Required:
    PLUGIN_NAME: str - unique identifier (e.g., 'trading212_csv')
    DISPLAY_NAME: str - shown in the UI (e.g., 'Trading212 CSV Export')
    SUPPORTED_EXTENSIONS: list - file extensions (e.g., ['.csv'])
    validate(file_path) -> (bool, str)
    parse(file_path) -> list[dict]

Each trade dict returned by parse() must contain:
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

PLUGIN_NAME = "template"
DISPLAY_NAME = "Template Plugin (Do Not Use)"
SUPPORTED_EXTENSIONS = [".csv"]


def validate(file_path: str) -> tuple:
    """Check if this file can be parsed by this plugin.
    Returns (is_valid: bool, message: str)"""
    return False, "This is a template plugin - not for actual use."


def parse(file_path: str) -> list:
    """Parse the broker file and return a list of standardized trade dicts."""
    raise NotImplementedError("Template plugin - implement your parser here.")
