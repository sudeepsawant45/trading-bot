# ============================================================
# core/indicators.py — Technical Indicators
# Uses 'ta' library (Python 3.14 compatible)
# pip install ta  — no numba dependency
# ============================================================
import pandas as pd
import numpy as np
from zoneinfo import ZoneInfo
from infra.logger import get_logger
from infra.config import (
    EMA_FAST, EMA_SLOW, EMA_TREND,
    RSI_PERIOD, ATR_PERIOD, ADX_PERIOD,
    VOLUME_SMA, ATR_SL_MULT, RVOL_THRESHOLD,
    TIMEZONE, MAX_GAP_NORMAL
)

log = get_logger("Indicators")
IST = ZoneInfo(TIMEZONE)


def calculate_all(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate all indicators on OHLCV DataFrame.
    Uses manual pandas calculations — no external TA library needed.
    Works on Python 3.14+
    """
    if df.empty or len(df) < EMA_TREND + 5:
        log.warning("Insufficient data for indicators")
        return df

    df = df.copy()
    try:
        # ── EMA ──────────────────────────────────────────
        df["ema_fast"]  = df["Close"].ewm(span=EMA_FAST,  adjust=False).mean()
        df["ema_slow"]  = df["Close"].ewm(span=EMA_SLOW,  adjust=False).mean()
        df["ema_trend"] = df["Close"].ewm(span=EMA_TREND, adjust=False).mean()

        # ── RSI ──────────────────────────────────────────
        df["rsi"] = _rsi(df["Close"], RSI_PERIOD)

        # ── ATR ──────────────────────────────────────────
        df["atr"] = _atr(df["High"], df["Low"], df["Close"], ATR_PERIOD)

        # ── VWAP ─────────────────────────────────────────
        df["vwap"] = _vwap(df)

        # ── ADX ──────────────────────────────────────────
        df["adx"] = _adx(df["High"], df["Low"], df["Close"], ADX_PERIOD)

        # ── Volume ───────────────────────────────────────
        df["vol_sma"]   = df["Volume"].rolling(window=VOLUME_SMA).mean()
        df["rvol"]      = df["Volume"] / df["vol_sma"].replace(0, np.nan)
        df["vol_spike"] = df["rvol"] >= RVOL_THRESHOLD

        # ── Derived ──────────────────────────────────────
        df["trend_up"]   = df["Close"] > df["ema_trend"]
        df["above_vwap"] = df["Close"] > df["vwap"]
        df["trending"]   = df["adx"] > 20
        df["sideways"]   = df["adx"] < 20

        df.dropna(subset=["ema_fast", "ema_slow", "rsi", "atr", "adx"], inplace=True)
        return df

    except Exception as e:
        log.error(f"Indicator calculation error: {e}")
        return df


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI using Wilder's smoothing method."""
    delta  = close.diff()
    gain   = delta.clip(lower=0)
    loss   = -delta.clip(upper=0)
    avg_g  = gain.ewm(com=period - 1, min_periods=period, adjust=False).mean()
    avg_l  = loss.ewm(com=period - 1, min_periods=period, adjust=False).mean()
    rs     = avg_g / avg_l.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(high: pd.Series, low: pd.Series, close: pd.Series,
         period: int = 14) -> pd.Series:
    """Average True Range."""
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, min_periods=period, adjust=False).mean()


def _adx(high: pd.Series, low: pd.Series, close: pd.Series,
         period: int = 14) -> pd.Series:
    """Average Directional Index."""
    prev_high  = high.shift(1)
    prev_low   = low.shift(1)
    prev_close = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs()
    ], axis=1).max(axis=1)

    plus_dm  = (high - prev_high).clip(lower=0)
    minus_dm = (prev_low - low).clip(lower=0)
    plus_dm  = plus_dm.where(plus_dm > minus_dm, 0)
    minus_dm = minus_dm.where(minus_dm > plus_dm, 0)

    atr14      = tr.ewm(com=period - 1, min_periods=period, adjust=False).mean()
    plus_di    = 100 * plus_dm.ewm(com=period - 1, min_periods=period, adjust=False).mean() / atr14.replace(0, np.nan)
    minus_di   = 100 * minus_dm.ewm(com=period - 1, min_periods=period, adjust=False).mean() / atr14.replace(0, np.nan)
    dx         = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(com=period - 1, min_periods=period, adjust=False).mean()


def _vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP resetting every trading day."""
    tp   = (df["High"] + df["Low"] + df["Close"]) / 3
    tpv  = tp * df["Volume"]
    vwap = pd.Series(index=df.index, dtype=float)
    for day, grp in df.groupby(df.index.date):
        idx       = grp.index
        vwap[idx] = tpv[idx].cumsum() / df.loc[idx, "Volume"].cumsum()
    return vwap


def get_stop_loss(entry: float, atr: float, gap_day: bool = False) -> float:
    """ATR-based dynamic stop loss for LONG trades."""
    mult = ATR_SL_MULT * 1.5 if gap_day else ATR_SL_MULT
    return round(entry - (mult * atr), 2)


def get_targets(entry: float, sl: float) -> dict:
    """Calculate T1 (1:1) and T2 (1:2.5) targets."""
    risk = entry - sl
    return {
        "target1": round(entry + risk * 1.0, 2),
        "target2": round(entry + risk * 2.5, 2),
        "risk":    round(risk, 2)
    }


def is_gap_day(df: pd.DataFrame, threshold: float = MAX_GAP_NORMAL) -> bool:
    """True if today's open gapped > threshold vs yesterday's close."""
    dates = df.index.normalize().unique()
    if len(dates) < 2:
        return False
    today     = dates[-1]
    yesterday = dates[-2]
    prev_data = df[df.index.normalize() == yesterday]
    today_data = df[df.index.normalize() == today]
    if prev_data.empty or today_data.empty:
        return False
    prev_close = float(prev_data["Close"].iloc[-1])
    today_open = float(today_data["Open"].iloc[0])
    return abs(today_open - prev_close) / prev_close > threshold


def get_ist_now():
    """Always returns current time in IST — never depends on system timezone."""
    from datetime import datetime
    return datetime.now(IST)
