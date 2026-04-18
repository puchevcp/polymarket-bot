"""
Polymarket Mispricing Bot — v5
================================
Optimización de costos:
- UN solo llamado a Claude Haiku por ciclo (batch de todos los mercados)
- Costo estimado: ~$0.10/día con Claude Haiku
- Flask + self-ping para Render free tier
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

TELEGRAM_TOKEN    = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID  = os.environ.get("TELEGRAM_CHAT_ID", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
RENDER_URL        = os.environ.get("RENDER_URL", "")

GAMMA_API           = "https://gamma-api.polymarket.com"
MIN_VOLUME          = 10000     # Solo mercados con buen volumen
MIN_MISPRICING_PCT  = 0.08      # 8% de gap mínimo para alertar
MAX_MARKETS         = 30        # Mercados por ciclo
SCAN_INTERVAL_SEC   = 300       # Cada 5 minutos (balance costo/frecuencia)
ALERT_COOLDOWN_SEC  = 7200      # No re-alertar mismo mercado por 2 horas
PING_INTERVAL_SEC   = 600

# UN solo modelo barato para el batch
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# ─── ESTADO GLOBAL ────────────────────────────────────────────────────────────

paper_trades: list    = []
alerted_markets: dict = {}
stats = {
    "cycles"        : 0,
    "total_alerts"  : 0,
    "api_calls"     : 0,
    "last_scan"     : None,
    "started_at"    : datetime.utcnow().isoformat()
}

# ─── FLASK ────────────────────────────────────────────────────────────────────

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({**stats, "paper_trades": len(paper_trades)})

@app.route("/trades")
def trades():
    return jsonify(paper_trades[-50:])

@app.route("/health")
def health():
    return "OK", 200

# ─── ESTRUCTURAS ──────────────────────────────────────────────────────────────

@dataclass
class Market:
    id: str
    question: str
    description: str
    yes_price: float
    no_price: float
    volume: float
    end_date: str

@dataclass
class MispricingAlert:
    market: Market
    market_price: float
    claude_estimate: float
    gap: float
    direction: str
    confidence: str
    reasoning: str

# ─── CLAUDE BATCH ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres un analista experto en mercados de predicción.
Recibirás una lista de mercados en JSON y debés estimar la probabilidad real de cada uno.

REGLAS ESTRICTAS:
- Respondé SOLO con un array JSON válido, sin texto adicional, sin markdown, sin backticks
- Para cada mercado incluí: id, probability (0.01-0.99), confidence (ALTA/MEDIA/BAJA), reasoning (max 100 chars en español)
- Sé calibrado y honesto. Si no tenés info suficiente usá confidence BAJA
- No copies el precio del mercado como tu estimación, pensá independientemente

Formato exacto de respuesta:
[
  {"id": "123", "probability": 0.65, "confidence": "ALTA", "reasoning": "razón breve"},
  {"id": "456", "probability": 0.30, "confidence": "MEDIA", "reasoning": "razón breve"}
]"""

def ask_claude_batch(markets: list[Market]) -> dict[str, tuple[float, str, str]]:
    """
    Manda TODOS los mercados en UNA sola llamada a Claude Haiku.
    Retorna dict: market_id -> (probability, confidence, reasoning)
    """
    if not ANTHROPIC_API_KEY:
        log.warning("ANTHROPIC_API_KEY no configurada")
        return {}

    # Armar el payload de mercados para Claude
    markets_payload = []
    for m in markets:
        markets_payload.append({
            "id"          : m.id,
            "question"    : m.question,
            "description" : m.description[:150] if m.description else "",
            "market_price": m.yes_price,
            "volume_usd"  : int(m.volume),
            "end_date"    : m.end_date
        })

    user_prompt = (
        f"Analizá estos {len(markets)} mercados de predicción y estimá la probabilidad real de YES para cada uno:\n\n"
        f"{json.dumps(markets_payload, ensure_ascii=False, indent=2)}"
    )

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key"         : ANTHROPIC_API_KEY,
                "anthropic-version" : "2023-06-01",
                "content-type"      : "application/json"
            },
            json={
                "model"      : CLAUDE_MODEL,
                "max_tokens" : 2000,
                "system"     : SYSTEM_PROMPT,
                "messages"   : [{"role": "user", "content": user_prompt}]
            },
            timeout=60
        )
        r.raise_for_status()
        stats["api_calls"] += 1

        raw = r.json()["content"][0]["text"].strip()
        raw = raw.replace("```json", "").replace("```", "").strip()

        results = json.loads(raw)

        # Construir dict indexado por id
        output = {}
        for item in results:
            market_id  = str(item["id"])
            prob       = float(item["probability"])
            confidence = str(item.get("confidence", "MEDIA"))
            reasoning  = str(item.get("reasoning", ""))

            if 0.01 <= prob <= 0.99:
                output[market_id] = (prob, confidence, reasoning)

        log.info(f"Claude Haiku procesó {len(output)}/{len(markets)} mercados en 1 llamada")
        return output

    except (requests.RequestException, json.JSONDecodeError, KeyError, ValueError) as e:
        log.error(f"Error en Claude batch: {e}")
        return {}

# ─── TELEGRAM ─────────────────────────────────────────────────────────────────

def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id"    : TELEGRAM_CHAT_ID,
                "text"       : message,
                "parse_mode" : "HTML"
            },
            timeout=10
        ).raise_for_status()
    except requests.RequestException as e:
        log.error(f"Telegram error: {e}")

def format_alert(alert: MispricingAlert) -> str:
    icons  = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "⚪"}
    icon   = icons.get(alert.confidence, "⚪")
    action = "✅ COMPRAR YES" if alert.direction == "BUY_YES" else "✅ COMPRAR NO"
    entry  = alert.market.yes_price if alert.direction == "BUY_YES" else alert.market.no_price
    diff   = "subestimado por mercado" if alert.direction == "BUY_YES" else "sobreestimado por mercado"

    return (
        f"{icon} <b>MISPRICING [{alert.confidence}]</b>\n\n"
        f"📋 <b>{alert.market.question[:90]}</b>\n\n"
        f"💰 Volumen: <b>${alert.market.volume:,.0f}</b>\n"
        f"📈 Mercado — YES: <b>{alert.market.yes_price:.2f}</b>  NO: {alert.market.no_price:.2f}\n"
        f"🧠 Haiku estima YES: <b>{alert.claude_estimate:.2f}</b> ({diff})\n"
        f"📊 Gap: <b>{alert.gap*100:.1f}%</b>\n\n"
        f"{action} @ <b>{entry:.2f}</b>\n\n"
        f"💡 <i>{alert.reasoning}</i>\n\n"
        f"🔗 polymarket.com"
    )

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
                yes = float(m.get("outcomePrices", ["0.5", "0.5"])[0])
                no  = float(m.get("outcomePrices", ["0.5", "0.5"])[1])
                vol = float(m.get("volume", 0) or 0)

                if vol < MIN_VOLUME:
                    continue
                # Ignorar mercados casi resueltos
                if yes > 0.96 or yes < 0.04:
                    continue

                markets.append(Market(
                    id          = str(m.get("id", "")),
                    question    = m.get("question", ""),
                    description = str(m.get("description", "") or "")[:200],
                    yes_price   = yes,
                    no_price    = no,
                    volume      = vol,
                    end_date    = m.get("endDate", "")
                ))
            except (ValueError, IndexError, TypeError):
                continue
        return markets

    except requests.RequestException as e:
        log.error(f"Error fetching: {e}")
        return []

# ─── PAPER TRADE ──────────────────────────────────────────────────────────────

def save_paper_trade(alert: MispricingAlert):
    entry = alert.market.yes_price if alert.direction == "BUY_YES" else alert.market.no_price
    paper_trades.append({
        "timestamp"       : datetime.utcnow().isoformat(),
        "market"          : alert.market.question[:80],
        "market_id"       : alert.market.id,
        "direction"       : alert.direction,
        "entry_price"     : entry,
        "claude_estimate" : alert.claude_estimate,
        "gap_pct"         : round(alert.gap * 100, 2),
        "confidence"      : alert.confidence,
        "reasoning"       : alert.reasoning
    })

# ─── SELF-PING ────────────────────────────────────────────────────────────────

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
    log.info("Scanner v5 — Haiku Batch — iniciado")
    send_telegram(
        "🤖 <b>Polymarket Bot v5 iniciado</b>\n"
        "🧠 Motor: Claude Haiku (batch)\n"
        f"📊 {MAX_MARKETS} mercados cada {SCAN_INTERVAL_SEC//60} minutos\n"
        "💰 Costo estimado: ~$0.10/día"
    )

    while True:
        stats["cycles"] += 1
        stats["last_scan"] = datetime.utcnow().isoformat()
        alerts_count = 0

        # 1. Traer mercados
        markets = fetch_markets()
        if not markets:
            log.warning("Sin mercados, reintentando...")
            time.sleep(SCAN_INTERVAL_SEC)
            continue

        # Filtrar los ya alertados recientemente
        markets_to_analyze = [
            m for m in markets
            if not (
                alerted_markets.get(m.id) and
                (time.time() - alerted_markets[m.id]) < ALERT_COOLDOWN_SEC
            )
        ]

        if not markets_to_analyze:
            log.info(f"Ciclo #{stats['cycles']} — todos en cooldown, esperando...")
            time.sleep(SCAN_INTERVAL_SEC)
            continue

        log.info(f"Ciclo #{stats['cycles']} — {len(markets_to_analyze)} mercados → 1 llamada a Haiku")

        # 2. UNA sola llamada batch a Claude Haiku
        estimates = ask_claude_batch(markets_to_analyze)

        # 3. Detectar mispricings
        for market in markets_to_analyze:
            result = estimates.get(market.id)
            if not result:
                continue

            claude_estimate, confidence, reasoning = result
            gap = abs(claude_estimate - market.yes_price)

            log.info(
                f"  {market.question[:40]:<40} "
                f"mkt={market.yes_price:.2f} "
                f"haiku={claude_estimate:.2f} "
                f"gap={gap*100:.1f}%"
            )

            if gap < MIN_MISPRICING_PCT:
                continue

            # ¡Mispricing encontrado!
            alert = MispricingAlert(
                market          = market,
                market_price    = market.yes_price,
                claude_estimate = claude_estimate,
                gap             = gap,
                direction       = "BUY_YES" if claude_estimate > market.yes_price else "BUY_NO",
                confidence      = confidence,
                reasoning       = reasoning
            )

            alerted_markets[market.id] = time.time()
            save_paper_trade(alert)
            send_telegram(format_alert(alert))
            stats["total_alerts"] += 1
            alerts_count += 1
            log.info(f"  *** ALERTA: gap={gap*100:.1f}% [{confidence}] ***")

        log.info(
            f"Ciclo #{stats['cycles']} OK | "
            f"Alertas: {alerts_count} | "
            f"API calls totales: {stats['api_calls']}"
        )
        time.sleep(SCAN_INTERVAL_SEC)

# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    threading.Thread(target=scanner_loop, daemon=True).start()
    threading.Thread(target=self_ping,    daemon=True).start()

    port = int(os.environ.get("PORT", 5000))
    log.info(f"Flask en puerto {port}")
    app.run(host="0.0.0.0", port=port)
