from __future__ import annotations

import argparse
import json

from crypto_agent.prepare_data import (
    prepare_market_data,
    prepare_sample_market_data,
    render_prepare_data_report,
    save_prepare_data_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare crypto market data")
    parser.add_argument("--source", choices=["sample", "csv"], default="sample")
    parser.add_argument("--input-csv", default=None)
    parser.add_argument("--output-15m", default="data/prepared_15m.csv")
    parser.add_argument("--output-1h", default="data/prepared_1h.csv")
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--output", default="runs/prepare_data_result.json")
    parser.add_argument("--report", default="runs/prepare_data_report.html")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.source == "sample":
        result = prepare_sample_market_data(
            output_15m=args.output_15m,
            output_1h=args.output_1h,
            days=args.days,
        )
    else:
        if not args.input_csv:
            raise SystemExit("--input-csv is required when --source csv is used")
        result = prepare_market_data(
            input_csv=args.input_csv,
            output_15m=args.output_15m,
            output_1h=args.output_1h,
        )
        result["data_source"] = "csv"

    save_prepare_data_json(result, args.output)
    render_prepare_data_report(result, args.report)

    summary = {
        key: value
        for key, value in result.items()
        if key not in {"quality_15m", "quality_1h"}
    }
    summary["quality_15m_status"] = result["quality_15m"]["status"]
    summary["quality_1h_status"] = result["quality_1h"]["status"]
    summary["report"] = args.report
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
