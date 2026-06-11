from __future__ import annotations

from dataclasses import asdict
from typing import Any

from crypto_agent.config import AgentConfig
from crypto_agent.indicators import latest_indicator_snapshot
from crypto_agent.market_data import Candle
from crypto_agent.paper_trading import PaperOrder, build_paper_order
from crypto_agent.risk import review_signal
from crypto_agent.strategy import build_signal
from crypto_agent.technical_analysis import build_technical_snapshot


def analyze_market(
    config: AgentConfig,
    candles: list[Candle],
) -> tuple[dict[str, Any], PaperOrder | None]:
    if len(candles) < 30:
        raise ValueError("Need at least 30 candles to analyze the market.")

    indicators = latest_indicator_snapshot(candles)
    technicals = build_technical_snapshot(candles)
    signal = build_signal(
        indicators,
        allow_short=config.allow_short,
        technicals=technicals,
    )
    review = review_signal(config, indicators, signal)
    order = build_paper_order(config, signal) if review.allowed else None
    latest = candles[-1]

    result: dict[str, Any] = {
        "symbol": config.symbol,
        "interval": config.interval,
        "latest_candle_time": latest.timestamp,
        "decision": signal.decision,
        "confidence": signal.confidence,
        "risk_score": review.risk_score,
        "risk_allowed": review.allowed,
        "risk_blocks": review.blocks,
        "indicators": {key: round(value, 4) for key, value in indicators.items()},
        "technicals": technicals,
        "trade_plan": {
            "entry": signal.entry,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
        },
        "paper_order": asdict(order) if order else None,
        "reasons": signal.reasons,
    }
    return result, order
