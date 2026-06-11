from __future__ import annotations

import argparse
import json

from crypto_agent.config import load_config
from crypto_agent.walk_forward import (
    render_walk_forward_report,
    run_walk_forward_csv,
    run_walk_forward_sample,
    save_walk_forward_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crypto walk-forward robustness report")
    parser.add_argument("--config", default="config.example.json")
    parser.add_argument("--source", choices=["sample", "csv"], default="sample")
    parser.add_argument("--csv-15m", default=None)
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--segment-days", type=int, default=14)
    parser.add_argument("--output", default="runs/walk_forward_result.json")
    parser.add_argument("--report", default="runs/walk_forward_report.html")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)

    if args.source == "csv":
        if not args.csv_15m:
            raise SystemExit("--csv-15m is required when --source csv is used")
        result = run_walk_forward_csv(
            config,
            csv_15m=args.csv_15m,
            segment_days=args.segment_days,
        )
    else:
        result = run_walk_forward_sample(
            config,
            days=args.days,
            segment_days=args.segment_days,
        )

    save_walk_forward_json(result, args.output)
    render_walk_forward_report(result, args.report)

    summary = {key: value for key, value in result.items() if key != "segments"}
    summary["report"] = args.report
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
