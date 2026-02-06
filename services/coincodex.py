import re
import time
import random
from typing import Optional
import requests
from bs4 import BeautifulSoup

from utils import parse_percent


class CoinCodex:
    """
    CoinCodex scraper using requests library with improved anti-detection.
    """
    BASE_URL = "https://coincodex.com/crypto/{coin_id}/price-prediction/"

    def __init__(self):
        self.session = requests.Session()
        # Rotate between multiple realistic user agents
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        ]
        self._update_headers()

    def _update_headers(self):
        """Update session headers with realistic browser headers"""
        self.session.headers.update({
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0',
        })

    def fetch_html(self, coin_id: str, max_retries: int = 3) -> str:
        """Fetch HTML with retry logic and random delays"""
        url = self.BASE_URL.format(coin_id=coin_id)

        for attempt in range(max_retries):
            try:
                # Add random delay between requests (1-3 seconds)
                if attempt > 0:
                    time.sleep(random.uniform(2, 5))

                # Rotate user agent on retry
                self._update_headers()

                response = self.session.get(url, timeout=10)
                response.raise_for_status()
                return response.text

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 403:
                    if attempt < max_retries - 1:
                        print(f"403 Forbidden, retrying ({attempt + 1}/{max_retries})...")
                        continue
                    else:
                        raise Exception(f"Failed after {max_retries} attempts: {e}")
                raise
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    print(f"Request failed, retrying ({attempt + 1}/{max_retries})...")
                    continue
                raise

    def _clean_price(self, price_str: str) -> str:
        """Remove $ symbol, unicode spaces, and commas from price strings"""
        cleaned = price_str.replace('\u202f', '').replace(',', '').strip()
        return cleaned

    def _clean_date(self, date_str: str) -> str:
        """Remove commas from dates"""
        return date_str.replace(',', '').strip()

    def _extract_prediction_tables(self, html_text: str) -> dict:
        soup = BeautifulSoup(html_text, 'html.parser')
        result = {"short_term": [], "long_term": []}

        tables = soup.find_all('table', class_='formatted-table full-size-table table-scrollable')

        # Short-term table
        if len(tables) >= 1:
            short_term_table = tables[0]
            tbody = short_term_table.find('tbody')
            if tbody:
                rows = tbody.find_all('tr')
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 3:
                        date = self._clean_date(cols[0].get_text(strip=True))
                        pred_col = cols[1]
                        pred_value_tag = pred_col.find('app-prediction-value')
                        prediction = pred_value_tag.get_text(strip=True) if pred_value_tag else pred_col.get_text(
                            strip=True)
                        prediction = self._clean_price(prediction)
                        change_col = cols[2]
                        change_span = change_col.find('span')
                        change = change_span.get_text(strip=True) if change_span else change_col.get_text(strip=True)

                        result["short_term"].append({
                            "date": date,
                            "prediction": prediction,
                            "change": change
                        })

        # Long-term table
        if len(tables) >= 2:
            long_term_table = tables[1]
            tbody = long_term_table.find('tbody')
            if tbody:
                rows = tbody.find_all('tr')
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 5:
                        month = self._clean_date(cols[0].get_text(strip=True))
                        min_tag = cols[1].find('app-prediction-value')
                        min_price = min_tag.get_text(strip=True) if min_tag else cols[1].get_text(strip=True)
                        min_price = self._clean_price(min_price)
                        avg_tag = cols[2].find('app-prediction-value')
                        avg_price = avg_tag.get_text(strip=True) if avg_tag else cols[2].get_text(strip=True)
                        avg_price = self._clean_price(avg_price)
                        max_tag = cols[3].find('app-prediction-value')
                        max_price = max_tag.get_text(strip=True) if max_tag else cols[3].get_text(strip=True)
                        max_price = self._clean_price(max_price)
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

            if 'Current Price' in label:
                price_match = re.search(r'\$\s*([0-9,]+(?:\.[0-9]+)?)', value)
                if price_match:
                    market["current_price"] = float(price_match.group(1).replace(",", ""))

            elif 'Price Prediction' in label:
                price_match = re.search(r'\$\s*([0-9,]+(?:\.[0-9]+)?)', value)
                if price_match:
                    market["predicted_price"] = float(price_match.group(1).replace(",", ""))
                pct_match = re.search(r'\(([0-9.,]+%?)\)', value)
                if pct_match:
                    market["predicted_change"] = parse_percent(pct_match.group(1))

            elif 'Fear' in label and 'Greed' in label:
                fear_match = re.search(r'(\d+)\s*\(([^)]+)\)', value)
                if fear_match:
                    market["fear_greed"] = f"{fear_match.group(1)} ({fear_match.group(2)})"
                else:
                    market["fear_greed"] = value

            elif 'Sentiment' in label:
                sentiment_match = re.search(r'(Bullish|Bearish|Neutral)', value, re.IGNORECASE)
                market["sentiment"] = sentiment_match.group(1) if sentiment_match else value

            elif 'Volatility' in label:
                vol_match = re.search(r'([0-9.,]+%?)', value)
                if vol_match:
                    market["volatility"] = parse_percent(vol_match.group(1))

            elif 'Green Days' in label:
                market["green_days"] = value

            elif '50-Day SMA' in label:
                sma_match = re.search(r'\$\s*([0-9,]+(?:\.[0-9]+)?)', value)
                if sma_match:
                    market["sma50"] = float(sma_match.group(1).replace(",", ""))

            elif '200-Day SMA' in label:
                sma_match = re.search(r'\$\s*([0-9,]+(?:\.[0-9]+)?)', value)
                if sma_match:
                    market["sma200"] = float(sma_match.group(1).replace(",", ""))

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