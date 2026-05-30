# ============================================================
# core/signals.py — Signal Engine
# FIXES:
#   - Per-symbol ORB state (separate instance per symbol)
#   - Nifty trend filter IMPLEMENTED in code
#   - No-trade zone 11:30-12:30
#   - Signals only on COMPLETED candles
# ============================================================
import pandas as pd
import numpy as np
from datetime import time
from infra.logger import get_logger
from infra.config import ADX_MIN, NO_TRADE_START, NO_TRADE_END, EXEC_START
from core.indicators import get_ist_now

log = get_logger("Signals")

# Parse time strings from config
_EXEC_START    = time(*[int(x) for x in EXEC_START.split(":")])
_NO_TRADE_ST   = time(*[int(x) for x in NO_TRADE_START.split(":")])
_NO_TRADE_END  = time(*[int(x) for x in NO_TRADE_END.split(":")])


class ORBState:
    """
    Per-symbol ORB state.
    One instance per symbol — fixes the multi-symbol bug.
    """
    def __init__(self, symbol: str):
        self.symbol   = symbol
        self.orb_high = None
        self.orb_low  = None
        self.is_set   = False

    def reset(self):
        self.orb_high = None
        self.orb_low  = None
        self.is_set   = False

    def set_from_df(self, df: pd.DataFrame) -> bool:
        """Extract ORB levels from 9:15-9:30 candles of completed candles only."""
        orb = df.between_time("09:15", "09:30")
        if orb.empty:
            return False
        self.orb_high = float(orb["High"].max())
        self.orb_low  = float(orb["Low"].min())
        self.is_set   = True
        log.info(f"[{self.symbol}] ORB — High: {self.orb_high:.2f} | Low: {self.orb_low:.2f}")
        return True

    def __repr__(self):
        return f"ORBState({self.symbol} H={self.orb_high} L={self.orb_low} set={self.is_set})"


def _in_no_trade_zone() -> bool:
    """True if current IST time is in 11:30-12:30 dead zone."""
    now = get_ist_now().time().replace(tzinfo=None)
    return _NO_TRADE_ST <= now <= _NO_TRADE_END

def _after_exec_start() -> bool:
    """True if current IST time >= 9:31 AM."""
    now = get_ist_now().time().replace(tzinfo=None)
    return now >= _EXEC_START


def orb_signal(df: pd.DataFrame, orb: ORBState, nifty_bullish: bool) -> str:
    """
    ORB signal for a single symbol.

    Args:
        df            : OHLCV + indicators for this symbol
        orb           : Per-symbol ORB state
        nifty_bullish : True if Nifty is above its 50 EMA

    Returns: 'BUY', 'EXIT', or 'NONE'
    """
    if not orb.is_set:
        return "NONE"
    if not _after_exec_start():
        return "NONE"
    if _in_no_trade_zone():
        log.debug("No-trade zone 11:30-12:30 — skipping")
        return "NONE"
    if not nifty_bullish:
        log.debug(f"[{orb.symbol}] Nifty bearish — no BUY signals")
        return "NONE"

    # Use SECOND-TO-LAST candle — last candle may still be forming
    if len(df) < 2:
        return "NONE"
    candle = df.iloc[-2]   # Last COMPLETED candle

    required = ["Close","adx","above_vwap","trend_up","vol_spike"]
    if not all(c in df.columns for c in required):
        return "NONE"

    close      = candle["Close"]
    adx        = candle["adx"]
    above_vwap = candle["above_vwap"]
    trend_up   = candle["trend_up"]
    vol_spike  = candle["vol_spike"]

    if (close > orb.orb_high and adx > ADX_MIN
            and above_vwap and trend_up and vol_spike):
        log.info(f"[{orb.symbol}] ORB BUY | Close {close:.2f} > ORB High {orb.orb_high:.2f}")
        return "BUY"

    if close < orb.orb_low:
        log.info(f"[{orb.symbol}] ORB EXIT | Close {close:.2f} < ORB Low {orb.orb_low:.2f}")
        return "EXIT"

    return "NONE"


def ema_signal(df: pd.DataFrame, nifty_bullish: bool) -> str:
    """EMA crossover signal with VWAP + ADX + Nifty filter."""
    if len(df) < 3 or not nifty_bullish:
        return "NONE"
    if _in_no_trade_zone():
        return "NONE"

    required = ["ema_fast","ema_slow","adx","above_vwap","trend_up","vol_spike"]
    if not all(c in df.columns for c in required):
        return "NONE"

    # Use completed candles (iloc[-2] and iloc[-3])
    curr = df.iloc[-2]
    prev = df.iloc[-3]

    cross_up   = prev["ema_fast"] < prev["ema_slow"] and curr["ema_fast"] > curr["ema_slow"]
    cross_down = prev["ema_fast"] > prev["ema_slow"] and curr["ema_fast"] < curr["ema_slow"]

    if cross_up and curr["adx"] > ADX_MIN and curr["above_vwap"] and curr["trend_up"] and curr["vol_spike"]:
        log.info(f"EMA BUY | Fast {curr['ema_fast']:.2f} crossed above Slow {curr['ema_slow']:.2f}")
        return "BUY"

    if cross_down:
        log.info("EMA EXIT | Fast crossed below Slow")
        return "EXIT"

    return "NONE"


def rsi_divergence_signal(df: pd.DataFrame, lookback: int = 10) -> str:
    """RSI divergence — only in sideways markets (ADX < 20)."""
    if len(df) < lookback + 3:
        return "NONE"

    required = ["Close","rsi","adx","vol_spike"]
    if not all(c in df.columns for c in required):
        return "NONE"

    curr = df.iloc[-2]   # Completed candle
    if curr["adx"] >= ADX_MIN:
        return "NONE"

    window      = df.iloc[-(lookback+2):-2]
    prev_low_i  = window["Close"].idxmin()
    prev_close  = window.loc[prev_low_i, "Close"]
    prev_rsi    = window.loc[prev_low_i, "rsi"]

    if curr["Close"] < prev_close and curr["rsi"] > prev_rsi and curr["vol_spike"]:
        log.info(f"RSI Divergence BUY | Price new low but RSI higher")
        return "BUY"

    if curr["rsi"] > 70:
        return "EXIT"

    return "NONE"


def is_nifty_bullish(nifty_df: pd.DataFrame) -> bool:
    """
    Check if Nifty 50 is in bullish regime.
    Bullish = Close > 50 EMA.
    Returns True (allow BUY), False (no BUY signals).
    """
    if nifty_df is None or nifty_df.empty:
        log.warning("No Nifty data — defaulting to BEARISH (safe)")
        return False
    if "ema_trend" not in nifty_df.columns:
        return False
    last = nifty_df.iloc[-1]
    return bool(last["Close"] > last["ema_trend"])
