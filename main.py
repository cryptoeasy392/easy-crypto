from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from orchestrator import CryptoAISystem
from config import config

agent = CryptoAISystem()


# ----------- Handlers -----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    await update.message.reply_text("👋 Welcome! Send me a coin analysis request.\n\n"
                                    "Use /spot <coin> for spot trade suggestion\n"
                                    "or /future <coin> for future trade suggestion."
                                    "or /analysis <coin> for a full analysis request.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle generic user query"""
    user_query = update.message.text
    analyzing_msg = await update.message.reply_text("⏳ Analyzing...")

    try:
        result = await agent.process_query(user_query)
        await analyzing_msg.edit_text(result, parse_mode="MarkdownV2")
    except Exception as e:
        await analyzing_msg.edit_text(f"❌ Error in processing your request. Please try again.\nError: {str(e)}")


# ----------- New Commands -----------

async def spot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle spot trade analysis"""
    if not context.args:
        await update.message.reply_text("⚠️ Please provide a coin symbol. Example: `/spot BTC`", parse_mode="Markdown")
        return

    coin = context.args[0].upper()
    analyzing_msg = await update.message.reply_text(f"🔍 Analyzing {coin} Spot Market...")

    try:
        # Pass a context-aware query to your orchestrator
        result = await agent.process_query(f"Suggested Spot trade for {coin}")
        await analyzing_msg.edit_text(result, parse_mode="MarkdownV2")
    except Exception as e:
        await analyzing_msg.edit_text(f"❌ Error analyzing {coin} spot market.\nError: {str(e)}")


async def futures(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle futures trade analysis"""
    if not context.args:
        await update.message.reply_text("⚠️ Please provide a coin symbol. Example: `/future ETH`", parse_mode="Markdown")
        return

    coin = context.args[0].upper()
    analyzing_msg = await update.message.reply_text(f"🔍 Analyzing {coin} Future Market...")

    try:
        # Same orchestrator call but with futures context
        result = await agent.process_query(f"Suggested Future trade for {coin}")
        await analyzing_msg.edit_text(result, parse_mode="MarkdownV2")
    except Exception as e:
        await analyzing_msg.edit_text(f"❌ Error analyzing {coin} future market.\nError: {str(e)}")

async def analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle futures trade analysis"""
    if not context.args:
        await update.message.reply_text("⚠️ Please provide a coin symbol. Example: `/analysis ETH`", parse_mode="Markdown")
        return

    coin = context.args[0].upper()
    analyzing_msg = await update.message.reply_text(f"🔍 Analyzing {coin}...")

    try:
        # Same orchestrator call but with futures context
        result = await agent.process_query(f"Detailed Analysis for {coin}")
        await analyzing_msg.edit_text(result, parse_mode="MarkdownV2")
    except Exception as e:
        await analyzing_msg.edit_text(f"❌ Error analyzing {coin}.\nError: {str(e)}")

# ----------- Main -----------

def run_bot():
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("spot", spot))
    app.add_handler(CommandHandler("future", futures))
    app.add_handler(CommandHandler("analysis", analysis))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Telegram bot is running...")
    app.run_polling()


if __name__ == "__main__":
    run_bot()
