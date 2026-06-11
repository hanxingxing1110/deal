from __future__ import annotations

import html
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from crypto_agent.config import AgentConfig
from crypto_agent.dual_timeframe import run_dual_timeframe_backtest
from crypto_agent.market_data import Candle, load_csv, resample_candles
from crypto_agent.strategy import StrategyParams
from crypto_agent.strategy_optimizer import _summary


def run_cached_binance_exit_validation(
    config: AgentConfig,
    csv_15m: str = "data/real_binance_btcusdt_15m_6000_latest.csv",
    base_params_json: str = "runs/binance_strategy_optimization_context_result.json",
    segment_days: int = 7,
) -> dict[str, Any]:
    candles_15m = load_csv(csv_15m)
    candles_1h = resample_candles(candles_15m, 4)
    base_params = _load_base_params(base_params_json)
    candidates = _exit_candidates(base_params)

    candidate_results = []
    for name, params in candidates.items():
        result = run_dual_timeframe_backtest(config, candles_15m, candles_1h, params)
        candidate_results.append(
            {
                "name": name,
                "params": params.__dict__,
                "summary": _summary(result),
                "score": _score_exit_result(result),
            }
        )
    candidate_results.sort(key=lambda item: item["score"], reverse=True)

    best_name = candidate_results[0]["name"]
    best_params = StrategyParams(**candidate_results[0]["params"])
    segmented = _run_exit_segments(
        config,
        candles_15m,
        {
            "base_exit": base_params,
            best_name: best_params,
        },
        segment_days=segment_days,
    )

    return {
        "symbol": config.symbol,
        "data_source": "cached_binance_vision_public_klines",
        "csv_15m": csv_15m,
        "base_params_json": base_params_json,
        "actual_15m_candles": len(candles_15m),
        "actual_1h_candles": len(candles_1h),
        "first_candle": candles_15m[0].timestamp,
        "last_candle": candles_15m[-1].timestamp,
        "candidate_count": len(candidate_results),
        "candidates": candidate_results,
        "best": candidate_results[0],
        "segmented": segmented,
        "assessment": _assess_exit_validation(candidate_results[0], segmented),
    }


def save_exit_validation_json(result: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def render_exit_validation_report(result: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    candidate_rows = "\n".join(
        _candidate_row(item) for item in result.get("candidates", [])[:12]
    )
    segment_rows = "\n".join(
        _segment_row(strategy, segment)
        for strategy, item in result.get("segmented", {}).get("strategies", {}).items()
        for segment in item.get("segments", [])
    )
    assessment = "\n".join(f"<li>{_e(item)}</li>" for item in result.get("assessment", []))

    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Exit Management Validation</title>
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
      <h1>{_e(result.get("symbol", "-"))} 出场管理验证</h1>
      <p class="subtitle">固定当前入场过滤，只比较保本止损和移动止损组合。</p>
    </header>
    <section>
      <h2>候选组合</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>组合</th>
              <th>交易数</th>
              <th>胜率</th>
              <th>收益率</th>
              <th>正常成本收益</th>
              <th>最大回撤</th>
              <th>盈亏比</th>
              <th>BE R</th>
              <th>Trail R</th>
              <th>Trail ATR</th>
            </tr>
          </thead>
          <tbody>{candidate_rows}</tbody>
        </table>
      </div>
    </section>
    <section>
      <h2>分段对比</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>策略</th>
              <th>分段</th>
              <th>交易数</th>
              <th>胜率</th>
              <th>正常成本收益</th>
              <th>严苛成本收益</th>
              <th>最大回撤</th>
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


def _load_base_params(path: str | Path) -> StrategyParams:
    params_path = Path(path)
    if not params_path.exists():
        return StrategyParams()
    result = json.loads(params_path.read_text(encoding="utf-8"))
    return StrategyParams(**result["best_params"])


def _exit_candidates(base_params: StrategyParams) -> dict[str, StrategyParams]:
    candidates = {"base_exit": base_params}
    for breakeven_at_r in (0.6, 0.8, 1.0):
        candidates[f"be_{breakeven_at_r:g}r"] = replace(
            base_params,
            breakeven_at_r=breakeven_at_r,
            trailing_start_r=0.0,
        )
    for breakeven_at_r in (0.6, 0.8, 1.0):
        for trailing_start_r in (1.0, 1.4, 1.8):
            for trailing_atr_mult in (0.8, 1.0, 1.3):
                name = f"be_{breakeven_at_r:g}r_trail_{trailing_start_r:g}r_{trailing_atr_mult:g}atr"
                candidates[name] = replace(
                    base_params,
                    breakeven_at_r=breakeven_at_r,
                    trailing_start_r=trailing_start_r,
                    trailing_atr_mult=trailing_atr_mult,
                )
    return candidates


def _score_exit_result(result: dict[str, Any]) -> float:
    normal_cost = _cost_case(result, "正常成本")
    normal_return = float(normal_cost.get("return_pct") or -99.0) if normal_cost else -99.0
    drawdown = float(result.get("max_drawdown_pct") or 0.0)
    trades = int(result.get("total_trades") or 0)
    if trades < 10:
        return -9999.0
    profit_factor = float(result.get("profit_factor") or 0.0)
    return normal_return * 5 + profit_factor * 1.5 - drawdown * 0.8


def _run_exit_segments(
    config: AgentConfig,
    candles_15m: list[Candle],
    strategies: dict[str, StrategyParams],
    segment_days: int,
) -> dict[str, Any]:
    segment_size = segment_days * 24 * 4
    results: dict[str, Any] = {}
    for name, params in strategies.items():
        segments = []
        for segment_index, start in enumerate(range(0, len(candles_15m), segment_size), start=1):
            segment_15m = candles_15m[start : start + segment_size]
            if len(segment_15m) < segment_size:
                continue
            backtest = run_dual_timeframe_backtest(
                config,
                segment_15m,
                resample_candles(segment_15m, 4),
                params,
            )
            normal_cost = _cost_case(backtest, "正常成本")
            severe_cost = _cost_case(backtest, "严苛成本")
            segments.append(
                {
                    "segment": segment_index,
                    "first_candle": segment_15m[0].timestamp,
                    "last_candle": segment_15m[-1].timestamp,
                    "total_trades": backtest["total_trades"],
                    "win_rate_pct": backtest["win_rate_pct"],
                    "max_drawdown_pct": backtest["max_drawdown_pct"],
                    "normal_cost_return_pct": normal_cost.get("return_pct") if normal_cost else None,
                    "normal_cost_net_profit": normal_cost.get("net_profit") if normal_cost else None,
                    "severe_cost_return_pct": severe_cost.get("return_pct") if severe_cost else None,
                    "severe_cost_net_profit": severe_cost.get("net_profit") if severe_cost else None,
                }
            )
        results[name] = {
            "params": params.__dict__,
            "segments": segments,
            "summary": _segment_summary(segments),
        }
    return {"segment_days": segment_days, "strategies": results}


def _segment_summary(segments: list[dict[str, Any]]) -> dict[str, Any]:
    normal_profit = sum(item.get("normal_cost_net_profit") or 0 for item in segments)
    severe_profit = sum(item.get("severe_cost_net_profit") or 0 for item in segments)
    normal_positive = [
        item for item in segments if (item.get("normal_cost_net_profit") or 0) > 0
    ]
    return {
        "segment_count": len(segments),
        "normal_cost_net_profit": round(normal_profit, 2),
        "severe_cost_net_profit": round(severe_profit, 2),
        "normal_positive_segment_rate_pct": round(
            (len(normal_positive) / len(segments)) * 100,
            2,
        )
        if segments
        else 0.0,
    }


def _assess_exit_validation(best: dict[str, Any], segmented: dict[str, Any]) -> list[str]:
    base = segmented["strategies"].get("base_exit", {}).get("summary", {})
    best_summary = segmented["strategies"].get(best["name"], {}).get("summary", {})
    notes = [
        f"全量正常成本评分最高的是 {best['name']}。",
        f"base_exit 分段正常成本净收益为 {_n(base.get('normal_cost_net_profit'))}。",
        f"{best['name']} 分段正常成本净收益为 {_n(best_summary.get('normal_cost_net_profit'))}。",
    ]
    if (best_summary.get("normal_cost_net_profit") or 0) <= (base.get("normal_cost_net_profit") or 0):
        notes.append("动态出场没有在分段验证里超过原出场，不应采用。")
    elif (best_summary.get("normal_cost_net_profit") or 0) <= 0:
        notes.append("动态出场优于原出场，但正常成本后仍为负，只能继续研究。")
    else:
        notes.append("动态出场在分段验证里改善明显，但仍需更长历史和模拟盘验证。")
    return notes


def _cost_case(result: dict[str, Any], name: str) -> dict[str, Any] | None:
    for item in result.get("cost_stress", []):
        if item.get("name") == name:
            return item
    return None


def _candidate_row(item: dict[str, Any]) -> str:
    summary = item.get("summary", {})
    params = item.get("params", {})
    return f"""<tr>
      <td>{_e(item.get("name"))}</td>
      <td>{_n(summary.get("total_trades"))}</td>
      <td>{_n(summary.get("win_rate_pct"))}%</td>
      <td class="{_pnl_class(summary.get("return_pct"))}">{_n(summary.get("return_pct"))}%</td>
      <td class="{_pnl_class(summary.get("normal_cost_return_pct"))}">{_n(summary.get("normal_cost_return_pct"))}%</td>
      <td>{_n(summary.get("max_drawdown_pct"))}%</td>
      <td>{_n(summary.get("profit_factor"))}</td>
      <td>{_n(params.get("breakeven_at_r"))}</td>
      <td>{_n(params.get("trailing_start_r"))}</td>
      <td>{_n(params.get("trailing_atr_mult"))}</td>
    </tr>"""


def _segment_row(strategy: str, segment: dict[str, Any]) -> str:
    return f"""<tr>
      <td>{_e(strategy)}</td>
      <td>{_n(segment.get("segment"))}</td>
      <td>{_n(segment.get("total_trades"))}</td>
      <td>{_n(segment.get("win_rate_pct"))}%</td>
      <td class="{_pnl_class(segment.get("normal_cost_net_profit"))}">{_n(segment.get("normal_cost_return_pct"))}%</td>
      <td class="{_pnl_class(segment.get("severe_cost_net_profit"))}">{_n(segment.get("severe_cost_return_pct"))}%</td>
      <td>{_n(segment.get("max_drawdown_pct"))}%</td>
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
