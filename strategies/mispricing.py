from typing import Optional
from .base import Strategy
from models import Market, Signal
import config

class MispricingStrategy(Strategy):
    def __init__(self):
        super().__init__("Arithmetic Mispricing", config.WEIGHT_MISPRICING)
        
    def analyze(self, market: Market, context: dict) -> Optional[Signal]:
        yes = market.yes_price
        no = market.no_price
        total = yes + no
        
        estimate, confidence, reason = None, 0.0, ""
        
        if total < 0.93:
            estimate = yes + (1.0 - total) / 2
            confidence = 0.9  
            reason = f"YES+NO sum {total:.3f} (undervalued)"
        elif total > 1.08:
            estimate = yes / total
            confidence = 0.8
            reason = f"YES+NO sum {total:.3f} (overpriced)"
        elif yes > 0.90 and no > 0.08:
            estimate = 0.95
            confidence = 0.6
            reason = f"YES={yes:.2f} high but NO={no:.2f} overvalued"
        elif yes < 0.10 and no < 0.92:
            estimate = 0.05
            confidence = 0.6
            reason = f"YES={yes:.2f} low but NO={no:.2f} undervalued"
        elif abs(1.0 - total) > 0.10:
            estimate = yes / total
            confidence = 0.4
            reason = f"Anomalous spread: {abs(1.0-total)*100:.1f}%"
            
        if not estimate:
             return None
             
        gap = abs(estimate - market.yes_price)
        if gap < 0.05: # Minimum gap 5% for this gap to matter
            return None
            
        return Signal(
             strategy_name=self.name,
             market_id=market.id,
             direction="BUY_YES" if estimate > market.yes_price else "BUY_NO",
             confidence=confidence,
             weight=self.weight,
             reason=reason,
             target_price=estimate
        )
