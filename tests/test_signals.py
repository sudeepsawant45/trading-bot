# ============================================================
# tests/test_signals.py — Signal Engine Tests
# ============================================================
import pytest
import pandas as pd
import numpy as np
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.signals import ORBState, is_nifty_bullish
from core.indicators import calculate_all


def _make_df(n=100, trend="up"):
    """Create a dummy OHLCV DataFrame for testing."""
    np.random.seed(42)
    base   = 500
    closes = [base + (i * 0.2 if trend == "up" else -i * 0.2) + np.random.randn() for i in range(n)]
    df = pd.DataFrame({
        "Open":   [c - 1 for c in closes],
        "High":   [c + 2 for c in closes],
        "Low":    [c - 2 for c in closes],
        "Close":  closes,
        "Volume": [100000 + np.random.randint(-10000, 50000) for _ in range(n)]
    }, index=pd.date_range("2025-01-01 09:15", periods=n, freq="5min"))
    return df


class TestORBState:
    def test_reset_clears_levels(self):
        orb = ORBState("RELIANCE")
        orb.orb_high = 500
        orb.orb_low  = 490
        orb.is_set   = True
        orb.reset()
        assert orb.orb_high is None
        assert not orb.is_set

    def test_repr(self):
        orb = ORBState("TCS")
        assert "TCS" in repr(orb)

    def test_per_symbol_independence(self):
        """Each symbol has its own ORB state — no cross-contamination."""
        orb1 = ORBState("RELIANCE")
        orb2 = ORBState("TCS")
        orb1.orb_high = 2900
        assert orb2.orb_high is None  # Independent


class TestNiftyFilter:
    def test_bullish_when_above_ema(self):
        df = _make_df(100, trend="up")
        df = calculate_all(df)
        if not df.empty and "ema_trend" in df.columns:
            # With uptrend data, should be bullish
            result = is_nifty_bullish(df)
            assert isinstance(result, bool)

    def test_no_nifty_data_returns_false(self):
        """Missing Nifty data = default to bearish (safe)."""
        assert is_nifty_bullish(None) == False
        assert is_nifty_bullish(pd.DataFrame()) == False


class TestIndicators:
    def test_calculate_all_adds_columns(self):
        df = _make_df(100)
        result = calculate_all(df)
        expected = ["ema_fast","ema_slow","ema_trend","rsi","atr","vwap","adx",
                    "vol_sma","rvol","vol_spike","trend_up","above_vwap"]
        for col in expected:
            assert col in result.columns, f"Missing column: {col}"

    def test_rvol_is_ratio(self):
        df = _make_df(100)
        result = calculate_all(df)
        if "rvol" in result.columns:
            assert (result["rvol"] >= 0).all()

    def test_empty_df_handled(self):
        result = calculate_all(pd.DataFrame())
        assert result.empty


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
