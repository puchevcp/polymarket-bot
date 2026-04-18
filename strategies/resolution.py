from datetime import datetime, timezone
from typing import Optional
from .base import Strategy
from models import Market, Signal
import config

class ResolutionStrategy(Strategy):
    def __init__(self):
        super().__init__("Resolution Imminente", config.WEIGHT_RESOLUTION)
        
    def analyze(self, market: Market, context: dict) -> Optional[Signal]:
        if not market.end_date: return None
        
        try:
            end_dt = datetime.fromisoformat(market.end_date.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            hours_left = (end_dt - now).total_seconds() / 3600
        except ValueError:
            return None
            
        if hours_left < 0 or hours_left > 24:
            return None 
            
        yes = market.yes_price
        
        if 0.85 < yes < 0.95:
            return Signal(
                 strategy_name=self.name,
                 market_id=market.id,
                 direction="BUY_YES",
                 confidence=0.7,
                 weight=self.weight,
                 reason=f"Resolves in {hours_left:.1f}h. Obvious YES outcome.",
                 target_price=0.97
            )
        elif 0.05 < yes < 0.15:
             return Signal(
                 strategy_name=self.name,
                 market_id=market.id,
                 direction="BUY_NO",
                 confidence=0.7,
                 weight=self.weight,
                 reason=f"Resolves in {hours_left:.1f}h. Obvious NO outcome.",
                 target_price=0.03
             )
        
        return None
