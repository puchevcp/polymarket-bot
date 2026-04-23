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

def resolution_checker_loop(store: SheetsStore, api: PolymarketAPI):
    """Background task to check status of open paper trades every hour."""
    while True:
        try:
            log.info("Checking resolution for open paper trades...")
            open_trades = store.get_open_trades()
            if not open_trades:
                log.info("No open trades to check.")
            else:
                for row_idx, trade in open_trades:
                    market_id = str(trade.get("market_id"))
                    if not market_id: continue
                    
                    try:
                        r = api.session.get(f"{config.GAMMA_API}/markets/{market_id}", timeout=10)
                        if r.status_code == 200:
                            data = r.json()
                            prices = data.get("outcomePrices", ["0", "0"])
                            yes_current = float(prices[0])
                            
                            # CRITICAL FIX: Google Sheets returns Spanish locale decimals with commas (e.g., "0,925")
                            entry_val = str(trade.get("entry_price", "0.5")).replace(",", ".").strip()
                            entry_price = float(entry_val) if entry_val else 0.5
                            
                            direction = trade.get("direction")
                            
                            is_closed = data.get("closed") or data.get("resolved")
                            
                            # Calculate realistic USDC capital allocation
                            # Example: If we invest $50 at $0.10, we buy 500 shares.
                            shares_bought = config.PAPER_TRADE_SIZE_USDC / entry_price
                            
                            if is_closed:
                                win = (direction == "BUY_YES" and yes_current > 0.99) or \
                                      (direction == "BUY_NO" and yes_current < 0.01)
                                
                                exit_price = 1.0 if win else 0.0
                                gross_return = shares_bought * exit_price
                                pnl = gross_return - config.PAPER_TRADE_SIZE_USDC
                                
                                store.update_trade_outcome(row_idx, exit_price, pnl, status="CLOSED")
                            else:
                                current_price = yes_current if direction == "BUY_YES" else (1.0 - yes_current)
                                gross_return = shares_bought * current_price
                                pnl = gross_return - config.PAPER_TRADE_SIZE_USDC
                                
                                store.update_trade_outcome(row_idx, current_price, pnl, status="OPEN")
                        elif r.status_code == 404:
                            log.warning(f"Market {market_id} not found (archived?)")
                    except Exception as e:
                        log.error(f"Error checking market {market_id}: {e}")
                
                store.refresh_performance_dashboard()
                
        except Exception as e:
            log.error(f"Resolution checker error: {e}")
            
        time.sleep(3600) # Wait 1 hour

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
    
    # Start the resolution checker
    threading.Thread(target=resolution_checker_loop, args=(store, api), daemon=True).start()
    
    alert_cooldowns = {}
    
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
                # Better dedup key using question + base token
                dedup_key = f"{market.question}_{market.clob_token_ids.get('YES', market.id)}"
                
                signal = combiner.evaluate_market(market, context)
                if signal:
                    # Cooldown check including direction
                    final_key = f"{dedup_key}_{signal.direction}"
                    if final_key in alert_cooldowns and (time.time() - alert_cooldowns[final_key]) < config.ALERT_COOLDOWN_SEC:
                        continue
                        
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
                    alert_cooldowns[final_key] = time.time()
                    
        except Exception as e:
             log.error(f"Scanner loop error: {e}")
             
        time.sleep(config.SCAN_INTERVAL_SEC)

if __name__ == "__main__":
    main()
