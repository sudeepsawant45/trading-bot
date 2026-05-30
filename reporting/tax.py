# ============================================================
# reporting/tax.py — Tax Calculator & Advance Tax Tracker
# Speculative Business Income (Section 43(5) IT Act)
# ============================================================
import pandas as pd
from datetime import datetime, date
from pathlib import Path
from infra.logger import get_logger
from infra.config import TAX_SLAB_RATE, ADVANCE_TAX_DATES, DATA_DIR, setup_dirs
from infra.storage import save_json, load_json

log = get_logger("Tax")

# Financial Year helpers
def current_fy() -> str:
    today = date.today()
    year  = today.year if today.month >= 4 else today.year - 1
    return f"FY{year}-{str(year+1)[2:]}"

def fy_start(fy: str = None) -> date:
    year = int((fy or current_fy())[2:6])
    return date(year, 4, 1)

def fy_end(fy: str = None) -> date:
    year = int((fy or current_fy())[2:6])
    return date(year + 1, 3, 31)


class TaxTracker:
    """
    Running tax liability tracker.
    Alerts when advance tax dates approach.
    """

    def __init__(self):
        setup_dirs()   # Ensure DATA_DIR exists — called here not at module level
        self.fy    = current_fy()
        self._path = Path(DATA_DIR) / f"tax_{self.fy}.json"
        self._data = load_json(self._path) or {
            "fy": self.fy, "total_profit": 0.0, "total_loss": 0.0,
            "tax_paid": 0.0, "trade_count": 0,
            "carry_forward_loss": 0.0   # Speculative loss from prior years (max 4 yrs)
        }

    def record_trade(self, pnl_net: float):
        """Call after every trade to update tax estimate."""
        if pnl_net > 0:
            self._data["total_profit"] += pnl_net
        else:
            self._data["total_loss"]   += abs(pnl_net)
        self._data["trade_count"] += 1
        self._save()
        self._check_advance_tax_alert()

    @property
    def speculative_income(self) -> float:
        """
        Net speculative income after carry forward loss set-off.
        Speculative loss can be carried forward 4 years (Section 73).
        """
        gross = self._data["total_profit"] - self._data["total_loss"]
        cf    = self._data.get("carry_forward_loss", 0.0)
        return max(0, gross - cf)

    def set_carry_forward_loss(self, amount: float):
        """
        Set carry forward speculative loss from prior years.
        Update this manually each April from your CA's computation.
        Max allowed: 4 years old losses only.
        """
        self._data["carry_forward_loss"] = abs(amount)
        self._save()
        log.info(f"Carry forward loss set: Rs.{amount:,.0f}")

    @property
    def estimated_tax(self) -> float:
        """Estimated tax liability at current slab rate."""
        return round(self.speculative_income * TAX_SLAB_RATE, 2)

    @property
    def tax_due(self) -> float:
        """Remaining tax after what's already paid."""
        return max(0, self.estimated_tax - self._data["tax_paid"])

    def mark_tax_paid(self, amount: float):
        """Record advance tax payment."""
        self._data["tax_paid"] += amount
        self._save()
        log.info(f"Tax payment recorded: Rs.{amount:,.0f} | Remaining: Rs.{self.tax_due:,.0f}")

    def _check_advance_tax_alert(self):
        """Alert if advance tax date is within 15 days."""
        today = date.today()
        for due_date in ADVANCE_TAX_DATES:
            m, d = due_date.split("-")
            month, day_num = int(m), int(d)
            # Use correct year — if due date already passed this year, check next year
            try:
                due = date(today.year, month, day_num)
            except ValueError:
                continue
            if due < today:
                # Already passed this year — check if it's next year's
                try:
                    due = date(today.year + 1, month, day_num)
                except ValueError:
                    continue
            days_to = (due - today).days
            if 0 <= days_to <= 15 and self.tax_due > 1000:
                log.warning(
                    f"ADVANCE TAX DUE in {days_to} days ({due})! "
                    f"Estimated liability: Rs.{self.tax_due:,.0f}"
                )

    def summary(self) -> dict:
        return {
            "fy":                    self.fy,
            "total_profit":          round(self._data["total_profit"], 2),
            "total_loss":            round(self._data["total_loss"], 2),
            "carry_forward_loss":    round(self._data.get("carry_forward_loss", 0), 2),
            "speculative_income":    round(self.speculative_income, 2),
            "estimated_tax":         round(self.estimated_tax, 2),
            "tax_paid":              round(self._data["tax_paid"], 2),
            "tax_due":               round(self.tax_due, 2),
            "trades":                self._data["trade_count"],
            "section_44AD_note":     "Alt: Pay 6% of turnover as tax (presumptive). Ask CA if beneficial.",
            "carry_forward_note":    "Speculative loss carry forward: max 4 years, set via set_carry_forward_loss()",
            "disclaimer":            "Consult your CA before filing. This is an estimate only."
        }

    def _save(self):
        save_json(self._data, self._path)


def generate_fy_report(fy: str = None) -> dict:
    """
    Generate a financial year report from trade logs.
    Groups trades April-March for tax filing.
    """
    fy     = fy or current_fy()
    start  = fy_start(fy)
    end    = fy_end(fy)
    tracker= TaxTracker()

    # Load all state files in this FY
    trades = []
    for fname in sorted(Path(DATA_DIR).glob("state_*.json")):
        state = load_json(fname)
        for t in state.get("trade_log", []):
            try:
                trade_date = datetime.fromisoformat(t["entry_time"]).date()
                if start <= trade_date <= end:
                    trades.append(t)
            except Exception:
                continue

    if not trades:
        return {"fy": fy, "error": "No trades found for this FY"}

    df           = pd.DataFrame(trades)
    total_pnl    = df["pnl_net"].sum()
    total_charges= df["charges"].sum() if "charges" in df else 0

    # Turnover = abs(profit) + abs(loss) per Section 44AB
    profit_trades = df[df["pnl_net"] > 0]["pnl_net"].sum()
    loss_trades   = abs(df[df["pnl_net"] <= 0]["pnl_net"].sum())
    turnover      = profit_trades + loss_trades

    report = {
        "fy":              fy,
        "period":          f"{start} to {end}",
        "total_trades":    len(df),
        "gross_profit":    round(profit_trades, 2),
        "gross_loss":      round(loss_trades, 2),
        "net_pnl":         round(total_pnl, 2),
        "total_charges":   round(total_charges, 2),
        "trading_turnover":round(turnover, 2),
        "audit_required":  turnover > 20000000,   # > Rs.2 Cr
        "tax_head":        "Speculative Business Income (Section 43(5))",
        "itr_form":        "ITR-3",
        "estimated_tax":   round(max(0, total_pnl) * TAX_SLAB_RATE, 2),
        "disclaimer":      "Share with your CA for accurate filing."
    }

    from infra.config import OUTPUT_DIR
    out_path = Path(OUTPUT_DIR) / "backtest" / f"fy_report_{fy}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    log.info(f"FY Report saved: {out_path}")
    log.info(f"Turnover: Rs.{turnover:,.0f} | Audit required: {report['audit_required']}")

    return report
