from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from crypto_agent.config import AgentConfig
from crypto_agent.strategy import TradeSignal


@dataclass(frozen=True)
class PaperOrder:
    created_at: str
    symbol: str
    side: str
    entry: float
    stop_loss: float
    take_profit: float
    quantity: float
    notional_usd: float
    estimated_fee: float
    risk_amount: float


def build_paper_order(config: AgentConfig, signal: TradeSignal) -> PaperOrder | None:
    if signal.decision not in {"LONG", "SHORT"}:
        return None
    if signal.entry is None or signal.stop_loss is None or signal.take_profit is None:
        return None

    risk_budget = config.starting_cash * config.risk_per_trade
    risk_per_unit = abs(signal.entry - signal.stop_loss)
    if risk_per_unit <= 0:
        return None

    quantity_by_risk = risk_budget / risk_per_unit
    quantity_by_cap = config.max_position_usd / signal.entry
    quantity = min(quantity_by_risk, quantity_by_cap)
    notional = quantity * signal.entry
    fee = notional * (config.fee_bps / 10_000)

    return PaperOrder(
        created_at=datetime.now(timezone.utc).isoformat(),
        symbol=config.symbol,
        side=signal.decision,
        entry=round(signal.entry, 2),
        stop_loss=round(signal.stop_loss, 2),
        take_profit=round(signal.take_profit, 2),
        quantity=round(quantity, 8),
        notional_usd=round(notional, 2),
        estimated_fee=round(fee, 2),
        risk_amount=round(quantity * risk_per_unit, 2),
    )


def append_order(path: str | Path, order: PaperOrder) -> None:
    ledger_path = Path(path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(order), ensure_ascii=False) + "\n")
