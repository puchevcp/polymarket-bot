"""
Polymarket Mispricing Bot — v3
================================
Adaptado para Render Web Service (free tier)
- Flask mantiene el servidor HTTP vivo
- Self-ping cada 10 min para evitar que Render lo duerma
- Scanner corre en thread paralelo
"""

import requests
import json
import time
import os
import logging
import threading
from datetime import datetime
from dataclasses import dataclass
from typing import Optional
from flask import Flask, jsonify

# ─── LOGGING ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

# ─── CONFIG ───────────────────────────────────────────────────────────────────

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
RENDER_URL       = os.environ.get("RENDER_URL", "")  # ej: https://mi-bot.onrender.com

GAMMA_API           = "https://gamma-api.polymarket.com"
MIN_VOLUME          = 1000
MIN_MISPRICING_PCT  = 0.07
MAX_MARKETS         = 100
SCAN_INTERVAL_SEC   = 30
ALERT_COOLDOWN_SEC  = 3600   # No re-alertar mismo mercado por 1 hora
PING_INTERVAL_SEC   = 600    # Auto-ping cada 10 minutos

# ─── ESTADO GLOBAL ────────────────────────────────────────────────────────────

paper_trades: list       = []
alerted_markets: dict    = {}
stats = {
    "cycles"       : 0,
    "total_alerts" : 0,
    "last_scan"    : None,
    "started_at"   : datetime.utcnow().isoformat()
}

# ─── FLASK APP ────────────────────────────────────────────────────────────────

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({
        "status"       : "running",
        "cycles"       : stats["cycles"],
        "total_alerts" : stats["total_alerts"],
        "last_scan"    : stats["last_scan"],
        "started_at"   : stats["started_at"],
        "paper_trades" : len(paper_trades)
    })

@app.route("/trades")
def trades():
    return jsonify(paper_trades)

@app.route("/health")
def health():
    return "OK", 200

# ─── TELEGRAM ─────────────────────────────────────────────────────────────────

def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram no configurado")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id"    : TELEGRAM_CHAT_ID,
            "text"       : message,
            "parse_mode" : "HTML"
        }, timeout=10)
        r.raise_for_status()
    except requests.RequestException as e:
        log.error(f"Telegram error: {e}")

def format_alert(alert) -> str:
    icons  = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "⚪"}
    icon   = icons.get(alert.confidence, "⚪")
    action = "✅ COMPRAR YES" if alert.direction == "BUY_YES" else "✅ COMPRAR NO"
    price  = alert.market.yes_price if alert.direction == "BUY_YES" else alert.market.no_price

    return (
        f"{icon} <b>MISPRICING [{alert.confidence}]</b>\n\n"
        f"📋 <b>{alert.market.question[:80]}</b>\n\n"
        f"💰 Volumen: <b>${alert.market.volume:,.0f}</b>\n"
        f"📈 YES: {alert.market.yes_price:.2f}  |  NO: {alert.market.no_price:.2f}\n"
        f"🎯 Estimación justa: <b>{alert.our_estimate:.2f}</b>\n"
        f"📊 Gap: <b>{alert.gap*100:.1f}%</b>\n\n"
        f"{action} @ <b>{price:.2f}</b>\n"
        f"💡 {alert.reason}\n\n"
        f"🔗 polymarket.com"
    )

# ─── ESTRUCTURAS ──────────────────────────────────────────────────────────────

@dataclass
class Market:
    id: str
    question: str
    yes_price: float
    no_price: float
    volume: float
    end_date: str

@dataclass
class MispricingAlert:
    market: Market
    implied_yes: float
    our_estimate: float
    gap: float
    direction: str
    confidence: str
    reason: str

# ─── FETCHER ──────────────────────────────────────────────────────────────────

def fetch_markets() -> list[Market]:
    try:
        r = requests.get(f"{GAMMA_API}/markets", params={
            "active"    : "true",
            "closed"    : "false",
            "limit"     : MAX_MARKETS,
            "order"     : "volume24hr",
            "ascending" : "false"
        }, timeout=10)
        r.raise_for_status()

        markets = []
        for m in r.json():
            try:
                yes   = float(m.get("outcomePrices", ["0.5", "0.5"])[0])
                no    = float(m.get("outcomePrices", ["0.5", "0.5"])[1])
                vol   = float(m.get("volume", 0) or 0)
                if vol < MIN_VOLUME:
                    continue
                markets.append(Market(
                    id        = str(m.get("id", "")),
                    question  = m.get("question", ""),
                    yes_price = yes,
                    no_price  = no,
                    volume    = vol,
                    end_date  = m.get("endDate", "")
                ))
            except (ValueError, IndexError, TypeError):
                continue
        return markets
    except requests.RequestException as e:
        log.error(f"Error fetching: {e}")
        return []

# ─── DETECTOR ─────────────────────────────────────────────────────────────────

def estimate_fair(market: Market) -> Optional[tuple[float, str, str]]:
    yes   = market.yes_price
    no    = market.no_price
    total = yes + no

    if total < 0.93:
        return (yes + (1.0 - total) / 2, "ALTA",
                f"YES+NO suman {total:.3f} — valor sin capturar")

    if total > 1.08:
        return (yes / total, "ALTA",
                f"YES+NO suman {total:.3f} — overpriced en ambos lados")

    if yes > 0.90 and no > 0.08:
        return (0.95, "MEDIA", f"YES={yes:.2f} alto pero NO={no:.2f} sobrevaluado")

    if yes < 0.10 and no < 0.92:
        return (0.05, "MEDIA", f"YES={yes:.2f} bajo pero NO={no:.2f} subvaluado")

    if abs(1.0 - total) > 0.10:
        return (yes / total, "BAJA",
                f"Spread anómalo: {abs(1.0-total)*100:.1f}%")

    return None

def detect(market: Market) -> Optional[MispricingAlert]:
    result = estimate_fair(market)
    if not result:
        return None
    estimate, confidence, reason = result
    gap = abs(estimate - market.yes_price)
    if gap < MIN_MISPRICING_PCT:
        return None
    return MispricingAlert(
        market       = market,
        implied_yes  = market.yes_price,
        our_estimate = estimate,
        gap          = gap,
        direction    = "BUY_YES" if estimate > market.yes_price else "BUY_NO",
        confidence   = confidence,
        reason       = reason
    )

# ─── PAPER TRADE ──────────────────────────────────────────────────────────────

def save_paper_trade(alert: MispricingAlert):
    price = alert.market.yes_price if alert.direction == "BUY_YES" else alert.market.no_price
    paper_trades.append({
        "timestamp"   : datetime.utcnow().isoformat(),
        "market"      : alert.market.question[:80],
        "market_id"   : alert.market.id,
        "direction"   : alert.direction,
        "entry_price" : price,
        "estimate"    : alert.our_estimate,
        "gap_pct"     : round(alert.gap * 100, 2),
        "confidence"  : alert.confidence,
        "reason"      : alert.reason
    })

# ─── AUTO-PING (evita que Render duerma el servicio) ──────────────────────────

def self_ping():
    while True:
        time.sleep(PING_INTERVAL_SEC)
        if RENDER_URL:
            try:
                requests.get(f"{RENDER_URL}/health", timeout=10)
                log.info("Self-ping OK")
            except Exception as e:
                log.warning(f"Self-ping falló: {e}")

# ─── SCANNER LOOP ─────────────────────────────────────────────────────────────

def scanner_loop():
    log.info("Scanner iniciado")
    send_telegram("🤖 <b>Polymarket Bot iniciado</b>\nEscaneando mercados 24/7...")

    while True:
        stats["cycles"] += 1
        stats["last_scan"] = datetime.utcnow().isoformat()
        alerts_count = 0

        markets = fetch_markets()
        if not markets:
            log.warning("Sin mercados")
            time.sleep(SCAN_INTERVAL_SEC)
            continue

        for market in markets:
            # Anti-duplicados
            last = alerted_markets.get(market.id)
            if last and (time.time() - last) < ALERT_COOLDOWN_SEC:
                continue

            alert = detect(market)
            if not alert:
                continue

            alerted_markets[market.id] = time.time()
            save_paper_trade(alert)
            send_telegram(format_alert(alert))
            stats["total_alerts"] += 1
            alerts_count += 1
            log.info(f"ALERTA: {market.question[:50]} | gap={alert.gap*100:.1f}%")

        log.info(f"Ciclo #{stats['cycles']} | Mercados: {len(markets)} | Alertas: {alerts_count}")
        time.sleep(SCAN_INTERVAL_SEC)

# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Lanzar scanner en thread paralelo
    threading.Thread(target=scanner_loop, daemon=True).start()

    # Lanzar auto-ping en thread paralelo
    threading.Thread(target=self_ping, daemon=True).start()

    # Flask en el hilo principal (Render necesita un puerto HTTP)
    port = int(os.environ.get("PORT", 5000))
    log.info(f"Flask escuchando en puerto {port}")
    app.run(host="0.0.0.0", port=port)
