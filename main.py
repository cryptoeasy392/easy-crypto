from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from logger import logger
from orchestrator import CryptoAISystem
from config import config
import json
import os
from datetime import datetime

agent = CryptoAISystem()

# Database file path
DB_FILE = "users_db.json"


# ----------- Database Functions -----------

def load_database():
    """Load user database from JSON file"""
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_database(db):
    """Save user database to JSON file"""
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, indent=2, ensure_ascii=False)


def get_user_data(user_id):
    """Get user data from database"""
    db = load_database()
    user_id_str = str(user_id)

    if user_id_str not in db:
        db[user_id_str] = {
            "user_id": user_id,
            "requests_used": 0,
            "is_subscribed": False,
            "first_seen": datetime.now().isoformat(),
            "last_request": None
        }
        save_database(db)

    return db[user_id_str]


def update_user_usage(user_id):
    """Increment user request count"""
    db = load_database()
    user_id_str = str(user_id)

    if user_id_str in db:
        db[user_id_str]["requests_used"] += 1
        db[user_id_str]["last_request"] = datetime.now().isoformat()
        save_database(db)
        return db[user_id_str]["requests_used"]
    return 0


def check_user_limit(user_id):
    """Check if user has remaining requests"""
    user_data = get_user_data(user_id)

    if user_data["is_subscribed"]:
        return True, -1  # Unlimited for subscribed users

    requests_used = user_data["requests_used"]
    remaining = 10 - requests_used

    return remaining > 0, remaining


def get_usage_message(user_id):
    """Get usage status message"""
    user_data = get_user_data(user_id)

    if user_data["is_subscribed"]:
        return "\n\n✨ You are a premium subscriber - Unlimited requests!"

    remaining = 10 - user_data["requests_used"]
    return f"\n\n📊 Remaining requests: {remaining}/10"


# ----------- Handlers -----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)  # Initialize user in database

    welcome_message = (
        "🌟 مرحباً بك في Easy Trade 🌟\n\n"
        "أنا هنا لمساعدتك في تحليل العملات الرقمية وتقديم أفضل التوصيات.\n\n"
        "🎁 لديك 10 طلبات مجانية للبدء!\n\n"
        "استخدم الأوامر التالية:\n"
        "/spot <coin> - للحصول على توصية تداول فوري\n"
        "/future <coin> - للحصول على توصية عقود آجلة\n"
        "/analysis <coin> - للحصول على تحليل شامل\n\n"
        "✨ ابدأ الآن بإرسال استفسارك!"
    )

    await update.message.reply_text(welcome_message)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle generic user query"""
    user_id = update.effective_user.id
    has_access, remaining = check_user_limit(user_id)

    if not has_access:
        await update.message.reply_text(
            "⚠️ You have used all your free requests!\n"
            "Please subscribe to continue using Easy Trade."
        )
        return

    user_query = update.message.text
    analyzing_msg = await update.message.reply_text("⏳ Analyzing...")

    try:
        result = await agent.process_query(user_query)
        update_user_usage(user_id)
        usage_msg = get_usage_message(user_id)

        final_message = result + usage_msg
        await analyzing_msg.edit_text(final_message, parse_mode="MarkdownV2")
    except Exception as e:
        logger.error(f"Error in handling the message: {e}")
        await analyzing_msg.edit_text(f"❌ عذرا!! هناك خطأ في معالجة طلبك")


# ----------- New Commands -----------

async def spot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle spot trade analysis"""
    user_id = update.effective_user.id
    has_access, remaining = check_user_limit(user_id)

    if not has_access:
        await update.message.reply_text(
            "⚠️ You have used all your free requests!\n"
            "Please subscribe to continue using Easy Trade."
        )
        return

    if not context.args:
        await update.message.reply_text("⚠️ Please provide a coin symbol. Example: `/spot BTC`", parse_mode="Markdown")
        return

    coin = context.args[0].upper()
    analyzing_msg = await update.message.reply_text(f"🔍 Analyzing {coin} Spot Market...")

    try:
        result = await agent.process_query(f"Suggested Spot trade for {coin}")
        update_user_usage(user_id)
        usage_msg = get_usage_message(user_id)

        final_message = result + usage_msg
        await analyzing_msg.edit_text(final_message, parse_mode="MarkdownV2")
    except Exception as e:
        await analyzing_msg.edit_text(f"❌ Error analyzing {coin} spot market.\nError: {str(e)}")


async def futures(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle futures trade analysis"""
    user_id = update.effective_user.id
    has_access, remaining = check_user_limit(user_id)

    if not has_access:
        await update.message.reply_text(
            "⚠️ You have used all your free requests!\n"
            "Please subscribe to continue using Easy Trade."
        )
        return

    if not context.args:
        await update.message.reply_text("⚠️ Please provide a coin symbol. Example: `/future ETH`",
                                        parse_mode="Markdown")
        return

    coin = context.args[0].upper()
    analyzing_msg = await update.message.reply_text(f"🔍 Analyzing {coin} Future Market...")

    try:
        result = await agent.process_query(f"Suggested Future trade for {coin}")
        update_user_usage(user_id)
        usage_msg = get_usage_message(user_id)

        final_message = result + usage_msg
        await analyzing_msg.edit_text(final_message, parse_mode="MarkdownV2")
    except Exception as e:
        await analyzing_msg.edit_text(f"❌ Error analyzing {coin} future market.\nError: {str(e)}")


async def analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle futures trade analysis"""
    user_id = update.effective_user.id
    has_access, remaining = check_user_limit(user_id)
    if not has_access:
        await update.message.reply_text(
            "⚠️ You have used all your free requests!\n"
            "Please subscribe to continue using Easy Trade."
        )
        return

    if not context.args:
        await update.message.reply_text("⚠️ Please provide a coin symbol. Example: `/analysis ETH`",
                                        parse_mode="Markdown")
        return

    coin = context.args[0].upper()
    analyzing_msg = await update.message.reply_text(f"🔍 Analyzing {coin}...")

    try:
        result = await agent.process_query(f"Detailed Analysis for {coin}")
        update_user_usage(user_id)
        usage_msg = get_usage_message(user_id)

        final_message = result + usage_msg
        await analyzing_msg.edit_text(final_message, parse_mode="MarkdownV2")
    except Exception as e:
        await analyzing_msg.edit_text(f"❌ Error analyzing {coin}.\nError: {str(e)}")


# ----------- Main -----------

async def post_init(application: Application):
    """Set bot commands for the menu"""
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("spot", "Spot trade analysis"),
        BotCommand("future", "Future trade analysis"),
        BotCommand("analysis", "Detailed coin analysis"),
    ]
    await application.bot.set_my_commands(commands)


def run_bot():
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("spot", spot))
    app.add_handler(CommandHandler("future", futures))
    app.add_handler(CommandHandler("analysis", analysis))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Telegram bot is running...")
    app.run_polling()


if __name__ == "__main__":
    run_bot()