# ============================================================
# engine/trader.py — Main Trading Engine
# Event-driven: processes on each completed candle close
# FIXES: per-symbol ORB, Nifty filter, no-trade zone,
#        completed candle check, all circuit breakers
# ============================================================
import time
from datetime import datetime, date
from zoneinfo import ZoneInfo
from infra.logger import get_logger
from infra.alerts import send_telegram, send_critical
from infra.config import (
    WATCHLIST_YF, NIFTY_SYMBOL, SCAN_SYMBOLS, SIGNAL_LOOKBACK,
    TIMEZONE, EXEC_START, ORB_END, SQUARE_OFF, MARKET_CLOSE
)
from core.indicators import calculate_all, get_stop_loss, get_targets, is_gap_day
from core.signals import (
    ORBState, orb_signal, ema_signal, rsi_divergence_signal, is_nifty_bullish
)
from core.risk import RiskManager
from data.yfinance_provider import YFinanceProvider

log    = get_logger("Trader")
IST    = ZoneInfo(TIMEZONE)

# Parse time strings
def _t(s): 
    h, m = s.split(":")
    from datetime import time as dtime
    return dtime(int(h), int(m))

T_ORB_END    = _t(ORB_END)
T_EXEC_START = _t(EXEC_START)
T_SQUARE_OFF = _t(SQUARE_OFF)
T_CLOSE      = _t(MARKET_CLOSE)


class Trader:
    """
    Main trading engine.
    Dependency injection: pass any DataProvider + OrderExecutor.
    """

    def __init__(self, executor, data_provider=None):
        self.executor  = executor
        self.data      = data_provider or YFinanceProvider()
        self.risk      = RiskManager()
        # Per-symbol ORB state — fixes the multi-symbol bug
        self.orb_states       = {sym: ORBState(sym) for sym in WATCHLIST_YF[:SCAN_SYMBOLS]}
        self.orb_set          = False
        self.nifty_df         = None
        self._last_orb_date   = None   # Ensures reset on first day regardless of start time
        self._nifty_fetched   = False  # Ensures Nifty fetched once per day
        log.info(f"Trader initialized | mode={'PAPER' if hasattr(executor, 'orders') else 'LIVE'}")

    def start(self):
        """Main loop — event-driven on candle close (approx every 5 min)."""
        log.info("=" * 55)
        log.info("TRADING ENGINE STARTED")
        log.info("Press Ctrl+C to stop")
        log.info("=" * 55)
        send_telegram("Trading session started")

        try:
            while True:
                now = datetime.now(IST).time().replace(tzinfo=None)

                # Before market — sleep until 9:10
                if now < _t("09:10"):
                    time.sleep(60)
                    continue

                # 9:15-9:30 — observe mode (fetch data, set ORB)
                elif _t("09:10") <= now < T_ORB_END:
                    self._observe_mode()
                    time.sleep(30)

                # 9:30-9:31 — set ORB levels
                elif T_ORB_END <= now < T_EXEC_START:
                    if not self.orb_set:
                        self._set_orb_levels()
                    time.sleep(15)

                # 9:31-15:15 — active trading
                elif T_EXEC_START <= now < T_SQUARE_OFF:
                    self._trading_cycle()
                    time.sleep(290)  # ~5 min between cycles (candle close)

                # 15:15 — square off all positions
                elif T_SQUARE_OFF <= now < T_CLOSE:
                    self._square_off()
                    time.sleep(60)

                # After close — end of day
                elif now >= T_CLOSE:
                    self._end_of_day()
                    break

        except KeyboardInterrupt:
            log.info("Stopping by user request...")
            self._square_off()
            self._end_of_day()

    def _observe_mode(self):
        """9:15-9:30: Fetch data and prepare. NO orders."""
        self.risk.check_new_day()
        # Reset ORB state if new day
        today = date.today()
        if not hasattr(self, '_last_orb_date') or self._last_orb_date != today:
            for orb in self.orb_states.values():
                orb.reset()
            self.orb_set         = False
            self._last_orb_date  = today
            self._nifty_fetched  = False   # Force one Nifty fetch per day
            log.info(f"New day {today} — ORB states reset")

        # Fetch Nifty ONCE per day during observe window (not every 30s)
        # NOTE: yfinance has ~5min delay for paper trading — acceptable.
        # For live trading, Kite WebSocket provides real-time data automatically.
        if not getattr(self, '_nifty_fetched', False):
            self.nifty_df = self.data.get_today(NIFTY_SYMBOL)
            if not self.nifty_df.empty:
                self.nifty_df       = calculate_all(self.nifty_df)
                self._nifty_fetched = True
                log.debug("Nifty data fetched for today")
        log.debug("Observe mode — monitoring market, no orders")

    def _set_orb_levels(self):
        """After 9:30: Set per-symbol ORB levels."""
        log.info("Setting ORB levels for all symbols...")
        for sym in list(self.orb_states.keys()):
            df = self.data.get_today(sym)
            if not df.empty:
                df = calculate_all(df)
                self.orb_states[sym].set_from_df(df)
        self.orb_set = True

    def _trading_cycle(self):
        """Main cycle on each candle close."""
        now = datetime.now(IST)
        log.debug(f"Trading cycle @ {now.strftime('%H:%M:%S')} IST")

        # Refresh Nifty ONCE per cycle — cache it
        nifty_today = self.data.get_today(NIFTY_SYMBOL)
        if not nifty_today.empty:
            self.nifty_df = calculate_all(nifty_today)

        nifty_bull = is_nifty_bullish(self.nifty_df)
        log.debug(f"Nifty bullish: {nifty_bull}")

        # ── Manage open position first ──────────────────
        if self.risk.position:
            self._manage_position(nifty_bull)
            return

        # ── Scan for new signals ────────────────────────
        if self.risk.is_shutdown:
            return

        ok, reason = self.risk.can_trade()
        if not ok:
            log.debug(f"Cannot trade: {reason}")
            return

        self._scan_signals(nifty_bull)

    def _manage_position(self, nifty_bull: bool):
        """Check exit conditions for open position."""
        sym = self.risk.position.symbol
        df  = self.data.get_today(sym)
        if df.empty:
            return

        df    = calculate_all(df)
        price = float(df["Close"].iloc[-1])

        exit_check = self.risk.check_exit(price)

        if exit_check["action"] == "PARTIAL_EXIT":
            record = self.risk.close_trade(price, exit_check["reason"], partial=True)
            if not record:
                log.error("close_trade returned empty — skipping executor call")
                return
            self.executor.sell(sym, record["exit_qty"], price, exit_check["reason"])
            send_telegram(f"PARTIAL EXIT: {sym} @ Rs.{price:.2f} | Net: Rs.{record['pnl_net']:.0f}")

        elif exit_check["action"] == "FULL_EXIT":
            record = self.risk.close_trade(price, exit_check["reason"], partial=False)
            if not record:
                log.error("close_trade returned empty — skipping executor call")
                return
            self.executor.sell(sym, record["exit_qty"], price, exit_check["reason"])
            send_telegram(
                f"EXIT: {sym} @ Rs.{price:.2f}\n"
                f"Reason: {exit_check['reason']}\n"
                f"Net P&L: Rs.{record['pnl_net']:.0f}\n"
                f"Daily P&L: Rs.{self.risk.daily_pnl:.0f}"
            )

        else:
            sig = self._get_signal(sym, df, nifty_bull)
            if sig == "EXIT":
                record = self.risk.close_trade(price, "SIGNAL_EXIT")
                if not record:
                    return
                self.executor.sell(sym, record["exit_qty"], price, "SIGNAL_EXIT")

    def _scan_signals(self, nifty_bull: bool):
        """Scan symbols for BUY signal."""
        for sym in list(self.orb_states.keys()):
            df = self.data.get_today(sym)
            if df.empty or len(df) < 60:
                continue
            df  = calculate_all(df)
            sig = self._get_signal(sym, df, nifty_bull)

            if sig == "BUY":
                self._execute_trade(sym, df)
                break   # One trade at a time

    def _get_signal(self, sym: str, df, nifty_bull: bool) -> str:
        """Get signal for one symbol using all strategies."""
        orb = self.orb_states.get(sym)
        recent = df.tail(SIGNAL_LOOKBACK)

        # ORB first (highest priority in trending market)
        if orb:
            sig = orb_signal(recent, orb, nifty_bull)
            if sig != "NONE":
                return sig

        # EMA crossover
        sig = ema_signal(recent, nifty_bull)
        if sig != "NONE":
            return sig

        # RSI divergence (sideways only)
        sig = rsi_divergence_signal(recent)
        return sig

    def _execute_trade(self, sym: str, df):
        """Execute a new trade with rollback if order placement fails."""
        gap   = is_gap_day(df)
        last  = df.iloc[-2]          # Completed candle
        entry = float(last["Close"])
        atr   = float(last["atr"])

        sl      = get_stop_loss(entry, atr, gap_day=gap)
        targets = get_targets(entry, sl)
        qty     = self.risk.position_size(entry, sl, gap_day=gap)

        if qty <= 0:
            log.warning(f"Position size 0 for {sym} — skip")
            return

        # Record position in risk manager first
        self.risk.open_trade(sym, entry, qty, sl,
                             targets["target1"], targets["target2"], "SIGNAL")

        # Place order — rollback if it fails
        order = self.executor.buy(sym, qty, entry, sl,
                                  targets["target1"], targets["target2"])

        if isinstance(order, dict) and order.get("status") == "FAILED":
            # Rollback: remove position from risk manager
            log.error(f"Order placement failed for {sym} — rolling back position")
            self.risk.close_trade(entry, "ORDER_FAILED_ROLLBACK")
            send_telegram(f"ORDER FAILED: {sym} — position rolled back. Check broker.")

    def _square_off(self):
        """15:15: Force close all open positions."""
        if not self.risk.position:
            return

        sym = self.risk.position.symbol
        df  = self.data.get_today(sym)

        if not df.empty:
            price = float(df["Close"].iloc[-1])
        else:
            # Fallback: use last known entry price (breakeven exit)
            price = self.risk.position.entry
            log.warning(f"Could not fetch price for {sym} — using entry price as fallback")
            send_critical(f"Square off data fetch failed for {sym} — used entry price {price:.2f}")

        record = self.risk.close_trade(price, "EOD_SQUARE_OFF")
        if not record:
            log.error(f"EOD square off close_trade failed for {sym}")
            return
        self.executor.sell(sym, record["exit_qty"], price, "EOD_SQUARE_OFF")
        send_telegram(f"EOD Square Off: {sym} @ Rs.{price:.2f} | P&L: Rs.{record['pnl_net']:.0f}")

    def _end_of_day(self):
        """Print and send EOD summary."""
        s = self.risk.summary()
        log.info("=" * 55)
        log.info(f"EOD | Trades: {s['trades']} | P&L: Rs.{s['daily_pnl']:,.0f} ({s['daily_pnl_pct']}%)")
        log.info("=" * 55)
        send_telegram(f"EOD Summary\nTrades: {s['trades']}\nP&L: Rs.{s['daily_pnl']:,.0f} ({s['daily_pnl_pct']}%)")
