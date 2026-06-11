from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from crypto_agent.agent import analyze_market
from crypto_agent.config import load_config
from crypto_agent.dashboard import render_dashboard
from crypto_agent.market_data import (
    fetch_binance_klines,
    fetch_coinbase_candles,
    generate_sample_candles,
    load_csv,
    save_sample_csv,
)
from crypto_agent.paper_trading import append_order


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crypto trading agent MVP")
    parser.add_argument("--config", default="config.example.json")
    parser.add_argument(
        "--source",
        choices=["sample", "csv", "binance", "coinbase"],
        default="sample",
    )
    parser.add_argument("--csv", default=None, help="CSV path when --source csv is used")
    parser.add_argument("--paper-trade", action="store_true")
    parser.add_argument("--fallback-sample", action="store_true")
    parser.add_argument("--output", default="runs/latest_signal.json")
    parser.add_argument("--ledger", default="runs/paper_ledger.jsonl")
    parser.add_argument("--dashboard", default="runs/dashboard.html")
    parser.add_argument("--no-dashboard", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    source = args.source
    source_warning = None

    if args.source == "sample":
        sample_path = Path(config.sample_csv)
        if sample_path.exists():
            candles = load_csv(sample_path)
        else:
            save_sample_csv(sample_path, config.candle_limit)
            candles = generate_sample_candles(config.candle_limit)
    elif args.source == "csv":
        if not args.csv:
            raise SystemExit("--csv is required when --source csv is used")
        candles = load_csv(args.csv)
    elif args.source == "binance":
        try:
            candles = fetch_binance_klines(
                symbol=config.symbol,
                interval=config.interval,
                limit=config.candle_limit,
            )
        except Exception as exc:
            if not args.fallback_sample:
                raise SystemExit(
                    f"Binance public market data failed: {exc}. "
                    "Try run_sample.ps1, run_coinbase.ps1, or add --fallback-sample."
                )
            source = "sample_fallback"
            source_warning = f"Binance public market data failed, used sample data: {exc}"
            print(source_warning, file=sys.stderr)
            candles = _load_or_create_sample(config)
    else:
        try:
            candles = fetch_coinbase_candles(
                product_id=config.coinbase_product_id,
                interval=config.interval,
                limit=config.candle_limit,
            )
        except Exception as exc:
            if not args.fallback_sample:
                raise SystemExit(
                    f"Coinbase public market data failed: {exc}. "
                    "Try run_sample.ps1 or add --fallback-sample."
                )
            source = "sample_fallback"
            source_warning = f"Coinbase public market data failed, used sample data: {exc}"
            print(source_warning, file=sys.stderr)
            candles = _load_or_create_sample(config)

    result, order = analyze_market(config, candles)
    result["data_source"] = source
    if source_warning:
        result["source_warning"] = source_warning
    if not args.no_dashboard:
        result["dashboard"] = args.dashboard

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if args.paper_trade and order:
        append_order(args.ledger, order)

    if not args.no_dashboard:
        render_dashboard(result, args.dashboard)

    print(json.dumps(result, ensure_ascii=False, indent=2))


def _load_or_create_sample(config) -> list:
    sample_path = Path(config.sample_csv)
    if sample_path.exists():
        return load_csv(sample_path)
    save_sample_csv(sample_path, config.candle_limit)
    return generate_sample_candles(config.candle_limit)


if __name__ == "__main__":
    main()
