import re
from typing import Optional
import requests
from bs4 import BeautifulSoup

from utils import parse_percent


class CoinCodex:
    """
    CoinCodex scraper using requests library. Provides:
    - get_coin_data(coin_id) -> {
          'coin': coin_id,
          'predictions': {...},
          'market_data': {...}
      }
    """
    BASE_URL = "https://coincodex.com/crypto/{coin_id}/price-prediction/"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })

    def fetch_html(self, coin_id: str) -> str:
        url = self.BASE_URL.format(coin_id=coin_id)
        response = self.session.get(url)
        response.raise_for_status()
        return response.text

    def _clean_price(self, price_str: str) -> str:
        """Remove $ symbol, unicode spaces, and commas from price strings"""
        # Remove $ symbol, \u202f (narrow no-break space), and commas
        cleaned = price_str.replace('\u202f', '').replace(',', '').strip()

        return cleaned

    def _extract_market_data(self, html_text: str) -> dict:
        soup = BeautifulSoup(html_text, 'html.parser')
        market = {}

        # Find the market data table
        market_table = soup.find('table', class_='table-grid prediction-data-table')
        if not market_table:
            return market

        rows = market_table.find_all('tr')

        for row in rows:
            th = row.find('th')
            td = row.find('td')

            if not th or not td:
                continue

            label = th.get_text(strip=True)
            value = td.get_text(strip=True)

            # Current Price
            if 'Current Price' in label:
                price_match = re.search(r'\$\s*([0-9,]+(?:\.[0-9]+)?)', value)
                if price_match:
                    market["current_price"] = float(price_match.group(1).replace(",", ""))

            # Price Prediction
            elif 'Price Prediction' in label:
                price_match = re.search(r'\$\s*([0-9,]+(?:\.[0-9]+)?)', value)
                if price_match:
                    market["predicted_price"] = float(price_match.group(1).replace(",", ""))
                # Extract percentage change (look for parentheses)
                pct_match = re.search(r'\(([0-9.,]+%?)\)', value)
                if pct_match:
                    market["predicted_change"] = parse_percent(pct_match.group(1))

            # Fear & Greed Index
            elif 'Fear' in label and 'Greed' in label:
                # Extract just the number and sentiment (e.g., "29 (Fear)")
                fear_match = re.search(r'(\d+)\s*\(([^)]+)\)', value)
                if fear_match:
                    market["fear_greed"] = f"{fear_match.group(1)} ({fear_match.group(2)})"
                else:
                    market["fear_greed"] = value

            # Sentiment
            elif 'Sentiment' in label:
                # Extract sentiment value (Bullish/Bearish/Neutral)
                sentiment_match = re.search(r'(Bullish|Bearish|Neutral)', value, re.IGNORECASE)
                market["sentiment"] = sentiment_match.group(1) if sentiment_match else value

            # Volatility
            elif 'Volatility' in label:
                vol_match = re.search(r'([0-9.,]+%?)', value)
                if vol_match:
                    market["volatility"] = parse_percent(vol_match.group(1))

            # Green Days
            elif 'Green Days' in label:
                market["green_days"] = value

            # 50-Day SMA
            elif '50-Day SMA' in label:
                sma_match = re.search(r'\$\s*([0-9,]+(?:\.[0-9]+)?)', value)
                if sma_match:
                    market["sma50"] = float(sma_match.group(1).replace(",", ""))

            # 200-Day SMA
            elif '200-Day SMA' in label:
                sma_match = re.search(r'\$\s*([0-9,]+(?:\.[0-9]+)?)', value)
                if sma_match:
                    market["sma200"] = float(sma_match.group(1).replace(",", ""))

            # 14-Day RSI
            elif '14-Day RSI' in label:
                rsi_match = re.search(r'([0-9.]+)', value)
                if rsi_match:
                    market["rsi_14"] = float(rsi_match.group(1))

        return market

    async def get_coin_data(self, coin_id: str) -> dict:
        """Make this async to match usage in your code"""
        html = self.fetch_html(coin_id)
        predictions = self._extract_prediction_tables(html)
        market_data = self._extract_market_data(html)
        return {"coin": coin_id, "predictions": predictions, "market_data": market_data}

    def close(self):
        self.session.close()

    def _clean_date(self, date_str: str) -> str:
        """Remove commas from dates"""
        return date_str.replace(',', '').strip()

    def _extract_prediction_tables(self, html_text: str) -> dict:
        soup = BeautifulSoup(html_text, 'html.parser')
        result = {"short_term": [], "long_term": []}

        # Find all tables with the specific class combination
        tables = soup.find_all('table', class_='formatted-table full-size-table table-scrollable')

        # Short-term table is the FIRST one (index 0)
        if len(tables) >= 1:
            short_term_table = tables[0]
            tbody = short_term_table.find('tbody')
            if tbody:
                rows = tbody.find_all('tr')
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 3:
                        date = self._clean_date(cols[0].get_text(strip=True))

                        # Extract prediction value from app-prediction-value tag
                        pred_col = cols[1]
                        pred_value_tag = pred_col.find('app-prediction-value')
                        prediction = pred_value_tag.get_text(strip=True) if pred_value_tag else pred_col.get_text(
                            strip=True)
                        prediction = self._clean_price(prediction)

                        # Extract change percentage from span
                        change_col = cols[2]
                        change_span = change_col.find('span')
                        change = change_span.get_text(strip=True) if change_span else change_col.get_text(strip=True)

                        result["short_term"].append({
                            "date": date,
                            "prediction": prediction,
                            "change": change
                        })

        # Long-term table is the SECOND one (index 1)
        if len(tables) >= 2:
            long_term_table = tables[1]
            tbody = long_term_table.find('tbody')
            if tbody:
                rows = tbody.find_all('tr')
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 5:
                        month = self._clean_date(cols[0].get_text(strip=True))

                        # Extract min, avg, max prices from app-prediction-value tags
                        min_tag = cols[1].find('app-prediction-value')
                        min_price = min_tag.get_text(strip=True) if min_tag else cols[1].get_text(strip=True)
                        min_price = self._clean_price(min_price)

                        avg_tag = cols[2].find('app-prediction-value')
                        avg_price = avg_tag.get_text(strip=True) if avg_tag else cols[2].get_text(strip=True)
                        avg_price = self._clean_price(avg_price)

                        max_tag = cols[3].find('app-prediction-value')
                        max_price = max_tag.get_text(strip=True) if max_tag else cols[3].get_text(strip=True)
                        max_price = self._clean_price(max_price)

                        # Extract change percentage from span
                        change_col = cols[4]
                        change_span = change_col.find('span')
                        change = change_span.get_text(strip=True) if change_span else change_col.get_text(strip=True)

                        result["long_term"].append({
                            "month": month,
                            "min_price": min_price,
                            "avg_price": avg_price,
                            "max_price": max_price,
                            "change": change
                        })

        return result

    def _extract_market_data(self, html_text: str) -> dict:
        soup = BeautifulSoup(html_text, 'html.parser')
        market = {}

        # Find the market data table
        market_table = soup.find('table', class_='table-grid prediction-data-table')
        if not market_table:
            return market

        rows = market_table.find_all('tr')

        for row in rows:
            th = row.find('th')
            td = row.find('td')

            if not th or not td:
                continue

            label = th.get_text(strip=True)
            value = td.get_text(strip=True)

            # Current Price
            if 'Current Price' in label:
                price_match = re.search(r'\$\s*([0-9,]+(?:\.[0-9]+)?)', value)
                if price_match:
                    market["current_price"] = float(price_match.group(1).replace(",", ""))

            # Price Prediction
            elif 'Price Prediction' in label:
                price_match = re.search(r'\$\s*([0-9,]+(?:\.[0-9]+)?)', value)
                if price_match:
                    market["predicted_price"] = float(price_match.group(1).replace(",", ""))
                # Extract percentage change (look for parentheses)
                pct_match = re.search(r'\(([0-9.,]+%?)\)', value)
                if pct_match:
                    market["predicted_change"] = parse_percent(pct_match.group(1))

            # Fear & Greed Index
            elif 'Fear' in label and 'Greed' in label:
                # Extract just the number and sentiment (e.g., "29 (Fear)")
                fear_match = re.search(r'(\d+)\s*\(([^)]+)\)', value)
                if fear_match:
                    market["fear_greed"] = f"{fear_match.group(1)} ({fear_match.group(2)})"
                else:
                    market["fear_greed"] = value

            # Sentiment
            elif 'Sentiment' in label:
                # Extract sentiment value (Bullish/Bearish/Neutral)
                sentiment_match = re.search(r'(Bullish|Bearish|Neutral)', value, re.IGNORECASE)
                market["sentiment"] = sentiment_match.group(1) if sentiment_match else value

            # Volatility
            elif 'Volatility' in label:
                vol_match = re.search(r'([0-9.,]+%?)', value)
                if vol_match:
                    market["volatility"] = parse_percent(vol_match.group(1))

            # Green Days
            elif 'Green Days' in label:
                market["green_days"] = value

            # 50-Day SMA
            elif '50-Day SMA' in label:
                sma_match = re.search(r'\$\s*([0-9,]+(?:\.[0-9]+)?)', value)
                if sma_match:
                    market["sma50"] = float(sma_match.group(1).replace(",", ""))

            # 200-Day SMA
            elif '200-Day SMA' in label:
                sma_match = re.search(r'\$\s*([0-9,]+(?:\.[0-9]+)?)', value)
                if sma_match:
                    market["sma200"] = float(sma_match.group(1).replace(",", ""))

            # 14-Day RSI
            elif '14-Day RSI' in label:
                rsi_match = re.search(r'([0-9.]+)', value)
                if rsi_match:
                    market["rsi_14"] = float(rsi_match.group(1))

        return market

    async def get_coin_data(self, coin_id: str) -> dict:
        """Make this async to match usage in your code"""
        html = self.fetch_html(coin_id)
        predictions = self._extract_prediction_tables(html)
        market_data = self._extract_market_data(html)
        return {"coin": coin_id, "predictions": predictions, "market_data": market_data}

    def close(self):
        self.session.close()