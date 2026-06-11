from __future__ import annotations

import argparse
import json

from crypto_agent.config import load_config
from crypto_agent.exit_management import (
    render_exit_validation_report,
    run_cached_binance_exit_validation,
    save_exit_validation_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate dynamic exit management")
    parser.add_argument("--config", default="config.example.json")
    parser.add_argument(
        "--csv-15m",
        default="data/real_binance_btcusdt_15m_6000_latest.csv",
    )
    parser.add_argument(
        "--base-params-json",
        default="runs/binance_strategy_optimization_context_result.json",
    )
    parser.add_argument("--segment-days", type=int, default=7)
    parser.add_argument(
        "--output",
        default="runs/binance_exit_management_result.json",
    )
    parser.add_argument(
        "--report",
        default="runs/binance_exit_management_report.html",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    result = run_cached_binance_exit_validation(
        config,
        csv_15m=args.csv_15m,
        base_params_json=args.base_params_json,
        segment_days=args.segment_days,
    )
    save_exit_validation_json(result, args.output)
    render_exit_validation_report(result, args.report)
    summary = {key: value for key, value in result.items() if key not in {"candidates", "segmented"}}
    summary["report"] = args.report
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
