import os
from dataclasses import dataclass
from dotenv import load_dotenv


# Load dotenv variables
load_dotenv()

# ================== CONFIGURATION ==================
@dataclass
class Config:
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")
    COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3/"
    TRADINGVIEW_BASE_URL = "https://scanner.tradingview.com/"


config = Config()