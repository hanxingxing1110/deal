from __future__ import annotations

import json
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AgentConfig:
    symbol: str = "BTCUSDT"
    coinbase_product_id: str = "BTC-USD"
    interval: str = "1h"
    candle_limit: int = 120
    starting_cash: float = 10_000.0
    risk_per_trade: float = 0.01
    max_position_usd: float = 1_000.0
    fee_bps: float = 10.0
    min_confidence: float = 0.55
    max_risk_score: int = 65
    allow_short: bool = False
    sample_csv: str = "data/sample_btcusdt_1h.csv"


def load_config(path: str | Path) -> AgentConfig:
    config_path = Path(path)
    if not config_path.exists():
        return AgentConfig()

    raw: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))
    allowed = {field.name for field in fields(AgentConfig)}
    filtered = {key: value for key, value in raw.items() if key in allowed}
    return AgentConfig(**filtered)
