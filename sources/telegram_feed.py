import asyncio
import logging
from telethon import TelegramClient, events
from typing import Callable
from models import NewsItem
from datetime import datetime, timezone
import config

log = logging.getLogger(__name__)

class TelegramNewsMonitor:
    def __init__(self, on_news: Callable[[NewsItem], None]):
        self.api_id = config.TELEGRAM_API_ID
        self.api_hash = config.TELEGRAM_API_HASH
        self.on_news = on_news
        self.enabled = bool(self.api_id and self.api_hash)
        
        self.target_channels = ['Cointelegraph', 'WatcherGuru', 'unusual_whales', 'DeItaone']
        
    async def _start_client(self):
        if not self.enabled:
            log.warning("Telegram feed disabled: missing TELEGRAM_API_ID or TELEGRAM_API_HASH")
            return
            
        client = TelegramClient('news_monitor', int(self.api_id), self.api_hash)
        
        @client.on(events.NewMessage(chats=self.target_channels))
        async def handler(event):
            text = event.raw_text
            if not text or len(text) < 10: return
                
            chat = await event.get_chat()
            
            news = NewsItem(
                source=f"Telegram ({chat.title})",
                timestamp=datetime.now(timezone.utc).isoformat(),
                text=text,
            )
            self.on_news(news)

        # Usamos el token de bot directamente, ya que un bot puede monitorear canales públicos
        # a los que ha sido añadido o algunos públicos, pero telethon en bot_token
        # puede no funcionar con usernames si no está en el grupo.
        # Asumiremos que el usuario agrega su bot a canal o usa user account (con numero).
        # Como es API key/hash puro, lo iniciamos como bot para probar.
        await client.start(bot_token=config.TELEGRAM_TOKEN)
        log.info(f"Started monitoring Telegram channels.")
        await client.run_until_disconnected()

    def start_in_background(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._start_client())
