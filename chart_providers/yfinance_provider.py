"""Yahoo Finance chart data provider using yfinance."""
from datetime import datetime, timedelta
from typing import List
from chart_providers.base import ChartProvider, OHLCBar

# Common forex pairs — MT4 symbol to yfinance symbol
_FOREX_MAP = {
    'EURUSD': 'EURUSD=X', 'GBPUSD': 'GBPUSD=X', 'USDJPY': 'USDJPY=X',
    'USDCHF': 'USDCHF=X', 'AUDUSD': 'AUDUSD=X', 'NZDUSD': 'NZDUSD=X',
    'USDCAD': 'USDCAD=X', 'EURGBP': 'EURGBP=X', 'EURJPY': 'EURJPY=X',
    'GBPJPY': 'GBPJPY=X', 'EURAUD': 'EURAUD=X', 'EURNZD': 'EURNZD=X',
    'EURCAD': 'EURCAD=X', 'EURCHF': 'EURCHF=X', 'AUDCAD': 'AUDCAD=X',
    'AUDNZD': 'AUDNZD=X', 'AUDJPY': 'AUDJPY=X', 'GBPAUD': 'GBPAUD=X',
    'GBPCAD': 'GBPCAD=X', 'GBPCHF': 'GBPCHF=X', 'GBPNZD': 'GBPNZD=X',
    'NZDJPY': 'NZDJPY=X', 'CADJPY': 'CADJPY=X', 'CADCHF': 'CADCHF=X',
    'CHFJPY': 'CHFJPY=X', 'NZDCAD': 'NZDCAD=X', 'NZDCHF': 'NZDCHF=X',
    # Gold/Silver
    'XAUUSD': 'GC=F', 'XAGUSD': 'SI=F',
}

# yfinance timeframe mapping
_TF_MAP = {
    '1h': '1h', '4h': '1h',  # 4h built from 1h bars
    '1d': '1d', '1wk': '1wk', '1mo': '1mo',
}


class YFinanceProvider(ChartProvider):
    PROVIDER_ID = 'yfinance'
    DISPLAY_NAME = 'Yahoo Finance'

    def fetch_ohlc(self, symbol: str, start_date: datetime, end_date: datetime,
                   timeframe: str = '1d') -> List[OHLCBar]:
        try:
            import yfinance as yf
        except ImportError:
            raise ImportError("yfinance not installed. Run: pip install yfinance")

        yf_symbol = self.normalize_symbol(symbol)
        yf_tf = _TF_MAP.get(timeframe, timeframe)

        # yfinance needs end_date + 1 day to include last day
        end_padded = end_date + timedelta(days=1)

        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(start=start_date.strftime('%Y-%m-%d'),
                            end=end_padded.strftime('%Y-%m-%d'),
                            interval=yf_tf,
                            auto_adjust=False)

        if df is None or df.empty:
            raise ValueError(f"No data returned for {yf_symbol} ({symbol})")

        # Build 4h bars from 1h if needed
        if timeframe == '4h' and yf_tf == '1h':
            df = self._resample_4h(df)

        bars = []
        for ts, row in df.iterrows():
            # Handle timezone-aware timestamps
            if hasattr(ts, 'tz') and ts.tz is not None:
                ts = ts.tz_localize(None)
            bars.append(OHLCBar(
                timestamp=ts.to_pydatetime(),
                open=float(row['Open']),
                high=float(row['High']),
                low=float(row['Low']),
                close=float(row['Close']),
                volume=float(row.get('Volume', 0)),
            ))
        return bars

    def normalize_symbol(self, symbol: str, asset_type: str = 'forex') -> str:
        # Clean up symbol (remove dots, spaces, hashes)
        clean = symbol.upper().replace('.', '').replace(' ', '').replace('#', '')

        # Check forex map first
        if clean in _FOREX_MAP:
            return _FOREX_MAP[clean]

        # MT4 often uses suffixes like EURUSDm, EURUSD.raw — strip common suffixes
        for suffix in ['M', '.RAW', '.ECN', '.PRO', '.STD', 'MINI']:
            stripped = clean.rstrip(suffix) if clean.endswith(suffix) else clean
            if stripped in _FOREX_MAP:
                return _FOREX_MAP[stripped]

        # If it's a forex pair pattern (6 chars, all alpha), try adding =X
        if len(clean) == 6 and clean.isalpha() and asset_type == 'forex':
            return f"{clean}=X"

        # For stocks, return as-is (yfinance uses standard tickers)
        return clean

    def supported_timeframes(self) -> List[str]:
        return ['1h', '4h', '1d', '1wk']

    @staticmethod
    def _resample_4h(df):
        """Resample 1h bars into 4h bars."""
        resampled = df.resample('4h').agg({
            'Open': 'first', 'High': 'max', 'Low': 'min',
            'Close': 'last', 'Volume': 'sum',
        }).dropna()
        return resampled
