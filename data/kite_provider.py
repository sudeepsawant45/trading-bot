# ============================================================
# data/kite_provider.py — Zerodha Kite Data Provider
# Used for LIVE trading only (Phase 5+)
# Requires: pip install kiteconnect
# ============================================================
import pandas as pd
from data.base import DataProvider
from infra.logger import get_logger
from infra.config import KITE_API_KEY, KITE_ACCESS_TOKEN

log = get_logger("KiteProvider")

class KiteProvider(DataProvider):
    """
    Zerodha Kite Connect data provider.
    Activate only after getting SEBI algo approval from Zerodha.
    """

    def __init__(self):
        if not KITE_API_KEY or KITE_API_KEY == "your_api_key_here":
            raise ValueError(
                "Kite API key not configured. "
                "Set KITE_API_KEY in .env file."
            )
        try:
            from kiteconnect import KiteConnect
            self.kite = KiteConnect(api_key=KITE_API_KEY)
            self.kite.set_access_token(KITE_ACCESS_TOKEN)
            log.info("Kite provider initialized")
        except ImportError:
            raise ImportError("kiteconnect not installed. Run: pip install kiteconnect")

    def get_historical(self, symbol: str, period: str = "1y",
                       interval: str = "5minute") -> pd.DataFrame:
        # Kite uses different interval names: '5minute', '15minute', 'day'
        raise NotImplementedError("Implement with kite.historical_data()")

    def get_today(self, symbol: str, interval: str = "5minute") -> pd.DataFrame:
        raise NotImplementedError("Use Kite WebSocket for live ticks")

    def get_multiple(self, symbols: list, period: str, interval: str) -> dict:
        raise NotImplementedError("Implement per symbol")
