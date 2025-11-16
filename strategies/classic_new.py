import re
from typing import Dict, Any, Optional
from utils import safe_get_by_substring, parse_money, parse_percent


class ClassicalAnalyst:
    """
    Build classical-school (المدرسة الكلاسيكية) long and short scenarios using:
      - CoinCodex market/predictions (passed externally)
      - TradingView technical indicators (passed externally)
    """

    DEFAULT_VOL_PERCENT = 0.03
    DEFAULT_RISK_PER_TRADE = 0.01

    @staticmethod
    def _calc_targets_from_r(entry: float, stop: float, long: bool = True):
        """Given entry & stop, compute TP1/TP2/TP3 as multiples of risk."""
        risk = abs(entry - stop)
        if risk <= 0:
            return None
        if long:
            return {
                "TP1": entry + 1 * risk,
                "TP2": entry + 2 * risk,
                "TP3": entry + 3 * risk,
            }
        else:
            return {
                "TP1": entry - 1 * risk,
                "TP2": entry - 2 * risk,
                "TP3": entry - 3 * risk,
            }

    async def analyze(
        self,
        coin_id: str,
        coincodex_data: Dict[str, Any],
        tv_pretty: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Analyze based on already-fetched CoinCodex + TradingView data.

        Args:
            coin_id: coin slug (e.g., 'bitcoin')
            coincodex_data: full dict from CoinCodex.get_coin_data()
            tv_pretty: dict from TradingViewAPI.get_technical_analysis_pretty()

        Returns:
            dict with scenarios, trend, and normalized market data
        """
        market = coincodex_data.get("market_data", {}) or {}

        # --- Normalize and extract main indicators ---
        current_price = market.get("current_price") or safe_get_by_substring(
            tv_pretty or {}, ["close", "price"]
        )
        if isinstance(current_price, str):
            current_price = parse_money(current_price)

        sma50 = market.get("sma50") or parse_money(
            safe_get_by_substring(tv_pretty or {}, ["sma50", "sma 50"])
        )
        sma200 = market.get("sma200") or parse_money(
            safe_get_by_substring(tv_pretty or {}, ["sma200", "sma 200"])
        )

        rsi = market.get("rsi_14") or safe_get_by_substring(
            tv_pretty or {}, ["rsi", "relative strength index"]
        )
        if isinstance(rsi, str):
            num = re.search(r"([0-9]+(?:\.[0-9]+)?)", rsi)
            rsi = float(num.group(1)) if num else None

        macd_val = safe_get_by_substring(tv_pretty or {}, ["macd"])
        if isinstance(macd_val, str):
            num = re.search(r"([-+]?[0-9]+(?:\.[0-9]+)?)", macd_val)
            macd_val = float(num.group(1)) if num else None

        volatility = market.get("volatility")
        if volatility is None:
            volatility = (
                parse_percent(safe_get_by_substring(tv_pretty or {}, ["volatility"]))
                or self.DEFAULT_VOL_PERCENT
            )

        # --- Determine trend ---
        trend = "neutral"
        if sma50 and sma200:
            if sma50 > sma200:
                trend = "bullish"
            elif sma50 < sma200:
                trend = "bearish"

        # --- Build scenarios for both spot and futures ---
        scenarios = {"spot": {}, "futures": {}}
        if not current_price:
            return {"coin": coin_id, "trend": "unknown", "scenarios": {}}

        sl_distance = (volatility or self.DEFAULT_VOL_PERCENT) * current_price
        sl_buffer = 0.5 * sl_distance

        # === SPOT LONG ===
        if trend == "bullish":
            momentum_ok = (macd_val and macd_val > 0) or (rsi and 30 < rsi < 70)
            long_entry = current_price if momentum_ok or not sma50 else float(sma50)
            long_stop = max(0.0, long_entry - (sl_distance + sl_buffer))
            long_targets = self._calc_targets_from_r(long_entry, long_stop, True)
            spot_long = {
                "bias": trend,
                "entry": long_entry,
                "stop_loss": long_stop,
                "targets": long_targets,
                "rationale": {
                    "trend": f"SMA50={sma50}, SMA200={sma200}",
                    "momentum": f"MACD={macd_val}, RSI={rsi}",
                    "volatility": f"{(volatility or self.DEFAULT_VOL_PERCENT):.2%}",
                },
            }
        else:
            fallback_entry = sma50 or current_price * 0.99
            long_stop = max(0.0, fallback_entry - (sl_distance + sl_buffer))
            long_targets = self._calc_targets_from_r(fallback_entry, long_stop, True)
            spot_long = {
                "bias": trend,
                "entry": fallback_entry,
                "stop_loss": long_stop,
                "targets": long_targets,
                "rationale": {"note": "Reversal/conservative long"},
            }

        # === SPOT SHORT ===
        if trend == "bearish":
            momentum_ok = (macd_val and macd_val < 0) or (rsi and 30 < rsi < 70)
            short_entry = current_price if momentum_ok or not sma50 else float(sma50)
            short_stop = short_entry + (sl_distance + sl_buffer)
            short_targets = self._calc_targets_from_r(short_entry, short_stop, False)
            spot_short = {
                "bias": trend,
                "entry": short_entry,
                "stop_loss": short_stop,
                "targets": short_targets,
                "rationale": {
                    "trend": f"SMA50={sma50}, SMA200={sma200}",
                    "momentum": f"MACD={macd_val}, RSI={rsi}",
                    "volatility": f"{(volatility or self.DEFAULT_VOL_PERCENT):.2%}",
                },
            }
        else:
            fallback_entry = sma50 or current_price * 1.01
            short_stop = fallback_entry + (sl_distance + sl_buffer)
            short_targets = self._calc_targets_from_r(fallback_entry, short_stop, False)
            spot_short = {
                "bias": trend,
                "entry": fallback_entry,
                "stop_loss": short_stop,
                "targets": short_targets,
                "rationale": {"note": "Reversal/conservative short"},
            }

        # Save spot scenarios
        scenarios["spot"]["long"] = spot_long
        scenarios["spot"]["short"] = spot_short

        # === FUTURES VARIANTS ===
        # Futures trades have tighter stops (0.7x) and larger targets (1.5x)
        def adjust_for_futures(base_scenario: Dict[str, Any], long: bool):
            entry = base_scenario["entry"]
            stop = base_scenario["stop_loss"]
            # Tighter stop = closer to entry
            risk = abs(entry - stop) * 0.7
            stop = entry - risk if long else entry + risk
            targets = self._calc_targets_from_r(entry, stop, long)
            return {
                **base_scenario,
                "stop_loss": stop,
                "targets": {
                    k: (v if not v else v * 1.5)
                    for k, v in targets.items()
                },
                "rationale": {**base_scenario["rationale"], "type": "futures"},
            }

        futures_long = adjust_for_futures(spot_long, long=True)
        futures_short = adjust_for_futures(spot_short, long=False)
        scenarios["futures"]["long"] = futures_long
        scenarios["futures"]["short"] = futures_short

        return {
            "coin": coin_id,
            "trend": trend,
            "market": market,
            "indicators_pretty": tv_pretty,
            "scenarios": scenarios,
        }
