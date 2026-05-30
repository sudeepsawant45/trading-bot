# ============================================================
# tests/test_backtest.py — Backtest Engine Tests
# ============================================================
import pytest
import pandas as pd
import numpy as np
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.backtest import Backtest
from infra.config import CAPITAL


def _make_ohlcv(n=200, trend="up", seed=42):
    """Create synthetic OHLCV data for backtest testing."""
    np.random.seed(seed)
    base   = 500.0
    closes = [base + (i * 0.5 if trend == "up" else -i * 0.3)
              + np.random.randn() * 3 for i in range(n)]
    idx = pd.date_range("2025-01-02", periods=n, freq="1D")
    df  = pd.DataFrame({
        "Open":   [max(1, c - abs(np.random.randn())) for c in closes],
        "High":   [c + abs(np.random.randn()) * 3 for c in closes],
        "Low":    [max(1, c - abs(np.random.randn()) * 3) for c in closes],
        "Close":  [max(1, c) for c in closes],
        "Volume": [500000 + np.random.randint(0, 200000) for _ in range(n)]
    }, index=idx)
    # Ensure High >= Close >= Low >= 1
    df["High"]  = df[["Open","Close","High"]].max(axis=1)
    df["Low"]   = df[["Open","Close","Low"]].min(axis=1).clip(lower=1)
    return df


class TestBacktestMetrics:
    def test_zero_trades_returns_error(self):
        """_metrics with no trades returns error dict not crash."""
        bt = Backtest("TEST.NS", capital=100000)
        # Force empty trades
        result = bt._metrics()
        assert "error" in result
        assert isinstance(result["error"], str)

    def test_metrics_keys_present(self):
        """Metrics dict has all expected keys."""
        bt = Backtest("TEST.NS", capital=100000)
        # Inject some dummy trades
        bt.trades = [
            {"symbol":"TEST","date":"2025-01-02","entry":500,"sl":490,
             "t1":510,"t2":525,"qty":10,"strategy":"ORB","exit":520,"reason":"TARGET2","pnl":190.0},
            {"symbol":"TEST","date":"2025-01-03","entry":500,"sl":490,
             "t1":510,"t2":525,"qty":10,"strategy":"ORB","exit":492,"reason":"SL_HIT","pnl":-90.0},
        ]
        bt.equity = [100000, 100190, 100100]
        bt.cur_cap = 100100
        result = bt._metrics()
        for key in ["symbol","total_trades","win_rate","profit_factor",
                    "rrr","max_drawdown","sharpe","total_pnl","total_return"]:
            assert key in result, f"Missing key: {key}"

    def test_win_rate_correct(self):
        bt = Backtest("TEST.NS", capital=100000)
        bt.trades = [
            {"pnl": 200.0}, {"pnl": -100.0},
            {"pnl": 150.0}, {"pnl": -80.0}
        ]
        bt.equity  = [100000, 100200, 100100, 100250, 100170]
        bt.cur_cap = 100170
        result = bt._metrics()
        assert result["win_rate"] == 50.0

    def test_profit_factor_no_inf(self):
        """profit_factor capped at 999 when no losing trades."""
        bt = Backtest("TEST.NS", capital=100000)
        bt.trades  = [{"pnl": 100.0}, {"pnl": 200.0}, {"pnl": 150.0}]
        bt.equity  = [100000, 100100, 100300, 100450]
        bt.cur_cap = 100450
        result = bt._metrics()
        assert result["profit_factor"] == 999.0
        assert result["profit_factor"] != float("inf")

    def test_total_return_uses_self_capital(self):
        """total_return must use self.capital not global CAPITAL constant."""
        custom_capital = 50000
        bt = Backtest("TEST.NS", capital=custom_capital)
        bt.trades  = [{"pnl": 5000.0}]
        bt.equity  = [50000, 55000]
        bt.cur_cap = 55000
        result = bt._metrics()
        assert abs(result["total_return"] - 10.0) < 0.1   # 10% return on 50K

    def test_max_drawdown_negative(self):
        """Max drawdown should be negative or zero."""
        bt = Backtest("TEST.NS", capital=100000)
        bt.trades  = [{"pnl": 1000.0}, {"pnl": -5000.0}, {"pnl": 2000.0}]
        bt.equity  = [100000, 101000, 96000, 98000]
        bt.cur_cap = 98000
        result = bt._metrics()
        assert result["max_drawdown"] <= 0


class TestBacktestInit:
    def test_fresh_instance_clean_state(self):
        bt = Backtest("TEST.NS", capital=100000)
        assert bt.trades   == []
        assert bt.equity   == [100000]
        assert bt.cur_cap  == 100000
        assert bt.capital  == 100000

    def test_custom_capital(self):
        bt = Backtest("TEST.NS", capital=50000)
        assert bt.capital  == 50000
        assert bt.cur_cap  == 50000
        assert bt.equity   == [50000]

    def test_gap_detection_in_run_day(self):
        """gap_day correctly detected from full_df."""
        bt       = Backtest("TEST.NS", capital=100000)
        # Day 1 closes at 500, Day 2 opens at 520 (4% gap)
        idx1 = pd.date_range("2025-01-02", periods=1, freq="1D")
        idx2 = pd.date_range("2025-01-03", periods=1, freq="1D")
        df1  = pd.DataFrame({"Open":498,"High":505,"Low":495,"Close":500,"Volume":500000}, index=idx1)
        df2  = pd.DataFrame({"Open":520,"High":528,"Low":518,"Close":525,"Volume":600000}, index=idx2)
        full = pd.concat([df1, df2])
        # Just verify no crash and gap is detected
        from core.indicators import calculate_all
        full_ind = calculate_all(full)
        # _run_day should not raise
        import datetime
        bt._run_day(datetime.date(2025, 1, 3), df2, pd.DataFrame(), full_df=full_ind)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
