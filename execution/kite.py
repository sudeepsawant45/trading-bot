# ============================================================
# execution/kite.py — Live Kite Order Executor
# ONLY activate after SEBI algo approval from Zerodha
# ============================================================
from execution.base import OrderExecutor
from infra.logger import get_logger
from infra.alerts import send_critical

log = get_logger("KiteExecutor")

class KiteExecutor(OrderExecutor):
    """
    Live order executor via Zerodha Kite Connect.
    Uses Bracket Orders — SL lives at broker, not local system.
    """

    def __init__(self, kite):
        self.kite = kite
        log.warning("LIVE EXECUTOR ACTIVE — REAL MONEY AT RISK")
        send_critical("Live trading executor activated")

    def buy(self, symbol, qty, price, sl, t1, t2) -> dict:
        """Place Bracket Order — entry + SL + target at broker level."""
        try:
            sl_pts = round(price - sl, 2)
            t2_pts = round(t2 - price, 2)
            order_id = self.kite.place_order(
                variety         = "bo",          # Bracket Order
                exchange        = "NSE",
                tradingsymbol   = symbol,
                transaction_type= "BUY",
                quantity        = qty,
                order_type      = "LIMIT",
                price           = price,
                squareoff       = t2_pts,
                stoploss        = sl_pts,
                product         = "MIS"          # Intraday
            )
            log.info(f"LIVE BUY placed: {symbol} qty={qty} @ {price:.2f} | order_id={order_id}")
            return {"order_id": order_id, "status": "PLACED"}
        except Exception as e:
            log.error(f"BUY order failed: {e}")
            send_critical(f"ORDER FAILED: {symbol} BUY | {e}")
            return {"status": "FAILED", "error": str(e)}

    def sell(self, symbol, qty, price, reason) -> dict:
        try:
            order_id = self.kite.place_order(
                variety          = "regular",
                exchange         = "NSE",
                tradingsymbol    = symbol,
                transaction_type = "SELL",
                quantity         = qty,
                order_type       = "MARKET",    # Market for exits
                product          = "MIS"
            )
            log.info(f"LIVE SELL: {symbol} qty={qty} reason={reason} | order_id={order_id}")
            return {"order_id": order_id, "status": "PLACED"}
        except Exception as e:
            log.error(f"SELL order failed: {e}")
            send_critical(f"EXIT ORDER FAILED: {symbol} | {e}")
            return {"status": "FAILED", "error": str(e)}

    def get_positions(self) -> list:
        try:
            return self.kite.positions().get("net", [])
        except Exception as e:
            log.error(f"get_positions failed: {e}")
            return []
