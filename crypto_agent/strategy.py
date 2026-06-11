from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TradeSignal:
    decision: str
    confidence: float
    entry: float | None
    stop_loss: float | None
    take_profit: float | None
    reasons: list[str]


@dataclass(frozen=True)
class StrategyParams:
    enable_long: bool = True
    enable_short: bool = True
    long_rsi_min: float = 38.0
    long_rsi_max: float = 68.0
    short_rsi_min: float = 30.0
    short_rsi_max: float = 100.0
    score_rsi_min: float = 38.0
    score_rsi_max: float = 68.0
    atr_pct_min: float = 0.0
    atr_pct_max: float = 2.5
    min_ema_gap_pct: float = 0.0
    min_sma_gap_pct: float = 0.0
    min_trend_efficiency: float = 0.0
    min_volume_ratio: float = 0.0
    min_range_atr_ratio: float = 0.0
    min_long_3d_return_pct: float = -999.0
    max_short_3d_return_pct: float = 999.0
    stop_atr_mult: float = 1.5
    target_atr_mult: float = 2.5
    breakeven_at_r: float = 0.0
    trailing_start_r: float = 0.0
    trailing_atr_mult: float = 1.0
    hourly_min_ema_gap_pct: float = 0.0
    hourly_min_sma_gap_pct: float = 0.0
    hourly_min_trend_efficiency: float = 0.0
    hourly_long_rsi_max: float = 75.0
    hourly_short_rsi_min: float = 25.0


def build_signal(
    indicators: dict[str, float],
    allow_short: bool = False,
    params: StrategyParams | None = None,
    technicals: dict | None = None,
) -> TradeSignal:
    params = params or StrategyParams()
    close = indicators["close"]
    ema_12 = indicators["ema_12"]
    ema_26 = indicators["ema_26"]
    sma_20 = indicators["sma_20"]
    rsi_14 = indicators["rsi_14"]
    atr_14 = indicators["atr_14"]
    atr_pct = indicators["atr_pct"]
    trend_efficiency_20 = indicators.get("trend_efficiency_20", 0.0)
    volume_ratio_20 = indicators.get("volume_ratio_20", 1.0)
    range_atr_ratio = indicators.get("range_atr_ratio", 0.0)
    return_3d_pct = indicators.get("return_3d_pct", 0.0)
    ema_gap_pct = (abs(ema_12 - ema_26) / close) * 100 if close else 0.0
    sma_gap_pct = (abs(close - sma_20) / close) * 100 if close else 0.0

    trend_strength_ok = (
        ema_gap_pct >= params.min_ema_gap_pct
        and sma_gap_pct >= params.min_sma_gap_pct
        and trend_efficiency_20 >= params.min_trend_efficiency
    )
    confirmation_checks = [
        params.min_volume_ratio > 0 and volume_ratio_20 >= params.min_volume_ratio,
        params.min_range_atr_ratio > 0 and range_atr_ratio >= params.min_range_atr_ratio,
    ]
    needs_confirmation = params.min_volume_ratio > 0 or params.min_range_atr_ratio > 0
    confirmation_ok = not needs_confirmation or any(confirmation_checks)
    volatility_ok = params.atr_pct_min <= atr_pct <= params.atr_pct_max
    bullish_trend = ema_12 > ema_26 and close > sma_20 and trend_strength_ok
    bearish_trend = ema_12 < ema_26 and close < sma_20 and trend_strength_ok
    long_context_ok = return_3d_pct >= params.min_long_3d_return_pct
    short_context_ok = return_3d_pct <= params.max_short_3d_return_pct
    long_momentum_ok = params.long_rsi_min <= rsi_14 <= params.long_rsi_max
    short_momentum_ok = params.short_rsi_min <= rsi_14 <= params.short_rsi_max
    score_momentum_ok = params.score_rsi_min <= rsi_14 <= params.score_rsi_max
    overbought = rsi_14 > 72
    oversold = rsi_14 < 30

    reasons: list[str] = []
    score = 0.30
    technical_score = 0.0
    technical_notes: list[str] = []
    if technicals:
        technical_score = float(technicals.get("score") or 0.0)
        technical_notes = [
            str(note)
            for note in technicals.get("notes", [])
            if str(note).strip()
        ][:4]

    if bullish_trend:
        score += 0.30
        reasons.append("短期均线强于中期均线，且价格在 20 周期均线上方。")
    elif bearish_trend:
        score += 0.18
        reasons.append("短期均线弱于中期均线，价格在 20 周期均线下方。")
    else:
        reasons.append("趋势方向不够清晰。")

    if trend_strength_ok:
        reasons.append("均线差距达到趋势强度要求。")
    else:
        score -= 0.10
        reasons.append("均线差距偏小，可能处于震荡区。")

    if score_momentum_ok:
        score += 0.18
        reasons.append("RSI 处于相对健康区间，没有明显过热或过冷。")
    elif overbought:
        score -= 0.12
        reasons.append("RSI 偏高，追涨风险增加。")
    elif oversold:
        score -= 0.05
        reasons.append("RSI 偏低，可能反弹，但也可能处于下跌惯性。")

    if atr_14 > 0 and volatility_ok:
        score += 0.10
        reasons.append("ATR 占比可控，波动没有明显失控。")
    else:
        score -= 0.10
        reasons.append("ATR 占比不在策略允许区间，当前波动环境不理想。")

    if needs_confirmation and confirmation_ok:
        score += 0.04
        reasons.append("成交量或单根K线波动达到确认要求。")
    elif needs_confirmation:
        score -= 0.12
        reasons.append("成交量和单根K线波动都没有确认突破力度。")

    if long_context_ok or short_context_ok:
        reasons.append("3天滚动收益满足大周期方向过滤。")
    else:
        score -= 0.08
        reasons.append("3天滚动收益不满足大周期方向过滤。")

    if technicals:
        score += max(-0.12, min(0.12, technical_score * 0.12))
        reasons.extend(technical_notes)
        if technical_score > 0.2:
            reasons.append("多组 K 线技术工具出现偏多共振。")
        elif technical_score < -0.2:
            reasons.append("多组 K 线技术工具出现偏空共振。")
        else:
            reasons.append("K 线技术工具共振不明显。")

    confidence = max(0.0, min(0.95, score))

    if (
        params.enable_long
        and bullish_trend
        and long_momentum_ok
        and volatility_ok
        and confirmation_ok
        and long_context_ok
        and technical_score >= -0.35
    ):
        stop = close - params.stop_atr_mult * atr_14
        target = close + params.target_atr_mult * atr_14
        return TradeSignal(
            decision="LONG",
            confidence=round(confidence, 3),
            entry=round(close, 2),
            stop_loss=round(stop, 2),
            take_profit=round(target, 2),
            reasons=reasons,
        )

    if (
        params.enable_short
        and allow_short
        and bearish_trend
        and short_momentum_ok
        and volatility_ok
        and confirmation_ok
        and short_context_ok
        and technical_score <= 0.35
    ):
        stop = close + params.stop_atr_mult * atr_14
        target = close - params.target_atr_mult * atr_14
        return TradeSignal(
            decision="SHORT",
            confidence=round(confidence, 3),
            entry=round(close, 2),
            stop_loss=round(stop, 2),
            take_profit=round(target, 2),
            reasons=reasons,
        )

    reasons.append("第一版没有出现足够干净的入场条件，保持观望。")
    return TradeSignal(
        decision="HOLD",
        confidence=round(confidence, 3),
        entry=None,
        stop_loss=None,
        take_profit=None,
        reasons=reasons,
    )
