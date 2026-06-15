from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from crypto_agent.strategy import StrategyParams


@dataclass(frozen=True)
class StrategyProfile:
    id: str
    name: str
    description: str
    params: StrategyParams


PROFILES = [
    StrategyProfile(
        id="win_rate_60_v1",
        name="60%胜率目标 v1",
        description="以提高胜率为第一目标，采用更近止盈和更宽止损，适合作为研究候选，不代表实盘承诺。",
        params=StrategyParams(
            long_rsi_min=40,
            long_rsi_max=66,
            short_rsi_min=32,
            short_rsi_max=60,
            score_rsi_min=40,
            score_rsi_max=68,
            atr_pct_max=2.2,
            min_ema_gap_pct=0.03,
            min_sma_gap_pct=0.01,
            min_trend_efficiency=0.08,
            stop_atr_mult=1.4,
            target_atr_mult=1.0,
        ),
    ),
    StrategyProfile(
        id="high_win_rate_v1",
        name="胜率优先 v1",
        description="更严格过滤震荡、过热和弱趋势，只保留更干净的趋势信号，目标是提高历史胜率。",
        params=StrategyParams(
            long_rsi_min=42,
            long_rsi_max=66,
            short_rsi_min=34,
            short_rsi_max=58,
            score_rsi_min=40,
            score_rsi_max=68,
            atr_pct_max=1.7,
            min_ema_gap_pct=0.06,
            min_sma_gap_pct=0.03,
            min_trend_efficiency=0.14,
            stop_atr_mult=1.1,
            target_atr_mult=1.8,
            breakeven_at_r=0.75,
            trailing_start_r=1.1,
            trailing_atr_mult=0.85,
            hourly_min_ema_gap_pct=0.03,
            hourly_min_trend_efficiency=0.1,
            hourly_long_rsi_max=70,
            hourly_short_rsi_min=30,
        ),
    ),
    StrategyProfile(
        id="balanced_v1",
        name="平衡趋势 v1",
        description="默认研究策略，兼顾趋势、RSI、ATR 和技术共振。",
        params=StrategyParams(),
    ),
    StrategyProfile(
        id="strict_trend_v1",
        name="严格趋势 v1",
        description="提高趋势强度和确认要求，减少震荡期交易。",
        params=StrategyParams(
            min_ema_gap_pct=0.035,
            min_sma_gap_pct=0.025,
            min_trend_efficiency=0.18,
            min_volume_ratio=0.95,
            hourly_min_ema_gap_pct=0.025,
            hourly_min_trend_efficiency=0.15,
            breakeven_at_r=1.0,
            trailing_start_r=1.5,
            trailing_atr_mult=1.2,
        ),
    ),
    StrategyProfile(
        id="conservative_risk_v1",
        name="保守风控 v1",
        description="降低波动容忍度并提前移动止损，更适合模拟盘观察。",
        params=StrategyParams(
            atr_pct_max=1.8,
            long_rsi_max=64,
            short_rsi_min=36,
            stop_atr_mult=1.2,
            target_atr_mult=2.0,
            breakeven_at_r=0.8,
            trailing_start_r=1.2,
            trailing_atr_mult=0.9,
        ),
    ),
]


def list_profiles() -> list[dict[str, Any]]:
    return [
        {
            "id": profile.id,
            "name": profile.name,
            "description": profile.description,
            "params": asdict(profile.params),
        }
        for profile in PROFILES
    ]


def get_profile(profile_id: str | None) -> StrategyProfile:
    if not profile_id:
        return PROFILES[0]
    for profile in PROFILES:
        if profile.id == profile_id:
            return profile
    return PROFILES[0]
