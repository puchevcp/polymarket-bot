"""
Polymarket Mispricing Bot — v2
================================
- Alertas por Telegram
- Corre 24/7 en servidor
- Evita alertas duplicadas
- Escaneo cada 30 segundos
"""

import requests
import json
import time
import os
import logging
from datetime import datetime
from dataclasses import dataclass
from typing import Optional

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

GAMMA_API            = "https://gamma-api.polymarket.com"
MIN_VOLUME           = 1000
MIN_MISPRICING_PCT   = 0.07
MAX_MARKETS_TO_SCAN  = 100
SCAN_INTERVAL_SEC    = 30
ALERT_COOLDOWN_SEC   = 3600  # No re-alertar el mismo mercado por 1 hora

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

# ─── TELEGRAM ─────────────────────────────────────────────────────────────────

def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram no configurado — revisá las variables de entorno")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id"    : TELEGRAM_CHAT_ID,
        "text"       : message,
        "parse_mode" : "HTML"
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
    except requests.RequestException as e:
        log.error(f"Error enviando Telegram: {e}")

def format_alert_message(alert: MispricingAlert) -> str:
    icons = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "⚪"}
    icon  = icons.get(alert.confidence, "⚪")
    action = "✅ COMPRAR YES" if alert.direction == "BUY_YES" else "✅ COMPRAR NO"
    price  = alert.market.yes_price if alert.direction == "BUY_YES" else alert.market.no_price

    return (
        f"{icon} <b>MISPRICING [{alert.confidence}]</b>\n\n"
        f"📋 <b>{alert.market.question[:80]}</b>\n\n"
        f"💰 Volumen: <b>${alert.market.volume:,.0f}</b>\n"
        f"📈 YES: {alert.market.yes_price:.2f}  |  NO: {alert.market.no_price:.2f}\n"
        f"🎯 Estimación justa YES: <b>{alert.our_estimate:.2f}</b>\n"
        f"📊 Gap: <b>{alert.gap*100:.1f}%</b>\n\n"
        f"{action} @ <b>{price:.2f}</b>\n"
        f"💡 {alert.reason}\n\n"
        f"🔗 polymarket.com"
    )

# ─── FETCHER ──────────────────────────────────────────────────────────────────

def fetch_markets() -> list[Market]:
    try:
        url = f"{GAMMA_API}/markets"
        params = {
            "active"    : "true",
            "closed"    : "false",
            "limit"     : MAX_MARKETS_TO_SCAN,
            "order"     : "volume24hr",
            "ascending" : "false"
        }
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()

        markets = []
        for m in r.json():
            try:
                yes_price = float(m.get("outcomePrices", ["0.5", "0.5"])[0])
                no_price  = float(m.get("outcomePrices", ["0.5", "0.5"])[1])
                volume    = float(m.get("volume", 0) or 0)
                if volume < MIN_VOLUME:
                    continue
                markets.append(Market(
                    id        = str(m.get("id", "")),
                    question  = m.get("question", "Sin título"),
                    yes_price = yes_price,
                    no_price  = no_price,
                    volume    = volume,
                    end_date  = m.get("endDate", "")
                ))
            except (ValueError, IndexError, TypeError):
                continue
        return markets

    except requests.RequestException as e:
        log.error(f"Error fetching markets: {e}")
        return []

# ─── MODELO DE MISPRICING ─────────────────────────────────────────────────────

def estimate_fair_probability(market: Market) -> Optional[tuple[float, str, str]]:
    yes   = market.yes_price
    no    = market.no_price
    total = yes + no

    # Regla 1: YES + NO no suman ~1.00
    if total < 0.93:
        adjusted = yes + (1.0 - total) / 2
        return (adjusted, "ALTA", f"YES+NO suman {total:.3f} — hay valor sin capturar")

    if total > 1.08:
        adjusted = yes / total
        return (adjusted, "ALTA", f"YES+NO suman {total:.3f} — overpriced en ambos lados")

    # Regla 2: Inconsistencia en extremos
    if yes > 0.90 and no > 0.08:
        return (0.95, "MEDIA", f"YES={yes:.2f} muy alto pero NO={no:.2f} sobrevaluado")

    if yes < 0.10 and no < 0.92:
        return (0.05, "MEDIA", f"YES={yes:.2f} muy bajo pero NO={no:.2f} subvaluado")

    # Regla 3: Spread anormalmente amplio
    spread = abs(1.0 - total)
    if spread > 0.10:
        mid = yes / total
        return (mid, "BAJA", f"Spread anormalmente amplio: {spread*100:.1f}%")

    return None

def detect_mispricing(market: Market) -> Optional[MispricingAlert]:
    result = estimate_fair_probability(market)
    if result is None:
        return None

    our_estimate, confidence, reason = result
    gap = abs(our_estimate - market.yes_price)

    if gap < MIN_MISPRICING_PCT:
        return None

    direction = "BUY_YES" if our_estimate > market.yes_price else "BUY_NO"

    return MispricingAlert(
        market       = market,
        implied_yes  = market.yes_price,
        our_estimate = our_estimate,
        gap          = gap,
        direction    = direction,
        confidence   = confidence,
        reason       = reason
    )

# ─── PAPER TRADING ────────────────────────────────────────────────────────────

paper_trades = []

def paper_trade(alert: MispricingAlert):
    entry = alert.market.yes_price if alert.direction == "BUY_YES" else alert.market.no_price
    trade = {
        "timestamp"    : datetime.utcnow().isoformat(),
        "market"       : alert.market.question[:80],
        "market_id"    : alert.market.id,
        "direction"    : alert.direction,
        "entry_price"  : entry,
        "our_estimate" : alert.our_estimate,
        "gap_pct"      : round(alert.gap * 100, 2),
        "confidence"   : alert.confidence,
        "reason"       : alert.reason,
        "status"       : "OPEN"
    }
    paper_trades.append(trade)
    try:
        with open("paper_trades.json", "w") as f:
            json.dump(paper_trades, f, indent=2, ensure_ascii=False)
    except IOError as e:
        log.error(f"Error guardando paper trade: {e}")

# ─── ANTI-DUPLICADOS ──────────────────────────────────────────────────────────

alerted_markets: dict[str, float] = {}

def already_alerted(market_id: str) -> bool:
    last = alerted_markets.get(market_id)
    if last is None:
        return False
    return (time.time() - last) < ALERT_COOLDOWN_SEC

def mark_alerted(market_id: str):
    alerted_markets[market_id] = time.time()

# ─── MAIN LOOP ────────────────────────────────────────────────────────────────

def run():
    log.info("=" * 50)
    log.info("POLYMARKET MISPRICING BOT v2 — Iniciando")
    log.info(f"Escaneando {MAX_MARKETS_TO_SCAN} mercados cada {SCAN_INTERVAL_SEC}s")
    log.info(f"Gap mínimo: {MIN_MISPRICING_PCT*100:.0f}% | Vol mínimo: ${MIN_VOLUME:,}")
    log.info("=" * 50)

    send_telegram("🤖 <b>Polymarket Bot iniciado</b>\nEscaneando mercados en busca de mispricings...")

    cycle = 0
    while True:
        cycle += 1
        alerts_count = 0

        markets = fetch_markets()
        if not markets:
            log.warning("Sin mercados, reintentando...")
            time.sleep(SCAN_INTERVAL_SEC)
            continue

        for market in markets:
            if already_alerted(market.id):
                continue
            alert = detect_mispricing(market)
            if not alert:
                continue

            alerts_count += 1
            mark_alerted(market.id)
            paper_trade(alert)
            send_telegram(format_alert_message(alert))
            log.info(f"ALERTA: {market.question[:50]} | gap={alert.gap*100:.1f}%")

        log.info(f"Ciclo #{cycle} | Mercados: {len(markets)} | Alertas: {alerts_count}")
        time.sleep(SCAN_INTERVAL_SEC)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        log.info("Bot detenido.")
        send_telegram("⛔ Bot detenido manualmente.")
