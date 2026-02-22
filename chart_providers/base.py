"""Base class for chart data providers."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime


@dataclass
class OHLCBar:
    """Single OHLC price bar."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class ChartProvider(ABC):
    """Abstract base class for chart data providers.

    Implement this to add a new data source (e.g., Alpha Vantage, Twelve Data, etc).
    """
    PROVIDER_ID: str = ""      # e.g. 'yfinance'
    DISPLAY_NAME: str = ""     # e.g. 'Yahoo Finance'

    @property
    def requires_api_key(self) -> bool:
        """Override to True if this provider needs an API key."""
        return False

    @property
    def api_key_instructions(self) -> str:
        """Human-readable instructions for getting an API key."""
        return ''

    @abstractmethod
    def fetch_ohlc(self, symbol: str, start_date: datetime, end_date: datetime,
                   timeframe: str = '1d') -> List[OHLCBar]:
        """Fetch OHLC data for a symbol.

        Args:
            symbol: The instrument symbol as stored in the journal (e.g. 'EURUSD', 'AAPL')
            start_date: Start of data range
            end_date: End of data range
            timeframe: Bar interval ('1h', '4h', '1d', '1wk')

        Returns:
            List of OHLCBar sorted by timestamp ascending.

        Raises:
            ValueError: If symbol not found or timeframe not supported.
            ConnectionError: If network request fails.
        """
        pass

    @abstractmethod
    def normalize_symbol(self, symbol: str, asset_type: str = 'forex') -> str:
        """Convert journal symbol to provider-specific format.

        Args:
            symbol: Journal symbol (e.g. 'EURUSD', 'GBPUSD', 'AAPL')
            asset_type: 'forex' or 'stocks' to guide conversion

        Returns:
            Provider-specific symbol string.
        """
        pass

    @abstractmethod
    def supported_timeframes(self) -> List[str]:
        """Return list of supported timeframe strings."""
        pass

    def display_timeframes(self) -> List[tuple]:
        """Return (value, label) pairs for UI dropdown."""
        labels = {
            '1h': '1 Hour', '4h': '4 Hours', '1d': 'Daily', '1wk': 'Weekly', '1mo': 'Monthly',
        }
        return [(tf, labels.get(tf, tf)) for tf in self.supported_timeframes()]
