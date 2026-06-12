from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable

from crypto_agent.market_data import Candle


INTERVAL_SECONDS = {
    "1s": 1,
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "6h": 21600,
    "8h": 28800,
    "1d": 86400,
    "3d": 259200,
    "1w": 604800,
    "1M": 2592000,
    "1y": 31536000,
}


def review_candles(candles: list[Candle], interval: str) -> dict[str, Any]:
    expected_seconds = INTERVAL_SECONDS.get(interval)
    parsed_times = [_parse_time(candle.timestamp) for candle in candles]
    warnings: list[str] = []

    duplicate_count = _duplicate_count(candle.timestamp for candle in candles)
    out_of_order_count = sum(
        1
        for previous, current in zip(parsed_times, parsed_times[1:])
        if current <= previous
    )
    ohlc_error_count = sum(1 for candle in candles if not _valid_ohlc(candle))
    non_positive_price_count = sum(
        1
        for candle in candles
        if candle.open <= 0 or candle.high <= 0 or candle.low <= 0 or candle.close <= 0
    )
    negative_volume_count = sum(1 for candle in candles if candle.volume < 0)

    gap_count = 0
    max_gap_seconds = 0
    gap_examples: list[str] = []
    if expected_seconds:
        for previous, current in zip(parsed_times, parsed_times[1:]):
            delta = int((current - previous).total_seconds())
            if delta > expected_seconds:
                gap_count += 1
                max_gap_seconds = max(max_gap_seconds, delta)
                if len(gap_examples) < 5:
                    gap_examples.append(
                        f"{previous.isoformat()} -> {current.isoformat()} ({delta}s)"
                    )

    if duplicate_count:
        warnings.append(f"发现 {duplicate_count} 个重复时间戳。")
    if out_of_order_count:
        warnings.append(f"发现 {out_of_order_count} 处时间顺序异常。")
    if gap_count:
        warnings.append(f"发现 {gap_count} 处时间断档。")
    if ohlc_error_count:
        warnings.append(f"发现 {ohlc_error_count} 根 K 线高低开收关系异常。")
    if non_positive_price_count:
        warnings.append(f"发现 {non_positive_price_count} 根 K 线价格小于或等于 0。")
    if negative_volume_count:
        warnings.append(f"发现 {negative_volume_count} 根 K 线成交量小于 0。")

    status = "ok"
    if warnings:
        status = "warning"
    if ohlc_error_count or non_positive_price_count or out_of_order_count:
        status = "bad"

    return {
        "status": status,
        "warnings": warnings,
        "candle_count": len(candles),
        "first_candle": candles[0].timestamp if candles else None,
        "last_candle": candles[-1].timestamp if candles else None,
        "expected_interval_seconds": expected_seconds,
        "duplicate_timestamps": duplicate_count,
        "out_of_order_count": out_of_order_count,
        "gap_count": gap_count,
        "max_gap_seconds": max_gap_seconds,
        "gap_examples": gap_examples,
        "ohlc_error_count": ohlc_error_count,
        "non_positive_price_count": non_positive_price_count,
        "negative_volume_count": negative_volume_count,
    }


def _parse_time(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _duplicate_count(values: Iterable[str]) -> int:
    counts = Counter(values)
    return sum(count - 1 for count in counts.values() if count > 1)


def _valid_ohlc(candle: Candle) -> bool:
    return (
        candle.high >= candle.open
        and candle.high >= candle.close
        and candle.high >= candle.low
        and candle.low <= candle.open
        and candle.low <= candle.close
        and candle.low <= candle.high
    )
