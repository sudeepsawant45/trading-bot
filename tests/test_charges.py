# ============================================================
# tests/test_charges.py — Charges Calculator Tests
# ============================================================
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.charges import calculate, net_pnl, ChargeBreakdown


class TestCalculate:
    def test_returns_charge_breakdown(self):
        result = calculate(500.0, 520.0, 100)
        assert isinstance(result, ChargeBreakdown)

    def test_all_components_positive(self):
        c = calculate(500.0, 520.0, 100)
        assert c.brokerage > 0
        assert c.stt       > 0
        assert c.exchange  > 0
        assert c.gst       > 0
        assert c.stamp_duty> 0
        assert c.sebi      > 0
        assert c.total     > 0

    def test_brokerage_is_fixed_40(self):
        """Rs.20 x 2 orders = Rs.40 brokerage."""
        c = calculate(500.0, 520.0, 100)
        assert abs(c.brokerage - 40.0) < 0.01

    def test_stt_on_sell_side_only(self):
        """STT = 0.025% on sell value only."""
        c = calculate(500.0, 520.0, 100)
        expected_stt = 520.0 * 100 * 0.00025
        assert abs(c.stt - expected_stt) < 0.01

    def test_gst_on_brokerage_only(self):
        """GST = 18% on brokerage only."""
        c = calculate(500.0, 520.0, 100)
        expected_gst = 40.0 * 0.18
        assert abs(c.gst - expected_gst) < 0.01

    def test_stamp_duty_on_buy_side(self):
        """Stamp duty = 0.003% on buy value."""
        c = calculate(500.0, 520.0, 100)
        expected = 500.0 * 100 * 0.00003
        assert abs(c.stamp_duty - expected) < 0.01

    def test_sebi_charge_present(self):
        """SEBI = Rs.10 per crore = 0.000001 of turnover."""
        c = calculate(500.0, 520.0, 100)
        turnover = (500.0 + 520.0) * 100
        expected_sebi = turnover * 0.000001
        assert abs(c.sebi - expected_sebi) < 0.001

    def test_total_is_sum_of_components(self):
        c = calculate(500.0, 520.0, 100)
        expected = c.brokerage + c.stt + c.exchange + c.gst + c.stamp_duty + c.sebi
        assert abs(c.total - round(expected, 2)) < 0.01

    def test_charges_scale_with_qty(self):
        """Larger qty = larger charges (except fixed brokerage)."""
        c_small = calculate(500.0, 520.0, 10)
        c_large = calculate(500.0, 520.0, 1000)
        assert c_large.total > c_small.total

    def test_realistic_charge_range(self):
        """For Rs.500 stock, 100 shares — charges should be Rs.60-200."""
        c = calculate(500.0, 510.0, 100)
        assert 50 <= c.total <= 250, f"Unusual charges: {c.total}"


class TestNetPnl:
    def test_profitable_trade_net_less_than_gross(self):
        gross = (520.0 - 500.0) * 100   # Rs.2000
        net   = net_pnl(500.0, 520.0, 100)
        assert net < gross
        assert net > 0   # Still profitable after charges

    def test_loss_trade_net_worse_than_gross(self):
        gross = (480.0 - 500.0) * 100   # -Rs.2000
        net   = net_pnl(500.0, 480.0, 100)
        assert net < gross   # More negative after charges

    def test_breakeven_trade_is_loss(self):
        """Entry == Exit means gross=0 but charges make it a loss."""
        net = net_pnl(500.0, 500.0, 100)
        assert net < 0

    def test_net_pnl_rounded(self):
        net = net_pnl(500.123, 520.456, 73)
        assert net == round(net, 2)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
