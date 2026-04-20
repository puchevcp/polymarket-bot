import base64
import json
import logging
import gspread
from dataclasses import asdict
from typing import List
from models import PaperTrade, Signal, NewsItem
import config

log = logging.getLogger(__name__)

class SheetsStore:
    def __init__(self, spreadsheet_name: str = "PolymarketBot"):
        self.client = None
        self.spreadsheet = None
        
        if not config.GOOGLE_SHEETS_CREDS:
            log.warning("GOOGLE_SHEETS_CREDS empty. SheetsStore will not persist data.")
            return
            
        try:
            # Decode base64 JSON
            creds_json_str = base64.b64decode(config.GOOGLE_SHEETS_CREDS).decode('utf-8')
            creds_dict = json.loads(creds_json_str)
            
            # Authenticate with gspread
            self.client = gspread.service_account_from_dict(creds_dict)
            log.info(f"Opening spreadsheet: '{spreadsheet_name}'...")
            try:
                self.spreadsheet = self.client.open(spreadsheet_name)
            except gspread.SpreadsheetNotFound:
                log.error(f"Spreadsheet '{spreadsheet_name}' NOT FOUND. Make sure you created it and shared it with {creds_dict.get('client_email')}")
                self.client = None
                return
            except Exception as e:
                log.error(f"Unexpected error opening spreadsheet: {e}")
                self.client = None
                return
                
            log.info(f"Successfully connected to Google Sheets: {spreadsheet_name}")
            
            # Ensure worksheets exist
            self._ensure_worksheet("Paper Trades", ["timestamp", "market", "market_id", "strategy", "direction", "entry_price", "estimate", "gap_pct", "confidence", "reason", "status", "exit_price", "pnl"])
            self._ensure_worksheet("Alerts History", ["timestamp", "market_id", "question", "strategies", "confidence_score"])
            self._ensure_worksheet("News Log", ["timestamp", "source", "text", "sentiment", "markets_affected"])
            self._ensure_worksheet("Strategy Performance", ["strategy", "trades", "wins", "losses", "pnl"])
            
        except Exception as e:
            log.error(f"CRITICAL: Failed to initialize SheetsStore logic: {e}")
            self.client = None
            
    def _ensure_worksheet(self, title: str, headers: List[str]):
        try:
            worksheet = self.spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            worksheet = self.spreadsheet.add_worksheet(title=title, rows="1000", cols=str(len(headers)))
            worksheet.append_row(headers)
            log.info(f"Created worksheet: {title}")

    def save_paper_trade(self, trade: PaperTrade):
        if not self.client: return
        try:
            ws = self.spreadsheet.worksheet("Paper Trades")
            ws.append_row([
                trade.timestamp, trade.market, trade.market_id, trade.strategy,
                trade.direction, trade.entry_price, trade.estimate, trade.gap_pct,
                trade.confidence, trade.reason, trade.status, trade.exit_price or "", trade.pnl or ""
            ])
        except Exception as e:
            log.error(f"Error saving paper trade to sheets: {e}")

    def log_alert(self, timestamp: str, market_id: str, question: str, strategies: str, confidence_score: float):
        if not self.client: return
        try:
            ws = self.spreadsheet.worksheet("Alerts History")
            ws.append_row([timestamp, market_id, question, strategies, confidence_score])
        except Exception as e:
            log.error(f"Error logging alert: {e}")

    def log_news(self, news: NewsItem, markets_affected: str = ""):
        if not self.client: return
        try:
            ws = self.spreadsheet.worksheet("News Log")
            ws.append_row([news.timestamp, news.source, news.text, news.sentiment, markets_affected])
        except Exception as e:
            log.error(f"Error logging news: {e}")
