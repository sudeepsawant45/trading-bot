# ============================================================
# data/yfinance_provider.py — yfinance Data Provider
# NOTE: yfinance 5-min data only available for last 60 days.
#       For backtesting use interval='1d' for longer periods.
# ============================================================
import time
import yfinance as yf
import pandas as pd
from data.base import DataProvider
from infra.logger import get_logger
from infra.config import NIFTY_SYMBOL

log = get_logger("YFinanceProvider")

# yfinance hard limits for intraday data
_INTRADAY_INTERVALS = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"}
_MAX_INTRADAY_DAYS  = 58   # yfinance allows ~60 days for 5m data

class YFinanceProvider(DataProvider):

    def get_historical(self, symbol: str, period: str = "1y",
                       interval: str = "1d") -> pd.DataFrame:
        """
        Fetch historical data.
        IMPORTANT: For 5m interval, period is capped at 58d automatically.
        """
        # Auto-correct: warn user if they request too much intraday data
        if interval in _INTRADAY_INTERVALS:
            if period not in ("1d", "5d", "1mo", "2mo"):
                log.warning(
                    f"yfinance {interval} data only available for ~60 days. "
                    f"Requested period='{period}' will be capped. "
                    f"For longer backtests, use interval='1d'."
                )
                period = "58d"   # Cap to avoid silent truncation

        return self._fetch(symbol, period=period, interval=interval)

    def get_today(self, symbol: str, interval: str = "5m") -> pd.DataFrame:
        return self._fetch(symbol, period="1d", interval=interval)

    def get_multiple(self, symbols: list, period: str = "1y",
                     interval: str = "1d") -> dict:
        data = {}
        for sym in symbols:
            df = self.get_historical(sym, period=period, interval=interval)
            if not df.empty:
                data[sym] = df
            time.sleep(0.3)   # Gentle rate limiting — avoid yfinance ban
        log.info(f"Fetched {len(data)}/{len(symbols)} symbols")
        return data

    def get_nifty(self, period: str = "3mo", interval: str = "5m") -> pd.DataFrame:
        """Fetch Nifty 50 index for trend filter."""
        return self._fetch(NIFTY_SYMBOL, period=period, interval=interval)

    def _fetch(self, symbol: str, period: str, interval: str,
               retries: int = 3) -> pd.DataFrame:
        """Internal fetch with retry logic."""
        for attempt in range(1, retries + 1):
            try:
                df = yf.Ticker(symbol).history(
                    period=period, interval=interval, auto_adjust=True
                )
                if df.empty:
                    log.warning(f"No data for {symbol} (attempt {attempt})")
                    time.sleep(2 ** attempt)
                    continue

                df = df[["Open","High","Low","Close","Volume"]].copy()
                df.index = pd.to_datetime(df.index).tz_localize(None)
                df.dropna(inplace=True)

                if interval in _INTRADAY_INTERVALS:
                    df = df.between_time("09:15", "15:30")

                log.info(f"Fetched {len(df)} candles for {symbol} ({interval})")
                return df

            except Exception as e:
                log.warning(f"Fetch error {symbol} attempt {attempt}: {e}")
                if attempt < retries:
                    time.sleep(2 ** attempt)

        log.error(f"All {retries} attempts failed for {symbol}")
        return pd.DataFrame()
