# ============================================================
# execution/paper.py — Paper Trading Executor
# Simulates orders without real money
# ============================================================
from execution.base import OrderExecutor
from infra.logger import get_logger
from infra.alerts import send_telegram

log = get_logger("PaperExecutor")

class PaperExecutor(OrderExecutor):
    """Simulates order execution — no real money."""

    def __init__(self):
        self.orders = []
        log.info("Paper executor active — NO REAL ORDERS")

    def buy(self, symbol, qty, price, sl, t1, t2) -> dict:
        order = {
            "type": "BUY", "symbol": symbol, "qty": qty,
            "price": price, "sl": sl, "t1": t1, "t2": t2,
            "status": "SIMULATED"
        }
        self.orders.append(order)
        if len(self.orders) > 500:   # Prevent unbounded growth
            self.orders = self.orders[-500:]
        msg = (f"[PAPER] BUY {symbol}\n"
               f"Qty: {qty} @ Rs.{price:.2f}\n"
               f"SL: Rs.{sl:.2f} | T1: Rs.{t1:.2f} | T2: Rs.{t2:.2f}")
        log.info(msg)
        send_telegram(msg)
        return order

    def sell(self, symbol, qty, price, reason) -> dict:
        order = {
            "type": "SELL", "symbol": symbol, "qty": qty,
            "price": price, "reason": reason, "status": "SIMULATED"
        }
        self.orders.append(order)
        msg = f"[PAPER] SELL {symbol} | Qty: {qty} @ Rs.{price:.2f} | {reason}"
        log.info(msg)
        send_telegram(msg)
        return order

    def get_positions(self) -> list:
        return []   # Paper trading has no broker positions
