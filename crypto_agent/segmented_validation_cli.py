from __future__ import annotations

import argparse
import json

from crypto_agent.config import load_config
from crypto_agent.segmented_validation import (
    render_segmented_validation_report,
    run_cached_binance_segmented_validation,
    save_segmented_validation_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Segmented strategy validation")
    parser.add_argument("--config", default="config.example.json")
    parser.add_argument(
        "--csv-15m",
        default="data/real_binance_btcusdt_15m_6000_latest.csv",
    )
    parser.add_argument(
        "--optimization-json",
        default="runs/binance_strategy_optimization_confirmation_result.json",
    )
    parser.add_argument(
        "--confirmation-json",
        default="runs/binance_strategy_confirmation_candidate_result.json",
    )
    parser.add_argument(
        "--context-json",
        default="runs/binance_strategy_context_candidate_result.json",
    )
    parser.add_argument("--segment-days", type=int, default=7)
    parser.add_argument(
        "--output",
        default="runs/binance_segmented_strategy_validation_result.json",
    )
    parser.add_argument(
        "--report",
        default="runs/binance_segmented_strategy_validation_report.html",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    result = run_cached_binance_segmented_validation(
        config,
        csv_15m=args.csv_15m,
        optimization_json=args.optimization_json,
        confirmation_json=args.confirmation_json,
        context_json=args.context_json,
        segment_days=args.segment_days,
    )
    save_segmented_validation_json(result, args.output)
    render_segmented_validation_report(result, args.report)
    summary = {key: value for key, value in result.items() if key != "strategies"}
    summary["report"] = args.report
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
