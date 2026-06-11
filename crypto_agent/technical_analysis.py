from __future__ import annotations

from typing import Any

from crypto_agent.indicators import ema, rsi, sma
from crypto_agent.market_data import Candle


FIB_RATIOS = [0.236, 0.382, 0.5, 0.618, 0.786]


def build_technical_snapshot(candles: list[Candle]) -> dict[str, Any]:
    if len(candles) < 30:
        raise ValueError("Need at least 30 candles for technical analysis.")
    if len(candles) > 240:
        candles = candles[-240:]

    closes = [candle.close for candle in candles]
    latest_price = closes[-1]
    swing_points = detect_swing_points(candles)
    structure = analyze_market_structure(swing_points)
    fibonacci = analyze_fibonacci(candles, swing_points)
    bollinger = analyze_bollinger_bands(closes)
    vwap_view = analyze_vwap(candles)
    macd_view = analyze_macd(closes)
    divergence = analyze_divergence(candles, swing_points)
    patterns = detect_candlestick_patterns(candles)
    volume_profile = analyze_volume_profile(candles)

    score = 0.0
    notes: list[str] = []

    if structure["bias"] == "bullish":
        score += 0.14
        notes.append("市场结构偏多。")
    elif structure["bias"] == "bearish":
        score -= 0.14
        notes.append("市场结构偏空。")

    if fibonacci["zone"] == "bullish_retracement":
        score += 0.08
        notes.append("价格位于多头回调常用斐波那契区域。")
    elif fibonacci["zone"] == "bearish_retracement":
        score -= 0.08
        notes.append("价格位于空头反弹常用斐波那契区域。")

    if bollinger["state"] == "upper_breakout":
        score += 0.05
        notes.append("布林带上轨突破，动能偏多。")
    elif bollinger["state"] == "lower_breakout":
        score -= 0.05
        notes.append("布林带下轨突破，动能偏空。")
    elif bollinger["state"] == "squeeze":
        notes.append("布林带收口，等待方向选择。")

    if vwap_view["position"] == "above":
        score += 0.04
        notes.append("价格在 VWAP 上方。")
    elif vwap_view["position"] == "below":
        score -= 0.04
        notes.append("价格在 VWAP 下方。")

    if macd_view["bias"] == "bullish":
        score += 0.06
        notes.append("MACD 偏多。")
    elif macd_view["bias"] == "bearish":
        score -= 0.06
        notes.append("MACD 偏空。")

    if divergence["type"] == "bullish":
        score += 0.08
        notes.append("出现潜在 RSI/MACD 底背离。")
    elif divergence["type"] == "bearish":
        score -= 0.08
        notes.append("出现潜在 RSI/MACD 顶背离。")

    bullish_patterns = sum(1 for item in patterns if item["bias"] == "bullish")
    bearish_patterns = sum(1 for item in patterns if item["bias"] == "bearish")
    score += min(0.06, bullish_patterns * 0.03)
    score -= min(0.06, bearish_patterns * 0.03)
    if bullish_patterns:
        notes.append("近期 K 线形态有多头信号。")
    if bearish_patterns:
        notes.append("近期 K 线形态有空头信号。")

    nearest_poc = volume_profile.get("point_of_control")
    if nearest_poc:
        distance_pct = ((latest_price - nearest_poc["price"]) / latest_price) * 100
        if abs(distance_pct) <= 0.35:
            notes.append("价格贴近成交量密集区，容易震荡或反复争夺。")

    return {
        "score": round(max(-1.0, min(1.0, score)), 3),
        "notes": notes,
        "swing_points": swing_points,
        "market_structure": structure,
        "fibonacci": fibonacci,
        "bollinger": bollinger,
        "vwap": vwap_view,
        "macd": macd_view,
        "divergence": divergence,
        "candlestick_patterns": patterns,
        "volume_profile": volume_profile,
    }


def detect_swing_points(candles: list[Candle], lookback: int = 3) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    if len(candles) < lookback * 2 + 1:
        return points

    for index in range(lookback, len(candles) - lookback):
        window = candles[index - lookback : index + lookback + 1]
        candle = candles[index]
        if candle.high == max(item.high for item in window):
            points.append(
                {
                    "index": index,
                    "time": candle.timestamp,
                    "type": "high",
                    "price": candle.high,
                }
            )
        if candle.low == min(item.low for item in window):
            points.append(
                {
                    "index": index,
                    "time": candle.timestamp,
                    "type": "low",
                    "price": candle.low,
                }
            )
    return points[-20:]


def analyze_market_structure(points: list[dict[str, Any]]) -> dict[str, Any]:
    highs = [point for point in points if point["type"] == "high"][-3:]
    lows = [point for point in points if point["type"] == "low"][-3:]
    labels: list[str] = []

    for previous, current in zip(highs[:-1], highs[1:]):
        labels.append("HH" if current["price"] > previous["price"] else "LH")
    for previous, current in zip(lows[:-1], lows[1:]):
        labels.append("HL" if current["price"] > previous["price"] else "LL")

    bullish = labels.count("HH") + labels.count("HL")
    bearish = labels.count("LH") + labels.count("LL")
    bias = "neutral"
    if bullish >= 3 and bullish > bearish:
        bias = "bullish"
    elif bearish >= 3 and bearish > bullish:
        bias = "bearish"

    return {
        "bias": bias,
        "labels": labels,
        "recent_highs": [_round_point(item) for item in highs],
        "recent_lows": [_round_point(item) for item in lows],
    }


def analyze_fibonacci(
    candles: list[Candle],
    points: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    points = points or detect_swing_points(candles)
    if len(points) >= 2:
        anchor_a, anchor_b = _latest_opposite_swings(points)
    else:
        recent = candles[-120:] if len(candles) > 120 else candles
        low_index, low_price = min(enumerate(recent), key=lambda item: item[1].low)
        high_index, high_price = max(enumerate(recent), key=lambda item: item[1].high)
        offset = len(candles) - len(recent)
        if low_index < high_index:
            anchor_a = {"index": offset + low_index, "type": "low", "price": low_price.low, "time": low_price.timestamp}
            anchor_b = {"index": offset + high_index, "type": "high", "price": high_price.high, "time": high_price.timestamp}
        else:
            anchor_a = {"index": offset + high_index, "type": "high", "price": high_price.high, "time": high_price.timestamp}
            anchor_b = {"index": offset + low_index, "type": "low", "price": low_price.low, "time": low_price.timestamp}

    start_price = float(anchor_a["price"])
    end_price = float(anchor_b["price"])
    direction = "up" if end_price > start_price else "down"
    move = end_price - start_price
    latest = candles[-1].close
    levels = []
    for ratio in FIB_RATIOS:
        price = end_price - move * ratio
        levels.append(
            {
                "ratio": ratio,
                "price": round(price, 4),
                "distance_pct": round(((latest - price) / latest) * 100, 4) if latest else 0.0,
            }
        )

    zone = "outside"
    level_382 = end_price - move * 0.382
    level_618 = end_price - move * 0.618
    low_zone = min(level_382, level_618)
    high_zone = max(level_382, level_618)
    if low_zone <= latest <= high_zone:
        zone = "bullish_retracement" if direction == "up" else "bearish_retracement"

    return {
        "direction": direction,
        "zone": zone,
        "anchor_start": _round_point(anchor_a),
        "anchor_end": _round_point(anchor_b),
        "levels": levels,
    }


def analyze_bollinger_bands(values: list[float], period: int = 20, std_mult: float = 2.0) -> dict[str, Any]:
    if len(values) < period:
        latest = values[-1] if values else 0.0
        return {"state": "unknown", "middle": latest, "upper": latest, "lower": latest, "bandwidth_pct": 0.0}

    recent = values[-period:]
    middle = sum(recent) / period
    variance = sum((value - middle) ** 2 for value in recent) / period
    std = variance ** 0.5
    upper = middle + std_mult * std
    lower = middle - std_mult * std
    latest = values[-1]
    bandwidth_pct = ((upper - lower) / middle) * 100 if middle else 0.0
    state = "inside"
    if bandwidth_pct < 1.2:
        state = "squeeze"
    if latest > upper:
        state = "upper_breakout"
    elif latest < lower:
        state = "lower_breakout"

    return {
        "state": state,
        "middle": round(middle, 4),
        "upper": round(upper, 4),
        "lower": round(lower, 4),
        "bandwidth_pct": round(bandwidth_pct, 4),
    }


def analyze_vwap(candles: list[Candle], period: int = 96) -> dict[str, Any]:
    recent = candles[-period:] if len(candles) > period else candles
    total_volume = sum(max(0.0, candle.volume) for candle in recent)
    latest = candles[-1].close
    if total_volume <= 0:
        return {"value": latest, "position": "unknown", "distance_pct": 0.0}
    value = sum(((c.high + c.low + c.close) / 3) * c.volume for c in recent) / total_volume
    position = "above" if latest > value else "below" if latest < value else "at"
    return {
        "value": round(value, 4),
        "position": position,
        "distance_pct": round(((latest - value) / latest) * 100, 4) if latest else 0.0,
    }


def analyze_macd(values: list[float]) -> dict[str, Any]:
    macd_values = macd_series(values)
    signal_values = ema_series([value for value in macd_values if value is not None], 9)
    macd_line = next((value for value in reversed(macd_values) if value is not None), 0.0)
    signal_line = signal_values[-1] if signal_values else 0.0
    histogram = macd_line - signal_line
    bias = "bullish" if macd_line > signal_line and histogram > 0 else "bearish" if macd_line < signal_line and histogram < 0 else "neutral"
    return {
        "macd": round(macd_line, 6),
        "signal": round(signal_line, 6),
        "histogram": round(histogram, 6),
        "bias": bias,
    }


def analyze_divergence(candles: list[Candle], points: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [candle.close for candle in candles]
    rsi_values = rsi_series(closes, 14)
    macd_values = macd_series(closes)
    lows = [point for point in points if point["type"] == "low"][-2:]
    highs = [point for point in points if point["type"] == "high"][-2:]

    if len(lows) == 2:
        previous, current = lows
        if current["price"] < previous["price"]:
            previous_rsi = _series_at(rsi_values, previous["index"])
            current_rsi = _series_at(rsi_values, current["index"])
            previous_macd = _series_at(macd_values, previous["index"])
            current_macd = _series_at(macd_values, current["index"])
            if (current_rsi is not None and previous_rsi is not None and current_rsi > previous_rsi) or (
                current_macd is not None and previous_macd is not None and current_macd > previous_macd
            ):
                return {
                    "type": "bullish",
                    "basis": "价格新低，但 RSI 或 MACD 没有同步新低。",
                    "points": [_round_point(previous), _round_point(current)],
                }

    if len(highs) == 2:
        previous, current = highs
        if current["price"] > previous["price"]:
            previous_rsi = _series_at(rsi_values, previous["index"])
            current_rsi = _series_at(rsi_values, current["index"])
            previous_macd = _series_at(macd_values, previous["index"])
            current_macd = _series_at(macd_values, current["index"])
            if (current_rsi is not None and previous_rsi is not None and current_rsi < previous_rsi) or (
                current_macd is not None and previous_macd is not None and current_macd < previous_macd
            ):
                return {
                    "type": "bearish",
                    "basis": "价格新高，但 RSI 或 MACD 没有同步新高。",
                    "points": [_round_point(previous), _round_point(current)],
                }

    return {"type": "none", "basis": "未发现明显背离。", "points": []}


def detect_candlestick_patterns(candles: list[Candle]) -> list[dict[str, Any]]:
    if len(candles) < 3:
        return []
    result: list[dict[str, Any]] = []
    recent = candles[-5:]
    for offset, candle in enumerate(recent):
        index = len(candles) - len(recent) + offset
        body = abs(candle.close - candle.open)
        full_range = candle.high - candle.low
        if full_range <= 0:
            continue
        upper = candle.high - max(candle.open, candle.close)
        lower = min(candle.open, candle.close) - candle.low
        if body / full_range <= 0.12:
            result.append(_pattern("doji", "neutral", "十字星", index, candle))
        if lower >= body * 2.2 and upper <= max(body, full_range * 0.18):
            result.append(_pattern("hammer", "bullish", "锤子线", index, candle))
        if upper >= body * 2.2 and lower <= max(body, full_range * 0.18):
            result.append(_pattern("shooting_star", "bearish", "倒锤/射击之星", index, candle))

    previous, current = candles[-2], candles[-1]
    previous_low_body = min(previous.open, previous.close)
    previous_high_body = max(previous.open, previous.close)
    current_low_body = min(current.open, current.close)
    current_high_body = max(current.open, current.close)
    if previous.close < previous.open and current.close > current.open and current_low_body <= previous_low_body and current_high_body >= previous_high_body:
        result.append(_pattern("bullish_engulfing", "bullish", "多头吞没", len(candles) - 1, current))
    if previous.close > previous.open and current.close < current.open and current_low_body <= previous_low_body and current_high_body >= previous_high_body:
        result.append(_pattern("bearish_engulfing", "bearish", "空头吞没", len(candles) - 1, current))

    last3 = candles[-3:]
    if all(item.close > item.open for item in last3):
        result.append(_pattern("three_white_soldiers", "bullish", "三连阳", len(candles) - 1, current))
    if all(item.close < item.open for item in last3):
        result.append(_pattern("three_black_crows", "bearish", "三连阴", len(candles) - 1, current))
    return result[-8:]


def analyze_volume_profile(candles: list[Candle], bins: int = 24) -> dict[str, Any]:
    recent = candles[-240:] if len(candles) > 240 else candles
    low = min(candle.low for candle in recent)
    high = max(candle.high for candle in recent)
    if high <= low:
        return {"bins": [], "point_of_control": None}
    bucket_size = (high - low) / bins
    buckets = [0.0 for _ in range(bins)]
    for candle in recent:
        typical_price = (candle.high + candle.low + candle.close) / 3
        index = int((typical_price - low) / bucket_size)
        index = max(0, min(bins - 1, index))
        buckets[index] += max(0.0, candle.volume)
    max_volume = max(buckets) if buckets else 0.0
    rows = []
    for index, volume in enumerate(buckets):
        price = low + bucket_size * (index + 0.5)
        rows.append(
            {
                "price": round(price, 4),
                "volume": round(volume, 4),
                "relative": round(volume / max_volume, 4) if max_volume else 0.0,
            }
        )
    poc = max(rows, key=lambda item: item["volume"]) if rows else None
    return {
        "bins": rows,
        "point_of_control": poc,
    }


def rsi_series(values: list[float], period: int = 14) -> list[float | None]:
    result: list[float | None] = []
    for index in range(len(values)):
        result.append(rsi(values[: index + 1], period))
    return result


def ema_series(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    result: list[float] = []
    for index in range(len(values)):
        value = ema(values[: index + 1], period)
        if value is not None:
            result.append(value)
    return result


def macd_series(values: list[float]) -> list[float | None]:
    result: list[float | None] = []
    for index in range(len(values)):
        subset = values[: index + 1]
        fast = ema(subset, 12)
        slow = ema(subset, 26)
        result.append((fast - slow) if fast is not None and slow is not None else None)
    return result


def _latest_opposite_swings(points: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    latest = points[-1]
    for point in reversed(points[:-1]):
        if point["type"] != latest["type"]:
            return point, latest
    return points[-2], latest


def _round_point(point: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": point["index"],
        "time": point.get("time"),
        "type": point["type"],
        "price": round(float(point["price"]), 4),
    }


def _series_at(values: list[float | None], index: int) -> float | None:
    if index < 0 or index >= len(values):
        return None
    return values[index]


def _pattern(code: str, bias: str, label: str, index: int, candle: Candle) -> dict[str, Any]:
    return {
        "code": code,
        "bias": bias,
        "label": label,
        "index": index,
        "time": candle.timestamp,
        "price": round(candle.close, 4),
    }
