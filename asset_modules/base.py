"""
Asset Module base class.
Each account type (forex, stocks, etc.) has a module that defines
how trades work for that asset class.
"""
from abc import ABC, abstractmethod


class AssetModule(ABC):
    """Base class for asset type modules."""

    ASSET_TYPE = ""       # e.g. "forex", "stocks"
    DISPLAY_NAME = ""     # e.g. "Forex", "Stocks & ETFs"

    # ── Schema ──

    @abstractmethod
    def extra_tables_sql(self) -> list[str]:
        """Return list of CREATE TABLE SQL strings for type-specific tables."""
        return []

    @abstractmethod
    def event_types(self) -> list[str]:
        """Account event types beyond deposit/withdrawal. e.g. ['dividend', 'interest']"""
        return []

    # ── Trade table columns ──

    @abstractmethod
    def trade_columns(self) -> list[dict]:
        """Return column definitions for the trades table.
        Each dict: {'key': str, 'header': str, 'width': int or None}
        Base columns (ID, Date, Instrument, Dir, P&L, Status) are always shown.
        These are the TYPE-SPECIFIC columns inserted between Dir and P&L.
        """
        pass

    @abstractmethod
    def format_trade_cell(self, trade: dict, column_key: str) -> str:
        """Format a trade value for display in the given column."""
        pass

    # ── Trade dialog fields ──

    @abstractmethod
    def trade_form_fields(self) -> list[dict]:
        """Return field definitions for the trade entry form.
        Each dict: {'key': str, 'label': str, 'type': 'float'|'int'|'text',
                     'decimals': int, 'range': (min, max), 'suffix': str}
        These are the TYPE-SPECIFIC fields added to the trade dialog.
        """
        pass

    # ── Stats ──

    @abstractmethod
    def format_stats_html(self, stats: dict, currency: str) -> str:
        """Return type-specific HTML stats section to append to the summary."""
        return ""

    # ── Defaults ──

    def default_instrument_type(self) -> str:
        """Default instrument type for this account."""
        return "other"

    def size_label(self) -> str:
        """Label for position size field. 'Lots' for forex, 'Shares' for stocks."""
        return "Size"

    def size_decimals(self) -> int:
        """Decimal places for position size."""
        return 2

    def price_decimals(self) -> int:
        """Default decimal places for prices."""
        return 5
