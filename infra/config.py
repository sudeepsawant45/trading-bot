# ============================================================
# infra/config.py — Central Configuration
# No side effects on import. Call setup_dirs() explicitly.
# ============================================================
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ─────────────────────────────────────────────────
BASE_DIR     = Path(__file__).resolve().parent.parent
LOG_DIR      = BASE_DIR / "logs"
OUTPUT_DIR   = BASE_DIR / "output"
DATA_DIR     = OUTPUT_DIR / "data"
CHART_DIR    = OUTPUT_DIR / "charts"
BACKTEST_DIR = OUTPUT_DIR / "backtest"

# ── Mode ──────────────────────────────────────────────────
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"
ALGO_APPROVED = os.getenv("ALGO_APPROVED", "false").lower() == "true"

# ── Capital & Risk ────────────────────────────────────────
CAPITAL            = float(os.getenv("CAPITAL", 100000))
RISK_PER_TRADE     = float(os.getenv("RISK_PER_TRADE", 0.01))
MAX_TRADES_PER_DAY = int(os.getenv("MAX_TRADES_PER_DAY", 5))
DAILY_LOSS_LIMIT   = float(os.getenv("DAILY_LOSS_LIMIT", 0.03))
RVOL_THRESHOLD     = float(os.getenv("RVOL_THRESHOLD", 1.5))

# ── Kite Connect ──────────────────────────────────────────
KITE_API_KEY      = os.getenv("KITE_API_KEY", "")
KITE_SECRET       = os.getenv("KITE_SECRET", "")
KITE_ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN", "")

# ── Telegram ──────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Timezone ──────────────────────────────────────────────
TIMEZONE = "Asia/Kolkata"   # Always IST — never assume system clock

# ── Strategy ──────────────────────────────────────────────
EMA_FAST    = 9
EMA_SLOW    = 21
EMA_TREND   = 50
RSI_PERIOD  = 14
ATR_PERIOD  = 14
ADX_PERIOD  = 14
VOLUME_SMA  = 20
ATR_SL_MULT = 1.5
ADX_MIN     = 20
ML_CONF_MIN = 0.60  # Phase 2: ML confidence filter threshold (not yet active)

# ── Market Timings (IST) ──────────────────────────────────
MARKET_OPEN    = "09:15"
ORB_END        = "09:30"
EXEC_START     = "09:31"   # No orders before this
NO_TRADE_START = "11:30"   # Dead zone start
NO_TRADE_END   = "12:30"   # Dead zone end
SQUARE_OFF     = "15:15"
MARKET_CLOSE   = "15:30"

# ── Scan settings ─────────────────────────────────────────
SCAN_SYMBOLS    = 5
SIGNAL_LOOKBACK = 100
MAX_GAP_NORMAL  = 0.01

# ── Watchlist ─────────────────────────────────────────────
WATCHLIST = [
    "RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK",
    "KOTAKBANK","HINDUNILVR","SBIN","BHARTIARTL","ITC",
    "BAJFINANCE","AXISBANK","LT","ASIANPAINT","MARUTI",
    "TITAN","SUNPHARMA","WIPRO","ULTRACEMCO","NESTLEIND"
]
NIFTY_SYMBOL = "^NSEI"
WATCHLIST_YF = [f"{s}.NS" for s in WATCHLIST]

# ── Tax ───────────────────────────────────────────────────
TAX_SLAB_RATE     = 0.30
ADVANCE_TAX_DATES = ["06-15", "09-15", "12-15", "03-15"]  # MM-DD


# ── Functions (defined after all variables) ───────────────
def setup_dirs():
    """Explicitly create directories. Call once at startup."""
    for d in [LOG_DIR, DATA_DIR, CHART_DIR, BACKTEST_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def validate_config():
    """
    Validate all config values on startup.
    Raises ValueError with clear message if something is wrong.
    All variables defined above — no closure confusion.
    """
    errors = []
    if CAPITAL <= 0:
        errors.append(f"CAPITAL must be > 0, got {CAPITAL}")
    if not (0 < RISK_PER_TRADE <= 0.05):
        errors.append(f"RISK_PER_TRADE must be 0-5%, got {RISK_PER_TRADE}")
    if not (1 <= MAX_TRADES_PER_DAY <= 20):
        errors.append(f"MAX_TRADES_PER_DAY must be 1-20, got {MAX_TRADES_PER_DAY}")
    if not (0.01 <= DAILY_LOSS_LIMIT <= 0.20):
        errors.append(f"DAILY_LOSS_LIMIT must be 1-20%, got {DAILY_LOSS_LIMIT}")
    if not (1.0 <= RVOL_THRESHOLD <= 5.0):
        errors.append(f"RVOL_THRESHOLD must be 1.0-5.0, got {RVOL_THRESHOLD}")
    if not (0 < TAX_SLAB_RATE <= 0.42):
        errors.append(f"TAX_SLAB_RATE must be 0-42%, got {TAX_SLAB_RATE}")
    if errors:
        raise ValueError(
            "Config validation failed:\n" +
            "\n".join(f"  - {e}" for e in errors)
        )
