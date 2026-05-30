# NSE Intraday Trading Bot v3.0
**Personal Use Only | 7-Expert Reviewed | All Critical Fixes Applied**

---

## Project Structure
```
trading_bot/
├── core/                    Business logic (pure, testable)
│   ├── indicators.py        EMA, RSI, ATR, VWAP, ADX + IST timezone
│   ├── signals.py           ORB, EMA, RSI strategies + Nifty filter
│   ├── risk.py              Position sizing, SL, circuit breakers
│   └── charges.py           All NSE trading charges
├── data/                    Data providers (swappable)
│   ├── base.py              Abstract interface
│   ├── yfinance_provider.py Paper trading / backtest (FREE)
│   └── kite_provider.py     Live trading (Zerodha)
├── execution/               Order execution (swappable)
│   ├── base.py              Abstract interface
│   ├── paper.py             Simulated orders
│   └── kite.py              Real orders (live only)
├── engine/                  Orchestration
│   ├── trader.py            Event-driven trading engine
│   └── backtest.py          Historical backtesting
├── reporting/               Analysis & compliance
│   ├── journal.py           Trade journal + charts
│   └── tax.py               Advance tax tracker + FY report
├── infra/                   Infrastructure
│   ├── config.py            Settings (no side effects on import)
│   ├── logger.py            Rotating file logger
│   ├── alerts.py            Telegram notifications
│   └── storage.py           Atomic JSON writes (crash-safe)
├── tests/                   Unit tests
│   ├── test_risk.py
│   └── test_signals.py
└── main.py                  Entry point
```

---

## Setup
```
1. setup.bat (double-click on Windows)
   OR manually:
   pip install -r requirements.txt
   copy .env.example .env

2. Edit .env — set your CAPITAL amount

3. python main.py test        (verify everything works)
4. python main.py backtest    (validate strategy)
5. python main.py paper       (run for 2-3 months)
6. python main.py journal     (review results)
7. python main.py tax         (check tax liability)
```

---

## Security Note
Log files in `logs/` contain trade details and P&L in plaintext.
Keep your laptop secure. Do not share log files with anyone.
Do not store logs in cloud folders (Google Drive, OneDrive) without encryption.

---

## Commands
| Command | What it does |
|---|---|
| `python main.py test` | Run all unit tests |
| `python main.py backtest` | Backtest on 1 year of data |
| `python main.py paper` | Paper trading (no real money) |
| `python main.py journal` | View results + charts |
| `python main.py tax` | Tax summary + FY report |
| `python main.py live --confirm` | Live trading (after setup) |

---

## Key Fixes in v2.0
- Per-symbol ORB state (no cross-contamination)
- Nifty trend filter implemented in code
- Signals on completed candles only (not forming)
- yfinance 60-day limit handled automatically
- Atomic file writes (crash-safe)
- IST timezone hardcoded (not system clock)
- Live trading requires explicit --confirm + ALGO_APPROVED=true
- First-run consent screen
- Advance tax tracker with quarterly alerts
- SEBI charges added to calculations

---

## Monthly Cost
| Item | Cost |
|---|---|
| Kite Connect API | Rs. 2,000/month |
| Your laptop | Rs. 0 |
| **Total (paper phase)** | **Rs. 0** |
| **Total (live phase)** | **Rs. 2,000/month** |

---

*Personal use only. Not for sale.*
*Not a SEBI registered investment adviser.*
*Trading involves substantial risk of capital loss.*
