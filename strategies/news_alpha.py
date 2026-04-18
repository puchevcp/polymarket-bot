from typing import Optional
from .base import Strategy
from models import Market, Signal
import config

class NewsAlphaStrategy(Strategy):
    def __init__(self):
        super().__init__("News-Driven Alpha", config.WEIGHT_NEWS_ALPHA)
        
    def analyze(self, market: Market, context: dict) -> Optional[Signal]:
        recent_news = context.get("recent_news", [])
        if not recent_news: return None
        
        for news in recent_news:
            # Fallback: exact substring match entity to market question
            for entity in getattr(news, "entities", []):
                if entity.lower() in market.question.lower():
                     direction = "BUY_YES" if news.sentiment > 0 else "BUY_NO"
                     
                     if (direction == "BUY_YES" and market.yes_price > 0.85) or \
                        (direction == "BUY_NO" and market.no_price > 0.85):
                        continue
                        
                     return Signal(
                         strategy_name=self.name,
                         market_id=market.id,
                         direction=direction,
                         confidence=0.6 + abs(news.sentiment)*0.3, # scale confidence by sentiment strength
                         weight=self.weight,
                         reason=f"Entity '{entity}' matched news (sentiment: {news.sentiment:.1f})\nSource: {news.source}",
                         target_price=0.8 if direction == "BUY_YES" else 0.2
                     )
        return None
