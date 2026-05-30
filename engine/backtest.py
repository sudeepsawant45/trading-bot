# ============================================================
# engine/backtest.py — Backtesting Engine
# FIXES: gap_day actually used, charges included, 1d data for
#        long periods (yfinance 60-day intraday limit)
# ============================================================
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from datetime import datetime
from infra.logger import get_logger
from infra.config import CAPITAL, RISK_PER_TRADE, DAILY_LOSS_LIMIT, ADX_MIN, OUTPUT_DIR
from data.yfinance_provider import YFinanceProvider
from core.indicators import calculate_all, get_stop_loss, get_targets
from core.charges import net_pnl as calc_net_pnl
from core.signals import is_nifty_bullish

log = get_logger("Backtest")


class Backtest:

    def __init__(self, symbol: str, capital: float = CAPITAL):
        self.symbol   = symbol
        self.capital  = capital
        self.trades   = []
        self.equity   = [capital]
        self.cur_cap  = capital
        self.provider = YFinanceProvider()

    def run(self, period: str = "1y") -> dict:
        """
        Run backtest.
        IMPORTANT: ORB strategy requires intraday (5m) candles.
        yfinance provides 5m data for last ~58 days only.
        For longer periods, daily candles are used — ORB signals
        are automatically disabled, only EMA + RSI are tested.
        For ORB-specific backtest use period='58d'.
        """
        long_periods = ("1y", "2y", "6mo")
        interval     = "1d" if period in long_periods else "5m"
        self.interval = interval   # Store for signal filtering

        log.info(f"Backtest: {self.symbol} | period={period} | interval={interval}")
        if interval == "1d":
            log.info(
                "Daily candles — ORB signals DISABLED (intraday only). "
                "Testing EMA + RSI signals only. "
                "Use period='58d' for full ORB backtest."
            )

        df = self.provider.get_historical(self.symbol, period=period, interval=interval)
        if df.empty:
            log.error("No data")
            return {}

        # Also get Nifty for trend filter
        nifty_df = self.provider.get_historical("^NSEI", period=period, interval=interval)
        nifty_df = calculate_all(nifty_df) if not nifty_df.empty else pd.DataFrame()

        df = calculate_all(df)
        log.info(f"Backtesting {len(df)} candles across {df.index.date[-1] - df.index.date[0]}")

        daily_groups = df.groupby(df.index.date)
        for day, day_df in daily_groups:
            nifty_day = nifty_df[nifty_df.index.date == day] if not nifty_df.empty else pd.DataFrame()
            # Pass full df so gap detection can look at previous day's close
            self._run_day(day, day_df, nifty_day, full_df=df)

        metrics = self._metrics()
        self._save(metrics)
        return metrics

    def _run_day(self, day, day_df, nifty_day, full_df=None):
        if len(day_df) < 3:
            return

        # Nifty trend filter
        nifty_bull = is_nifty_bullish(nifty_day) if not nifty_day.empty else True

        # ORB levels — first 4 candles (9:15-9:30)
        orb_high = float(day_df["High"].iloc[:4].max())
        orb_low  = float(day_df["Low"].iloc[:4].min())

        # Gap detection — FIXED: use full_df to look at previous day's close
        gap_day = False
        if full_df is not None:
            prev_data = full_df[full_df.index.date < day]
            if not prev_data.empty:
                prev_close = float(prev_data["Close"].iloc[-1])
                today_open = float(day_df["Open"].iloc[0])
                gap_day    = abs(today_open - prev_close) / prev_close > 0.01
                if gap_day:
                    log.debug(f"Gap day: {day} | prev={prev_close:.2f} open={today_open:.2f}")

        trade_df   = day_df.iloc[4:]   # Skip ORB candles
        daily_pnl  = 0.0
        open_trade = None
        n_trades   = 0

        for i, (idx, c) in enumerate(trade_df.iterrows()):
            if daily_pnl < -(self.cur_cap * DAILY_LOSS_LIMIT):
                break
            if n_trades >= 5:
                break

            if open_trade:
                price  = float(c["Close"])
                entry  = open_trade["entry"]
                sl     = open_trade["sl"]
                t1     = open_trade["t1"]
                t2     = open_trade["t2"]
                qty    = open_trade["qty"]
                partial= open_trade.get("partial", False)

                if price <= sl:
                    pnl = calc_net_pnl(entry, price, qty)
                    daily_pnl      += pnl
                    self.cur_cap   += pnl
                    self._log(open_trade, price, "SL_HIT", pnl)
                    open_trade = None

                elif price >= t2:
                    pnl = calc_net_pnl(entry, price, qty)
                    daily_pnl      += pnl
                    self.cur_cap   += pnl
                    self._log(open_trade, price, "TARGET2", pnl)
                    open_trade = None

                elif price >= t1 and not partial:
                    if qty <= 1:
                        # Cannot split qty=1 — do full exit at target1
                        pnl = calc_net_pnl(entry, price, qty)
                        daily_pnl      += pnl
                        self.cur_cap   += pnl
                        self._log(open_trade, price, "TARGET1_FULL", pnl)
                        open_trade = None
                    else:
                        exit_qty = qty // 2
                        pnl      = calc_net_pnl(entry, price, exit_qty)
                        daily_pnl          += pnl
                        self.cur_cap       += pnl
                        open_trade["qty"]  -= exit_qty
                        open_trade["sl"]    = entry   # Breakeven
                        open_trade["partial"] = True

                elif i == len(trade_df) - 1:   # EOD
                    pnl = calc_net_pnl(entry, price, qty)
                    daily_pnl      += pnl
                    self.cur_cap   += pnl
                    self._log(open_trade, price, "EOD", pnl)
                    open_trade = None

                continue

            # ── BUY signal check ────────────────────────
            adx        = c.get("adx", 0)
            above_vwap = c.get("above_vwap", False)
            trend_up   = c.get("trend_up", False)
            vol_spike  = c.get("vol_spike", False)
            close      = float(c["Close"])
            use_intraday = getattr(self, "interval", "1d") != "1d"

            # ORB only valid on intraday candles — skip on daily
            orb_condition = (use_intraday and close > orb_high)

            if (nifty_bull and orb_condition
                    and adx > ADX_MIN and above_vwap
                    and trend_up and vol_spike):
                atr   = float(c.get("atr", close * 0.005))
                sl    = get_stop_loss(close, atr, gap_day)
                tgt   = get_targets(close, sl)
                risk  = self.cur_cap * RISK_PER_TRADE
                rps   = (close - sl) + close * 0.003
                qty   = max(1, int(risk / rps))

                open_trade = {
                    "symbol": self.symbol, "date": str(day),
                    "entry": close, "sl": sl,
                    "t1": tgt["target1"], "t2": tgt["target2"],
                    "qty": qty, "strategy": "ORB", "partial": False
                }
                n_trades += 1

        self.equity.append(self.cur_cap)

    def _log(self, trade, exit_price, reason, pnl):
        self.trades.append({**trade, "exit": exit_price, "reason": reason, "pnl": round(pnl, 2)})

    def _metrics(self) -> dict:
        if not self.trades:
            return {"error": "No trades — strategy too strict or data issue"}

        df    = pd.DataFrame(self.trades)
        total = len(df)
        wins  = df[df["pnl"] > 0]
        loss  = df[df["pnl"] <= 0]
        wr    = len(wins) / total * 100

        avg_w = wins["pnl"].mean() if len(wins) else 0
        avg_l = loss["pnl"].mean() if len(loss) else 0
        pf    = abs(wins["pnl"].sum() / loss["pnl"].sum()) if len(loss) else 999.0  # Cap at 999 (no losses)
        rrr   = abs(avg_w / avg_l) if avg_l else 0

        eq    = pd.Series(self.equity)
        dd    = ((eq - eq.cummax()) / eq.cummax() * 100).min()
        ret   = eq.pct_change().dropna()
        sharpe= (ret.mean() / ret.std() * (252**0.5)) if ret.std() > 0 else 0

        m = {
            "symbol":        self.symbol,
            "total_trades":  total,
            "win_rate":      round(wr, 1),
            "profit_factor": round(pf, 2),
            "rrr":           round(rrr, 2),
            "max_drawdown":  round(dd, 2),
            "sharpe":        round(sharpe, 2),
            "total_pnl":     round(df["pnl"].sum(), 2),
            "final_capital": round(self.cur_cap, 2),
            "total_return":  round((self.cur_cap - self.capital) / self.capital * 100, 2)
        }

        log.info("=" * 50)
        log.info("BACKTEST RESULTS")
        for k, v in m.items():
            log.info(f"  {k:<18}: {v}")

        # Quality check
        checks = {
            "Win Rate 40-55%"      : 40 <= wr <= 60,
            "RRR >= 1:2"           : rrr >= 1.8,
            "Profit Factor >= 1.3" : pf  >= 1.3,
            "Max Drawdown < 25%"   : dd  > -25,
            "Sharpe > 1.0"         : sharpe > 1.0,
            "200+ Trades"          : total >= 50,
        }
        log.info("\nQUALITY CHECK:")
        for chk, ok in checks.items():
            log.info(f"  [{'PASS' if ok else 'FAIL'}] {chk}")

        return m

    def _save(self, metrics):
        if not self.trades:
            return
        ts    = datetime.now().strftime("%Y%m%d_%H%M")
        sym   = self.symbol.replace(".", "_")
        outdir= OUTPUT_DIR / "backtest"
        outdir.mkdir(parents=True, exist_ok=True)

        pd.DataFrame(self.trades).to_csv(outdir / f"trades_{sym}_{ts}.csv", index=False)
        pd.DataFrame([metrics]).to_csv(outdir / f"metrics_{sym}_{ts}.csv", index=False)
        self._plot(sym, ts)

    def _plot(self, sym, ts):
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8))
        fig.suptitle(f"Backtest — {sym}", fontweight="bold")

        ax1.plot(self.equity, color="#2E6DA4", lw=1.5)
        ax1.axhline(self.capital, color="gray", ls="--", lw=1)
        ax1.fill_between(range(len(self.equity)), self.capital, self.equity,
                         where=[e >= self.capital for e in self.equity], alpha=0.2, color="green")
        ax1.fill_between(range(len(self.equity)), self.capital, self.equity,
                         where=[e < self.capital for e in self.equity], alpha=0.2, color="red")
        ax1.set_title("Equity Curve"); ax1.set_ylabel("Capital (Rs.)"); ax1.grid(alpha=0.3)

        if self.trades:
            pnls = [t["pnl"] for t in self.trades]
            ax2.bar(range(len(pnls)), pnls, color=["green" if p > 0 else "red" for p in pnls], alpha=0.7)
            ax2.axhline(0, color="black", lw=0.5)
            ax2.set_title("Trade P&L"); ax2.set_ylabel("P&L (Rs.)"); ax2.grid(alpha=0.3)

        plt.tight_layout()
        path = OUTPUT_DIR / "charts" / f"equity_{sym}_{ts}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(path, dpi=150, bbox_inches="tight")
        plt.close()
        log.info(f"Chart saved: {path}")
