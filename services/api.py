from datetime import datetime

import aiohttp
from config import config
from typing import Dict, List, Tuple, Any
import pandas as pd
import polars as pl


class CoinGeckoAPI:
    """
    Async CoinGecko API client with context management.
    Supports fetching cryptocurrency data for Telegram bots or other async apps.
    """

    def __init__(self):
        self.base_url = config.COINGECKO_BASE_URL.rstrip("/")
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        """Async context manager entry - initialize HTTP session"""
        self.session = aiohttp.ClientSession(
            headers={
                "Accept": "application/json",
                "x-cg-demo-api-key": config.COINGECKO_API_KEY
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

    async def search_coin_id(self, query: str) -> str | None:
        """Search for a coin id by query"""
        data = await self._get("search", params={"query": query})
        if "coins" in data and data["coins"]:
            return data["coins"][0].get("id")
        return None
    
    async def get_price(self, coin_id: str) -> Dict[str, float] | None:
        """Get a coin price"""
        params = {
            'ids': coin_id,
            'vs_currencies': 'usd',
            'include_24hr_change': 'true'
        }
        data = await self._get("simple/price", params=params)
        price_data = {
            'price': round(data[coin_id]['usd'], 2),  # two digits after point
            'change24h': round(data[coin_id].get('usd_24h_change', 0), 2),
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # readable real time
        }
        return price_data
    
    def _calculate_24h_change(self, prices: List[Tuple[int, float]]) -> float:
        """
        Calculate 24-hour price change percentage.
        
        Args:
            prices: List of [timestamp, price] tuples
            
        Returns:
            Percentage change over 24 hours
        """
        if len(prices) < 2:
            return 0.0
        
        current_price = prices[-1][1]
        yesterday_price = prices[-2][1]
        
        return ((current_price - yesterday_price) / yesterday_price) * 100

    async def get_historical_data(self, coin_id: str, days: int = 180) -> Dict[str, float] | None:
        """Get a coin historical price and volume data"""
        params = {
                'vs_currency': 'usd',
                'days': str(days),
                'precision': '2'
            }
        data = await self._get(f"coins/{coin_id}/market_chart", params=params)
        # Transform data into consistent format
        transformed_data = {
            'prices': [item[1] for item in data['prices']],
            'volumes': [item[1] for item in data['total_volumes']],
            'timestamps': [item[0] for item in data['prices']],
            'current_price': data['prices'][-1][1],
            'market_cap': data['market_caps'][-1][1],
            'price_change_24h': self._calculate_24h_change(data['prices'])
        }
        return transformed_data
    
    async def get_sentiment(self, coin_id: str) -> Dict[str, float] | None:
        """Generate sentiment data based on market analysis"""
        # Get market data for sentiment analysis
        price_data = await self.get_price(coin_id)
        historical_data = await self.get_historical_data(coin_id)
        
        # Calculate volume change
        volumes = historical_data['volumes']
        if len(volumes) > 1:
            volume_change = ((volumes[-1] - volumes[0]) / volumes[0]) * 100
        else:
            volume_change = 0
        
        # Determine sentiment based on price change
        price_change = price_data.get('change24h')
        if price_change > 2:
            sentiment = 'Bullish'
        elif price_change < -2:
            sentiment = 'Bearish'
        else:
            sentiment = 'Neutral'
        
        sentiment_data = {
            'source': 'Market Analysis',
            'sentiment': sentiment,
            'volume': round(min(100, max(0, abs(volume_change))), 2),
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        return sentiment_data
    
    async def get_predictions(self, coin_id: str) -> List[Dict[str, Any]] | None:
        """Generate price predictions based on historical data analysis"""
        # Get historical data for predictions
        historical_data = await self.get_historical_data(coin_id)
        current_price = round(historical_data['current_price'], 2)
        
        # Generate predictions with some randomization (in real implementation, use ML models)
        import random
        
        predictions_data = [
            {
                'period': 'Short-term',
                'price': current_price * (1 + (random.random() * 0.1 - 0.05)),  # ±5%
                'confidence': round(75 + random.random() * 20, 2),
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            },
            {
                'period': 'Mid-term',
                'price': current_price * (1 + (random.random() * 0.2 - 0.1)),  # ±10%
                'confidence': round(65 + random.random() * 20, 2),
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            },
            {
                'period': 'Long-term',
                'price': current_price * (1 + (random.random() * 0.3 - 0.15)),  # ±15%
                'confidence': round(55 + random.random() * 20, 2),
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        ]
        return predictions_data
    
    async def get_ohlc_data(self, coin_id: str, days: int = 180) -> pl.DataFrame:
        """Get a coin OHLC chart (Open, High, Low, Close) data"""
        params = {
            "vs_currency": "usd",
            "days": str(days)
        }
        data = await self._get(f"coins/{coin_id}/ohlc", params=params)

        if not data:
            return None

        # Transform into DataFrame with timestamp
        # df = pd.DataFrame(
        #     data,
        #     columns=["timestamp", "open", "high", "low", "close"]
        # )
        df = pl.DataFrame(
            data,
            schema={
                "timestamp": pl.Int64,  # Timestamps are usually large integers (ms)
                "open": pl.Float64,
                "high": pl.Float64,
                "low": pl.Float64,
                "close": pl.Float64,
            },
            orient="row"
        )

        # Convert timestamp from ms to datetime
        # df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        # df.set_index("timestamp", inplace=True)
        df = df.with_columns(
            pl.col("timestamp")
            .cast(pl.Datetime(time_unit="ms"))
            .alias("timestamp")  # Replaces the old 'timestamp' column
        )
        df = df.sort("timestamp")

        return df

    async def get_historical_volume_df(self, coin_id: str, days: int = 180) -> pd.DataFrame:
        """
        Get historical volume data as a pandas DataFrame.

        Returns:
            DataFrame with:
                index   -> datetime (from timestamp)
                columns -> ["volume"]
        """
        data = await self.get_historical_data(coin_id, days)
        if not data:
            return None

        # Build DataFrame
        df = pd.DataFrame({
            "timestamp": data["timestamps"],
            "volume": data["volumes"]
        })

        # Convert timestamp to datetime
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

        # Set timestamp as index
        df.set_index("timestamp", inplace=True)

        return df

    async def get_ohlcv_data(self, coin_id: str) -> pd.DataFrame:
        """
        Get combined OHLCV data (Open, High, Low, Close, Volume) as a single DataFrame.
        """

        # Get OHLC data (returns a DataFrame)
        ohlc_df = await self.get_ohlc_data(coin_id, 30)
        if ohlc_df is None or ohlc_df.empty:
            return None

        # Get Volume data (returns a DataFrame with timestamp index)
        volume_df = await self.get_historical_volume_df(coin_id, 30)
        if volume_df is None or volume_df.empty:
            ohlc_df["volume"] = None
            return ohlc_df

        # Align by timestamp (inner join to ensure same days)
        # ohlcv_df = ohlc_df.join(volume_df, how="inner")
        ohlcv_df = self.merge_ohlc_with_nearest_volume(ohlc_df, volume_df)

        return ohlcv_df

    @staticmethod
    def merge_ohlc_with_nearest_volume(ohlc_df: pd.DataFrame, vol_df: pd.DataFrame) -> pd.DataFrame:
        """
        Merge OHLC (4h) and volume (irregular/hourly) data by nearest timestamp.

        Both DataFrames must have datetime indexes.
        Returns a new OHLCV DataFrame.
        """
        # Ensure proper datetime index and sort
        ohlc_df = ohlc_df.sort_index()
        vol_df = vol_df.sort_index()

        # Reset index for merge_asof
        ohlc_df = ohlc_df.reset_index().rename(columns={'index': 'timestamp'})
        vol_df = vol_df.reset_index().rename(columns={'index': 'timestamp'})

        # Merge by nearest timestamp
        merged = pd.merge_asof(
            ohlc_df,
            vol_df,
            on='timestamp',
            direction='nearest',
            tolerance=pd.Timedelta('2H')  # optional: max gap allowed (2 hours)
        )

        # If some OHLC rows didn’t find a nearby volume, they’ll have NaN
        merged = merged.set_index('timestamp')

        return merged
