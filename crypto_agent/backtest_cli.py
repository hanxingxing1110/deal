from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from crypto_agent.backtest import (
    render_backtest_report,
    run_backtest,
    save_backtest_json,
)
from crypto_agent.config import AgentConfig, load_config
from crypto_agent.market_data import (
    fetch_binance_klines,
    fetch_coinbase_candles,
    generate_research_sample_candles,
    generate_sample_candles,
    load_csv,
    save_research_sample_csv,
    save_sample_csv,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crypto trading agent backtest")
    parser.add_argument("--config", default="config.example.json")
    parser.add_argument(
        "--source",
        choices=["sample", "long_sample", "csv", "binance", "coinbase"],
        default="sample",
    )
    parser.add_argument("--csv", default=None, help="CSV path when --source csv is used")
    parser.add_argument("--sample-count", type=int, default=1440)
    parser.add_argument("--sample-output", default="data/sample_btcusdt_1h_long.csv")
    parser.add_argument("--fallback-sample", action="store_true")
    parser.add_argument("--output", default="runs/backtest_result.json")
    parser.add_argument("--report", default="runs/backtest_report.html")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    candles, source, warning = _load_candles(args, config)

    result = run_backtest(config, candles)
    result["data_source"] = source
    if warning:
        result["source_warning"] = warning

    save_backtest_json(result, args.output)
    render_backtest_report(result, args.report)

    summary = {key: value for key, value in result.items() if key != "trades"}
    summary["report"] = args.report
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _load_candles(
    args: argparse.Namespace,
    config: AgentConfig,
) -> tuple[list, str, str | None]:
    if args.source == "sample":
        return _load_or_create_sample(config), "sample", None

    if args.source == "long_sample":
        candles = generate_research_sample_candles(args.sample_count)
        save_research_sample_csv(args.sample_output, args.sample_count)
        return candles, "long_sample", None

    if args.source == "csv":
        if not args.csv:
            raise SystemExit("--csv is required when --source csv is used")
        return load_csv(args.csv), "csv", None

    if args.source == "binance":
        try:
            return (
                fetch_binance_klines(config.symbol, config.interval, config.candle_limit),
                "binance",
                None,
            )
        except Exception as exc:
            return _fallback_or_exit(args, config, "Binance", exc)

    try:
        return (
            fetch_coinbase_candles(
                config.coinbase_product_id,
                config.interval,
                config.candle_limit,
            ),
            "coinbase",
            None,
        )
    except Exception as exc:
        return _fallback_or_exit(args, config, "Coinbase", exc)


def _fallback_or_exit(
    args: argparse.Namespace,
    config: AgentConfig,
    source_name: str,
    exc: Exception,
) -> tuple[list, str, str]:
    if not args.fallback_sample:
        raise SystemExit(
            f"{source_name} public market data failed: {exc}. "
            "Try run_sample.ps1 or add --fallback-sample."
        )
    warning = f"{source_name} public market data failed, used sample data: {exc}"
    print(warning, file=sys.stderr)
    return _load_or_create_sample(config), "sample_fallback", warning


def _load_or_create_sample(config: AgentConfig) -> list:
    sample_path = Path(config.sample_csv)
    if sample_path.exists():
        return load_csv(sample_path)
    save_sample_csv(sample_path, config.candle_limit)
    return generate_sample_candles(config.candle_limit)


if __name__ == "__main__":
    main()
