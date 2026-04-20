import logging
from typing import List, Optional
from models import Market, Signal
from .base import Strategy
import config

log = logging.getLogger(__name__)

class StrategyCombiner:
    def __init__(self, strategies: List[Strategy]):
        self.strategies = strategies
        
    def evaluate_market(self, market: Market, context: dict) -> Optional[Signal]:
        signals = []
        for strategy in self.strategies:
            try:
                signal = strategy.analyze(market, context)
                if signal:
                    signals.append(signal)
                    log.info(f"  ✅ {strategy.name} triggered for '{market.question[:60]}' | conf={signal.confidence:.2f} | dir={signal.direction}")
            except Exception as e:
                log.error(f"Error in strategy {strategy.name}: {e}")
                
        if not signals:
            return None
            
        # Combine signals
        yes_score = 0.0
        no_score = 0.0
        reasons = []
        names = []
        
        for s in signals:
            score = s.confidence * s.weight
            if s.direction == "BUY_YES":
                yes_score += score
            else:
                no_score += score
            reasons.append(f"[{s.strategy_name}] {s.reason}")
            names.append(s.strategy_name)
            
        # Resolve conflict: calculate net score
        net_score = abs(yes_score - no_score)
        direction = "BUY_YES" if yes_score > no_score else "BUY_NO"
        
        log.info(f"  📊 Combined score for '{market.question[:50]}': YES={yes_score:.3f} NO={no_score:.3f} net={net_score:.3f} (threshold={config.MIN_SIGNAL_CONFIDENCE})")
        
        if net_score < config.MIN_SIGNAL_CONFIDENCE:
            return None
            
        # Target price estimate based on the highest confidence signal
        best_signal = max(signals, key=lambda x: x.confidence)
            
        return Signal(
             strategy_name=" + ".join(names),
             market_id=market.id,
             direction=direction,
             confidence=net_score,
             weight=1.0, 
             reason=" | ".join(reasons),
             target_price=best_signal.target_price
        )
