import requests
import logging
import time
from typing import List, Optional
from models import Market
import config

log = logging.getLogger(__name__)

class PolymarketAPI:
    def __init__(self):
        self.session = requests.Session()
        
    def fetch_markets(self) -> List[Market]:
        markets = []
        try:
            log.info("Fetching markets from Gamma API...")
            r = self.session.get(f"{config.GAMMA_API}/events", params={
                "active": "true",
                "closed": "false",
                "limit": config.MAX_MARKETS // 2, # events contain multiple markets
                "order": "volume24hr",
                "ascending": "false"
            }, timeout=15)
            r.raise_for_status()
            
            events_data = r.json()
            for event in events_data:
                category = event.get("tags", [{}])[0].get("label", "") if event.get("tags") else ""
                
                for m in event.get("markets", []):
                    if not m.get("active") or m.get("closed"): continue
                    
                    try:
                        prices = m.get("outcomePrices")
                        if not prices: continue
                            
                        # Handle list, dict or unexpected types
                        if isinstance(prices, list) and len(prices) >= 2:
                            yes = float(prices[0])
                            no = float(prices[1])
                        elif isinstance(prices, dict):
                            yes = float(prices.get("Yes", prices.get("yes", 0.5)))
                            no = float(prices.get("No", prices.get("no", 0.5)))
                        else:
                            log.warning(f"Unexpected price format for market {m.get('id')}: {type(prices)}")
                            continue
                        
                        vol = float(m.get("volume", 0) or 0)
                        
                        if vol < config.MIN_VOLUME:
                            continue
                            
                        # Polymarket usually returns string '[]' or '["token_id_yes", "token_id_no"]'
                        clob_ids = {}
                        if isinstance(m.get("clobTokenIds"), list) and len(m.get("clobTokenIds")) >= 2:
                             clob_ids["YES"] = m["clobTokenIds"][0]
                             clob_ids["NO"] = m["clobTokenIds"][1]
                        
                        markets.append(Market(
                            id=str(m.get("id", "")),
                            question=m.get("question", ""),
                            yes_price=yes,
                            no_price=no,
                            volume=vol,
                            end_date=m.get("endDate", ""),
                            category=category,
                            created_at=m.get("createdAt", ""),
                            slug=m.get("slug", ""),
                            clob_token_ids=clob_ids
                        ))
                    except (ValueError, IndexError, TypeError) as e:
                        continue
                        
            return sorted(markets, key=lambda x: x.volume, reverse=True)[:config.MAX_MARKETS]
            
        except requests.RequestException as e:
            log.error(f"Error fetching from Gamma API: {e}")
            return []
            
    def fetch_markets_with_retry(self, max_retries=3) -> List[Market]:
        for attempt in range(max_retries):
            markets = self.fetch_markets()
            if markets:
                return markets
            log.warning(f"Fetch failed via Gamma, retrying {attempt+1}/{max_retries} in 5s...")
            time.sleep(5)
        return []
