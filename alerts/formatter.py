from models import Signal, Market

class Formatter:
    @staticmethod
    def format_signal(signal: Signal, market: Market) -> str:
        icon = "🔴" if signal.confidence > 0.8 else "🟡" if signal.confidence > 0.5 else "⚪"
        action = "✅ BUY YES" if signal.direction == "BUY_YES" else "❌ BUY NO"
        current_price = market.yes_price if signal.direction == "BUY_YES" else market.no_price
        
        return (
            f"{icon} <b>POLYMARKET SIGNAL ALERT</b>\n\n"
            f"📋 <b>{market.question}</b>\n\n"
            f"🎯 <b>Action:</b> {action} @ ${current_price:.2f}\n"
            f"🧠 <b>Strategy Stack:</b> {signal.strategy_name}\n"
            f"📊 <b>Confidence Score:</b> {signal.confidence:.2f}\n"
            f"💡 <b>Reason:</b> {signal.reason}\n\n"
            f"💰 <b>Volume 24h:</b> ${market.volume:,.0f}\n"
            f"🔗 <a href='https://polymarket.com/event/{market.slug}'>Trade on Polymarket</a>"
        )
