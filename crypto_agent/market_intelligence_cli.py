from __future__ import annotations

import argparse
import json

from crypto_agent.config import load_config
from crypto_agent.market_intelligence import (
    render_market_intelligence_report,
    run_market_intelligence,
    save_market_intelligence_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a crypto market intelligence report")
    parser.add_argument("--config", default="config.example.json")
    parser.add_argument("--source", default="auto", choices=["auto", "okx", "binance", "coinbase"])
    parser.add_argument("--candle-limit", type=int, default=1000)
    parser.add_argument("--order-book-limit", type=int, default=100)
    parser.add_argument("--news-limit", type=int, default=8)
    parser.add_argument(
        "--cache-csv",
        default="data/market_intelligence_latest.csv",
    )
    parser.add_argument(
        "--output",
        default="runs/market_intelligence_result.json",
    )
    parser.add_argument(
        "--report",
        default="runs/market_intelligence_report.html",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    result = run_market_intelligence(
        config,
        source=args.source,
        candle_limit=args.candle_limit,
        order_book_limit=args.order_book_limit,
        cache_csv=args.cache_csv,
        news_limit=args.news_limit,
    )
    save_market_intelligence_json(result, args.output)
    render_market_intelligence_report(result, args.report)

    summary = {
        "symbol": result["symbol"],
        "interval": result["interval"],
        "candle_source": result["candle_source"],
        "latest_price": result["latest_price"],
        "trend": result["trend"]["direction"],
        "volatility": result["volatility"]["state"],
        "trade_view": result["trade_view"],
        "paper_action": {
            key: result["paper_action"][key]
            for key in ("decision", "confidence", "entry", "stop_loss", "take_profit")
        },
        "report": args.report,
        "output": args.output,
        "source_errors": result.get("source_errors", {}),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
