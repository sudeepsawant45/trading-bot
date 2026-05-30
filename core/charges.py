# ============================================================
# core/charges.py — Trading Charges Calculator
# All NSE intraday charges in one place
# ============================================================
from dataclasses import dataclass

@dataclass
class ChargeBreakdown:
    brokerage:    float
    stt:          float
    exchange:     float
    gst:          float
    stamp_duty:   float
    sebi:         float
    total:        float

def calculate(entry: float, exit_price: float, qty: int) -> ChargeBreakdown:
    """
    Calculate all charges for an intraday round trip.
    All rates as per NSE/SEBI guidelines.
    """
    buy_value  = entry * qty
    sell_value = exit_price * qty
    turnover   = buy_value + sell_value

    brokerage  = 20.0 * 2                      # Rs.20 per order x 2
    stt        = sell_value * 0.00025           # 0.025% on sell side only (intraday)
    exchange   = turnover * 0.0000325           # NSE transaction charges
    gst        = brokerage * 0.18              # 18% GST on brokerage only
    stamp_duty = buy_value * 0.00003           # 0.003% on buy side
    sebi       = turnover * 0.000001           # SEBI turnover fee Rs.10/crore

    total = brokerage + stt + exchange + gst + stamp_duty + sebi

    return ChargeBreakdown(
        brokerage  = round(brokerage, 4),
        stt        = round(stt, 4),
        exchange   = round(exchange, 4),
        gst        = round(gst, 4),
        stamp_duty = round(stamp_duty, 4),
        sebi       = round(sebi, 4),
        total      = round(total, 2)
    )

def net_pnl(entry: float, exit_price: float, qty: int) -> float:
    """Quick helper: gross P&L minus all charges."""
    gross   = (exit_price - entry) * qty
    charges = calculate(entry, exit_price, qty).total
    return round(gross - charges, 2)
