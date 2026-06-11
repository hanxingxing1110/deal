from __future__ import annotations

import html
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from crypto_agent.config import AgentConfig
from crypto_agent.dual_timeframe import run_dual_timeframe_backtest
from crypto_agent.market_data import Candle, load_csv, resample_candles
from crypto_agent.strategy import StrategyParams


def run_segmented_strategy_validation(
    config: AgentConfig,
    candles_15m: list[Candle],
    strategies: dict[str, StrategyParams],
    segment_days: int = 7,
) -> dict[str, Any]:
    segment_size = segment_days * 24 * 4
    if segment_size < 160:
        raise ValueError("segment_days is too small for dual-timeframe validation.")
    if not strategies:
        raise ValueError("At least one strategy is required.")

    strategy_results = {
        name: {
            "params": asdict(params),
            "segments": [],
        }
        for name, params in strategies.items()
    }

    for segment_index, start in enumerate(range(0, len(candles_15m), segment_size), start=1):
        segment_15m = candles_15m[start : start + segment_size]
        if len(segment_15m) < segment_size:
            continue
        segment_1h = resample_candles(segment_15m, 4)
        if len(segment_1h) < 40:
            continue

        for name, params in strategies.items():
            backtest = run_dual_timeframe_backtest(config, segment_15m, segment_1h, params)
            normal_cost = _cost_case(backtest, "正常成本")
            severe_cost = _cost_case(backtest, "严苛成本")
            strategy_results[name]["segments"].append(
                {
                    "segment": segment_index,
                    "first_candle": segment_15m[0].timestamp,
                    "last_candle": segment_15m[-1].timestamp,
                    "return_pct": backtest["return_pct"],
                    "net_profit": backtest["net_profit"],
                    "max_drawdown_pct": backtest["max_drawdown_pct"],
                    "total_trades": backtest["total_trades"],
                    "win_rate_pct": backtest["win_rate_pct"],
                    "profit_factor": backtest["profit_factor"],
                    "long_trades": backtest["long_trades"],
                    "short_trades": backtest["short_trades"],
                    "normal_cost_return_pct": normal_cost.get("return_pct") if normal_cost else None,
                    "normal_cost_net_profit": normal_cost.get("net_profit") if normal_cost else None,
                    "severe_cost_return_pct": severe_cost.get("return_pct") if severe_cost else None,
                    "severe_cost_net_profit": severe_cost.get("net_profit") if severe_cost else None,
                }
            )

    for name, item in strategy_results.items():
        item["summary"] = _summarize_segments(item["segments"])

    comparison = _rank_strategies(strategy_results)
    return {
        "symbol": config.symbol,
        "segment_days": segment_days,
        "segment_count": max(
            (len(item["segments"]) for item in strategy_results.values()),
            default=0,
        ),
        "first_candle": candles_15m[0].timestamp if candles_15m else None,
        "last_candle": candles_15m[-1].timestamp if candles_15m else None,
        "strategies": strategy_results,
        "comparison": comparison,
        "assessment": _assess_comparison(comparison),
    }


def run_cached_binance_segmented_validation(
    config: AgentConfig,
    csv_15m: str = "data/real_binance_btcusdt_15m_6000_latest.csv",
    optimization_json: str = "runs/binance_strategy_optimization_confirmation_result.json",
    confirmation_json: str = "runs/binance_strategy_confirmation_candidate_result.json",
    context_json: str = "runs/binance_strategy_context_candidate_result.json",
    segment_days: int = 7,
) -> dict[str, Any]:
    candles_15m = load_csv(csv_15m)
    strategies = _load_strategy_set(optimization_json, confirmation_json, context_json)
    result = run_segmented_strategy_validation(
        config,
        candles_15m,
        strategies,
        segment_days=segment_days,
    )
    result["data_source"] = "cached_binance_vision_public_klines"
    result["csv_15m"] = csv_15m
    result["optimization_json"] = optimization_json
    result["confirmation_json"] = confirmation_json
    result["context_json"] = context_json
    return result


def save_segmented_validation_json(result: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def render_segmented_validation_report(result: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    summary_rows = "\n".join(
        _summary_row(name, item.get("summary", {}))
        for name, item in result.get("strategies", {}).items()
    )
    segment_rows = "\n".join(_segment_comparison_rows(result))
    assessment = "\n".join(f"<li>{_e(item)}</li>" for item in result.get("assessment", []))
    if not assessment:
        assessment = "<li>No assessment.</li>"

    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Segmented Strategy Validation</title>
  <style>
    :root {{
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #17202a;
      --muted: #667085;
      --line: #d8dee8;
      --green: #0f8a5f;
      --red: #bf3b35;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Arial, "Microsoft YaHei", sans-serif;
      letter-spacing: 0;
    }}
    main {{
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto;
      padding: 28px 0 40px;
    }}
    header {{ padding-bottom: 18px; border-bottom: 1px solid var(--line); }}
    h1, h2, p {{ margin: 0; }}
    h1 {{ font-size: 28px; line-height: 1.2; }}
    h2 {{ font-size: 16px; margin-bottom: 14px; }}
    .subtitle {{ margin-top: 8px; color: var(--muted); font-size: 14px; }}
    section {{
      margin-top: 16px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
    }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{
      padding: 10px 8px;
      border-bottom: 1px solid #edf0f4;
      text-align: right;
      white-space: nowrap;
    }}
    th:first-child, td:first-child {{ text-align: left; }}
    th {{ color: var(--muted); }}
    .table-wrap {{ overflow-x: auto; }}
    .positive {{ color: var(--green); font-weight: 700; }}
    .negative {{ color: var(--red); font-weight: 700; }}
    ul {{ margin: 0; padding-left: 20px; line-height: 1.7; }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{_e(result.get("symbol", "-"))} 分段策略稳定性验证</h1>
      <p class="subtitle">每 {_n(result.get("segment_days"))} 天独立回测一次，比较原策略、趋势过滤、成交量确认候选。</p>
    </header>
    <section>
      <h2>策略总览</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>策略</th>
              <th>分段数</th>
              <th>正常成本正收益段</th>
              <th>正常成本总收益</th>
              <th>严苛成本正收益段</th>
              <th>严苛成本总收益</th>
              <th>总交易数</th>
              <th>平均回撤</th>
            </tr>
          </thead>
          <tbody>{summary_rows}</tbody>
        </table>
      </div>
    </section>
    <section>
      <h2>分段明细</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>分段</th>
              <th>策略</th>
              <th>时间范围</th>
              <th>交易数</th>
              <th>胜率</th>
              <th>正常成本收益</th>
              <th>严苛成本收益</th>
              <th>最大回撤</th>
              <th>多/空</th>
            </tr>
          </thead>
          <tbody>{segment_rows}</tbody>
        </table>
      </div>
    </section>
    <section>
      <h2>评估</h2>
      <ul>{assessment}</ul>
    </section>
  </main>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")


def _load_strategy_set(
    optimization_json: str | Path,
    confirmation_json: str | Path,
    context_json: str | Path,
) -> dict[str, StrategyParams]:
    strategies = {"baseline": StrategyParams()}
    optimization_path = Path(optimization_json)
    if optimization_path.exists():
        optimization = json.loads(optimization_path.read_text(encoding="utf-8"))
        strategies["trend_filter"] = StrategyParams(**optimization["best_params"])
    confirmation_path = Path(confirmation_json)
    if confirmation_path.exists():
        confirmation = json.loads(confirmation_path.read_text(encoding="utf-8"))
        strategies["volume_confirmation"] = StrategyParams(
            **confirmation["best_confirmation_params"]
        )
    context_path = Path(context_json)
    if context_path.exists():
        context = json.loads(context_path.read_text(encoding="utf-8"))
        strategies["three_day_context"] = StrategyParams(
            **context["best_context_params"]
        )
    return strategies


def _summarize_segments(segments: list[dict[str, Any]]) -> dict[str, Any]:
    normal_positive = [
        item for item in segments if (item.get("normal_cost_net_profit") or 0) > 0
    ]
    severe_positive = [
        item for item in segments if (item.get("severe_cost_net_profit") or 0) > 0
    ]
    total_normal = sum(item.get("normal_cost_net_profit") or 0 for item in segments)
    total_severe = sum(item.get("severe_cost_net_profit") or 0 for item in segments)
    return {
        "segment_count": len(segments),
        "normal_positive_segments": len(normal_positive),
        "normal_positive_segment_rate_pct": round(
            (len(normal_positive) / len(segments)) * 100,
            2,
        )
        if segments
        else 0.0,
        "normal_cost_net_profit": round(total_normal, 2),
        "severe_positive_segments": len(severe_positive),
        "severe_positive_segment_rate_pct": round(
            (len(severe_positive) / len(segments)) * 100,
            2,
        )
        if segments
        else 0.0,
        "severe_cost_net_profit": round(total_severe, 2),
        "total_trades": sum(item.get("total_trades") or 0 for item in segments),
        "average_max_drawdown_pct": round(
            sum(item.get("max_drawdown_pct") or 0 for item in segments) / len(segments),
            4,
        )
        if segments
        else 0.0,
    }


def _rank_strategies(strategy_results: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for name, item in strategy_results.items():
        summary = item.get("summary", {})
        rows.append(
            {
                "strategy": name,
                "normal_cost_net_profit": summary.get("normal_cost_net_profit", 0),
                "normal_positive_segment_rate_pct": summary.get(
                    "normal_positive_segment_rate_pct",
                    0,
                ),
                "severe_cost_net_profit": summary.get("severe_cost_net_profit", 0),
                "total_trades": summary.get("total_trades", 0),
            }
        )
    rows.sort(
        key=lambda item: (
            item["normal_cost_net_profit"],
            item["normal_positive_segment_rate_pct"],
            item["severe_cost_net_profit"],
        ),
        reverse=True,
    )
    return rows


def _assess_comparison(comparison: list[dict[str, Any]]) -> list[str]:
    if not comparison:
        return ["没有足够数据生成分段验证。"]
    best = comparison[0]
    notes = [
        f"正常成本下排名最高的是 {best['strategy']}，总净收益为 {_n(best['normal_cost_net_profit'])}。",
    ]
    if best["normal_cost_net_profit"] <= 0:
        notes.append("最佳策略在正常成本后仍为负，不能进入实盘。")
    elif best["normal_positive_segment_rate_pct"] < 60:
        notes.append("虽然总收益为正，但正收益分段比例不足，稳定性仍然不够。")
    else:
        notes.append("分段表现有所改善，但仍需要更长历史和模拟盘验证。")
    notes.append("这一步只做公开K线回测，没有真实盘口、资金费率和订单簿冲击。")
    return notes


def _cost_case(result: dict[str, Any], name: str) -> dict[str, Any] | None:
    for item in result.get("cost_stress", []):
        if item.get("name") == name:
            return item
    return None


def _summary_row(name: str, summary: dict[str, Any]) -> str:
    return f"""<tr>
      <td>{_e(name)}</td>
      <td>{_n(summary.get("segment_count"))}</td>
      <td>{_n(summary.get("normal_positive_segment_rate_pct"))}%</td>
      <td class="{_pnl_class(summary.get("normal_cost_net_profit"))}">{_n(summary.get("normal_cost_net_profit"))}</td>
      <td>{_n(summary.get("severe_positive_segment_rate_pct"))}%</td>
      <td class="{_pnl_class(summary.get("severe_cost_net_profit"))}">{_n(summary.get("severe_cost_net_profit"))}</td>
      <td>{_n(summary.get("total_trades"))}</td>
      <td>{_n(summary.get("average_max_drawdown_pct"))}%</td>
    </tr>"""


def _segment_comparison_rows(result: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for name, item in result.get("strategies", {}).items():
        for segment in item.get("segments", []):
            rows.append(
                f"""<tr>
      <td>{_n(segment.get("segment"))}</td>
      <td>{_e(name)}</td>
      <td>{_e(segment.get("first_candle", "-"))} - {_e(segment.get("last_candle", "-"))}</td>
      <td>{_n(segment.get("total_trades"))}</td>
      <td>{_n(segment.get("win_rate_pct"))}%</td>
      <td class="{_pnl_class(segment.get("normal_cost_net_profit"))}">{_n(segment.get("normal_cost_return_pct"))}%</td>
      <td class="{_pnl_class(segment.get("severe_cost_net_profit"))}">{_n(segment.get("severe_cost_return_pct"))}%</td>
      <td>{_n(segment.get("max_drawdown_pct"))}%</td>
      <td>{_n(segment.get("long_trades"))}/{_n(segment.get("short_trades"))}</td>
    </tr>"""
            )
    return rows


def _pnl_class(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if number > 0:
        return "positive"
    if number < 0:
        return "negative"
    return ""


def _n(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    return _e(value)


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)
