import feedparser
import time
import logging
import threading
from typing import Callable
from datetime import datetime, timezone
from models import NewsItem

log = logging.getLogger(__name__)

class RssFeedMonitor:
    def __init__(self, on_news: Callable[[NewsItem], None]):
        self.on_news = on_news
        self.feeds = [
            "https://feeds.a.dj.com/rss/RSSWSJD.xml",  # WSJ
            "https://search.cnbc.com/rs/search/combinedcms/view.xml?profile=120000000&id=10000664", # CNBC
            "https://cointelegraph.com/rss"            # Crypto
        ]
        self.seen_urls = set()
        self.should_run = False
        
    def start(self):
        self.should_run = True
        self.thread = threading.Thread(target=self._run_forever, daemon=True)
        self.thread.start()
        
    def stop(self):
        self.should_run = False
        
    def _run_forever(self):
        log.info("RSS Monitor started")
        while self.should_run:
            try:
                for url in self.feeds:
                    feed = feedparser.parse(url)
                    for entry in feed.entries[:5]: 
                        if entry.link not in self.seen_urls:
                            self.seen_urls.add(entry.link)
                            
                            text = f"{entry.title}. {entry.get('summary', '')}"
                            
                            news = NewsItem(
                                source=f"RSS ({feed.feed.get('title', 'Feed')})",
                                timestamp=datetime.now(timezone.utc).isoformat(),
                                text=text[:500],
                                url=entry.link
                            )
                            self.on_news(news)
            except Exception as e:
                log.error(f"RSS polling error: {e}")
                
            for _ in range(180): # 3 min wait with quick exit
                 if not self.should_run: return
                 time.sleep(1)
