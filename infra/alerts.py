# ============================================================
# infra/alerts.py — Telegram Alerts
# ============================================================
import requests
from infra.logger import get_logger
from infra.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

log = get_logger("Alerts")

def send_telegram(message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "your_telegram_bot_token":
        log.debug(f"[ALERT] {message}")
        return False
    try:
        url  = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": f"🤖 Trading Bot\n\n{message}"
        }, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        log.error(f"Telegram error: {e}")
        return False

def send_critical(message: str):
    log.critical(message)
    send_telegram(f"🚨 CRITICAL\n\n{message}")
