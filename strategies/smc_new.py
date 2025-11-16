from dataclasses import dataclass
from typing import Optional, Any, Dict, List, Tuple, Coroutine
import polars as pl


@dataclass
class Decision:
    action: str  # 'buy', 'sell', 'hold'
    reason: str
    confidence: float  # 0..1
    entry: Optional[float]
    stop: Optional[float]
    targets: List[float]
    suggested_risk_pct: float
    details: Dict[str, Any]


class SMCAnalyzer:
    """
    Async, Polars-based Smart Money Concepts analyzer.
    - Accepts an OHLC polars.DataFrame (columns: open, high, low, close, optionally timestamp)
    - Works with OHLC-only indicators (no volume). Detects swings, FVG, simple BOS/CHOCH, liquidity clusters,
      and returns a Decision dataclass.
    """

    def __init__(self, swing_length: int = 10, fvg_max_dist_pct: float = 0.03, liq_range_pct: float = 0.01):
        self.swing_length = int(swing_length)
        self.fvg_max_dist_pct = float(fvg_max_dist_pct)
        self.liq_range_pct = float(liq_range_pct)

    # ----------------------------
    # Helpers: convert polars cols to lists (safe for small N like 180)
    # ----------------------------
    @staticmethod
    def _col_list(df: pl.DataFrame, col: str) -> List[float]:
        return df.select(col).to_series().to_list()

    # ----------------------------
    # Swing detection (async)
    # ----------------------------
    async def detect_swings(self, ohlc: pl.DataFrame) -> pl.DataFrame:
        """
        Mark swing highs/lows. Requirement: full look-ahead of swing_length on both sides.
        Returns a polars.DataFrame with columns: idx:int, type:str ('high'/'low'), price:float
        """
        highs = self._col_list(ohlc, "high")
        lows = self._col_list(ohlc, "low")
        n = len(highs)
        swings: List[dict] = []
        L = self.swing_length
        for i in range(n):
            if (i - L) < 0 or (i + L) >= n:
                continue
            left = i - L
            right = i + L + 1
            window_high = max(highs[left:right])
            window_low = min(lows[left:right])
            if highs[i] == window_high:
                swings.append({"idx": i, "type": "high", "price": float(highs[i])})
            if lows[i] == window_low:
                swings.append({"idx": i, "type": "low", "price": float(lows[i])})
        if not swings:
            return pl.DataFrame([])

        return pl.DataFrame(swings).sort("idx")

    # ----------------------------
    # FVG detection (async)
    # ----------------------------
    async def detect_fvg(self, ohlc: pl.DataFrame) -> pl.DataFrame:
        """
        3-candle FVG detection:
        - Bull gap: candle1.high < candle3.low
        - Bear gap: candle1.low > candle3.high
        Returns columns: start_idx, end_idx, type, low, high
        """
        highs = self._col_list(ohlc, "high")
        lows = self._col_list(ohlc, "low")
        N = len(highs)
        gaps: List[dict] = []
        for i in range(N - 2):
            c1h = highs[i]
            c1l = lows[i]
            c3h = highs[i + 2]
            c3l = lows[i + 2]
            if c1h < c3l:
                gaps.append({"start_idx": i, "end_idx": i + 2, "type": "bull", "low": float(c1h), "high": float(c3l)})
            if c1l > c3h:
                gaps.append({"start_idx": i, "end_idx": i + 2, "type": "bear", "low": float(c3h), "high": float(c1l)})
        if not gaps:
            return pl.DataFrame([])
        return pl.DataFrame(gaps).sort("start_idx")

    # ----------------------------
    # Simple BOS/CHOCH detection (async)
    # ----------------------------
    async def detect_bos_choch(self, ohlc: pl.DataFrame, swings_df: pl.DataFrame) -> pl.DataFrame:
        """
        Very lightweight detection:
        - BOS_high: a close breaks the most recent swing high by a small margin
        - BOS_low: a close breaks the most recent swing low by a small margin
        - CHOCH detection: naive check of last few swings trend (up/up -> bull, down/down -> bear)
        Returns columns: idx, type, price, ref_idx (optional)
        """
        closes = self._col_list(ohlc, "close")
        n = len(closes)
        events: List[dict] = []

        if swings_df.is_empty():
            # No swings -> no BOS/CHOCH
            return pl.DataFrame([])

        # build mapping of swing idx -> price by type
        highs = swings_df.filter(pl.col("type") == "high").to_dicts()
        lows = swings_df.filter(pl.col("type") == "low").to_dicts()
        # find latest high/low by idx
        latest_high = max((s for s in highs), key=lambda x: x["idx"]) if highs else None
        latest_low = max((s for s in lows), key=lambda x: x["idx"]) if lows else None

        # check last 30 candles for breaks
        recent_window = min(30, n)
        start = max(0, n - recent_window)
        for i in range(start, n):
            close = closes[i]
            if latest_high and i > latest_high["idx"] and close > latest_high["price"] * 1.001:
                events.append({"idx": i, "type": "BOS_high", "price": float(close), "ref_idx": int(latest_high["idx"])})
            if latest_low and i > latest_low["idx"] and close < latest_low["price"] * 0.999:
                events.append({"idx": i, "type": "BOS_low", "price": float(close), "ref_idx": int(latest_low["idx"])})

        # CHOCH: analyze last few swings for trend direction
        seq = swings_df.sort("idx")
        seq_short = seq.tail(6)
        seq_dicts = seq_short.to_dicts()
        highs_vals = [d["price"] for d in seq_dicts if d["type"] == "high"]
        lows_vals = [d["price"] for d in seq_dicts if d["type"] == "low"]

        def simple_trend(vals: List[float]) -> Optional[str]:
            if len(vals) < 2:
                return None
            return "up" if vals[-1] > vals[-2] else "down"

        htrend = simple_trend(highs_vals)
        ltrend = simple_trend(lows_vals)
        if htrend and ltrend and htrend == "down" and ltrend == "down":
            events.append({"idx": n - 1, "type": "CHOCH_bear", "price": float(closes[-1])})
        if htrend and ltrend and htrend == "up" and ltrend == "up":
            events.append({"idx": n - 1, "type": "CHOCH_bull", "price": float(closes[-1])})

        if not events:
            return pl.DataFrame([])

        return pl.DataFrame(events).sort("idx")

    # ----------------------------
    # Liquidity clusters from swings (async)
    # ----------------------------
    async def detect_liquidity_clusters(self, swings_df: pl.DataFrame, range_percent: Optional[float] = None) -> pl.DataFrame:
        """
        Cluster swing prices that are within range_percent of each other.
        Returns mean_price, size, members_idx (list), types (list)
        """
        if swings_df.is_empty():
            return pl.DataFrame([])

        rp = self.liq_range_pct if range_percent is None else float(range_percent)
        swings = swings_df.to_dicts()
        prices = [s["price"] for s in swings]
        used = set()
        clusters: List[dict] = []

        for i, p in enumerate(prices):
            if i in used:
                continue
            members = [i]
            used.add(i)
            for j in range(i + 1, len(prices)):
                if j in used:
                    continue
                if abs(prices[j] - p) / p <= rp:
                    members.append(j)
                    used.add(j)
            member_rows = [swings[m] for m in members]
            clusters.append({
                "mean_price": float(sum(m["price"] for m in member_rows) / len(member_rows)),
                "size": len(member_rows),
                "members_idx": [int(m["idx"]) for m in member_rows],
                "types": [m["type"] for m in member_rows],
            })

        # sort by size desc
        clusters.sort(key=lambda x: x["size"], reverse=True)
        return pl.DataFrame(clusters)

    # ----------------------------
    # Nearest helpers (sync helpers inside async method)
    # ----------------------------
    @staticmethod
    def _nearest_fvg(price: float, fvg_df: pl.DataFrame, max_dist_pct: float) -> Tuple[Optional[dict], Optional[float]]:
        if fvg_df.is_empty():
            return None, None
        centers = [(r["low"] + r["high"]) / 2.0 for r in fvg_df.to_dicts()]
        dists = [abs(c - price) / c for c in centers]
        min_i = int(min(range(len(dists)), key=lambda k: dists[k]))
        if dists[min_i] <= max_dist_pct:
            rec = fvg_df.to_dicts()[min_i]
            return rec, float(dists[min_i])
        return None, None

    @staticmethod
    def _nearest_liquidity(price: float, lc_df: pl.DataFrame, max_dist_pct: float) -> Tuple[Optional[dict], Optional[float]]:
        if lc_df.is_empty():
            return None, None
        recs = lc_df.to_dicts()
        dists = [abs(r["mean_price"] - price) / r["mean_price"] for r in recs]
        min_i = int(min(range(len(dists)), key=lambda k: dists[k]))
        if dists[min_i] <= max_dist_pct:
            return recs[min_i], float(dists[min_i])
        return None, None

    # ----------------------------
    # Main analyze method (async)
    # ----------------------------
    async def analyze_trade(
        self,
        ohlc: pl.DataFrame,
        swings: Optional[pl.DataFrame] = None,
        fvg: Optional[pl.DataFrame] = None,
        bos_choch: Optional[pl.DataFrame] = None,
        liquidity_clusters: Optional[pl.DataFrame] = None,
    ) -> Decision:
        """
        Analyze the provided polars DataFrames and return a Decision plus computed frames.
        If indicator frames are None, they will be computed from ohlc.
        """
        # compute if needed
        if swings is None:
            swings = await self.detect_swings(ohlc)
        if fvg is None:
            fvg = await self.detect_fvg(ohlc)
        if bos_choch is None:
            bos_choch = await self.detect_bos_choch(ohlc, swings)
        if liquidity_clusters is None:
            liquidity_clusters = await self.detect_liquidity_clusters(swings, range_percent=self.liq_range_pct)

        n = ohlc.height
        last_close = float(ohlc.select("close").to_series()[-1])

        # determine bias from last swings
        bias = "neutral"
        if not swings.is_empty() and swings.height >= 4:
            seq = swings.sort("idx")
            highs = [r["price"] for r in seq.filter(pl.col("type") == "high").to_dicts()[-3:]]
            lows = [r["price"] for r in seq.filter(pl.col("type") == "low").to_dicts()[-3:]]
            if len(highs) >= 2 and len(lows) >= 2:
                if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
                    bias = "bull"
                if highs[-1] < highs[-2] and lows[-1] < lows[-2]:
                    bias = "bear"

        # recent events
        recent_threshold = max(0, n - 30)
        recent_events = [] if bos_choch.is_empty() else [r["type"] for r in bos_choch.to_dicts() if r["idx"] >= recent_threshold]
        has_bos_bull = "BOS_high" in recent_events
        has_bos_bear = "BOS_low" in recent_events
        has_choch_bull = "CHOCH_bull" in recent_events
        has_choch_bear = "CHOCH_bear" in recent_events

        # nearest fvg / liquidity
        nearest_gap, gap_dist = self._nearest_fvg(last_close, fvg, self.fvg_max_dist_pct)
        nearest_liq, liq_dist = self._nearest_liquidity(last_close, liquidity_clusters, self.liq_range_pct * 3)

        # scoring
        score = 0.5
        reasons: List[str] = []

        if bias == "bull":
            score += 0.15
            reasons.append("structure_bullish")
        elif bias == "bear":
            score -= 0.15
            reasons.append("structure_bearish")
        else:
            reasons.append("structure_neutral")

        if has_choch_bull:
            score += 0.25
            reasons.append("recent_CHOCH_bull")
        if has_choch_bear:
            score -= 0.25
            reasons.append("recent_CHOCH_bear")
        if has_bos_bull:
            score += 0.12
            reasons.append("recent_BOS_bull")
        if has_bos_bear:
            score -= 0.12
            reasons.append("recent_BOS_bear")

        if nearest_gap is not None:
            gtype = nearest_gap["type"]
            if (gtype == "bull" and bias == "bull") or (gtype == "bear" and bias == "bear") or bias == "neutral":
                score += max(0.08, 0.12 - (gap_dist or 0.0))
                reasons.append(f"near_fvg_{gtype}")
            else:
                score -= 0.05
                reasons.append(f"near_fvg_misaligned_{gtype}")

        if nearest_liq is not None:
            types = nearest_liq.get("types", [])
            high_count = types.count("high")
            low_count = types.count("low")
            if high_count > low_count:
                if bias == "bull":
                    score -= 0.08
                    reasons.append("overhead_liquidity_nearby")
                else:
                    score += 0.03
                    reasons.append("overhead_liquidity_target")
            elif low_count > high_count:
                if bias == "bear":
                    score += 0.03
                    reasons.append("support_liquidity_nearby_bear")
                else:
                    score += 0.05
                    reasons.append("support_liquidity_nearby")

        # proximity to last swing
        if not swings.is_empty():
            last_swing = swings.sort("idx").to_dicts()[-1]
            dist_swing = abs(last_close - last_swing["price"]) / last_swing["price"]
            if dist_swing <= 0.015:
                reasons.append("price_near_last_swing")
                if (last_swing["type"] == "low" and bias == "bull") or (last_swing["type"] == "high" and bias == "bear"):
                    score += 0.03
                else:
                    score -= 0.03

        # normalize
        confidence = max(0.0, min(1.0, score))

        # thresholds -> action
        if confidence >= 0.62:
            action = "buy" if (bias in ("bull", "neutral") or has_choch_bull) else "sell"
        elif confidence <= 0.38:
            action = "sell" if (bias in ("bear", "neutral") or has_choch_bear) else "buy"
        else:
            action = "hold"

        # entry/stop/targets generation
        entry = None
        stop = None
        targets: List[float] = []

        if action == "buy":
            if nearest_gap is not None and nearest_gap["type"] == "bull":
                entry = max(nearest_gap["low"], last_close)
                stop = nearest_gap["low"] - (abs(nearest_gap["high"] - nearest_gap["low"]) * 0.6)
                targets = [entry + (entry - stop) * 1.5, entry + (entry - stop) * 3.0]
            else:
                lows = swings.filter(pl.col("type") == "low")
                if not lows.is_empty():
                    last_low = lows.sort("idx").to_dicts()[-1]["price"]
                    entry = max(last_low, last_close)
                    stop = last_low - (abs(entry - last_low) * 0.6 + 1e-9)
                    targets = [entry + (entry - stop) * 1.2, entry + (entry - stop) * 2.0]
                else:
                    entry = last_close
                    stop = last_close * 0.98
                    targets = [last_close * 1.02, last_close * 1.04]

        elif action == "sell":
            if nearest_gap is not None and nearest_gap["type"] == "bear":
                entry = min(nearest_gap["high"], last_close)
                stop = nearest_gap["high"] + (abs(nearest_gap["high"] - nearest_gap["low"]) * 0.6)
                targets = [entry - (stop - entry) * 1.5, entry - (stop - entry) * 3.0]
            else:
                highs = swings.filter(pl.col("type") == "high")
                if not highs.is_empty():
                    last_high = highs.sort("idx").to_dicts()[-1]["price"]
                    entry = min(last_high, last_close)
                    stop = last_high + (abs(entry - last_high) * 0.6 + 1e-9)
                    targets = [entry - (stop - entry) * 1.2, entry - (stop - entry) * 2.0]
                else:
                    entry = last_close
                    stop = last_close * 1.02
                    targets = [last_close * 0.98, last_close * 0.96]

        suggested_risk = max(0.25, 1.5 * confidence)

        details = {
            "bias": bias,
            "recent_events": recent_events,
            "nearest_fvg": nearest_gap,
            "nearest_fvg_dist": gap_dist,
            "nearest_liquidity": nearest_liq,
            "nearest_liquidity_dist": liq_dist,
            "last_close": last_close,
            "score_raw": score,
            "swings_count": swings.height if not swings.is_empty() else 0,
            "fvg_count": fvg.height if not fvg.is_empty() else 0,
            "liquidity_clusters_count": liquidity_clusters.height if not liquidity_clusters.is_empty() else 0,
        }

        decision = Decision(
            action=action,
            reason="; ".join(reasons),
            confidence=confidence,
            entry=round(entry, 3),
            stop=round(stop, 3),
            targets=targets,
            suggested_risk_pct=suggested_risk,
            details=details,
        )

        # computed = {
        #     "swings": swings,
        #     "fvg": fvg,
        #     "bos_choch": bos_choch,
        #     "liquidity_clusters": liquidity_clusters,
        # }

        return decision
