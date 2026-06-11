from __future__ import annotations

import argparse
import json

from crypto_agent.config import load_config
from crypto_agent.direction_validation import (
    render_direction_validation_report,
    run_binance_direction_validation,
    save_direction_validation_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate long-only vs short-only strategy")
    parser.add_argument("--config", default="config.example.json")
    parser.add_argument("--candle-limit", type=int, default=3000)
    parser.add_argument(
        "--base-params-json",
        default="runs/binance_strategy_optimization_context_result.json",
    )
    parser.add_argument(
        "--output",
        default="runs/binance_direction_validation_result.json",
    )
    parser.add_argument(
        "--report",
        default="runs/binance_direction_validation_report.html",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    result = run_binance_direction_validation(
        config,
        candle_limit=args.candle_limit,
        base_params_json=args.base_params_json,
    )
    save_direction_validation_json(result, args.output)
    render_direction_validation_report(result, args.report)
    summary = {key: value for key, value in result.items() if key != "strategies"}
    summary["report"] = args.report
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
