import json
import logging
from anthropic import Anthropic
from models import NewsItem
import config

log = logging.getLogger(__name__)

class NewsProcessor:
    def __init__(self):
        self.enabled = bool(config.ANTHROPIC_API_KEY)
        if self.enabled:
            self.client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
            log.info("Claude NLP analyzer ready")
        else:
            log.warning("Anthropic API key not provided. NLP disabled.")
            
    def analyze(self, news: NewsItem) -> NewsItem:
        if not self.enabled: return news
        
        system_prompt = """
        You are a financial news intelligence agent for Polymarket. 
        Extract the sentiment (-1.0 to 1.0) and key entities (Persons, Organizations, Countries) from the text.
        Respond ONLY in raw JSON format:
        {"sentiment": float, "entities": ["entity1", "entity2"]}
        """
        
        try:
            response = self.client.messages.create(
                model="claude-3-5-haiku-latest",
                max_tokens=200,
                system=system_prompt,
                messages=[{"role": "user", "content": news.text}]
            )
            
            raw_json = response.content[0].text
            if raw_json.startswith("```json"):
                raw_json = raw_json[7:-3]
                
            data = json.loads(raw_json.strip())
            news.sentiment = data.get("sentiment", 0.0)
            news.entities = data.get("entities", [])
            log.info(f"Processed news via Claude: sentiment={news.sentiment}, entities={news.entities[:2]}")
            
        except Exception as e:
            log.error(f"Claude API Error: {e}")
            
        return news
