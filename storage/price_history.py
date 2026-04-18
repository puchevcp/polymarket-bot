import time
import logging
from collections import defaultdict
from typing import Dict, List

log = logging.getLogger(__name__)

class PriceHistoryTracker:
    def __init__(self):
        # Maps token_id -> list of (timestamp, price)
        self.history: Dict[str, List[tuple]] = defaultdict(list)
    
    def add_price(self, token_id: str, price: float):
        now = time.time()
        self.history[token_id].append((now, price))
        
        # Cleanup old prices (keep last 24h)
        cutoff = now - 86400
        self.history[token_id] = [p for p in self.history[token_id] if p[0] > cutoff]
        
    def get_velocity(self, token_id: str, window_minutes: int = 5) -> float:
        """Returns raw price change over the last window_minutes"""
        if token_id not in self.history or len(self.history[token_id]) < 2:
            return 0.0
            
        now = time.time()
        cutoff = now - (window_minutes * 60)
        
        # Find oldest price within window
        window_prices = [p for p in self.history[token_id] if p[0] >= cutoff]
        if len(window_prices) < 2:
            return 0.0
            
        oldest_price = window_prices[0][1]
        newest_price = window_prices[-1][1]
        
        return newest_price - oldest_price
