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
            
        if hours_alive > 12:  # Expanded from 4h to 12h
            return None 
            
        yes = market.yes_price
        
        # Wider band: detect any new market not yet settled
        if 0.30 < yes < 0.70 and market.volume > config.MIN_VOLUME:
             confidence = 0.5 + (0.5 - abs(yes - 0.5))  # Closer to 50/50 = higher confidence
             return Signal(
                 strategy_name=self.name,
                 market_id=market.id,
                 direction="BUY_YES" if yes < 0.50 else "BUY_NO",
                 confidence=min(confidence, 0.8),
                 weight=self.weight,
                 reason=f"New market ({hours_alive:.1f}h old), price still forming at YES={yes:.2f}",
                 target_price=0.65 if yes < 0.50 else 0.35
             )
        return None
