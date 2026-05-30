# ============================================================
# data/base.py — Abstract Data Provider Interface
# Swap yfinance ↔ Kite without changing any other code
# ============================================================
from abc import ABC, abstractmethod
import pandas as pd

class DataProvider(ABC):
    """
    Abstract base class for all data providers.
    Implement this to add any new data source.
    """

    @abstractmethod
    def get_historical(self, symbol: str, period: str, interval: str) -> pd.DataFrame:
        """Fetch historical OHLCV data."""
        ...

    @abstractmethod
    def get_today(self, symbol: str, interval: str = "5m") -> pd.DataFrame:
        """Fetch today's intraday data."""
        ...

    @abstractmethod
    def get_multiple(self, symbols: list, period: str, interval: str) -> dict:
        """Fetch data for multiple symbols. Returns {symbol: DataFrame}."""
        ...
