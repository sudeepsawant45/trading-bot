#!/usr/bin/env python3
# ============================================================
# main.py — Entry Point
# Usage:
#   python main.py test              Run unit tests
#   python main.py backtest          Run backtest
#   python main.py paper             Paper trading
#   python main.py journal           View journal & charts
#   python main.py tax               Tax summary & FY report
#   python main.py live --confirm    LIVE trading (real money!)
# ============================================================

import sys
import os

# Setup directories FIRST (before any imports that use them)
from infra.config import setup_dirs, validate_config
setup_dirs()

# Skip config validation for unit tests — test env may not have .env
_cmd = sys.argv[1].lower() if len(sys.argv) > 1 else ""
if _cmd != "test":
    try:
        validate_config()
    except ValueError as e:
        print(f"\n{'='*55}")
        print("  CONFIG ERROR — Please fix your .env file:")
        print(f"{'='*55}")
        print(str(e))
        print(f"\n  Edit .env file and fix the values above.")
        print(f"  Reference: .env.example\n")
        sys.exit(1)

from infra.logger import get_logger
from infra.config import ALGO_APPROVED, DATA_DIR

log = get_logger("Main")

# Consent file — defined after setup_dirs() so DATA_DIR exists
CONSENT_FILE = DATA_DIR / ".consent_v2"   # v2 = re-consent on major version update


def show_disclaimer_and_get_consent():
    """
    Show legal disclaimer on first run.
    Requires typed confirmation before proceeding.
    """
    if CONSENT_FILE.exists():
        return True

    print("\n" + "=" * 62)
    print("  IMPORTANT — PLEASE READ BEFORE USING THIS SYSTEM")
    print("=" * 62)
    print("""
  1. This system is for PERSONAL USE ONLY.
  2. NOT a SEBI registered investment adviser.
  3. Trading involves substantial risk of capital loss.
  4. Past performance does NOT guarantee future results.
  5. For live trading: get SEBI algo approval from your broker.
  6. Consult a CA for tax filing (Speculative Business Income).
  7. The creators are not liable for any financial losses.

  By continuing, you acknowledge all of the above.
    """)
    print("=" * 62)

    response = input("  Type AGREE to continue (or anything else to exit): ").strip()
    if response.upper() != "AGREE":
        print("Exiting. Come back when ready.")
        sys.exit(0)

    CONSENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONSENT_FILE.touch()
    print("  Consent recorded. Starting...\n")
    return True


def run_tests():
    import subprocess
    log.info("Running unit tests...")
    result = subprocess.run(
        ["python", "-m", "pytest", "tests/", "-v", "--tb=short"]
    )
    return result.returncode == 0


def run_backtest():
    from engine.backtest import Backtest
    from infra.config import CAPITAL, WATCHLIST_YF

    symbols = WATCHLIST_YF[:3]
    log.info(f"Running backtest on: {symbols}")
    log.info("Using 58d period with 5m candles — ORB + EMA + RSI all active")

    for sym in symbols:
        bt     = Backtest(sym, capital=CAPITAL)
        result = bt.run(period="58d")   # 5m intraday data — all strategies active
        if not result or "error" in result:
            log.warning(f"Backtest for {sym}: {result.get('error','no trades')}")


def run_paper():
    from engine.trader import Trader
    from execution.paper import PaperExecutor

    executor = PaperExecutor()
    trader   = Trader(executor=executor)
    trader.start()


def run_live():
    """Live trading — requires explicit --confirm flag + ALGO_APPROVED=true."""
    if "--confirm" not in sys.argv:
        print("\nTo run live trading:")
        print("  1. Set ALGO_APPROVED=true in .env (after broker approval)")
        print("  2. Set PAPER_TRADING=false in .env")
        print("  3. Run: python main.py live --confirm")
        print("\nThis protection prevents accidental live trading.")
        sys.exit(1)

    if not ALGO_APPROVED:
        print("\nERROR: ALGO_APPROVED=false in .env")
        print("Get written algo approval from your broker first.")
        print("Then set ALGO_APPROVED=true in .env")
        sys.exit(1)

    confirm = input("\nLIVE TRADING with REAL MONEY. Type 'YES I UNDERSTAND': ")
    if confirm.strip() != "YES I UNDERSTAND":
        print("Cancelled.")
        sys.exit(0)

    from engine.trader import Trader
    from execution.kite import KiteExecutor
    from data.kite_provider import KiteProvider

    provider = KiteProvider()
    executor = KiteExecutor(provider.kite)
    trader   = Trader(executor=executor, data_provider=provider)
    trader.start()


def run_journal():
    from reporting.journal import load_trades, print_summary, plot_journal, export_csv
    df = load_trades()
    print_summary(df)
    export_csv(df)
    if len(df) >= 3:
        plot_journal(df)


def run_tax():
    from reporting.tax import TaxTracker, generate_fy_report
    tracker = TaxTracker()
    summary = tracker.summary()
    print("\n" + "=" * 50)
    print("  TAX SUMMARY")
    print("=" * 50)
    for k, v in summary.items():
        print(f"  {k:<22}: {v}")
    print("=" * 50)

    fy_report = generate_fy_report()
    print("\n  FY REPORT:")
    for k, v in fy_report.items():
        print(f"  {k:<22}: {v}")
    print("\n  NOTE: Share with your CA for accurate tax filing.")


def print_help():
    print("""
╔══════════════════════════════════════════════════╗
║       NSE INTRADAY TRADING BOT  v5.0 Final       ║
║       Personal Use Only                          ║
╠══════════════════════════════════════════════════╣
║                                                  ║
║  python main.py test       Run unit tests        ║
║  python main.py backtest   Historical backtest   ║
║  python main.py paper      Paper trading         ║
║  python main.py journal    View results          ║
║  python main.py tax        Tax summary           ║
║  python main.py live       Live trading*         ║
║                                                  ║
║  * Requires ALGO_APPROVED=true + --confirm flag  ║
║                                                  ║
║  RECOMMENDED ORDER:                              ║
║  1. test → 2. backtest → 3. paper (3 months)     ║
║             → 4. live (small capital)            ║
╚══════════════════════════════════════════════════╝
    """)


if __name__ == "__main__":
    # Skip consent for unit tests — no financial activity involved
    if len(sys.argv) < 2 or sys.argv[1].lower() != "test":
        show_disclaimer_and_get_consent()

    if len(sys.argv) < 2:
        print_help()
        sys.exit(0)

    cmd = sys.argv[1].lower()

    commands = {
        "test":     run_tests,
        "backtest": run_backtest,
        "paper":    run_paper,
        "journal":  run_journal,
        "tax":      run_tax,
        "live":     run_live,
    }

    if cmd in commands:
        commands[cmd]()
    else:
        print(f"Unknown command: {cmd}")
        print_help()
        sys.exit(1)
