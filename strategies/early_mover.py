from datetime import datetime, timezone
from typing import Optional
from .base import Strategy
from models import Market, Signal
import config

class EarlyMoverStrategy(Strategy):
    def __init__(self):
        super().__init__("Early Mover", config.WEIGHT_EARLY_MOVER)
        
    def analyze(self, market: Market, context: dict) -> Optional[Signal]:
        if not market.created_at: return None
        
        try:
            created_dt = datetime.fromisoformat(market.created_at.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            hours_alive = (now - created_dt).total_seconds() / 3600
        except ValueError:
            return None
            
        if hours_alive > 4:
            return None 
            
        # Simplified: Check early markets that might be a 50/50 toss-up 
        # Future improvement: Combine strongly with news NLP
        yes = market.yes_price
        
        if 0.45 < yes < 0.55 and market.volume > config.MIN_VOLUME:
             return Signal(
                 strategy_name=self.name,
                 market_id=market.id,
                 direction="BUY_YES",
                 confidence=0.4, # Low confidence without news, but highlights new active market
                 weight=self.weight,
                 reason=f"New market (<4h old) with good volume. Need News correlation to confirm.",
                 target_price=0.6
             )
        return None
