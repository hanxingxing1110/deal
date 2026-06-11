from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from crypto_agent.config import AgentConfig
from crypto_agent.dual_timeframe import run_dual_timeframe_backtest
from crypto_agent.market_data import (
    Candle,
    generate_intraday_sample_candles,
    load_csv,
    resample_candles,
    save_candles_csv,
)


def run_walk_forward_sample(
    config: AgentConfig,
    days: int = 60,
    segment_days: int = 14,
) -> dict[str, Any]:
    candles_15m = generate_intraday_sample_candles(days * 24 * 4)
    save_candles_csv("data/walk_forward_sample_15m.csv", candles_15m)
    result = run_walk_forward(config, candles_15m, segment_days=segment_days)
    result["data_source"] = "sample"
    result["days"] = days
    return result


def run_walk_forward_csv(
    config: AgentConfig,
    csv_15m: str,
    segment_days: int = 14,
) -> dict[str, Any]:
    candles_15m = load_csv(csv_15m)
    result = run_walk_forward(config, candles_15m, segment_days=segment_days)
    result["data_source"] = "csv"
    result["csv_15m"] = csv_15m
    return result


def run_walk_forward(
    config: AgentConfig,
    candles_15m: list[Candle],
    segment_days: int = 14,
) -> dict[str, Any]:
    segment_size = segment_days * 24 * 4
    if segment_size < 160:
        raise ValueError("segment_days is too small for dual-timeframe backtesting.")

    segments: list[dict[str, Any]] = []
    for segment_index, start in enumerate(range(0, len(candles_15m), segment_size), start=1):
        segment_15m = candles_15m[start : start + segment_size]
        if len(segment_15m) < segment_size:
            continue
        segment_1h = resample_candles(segment_15m, 4)
        if len(segment_1h) < 40:
            continue
        result = run_dual_timeframe_backtest(config, segment_15m, segment_1h)
        strict_case = _strict_cost_case(result.get("cost_stress", []))
        segments.append(
            {
                "segment": segment_index,
                "first_candle": segment_15m[0].timestamp,
                "last_candle": segment_15m[-1].timestamp,
                "return_pct": result["return_pct"],
                "net_profit": result["net_profit"],
                "max_drawdown_pct": result["max_drawdown_pct"],
                "total_trades": result["total_trades"],
                "win_rate_pct": result["win_rate_pct"],
                "profit_factor": result["profit_factor"],
                "strict_return_pct": strict_case.get("return_pct") if strict_case else None,
                "strict_net_profit": strict_case.get("net_profit") if strict_case else None,
                "strict_profit_factor": strict_case.get("profit_factor") if strict_case else None,
                "long_trades": result["long_trades"],
                "short_trades": result["short_trades"],
            }
        )

    positive_segments = [item for item in segments if item["net_profit"] > 0]
    strict_positive_segments = [
        item for item in segments if (item.get("strict_net_profit") or 0) > 0
    ]
    total_net_profit = sum(item["net_profit"] for item in segments)
    total_strict_net_profit = sum(item.get("strict_net_profit") or 0 for item in segments)

    return {
        "symbol": config.symbol,
        "segment_days": segment_days,
        "segment_count": len(segments),
        "positive_segments": len(positive_segments),
        "strict_positive_segments": len(strict_positive_segments),
        "positive_segment_rate_pct": round((len(positive_segments) / len(segments)) * 100, 2)
        if segments
        else 0.0,
        "strict_positive_segment_rate_pct": round(
            (len(strict_positive_segments) / len(segments)) * 100,
            2,
        )
        if segments
        else 0.0,
        "total_net_profit": round(total_net_profit, 2),
        "total_strict_net_profit": round(total_strict_net_profit, 2),
        "average_return_pct": round(
            sum(item["return_pct"] for item in segments) / len(segments),
            4,
        )
        if segments
        else 0.0,
        "average_strict_return_pct": round(
            sum(item.get("strict_return_pct") or 0 for item in segments) / len(segments),
            4,
        )
        if segments
        else 0.0,
        "segments": segments,
        "assessment": _assess_walk_forward(segments),
    }


def save_walk_forward_json(result: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def render_walk_forward_report(result: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(_segment_row(item) for item in result.get("segments", []))
    if not rows:
        rows = "<tr><td colspan=\"10\">没有足够数据生成分段报告。</td></tr>"
    assessment_items = "\n".join(
        f"<li>{_e(item)}</li>" for item in result.get("assessment", [])
    )
    if not assessment_items:
        assessment_items = "<li>没有额外评估。</li>"

    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Crypto Agent Walk Forward</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #17202a;
      --muted: #667085;
      --line: #d8dee8;
      --green: #0f8a5f;
      --red: #bf3b35;
      --amber: #ad7415;
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

    header {{
      padding: 18px 0 22px;
      border-bottom: 1px solid var(--line);
    }}

    h1, h2, p {{ margin: 0; }}
    h1 {{ font-size: 28px; line-height: 1.2; }}
    h2 {{ font-size: 16px; margin-bottom: 14px; }}

    .subtitle {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 14px;
    }}

    .grid {{
      display: grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 16px;
      margin-top: 18px;
    }}

    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
    }}

    .span-3 {{ grid-column: span 3; }}
    .span-12 {{ grid-column: span 12; }}

    .metric {{
      display: grid;
      gap: 6px;
    }}

    .metric strong {{
      font-size: 28px;
      line-height: 1;
    }}

    .metric span {{
      color: var(--muted);
      font-size: 13px;
    }}

    .positive {{ color: var(--green); }}
    .negative {{ color: var(--red); }}
    .neutral {{ color: var(--amber); }}

    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}

    th, td {{
      padding: 10px 8px;
      border-bottom: 1px solid #edf0f4;
      text-align: right;
      white-space: nowrap;
    }}

    th:first-child, td:first-child {{
      text-align: left;
    }}

    th {{
      color: var(--muted);
      font-weight: 700;
    }}

    .table-wrap {{ overflow-x: auto; }}

    ul {{
      margin: 0;
      padding-left: 20px;
      line-height: 1.7;
    }}

    @media (max-width: 860px) {{
      .span-3, .span-12 {{ grid-column: span 12; }}
      main {{ width: min(100% - 20px, 1180px); padding-top: 16px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{_e(result.get("symbol", "-"))} 分段稳健性报告</h1>
      <p class="subtitle">每 {_n(result.get("segment_days"))} 天独立跑一次双周期多空回测，并检查严苛成本后的表现。</p>
    </header>

    <div class="grid">
      <section class="span-3">
        <div class="metric">
          <span>分段数量</span>
          <strong>{_n(result.get("segment_count"))}</strong>
        </div>
      </section>
      <section class="span-3">
        <div class="metric">
          <span>原始正收益分段</span>
          <strong>{_n(result.get("positive_segment_rate_pct"))}%</strong>
        </div>
      </section>
      <section class="span-3">
        <div class="metric">
          <span>严苛成本正收益分段</span>
          <strong>{_n(result.get("strict_positive_segment_rate_pct"))}%</strong>
        </div>
      </section>
      <section class="span-3">
        <div class="metric">
          <span>严苛成本总净收益</span>
          <strong class="{_pnl_class(result.get("total_strict_net_profit"))}">{_n(result.get("total_strict_net_profit"))}</strong>
        </div>
      </section>

      <section class="span-12">
        <h2>分段明细</h2>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>分段</th>
                <th>开始</th>
                <th>结束</th>
                <th>交易次数</th>
                <th>胜率</th>
                <th>原始收益率</th>
                <th>严苛成本收益率</th>
                <th>最大回撤</th>
                <th>做多/做空</th>
                <th>严苛成本净收益</th>
              </tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
        </div>
      </section>

      <section class="span-12">
        <h2>评估</h2>
        <ul>{assessment_items}</ul>
      </section>
    </div>
  </main>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")


def _strict_cost_case(cost_stress: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in cost_stress:
        if item.get("name") == "严苛成本":
            return item
    return cost_stress[-1] if cost_stress else None


def _assess_walk_forward(segments: list[dict[str, Any]]) -> list[str]:
    if not segments:
        return ["数据不足，无法做分段稳健性验证。"]

    strict_positive = [
        item for item in segments if (item.get("strict_net_profit") or 0) > 0
    ]
    strict_rate = len(strict_positive) / len(segments)
    total_strict_profit = sum(item.get("strict_net_profit") or 0 for item in segments)
    notes: list[str] = []

    if strict_rate >= 0.7 and total_strict_profit > 0:
        notes.append("严苛成本下多数分段为正，样例上的稳健性较好。")
    elif strict_rate >= 0.5 and total_strict_profit > 0:
        notes.append("严苛成本下约半数以上分段为正，策略值得继续用真实数据验证。")
    else:
        notes.append("严苛成本下分段表现不稳定，不适合进入实盘阶段。")

    losing_segments = len(segments) - len(strict_positive)
    if losing_segments:
        notes.append(f"有 {losing_segments} 个分段在严苛成本下为负，需要检查这些市场阶段。")
    notes.append("下一步应对真实历史数据做同样分段验证，并保留亏损分段做策略复盘。")
    return notes


def _segment_row(item: dict[str, Any]) -> str:
    strict_net = item.get("strict_net_profit")
    return f"""<tr>
      <td>{_n(item.get("segment"))}</td>
      <td>{_e(item.get("first_candle", "-"))}</td>
      <td>{_e(item.get("last_candle", "-"))}</td>
      <td>{_n(item.get("total_trades"))}</td>
      <td>{_n(item.get("win_rate_pct"))}%</td>
      <td class="{_pnl_class(item.get("return_pct"))}">{_n(item.get("return_pct"))}%</td>
      <td class="{_pnl_class(item.get("strict_return_pct"))}">{_n(item.get("strict_return_pct"))}%</td>
      <td>{_n(item.get("max_drawdown_pct"))}%</td>
      <td>{_n(item.get("long_trades"))}/{_n(item.get("short_trades"))}</td>
      <td class="{_pnl_class(strict_net)}">{_n(strict_net)}</td>
    </tr>"""


def _pnl_class(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "neutral"
    if number > 0:
        return "positive"
    if number < 0:
        return "negative"
    return "neutral"


def _n(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    return _e(value)


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)
