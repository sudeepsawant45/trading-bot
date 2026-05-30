# ============================================================
# tests/test_risk.py — Risk Manager Tests
# Run: pytest tests/ -v
# ============================================================
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.risk import RiskManager, Position
from core.charges import calculate, net_pnl
from core.indicators import get_stop_loss, get_targets


class TestPosition:
    def test_valid_position(self):
        p = Position("RELIANCE", 2850, 50, 2810, 2890, 2960, "ORB")
        assert p.symbol == "RELIANCE"
        assert p.entry == 2850

    def test_sl_above_entry_rejected(self):
        with pytest.raises(ValueError):
            Position("RELIANCE", 2850, 50, 2900, 2890, 2960, "ORB")

    def test_t1_below_entry_rejected(self):
        with pytest.raises(ValueError):
            Position("RELIANCE", 2850, 50, 2810, 2800, 2960, "ORB")

    def test_t2_below_t1_rejected(self):
        with pytest.raises(ValueError):
            Position("RELIANCE", 2850, 50, 2810, 2890, 2850, "ORB")

    def test_zero_qty_rejected(self):
        with pytest.raises(ValueError):
            Position("RELIANCE", 2850, 0, 2810, 2890, 2960, "ORB")


class TestPositionSizing:
    def setup_method(self):
        self.rm = RiskManager(capital=100000)
        # Clear disk state — test isolation
        self.rm.position     = None
        self.rm.daily_pnl    = 0.0
        self.rm.trades_today = 0
        self.rm.is_shutdown  = False

    def test_basic_sizing(self):
        size = self.rm.position_size(500, 490)
        assert 85 <= size <= 105

    def test_gap_day_halves_size(self):
        normal = self.rm.position_size(500, 490, gap_day=False)
        gap    = self.rm.position_size(500, 490, gap_day=True)
        assert gap <= normal // 2 + 1

    def test_sl_above_entry_returns_zero(self):
        assert self.rm.position_size(500, 510) == 0

    def test_minimum_one_share(self):
        rm = RiskManager(capital=500)
        assert rm.position_size(500, 490) >= 1


class TestCircuitBreakers:

    def _fresh(self):
        """Create RiskManager with clean state — ignores any disk state."""
        rm = RiskManager(capital=100000)
        rm.position     = None
        rm.daily_pnl    = 0.0
        rm.trades_today = 0
        rm.is_shutdown  = False
        return rm

    def test_shutdown_on_daily_loss(self):
        rm = self._fresh()
        rm.daily_pnl = -3100
        ok, reason = rm.can_trade()
        assert not ok
        assert "loss" in reason.lower()

    def test_max_trades_blocks(self):
        rm = self._fresh()
        rm.trades_today = 5
        ok, _ = rm.can_trade()
        assert not ok

    def test_open_position_blocks(self):
        rm = self._fresh()
        rm.open_trade("REL", 2850, 50, 2810, 2890, 2960, "ORB")
        ok, _ = rm.can_trade()
        assert not ok

    def test_clean_state_allows_trade(self):
        rm = self._fresh()
        ok, reason = rm.can_trade()
        assert ok and reason == "OK"


class TestTradeLifecycle:
    def test_full_trade_profitable(self):
        rm  = RiskManager(capital=100000)
        sl  = get_stop_loss(2850, 25)
        tgt = get_targets(2850, sl)
        rm.open_trade("REL", 2850, 50, sl, tgt["target1"], tgt["target2"], "ORB")
        rec = rm.close_trade(2950, "TARGET2")
        assert rec["pnl_gross"] > 0
        assert rec["pnl_net"]   < rec["pnl_gross"]   # Charges deducted
        assert rec["pnl_net"]   > 0

    def test_sl_trade_is_loss(self):
        rm  = RiskManager(capital=100000)
        rm.open_trade("REL", 2850, 50, 2810, 2890, 2960, "ORB")
        rec = rm.close_trade(2810, "SL_HIT")
        assert rec["pnl_net"] < 0

    def test_partial_exit_leaves_position_open(self):
        rm  = RiskManager(capital=100000)
        rm.open_trade("REL", 2850, 10, 2810, 2890, 2960, "ORB")
        rm.close_trade(2890, "TARGET1", partial=True)
        assert rm.position is not None
        assert rm.position.sl == 2850  # SL moved to breakeven

    def test_partial_exit_qty_1_does_full_exit(self):
        rm = RiskManager(capital=100000)
        rm.open_trade("REL", 500, 1, 490, 510, 525, "ORB")
        rm.close_trade(510, "TARGET1", partial=True)
        assert rm.position is None  # Full exit when qty=1


class TestPositionRestore:
    def test_position_restored_as_object_not_dict(self):
        """After restart, position must be Position object — not raw dict."""
        rm = RiskManager(capital=100000)
        rm.open_trade("RELIANCE", 2850.0, 50, 2810.0, 2890.0, 2960.0, "ORB")
        # Simulate restart
        rm2 = RiskManager(capital=100000)
        if rm2.position is not None:
            assert hasattr(rm2.position, 'symbol'), "Must be Position object, not dict"
            assert hasattr(rm2.position, 'entry')
            assert hasattr(rm2.position, 'sl')
            assert isinstance(rm2.position.symbol, str)

    def test_check_exit_works_after_restore(self):
        """check_exit must not raise AttributeError on restored position."""
        rm = RiskManager(capital=100000)
        rm.open_trade("TCS", 3500.0, 10, 3460.0, 3540.0, 3600.0, "EMA")
        rm2 = RiskManager(capital=100000)
        if rm2.position is not None:
            result = rm2.check_exit(3460.0)
            assert "action" in result


class TestCharges:
    def test_charges_positive(self):
        c = calculate(500, 520, 100)
        assert c.total > 0

    def test_sebi_charges_included(self):
        c = calculate(500, 520, 100)
        assert c.sebi > 0

    def test_stt_on_sell_only(self):
        c = calculate(500, 520, 100)
        expected_stt = 520 * 100 * 0.00025
        assert abs(c.stt - expected_stt) < 0.01

    def test_net_pnl_less_than_gross(self):
        gross = (520 - 500) * 100
        net   = net_pnl(500, 520, 100)
        assert net < gross

    def test_charges_in_range(self):
        c = calculate(500, 510, 100)
        assert 50 <= c.total <= 250


class TestStopLossTargets:
    def test_sl_below_entry(self):
        assert get_stop_loss(500, 10) < 500

    def test_gap_wider_sl(self):
        normal = get_stop_loss(500, 10, False)
        gap    = get_stop_loss(500, 10, True)
        assert gap < normal

    def test_t1_is_1to1_rrr(self):
        t = get_targets(500, 490)
        assert t["target1"] == 510.0

    def test_t2_is_2point5_rrr(self):
        t = get_targets(500, 490)
        assert t["target2"] == 525.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
