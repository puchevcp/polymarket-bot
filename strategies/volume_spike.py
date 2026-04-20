from typing import Optional
from .base import Strategy
from models import Market, Signal
import config

class VolumeSpikeStrategy(Strategy):
    def __init__(self):
        super().__init__("Volume Spike", config.WEIGHT_VOLUME_SPIKE)
        
    def analyze(self, market: Market, context: dict) -> Optional[Signal]:
        tracker = context.get("price_tracker")
        if not tracker: return None
        
        token_id_yes = market.clob_token_ids.get("YES")
        if not token_id_yes: return None
        
        velocity = tracker.get_velocity(token_id_yes, window_minutes=10)  # Wider window
        
        # Relaxed from 0.08 to 0.03 (3% move in 10 min)
        if velocity > 0.03:
            return Signal(
                 strategy_name=self.name,
                 market_id=market.id,
                 direction="BUY_YES",
                 confidence=min(0.5 + velocity * 5, 1.0),
                 weight=self.weight,
                 reason=f"YES price spike (+{velocity*100:.1f}%) in last 10m",
            )
        elif velocity < -0.03:
            return Signal(
                 strategy_name=self.name,
                 market_id=market.id,
                 direction="BUY_NO",
                 confidence=min(0.5 + abs(velocity) * 5, 1.0),
                 weight=self.weight,
                 reason=f"YES price drop ({velocity*100:.1f}%) in last 10m",
            )
        return None
