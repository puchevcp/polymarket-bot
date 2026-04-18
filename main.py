import threading
import time
import logging
from datetime import datetime, timezone

import config
from storage.sheets_store import SheetsStore
from storage.price_history import PriceHistoryTracker
from sources.polymarket_api import PolymarketAPI
from sources.polymarket_ws import PolymarketWebSocket
from sources.telegram_feed import TelegramNewsMonitor
from sources.rss_feed import RssFeedMonitor
from sources.news_processor import NewsProcessor
from strategies.combiner import StrategyCombiner
from strategies.mispricing import MispricingStrategy
from strategies.volume_spike import VolumeSpikeStrategy
from strategies.early_mover import EarlyMoverStrategy
from strategies.resolution import ResolutionStrategy
from strategies.news_alpha import NewsAlphaStrategy
from alerts.telegram_sender import TelegramSender
from alerts.formatter import Formatter
from models import Market, Signal, PaperTrade, NewsItem

import web

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("main")

def main():
    log.info("Starting Polymarket Multi-Strategy Bot...")
    config.validate_config()
    
    store = SheetsStore()
    alert_sender = TelegramSender()
    
    api = PolymarketAPI()
    price_tracker = PriceHistoryTracker()
    ws_client = PolymarketWebSocket(on_price_update=price_tracker.add_price)
    ws_client.start()
    
    context = {"recent_news": [], "price_tracker": price_tracker}
    
    news_nlp = NewsProcessor()
    def on_new_news(raw_news: NewsItem):
        processed = news_nlp.analyze(raw_news)
        context["recent_news"].insert(0, processed)
        context["recent_news"] = context["recent_news"][:50] 
        store.log_news(processed)
        
    rss_monitor = RssFeedMonitor(on_news=on_new_news)
    rss_monitor.start()
    
    telegram_monitor = TelegramNewsMonitor(on_news=on_new_news)
    threading.Thread(target=telegram_monitor.start_in_background, daemon=True).start()

    combiner = StrategyCombiner([
        MispricingStrategy(),
        VolumeSpikeStrategy(),
        EarlyMoverStrategy(),
        ResolutionStrategy(),
        NewsAlphaStrategy()
    ])
    
    web.stats["started_at"] = datetime.now(timezone.utc).isoformat()
    threading.Thread(target=web.start_server, daemon=True).start()
    
    alerted_markets = {}
    
    while True:
        try:
            web.stats["cycles"] += 1
            markets = api.fetch_markets_with_retry()
            log.info(f"Cycle {web.stats['cycles']}: Fetched {len(markets)} markets.")
            
            token_ids = []
            for m in markets:
                token_ids.extend(m.clob_token_ids.values())
            if token_ids:
                ws_client.subscribe(token_ids)
                
            for market in markets:
                if market.id in alerted_markets and (time.time() - alerted_markets[market.id]) < config.ALERT_COOLDOWN_SEC:
                    continue
                    
                signal = combiner.evaluate_market(market, context)
                if signal:
                    msg = Formatter.format_signal(signal, market)
                    alert_sender.send_alert(msg)
                    
                    trade = PaperTrade(
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        market=market.question[:100],
                        market_id=market.id,
                        strategy=signal.strategy_name,
                        direction=signal.direction,
                        entry_price=market.yes_price if signal.direction == "BUY_YES" else market.no_price,
                        estimate=signal.target_price or 0.0,
                        gap_pct=signal.confidence * 100,
                        confidence="ALTA" if signal.confidence > 0.8 else "MEDIA",
                        reason=signal.reason
                    )
                    store.save_paper_trade(trade)
                    store.log_alert(datetime.now(timezone.utc).isoformat(), market.id, market.question, signal.strategy_name, signal.confidence)
                    
                    web.paper_trades_ref.append(trade)
                    web.stats["total_alerts"] += 1
                    alerted_markets[market.id] = time.time()
                    
        except Exception as e:
             log.error(f"Scanner loop error: {e}")
             
        time.sleep(config.SCAN_INTERVAL_SEC)

if __name__ == "__main__":
    main()
