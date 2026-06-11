from __future__ import annotations

from dataclasses import dataclass

from crypto_agent.config import AgentConfig
from crypto_agent.strategy import TradeSignal


@dataclass(frozen=True)
class RiskReview:
    risk_score: int
    allowed: bool
    blocks: list[str]


def score_market_risk(indicators: dict[str, float], signal: TradeSignal) -> int:
    score = 20
    atr_pct = indicators["atr_pct"]
    rsi_14 = indicators["rsi_14"]

    if atr_pct > 1.5:
        score += 15
    if atr_pct > 3.0:
        score += 20
    if rsi_14 > 72 or rsi_14 < 28:
        score += 15
    if signal.confidence < 0.55:
        score += 15
    if signal.decision == "SHORT":
        score += 10

    return max(0, min(100, score))


def review_signal(
    config: AgentConfig,
    indicators: dict[str, float],
    signal: TradeSignal,
) -> RiskReview:
    blocks: list[str] = []
    risk_score = score_market_risk(indicators, signal)

    if signal.decision == "HOLD":
        blocks.append("当前信号是 HOLD，不生成交易计划。")
    if signal.confidence < config.min_confidence:
        blocks.append(
            f"信号置信度 {signal.confidence:.2f} 低于阈值 {config.min_confidence:.2f}。"
        )
    if risk_score > config.max_risk_score:
        blocks.append(f"风险分数 {risk_score} 高于上限 {config.max_risk_score}。")
    if signal.decision == "SHORT" and not config.allow_short:
        blocks.append("配置禁止做空，第一版默认只做现货方向。")

    return RiskReview(
        risk_score=risk_score,
        allowed=not blocks,
        blocks=blocks,
    )
