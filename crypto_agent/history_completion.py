from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from crypto_agent.market_data import Candle


@dataclass(frozen=True)
class SourceCandles:
    source: str
    candles: list[Candle]


def complete_history(
    sources: list[SourceCandles],
    interval_seconds: int,
    limit: int,
    start: str | None = None,
) -> tuple[list[Candle], dict[str, Any]]:
    merged_by_time: dict[int, Candle] = {}
    candle_source: dict[int, str] = {}
    source_counts = {source.source: len(source.candles) for source in sources}

    for source in sources:
        for candle in source.candles:
            timestamp = _timestamp_seconds(candle.timestamp)
            if start and timestamp < _timestamp_seconds(start):
                continue
            if timestamp not in merged_by_time:
                merged_by_time[timestamp] = candle
                candle_source[timestamp] = source.source

    ordered_times = sorted(merged_by_time)
    if limit > 0:
        ordered_times = ordered_times[-limit:]
    candles = [merged_by_time[timestamp] for timestamp in ordered_times]
    contribution: dict[str, int] = {}
    for timestamp in ordered_times:
        source = candle_source[timestamp]
        contribution[source] = contribution.get(source, 0) + 1

    gaps = _find_gaps(ordered_times, interval_seconds)
    report = {
        "enabled": True,
        "source_count": len(sources),
        "source_counts": source_counts,
        "contribution": contribution,
        "filled_from_secondary": sum(
            count
            for source, count in contribution.items()
            if sources and source != sources[0].source
        ),
        "gap_count": len(gaps),
        "gaps": gaps[:20],
        "first_candle": candles[0].timestamp if candles else None,
        "last_candle": candles[-1].timestamp if candles else None,
    }
    return candles, report


def coverage_needs_more_sources(
    candles: list[Candle],
    interval_seconds: int,
    limit: int,
    start: str | None,
) -> bool:
    if not candles:
        return True
    if len(candles) >= limit and not _find_gaps([_timestamp_seconds(c.timestamp) for c in candles], interval_seconds):
        return False
    if start:
        first_timestamp = _timestamp_seconds(candles[0].timestamp)
        start_timestamp = _timestamp_seconds(start)
        if first_timestamp > start_timestamp + interval_seconds:
            return True
    return bool(_find_gaps([_timestamp_seconds(c.timestamp) for c in candles], interval_seconds))


def _find_gaps(timestamps: list[int], interval_seconds: int) -> list[dict[str, Any]]:
    if interval_seconds <= 0 or len(timestamps) < 2:
        return []
    gaps: list[dict[str, Any]] = []
    tolerance = max(1, int(interval_seconds * 1.5))
    for previous, current in zip(timestamps, timestamps[1:]):
        delta = current - previous
        if delta > tolerance:
            missing = max(0, round(delta / interval_seconds) - 1)
            gaps.append(
                {
                    "from": _iso_from_timestamp(previous),
                    "to": _iso_from_timestamp(current),
                    "missing_estimate": missing,
                }
            )
    return gaps


def _timestamp_seconds(value: str) -> int:
    normalized = value.strip()
    if len(normalized) == 10:
        normalized = f"{normalized}T00:00:00+00:00"
    parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.astimezone(timezone.utc).timestamp())


def _iso_from_timestamp(value: int) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
