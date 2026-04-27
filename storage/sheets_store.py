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

    def get_open_trades(self):
        """Returns a list of (row_index, trade_data) for trades without a result."""
        if not self.client: return []
        try:
            ws = self.spreadsheet.worksheet("Paper Trades")
            records = ws.get_all_records()
            open_trades = []
            for i, row in enumerate(records):
                if row.get("status", "") != "CLOSED":
                    # +2 because spreadsheet is 1-indexed and has header row
                    open_trades.append((i + 2, row))
            return open_trades
        except Exception as e:
            log.error(f"Error reading open trades: {e}")
            return []

    def update_trade_outcome(self, row_index: int, exit_price: float, pnl: float, status: str = "CLOSED"):
        """Updates a specific trade row with the final or unrealized result."""
        if not self.client: return
        try:
            ws = self.spreadsheet.worksheet("Paper Trades")
            # Columns: K=11, L=12, M=13
            # Using update_cell is 100% immune to gspread version breaking-changes
            ws.update_cell(row_index, 11, status)
            ws.update_cell(row_index, 12, exit_price)
            ws.update_cell(row_index, 13, pnl)
            log.info(f"Updated trade at row {row_index} with Status: {status}, P&L: {pnl}")
        except Exception as e:
            log.error(f"Error updating trade outcome: {e}")

    def refresh_performance_dashboard(self):
        """Aggregates all results and updates the 'Strategy Performance' sheet (including Unrealized PNL)."""
        if not self.client: return
        try:
            ws_trades = self.spreadsheet.worksheet("Paper Trades")
            records = ws_trades.get_all_records()
            
            perf = {} # strategy -> {trades, wins, losses, realized_pnl, unrealized_pnl}
            for row in records:
                s_name = row.get("strategy", "Unknown")
                pnl = row.get("pnl")
                status = row.get("status", "OPEN")
                if pnl == "" or pnl is None: continue
                
                pnl_val = float(pnl)
                if s_name not in perf:
                    perf[s_name] = {"trades": 0, "wins": 0, "losses": 0, "realized_pnl": 0.0, "unrealized_pnl": 0.0}
                
                perf[s_name]["trades"] += 1
                if status == "CLOSED":
                    perf[s_name]["realized_pnl"] += pnl_val
                    if pnl_val > 0: perf[s_name]["wins"] += 1
                    else: perf[s_name]["losses"] += 1
                else:
                    perf[s_name]["unrealized_pnl"] += pnl_val
                
            ws_perf = self.spreadsheet.worksheet("Strategy Performance")
            ws_perf.clear()
            ws_perf.append_row(["strategy", "trades", "wins", "losses", "realized_pnl", "unrealized_pnl"])
            for s, data in perf.items():
                ws_perf.append_row([
                    s, data["trades"], data["wins"], data["losses"], 
                    round(data["realized_pnl"], 4), round(data["unrealized_pnl"], 4)
                ])
            
            log.info("Refreshed strategy performance dashboard with Unrealized PNL.")
        except Exception as e:
            log.error(f"Error refreshing performance dashboard: {e}")
