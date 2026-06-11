from __future__ import annotations

import argparse
import json

from crypto_agent.config import load_config
from crypto_agent.dual_timeframe import (
    run_dual_timeframe_backtest,
    render_dual_timeframe_report,
    run_sample_dual_timeframe_experiment,
    save_dual_timeframe_json,
)
from crypto_agent.market_data import load_csv, resample_candles, save_candles_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crypto dual-timeframe backtest")
    parser.add_argument("--config", default="config.example.json")
    parser.add_argument("--source", choices=["sample", "csv"], default="sample")
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--csv-15m", default=None)
    parser.add_argument("--csv-1h", default=None)
    parser.add_argument("--output", default="runs/dual_timeframe_result.json")
    parser.add_argument("--report", default="runs/dual_timeframe_report.html")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    if args.source == "sample":
        result = run_sample_dual_timeframe_experiment(config, days=args.days)
    else:
        if not args.csv_15m:
            raise SystemExit("--csv-15m is required when --source csv is used")
        candles_15m = load_csv(args.csv_15m)
        if args.csv_1h:
            candles_1h = load_csv(args.csv_1h)
            generated_1h = False
        else:
            candles_1h = resample_candles(candles_15m, 4)
            save_candles_csv("data/generated_1h_from_csv_15m.csv", candles_1h)
            generated_1h = True

        result = run_dual_timeframe_backtest(config, candles_15m, candles_1h)
        result["data_source"] = "csv"
        result["csv_15m"] = args.csv_15m
        result["csv_1h"] = args.csv_1h or "data/generated_1h_from_csv_15m.csv"
        result["generated_1h_from_15m"] = generated_1h

    save_dual_timeframe_json(result, args.output)
    render_dual_timeframe_report(result, args.report)

    summary = {key: value for key, value in result.items() if key != "trades"}
    summary["report"] = args.report
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
