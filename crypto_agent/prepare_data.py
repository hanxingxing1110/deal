from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from crypto_agent.data_quality import review_candles
from crypto_agent.market_data import (
    Candle,
    generate_intraday_sample_candles,
    load_csv,
    resample_candles,
    save_candles_csv,
)


def prepare_market_data(
    input_csv: str | Path,
    output_15m: str | Path,
    output_1h: str | Path,
) -> dict[str, Any]:
    candles_15m = _dedupe_and_sort(load_csv(input_csv))
    candles_1h = resample_candles(candles_15m, 4)

    save_candles_csv(output_15m, candles_15m)
    save_candles_csv(output_1h, candles_1h)

    quality_15m = review_candles(candles_15m, "15m")
    quality_1h = review_candles(candles_1h, "1h")
    ready = quality_15m["status"] == "ok" and quality_1h["status"] == "ok"

    return {
        "input_csv": str(input_csv),
        "output_15m": str(output_15m),
        "output_1h": str(output_1h),
        "ready_for_backtest": ready,
        "quality_15m": quality_15m,
        "quality_1h": quality_1h,
        "recommendations": _recommendations(quality_15m, quality_1h),
    }


def prepare_sample_market_data(
    output_15m: str | Path = "data/prepared_sample_15m.csv",
    output_1h: str | Path = "data/prepared_sample_1h.csv",
    source_csv: str | Path = "data/prepare_sample_source_15m.csv",
    days: int = 60,
) -> dict[str, Any]:
    source_path = Path(source_csv)
    candles = generate_intraday_sample_candles(days * 24 * 4)
    save_candles_csv(source_path, candles)
    result = prepare_market_data(source_path, output_15m, output_1h)
    result["data_source"] = "sample"
    result["days"] = days
    return result


def save_prepare_data_json(result: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def render_prepare_data_report(result: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    q15 = result.get("quality_15m") or {}
    q1h = result.get("quality_1h") or {}
    recommendations = "\n".join(
        f"<li>{_e(item)}</li>" for item in result.get("recommendations", [])
    )
    if not recommendations:
        recommendations = "<li>没有额外建议。</li>"

    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Crypto Agent Data Preparation</title>
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
      width: min(1120px, calc(100% - 32px));
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

    .span-4 {{ grid-column: span 4; }}
    .span-6 {{ grid-column: span 6; }}
    .span-12 {{ grid-column: span 12; }}

    .metric {{
      display: grid;
      gap: 6px;
    }}

    .metric strong {{
      font-size: 26px;
      line-height: 1;
    }}

    .metric span {{
      color: var(--muted);
      font-size: 13px;
    }}

    .status-ok {{ color: var(--green); }}
    .status-warning {{ color: var(--amber); }}
    .status-bad {{ color: var(--red); }}

    .kv {{
      display: grid;
      gap: 10px;
    }}

    .kv div {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      border-bottom: 1px solid #edf0f4;
      padding-bottom: 8px;
    }}

    .kv span {{
      color: var(--muted);
      font-size: 13px;
    }}

    .kv strong {{
      text-align: right;
      font-size: 14px;
    }}

    ul {{
      margin: 0;
      padding-left: 20px;
      line-height: 1.7;
    }}

    @media (max-width: 760px) {{
      .span-4, .span-6, .span-12 {{ grid-column: span 12; }}
      main {{ width: min(100% - 20px, 1120px); padding-top: 16px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>数据导入报告</h1>
      <p class="subtitle">标准化 15分钟 K 线，自动聚合 1小时趋势 K 线，并检查数据质量。</p>
    </header>

    <div class="grid">
      <section class="span-4">
        <div class="metric">
          <span>是否适合回测</span>
          <strong class="{_ready_class(result.get("ready_for_backtest"))}">{_ready_label(result.get("ready_for_backtest"))}</strong>
        </div>
      </section>
      <section class="span-4">
        <div class="metric">
          <span>15分钟数据状态</span>
          <strong class="status-{_e(q15.get("status", "unknown"))}">{_quality_label(q15.get("status"))}</strong>
        </div>
      </section>
      <section class="span-4">
        <div class="metric">
          <span>1小时数据状态</span>
          <strong class="status-{_e(q1h.get("status", "unknown"))}">{_quality_label(q1h.get("status"))}</strong>
        </div>
      </section>

      <section class="span-6">
        <h2>输入输出</h2>
        <div class="kv">
          <div><span>输入CSV</span><strong>{_e(result.get("input_csv", "-"))}</strong></div>
          <div><span>标准化15分钟CSV</span><strong>{_e(result.get("output_15m", "-"))}</strong></div>
          <div><span>聚合1小时CSV</span><strong>{_e(result.get("output_1h", "-"))}</strong></div>
        </div>
      </section>

      <section class="span-6">
        <h2>数据规模</h2>
        <div class="kv">
          <div><span>15分钟K线数量</span><strong>{_n(q15.get("candle_count"))}</strong></div>
          <div><span>1小时K线数量</span><strong>{_n(q1h.get("candle_count"))}</strong></div>
          <div><span>开始时间</span><strong>{_e(q15.get("first_candle", "-"))}</strong></div>
          <div><span>结束时间</span><strong>{_e(q15.get("last_candle", "-"))}</strong></div>
        </div>
      </section>

      <section class="span-6">
        <h2>15分钟质量指标</h2>
        <div class="kv">
          <div><span>时间断档</span><strong>{_n(q15.get("gap_count"))}</strong></div>
          <div><span>重复时间戳</span><strong>{_n(q15.get("duplicate_timestamps"))}</strong></div>
          <div><span>顺序异常</span><strong>{_n(q15.get("out_of_order_count"))}</strong></div>
          <div><span>OHLC异常</span><strong>{_n(q15.get("ohlc_error_count"))}</strong></div>
        </div>
      </section>

      <section class="span-6">
        <h2>1小时质量指标</h2>
        <div class="kv">
          <div><span>时间断档</span><strong>{_n(q1h.get("gap_count"))}</strong></div>
          <div><span>重复时间戳</span><strong>{_n(q1h.get("duplicate_timestamps"))}</strong></div>
          <div><span>顺序异常</span><strong>{_n(q1h.get("out_of_order_count"))}</strong></div>
          <div><span>OHLC异常</span><strong>{_n(q1h.get("ohlc_error_count"))}</strong></div>
        </div>
      </section>

      <section class="span-12">
        <h2>建议</h2>
        <ul>{recommendations}</ul>
      </section>
    </div>
  </main>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")


def _dedupe_and_sort(candles: list[Candle]) -> list[Candle]:
    by_time: dict[str, Candle] = {}
    for candle in candles:
        by_time[candle.timestamp] = candle
    return sorted(by_time.values(), key=lambda candle: candle.timestamp)


def _recommendations(q15: dict[str, Any], q1h: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    if q15["status"] == "ok" and q1h["status"] == "ok":
        notes.append("数据质量正常，可以继续跑双周期回测和分段稳健性验证。")
    else:
        notes.append("数据存在质量问题，建议先修复后再回测。")
    if q15.get("gap_count"):
        notes.append("15分钟数据存在时间断档，可能导致信号遗漏或回测偏差。")
    if q15.get("duplicate_timestamps"):
        notes.append("已按时间戳去重，重复数据可能来自下载源或拼接过程。")
    if q15.get("ohlc_error_count") or q1h.get("ohlc_error_count"):
        notes.append("存在高低开收关系异常，请检查 CSV 是否列顺序或字段映射错误。")
    return notes


def _ready_label(value: object) -> str:
    return "可以" if value else "暂缓"


def _ready_class(value: object) -> str:
    return "status-ok" if value else "status-bad"


def _quality_label(value: object) -> str:
    if value == "ok":
        return "正常"
    if value == "warning":
        return "有提醒"
    if value == "bad":
        return "需处理"
    return "未知"


def _n(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    return _e(value)


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)
