import websocket
import json
import logging
import threading
import time
from typing import Callable, Set

log = logging.getLogger(__name__)

class PolymarketWebSocket:
    def __init__(self, on_price_update: Callable[[str, float], None]):
        self.url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
        self.ws = None
        self.on_price_update = on_price_update
        self.active_subscriptions: Set[str] = set()
        self.should_run = False
        
    def start(self):
        self.should_run = True
        self.thread = threading.Thread(target=self._run_forever, daemon=True)
        self.thread.start()
        
    def stop(self):
        self.should_run = False
        if self.ws:
            self.ws.close()
            
    def subscribe(self, token_ids: list):
        new_tokens = [t for t in token_ids if t not in self.active_subscriptions]
        if not new_tokens: return
        
        self.active_subscriptions.update(new_tokens)
        
        if self.ws and self.ws.sock and self.ws.sock.connected:
            try:
                msg = {
                    "assets": new_tokens,
                    "type": "market"
                }
                self.ws.send(json.dumps(msg))
                log.info(f"Subscribed to {len(new_tokens)} new token IDs via WS")
            except Exception as e:
                log.error(f"Failed to subscribe to WS: {e}")

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            if isinstance(data, list):
                for event in data:
                    self._process_event(event)
            else:
                self._process_event(data)
        except Exception as e:
            log.error(f"WS Parse error: {e}")

    def _process_event(self, event):
        # Extract asset_id and price
        asset_id = event.get("asset_id")
        if not asset_id: return
        
        price = event.get("price")
        if price is not None:
            self.on_price_update(asset_id, float(price))

    def _on_error(self, ws, error):
        log.warning(f"WebSocket error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        log.info("WebSocket closed")

    def _on_open(self, ws):
        log.info("WebSocket connected")
        if self.active_subscriptions:
            msg = {"assets": list(self.active_subscriptions), "type": "market"}
            ws.send(json.dumps(msg))

    def _run_forever(self):
        while self.should_run:
            try:
                self.ws = websocket.WebSocketApp(
                    self.url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close
                )
                self.ws.run_forever()
            except Exception as e:
                log.error(f"WebSocket connection failed: {e}")
            
            if self.should_run:
                log.info("Reconnecting WebSocket in 5s...")
                time.sleep(5)
