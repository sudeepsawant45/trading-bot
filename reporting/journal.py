# ============================================================
# reporting/journal.py — Trade Journal Analyzer
# ============================================================
import json
import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path
from datetime import datetime
from infra.logger import get_logger
from infra.config import DATA_DIR, OUTPUT_DIR
from reporting.tax import TaxTracker

log = get_logger("Journal")

def load_trades() -> pd.DataFrame:
    """Load all trades from all state files."""
    all_trades = []
    for fname in sorted(Path(DATA_DIR).glob("state_*.json")):
        from infra.storage import load_json
        state = load_json(fname)
        all_trades.extend(state.get("trade_log", []))

    if not all_trades:
        return pd.DataFrame()

    df = pd.DataFrame(all_trades)
    df["entry_time"] = pd.to_datetime(df["entry_time"])
    df["exit_time"]  = pd.to_datetime(df["exit_time"])
    return df


def print_summary(df: pd.DataFrame):
    if df.empty:
        print("No trades yet. Run paper trading first.")
        return

    total  = len(df)
    wins   = df[df["pnl_net"] > 0]
    losses = df[df["pnl_net"] <= 0]
    wr     = len(wins) / total * 100
    avg_w  = wins["pnl_net"].mean() if len(wins) else 0
    avg_l  = losses["pnl_net"].mean() if len(losses) else 0
    pf     = abs(wins["pnl_net"].sum() / losses["pnl_net"].sum()) if len(losses) else float("inf")
    rrr    = abs(avg_w / avg_l) if avg_l else 0

    tax = TaxTracker()

    print("\n" + "=" * 58)
    print("      PAPER TRADING JOURNAL SUMMARY")
    print("=" * 58)
    print(f"  Period        : {df['entry_time'].min().date()} → {df['entry_time'].max().date()}")
    print(f"  Total Trades  : {total}")
    print(f"  Win Rate      : {wr:.1f}%  ({len(wins)}W / {len(losses)}L)")
    print(f"  Risk:Reward   : 1:{rrr:.2f}")
    print(f"  Profit Factor : {pf:.2f}")
    print(f"  Net P&L       : Rs. {df['pnl_net'].sum():,.0f}")
    print(f"  Total Charges : Rs. {df['charges'].sum():,.0f}" if "charges" in df else "")
    print("-" * 58)
    print(f"  Est. Tax Due  : Rs. {tax.tax_due:,.0f}  ({tax.fy})")
    print("-" * 58)

    if "strategy" in df.columns:
        print("\n  BY STRATEGY:")
        for s, g in df.groupby("strategy"):
            swr = len(g[g["pnl_net"] > 0]) / len(g) * 100
            print(f"  {s:<12} | {len(g):>3} trades | {swr:.0f}% win | Rs.{g['pnl_net'].sum():,.0f}")

    print("\n  READINESS CHECK:")
    checks = {
        "Win Rate 40-55%":      40 <= wr <= 60,
        "RRR >= 1:2":          rrr >= 1.8,
        "Profit Factor >= 1.3": pf  >= 1.3,
        "50+ Trades":           total >= 50,
    }
    for chk, ok in checks.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {chk}")

    ready = all(checks.values())
    print(f"\n  {'✅ READY FOR LIVE TRADING' if ready else '⏳ Keep paper trading — not ready yet'}")
    print("=" * 58)


def plot_journal(df: pd.DataFrame):
    if df.empty or len(df) < 3:
        return

    fig = plt.figure(figsize=(16, 10))
    fig.suptitle("Paper Trading Journal", fontsize=14, fontweight="bold")
    gs  = gridspec.GridSpec(3, 2, figure=fig, hspace=0.4, wspace=0.3)

    ax1 = fig.add_subplot(gs[0, :])
    cum = df["pnl_net"].cumsum()
    ax1.plot(cum.values, color="#2E6DA4", lw=2)
    ax1.axhline(0, color="black", lw=0.8, ls="--")
    ax1.fill_between(range(len(cum)), 0, cum.values,
                     where=cum.values >= 0, alpha=0.2, color="green")
    ax1.fill_between(range(len(cum)), 0, cum.values,
                     where=cum.values < 0, alpha=0.2, color="red")
    ax1.set_title("Cumulative P&L"); ax1.set_ylabel("Rs."); ax1.grid(alpha=0.3)

    ax2 = fig.add_subplot(gs[1, 0])
    ax2.bar(range(len(df)), df["pnl_net"],
            color=["green" if p > 0 else "red" for p in df["pnl_net"]], alpha=0.7)
    ax2.axhline(0, color="black", lw=0.5)
    ax2.set_title("Per-Trade P&L"); ax2.set_ylabel("Rs."); ax2.grid(alpha=0.3)

    ax3 = fig.add_subplot(gs[1, 1])
    w = len(df[df["pnl_net"] > 0]); l = len(df[df["pnl_net"] <= 0])
    ax3.pie([w, l], labels=[f"Wins ({w})", f"Losses ({l})"],
            colors=["#27AE60","#C0392B"], autopct="%1.0f%%", startangle=90)
    ax3.set_title("Win/Loss")

    ax4 = fig.add_subplot(gs[2, 0])
    if "strategy" in df.columns:
        sp = df.groupby("strategy")["pnl_net"].sum()
        ax4.bar(sp.index, sp.values,
                color=["green" if v > 0 else "red" for v in sp.values], alpha=0.8)
        ax4.axhline(0, color="black", lw=0.5)
        ax4.set_title("P&L by Strategy"); ax4.grid(alpha=0.3)

    ax5 = fig.add_subplot(gs[2, 1])
    ax5.hist(df["pnl_net"], bins=20, color="#2E6DA4", alpha=0.7, edgecolor="white")
    ax5.axvline(0, color="red", lw=1.5, ls="--")
    ax5.axvline(df["pnl_net"].mean(), color="green", lw=1.5, ls="--",
                label=f"Mean: Rs.{df['pnl_net'].mean():.0f}")
    ax5.set_title("P&L Distribution"); ax5.legend(); ax5.grid(alpha=0.3)

    path = Path(OUTPUT_DIR) / "charts" / f"journal_{datetime.now().strftime('%Y%m%d')}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.show()
    log.info(f"Chart saved: {path}")


def export_csv(df: pd.DataFrame):
    if df.empty:
        return
    path = Path(DATA_DIR) / f"trade_export_{datetime.now().strftime('%Y%m%d')}.csv"
    if "entry_time" in df.columns:
        df["trade_date"] = df["entry_time"].dt.date
    df.to_csv(path, index=False)
    print(f"\nExported to: {path}")
    print("Share with your CA for tax filing.")
