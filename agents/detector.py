import json
from typing import Dict
from openai import AsyncOpenAI
import re
from logger import logger
from config import config
from services.api import CoinGeckoAPI


class CoinDetectorAgent:
    """
    Agent specialized in detecting cryptocurrency coin IDs from user queries.
    Uses OpenAI to parse natural language and return structured coin identification.
    """

    def __init__(self):
        self.client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)

    async def detect_coin(self, user_query: str) -> Dict[str, str]:
        """
        Detect cryptocurrency coin symbol, time interval, and language from user query.

        Args:
            user_query: Natural language query from user

        Returns:
            Dictionary with coin_id, symbol, interval, and language keys
        """
        prompt = f"""
        You are a cryptocurrency coin identifier. Your task is to identify the specific cryptocurrency coin symbol, time interval, and the language of the user's query.
        Understand user query and figure out the symbol, interval, and language.

        Examples of coin symbols mapping:
        - Bitcoin, BTC, bitcoin, بيتكوين → BTC
        - Ethereum, ETH, ethereum, ether, إيثيريوم → ETH  
        - Binance Coin, BNB, binance, بينانس كوين → BNB

        Valid intervals:
        - "1 minute"
        - "5 minutes"
        - "15 minutes"
        - "30 minutes"
        - "1 hour"
        - "2 hours"
        - "4 hours"
        - "1 day" (default)
        - "1 week"
        - "1 month"

        Supported languages:
        - "English" - for English queries
        - "Arabic" - for Arabic queries (e.g., تحليل، عملة، سعر)
        - "Spanish" - for Spanish queries
        - "French" - for French queries
        - "German" - for German queries
        - Other languages as needed

        User Query: "{user_query}"

        Analyze the query and identify:
        1. The cryptocurrency symbol
        2. The time interval (if mentioned)
        3. The language of the query

        Return ONLY a valid JSON object:

        {{"symbol": "identified_coin_symbol", "interval": "identified_interval", "language": "detected_language"}}

        Rules:
        - Return only valid JSON, no additional text
        - Use uppercase coin symbols as shown in the examples
        - Look for ticker symbols or coin names in any language
        - If no interval is mentioned, use "1 month"
        - Interval must match exactly one of the valid intervals listed above
        - Language must be the full name (e.g., "English", "Arabic", not "en", "ar")
        - Detect language based on the script and vocabulary used in the query
        """

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a cryptocurrency coin identifier."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0
            )
            response_text = response.choices[0].message.content.strip()

            # Extract JSON from response
            json_match = re.search(r'\{[^}]+\}', response_text)
            if json_match:
                json_str = json_match.group(0)
                result = json.loads(json_str)
                if 'symbol' in result:
                    interval = result.get('interval', '1 month')
                    language = result.get('language', 'Arabic')

                    async with CoinGeckoAPI() as api:
                        coin_id = await api.search_coin_id(result['symbol'])
                        logger.info(f"Successfully run coin detector for {result['symbol']}")
                        return {
                            'coin_id': coin_id,
                            'symbol': result['symbol'],
                            'interval': interval,
                            'language': language
                        }

        except Exception as e:
            logger.error(f"Error in coin detection: {e}")

        # Return default values if detection fails
        return {
            'coin_id': 'UNKNOWN',
            'symbol': 'UNKNOWN',
            'interval': '1 month',
            'language': 'Arabic'
        }