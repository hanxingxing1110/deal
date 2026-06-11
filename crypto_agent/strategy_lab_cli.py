from __future__ import annotations

import argparse
import json

from crypto_agent.config import load_config
from crypto_agent.strategy_lab import (
    render_strategy_lab_report,
    run_timeframe_experiment,
    save_strategy_lab_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crypto trading agent strategy lab")
    parser.add_argument("--config", default="config.example.json")
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--output", default="runs/strategy_lab_result.json")
    parser.add_argument("--report", default="runs/strategy_lab_report.html")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    result = run_timeframe_experiment(config, days=args.days)

    save_strategy_lab_json(result, args.output)
    render_strategy_lab_report(result, args.report)

    summary = {
        "symbol": result["symbol"],
        "days": result["days"],
        "timeframes": {
            key: {
                "return_pct": value["return_pct"],
                "max_drawdown_pct": value["max_drawdown_pct"],
                "total_trades": value["total_trades"],
                "win_rate_pct": value["win_rate_pct"],
                "total_fees": value["total_fees"],
                "data_quality": value["data_quality"]["status"],
            }
            for key, value in result["timeframes"].items()
        },
        "report": args.report,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
