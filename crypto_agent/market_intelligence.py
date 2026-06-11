from __future__ import annotations

import html
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crypto_agent.config import AgentConfig
from crypto_agent.indicators import latest_indicator_snapshot
from crypto_agent.market_data import (
    Candle,
    FundingRateSnapshot,
    NewsItem,
    OrderBookLevel,
    OrderBookSnapshot,
    fetch_binance_klines,
    fetch_coinbase_candles,
    fetch_crypto_news,
    fetch_funding_rate,
    fetch_okx_candles,
    fetch_order_book,
    load_csv,
    save_candles_csv,
)
from crypto_agent.strategy import build_signal
from crypto_agent.technical_analysis import build_technical_snapshot


def run_market_intelligence(
    config: AgentConfig,
    *,
    source: str = "auto",
    candle_limit: int | None = None,
    order_book_limit: int = 100,
    cache_csv: str | Path | None = None,
    news_limit: int = 8,
) -> dict[str, Any]:
    limit = candle_limit or config.candle_limit
    candles, candle_source, source_errors = _fetch_or_load_candles(
        config,
        source=source,
        limit=limit,
        cache_csv=cache_csv,
    )

    book = None
    book_errors: dict[str, str] = {}
    try:
        book, book_errors = fetch_order_book(config.symbol, order_book_limit, source)
    except Exception as exc:
        book_errors["all"] = _format_error(exc)

    funding = None
    funding_errors: dict[str, str] = {}
    try:
        funding, funding_errors = fetch_funding_rate(config.symbol, source)
    except Exception as exc:
        funding_errors["all"] = _format_error(exc)

    news: list[NewsItem] = []
    news_errors: dict[str, str] = {}
    try:
        news, news_errors = fetch_crypto_news(news_limit)
    except Exception as exc:
        news_errors["all"] = _format_error(exc)

    return build_market_intelligence(
        config=config,
        candles=candles,
        candle_source=candle_source,
        order_book=book,
        funding=funding,
        news=news,
        source_errors={
            "candles": source_errors,
            "order_book": book_errors,
            "funding": funding_errors,
            "news": news_errors,
        },
    )


def build_market_intelligence(
    config: AgentConfig,
    candles: list[Candle],
    *,
    candle_source: str = "provided",
    order_book: OrderBookSnapshot | None = None,
    funding: FundingRateSnapshot | None = None,
    news: list[NewsItem] | None = None,
    source_errors: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if len(candles) < 30:
        raise ValueError("Need at least 30 candles to build market intelligence.")

    indicators = latest_indicator_snapshot(candles)
    technicals = build_technical_snapshot(candles)
    signal = build_signal(indicators, allow_short=True, technicals=technicals)
    support_resistance = analyze_support_resistance(candles)
    order_book_view = analyze_order_book(order_book)
    funding_view = analyze_funding(funding)
    risk_events = analyze_risk_events(news or [])
    trend_view = analyze_trend(indicators)
    volatility_view = analyze_volatility(indicators)
    trade_view = synthesize_trade_view(
        signal_decision=signal.decision,
        signal_confidence=signal.confidence,
        trend_view=trend_view,
        volatility_view=volatility_view,
        order_book_view=order_book_view,
        funding_view=funding_view,
        risk_events=risk_events,
    )

    latest = candles[-1]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "research_paper_only",
        "symbol": config.symbol,
        "interval": config.interval,
        "candle_source": candle_source,
        "latest_candle_time": latest.timestamp,
        "latest_price": latest.close,
        "indicators": {key: round(value, 6) for key, value in indicators.items()},
        "trend": trend_view,
        "volatility": volatility_view,
        "support_resistance": support_resistance,
        "technicals": technicals,
        "order_book": order_book_view,
        "funding": funding_view,
        "risk_events": risk_events,
        "trade_view": trade_view,
        "paper_action": {
            "decision": signal.decision,
            "confidence": signal.confidence,
            "entry": signal.entry,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "note": "仅用于纸上交易和研究，不会真实下单。",
            "reasons": signal.reasons,
        },
        "source_errors": source_errors or {},
    }


def analyze_trend(indicators: dict[str, float]) -> dict[str, Any]:
    close = indicators["close"]
    ema_12 = indicators["ema_12"]
    ema_26 = indicators["ema_26"]
    sma_20 = indicators["sma_20"]
    rsi_14 = indicators["rsi_14"]
    trend_efficiency = indicators.get("trend_efficiency_20", 0.0)
    ema_gap_pct = ((ema_12 - ema_26) / close) * 100 if close else 0.0
    sma_gap_pct = ((close - sma_20) / close) * 100 if close else 0.0

    direction = "neutral"
    score = 0.0
    notes: list[str] = []
    if ema_12 > ema_26 and close > sma_20:
        direction = "bullish"
        score += 0.45
        notes.append("短期均线在中期均线上方，价格站上 SMA20。")
    elif ema_12 < ema_26 and close < sma_20:
        direction = "bearish"
        score += 0.45
        notes.append("短期均线在中期均线下方，价格跌破 SMA20。")
    else:
        notes.append("均线方向不一致，趋势暂时不够清晰。")

    if trend_efficiency >= 0.35:
        score += 0.25
        notes.append("趋势效率较高，近期走势更偏单边。")
    elif trend_efficiency < 0.18:
        notes.append("趋势效率偏低，容易出现震荡和假突破。")

    if 42 <= rsi_14 <= 68:
        score += 0.15
        notes.append("RSI 没有明显过热或过冷。")
    elif rsi_14 > 72:
        notes.append("RSI 偏高，追多风险增加。")
    elif rsi_14 < 30:
        notes.append("RSI 偏低，追空风险增加。")

    return {
        "direction": direction,
        "strength": round(min(score, 1.0), 3),
        "ema_gap_pct": round(ema_gap_pct, 4),
        "sma_gap_pct": round(sma_gap_pct, 4),
        "trend_efficiency_20": round(trend_efficiency, 4),
        "notes": notes,
    }


def analyze_volatility(indicators: dict[str, float]) -> dict[str, Any]:
    atr_pct = indicators["atr_pct"]
    range_atr_ratio = indicators.get("range_atr_ratio", 0.0)
    state = "normal"
    notes = ["波动处于可观察区间。"]
    risk_score = 0.35
    if atr_pct >= 2.5:
        state = "high"
        risk_score = 0.75
        notes = ["ATR 占比偏高，止损距离和滑点风险都要放大。"]
    elif atr_pct <= 0.35:
        state = "compressed"
        risk_score = 0.55
        notes = ["ATR 占比偏低，行情可能在压缩区间内等待突破。"]

    if range_atr_ratio >= 1.8:
        risk_score += 0.12
        notes.append("最新 K 线实体/影线波动较大，短线噪声上升。")

    return {
        "state": state,
        "risk_score": round(min(risk_score, 1.0), 3),
        "atr_pct": round(atr_pct, 4),
        "range_atr_ratio": round(range_atr_ratio, 4),
        "notes": notes,
    }


def analyze_support_resistance(candles: list[Candle]) -> dict[str, Any]:
    latest_price = candles[-1].close
    recent = candles[-180:] if len(candles) > 180 else candles
    lows = _cluster_levels([candle.low for candle in recent], latest_price)
    highs = _cluster_levels([candle.high for candle in recent], latest_price)
    supports = [level for level in lows if level["price"] < latest_price]
    resistances = [level for level in highs if level["price"] > latest_price]
    supports = sorted(supports, key=lambda item: abs(latest_price - item["price"]))[:5]
    resistances = sorted(resistances, key=lambda item: abs(item["price"] - latest_price))[:5]

    return {
        "latest_price": round(latest_price, 4),
        "nearest_support": supports[0] if supports else None,
        "nearest_resistance": resistances[0] if resistances else None,
        "supports": supports,
        "resistances": resistances,
        "method": "最近 180 根 K 线高低点聚类。",
    }


def analyze_order_book(book: OrderBookSnapshot | None) -> dict[str, Any]:
    if book is None or not book.bids or not book.asks:
        return {
            "available": False,
            "note": "订单簿未获取到，当前观点不使用盘口倾斜。",
        }

    top_bid = book.bids[0].price
    top_ask = book.asks[0].price
    mid = (top_bid + top_ask) / 2
    spread_bps = ((top_ask - top_bid) / mid) * 10_000 if mid else 0.0
    bid_notional = sum(level.notional for level in book.bids[:20])
    ask_notional = sum(level.notional for level in book.asks[:20])
    total = bid_notional + ask_notional
    imbalance = (bid_notional - ask_notional) / total if total else 0.0
    bid_wall = _largest_wall(book.bids[:40])
    ask_wall = _largest_wall(book.asks[:40])

    tilt = "neutral"
    note = "买卖盘相对均衡。"
    if imbalance >= 0.12:
        tilt = "bid_heavy"
        note = "近端买盘更厚，短线下方承接相对强。"
    elif imbalance <= -0.12:
        tilt = "ask_heavy"
        note = "近端卖盘更厚，短线上方抛压相对强。"

    return {
        "available": True,
        "source": book.source,
        "timestamp": book.timestamp,
        "top_bid": round(top_bid, 4),
        "top_ask": round(top_ask, 4),
        "spread_bps": round(spread_bps, 4),
        "top20_bid_notional": round(bid_notional, 2),
        "top20_ask_notional": round(ask_notional, 2),
        "imbalance": round(imbalance, 4),
        "tilt": tilt,
        "nearest_bid_wall": bid_wall,
        "nearest_ask_wall": ask_wall,
        "note": note,
    }


def analyze_funding(funding: FundingRateSnapshot | None) -> dict[str, Any]:
    if funding is None or funding.funding_rate is None:
        return {
            "available": False,
            "note": "资金费率未获取到，当前观点不使用合约拥挤度。",
        }

    rate_pct = funding.funding_rate * 100
    crowding = "neutral"
    note = "资金费率接近中性，多空拥挤度不明显。"
    if rate_pct >= 0.03:
        crowding = "long_crowded"
        note = "资金费率偏高，多头拥挤，追多要更谨慎。"
    elif rate_pct <= -0.03:
        crowding = "short_crowded"
        note = "资金费率偏负，空头拥挤，追空要更谨慎。"

    return {
        "available": True,
        "source": funding.source,
        "timestamp": funding.timestamp,
        "funding_rate_pct": round(rate_pct, 6),
        "next_funding_time": funding.next_funding_time,
        "mark_price": funding.mark_price,
        "index_price": funding.index_price,
        "crowding": crowding,
        "note": note,
    }


def analyze_risk_events(news: list[NewsItem]) -> dict[str, Any]:
    if not news:
        return {
            "available": False,
            "headline_count": 0,
            "risk_level": "unknown",
            "events": [],
            "note": "新闻源未接入成功或暂无公开新闻数据。",
        }

    keywords = {
        "high": [
            "hack",
            "exploit",
            "lawsuit",
            "sec",
            "fed",
            "fomc",
            "cpi",
            "inflation",
            "war",
            "ban",
            "outage",
            "liquidation",
        ],
        "medium": ["etf", "regulation", "court", "tariff", "rate", "exchange"],
    }
    events: list[dict[str, Any]] = []
    high_hits = 0
    medium_hits = 0
    for item in news:
        text = f"{item.title} {item.summary or ''}".lower()
        severity = "low"
        matched: list[str] = []
        for keyword in keywords["high"]:
            if keyword in text:
                severity = "high"
                matched.append(keyword)
        if severity != "high":
            for keyword in keywords["medium"]:
                if keyword in text:
                    severity = "medium"
                    matched.append(keyword)
        high_hits += severity == "high"
        medium_hits += severity == "medium"
        events.append(
            {
                "source": item.source,
                "title": item.title,
                "link": item.link,
                "published_at": item.published_at,
                "severity": severity,
                "matched_keywords": matched,
            }
        )

    risk_level = "low"
    if high_hits:
        risk_level = "high"
    elif medium_hits >= 2:
        risk_level = "medium"

    return {
        "available": True,
        "headline_count": len(news),
        "risk_level": risk_level,
        "events": events,
        "note": "新闻只是风险提示，不直接作为买卖信号。",
    }


def synthesize_trade_view(
    *,
    signal_decision: str,
    signal_confidence: float,
    trend_view: dict[str, Any],
    volatility_view: dict[str, Any],
    order_book_view: dict[str, Any],
    funding_view: dict[str, Any],
    risk_events: dict[str, Any],
) -> dict[str, Any]:
    stance = "wait"
    score = signal_confidence
    notes: list[str] = []

    if trend_view["direction"] == "bullish":
        score += 0.08
        notes.append("趋势层偏多。")
    elif trend_view["direction"] == "bearish":
        score += 0.08
        notes.append("趋势层偏空。")
    else:
        score -= 0.08
        notes.append("趋势层中性，降低主动交易优先级。")

    if volatility_view["state"] == "high":
        score -= 0.12
        notes.append("波动偏高，仓位和止损需要更保守。")
    elif volatility_view["state"] == "compressed":
        score -= 0.04
        notes.append("波动压缩，等待放量突破更合适。")

    if order_book_view.get("available"):
        if signal_decision == "LONG" and order_book_view.get("tilt") == "bid_heavy":
            score += 0.05
            notes.append("盘口买盘厚度支持做多观点。")
        elif signal_decision == "SHORT" and order_book_view.get("tilt") == "ask_heavy":
            score += 0.05
            notes.append("盘口卖盘厚度支持做空观点。")
        elif order_book_view.get("tilt") != "neutral":
            score -= 0.03
            notes.append("盘口倾斜与策略信号不完全一致。")

    if funding_view.get("available"):
        crowding = funding_view.get("crowding")
        if signal_decision == "LONG" and crowding == "long_crowded":
            score -= 0.08
            notes.append("多头资金费率拥挤，不适合追高。")
        elif signal_decision == "SHORT" and crowding == "short_crowded":
            score -= 0.08
            notes.append("空头资金费率拥挤，不适合追空。")

    if risk_events.get("risk_level") == "high":
        score -= 0.15
        notes.append("新闻风险偏高，优先观望或降低仓位。")
    elif risk_events.get("risk_level") == "medium":
        score -= 0.06
        notes.append("新闻风险中等，需要缩小风险暴露。")

    score = round(max(0.0, min(score, 0.95)), 3)
    if signal_decision in {"LONG", "SHORT"} and score >= 0.58:
        stance = signal_decision.lower()
    elif signal_decision in {"LONG", "SHORT"}:
        notes.append("策略有方向，但综合分不足，先列入观察。")

    return {
        "stance": stance,
        "score": score,
        "strategy_signal": signal_decision,
        "notes": notes,
        "safety": "研究版本只生成观点和纸上动作，不连接交易所账户，不真实下单。",
    }


def save_market_intelligence_json(result: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def render_market_intelligence_report(
    result: dict[str, Any],
    output_path: str | Path,
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    cards = [
        ("趋势", result["trend"]["direction"], result["trend"].get("notes", [])),
        ("波动", result["volatility"]["state"], result["volatility"].get("notes", [])),
        ("盘口", result["order_book"].get("tilt", "unavailable"), [result["order_book"].get("note", "")]),
        ("资金费率", result["funding"].get("crowding", "unavailable"), [result["funding"].get("note", "")]),
        ("新闻风险", result["risk_events"].get("risk_level", "unknown"), [result["risk_events"].get("note", "")]),
        ("综合观点", result["trade_view"]["stance"], result["trade_view"].get("notes", [])),
    ]
    card_html = "\n".join(_render_card(title, value, notes) for title, value, notes in cards)
    support_rows = _render_level_rows(result["support_resistance"].get("supports") or [])
    resistance_rows = _render_level_rows(result["support_resistance"].get("resistances") or [])
    event_rows = _render_event_rows(result["risk_events"].get("events") or [])
    source_errors = _render_source_errors(result.get("source_errors") or {})

    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Market Intelligence Report</title>
  <style>
    :root {{
      --bg: #f7f8fa;
      --panel: #ffffff;
      --ink: #18212f;
      --muted: #667085;
      --line: #d9e0ea;
      --green: #0b7f5b;
      --red: #b73935;
      --blue: #245f9f;
      --amber: #a76f12;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Arial, "Microsoft YaHei", sans-serif;
      letter-spacing: 0;
    }}
    main {{
      width: min(1180px, calc(100% - 28px));
      margin: 0 auto;
      padding: 24px 0 42px;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      padding-bottom: 18px;
      border-bottom: 1px solid var(--line);
    }}
    h1, h2, h3, p {{ margin: 0; }}
    h1 {{ font-size: 28px; line-height: 1.2; }}
    h2 {{ font-size: 17px; margin-bottom: 12px; }}
    h3 {{ font-size: 13px; color: var(--muted); margin-bottom: 8px; }}
    .muted {{ color: var(--muted); font-size: 14px; line-height: 1.55; margin-top: 7px; }}
    .badge {{
      min-width: 112px;
      height: 38px;
      padding: 0 14px;
      border-radius: 8px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: var(--blue);
      color: #fff;
      font-weight: 700;
      text-transform: uppercase;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 14px;
      margin-top: 18px;
    }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    .span-4 {{ grid-column: span 4; }}
    .span-6 {{ grid-column: span 6; }}
    .span-12 {{ grid-column: span 12; }}
    .value {{ font-size: 24px; font-weight: 700; text-transform: uppercase; }}
    ul {{ margin: 10px 0 0; padding-left: 18px; }}
    li {{ margin: 6px 0; line-height: 1.45; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 9px 8px; border-bottom: 1px solid #edf1f5; text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-weight: 600; }}
    .metric {{
      display: grid;
      grid-template-columns: 150px 1fr;
      gap: 10px;
      padding: 7px 0;
      border-bottom: 1px solid #edf1f5;
      font-size: 14px;
    }}
    .metric span {{ color: var(--muted); }}
    .warning {{ color: var(--red); }}
    @media (max-width: 760px) {{
      header {{ flex-direction: column; }}
      .span-4, .span-6, .span-12 {{ grid-column: span 12; }}
      .metric {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>{_escape(result["symbol"])} 市场情报报告</h1>
        <p class="muted">周期 {_escape(result["interval"])} | K 线源 {_escape(result["candle_source"])} | 最新 K 线 {_escape(result["latest_candle_time"])}</p>
        <p class="muted">本报告只用于研究和纸上交易，不连接账户，不真实下单。</p>
      </div>
      <span class="badge">{_escape(result["trade_view"]["stance"])}</span>
    </header>
    <div class="grid">
      {card_html}
      <section class="span-6">
        <h2>支撑位</h2>
        <table><thead><tr><th>价格</th><th>距离</th><th>触点</th></tr></thead><tbody>{support_rows}</tbody></table>
      </section>
      <section class="span-6">
        <h2>压力位</h2>
        <table><thead><tr><th>价格</th><th>距离</th><th>触点</th></tr></thead><tbody>{resistance_rows}</tbody></table>
      </section>
      <section class="span-6">
        <h2>纸上动作</h2>
        {_render_metrics(result["paper_action"])}
      </section>
      <section class="span-6">
        <h2>盘口摘要</h2>
        {_render_metrics(result["order_book"])}
      </section>
      <section class="span-12">
        <h2>风险事件</h2>
        <table><thead><tr><th>级别</th><th>来源</th><th>标题</th></tr></thead><tbody>{event_rows}</tbody></table>
      </section>
      <section class="span-12">
        <h2>数据源错误</h2>
        {source_errors}
      </section>
    </div>
  </main>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")


def _fetch_or_load_candles(
    config: AgentConfig,
    *,
    source: str,
    limit: int,
    cache_csv: str | Path | None,
) -> tuple[list[Candle], str, dict[str, str]]:
    errors: dict[str, str] = {}
    for candidate in _source_order(source):
        try:
            candles = _fetch_candles_from_source(candidate, config.symbol, config.interval, limit)
            if cache_csv:
                save_candles_csv(cache_csv, candles)
            return candles, candidate, errors
        except Exception as exc:
            errors[candidate] = _format_error(exc)

    if cache_csv and Path(cache_csv).exists():
        return load_csv(cache_csv), f"cache:{cache_csv}", errors

    detail = "; ".join(f"{name}: {message}" for name, message in errors.items())
    raise RuntimeError(f"All candle sources failed. {detail}")


def _source_order(source: str) -> list[str]:
    supported = ("okx", "binance", "coinbase")
    normalized = source.lower().strip()
    if normalized in {"", "auto"}:
        return list(supported)
    if normalized not in supported:
        raise ValueError("source must be auto, okx, binance, or coinbase.")
    return [normalized, *[item for item in supported if item != normalized]]


def _fetch_candles_from_source(
    source: str,
    symbol: str,
    interval: str,
    limit: int,
) -> list[Candle]:
    if source == "okx":
        return fetch_okx_candles(symbol, interval, limit)
    if source == "binance":
        return fetch_binance_klines(symbol, interval, limit)
    return fetch_coinbase_candles(_coinbase_product(symbol), interval, limit)


def _coinbase_product(symbol: str) -> str:
    normalized = symbol.upper()
    if "-" in normalized:
        return normalized
    if normalized.endswith("USDT"):
        return normalized[:-4] + "-USD"
    if normalized.endswith("USD"):
        return normalized[:-3] + "-USD"
    return normalized


def _cluster_levels(prices: list[float], latest_price: float) -> list[dict[str, Any]]:
    if not prices:
        return []
    tolerance = max(latest_price * 0.0025, 1e-9)
    clusters: list[list[float]] = []
    for price in sorted(prices):
        if not clusters or abs(price - (sum(clusters[-1]) / len(clusters[-1]))) > tolerance:
            clusters.append([price])
        else:
            clusters[-1].append(price)

    levels: list[dict[str, Any]] = []
    for cluster in clusters:
        price = sum(cluster) / len(cluster)
        distance_pct = ((price - latest_price) / latest_price) * 100 if latest_price else 0.0
        levels.append(
            {
                "price": round(price, 4),
                "distance_pct": round(distance_pct, 4),
                "touches": len(cluster),
            }
        )
    return sorted(levels, key=lambda item: item["touches"], reverse=True)


def _largest_wall(levels: list[OrderBookLevel]) -> dict[str, float] | None:
    if not levels:
        return None
    wall = max(levels, key=lambda item: item.notional)
    return {
        "price": round(wall.price, 4),
        "quantity": round(wall.quantity, 6),
        "notional": round(wall.notional, 2),
    }


def _render_card(title: str, value: object, notes: list[str]) -> str:
    notes_html = "".join(f"<li>{_escape(note)}</li>" for note in notes if note)
    if not notes_html:
        notes_html = "<li>暂无补充说明。</li>"
    return f"""
      <section class="span-4">
        <h3>{_escape(title)}</h3>
        <p class="value">{_escape(value)}</p>
        <ul>{notes_html}</ul>
      </section>
    """


def _render_level_rows(levels: list[dict[str, Any]]) -> str:
    if not levels:
        return "<tr><td colspan=\"3\">暂无可用价位。</td></tr>"
    return "".join(
        "<tr>"
        f"<td>{_escape(level['price'])}</td>"
        f"<td>{_escape(level['distance_pct'])}%</td>"
        f"<td>{_escape(level['touches'])}</td>"
        "</tr>"
        for level in levels
    )


def _render_event_rows(events: list[dict[str, Any]]) -> str:
    if not events:
        return "<tr><td colspan=\"3\">暂无新闻事件。</td></tr>"
    return "".join(
        "<tr>"
        f"<td>{_escape(event.get('severity', '-'))}</td>"
        f"<td>{_escape(event.get('source', '-'))}</td>"
        f"<td><a href=\"{_escape(event.get('link', ''))}\">{_escape(event.get('title', '-'))}</a></td>"
        "</tr>"
        for event in events
    )


def _render_metrics(payload: dict[str, Any]) -> str:
    rows: list[str] = []
    for key, value in payload.items():
        if isinstance(value, (list, dict)):
            continue
        rows.append(
            f"<div class=\"metric\"><span>{_escape(key)}</span><strong>{_escape(value)}</strong></div>"
        )
    return "".join(rows) or "<p class=\"muted\">暂无数据。</p>"


def _render_source_errors(errors: dict[str, Any]) -> str:
    flat: list[str] = []
    for group, items in errors.items():
        if isinstance(items, dict):
            for source, message in items.items():
                flat.append(f"{group}/{source}: {message}")
    if not flat:
        return "<p class=\"muted\">主要数据源获取正常。</p>"
    return "<ul>" + "".join(f"<li class=\"warning\">{_escape(item)}</li>" for item in flat) + "</ul>"


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _format_error(exc: BaseException) -> str:
    message = str(exc).strip()
    return message if message else exc.__class__.__name__


def snapshot_to_dict(value: object) -> dict[str, Any]:
    return asdict(value)
