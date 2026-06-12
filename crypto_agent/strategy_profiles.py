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
