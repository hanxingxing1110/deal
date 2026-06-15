from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import asdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from crypto_agent.agent import analyze_market
from crypto_agent.backtest import run_backtest
from crypto_agent.config import AgentConfig
from crypto_agent.history_completion import (
    SourceCandles,
    complete_history,
    coverage_needs_more_sources,
)
from crypto_agent.market_intelligence import build_market_intelligence
from crypto_agent.market_data import (
    Candle,
    fetch_crypto_news,
    fetch_binance_klines,
    fetch_coinbase_candles,
    fetch_funding_rate,
    fetch_order_book,
)
from crypto_agent.paper_ledger import (
    append_ledger_entry,
    clear_ledger,
    read_ledger,
    summarize_ledger,
)
from crypto_agent.strategy_profiles import get_profile, list_profiles


ROOT = Path(__file__).resolve().parent.parent
MARKET_SOURCES = ("okx", "binance", "coinbase")
INTERVALS: dict[str, dict[str, Any]] = {
    "1s": {"seconds": 1, "okx": "1s", "binance": "1s", "coinbase": None, "max_full": 86_400},
    "1m": {"seconds": 60, "okx": "1m", "binance": "1m", "coinbase": 60, "max_full": 250_000},
    "5m": {"seconds": 300, "okx": "5m", "binance": "5m", "coinbase": 300, "max_full": 250_000},
    "15m": {"seconds": 900, "okx": "15m", "binance": "15m", "coinbase": 900, "max_full": 500_000},
    "1h": {"seconds": 3600, "okx": "1H", "binance": "1h", "coinbase": 3600, "max_full": 150_000},
    "4h": {"seconds": 14_400, "okx": "4H", "binance": "4h", "coinbase": None, "max_full": 80_000},
    "8h": {"seconds": 28_800, "okx": "8H", "binance": "8h", "coinbase": None, "max_full": 60_000},
    "1d": {"seconds": 86_400, "okx": "1D", "binance": "1d", "coinbase": 86_400, "max_full": 20_000},
    "3d": {"seconds": 259_200, "okx": "3D", "binance": "3d", "coinbase": None, "max_full": 10_000},
    "1w": {"seconds": 604_800, "okx": "1W", "binance": "1w", "coinbase": None, "max_full": 5_000},
    "1M": {"seconds": 2_592_000, "okx": "1M", "binance": "1M", "coinbase": None, "max_full": 2_000},
    "1y": {"seconds": 31_536_000, "okx": "1M", "binance": "1M", "coinbase": None, "max_full": 500},
}
DEFAULT_HISTORY_START = "2012-01-01"


class TradingDeskHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in {"/", "/trading_desk.html"}:
            self._send_file(ROOT / "trading_desk.html", "text/html; charset=utf-8")
            return

        if parsed.path == "/api/candles":
            self._handle_candles(parsed.query)
            return

        if parsed.path == "/api/intelligence":
            self._handle_intelligence(parsed.query)
            return

        if parsed.path == "/api/backtest-summary":
            self._handle_backtest_summary(parsed.query)
            return

        if parsed.path == "/api/ledger":
            self._handle_ledger()
            return

        if parsed.path == "/api/strategy-profiles":
            self._send_json({"ok": True, "profiles": list_profiles()})
            return

        if parsed.path == "/api/alerts":
            self._handle_alerts(parsed.query)
            return

        self.send_error(404, "Not found")

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/ledger":
            self._handle_ledger_post()
            return
        self.send_error(404, "Not found")

    def do_DELETE(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/ledger":
            clear_ledger()
            self._send_json({"ok": True, "entries": [], "summary": summarize_ledger([])})
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
            start = _normalize_start(params.get("start", [""])[0])
            limit = _normalize_limit(params.get("limit", ["300"])[0], interval)
            strategy_profile = get_profile(params.get("strategy", ["balanced_v1"])[0])
            candles, actual_source, source_errors, completion = _fetch_market_candles(
                source,
                symbol,
                interval,
                limit,
                start,
            )
            analysis_error = None
            try:
                analysis = _build_analysis(symbol, interval, candles, strategy_profile.params)
            except Exception as exc:
                analysis = None
                analysis_error = _format_error(exc)
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
                "start": start,
                "interval_meta": _interval_meta(interval),
                "strategy_profile": {
                    "id": strategy_profile.id,
                    "name": strategy_profile.name,
                    "description": strategy_profile.description,
                    "params": asdict(strategy_profile.params),
                },
                "source_errors": source_errors,
                "history_completion": completion,
                "analysis": analysis,
                "analysis_error": analysis_error,
                "candles": [_candle_payload(candle) for candle in candles],
            }
        )

    def _handle_intelligence(self, query: str) -> None:
        params = urllib.parse.parse_qs(query)
        try:
            source = params.get("source", ["auto"])[0].lower()
            symbol = params.get("symbol", ["BTCUSDT"])[0].upper()
            interval = _normalize_interval(params.get("interval", ["15m"])[0])
            start = _normalize_start(params.get("start", [""])[0])
            limit = _normalize_limit(params.get("limit", ["320"])[0], interval)
            candles, actual_source, candle_errors, _completion = _fetch_market_candles(
                source,
                symbol,
                interval,
                limit,
                start,
            )
            config = AgentConfig(symbol=symbol, interval=interval, candle_limit=len(candles), allow_short=True)
            book, book_errors = _optional_fetch(lambda: fetch_order_book(symbol, 100, source))
            funding, funding_errors = _optional_fetch(lambda: fetch_funding_rate(symbol, source))
            news, news_errors = _optional_fetch(lambda: fetch_crypto_news(8), default=[])
            result = build_market_intelligence(
                config,
                candles,
                candle_source=actual_source,
                order_book=book,
                funding=funding,
                news=news,
                source_errors={
                    "candles": candle_errors,
                    "order_book": book_errors,
                    "funding": funding_errors,
                    "news": news_errors,
                },
            )
        except Exception as exc:
            self._send_json({"ok": False, "error": _format_error(exc)}, status=502)
            return

        self._send_json({"ok": True, "intelligence": result})

    def _handle_backtest_summary(self, query: str) -> None:
        params = urllib.parse.parse_qs(query)
        try:
            source = params.get("source", ["auto"])[0].lower()
            symbol = params.get("symbol", ["BTCUSDT"])[0].upper()
            interval = _normalize_interval(params.get("interval", ["15m"])[0])
            start = _normalize_start(params.get("start", [""])[0])
            limit = _normalize_limit(params.get("limit", ["1000"])[0], interval)
            strategy_profile = get_profile(params.get("strategy", ["balanced_v1"])[0])
            candles, actual_source, source_errors, completion = _fetch_market_candles(
                source,
                symbol,
                interval,
                limit,
                start,
            )
            config = AgentConfig(symbol=symbol, interval=interval, candle_limit=len(candles), allow_short=True)
            result = run_backtest(config, candles, strategy_profile.params)
            summary = {
                key: result.get(key)
                for key in (
                    "symbol",
                    "interval",
                    "return_pct",
                    "net_profit",
                    "max_drawdown_pct",
                    "total_trades",
                    "win_rate_pct",
                    "profit_factor",
                    "advanced_metrics",
                    "data_quality",
                )
            }
            summary["source"] = actual_source
            summary["source_errors"] = source_errors
            summary["history_completion"] = completion
            baseline_result = run_backtest(config, candles, get_profile("balanced_v1").params)
            summary["baseline"] = {
                "strategy": "balanced_v1",
                "win_rate_pct": baseline_result.get("win_rate_pct"),
                "total_trades": baseline_result.get("total_trades"),
                "return_pct": baseline_result.get("return_pct"),
                "profit_factor": baseline_result.get("profit_factor"),
            }
            summary["win_rate_delta_pct"] = round(
                float(summary.get("win_rate_pct") or 0.0)
                - float(summary["baseline"].get("win_rate_pct") or 0.0),
                2,
            )
            summary["strategy_profile"] = {
                "id": strategy_profile.id,
                "name": strategy_profile.name,
                "params": asdict(strategy_profile.params),
            }
            summary["readiness"] = _readiness_notes(summary)
        except Exception as exc:
            self._send_json({"ok": False, "error": _format_error(exc)}, status=502)
            return

        self._send_json({"ok": True, "summary": summary})

    def _handle_ledger(self) -> None:
        entries = read_ledger()
        self._send_json({"ok": True, "entries": entries, "summary": summarize_ledger(entries)})

    def _handle_ledger_post(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            payload = json.loads(raw)
            entry = append_ledger_entry(payload)
            entries = read_ledger()
        except Exception as exc:
            self._send_json({"ok": False, "error": _format_error(exc)}, status=400)
            return
        self._send_json(
            {
                "ok": True,
                "entry": entry.__dict__,
                "entries": entries,
                "summary": summarize_ledger(entries),
            }
        )

    def _handle_alerts(self, query: str) -> None:
        params = urllib.parse.parse_qs(query)
        try:
            source = params.get("source", ["auto"])[0].lower()
            symbol = params.get("symbol", ["BTCUSDT"])[0].upper()
            interval = _normalize_interval(params.get("interval", ["15m"])[0])
            start = _normalize_start(params.get("start", [""])[0])
            limit = _normalize_limit(params.get("limit", ["320"])[0], interval)
            candles, actual_source, source_errors, _completion = _fetch_market_candles(source, symbol, interval, limit, start)
            analysis = _build_analysis(symbol, interval, candles, get_profile(None).params)
            alerts = _build_alerts(candles, analysis, actual_source)
        except Exception as exc:
            self._send_json({"ok": False, "error": _format_error(exc)}, status=502)
            return
        self._send_json({"ok": True, "alerts": alerts, "source_errors": source_errors})

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
    start: str | None = None,
) -> tuple[list[Candle], str, dict[str, str], dict[str, Any]]:
    errors: dict[str, str] = {}
    successful: list[SourceCandles] = []
    for candidate in _source_order(source):
        try:
            candles = _fetch_from_source(candidate, symbol, interval, limit, start)
            successful.append(SourceCandles(candidate, candles))
            completed, report = complete_history(
                successful,
                int(INTERVALS[interval]["seconds"]),
                limit,
                start,
            )
            if not coverage_needs_more_sources(completed, int(INTERVALS[interval]["seconds"]), limit, start):
                actual_source = "+".join(report.get("contribution", {}).keys()) or candidate
                return completed, actual_source, errors, report
        except Exception as exc:
            errors[candidate] = _format_error(exc)

    if successful:
        completed, report = complete_history(
            successful,
            int(INTERVALS[interval]["seconds"]),
            limit,
            start,
        )
        actual_source = "+".join(report.get("contribution", {}).keys()) or successful[0].source
        return completed, actual_source, errors, report

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
    start: str | None = None,
) -> list[Candle]:
    if source == "binance":
        return _fetch_binance_candles(symbol, interval, limit, start)
    if source == "coinbase":
        return _fetch_coinbase_range(_coinbase_product(symbol), interval, limit, start)
    return _fetch_okx_candles(symbol, interval, limit, start)


def _fetch_okx_candles(
    symbol: str,
    interval: str,
    limit: int,
    start: str | None = None,
) -> list[Candle]:
    inst_id = _okx_inst_id(symbol)
    bar = INTERVALS[interval]["okx"]
    if interval == "1y":
        return _aggregate_yearly(_fetch_okx_candles(symbol, "1M", min(limit * 12, INTERVALS["1M"]["max_full"]), start))[-limit:]
    rows: list[list[Any]] = []
    after: str | None = None
    start_ts = _start_timestamp_ms(start)

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
        if start_ts and int(oldest_timestamp) <= start_ts:
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
    if start:
        candles = _filter_from_start(candles, start)
    if len(candles) < 30:
        raise ValueError("OKX returned too few candles.")
    return candles[-limit:]


def _fetch_binance_candles(
    symbol: str,
    interval: str,
    limit: int,
    start: str | None = None,
) -> list[Candle]:
    binance_interval = INTERVALS[interval]["binance"]
    if not binance_interval:
        raise ValueError(f"Binance does not support interval {interval}.")
    if interval == "1y":
        monthly = _fetch_binance_candles(symbol, "1M", min(limit * 12, INTERVALS["1M"]["max_full"]), start)
        return _aggregate_yearly(monthly)[-limit:]
    candles = fetch_binance_klines(symbol, binance_interval, limit)
    if start:
        candles = _filter_from_start(candles, start)
    if len(candles) < 30:
        raise ValueError("Binance returned too few candles.")
    return candles[-limit:]


def _fetch_coinbase_range(
    product_id: str,
    interval: str,
    limit: int,
    start: str | None = None,
) -> list[Candle]:
    granularity = INTERVALS[interval]["coinbase"]
    if not granularity:
        raise ValueError(f"Coinbase does not support interval {interval}.")
    # Coinbase's public candles endpoint is capped per request and is best used as a
    # fallback for recent history. Deep history should use OKX/Binance or imported CSV.
    candles = fetch_coinbase_candles(product_id, interval, min(limit, 300))
    if start:
        candles = _filter_from_start(candles, start)
    return candles[-limit:]


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


def _filter_from_start(candles: list[Candle], start: str) -> list[Candle]:
    start_dt = _parse_start_date(start)
    return [
        candle
        for candle in candles
        if _parse_iso_time(candle.timestamp) >= start_dt
    ]


def _start_timestamp_ms(start: str | None) -> int | None:
    if not start:
        return None
    return int(_parse_start_date(start).timestamp() * 1000)


def _parse_start_date(value: str) -> datetime:
    normalized = value.strip() or DEFAULT_HISTORY_START
    if len(normalized) == 10:
        normalized = f"{normalized}T00:00:00+00:00"
    normalized = normalized.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_iso_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _aggregate_yearly(candles: list[Candle]) -> list[Candle]:
    buckets: dict[int, list[Candle]] = {}
    for candle in candles:
        year = _parse_iso_time(candle.timestamp).year
        buckets.setdefault(year, []).append(candle)
    result: list[Candle] = []
    for year, rows in sorted(buckets.items()):
        rows = sorted(rows, key=lambda item: _parse_iso_time(item.timestamp))
        result.append(
            Candle(
                timestamp=datetime(year, 1, 1, tzinfo=timezone.utc).isoformat(),
                open=rows[0].open,
                high=max(item.high for item in rows),
                low=min(item.low for item in rows),
                close=rows[-1].close,
                volume=round(sum(item.volume for item in rows), 6),
            )
        )
    return result


def _build_analysis(
    symbol: str,
    interval: str,
    candles: list[Candle],
    strategy_params: Any,
) -> dict[str, Any]:
    config = AgentConfig(
        symbol=symbol,
        interval=interval,
        candle_limit=len(candles),
        allow_short=True,
    )
    result, _ = analyze_market(config, candles, strategy_params)
    return result


def _optional_fetch(fetcher: Any, default: Any = None) -> tuple[Any, dict[str, str]]:
    try:
        result = fetcher()
        if isinstance(result, tuple) and len(result) == 2:
            return result
        return result, {}
    except Exception as exc:
        return default, {"all": _format_error(exc)}


def _build_alerts(candles: list[Candle], analysis: dict[str, Any], source: str) -> list[dict[str, Any]]:
    latest = candles[-1]
    indicators = analysis.get("indicators") or {}
    technicals = analysis.get("technicals") or {}
    alerts: list[dict[str, Any]] = []
    if analysis.get("decision") in {"LONG", "SHORT"} and analysis.get("risk_allowed"):
        alerts.append(
            {
                "level": "signal",
                "title": f"出现 {analysis.get('decision')} 纸上交易信号",
                "detail": f"置信度 {analysis.get('confidence')}，数据源 {source}。",
            }
        )
    if float(indicators.get("atr_pct") or 0) >= 2.0:
        alerts.append(
            {
                "level": "risk",
                "title": "波动率偏高",
                "detail": f"ATR 占比 {round(float(indicators.get('atr_pct') or 0), 3)}%，需要缩小仓位。",
            }
        )
    if float(indicators.get("rsi_14") or 50) >= 72:
        alerts.append({"level": "risk", "title": "RSI 过热", "detail": "追多风险升高。"})
    if float(indicators.get("rsi_14") or 50) <= 28:
        alerts.append({"level": "risk", "title": "RSI 过冷", "detail": "追空风险升高，可能出现反弹。"})
    if abs(float(technicals.get("score") or 0.0)) >= 0.28:
        direction = "偏多" if float(technicals.get("score") or 0.0) > 0 else "偏空"
        alerts.append({"level": "technical", "title": f"技术共振{direction}", "detail": "多组 K 线工具方向一致。"})
    if not alerts:
        alerts.append({"level": "info", "title": "暂无触发提醒", "detail": f"{latest.timestamp} 保持观察。"})
    return alerts


def _readiness_notes(summary: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    trades = int(summary.get("total_trades") or 0)
    return_pct = float(summary.get("return_pct") or 0.0)
    drawdown = float(summary.get("max_drawdown_pct") or 0.0)
    profit_factor = float(summary.get("profit_factor") or 0.0)
    if trades < 20:
        notes.append("交易样本偏少，不能进入实盘，只能继续观察。")
    if return_pct <= 0:
        notes.append("当前回测收益不为正，需要继续优化或换行情分段。")
    if drawdown >= 8:
        notes.append("最大回撤偏高，模拟盘也应降低风险敞口。")
    if not notes:
        notes.append("研究指标初步可观察，但仍需更长历史和分段验证。")
    return notes


def _normalize_interval(value: str) -> str:
    raw = value.strip()
    aliases = {
        "1sec": "1s",
        "1second": "1s",
        "1min": "1m",
        "1month": "1M",
        "1mo": "1M",
        "1y": "1y",
        "1yr": "1y",
        "1year": "1y",
    }
    interval = aliases.get(raw, aliases.get(raw.lower(), raw))
    if interval.lower() == "1m" and raw == "1M":
        interval = "1M"
    elif interval not in INTERVALS:
        interval = interval.lower()
    if interval not in INTERVALS:
        raise ValueError(
            "Trading desk supports 1s, 1m, 5m, 15m, 1h, 4h, 8h, 1d, 3d, 1w, 1M, 1y intervals."
        )
    return interval


def _normalize_limit(value: str, interval: str = "15m") -> int:
    raw = str(value).strip().lower()
    if raw in {"all", "max", "full", "0"}:
        return int(INTERVALS[interval]["max_full"])
    try:
        limit = int(raw)
    except ValueError as exc:
        raise ValueError("limit must be an integer, all, max, or full.") from exc
    return max(30, min(int(INTERVALS[interval]["max_full"]), limit))


def _normalize_start(value: str) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    return _parse_start_date(raw).date().isoformat()


def _interval_meta(interval: str) -> dict[str, Any]:
    meta = INTERVALS[interval]
    return {
        "seconds": meta["seconds"],
        "max_full": meta["max_full"],
        "deep_history_note": _deep_history_note(interval),
    }


def _deep_history_note(interval: str) -> str:
    if interval in {"1s", "1m", "5m"}:
        return "小周期历史数据量极大，页面会使用安全上限；如需多年秒线/分钟线，建议离线下载到 CSV 后导入。"
    if interval in {"15m", "1h"}:
        return "可以拉取较长历史，但最早时间仍取决于交易所和交易对上线时间。"
    return "适合查看多年历史，最早时间取决于交易所和交易对上线时间。"


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
