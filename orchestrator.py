from agents.detector import CoinDetectorAgent
from agents.expert import CryptoExpertAgent


class CryptoAISystem:
    """Main system orchestrating both agents using OpenAI"""

    def __init__(self):
        self.coin_detector = CoinDetectorAgent()
        self.expert_agent = CryptoExpertAgent()

    async def process_query(self, user_query: str) -> str:
        """Process user query through the two-agent system"""

        # Step 1: Extract coin symbol, interval, and language
        coin_info = await self.coin_detector.detect_coin(user_query)

        # Step 2: Run expert analysis with detected parameters
        result = await self.expert_agent.chat(
            user_query,
            coin_info.get("coin_id"),
            coin_info.get("symbol"),
            coin_info.get("interval"),
            coin_info.get("language")
        )

        # Step 3: Format for Telegram
        result = self.expert_agent.format_for_telegram(result)

        return result