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
        
        # Relaxed thresholds: original was 0.93/1.08 which almost never triggers
        if total < 0.96:
            estimate = yes + (1.0 - total) / 2
            confidence = 0.7 + (0.96 - total) * 5  # More deviation = more confidence
            reason = f"YES+NO={total:.3f} (undervalued by {(1-total)*100:.1f}%)"
        elif total > 1.04:
            estimate = yes / total
            confidence = 0.7 + (total - 1.04) * 5
            reason = f"YES+NO={total:.3f} (overpriced by {(total-1)*100:.1f}%)"
        elif yes > 0.88 and no > 0.06:
            estimate = 0.95
            confidence = 0.6
            reason = f"YES={yes:.2f} high but NO={no:.2f} still overvalued"
        elif yes < 0.12 and no < 0.94:
            estimate = 0.05
            confidence = 0.6
            reason = f"YES={yes:.2f} low but NO={no:.2f} undervalued"
        elif abs(1.0 - total) > 0.05:
            estimate = yes / total
            confidence = 0.5
            reason = f"Spread anomaly: {abs(1.0-total)*100:.1f}% deviation"
            
        if not estimate:
             return None
             
        gap = abs(estimate - market.yes_price)
        if gap < 0.02:  # Relaxed from 5% to 2%
            return None
            
        return Signal(
             strategy_name=self.name,
             market_id=market.id,
             direction="BUY_YES" if estimate > market.yes_price else "BUY_NO",
             confidence=min(confidence, 1.0),
             weight=self.weight,
             reason=reason,
             target_price=estimate
        )
