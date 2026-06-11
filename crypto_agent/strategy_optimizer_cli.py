from __future__ import annotations

import argparse
import json

from crypto_agent.config import load_config
from crypto_agent.strategy_optimizer import (
    render_optimization_report,
    run_binance_strategy_optimization,
    save_optimization_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Optimize the Binance dual-timeframe strategy")
    parser.add_argument("--config", default="config.example.json")
    parser.add_argument("--candle-limit", type=int, default=3000)
    parser.add_argument("--train-ratio", type=float, default=0.7)
    parser.add_argument(
        "--output",
        default="runs/binance_strategy_optimization_result.json",
    )
    parser.add_argument(
        "--report",
        default="runs/binance_strategy_optimization_report.html",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    result = run_binance_strategy_optimization(
        config,
        candle_limit=args.candle_limit,
        train_ratio=args.train_ratio,
    )

    save_optimization_json(result, args.output)
    render_optimization_report(result, args.report)

    summary = {key: value for key, value in result.items() if key != "top_candidates"}
    summary["report"] = args.report
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
