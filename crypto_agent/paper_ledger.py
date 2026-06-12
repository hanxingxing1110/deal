from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LEDGER_PATH = Path("runs/trading_desk_ledger.jsonl")


@dataclass(frozen=True)
class LedgerEntry:
    created_at: str
    symbol: str
    interval: str
    market_source: str
    source: str
    side: str
    price: float
    quantity: float
    note: str
    candle_time: int | None = None


def build_ledger_entry(payload: dict[str, Any]) -> LedgerEntry:
    return LedgerEntry(
        created_at=str(payload.get("created_at") or datetime.now(timezone.utc).isoformat()),
        symbol=str(payload.get("symbol") or "BTCUSDT").upper(),
        interval=str(payload.get("interval") or "15m"),
        market_source=str(payload.get("market_source") or payload.get("marketSource") or "unknown"),
        source=str(payload.get("source") or "manual"),
        side=str(payload.get("side") or "HOLD").upper(),
        price=_float(payload.get("price")),
        quantity=_float(payload.get("quantity")),
        note=str(payload.get("note") or ""),
        candle_time=_optional_int(payload.get("candle_time") or payload.get("candleTime")),
    )


def append_ledger_entry(payload: dict[str, Any], path: str | Path = LEDGER_PATH) -> LedgerEntry:
    entry = build_ledger_entry(payload)
    ledger_path = Path(path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry.__dict__, ensure_ascii=False) + "\n")
    return entry


def read_ledger(path: str | Path = LEDGER_PATH, limit: int = 500) -> list[dict[str, Any]]:
    ledger_path = Path(path)
    if not ledger_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with ledger_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-limit:]


def clear_ledger(path: str | Path = LEDGER_PATH) -> None:
    ledger_path = Path(path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text("", encoding="utf-8")


def summarize_ledger(entries: list[dict[str, Any]]) -> dict[str, Any]:
    closed_like = [entry for entry in entries if entry.get("side") in {"LONG", "SHORT"}]
    by_side = {
        "LONG": sum(1 for entry in closed_like if entry.get("side") == "LONG"),
        "SHORT": sum(1 for entry in closed_like if entry.get("side") == "SHORT"),
        "HOLD": sum(1 for entry in entries if entry.get("side") == "HOLD"),
    }
    notional = sum(
        abs(_float(entry.get("price")) * _float(entry.get("quantity")))
        for entry in closed_like
    )
    return {
        "total": len(entries),
        "trade_like_total": len(closed_like),
        "by_side": by_side,
        "notional_usd": round(notional, 2),
        "latest": entries[-1] if entries else None,
        "storage": str(Path(LEDGER_PATH)),
    }


def _float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _optional_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
