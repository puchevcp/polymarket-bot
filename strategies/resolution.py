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
            
        if hours_left < 0 or hours_left > 48:  # Expanded from 24h to 48h
            return None 
            
        yes = market.yes_price
        
        # Wider detection bands
        if 0.80 < yes < 0.96:
            return Signal(
                 strategy_name=self.name,
                 market_id=market.id,
                 direction="BUY_YES",
                 confidence=0.6 + (yes - 0.80) * 1.5,  # Higher price = more obvious
                 weight=self.weight,
                 reason=f"Resolves in {hours_left:.1f}h. YES at {yes:.2f}, likely outcome.",
                 target_price=0.98
            )
        elif 0.04 < yes < 0.20:
             return Signal(
                 strategy_name=self.name,
                 market_id=market.id,
                 direction="BUY_NO",
                 confidence=0.6 + (0.20 - yes) * 1.5,
                 weight=self.weight,
                 reason=f"Resolves in {hours_left:.1f}h. YES at {yes:.2f}, likely NO outcome.",
                 target_price=0.02
             )
        
        return None
