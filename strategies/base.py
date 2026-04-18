from abc import ABC, abstractmethod
from typing import Optional
from models import Market, Signal

class Strategy(ABC):
    def __init__(self, name: str, weight: float):
        self.name = name
        self.weight = weight
        
    @abstractmethod
    def analyze(self, market: Market, context: dict) -> Optional[Signal]:
        pass
