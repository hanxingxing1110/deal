from __future__ import annotations

import csv
import json
import math
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Candle:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class OrderBookLevel:
    price: float
    quantity: float
    notional: float


@dataclass(frozen=True)
class OrderBookSnapshot:
    source: str
    symbol: str
    timestamp: str
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]


@dataclass(frozen=True)
class FundingRateSnapshot:
    source: str
    symbol: str
    timestamp: str
    funding_rate: float | None
    next_funding_time: str | None = None
    mark_price: float | None = None
    index_price: float | None = None


@dataclass(frozen=True)
class NewsItem:
    source: str
    title: str
    link: str
    published_at: str | None = None
    summary: str | None = None


def load_csv(path: str | Path) -> list[Candle]:
    csv_path = Path(path)
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"{csv_path} has no CSV header row.")
        field_map = _build_field_map(reader.fieldnames)
        candles = [
            Candle(
                timestamp=_normalize_timestamp(row[field_map["timestamp"]]),
                open=float(row[field_map["open"]]),
                high=float(row[field_map["high"]]),
                low=float(row[field_map["low"]]),
                close=float(row[field_map["close"]]),
                volume=float(row[field_map["volume"]]),
            )
            for row in reader
        ]
    if len(candles) < 30:
        raise ValueError("Need at least 30 candles for the MVP indicators.")
    return candles


def _build_field_map(fieldnames: list[str]) -> dict[str, str]:
    normalized = {_normalize_column_name(name): name for name in fieldnames}
    candidates = {
        "timestamp": [
            "timestamp",
            "time",
            "datetime",
            "date",
            "open_time",
            "opentime",
            "open_time_utc",
            "start",
        ],
        "open": ["open", "o"],
        "high": ["high", "h"],
        "low": ["low", "l"],
        "close": ["close", "c", "last"],
        "volume": ["volume", "vol", "v", "base_volume", "baseassetvolume"],
    }

    result: dict[str, str] = {}
    missing: list[str] = []
    for required, options in candidates.items():
        for option in options:
            if option in normalized:
                result[required] = normalized[option]
                break
        else:
            missing.append(required)

    if missing:
        raise ValueError(
            "CSV missing required columns: "
            + ", ".join(missing)
            + ". Expected timestamp/open/high/low/close/volume or common aliases."
        )
    return result


def _normalize_column_name(value: str) -> str:
    return (
        value.strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
        .replace(".", "")
    )


def _normalize_timestamp(value: str) -> str:
    raw = value.strip()
    if raw.isdigit():
        number = int(raw)
        if number > 10_000_000_000:
            number = number / 1000
        return datetime.fromtimestamp(number, tz=timezone.utc).isoformat()
    return raw


def fetch_binance_klines(symbol: str, interval: str, limit: int) -> list[Candle]:
    errors: list[str] = []
    for base_url in ("https://api.binance.com", "https://data-api.binance.vision"):
        try:
            return _fetch_binance_klines_from_base(base_url, symbol, interval, limit)
        except Exception as exc:
            errors.append(f"{base_url}: {exc}")
    raise RuntimeError("; ".join(errors))


def _fetch_binance_klines_from_base(
    base_url: str,
    symbol: str,
    interval: str,
    limit: int,
) -> list[Candle]:
    rows: list[list] = []
    end_time: int | None = None

    while len(rows) < limit:
        page_limit = min(1000, limit - len(rows))
        page = _request_binance_klines_page(
            base_url=base_url,
            symbol=symbol,
            interval=interval,
            limit=page_limit,
            end_time=end_time,
        )
        if not page:
            break
        rows = page + rows
        oldest_open_time = int(page[0][0])
        if end_time == oldest_open_time - 1:
            break
        end_time = oldest_open_time - 1

    deduped: dict[int, list] = {}
    for row in rows:
        deduped[int(row[0])] = row
    ordered_rows = [deduped[key] for key in sorted(deduped)][-limit:]
    candles = _binance_rows_to_candles(ordered_rows)
    if len(candles) < 30:
        raise ValueError("Binance returned too few candles.")
    return candles


def _request_binance_klines_page(
    base_url: str,
    symbol: str,
    interval: str,
    limit: int,
    end_time: int | None = None,
) -> list:
    query_params: dict[str, object] = {
        "symbol": symbol.upper(),
        "interval": interval,
        "limit": limit,
    }
    if end_time is not None:
        query_params["endTime"] = end_time
    query = urllib.parse.urlencode(
        query_params
    )
    url = f"{base_url}/api/v3/klines?{query}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "crypto-agent-mvp/0.1"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _binance_rows_to_candles(rows: list[list]) -> list[Candle]:
    candles: list[Candle] = []
    for item in rows:
        opened_at = datetime.fromtimestamp(item[0] / 1000, tz=timezone.utc)
        candles.append(
            Candle(
                timestamp=opened_at.isoformat(),
                open=float(item[1]),
                high=float(item[2]),
                low=float(item[3]),
                close=float(item[4]),
                volume=float(item[5]),
            )
        )
    return candles


def fetch_okx_candles(symbol: str, interval: str, limit: int) -> list[Candle]:
    inst_id = okx_inst_id(symbol)
    bar = "15m" if interval == "15m" else "1H" if interval == "1h" else interval
    rows: list[list[Any]] = []
    after: str | None = None

    while len(rows) < limit:
        page_limit = min(300, limit - len(rows))
        params: dict[str, object] = {"instId": inst_id, "bar": bar, "limit": page_limit}
        if after:
            params["after"] = after
        payload = _request_okx_page(
            f"/api/v5/market/{'history-candles' if after else 'candles'}",
            params,
        )
        page_rows = payload.get("data") or []
        if not page_rows:
            break
        rows.extend(page_rows)
        oldest_timestamp = str(page_rows[-1][0])
        if oldest_timestamp == after:
            break
        after = oldest_timestamp

    deduped: dict[str, list[Any]] = {}
    for row in rows:
        deduped[str(row[0])] = row

    candles: list[Candle] = []
    for row in sorted(deduped.values(), key=lambda item: int(item[0])):
        candles.append(
            Candle(
                timestamp=datetime.fromtimestamp(
                    int(row[0]) / 1000,
                    tz=timezone.utc,
                ).isoformat(),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
        )
    if len(candles) < 30:
        raise ValueError("OKX returned too few candles.")
    return candles[-limit:]


def fetch_coinbase_candles(product_id: str, interval: str, limit: int) -> list[Candle]:
    granularity = _coinbase_granularity(interval)
    end = datetime.now(timezone.utc).replace(microsecond=0)
    start = end - timedelta(seconds=granularity * min(limit, 300))
    query = urllib.parse.urlencode(
        {
            "granularity": granularity,
            "start": start.isoformat().replace("+00:00", "Z"),
            "end": end.isoformat().replace("+00:00", "Z"),
        }
    )
    product = urllib.parse.quote(product_id.upper(), safe="")
    url = f"https://api.exchange.coinbase.com/products/{product}/candles?{query}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "crypto-agent-mvp/0.1"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))

    candles: list[Candle] = []
    for item in sorted(payload, key=lambda row: row[0]):
        opened_at = datetime.fromtimestamp(item[0], tz=timezone.utc)
        candles.append(
            Candle(
                timestamp=opened_at.isoformat(),
                low=float(item[1]),
                high=float(item[2]),
                open=float(item[3]),
                close=float(item[4]),
                volume=float(item[5]),
            )
        )
    if len(candles) < 30:
        raise ValueError("Coinbase returned too few candles.")
    return candles[-limit:]


def fetch_binance_order_book(symbol: str, limit: int = 100) -> OrderBookSnapshot:
    params = {"symbol": symbol.upper(), "limit": max(5, min(5000, limit))}
    errors: list[str] = []
    for base_url in ("https://api.binance.com", "https://data-api.binance.vision"):
        url = f"{base_url}/api/v3/depth?{urllib.parse.urlencode(params)}"
        try:
            payload = _request_json(url)
            return _binance_order_book_payload(symbol, payload)
        except Exception as exc:
            errors.append(f"{base_url}: {exc}")
    raise RuntimeError("; ".join(errors))


def fetch_okx_order_book(symbol: str, limit: int = 100) -> OrderBookSnapshot:
    params = {"instId": okx_inst_id(symbol), "sz": max(1, min(400, limit))}
    payload = _request_okx_page("/api/v5/market/books", params)
    rows = payload.get("data") or []
    if not rows:
        raise ValueError("OKX returned no order book data.")
    item = rows[0]
    timestamp = datetime.fromtimestamp(int(item["ts"]) / 1000, tz=timezone.utc)
    return OrderBookSnapshot(
        source="okx",
        symbol=symbol.upper(),
        timestamp=timestamp.isoformat(),
        bids=_levels_from_pairs(item.get("bids") or []),
        asks=_levels_from_pairs(item.get("asks") or []),
    )


def fetch_order_book(
    symbol: str,
    limit: int = 100,
    source: str = "auto",
) -> tuple[OrderBookSnapshot, dict[str, str]]:
    errors: dict[str, str] = {}
    for candidate in _source_order(source, ("okx", "binance")):
        try:
            if candidate == "okx":
                return fetch_okx_order_book(symbol, limit), errors
            if candidate == "binance":
                return fetch_binance_order_book(symbol, limit), errors
        except Exception as exc:
            errors[candidate] = _format_error(exc)
    raise RuntimeError("; ".join(f"{key}: {value}" for key, value in errors.items()))


def fetch_binance_funding_rate(symbol: str) -> FundingRateSnapshot:
    premium_url = (
        "https://fapi.binance.com/fapi/v1/premiumIndex?"
        + urllib.parse.urlencode({"symbol": symbol.upper()})
    )
    premium = _request_json(premium_url)
    timestamp = datetime.now(timezone.utc).isoformat()
    if premium.get("time"):
        timestamp = datetime.fromtimestamp(
            int(premium["time"]) / 1000,
            tz=timezone.utc,
        ).isoformat()
    next_funding_time = None
    if premium.get("nextFundingTime"):
        next_funding_time = datetime.fromtimestamp(
            int(premium["nextFundingTime"]) / 1000,
            tz=timezone.utc,
        ).isoformat()
    return FundingRateSnapshot(
        source="binance_futures",
        symbol=symbol.upper(),
        timestamp=timestamp,
        funding_rate=_safe_float(premium.get("lastFundingRate")),
        next_funding_time=next_funding_time,
        mark_price=_safe_float(premium.get("markPrice")),
        index_price=_safe_float(premium.get("indexPrice")),
    )


def fetch_okx_funding_rate(symbol: str) -> FundingRateSnapshot:
    params = {"instId": okx_swap_inst_id(symbol)}
    payload = _request_okx_page("/api/v5/public/funding-rate", params)
    rows = payload.get("data") or []
    if not rows:
        raise ValueError("OKX returned no funding data.")
    item = rows[0]
    timestamp = datetime.fromtimestamp(
        int(item.get("fundingTime") or item.get("ts") or 0) / 1000,
        tz=timezone.utc,
    ).isoformat()
    next_funding_time = None
    if item.get("nextFundingTime"):
        next_funding_time = datetime.fromtimestamp(
            int(item["nextFundingTime"]) / 1000,
            tz=timezone.utc,
        ).isoformat()
    return FundingRateSnapshot(
        source="okx_swap",
        symbol=symbol.upper(),
        timestamp=timestamp,
        funding_rate=_safe_float(item.get("fundingRate")),
        next_funding_time=next_funding_time,
    )


def fetch_funding_rate(
    symbol: str,
    source: str = "auto",
) -> tuple[FundingRateSnapshot, dict[str, str]]:
    errors: dict[str, str] = {}
    for candidate in _source_order(source, ("okx", "binance")):
        try:
            if candidate == "okx":
                return fetch_okx_funding_rate(symbol), errors
            if candidate == "binance":
                return fetch_binance_funding_rate(symbol), errors
        except Exception as exc:
            errors[candidate] = _format_error(exc)
    raise RuntimeError("; ".join(f"{key}: {value}" for key, value in errors.items()))


def fetch_crypto_news(limit: int = 8) -> tuple[list[NewsItem], dict[str, str]]:
    feeds = {
        "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "Cointelegraph": "https://cointelegraph.com/rss",
    }
    errors: dict[str, str] = {}
    items: list[NewsItem] = []
    for source, url in feeds.items():
        try:
            payload = _request_text(url, timeout=10)
            items.extend(_parse_rss_items(source, payload))
        except Exception as exc:
            errors[source] = _format_error(exc)

    deduped: dict[str, NewsItem] = {}
    for item in items:
        key = item.link or item.title
        if key and key not in deduped:
            deduped[key] = item
    return list(deduped.values())[:limit], errors


def okx_inst_id(symbol: str) -> str:
    normalized = symbol.upper()
    if "-" in normalized:
        return normalized
    for quote in ("USDT", "USDC", "USD"):
        if normalized.endswith(quote):
            return f"{normalized[: -len(quote)]}-{quote}"
    return normalized


def okx_swap_inst_id(symbol: str) -> str:
    inst_id = okx_inst_id(symbol)
    if inst_id.endswith("-SWAP"):
        return inst_id
    if inst_id.endswith("-USDT") or inst_id.endswith("-USDC") or inst_id.endswith("-USD"):
        return f"{inst_id}-SWAP"
    return inst_id


def _coinbase_granularity(interval: str) -> int:
    mapping = {
        "1m": 60,
        "5m": 300,
        "15m": 900,
        "1h": 3600,
        "6h": 21600,
        "1d": 86400,
    }
    if interval not in mapping:
        raise ValueError(
            "Coinbase source supports intervals: 1m, 5m, 15m, 1h, 6h, 1d."
        )
    return mapping[interval]


def _source_order(source: str, supported: tuple[str, ...]) -> list[str]:
    normalized = source.lower().strip()
    if normalized in {"", "auto"}:
        return list(supported)
    if normalized not in supported:
        raise ValueError(f"Unsupported source '{source}'. Use auto or {', '.join(supported)}.")
    return [normalized, *[candidate for candidate in supported if candidate != normalized]]


def _request_json(url: str, timeout: int = 15) -> Any:
    return json.loads(_request_text(url, timeout=timeout))


def _request_text(url: str, timeout: int = 15) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "crypto-agent-mvp/0.1"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def _request_okx_page(path: str, params: dict[str, object]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    errors: list[str] = []
    for domain in ("https://www.okx.com", "https://us.okx.com"):
        url = f"{domain}{path}?{query}"
        try:
            return _request_json(url)
        except Exception as exc:
            errors.append(f"{domain}: {_format_error(exc)}")
    raise RuntimeError("; ".join(errors))


def _binance_order_book_payload(symbol: str, payload: dict[str, Any]) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        source="binance_spot",
        symbol=symbol.upper(),
        timestamp=datetime.now(timezone.utc).isoformat(),
        bids=_levels_from_pairs(payload.get("bids") or []),
        asks=_levels_from_pairs(payload.get("asks") or []),
    )


def _levels_from_pairs(rows: list[list[Any]]) -> list[OrderBookLevel]:
    levels: list[OrderBookLevel] = []
    for row in rows:
        price = float(row[0])
        quantity = float(row[1])
        levels.append(
            OrderBookLevel(
                price=price,
                quantity=quantity,
                notional=price * quantity,
            )
        )
    return levels


def _parse_rss_items(source: str, payload: str) -> list[NewsItem]:
    import xml.etree.ElementTree as ET

    root = ET.fromstring(payload)
    result: list[NewsItem] = []
    for item in root.findall(".//item"):
        title = _xml_text(item, "title")
        link = _xml_text(item, "link")
        published_at = _xml_text(item, "pubDate") or None
        summary = _xml_text(item, "description") or None
        if title:
            result.append(
                NewsItem(
                    source=source,
                    title=title,
                    link=link,
                    published_at=published_at,
                    summary=summary,
                )
            )
    return result


def _xml_text(item: Any, tag: str) -> str:
    element = item.find(tag)
    if element is None or element.text is None:
        return ""
    return element.text.strip()


def _safe_float(value: object) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_error(exc: BaseException) -> str:
    message = str(exc).strip()
    if message:
        return message
    return exc.__class__.__name__


def generate_sample_candles(count: int = 120) -> list[Candle]:
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    price = 67_500.0
    candles: list[Candle] = []
    for index in range(count):
        wave = math.sin(index / 6) * 220
        drift = index * 18
        shock = math.sin(index / 2.7) * 90
        close = price + drift + wave + shock
        open_price = close - math.sin(index / 3) * 80
        high = max(open_price, close) + 180 + abs(math.sin(index)) * 70
        low = min(open_price, close) - 160 - abs(math.cos(index)) * 60
        volume = 1200 + 120 * math.sin(index / 4) + index * 3
        candles.append(
            Candle(
                timestamp=(start + timedelta(hours=index)).isoformat(),
                open=round(open_price, 2),
                high=round(high, 2),
                low=round(low, 2),
                close=round(close, 2),
                volume=round(volume, 2),
            )
        )
    return candles


def generate_research_sample_candles(count: int = 1440) -> list[Candle]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    price = 45_000.0
    candles: list[Candle] = []
    regimes = [0.00055, -0.00035, 0.0008, -0.00065, 0.00015, 0.0]

    for index in range(count):
        regime = regimes[(index // 240) % len(regimes)]
        cycle = math.sin(index / 18) * 0.0018
        faster_cycle = math.sin(index / 5.5) * 0.0009
        volatility = 0.006 + 0.0025 * abs(math.sin(index / 37))
        change = regime + cycle + faster_cycle

        open_price = price
        close = max(1_000.0, open_price * (1 + change))
        range_size = open_price * volatility
        high = max(open_price, close) + range_size * (0.55 + abs(math.sin(index)))
        low = min(open_price, close) - range_size * (0.45 + abs(math.cos(index / 2)))
        volume = 1800 + 450 * abs(math.sin(index / 11)) + (index % 90) * 8

        candles.append(
            Candle(
                timestamp=(start + timedelta(hours=index)).isoformat(),
                open=round(open_price, 2),
                high=round(high, 2),
                low=round(low, 2),
                close=round(close, 2),
                volume=round(volume, 2),
            )
        )
        price = close

    return candles


def generate_intraday_sample_candles(count: int = 5760) -> list[Candle]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    price = 45_000.0
    candles: list[Candle] = []
    regimes = [0.00016, -0.00011, 0.00022, -0.00018, 0.00004, 0.0]

    for index in range(count):
        regime = regimes[(index // 960) % len(regimes)]
        cycle = math.sin(index / 72) * 0.00055
        faster_cycle = math.sin(index / 17) * 0.00032
        micro_noise = math.sin(index / 3.7) * 0.00018
        volatility = 0.0022 + 0.0011 * abs(math.sin(index / 149))
        change = regime + cycle + faster_cycle + micro_noise

        open_price = price
        close = max(1_000.0, open_price * (1 + change))
        range_size = open_price * volatility
        high = max(open_price, close) + range_size * (0.35 + abs(math.sin(index / 2)))
        low = min(open_price, close) - range_size * (0.35 + abs(math.cos(index / 3)))
        volume = 520 + 160 * abs(math.sin(index / 29)) + (index % 96) * 3.5

        candles.append(
            Candle(
                timestamp=(start + timedelta(minutes=15 * index)).isoformat(),
                open=round(open_price, 2),
                high=round(high, 2),
                low=round(low, 2),
                close=round(close, 2),
                volume=round(volume, 2),
            )
        )
        price = close

    return candles


def resample_candles(candles: list[Candle], group_size: int) -> list[Candle]:
    if group_size <= 0:
        raise ValueError("group_size must be positive.")

    resampled: list[Candle] = []
    for index in range(0, len(candles) - group_size + 1, group_size):
        group = candles[index : index + group_size]
        resampled.append(
            Candle(
                timestamp=group[0].timestamp,
                open=group[0].open,
                high=max(candle.high for candle in group),
                low=min(candle.low for candle in group),
                close=group[-1].close,
                volume=round(sum(candle.volume for candle in group), 2),
            )
        )
    return resampled


def save_sample_csv(path: str | Path, count: int = 120) -> None:
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    candles = generate_sample_candles(count)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp", "open", "high", "low", "close", "volume"],
        )
        writer.writeheader()
        for candle in candles:
            writer.writerow(candle.__dict__)


def save_research_sample_csv(path: str | Path, count: int = 1440) -> None:
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    candles = generate_research_sample_candles(count)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp", "open", "high", "low", "close", "volume"],
        )
        writer.writeheader()
        for candle in candles:
            writer.writerow(candle.__dict__)


def save_candles_csv(path: str | Path, candles: list[Candle]) -> None:
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp", "open", "high", "low", "close", "volume"],
        )
        writer.writeheader()
        for candle in candles:
            writer.writerow(candle.__dict__)
