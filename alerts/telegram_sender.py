import requests
import logging
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

log = logging.getLogger(__name__)

class TelegramSender:
    def __init__(self):
        self.enabled = bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID)
        if not self.enabled:
            log.warning("Telegram is not configured. Alerts will only be logged locally.")
            
    def send_alert(self, message: str, parse_mode: str = "HTML"):
        if not self.enabled:
            print(f"--- FAKE TELEGRAM --- \n{message}\n---------------------")
            return
            
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        try:
            r = requests.post(url, json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True
            }, timeout=10)
            r.raise_for_status()
        except requests.RequestException as e:
            log.error(f"Telegram API error: {e}")
