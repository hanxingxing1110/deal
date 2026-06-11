from __future__ import annotations

from crypto_agent.market_data import Candle


def sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    multiplier = 2 / (period + 1)
    value = sum(values[:period]) / period
    for price in values[period:]:
        value = (price - value) * multiplier + value
    return value


def rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for previous, current in zip(values[-period - 1 : -1], values[-period:]):
        change = current - previous
        if change >= 0:
            gains.append(change)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(change))
    average_gain = sum(gains) / period
    average_loss = sum(losses) / period
    if average_loss == 0:
        return 100.0
    relative_strength = average_gain / average_loss
    return 100 - (100 / (1 + relative_strength))


def atr(candles: list[Candle], period: int = 14) -> float | None:
    if len(candles) <= period:
        return None
    true_ranges: list[float] = []
    recent = candles[-period:]
    previous_close = candles[-period - 1].close
    for candle in recent:
        true_range = max(
            candle.high - candle.low,
            abs(candle.high - previous_close),
            abs(candle.low - previous_close),
        )
        true_ranges.append(true_range)
        previous_close = candle.close
    return sum(true_ranges) / period


def trend_efficiency(values: list[float], period: int = 20) -> float | None:
    if len(values) <= period:
        return None
    recent = values[-period - 1 :]
    directional_move = abs(recent[-1] - recent[0])
    total_move = sum(
        abs(current - previous)
        for previous, current in zip(recent[:-1], recent[1:])
    )
    if total_move == 0:
        return 0.0
    return directional_move / total_move


def rolling_return_pct(values: list[float], period: int) -> float | None:
    if len(values) <= period:
        return None
    previous = values[-period - 1]
    if previous == 0:
        return None
    return ((values[-1] / previous) - 1) * 100


def latest_indicator_snapshot(candles: list[Candle]) -> dict[str, float]:
    closes = [candle.close for candle in candles]
    volumes = [candle.volume for candle in candles]
    latest_atr = atr(candles) or 0.0
    latest_candle = candles[-1]
    latest_close = closes[-1]
    latest_volume = volumes[-1]
    volume_sma_20 = sma(volumes, 20) or latest_volume
    candle_range = latest_candle.high - latest_candle.low
    return {
        "close": latest_close,
        "sma_20": sma(closes, 20) or latest_close,
        "ema_12": ema(closes, 12) or latest_close,
        "ema_26": ema(closes, 26) or latest_close,
        "rsi_14": rsi(closes, 14) or 50.0,
        "atr_14": latest_atr,
        "atr_pct": (latest_atr / latest_close) * 100 if latest_close else 0.0,
        "trend_efficiency_20": trend_efficiency(closes, 20) or 0.0,
        "return_1d_pct": rolling_return_pct(closes, 96) or 0.0,
        "return_3d_pct": rolling_return_pct(closes, 288) or 0.0,
        "volume_sma_20": volume_sma_20,
        "volume_ratio_20": latest_volume / volume_sma_20 if volume_sma_20 else 0.0,
        "range_atr_ratio": candle_range / latest_atr if latest_atr else 0.0,
    }
