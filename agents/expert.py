from typing import Dict, Any, List
from openai import AsyncOpenAI
from config import config
from logger import logger
from services.api import CoinGeckoAPI
import re
import asyncio
import json

from services.coincodex import CoinCodex
from services.trading_view import TradingViewAPI
from strategies.classic_new import ClassicalAnalyst

class CryptoExpertAgent:
    """
    Expert cryptocurrency analysis agent using OpenAI with tool calling.
    """

    def __init__(self):
        self.client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
        self.conversation_history: List[Dict[str, Any]] = []

        # Define the tool schema for OpenAI
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_crypto_analysis",
                    "description": "Get comprehensive cryptocurrency analysis including price, technical indicators, and AI insights",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "coin_id": {
                                "type": "string",
                                "description": "The cryptocurrency coin ID (e.g., 'bitcoin', 'ethereum')"
                            },
                            "coin_symbol": {
                                "type": "string",
                                "description": "The cryptocurrency symbol (e.g., 'BTC', 'ETH')"
                            },
                            "interval": {
                                "type": "string",
                                "description": "Time interval for analysis. Must be one of: '1 minute', '5 minutes', '15 minutes', '30 minutes', '1 hour', '2 hours', '4 hours', '1 day', '1 week', '1 month'",
                                "default": "1 month"
                            },
                            "language": {
                                "type": "string",
                                "description": "The language of the agent output (e.g., 'Arabic', 'English', 'Spanish')",
                                "default": "Arabic"
                            }
                        },
                        "required": ["coin_id", "coin_symbol"]
                    }
                }
            }
        ]

        self.system_prompt = """
You are CryptoSage, a professional cryptocurrency trading analyst providing actionable trade setups and market analysis.

LANGUAGE POLICY (HARD ENFORCEMENT):
- Detect the user's language from their latest message.
- Always respond in that same language, regardless of the question topic.
- Never switch to English unless the user does.
- Maintain the same tone and style in that language.

CORE CAPABILITIES:
1. Real-time price analysis and market structure assessment
2. Entry/exit levels with risk management
3. Support/resistance (liquidity zone) identification
4. Trade setup recommendations with leverage guidance
5. Multi-timeframe perspective (daily, short-term)

DATA INTEGRATION RULES:
- Always interpret **all sections** from the tool output:
  * Current Price
  * Market Data (fear & greed, sentiment, volatility, green days)
  * Predictions (short/long term)
  * Technical Analysis (indicators, SMA, RSI, etc.)
  * Classical School Analysis (long/short setups)
- Use Market Data to gauge **overall sentiment**, risk appetite, and volatility context.
- Use Predictions for directional bias reinforcement (if aligned with analysis).
- Combine Technical + Classical + Market Data for a unified, confluence-based conclusion.
- Avoid listing all raw values; summarize meaningfully (e.g. "Extreme Fear and medium volatility indicate risk-off environment").

STRATEGY INTEGRATION RULES:
- Consider **all available data** in the tool output.
- Always include short references to the Classical School Analysis section covering **all 4 scenarios**:
  * Spot Long
  * Spot Short
  * Futures Long
  * Futures Short
- For each, briefly mention its directional bias, key target, and stop loss — **one short line per scenario**.
- Integrate them naturally into “Market Insights” or “Final Recommendation” without increasing total word count.
- Example (in one compact paragraph):  
  "Classical Analysis shows spot bias bullish toward 0.23 with stops at 0.16, while futures long aims for 0.32; short setups remain conservative."


TOOL USAGE DECISION RULES:
- ALWAYS use `get_crypto_analysis` tool when user asks for:
  * Market analysis, technical analysis, or trading advice
  * Price predictions or forecasts
  * Trading signals or recommendations
  * Trade setups or deals
  * Current price with context
  * Support/resistance levels
  * Market sentiment analysis
  * Any analysis request

PRIMARY RESPONSE FORMAT FOR DETAILED ANALYSIS:
**DETAILED ANALYSIS FOR [COIN_SYMBOL]:**

**LONG (Buy Scenario):**
Entry Zones:
1. [spot_price] (Spot) / [futures_price] (Futures) — [reason]
2. [spot_price] (Spot) / [futures_price] (Futures) — [reason]
Stop Loss: [spot_sl] (Spot) / [futures_sl] (Futures)
Targets:
1. [spot_target] (Spot) / [futures_target] (Futures)
2. [spot_target] (Spot) / [futures_target] (Futures)
3. [spot_target] (Spot) / [futures_target] (Futures) [if applicable]

**SHORT (Sell Scenario):**
Entry Zones:
1. [spot_price] (Spot) / [futures_price] (Futures) — [reason]
2. [spot_price] (Spot) / [futures_price] (Futures) — [reason]
Stop Loss: [spot_sl] (Spot) / [futures_sl] (Futures)
Targets:
1. [spot_target] (Spot) / [futures_target] (Futures)
2. [spot_target] (Spot) / [futures_target] (Futures)
3. [spot_target] (Spot) / [futures_target] (Futures) [if applicable]

**Market Insights:**
- Current Trend: [bullish / bearish / neutral with % change]
- Sentiment & Fear/Greed: [interpret overall tone, e.g. "Extreme Fear → contrarian buy pressure possible"]
- Volatility: [low / medium / high with implication for risk]
- Green Days: [brief insight on recent market consistency]
- Support / Resistance: [price levels]
- Technical Bias (from combined strategies): [summary of SMC + Classical alignment]
- Confidence Level: [qualitative rating based on data agreement]
- Futures Leverage: [Choose the most higher one between 10–20x based on volatility, confidence, and alignment]


**Final Recommendation:**
- Best Approach: LONG / SHORT
- Justification: [1–2 concise sentences — clear reason based on structure, sentiment, and confluence]

SIMPLIFIED FORMAT FOR SINGLE DIRECTION SETUP [MUST HAVE BOTH LONG AND SHORT]:
**SUGGESTED TRADE FOR [COIN_SYMBOL]:**
Entry Points between [price] (Long) and [price] (Short)
Stop Loss between [price] (Long) and [price] (Short)
Targets: 
1. [target] (Long) and [target] (Short)
2. [target] (Long) and [target] (Long)
3. [target] (Long) and [target] (Short) [if applicable]
Recommended Leverage: [ONLY WHEN A FUTURE TRADE IS REQUESTED]
Suggested Trade: [LONG or SHORT and 1–2 concise sentences of clear reasoning of why this trade is the best now]

RESPONSE STYLE RULES:
- Under 200 words if possible.
- Focus on actionable direction and entries.
- Avoid indicator lists; interpret instead.
- Always include stop loss and at least two targets.
- Use real prices from the tool output (Current, SMC, Classical, Market Data).
- Use the analysis format for analysis queries only
- Use the simplified format for queries like "Suggested Future trade for" or "Suggested Spot trade for"

RISK GUIDELINES:
- Conservative setups: 1x–2x leverage
- Moderate: 2x–3x
- Aggressive: 3x–5x (only if all strategies align)
- Always emphasize risk management.

PERSONAL QUERIES:
- "Who are you": "I am CryptoSage, your cryptocurrency trading analyst providing concise, reliable trade setups and market insights."
- "What can you do": Describe your trading and analysis capabilities in the user's language.

CRITICAL RULES:
- Match the user's language completely.
- Combine insights from all strategy and market data.
- Keep answers brief, direct, and professional.
- Never echo or list raw data.
- Focus on interpretation and actionable guidance.
"""

    async def _execute_analysis_tool(self, coin_id: str, coin_symbol: str, interval: str) -> Dict[str, Any]:
        """Execute the analysis tool with parallel async operations."""
        try:
            coingecko_api = CoinGeckoAPI()
            trading_view_api = TradingViewAPI()

            # Properly enter async context managers
            await coingecko_api.__aenter__()
            await trading_view_api.__aenter__()

            try:
                coin_codex = CoinCodex()
                classic = ClassicalAnalyst()

                # Execute all API calls in parallel
                price, technical = await asyncio.gather(
                    coingecko_api.get_price(coin_id),
                    trading_view_api.get_technical_analysis_pretty(coin_symbol, interval),
                )

                coin_codex_data = await coin_codex.get_coin_data(coin_id)

                # Analyze classical with all data
                classic_analysis = await classic.analyze(coin_id, coin_codex_data, technical)

                data = {
                    "Current Price": price,
                    "Market Data": coin_codex_data["market_data"],
                    "Predictions": coin_codex_data["predictions"],
                    "Technical Analysis": technical,
                    "Classical School Analysis Short Scenario": classic_analysis["scenarios"],
                }

                logger.info("Successfully run crypto analysis tool async.")
                logger.info(f"data: {data}")

                return data

            finally:
                # Properly close resources
                await coingecko_api.__aexit__(None, None, None)
                await trading_view_api.__aexit__(None, None, None)

        except Exception as e:
            logger.error(f"Error executing analysis tool: {e}")
            return {"error": str(e)}

    async def chat(self, query: str, coin_id: str = None, coin_symbol: str = None,
                   interval: str = "1 month", user_language: str = 'Arabic') -> str:
        """
        Run the agent with OpenAI tool calling.
        """
        try:
            # Prepare the user message
            if coin_id and coin_symbol:
                user_message = f"""
User Query: {query}

Context: Analyze {coin_id} ({coin_symbol}) with interval: {interval}

Instructions: Use the get_crypto_analysis tool with these exact parameters:
- coin_id: {coin_id}
- coin_symbol: {coin_symbol}
- interval: {interval}

Output Language: {user_language}
"""
            else:
                user_message = query

            # Add user message to history
            self.conversation_history.append({
                "role": "user",
                "content": user_message
            })

            # Initial API call
            response = await self.client.chat.completions.create(
                model="gpt-5-mini",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    *self.conversation_history
                ],
                tools=self.tools,
                tool_choice="auto"
            )

            response_message = response.choices[0].message

            # Handle tool calls
            while response_message.tool_calls:
                # Add assistant's response to history
                self.conversation_history.append({
                    "role": "assistant",
                    "content": response_message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        } for tc in response_message.tool_calls
                    ]
                })

                # Execute each tool call
                for tool_call in response_message.tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)

                    if function_name == "get_crypto_analysis":
                        # Execute the analysis tool
                        tool_result = await self._execute_analysis_tool(
                            coin_id=function_args.get("coin_id"),
                            coin_symbol=function_args.get("coin_symbol"),
                            interval=function_args.get("interval", "1 month")
                        )

                        # Add tool result to history
                        self.conversation_history.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": function_name,
                            "content": json.dumps(tool_result)
                        })

                # Get the final response with tool results
                response = await self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        *self.conversation_history
                    ],
                    temperature=0.1
                )

                response_message = response.choices[0].message

            # Add final assistant response to history
            self.conversation_history.append({
                "role": "assistant",
                "content": response_message.content
            })

            return response_message.content or "No response generated"

        except Exception as e:
            logger.error(f"Error in chat: {e}")
            return {
                "English": f"I apologize, but I'm experiencing technical difficulties. As CryptoSage, I specialize in cryptocurrency analysis for {coin_id.upper() if coin_id else 'cryptocurrencies'}. Please try again.",
                "Arabic": f"أعتذر، ولكنني أواجه صعوبات تقنية. كـ CryptoSage، أتخصص في تحليل العملات المشفرة لـ {coin_id.upper() if coin_id else 'العملات المشفرة'}. يرجى المحاولة مرة أخرى."
            }.get(user_language, "I apologize, please try again.")

    @staticmethod
    def format_for_telegram(md_content: str) -> str:
        """
        Convert LLM Markdown output into Telegram-friendly MarkdownV2.
        """
        # Convert headings (##, ###, etc.) → Bold uppercase lines
        md_content = re.sub(r'#{1,6}\s*(.+)', lambda m: f"*{m.group(1).upper()}*", md_content)

        # Convert bold (**text**) → *text*
        md_content = re.sub(r'\*\*(.+?)\*\*', r'*\1*', md_content)

        # Remove any remaining backticks (to avoid Telegram parsing issues)
        md_content = md_content.replace("`", "")

        # Escape Telegram special chars (_ [ ] ( ) ~ > # + - = | { } . !)
        special_chars = r'[_\[\]\(\)~`>#+\-=|{}.!]'
        md_content = re.sub(special_chars, lambda m: f"\\{m.group(0)}", md_content)

        return md_content