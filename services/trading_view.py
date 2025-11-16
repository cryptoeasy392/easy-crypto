import math

import aiohttp
from config import config
from typing import Dict, Any

class TradingViewAPI:
    """
    Async TradingView API client with context management.
    Supports fetching technical analysis data.
    """

    def __init__(self):
        self.base_url = config.TRADINGVIEW_BASE_URL.rstrip("/")
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        """Async context manager entry - initialize HTTP session"""
        self.session = aiohttp.ClientSession(
            headers={
                "Accept": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=30)
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - close session"""
        if self.session:
            await self.session.close()

    async def _get(self, endpoint: str, params: dict = None) -> Dict[str, Any]:
        """Helper method to send GET requests"""
        if not self.session:
            raise RuntimeError("Session not initialized. Use 'async with' context.")

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            async with self.session.get(url, params=params) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            return {"error": str(e)}

    async def get_technical_analysis(self, coin_symbol: str, interval: str = None) -> Dict[str, float] | None:
        """Get technical analysis data with optional interval (e.g., 1W, 1D, 1M)"""

        base_fields = [
            "Recommend.Other", "Recommend.All", "Recommend.MA",
            "RSI", "RSI[1]",
            "Stoch.K", "Stoch.D", "Stoch.K[1]", "Stoch.D[1]",
            "CCI20", "CCI20[1]",
            "ADX", "ADX+DI", "ADX-DI", "ADX+DI[1]", "ADX-DI[1]",
            "AO", "AO[1]", "AO[2]",
            "Mom", "Mom[1]",
            "MACD.macd", "MACD.signal",
            "Rec.Stoch.RSI", "Stoch.RSI.K",
            "Rec.WR", "W.R",
            "Rec.BBPower", "BBPower",
            "Rec.UO", "UO",
            "EMA10", "close", "SMA10",
            "EMA20", "SMA20", "EMA30", "SMA30", "EMA50", "SMA50",
            "EMA100", "SMA100", "EMA200", "SMA200",
            "Rec.Ichimoku", "Ichimoku.BLine",
            "Rec.VWMA", "VWMA", "Rec.HullMA9", "HullMA9",
            "Pivot.M.Classic.R3", "Pivot.M.Classic.R2", "Pivot.M.Classic.R1",
            "Pivot.M.Classic.Middle", "Pivot.M.Classic.S1", "Pivot.M.Classic.S2", "Pivot.M.Classic.S3",
            "Pivot.M.Fibonacci.R3", "Pivot.M.Fibonacci.R2", "Pivot.M.Fibonacci.R1",
            "Pivot.M.Fibonacci.Middle", "Pivot.M.Fibonacci.S1", "Pivot.M.Fibonacci.S2", "Pivot.M.Fibonacci.S3",
            "Pivot.M.Camarilla.R3", "Pivot.M.Camarilla.R2", "Pivot.M.Camarilla.R1",
            "Pivot.M.Camarilla.Middle", "Pivot.M.Camarilla.S1", "Pivot.M.Camarilla.S2", "Pivot.M.Camarilla.S3",
            "Pivot.M.Woodie.R3", "Pivot.M.Woodie.R2", "Pivot.M.Woodie.R1",
            "Pivot.M.Woodie.Middle", "Pivot.M.Woodie.S1", "Pivot.M.Woodie.S2", "Pivot.M.Woodie.S3",
            "Pivot.M.Demark.R1", "Pivot.M.Demark.Middle", "Pivot.M.Demark.S1"
        ]

        # Append interval if provided
        if interval:
            fields = [f"{field}|{interval}" for field in base_fields]
        else:
            fields = base_fields

        params = {
            "symbol": f"CRYPTO:{coin_symbol}USD",  # corrected to use symbol param
            "fields": ",".join(fields),
            "no_404": "true",
            "label-product": "popup-technicals"
        }

        data = await self._get("/symbol", params=params)
        return data

    async def get_technical_analysis_pretty(
            self,
            coin_symbol: str,
            interval: str = None
    ) -> Dict[str, float] | None:
        """
        Get technical analysis data with human-readable field names.
        Includes all TradingView fields mapped to descriptive labels.
        """

        interval_suffix, interval_label = self._resolve_interval_suffix(interval)
        raw_data = await self.get_technical_analysis(coin_symbol, interval_suffix)

        if not raw_data or "error" in raw_data:
            return raw_data

        # Full mapping for all requested fields
        name_map = {
            "Recommend.Other": "Other Recommendations",
            "Recommend.All": "Overall Recommendation",
            "Recommend.MA": "Moving Average Recommendation",

            "RSI": "Relative Strength Index (RSI)",
            "RSI[1]": "RSI (Previous)",
            "Stoch.K": "Stochastic %K",
            "Stoch.D": "Stochastic %D",
            "Stoch.K[1]": "Stochastic %K (Previous)",
            "Stoch.D[1]": "Stochastic %D (Previous)",
            "CCI20": "Commodity Channel Index (CCI 20)",
            "CCI20[1]": "CCI 20 (Previous)",

            "ADX": "Average Directional Index (ADX)",
            "ADX+DI": "ADX Positive Directional Indicator (+DI)",
            "ADX-DI": "ADX Negative Directional Indicator (-DI)",
            "ADX+DI[1]": "ADX +DI (Previous)",
            "ADX-DI[1]": "ADX -DI (Previous)",

            "AO": "Awesome Oscillator (AO)",
            "AO[1]": "Awesome Oscillator (Previous)",
            "AO[2]": "Awesome Oscillator (2 Bars Ago)",

            "Mom": "Momentum",
            "Mom[1]": "Momentum (Previous)",

            "MACD.macd": "MACD Line",
            "MACD.signal": "MACD Signal Line",

            "Rec.Stoch.RSI": "Stochastic RSI Recommendation",
            "Stoch.RSI.K": "Stochastic RSI %K",

            "Rec.WR": "Williams %R Recommendation",
            "W.R": "Williams %R",

            "Rec.BBPower": "Bollinger Band Power Recommendation",
            "BBPower": "Bollinger Band Power",

            "Rec.UO": "Ultimate Oscillator Recommendation",
            "UO": "Ultimate Oscillator",

            "EMA10": "Exponential Moving Average (10)",
            "SMA10": "Simple Moving Average (10)",
            "EMA20": "Exponential Moving Average (20)",
            "SMA20": "Simple Moving Average (20)",
            "EMA30": "Exponential Moving Average (30)",
            "SMA30": "Simple Moving Average (30)",
            "EMA50": "Exponential Moving Average (50)",
            "SMA50": "Simple Moving Average (50)",
            "EMA100": "Exponential Moving Average (100)",
            "SMA100": "Simple Moving Average (100)",
            "EMA200": "Exponential Moving Average (200)",
            "SMA200": "Simple Moving Average (200)",

            "Rec.Ichimoku": "Ichimoku Cloud Recommendation",
            "Ichimoku.BLine": "Ichimoku Base Line",

            "Rec.VWMA": "VWMA Recommendation",
            "VWMA": "Volume Weighted Moving Average (VWMA)",

            "Rec.HullMA9": "Hull Moving Average (9) Recommendation",
            "HullMA9": "Hull Moving Average (9)",

            # Pivot Points - Classic
            "Pivot.M.Classic.R3": "Pivot Point Classic R3",
            "Pivot.M.Classic.R2": "Pivot Point Classic R2",
            "Pivot.M.Classic.R1": "Pivot Point Classic R1",
            "Pivot.M.Classic.Middle": "Pivot Point Classic Middle",
            "Pivot.M.Classic.S1": "Pivot Point Classic S1",
            "Pivot.M.Classic.S2": "Pivot Point Classic S2",
            "Pivot.M.Classic.S3": "Pivot Point Classic S3",

            # Pivot Points - Fibonacci
            "Pivot.M.Fibonacci.R3": "Pivot Point Fibonacci R3",
            "Pivot.M.Fibonacci.R2": "Pivot Point Fibonacci R2",
            "Pivot.M.Fibonacci.R1": "Pivot Point Fibonacci R1",
            "Pivot.M.Fibonacci.Middle": "Pivot Point Fibonacci Middle",
            "Pivot.M.Fibonacci.S1": "Pivot Point Fibonacci S1",
            "Pivot.M.Fibonacci.S2": "Pivot Point Fibonacci S2",
            "Pivot.M.Fibonacci.S3": "Pivot Point Fibonacci S3",

            # Pivot Points - Camarilla
            "Pivot.M.Camarilla.R3": "Pivot Point Camarilla R3",
            "Pivot.M.Camarilla.R2": "Pivot Point Camarilla R2",
            "Pivot.M.Camarilla.R1": "Pivot Point Camarilla R1",
            "Pivot.M.Camarilla.Middle": "Pivot Point Camarilla Middle",
            "Pivot.M.Camarilla.S1": "Pivot Point Camarilla S1",
            "Pivot.M.Camarilla.S2": "Pivot Point Camarilla S2",
            "Pivot.M.Camarilla.S3": "Pivot Point Camarilla S3",

            # Pivot Points - Woodie
            "Pivot.M.Woodie.R3": "Pivot Point Woodie R3",
            "Pivot.M.Woodie.R2": "Pivot Point Woodie R2",
            "Pivot.M.Woodie.R1": "Pivot Point Woodie R1",
            "Pivot.M.Woodie.Middle": "Pivot Point Woodie Middle",
            "Pivot.M.Woodie.S1": "Pivot Point Woodie S1",
            "Pivot.M.Woodie.S2": "Pivot Point Woodie S2",
            "Pivot.M.Woodie.S3": "Pivot Point Woodie S3",

            # Pivot Points - Demark
            "Pivot.M.Demark.R1": "Pivot Point Demark R1",
            "Pivot.M.Demark.Middle": "Pivot Point Demark Middle",
            "Pivot.M.Demark.S1": "Pivot Point Demark S1",

            "close": "Closing Price"
        }

        # Build readable output
        pretty_data = {}
        for key, value in raw_data.items():
            base_key = key.split("|")[0]
            if value is None:
                continue  # skip missing data

            # build readable name
            readable = name_map.get(base_key, base_key)

            # append interval name if applicable
            if interval_label:
                readable += f" ({interval_label})"

            # interpret & format the number
            interpreted = self.interpret_indicator(base_key, value)

            if interpreted is not None:
                pretty_data[readable] = interpreted

        return pretty_data

    def interpret_indicator(self, name: str, value: float) -> str | None | Any:
        """Convert raw indicator values into meaningful, formatted strings."""
        if value is None or math.isnan(value):
            return None

        # Recommendation-like values
        if "Recommend" in name:
            return self.interpret_recommendation(value)

        # Price-like indicators (numbers that look like BTC/USD prices)
        if any(word in name.lower() for word in [
            "price", "close", "open", "high", "low", "target",
            "sma", "ema", "bb.upper", "bb.lower",
            "pivot", "ichimoku", "hull", "vwma", "ao", "bbpower"
        ]):
            return f"${value:,.2f}"

        # Momentum / oscillator indicators
        if "rsi" in name.lower():
            if value > 70:
                meaning = "Overbought"
            elif value < 30:
                meaning = "Oversold"
            else:
                meaning = "Neutral"
            return f"{value:.2f} ({meaning})"

        if "macd" in name.lower():
            meaning = "Bullish" if value > 0 else "Bearish" if value < 0 else "Neutral"
            return f"{value:.2f} ({meaning})"

        if "ao" in name.lower():  # Awesome Oscillator
            meaning = "Bullish" if value > 0 else "Bearish" if value < 0 else "Neutral"
            return f"{value:.2f} ({meaning})"

        # Default numeric format
        return f"{value:.2f}"

    @staticmethod
    def interpret_recommendation(value: float) -> str | None:
        """Convert TradingView recommendation numeric value to label."""
        if value is None or math.isnan(value):
            return None
        if value >= 0.5:
            return "Strong Buy"
        elif value >= 0.1:
            return "Buy"
        elif value <= -0.5:
            return "Strong Sell"
        elif value <= -0.1:
            return "Sell"
        else:
            return "Neutral"

    @staticmethod
    def _resolve_interval_suffix(interval: str | None) -> tuple[str | None, str | None]:
        """
        Map human-readable interval (like '1 day', '4 hours') to TradingView API suffix
        and readable label.
        Returns: (api_suffix, readable_label)
        If no interval is provided, defaults to '1 day' (Daily).
        Raises ValueError if an unsupported interval is passed.
        """

        # Default interval → Daily
        if not interval:
            interval = "1 day"

        mapping = {
            "1 minute": ("1", "1-Minute"),
            "5 minutes": ("5", "5-Minute"),
            "15 minutes": ("15", "15-Minute"),
            "30 minutes": ("30", "30-Minute"),
            "1 hour": ("60", "1-Hour"),
            "2 hours": ("120", "2-Hour"),
            "4 hours": ("240", "4-Hour"),
            "1 day": (None, "Daily"),  # default (no |suffix)
            "1 week": ("1W", "Weekly"),
            "1 month": ("1M", "Monthly"),
        }

        # Strict validation — reject unknown intervals
        if interval not in mapping:
            raise ValueError(
                f"Invalid interval '{interval}'. Allowed values are: {', '.join(mapping.keys())}"
            )

        return mapping[interval]


