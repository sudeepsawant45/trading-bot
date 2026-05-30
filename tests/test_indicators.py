# ============================================================
# tests/test_indicators.py — Indicator Tests
# ============================================================
import pytest
import pandas as pd
import numpy as np
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.indicators import (
    calculate_all, get_stop_loss, get_targets, is_gap_day, _vwap
)
from infra.config import ATR_SL_MULT


def _ohlcv(n=120, trend="up", seed=42):
    np.random.seed(seed)
    base   = 500.0
    closes = [base + (i * 0.3 if trend == "up" else -i * 0.3)
              + np.random.randn() * 2 for i in range(n)]
    idx = pd.date_range("2025-01-02 09:15", periods=n, freq="5min")
    return pd.DataFrame({
        "Open":   [c - abs(np.random.randn()) for c in closes],
        "High":   [c + abs(np.random.randn()) * 2 for c in closes],
        "Low":    [c - abs(np.random.randn()) * 2 for c in closes],
        "Close":  closes,
        "Volume": [100000 + np.random.randint(0, 50000) for _ in range(n)]
    }, index=idx)


class TestCalculateAll:
    def test_all_columns_added(self):
        df     = _ohlcv(120)
        result = calculate_all(df)
        for col in ["ema_fast","ema_slow","ema_trend","rsi","atr",
                    "vwap","adx","rvol","vol_spike","trend_up","above_vwap"]:
            assert col in result.columns, f"Missing: {col}"

    def test_empty_df_returns_empty(self):
        result = calculate_all(pd.DataFrame())
        assert result.empty

    def test_insufficient_data_returns_unchanged(self):
        df     = _ohlcv(10)   # Too short for EMA_TREND=50
        result = calculate_all(df)
        assert result.empty or len(result) <= len(df)

    def test_no_nans_in_output(self):
        df     = _ohlcv(120)
        result = calculate_all(df)
        for col in ["ema_fast","ema_slow","rsi","atr"]:
            assert result[col].notna().all(), f"NaN in {col}"

    def test_rvol_is_positive(self):
        df     = _ohlcv(120)
        result = calculate_all(df)
        assert (result["rvol"] >= 0).all()

    def test_trend_up_is_boolean(self):
        df     = _ohlcv(120)
        result = calculate_all(df)
        assert result["trend_up"].dtype == bool or result["trend_up"].isin([True, False]).all()

    def test_vwap_no_date_variable_shadow(self):
        """Ensure _vwap uses 'day' not 'date' — no shadowing."""
        import inspect
        src = inspect.getsource(_vwap)
        assert "for day," in src, "Loop variable should be 'day' not 'date'"
        assert "for date," not in src, "Loop variable 'date' shadows datetime.date import"


class TestStopLoss:
    def test_sl_below_entry_long(self):
        sl = get_stop_loss(500.0, 10.0)
        assert sl < 500.0

    def test_sl_formula(self):
        sl = get_stop_loss(500.0, 10.0, gap_day=False)
        assert abs(sl - (500.0 - ATR_SL_MULT * 10.0)) < 0.01

    def test_gap_day_wider_sl(self):
        normal = get_stop_loss(500.0, 10.0, gap_day=False)
        gap    = get_stop_loss(500.0, 10.0, gap_day=True)
        assert gap < normal

    def test_sl_rounded_to_2dp(self):
        sl = get_stop_loss(500.123, 9.876)
        assert sl == round(sl, 2)


class TestTargets:
    def test_t1_is_1to1(self):
        t = get_targets(500.0, 490.0)
        assert t["target1"] == 510.0

    def test_t2_is_2point5to1(self):
        t = get_targets(500.0, 490.0)
        assert t["target2"] == 525.0

    def test_risk_is_correct(self):
        t = get_targets(500.0, 490.0)
        assert t["risk"] == 10.0

    def test_both_targets_above_entry(self):
        t = get_targets(1000.0, 975.0)
        assert t["target1"] > 1000.0
        assert t["target2"] > t["target1"]


class TestGapDay:
    def test_gap_day_detected(self):
        # Day 1: close at 500. Day 2: open at 510 (2% gap)
        idx1 = pd.date_range("2025-01-02 09:15", periods=5, freq="5min")
        idx2 = pd.date_range("2025-01-03 09:15", periods=5, freq="5min")
        df1  = pd.DataFrame({"Open":500,"High":505,"Low":495,"Close":500,"Volume":100000}, index=idx1)
        df2  = pd.DataFrame({"Open":510,"High":515,"Low":508,"Close":512,"Volume":100000}, index=idx2)
        df   = pd.concat([df1, df2])
        assert is_gap_day(df, threshold=0.01) == True

    def test_no_gap_day(self):
        idx1 = pd.date_range("2025-01-02 09:15", periods=5, freq="5min")
        idx2 = pd.date_range("2025-01-03 09:15", periods=5, freq="5min")
        df1  = pd.DataFrame({"Open":500,"High":505,"Low":495,"Close":500,"Volume":100000}, index=idx1)
        df2  = pd.DataFrame({"Open":501,"High":506,"Low":499,"Close":502,"Volume":100000}, index=idx2)
        df   = pd.concat([df1, df2])
        assert is_gap_day(df, threshold=0.01) == False

    def test_single_day_no_gap(self):
        df = _ohlcv(10)
        assert is_gap_day(df) == False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
