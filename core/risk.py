# ============================================================
# core/risk.py — Risk Management Engine
# FIXES: Input validation, atomic saves, FY-aware state
# ============================================================
import threading
from datetime import datetime, date
from pathlib import Path
from infra.logger import get_logger
from infra.storage import save_json, load_json
from infra.config import (
    CAPITAL, RISK_PER_TRADE, MAX_TRADES_PER_DAY,
    DAILY_LOSS_LIMIT, DATA_DIR
)
from core.charges import calculate as calc_charges

log = get_logger("Risk")


class Position:
    """Represents a single open trade."""
    def __init__(self, symbol, entry, qty, sl, t1, t2, strategy):
        # Validate — use ValueError not assert (assert disabled by python -O flag)
        if entry <= 0:
            raise ValueError(f"Invalid entry price: {entry}")
        if sl >= entry:
            raise ValueError(f"Stop loss ({sl}) must be below entry ({entry}) for long trades")
        if t1 <= entry:
            raise ValueError(f"Target 1 ({t1}) must be above entry ({entry})")
        if t2 <= t1:
            raise ValueError(f"Target 2 ({t2}) must be above Target 1 ({t1})")
        if qty <= 0:
            raise ValueError(f"Quantity must be positive: {qty}")

        self.symbol       = symbol
        self.entry        = entry
        self.qty          = qty
        self.sl           = sl
        self.t1           = t1
        self.t2           = t2
        self.strategy     = strategy
        self.partial_done = False
        self.entry_time   = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol, "entry": self.entry, "qty": self.qty,
            "sl": self.sl, "t1": self.t1, "t2": self.t2,
            "strategy": self.strategy, "partial_done": self.partial_done,
            "entry_time": self.entry_time
        }

    def __repr__(self):
        return (f"Position({self.symbol} entry={self.entry:.2f} qty={self.qty} "
                f"sl={self.sl:.2f} t1={self.t1:.2f} t2={self.t2:.2f})")


class RiskManager:
    """Thread-safe risk management engine."""

    def __init__(self, capital: float = None):
        self._lock        = threading.Lock()
        self.capital      = capital or CAPITAL
        self.daily_pnl    = 0.0
        self.trades_today = 0
        self.is_shutdown  = False
        self.position     = None       # One position at a time
        self.trade_log    = []
        self.today        = date.today()
        self._load()
        log.info(f"RiskManager ready | Capital: Rs.{self.capital:,.0f} | Paper mode")

    def __repr__(self):
        return (f"RiskManager(capital={self.capital:.0f} daily_pnl={self.daily_pnl:.0f} "
                f"trades={self.trades_today} shutdown={self.is_shutdown})")

    # ── New Day ───────────────────────────────────────────
    def check_new_day(self):
        with self._lock:
            today = date.today()
            if today != self.today:
                log.info(f"New day: {today} — resetting counters")
                self.daily_pnl    = 0.0
                self.trades_today = 0
                self.is_shutdown  = False
                self.today        = today
                self._save()

    # ── Position Sizing ───────────────────────────────────
    def position_size(self, entry: float, sl: float, gap_day: bool = False) -> int:
        """
        Calculate shares to buy.
        Formula: (Capital * Risk%) / (Entry - SL + slippage buffer)
        """
        if sl >= entry:
            log.error(f"Invalid: SL {sl} >= Entry {entry}")
            return 0

        risk_amt   = self.capital * RISK_PER_TRADE
        risk_share = (entry - sl) + (entry * 0.003)   # +0.3% slippage buffer
        size       = int(risk_amt / risk_share)
        size       = max(1, size // 2 if gap_day else size)

        log.info(f"Position size: {size} shares | entry={entry:.2f} sl={sl:.2f} "
                 f"risk=Rs.{risk_amt:.0f} gap={gap_day}")
        return size

    # ── Can Trade? ────────────────────────────────────────
    def can_trade(self) -> tuple[bool, str]:
        with self._lock:
            if self.is_shutdown:
                return False, "System shutdown — daily loss limit hit"
            if self.position is not None:
                return False, f"Already in: {self.position.symbol}"
            if self.trades_today >= MAX_TRADES_PER_DAY:
                return False, f"Max trades: {self.trades_today}/{MAX_TRADES_PER_DAY}"
            loss_pct = abs(self.daily_pnl) / self.capital if self.daily_pnl < 0 else 0
            if loss_pct >= DAILY_LOSS_LIMIT:
                self.is_shutdown = True
                log.critical(f"DAILY LOSS LIMIT HIT: {loss_pct*100:.1f}% — Shutdown!")
                return False, f"Daily loss limit: Rs.{self.daily_pnl:.0f}"
            return True, "OK"

    # ── Open Trade ────────────────────────────────────────
    def open_trade(self, symbol, entry, qty, sl, t1, t2, strategy) -> Position:
        with self._lock:
            pos = Position(symbol, entry, qty, sl, t1, t2, strategy)
            self.position      = pos
            self.trades_today += 1
            log.info(f"OPENED: {pos}")
            self._save()
            return pos

    # ── Check Exit ────────────────────────────────────────
    def check_exit(self, price: float) -> dict:
        with self._lock:
            if self.position is None:
                return {"action": "NONE"}
            p = self.position
            if price <= p.sl:
                return {"action": "FULL_EXIT",    "reason": "SL_HIT",  "price": price}
            if price >= p.t2:
                return {"action": "FULL_EXIT",    "reason": "TARGET2", "price": price}
            if price >= p.t1 and not p.partial_done:
                return {"action": "PARTIAL_EXIT", "reason": "TARGET1", "price": price}
            return {"action": "NONE"}

    # ── Close Trade ───────────────────────────────────────
    def close_trade(self, exit_price: float, reason: str, partial: bool = False) -> dict:
        with self._lock:
            if self.position is None:
                log.warning("close_trade() called with no open position")
                return {}

            p        = self.position
            exit_qty = p.qty // 2 if partial else p.qty

            # Fix: ensure even split is tracked correctly
            if partial and p.qty == 1:
                log.warning("Cannot partial exit qty=1 — doing full exit")
                partial  = False
                exit_qty = 1

            charges  = calc_charges(p.entry, exit_price, exit_qty).total
            gross    = (exit_price - p.entry) * exit_qty
            net      = round(gross - charges, 2)
            self.daily_pnl += net

            record = {
                **p.to_dict(),
                "exit_price": exit_price,
                "exit_qty":   exit_qty,
                "exit_time":  datetime.now().isoformat(),
                "reason":     reason,
                "pnl_gross":  round(gross, 2),
                "charges":    round(charges, 2),
                "pnl_net":    net,
                "daily_pnl":  round(self.daily_pnl, 2),
                "partial":    partial
            }
            self.trade_log.append(record)

            if partial:
                remaining = p.qty - exit_qty
                self.position.qty          = remaining
                self.position.partial_done = True
                self.position.sl           = p.entry
                log.info(f"PARTIAL EXIT {p.symbol} @ {exit_price:.2f} | "
                         f"qty={exit_qty} net=Rs.{net:.0f} | remaining={remaining}")
            else:
                log.info(f"CLOSED {p.symbol} @ {exit_price:.2f} | "
                         f"reason={reason} net=Rs.{net:.0f} | daily=Rs.{self.daily_pnl:.0f}")
                self.position = None

            self._save()

        # TaxTracker called OUTSIDE lock — file I/O must never be inside mutex
        try:
            from reporting.tax import TaxTracker
            TaxTracker().record_trade(net)
        except Exception as e:
            log.warning(f"Tax tracker update failed (non-critical): {e}")

        return record

    # ── Summary ───────────────────────────────────────────
    def summary(self) -> dict:
        with self._lock:
            return {
                "date":          str(self.today),
                "capital":       self.capital,
                "trades":        self.trades_today,
                "daily_pnl":     round(self.daily_pnl, 2),
                "daily_pnl_pct": round(self.daily_pnl / self.capital * 100, 2),
                "is_shutdown":   self.is_shutdown,
                "has_position":  self.position is not None,
                "trade_log":     list(self.trade_log)   # Copy — prevent external mutation
            }

    # ── Persistence (Atomic) ──────────────────────────────
    def _save(self):
        from infra.config import DATA_DIR
        path = Path(DATA_DIR) / f"state_{self.today}.json"
        save_json({
            "daily_pnl":    self.daily_pnl,
            "trades_today": self.trades_today,
            "is_shutdown":  self.is_shutdown,
            "trade_log":    self.trade_log,
            "position":     self.position.to_dict() if self.position else None
        }, path)

    def _load(self):
        from infra.config import DATA_DIR
        path  = Path(DATA_DIR) / f"state_{self.today}.json"
        state = load_json(path)
        if not state:
            return
        self.daily_pnl    = state.get("daily_pnl", 0.0)
        self.trades_today = state.get("trades_today", 0)
        self.is_shutdown  = state.get("is_shutdown", False)
        self.trade_log    = state.get("trade_log", [])

        # Reconstruct Position object from saved dict — critical after restart
        pos_data = state.get("position")
        if pos_data:
            try:
                self.position = Position(
                    symbol   = pos_data["symbol"],
                    entry    = pos_data["entry"],
                    qty      = pos_data["qty"],
                    sl       = pos_data["sl"],
                    t1       = pos_data["t1"],
                    t2       = pos_data["t2"],
                    strategy = pos_data.get("strategy", "UNKNOWN")
                )
                self.position.partial_done = pos_data.get("partial_done", False)
                self.position.entry_time   = pos_data.get("entry_time", "")
                log.warning(f"Restored open position from disk: {self.position}")
            except (KeyError, ValueError) as e:
                log.error(f"Could not restore position from disk: {e} — treating as no position")
                self.position = None

        log.info(f"Loaded state — P&L: Rs.{self.daily_pnl:.0f} | Trades: {self.trades_today} | Position: {self.position is not None}")
