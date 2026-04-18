import os
import logging
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
RENDER_URL = os.environ.get("RENDER_URL", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
TELEGRAM_API_ID = os.environ.get("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.environ.get("TELEGRAM_API_HASH", "")
GOOGLE_SHEETS_CREDS = os.environ.get("GOOGLE_SHEETS_CREDS", "")

GAMMA_API = "https://gamma-api.polymarket.com"
MAX_MARKETS = 150
MIN_VOLUME = 1000
SCAN_INTERVAL_SEC = 30
ALERT_COOLDOWN_SEC = 3600

# Strategy weights
WEIGHT_MISPRICING = 0.10
WEIGHT_NEWS_ALPHA = 0.35
WEIGHT_VOLUME_SPIKE = 0.20
WEIGHT_EARLY_MOVER = 0.15
WEIGHT_RESOLUTION = 0.10
WEIGHT_CROSS_MARKET = 0.10

MIN_SIGNAL_CONFIDENCE = 0.30

def validate_config():
    missing = []
    if not TELEGRAM_TOKEN: missing.append("TELEGRAM_TOKEN")
    if not TELEGRAM_CHAT_ID: missing.append("TELEGRAM_CHAT_ID")
    if not GOOGLE_SHEETS_CREDS: logging.warning("GOOGLE_SHEETS_CREDS no configurado, persistencia en sheets fallará.")
    
    if missing:
        raise ValueError(f"⚠️ Faltan variables de entorno requeridas: {', '.join(missing)}")
