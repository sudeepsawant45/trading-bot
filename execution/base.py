# ============================================================
# execution/base.py — Abstract Order Executor
# ============================================================
from abc import ABC, abstractmethod

class OrderExecutor(ABC):

    @abstractmethod
    def buy(self, symbol: str, qty: int, price: float,
            sl: float, t1: float, t2: float) -> dict:
        """Place a buy order. Returns order details."""
        ...

    @abstractmethod
    def sell(self, symbol: str, qty: int, price: float, reason: str) -> dict:
        """Place a sell/exit order."""
        ...

    @abstractmethod
    def get_positions(self) -> list:
        """Get all current open positions from broker."""
        ...
