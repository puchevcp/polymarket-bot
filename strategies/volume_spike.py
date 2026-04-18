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
        
        velocity = tracker.get_velocity(token_id_yes, window_minutes=5)
        
        if velocity > 0.08:
            return Signal(
                 strategy_name=self.name,
                 market_id=market.id,
                 direction="BUY_YES",
                 confidence=0.6,
                 weight=self.weight,
                 reason=f"Violent YES price spike (+{velocity*100:.1f}%) in last 5m",
            )
        elif velocity < -0.08:
            return Signal(
                 strategy_name=self.name,
                 market_id=market.id,
                 direction="BUY_NO",
                 confidence=0.6,
                 weight=self.weight,
                 reason=f"Violent YES price drop ({velocity*100:.1f}%) in last 5m",
            )
        return None
