from __future__ import annotations

import json
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from crypto_agent.agent import analyze_market
from crypto_agent.config import AgentConfig
from crypto_agent.market_data import (
    Candle,
    fetch_binance_klines,
    fetch_coinbase_candles,
)


ROOT = Path(__file__).resolve().parent.parent
MARKET_SOURCES = ("okx", "binance", "coinbase")
SUPPORTED_INTERVALS = {"15m", "1h"}


class TradingDeskHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in {"/", "/trading_desk.html"}:
            self._send_file(ROOT / "trading_desk.html", "text/html; charset=utf-8")
            return

        if parsed.path == "/api/candles":
            self._handle_candles(parsed.query)
            return

        self.send_error(404, "Not found")

    def log_message(self, format: str, *args) -> None:
        return

    def _handle_candles(self, query: str) -> None:
        params = urllib.parse.parse_qs(query)
        try:
            source = params.get("source", ["auto"])[0].lower()
            symbol = params.get("symbol", ["BTCUSDT"])[0].upper()
            interval = _normalize_interval(params.get("interval", ["15m"])[0])
            limit = _normalize_limit(params.get("limit", ["300"])[0])
            candles, actual_source, source_errors = _fetch_market_candles(
                source,
                symbol,
                interval,
                limit,
            )
            analysis = _build_analysis(symbol, interval, candles)
        except Exception as exc:
            self._send_json({"ok": False, "error": _format_error(exc)}, status=502)
            return

        self._send_json(
            {
                "ok": True,
                "requested_source": source,
                "source": actual_source,
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
                "source_errors": source_errors,
                "analysis": analysis,
                "candles": [_candle_payload(candle) for candle in candles],
            }
        )

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(404, "File not found")
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _fetch_market_candles(
    source: str,
    symbol: str,
    interval: str,
    limit: int,
) -> tuple[list[Candle], str, dict[str, str]]:
    errors: dict[str, str] = {}
    for candidate in _source_order(source):
        try:
            candles = _fetch_from_source(candidate, symbol, interval, limit)
            return candles, candidate, errors
        except Exception as exc:
            errors[candidate] = _format_error(exc)

    detail = "; ".join(f"{name}: {message}" for name, message in errors.items())
    raise RuntimeError(f"All market data sources failed. {detail}")


def _source_order(source: str) -> list[str]:
    if source in {"", "auto"}:
        return list(MARKET_SOURCES)
    if source not in MARKET_SOURCES:
        raise ValueError(
            f"Unsupported source '{source}'. Use auto, okx, binance, or coinbase."
        )
    return [source, *[candidate for candidate in MARKET_SOURCES if candidate != source]]


def _fetch_from_source(
    source: str,
    symbol: str,
    interval: str,
    limit: int,
) -> list[Candle]:
    if source == "binance":
        return fetch_binance_klines(symbol, interval, limit)
    if source == "coinbase":
        return fetch_coinbase_candles(_coinbase_product(symbol), interval, limit)
    return _fetch_okx_candles(symbol, interval, limit)


def _fetch_okx_candles(symbol: str, interval: str, limit: int) -> list[Candle]:
    inst_id = _okx_inst_id(symbol)
    bar = "15m" if interval == "15m" else "1H"
    rows: list[list[Any]] = []
    after: str | None = None

    while len(rows) < limit:
        page_limit = min(300, limit - len(rows))
        params = {"instId": inst_id, "bar": bar, "limit": page_limit}
        if after:
            params["after"] = after
        payload = _request_okx_candle_page(params, history=after is not None)
        page_rows = payload.get("data") or []
        if not page_rows:
            break
        rows.extend(page_rows)
        oldest_timestamp = str(page_rows[-1][0])
        if oldest_timestamp == after:
            break
        after = oldest_timestamp

    rows = _dedupe_okx_rows(rows)
    candles = []
    for row in reversed(rows):
        opened_at = int(row[0]) / 1000
        from datetime import datetime, timezone

        candles.append(
            Candle(
                timestamp=datetime.fromtimestamp(opened_at, tz=timezone.utc).isoformat(),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
        )
    if len(candles) < 30:
        raise ValueError("OKX returned too few candles.")
    return candles


def _request_okx_candle_page(
    params: dict[str, object],
    history: bool = False,
) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    endpoint = "history-candles" if history else "candles"
    errors: list[str] = []
    for domain in ("https://www.okx.com", "https://us.okx.com"):
        url = f"{domain}/api/v5/market/{endpoint}?{query}"
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "crypto-agent-mvp/0.1"},
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            errors.append(f"{domain}: {_format_error(exc)}")
    raise RuntimeError("; ".join(errors))


def _dedupe_okx_rows(rows: list[list[Any]]) -> list[list[Any]]:
    result: list[list[Any]] = []
    seen: set[str] = set()
    for row in rows:
        timestamp = str(row[0])
        if timestamp in seen:
            continue
        seen.add(timestamp)
        result.append(row)
    return result


def _okx_inst_id(symbol: str) -> str:
    normalized = symbol.upper()
    if "-" in normalized:
        return normalized
    for quote in ("USDT", "USDC", "USD"):
        if normalized.endswith(quote):
            return f"{normalized[: -len(quote)]}-{quote}"
    return normalized


def _coinbase_product(symbol: str) -> str:
    normalized = symbol.upper()
    if "-" in normalized:
        return normalized
    if normalized.endswith("USDT"):
        return normalized[:-4] + "-USD"
    if normalized.endswith("USD"):
        return normalized[:-3] + "-USD"
    return normalized


def _candle_payload(candle: Candle) -> dict:
    from datetime import datetime, timezone

    timestamp = datetime.fromisoformat(candle.timestamp)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return {
        "time": int(timestamp.timestamp()),
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
    }


def _build_analysis(symbol: str, interval: str, candles: list[Candle]) -> dict[str, Any]:
    config = AgentConfig(
        symbol=symbol,
        interval=interval,
        candle_limit=len(candles),
        allow_short=True,
    )
    result, _ = analyze_market(config, candles)
    return result


def _normalize_interval(value: str) -> str:
    interval = value.lower()
    if interval not in SUPPORTED_INTERVALS:
        raise ValueError("Trading desk supports 15m and 1h intervals.")
    return interval


def _normalize_limit(value: str) -> int:
    try:
        limit = int(value)
    except ValueError as exc:
        raise ValueError("limit must be an integer.") from exc
    return max(30, min(50_000, limit))


def _format_error(exc: BaseException) -> str:
    message = str(exc).strip()
    if message:
        return message
    return exc.__class__.__name__


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8765), TradingDeskHandler)
    print("Trading desk running at http://127.0.0.1:8765")
    server.serve_forever()


if __name__ == "__main__":
    main()
