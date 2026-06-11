from __future__ import annotations

import html
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from crypto_agent.config import AgentConfig
from crypto_agent.dual_timeframe import run_dual_timeframe_backtest
from crypto_agent.market_data import (
    Candle,
    fetch_binance_klines,
    load_csv,
    resample_candles,
    save_candles_csv,
)
from crypto_agent.strategy import StrategyParams
from crypto_agent.strategy_optimizer import _summary


def run_binance_direction_validation(
    config: AgentConfig,
    candle_limit: int = 3000,
    base_params_json: str = "runs/binance_strategy_optimization_context_result.json",
    fallback_csv_15m: str = "data/real_binance_btcusdt_15m_6000_latest.csv",
) -> dict[str, Any]:
    data_source = "binance_vision_public_klines"
    try:
        candles_15m = fetch_binance_klines(config.symbol, "15m", candle_limit)
        save_candles_csv("data/real_binance_btcusdt_15m_direction_latest.csv", candles_15m)
    except Exception as exc:
        candles_15m = load_csv(fallback_csv_15m)[-candle_limit:]
        data_source = "cached_binance_vision_public_klines"
        source_warning = str(exc)
    else:
        source_warning = None

    candles_1h = resample_candles(candles_15m, 4)
    save_candles_csv("data/real_binance_btcusdt_1h_direction_latest.csv", candles_1h)
    base_params = _load_base_params(base_params_json)
    strategies = {
        "both_sides": base_params,
        "long_only": replace(base_params, enable_long=True, enable_short=False),
        "short_only": replace(base_params, enable_long=False, enable_short=True),
    }

    strategy_results = {}
    for name, params in strategies.items():
        result = run_dual_timeframe_backtest(config, candles_15m, candles_1h, params)
        strategy_results[name] = {
            "params": params.__dict__,
            "summary": _summary(result),
            "assessment": result.get("assessment", []),
        }

    ranking = _rank_strategies(strategy_results)
    output = {
        "symbol": config.symbol,
        "data_source": data_source,
        "source_warning": source_warning,
        "actual_15m_candles": len(candles_15m),
        "actual_1h_candles": len(candles_1h),
        "first_candle": candles_15m[0].timestamp,
        "last_candle": candles_15m[-1].timestamp,
        "base_params_json": base_params_json,
        "strategies": strategy_results,
        "ranking": ranking,
        "assessment": _assess_direction_result(ranking),
    }
    return output


def save_direction_validation_json(result: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def render_direction_validation_report(result: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(
        _strategy_row(name, item)
        for name, item in result.get("strategies", {}).items()
    )
    assessment = "\n".join(f"<li>{_e(item)}</li>" for item in result.get("assessment", []))
    if not assessment:
        assessment = "<li>No assessment.</li>"

    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Direction Validation</title>
  <style>
    :root {{
      --bg: #f6f7f9;
      --panel: #fff;
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
    main {{ width: min(1180px, calc(100% - 32px)); margin: 0 auto; padding: 28px 0 40px; }}
    header {{ padding-bottom: 18px; border-bottom: 1px solid var(--line); }}
    h1, h2, p {{ margin: 0; }}
    h1 {{ font-size: 28px; line-height: 1.2; }}
    h2 {{ font-size: 16px; margin-bottom: 14px; }}
    .subtitle {{ margin-top: 8px; color: var(--muted); font-size: 14px; }}
    section {{ margin-top: 16px; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 18px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 10px 8px; border-bottom: 1px solid #edf0f4; text-align: right; white-space: nowrap; }}
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
      <h1>{_e(result.get("symbol", "-"))} 交易方向拆分验证</h1>
      <p class="subtitle">真实 Binance 公开K线：{_e(result.get("first_candle", "-"))} 至 {_e(result.get("last_candle", "-"))}</p>
    </header>
    <section>
      <h2>多空方向对比</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>策略</th>
              <th>交易数</th>
              <th>胜率</th>
              <th>收益率</th>
              <th>正常成本收益</th>
              <th>严苛成本收益</th>
              <th>最大回撤</th>
              <th>盈亏比</th>
              <th>多/空</th>
              <th>多头净收益</th>
              <th>空头净收益</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
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


def _load_base_params(path: str | Path) -> StrategyParams:
    params_path = Path(path)
    if not params_path.exists():
        return StrategyParams()
    result = json.loads(params_path.read_text(encoding="utf-8"))
    return StrategyParams(**result["best_params"])


def _rank_strategies(strategy_results: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for name, item in strategy_results.items():
        summary = item.get("summary", {})
        rows.append(
            {
                "strategy": name,
                "normal_cost_return_pct": summary.get("normal_cost_return_pct") or -999.0,
                "normal_cost_net_profit": _net_profit_proxy(summary),
                "return_pct": summary.get("return_pct") or -999.0,
                "total_trades": summary.get("total_trades") or 0,
                "win_rate_pct": summary.get("win_rate_pct") or 0.0,
            }
        )
    rows.sort(
        key=lambda item: (
            item["normal_cost_return_pct"],
            item["return_pct"],
            item["win_rate_pct"],
        ),
        reverse=True,
    )
    return rows


def _net_profit_proxy(summary: dict[str, Any]) -> float:
    return float(summary.get("normal_cost_return_pct") or 0.0) * 100


def _assess_direction_result(ranking: list[dict[str, Any]]) -> list[str]:
    if not ranking:
        return ["没有足够数据完成方向拆分。"]
    best = ranking[0]
    notes = [
        f"正常成本后排名最高的是 {best['strategy']}，收益率为 {_n(best['normal_cost_return_pct'])}%。",
    ]
    if best["normal_cost_return_pct"] <= 0:
        notes.append("即使最佳方向仍为负，不能进入实盘，只能继续纸上交易和研究。")
    elif best["total_trades"] < 10:
        notes.append("最佳方向为正，但交易次数偏少，需要更长历史验证。")
    else:
        notes.append("方向拆分有改善迹象，但还需要分段验证和模拟盘。")
    notes.append("本步骤仍然只使用公开K线和本地模拟订单，没有真实下单。")
    return notes


def _strategy_row(name: str, item: dict[str, Any]) -> str:
    summary = item.get("summary", {})
    return f"""<tr>
      <td>{_e(name)}</td>
      <td>{_n(summary.get("total_trades"))}</td>
      <td>{_n(summary.get("win_rate_pct"))}%</td>
      <td class="{_pnl_class(summary.get("return_pct"))}">{_n(summary.get("return_pct"))}%</td>
      <td class="{_pnl_class(summary.get("normal_cost_return_pct"))}">{_n(summary.get("normal_cost_return_pct"))}%</td>
      <td class="{_pnl_class(summary.get("severe_cost_return_pct"))}">{_n(summary.get("severe_cost_return_pct"))}%</td>
      <td>{_n(summary.get("max_drawdown_pct"))}%</td>
      <td>{_n(summary.get("profit_factor"))}</td>
      <td>{_n(summary.get("long_trades"))}/{_n(summary.get("short_trades"))}</td>
      <td class="{_pnl_class(summary.get("long_net_pnl"))}">{_n(summary.get("long_net_pnl"))}</td>
      <td class="{_pnl_class(summary.get("short_net_pnl"))}">{_n(summary.get("short_net_pnl"))}</td>
    </tr>"""


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
