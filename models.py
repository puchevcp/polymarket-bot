from dataclasses import dataclass, field
from typing import Optional, List

@dataclass
class Market:
    id: str
    question: str
    yes_price: float
    no_price: float
    volume: float
    end_date: str
    category: str = ""
    created_at: str = ""
    slug: str = ""
    clob_token_ids: dict = field(default_factory=dict)

@dataclass
class Signal:
    strategy_name: str
    market_id: str
    direction: str  # "BUY_YES" or "BUY_NO"
    confidence: float # 0.0 to 1.0 (internal weighting)
    weight: float
    reason: str
    target_price: Optional[float] = None

@dataclass
class PaperTrade:
    timestamp: str
    market: str
    market_id: str
    strategy: str # Comma-separated strategies that generated it
    direction: str
    entry_price: float
    estimate: float
    gap_pct: float
    confidence: str # "ALTA", "MEDIA", "BAJA" for UI/alerts
    reason: str
    status: str = "OPEN" # "OPEN", "CLOSED"
    exit_price: Optional[float] = None
    pnl: Optional[float] = None

@dataclass
class NewsItem:
    source: str
    timestamp: str
    text: str
    url: str = ""
    entities: List[str] = field(default_factory=list)
    sentiment: float = 0.0
