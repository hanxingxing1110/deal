from __future__ import annotations

import html
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from crypto_agent.backtest import run_backtest
from crypto_agent.config import AgentConfig
from crypto_agent.market_data import (
    generate_intraday_sample_candles,
    resample_candles,
    save_candles_csv,
)


def run_timeframe_experiment(config: AgentConfig, days: int = 60) -> dict[str, Any]:
    candle_count_15m = days * 24 * 4
    candles_15m = generate_intraday_sample_candles(candle_count_15m)
    candles_1h = resample_candles(candles_15m, 4)

    config_15m = replace(config, interval="15m")
    config_1h = replace(config, interval="1h")

    result_15m = run_backtest(config_15m, candles_15m)
    result_1h = run_backtest(config_1h, candles_1h)

    save_candles_csv("data/sample_btcusdt_15m_60d.csv", candles_15m)
    save_candles_csv("data/sample_btcusdt_1h_from_15m_60d.csv", candles_1h)

    return {
        "symbol": config.symbol,
        "days": days,
        "starting_cash": config.starting_cash,
        "risk_per_trade": config.risk_per_trade,
        "max_position_usd": config.max_position_usd,
        "timeframes": {
            "15m": result_15m,
            "1h": result_1h,
        },
        "assessment": _assess_results(result_15m, result_1h),
    }


def save_strategy_lab_json(result: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def render_strategy_lab_report(result: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    timeframes = result.get("timeframes", {})
    rows = "\n".join(
        _timeframe_row(label, stats) for label, stats in timeframes.items()
    )
    assessment_items = "\n".join(
        f"<li>{_e(item)}</li>" for item in result.get("assessment", [])
    )
    if not assessment_items:
        assessment_items = "<li>没有生成额外评估。</li>"

    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Crypto Agent Strategy Lab</title>
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

    .span-12 {{ grid-column: span 12; }}

    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}

    th, td {{
      padding: 11px 8px;
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

    .table-wrap {{
      overflow-x: auto;
    }}

    .positive {{ color: var(--green); font-weight: 700; }}
    .negative {{ color: var(--red); font-weight: 700; }}
    .neutral {{ color: var(--amber); font-weight: 700; }}

    ul {{
      margin: 0;
      padding-left: 20px;
      line-height: 1.7;
    }}

    .note {{
      margin-top: 12px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.55;
    }}

    @media (max-width: 860px) {{
      .span-12 {{ grid-column: span 12; }}
      main {{ width: min(100% - 20px, 1180px); padding-top: 16px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{_e(result.get("symbol", "-"))} 策略实验室</h1>
      <p class="subtitle">同一段约 {_n(result.get("days"))} 天样例行情，对比 15分钟 K 线和 1小时 K 线。</p>
    </header>

    <div class="grid">
      <section class="span-12">
        <h2>周期对比</h2>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>周期</th>
                <th>K线数量</th>
                <th>交易次数</th>
                <th>胜率</th>
                <th>收益率</th>
                <th>净收益</th>
                <th>最大回撤</th>
                <th>总手续费</th>
                <th>盈亏比因子</th>
                <th>数据质量</th>
              </tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
        </div>
        <p class="note">15分钟 K 线通常交易更多，也更容易被手续费、滑点和噪音吞掉优势。1小时 K 线信号更慢，但通常更稳。</p>
      </section>

      <section class="span-12">
        <h2>适用性评估</h2>
        <ul>{assessment_items}</ul>
      </section>
    </div>
  </main>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")


def _assess_results(result_15m: dict[str, Any], result_1h: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    trades_15m = int(result_15m.get("total_trades", 0))
    trades_1h = int(result_1h.get("total_trades", 0))
    return_15m = float(result_15m.get("return_pct", 0))
    return_1h = float(result_1h.get("return_pct", 0))
    drawdown_15m = float(result_15m.get("max_drawdown_pct", 0))
    drawdown_1h = float(result_1h.get("max_drawdown_pct", 0))

    if trades_15m > trades_1h * 2:
        notes.append("15分钟周期明显更活跃，后续必须把手续费和滑点设得更保守。")
    if return_15m < 0:
        notes.append("15分钟周期在这段样例上没有赚钱，不适合直接进入实盘。")
    if return_1h < 0:
        notes.append("1小时周期在这段样例上也没有通过初筛，策略本身需要优化。")
    if drawdown_15m > drawdown_1h:
        notes.append("15分钟周期回撤更大，说明短周期噪音风险更明显。")
    if return_15m > return_1h and drawdown_15m <= drawdown_1h:
        notes.append("15分钟周期在收益和回撤上暂时占优，可以作为后续重点研究对象。")
    if return_1h > return_15m and drawdown_1h <= drawdown_15m:
        notes.append("1小时周期暂时更稳，可以作为大方向过滤器。")
    notes.append("建议先采用 1小时定方向、15分钟找入场的双周期架构，而不是让 15分钟信号单独决定交易。")
    return notes


def _timeframe_row(label: str, stats: dict[str, Any]) -> str:
    quality = stats.get("data_quality") or {}
    return_pct = stats.get("return_pct", 0)
    net_profit = stats.get("net_profit", 0)
    return f"""<tr>
      <td>{_e(label)}</td>
      <td>{_n(quality.get("candle_count"))}</td>
      <td>{_n(stats.get("total_trades"))}</td>
      <td>{_n(stats.get("win_rate_pct"))}%</td>
      <td class="{_pnl_class(return_pct)}">{_n(return_pct)}%</td>
      <td class="{_pnl_class(net_profit)}">{_n(net_profit)}</td>
      <td>{_n(stats.get("max_drawdown_pct"))}%</td>
      <td>{_n(stats.get("total_fees"))}</td>
      <td>{_n(stats.get("profit_factor"))}</td>
      <td>{_quality_label(quality.get("status"))}</td>
    </tr>"""


def _quality_label(value: object) -> str:
    if value == "ok":
        return "正常"
    if value == "warning":
        return "有提醒"
    if value == "bad":
        return "需处理"
    return "未知"


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
