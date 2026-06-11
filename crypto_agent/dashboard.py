from __future__ import annotations

import html
from pathlib import Path
from typing import Any


FIELD_LABELS = {
    "close": "收盘价",
    "sma_20": "20周期简单移动平均线（SMA20）",
    "ema_12": "12周期指数移动平均线（EMA12）",
    "ema_26": "26周期指数移动平均线（EMA26）",
    "rsi_14": "14周期相对强弱指数（RSI14）",
    "atr_14": "14周期平均真实波幅（ATR14）",
    "atr_pct": "ATR占价格比例",
    "entry": "入场价",
    "stop_loss": "止损价",
    "take_profit": "止盈价",
    "created_at": "生成时间",
    "symbol": "交易标的",
    "side": "方向",
    "quantity": "数量",
    "notional_usd": "名义仓位（美元）",
    "estimated_fee": "预估手续费",
    "risk_amount": "计划风险金额",
}

VALUE_LABELS = {
    "LONG": "做多（LONG）",
    "SHORT": "做空（SHORT）",
    "HOLD": "观望（HOLD）",
}


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _label(key: object) -> str:
    return _escape(FIELD_LABELS.get(str(key), str(key)))


def _format_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, str) and value in VALUE_LABELS:
        return _escape(VALUE_LABELS[value])
    if isinstance(value, float):
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    return _escape(value)


def _badge_class(decision: str) -> str:
    if decision == "LONG":
        return "badge badge-long"
    if decision == "SHORT":
        return "badge badge-short"
    return "badge badge-hold"


def render_dashboard(result: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    decision = str(result.get("decision", "HOLD"))
    indicators = result.get("indicators", {})
    trade_plan = result.get("trade_plan", {})
    risk_blocks = result.get("risk_blocks") or []
    reasons = result.get("reasons") or []
    paper_order = result.get("paper_order")
    source_warning = result.get("source_warning")
    source_warning_html = ""
    if source_warning:
        source_warning_html = f"<p class=\"warning\">{_escape(source_warning)}</p>"

    indicator_rows = "\n".join(
        f"<div><span>{_label(key)}</span><strong>{_format_value(value)}</strong></div>"
        for key, value in indicators.items()
    )
    reason_items = "\n".join(f"<li>{_escape(reason)}</li>" for reason in reasons)
    block_items = "\n".join(f"<li>{_escape(block)}</li>" for block in risk_blocks)
    if not block_items:
        block_items = "<li>风控通过，可以生成纸上交易计划。</li>"

    paper_order_html = "<p class=\"muted\">本次没有生成纸上订单。</p>"
    if paper_order:
        paper_order_html = "".join(
            [
                "<div class=\"metric-list\">",
                *[
                    f"<div><span>{_label(key)}</span><strong>{_format_value(value)}</strong></div>"
                    for key, value in paper_order.items()
                ],
                "</div>",
            ]
        )

    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Crypto Agent Dashboard</title>
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
      --blue: #2969b0;
    }}

    * {{
      box-sizing: border-box;
    }}

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
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 18px;
      padding: 18px 0 22px;
      border-bottom: 1px solid var(--line);
    }}

    h1, h2, p {{
      margin: 0;
    }}

    h1 {{
      font-size: 28px;
      line-height: 1.2;
    }}

    h2 {{
      font-size: 16px;
      margin-bottom: 14px;
    }}

    .subtitle {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 14px;
    }}

    .badge {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 94px;
      height: 38px;
      padding: 0 14px;
      border-radius: 8px;
      color: #ffffff;
      font-weight: 700;
      font-size: 16px;
    }}

    .badge-long {{ background: var(--green); }}
    .badge-short {{ background: var(--red); }}
    .badge-hold {{ background: var(--amber); }}

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
    .span-8 {{ grid-column: span 8; }}
    .span-12 {{ grid-column: span 12; }}

    .big-number {{
      font-size: 30px;
      line-height: 1;
      font-weight: 700;
    }}

    .muted {{
      color: var(--muted);
      font-size: 14px;
      line-height: 1.55;
    }}

    .metric-list {{
      display: grid;
      gap: 10px;
    }}

    .metric-list div {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      min-height: 32px;
      padding-bottom: 8px;
      border-bottom: 1px solid #edf0f4;
    }}

    .metric-list div:last-child {{
      border-bottom: 0;
      padding-bottom: 0;
    }}

    .metric-list span {{
      color: var(--muted);
      font-size: 13px;
    }}

    .metric-list strong {{
      text-align: right;
      font-size: 14px;
    }}

    ul {{
      margin: 0;
      padding-left: 20px;
    }}

    li {{
      margin: 8px 0;
      line-height: 1.55;
    }}

    .risk-ok {{
      color: var(--green);
      font-weight: 700;
    }}

    .risk-blocked {{
      color: var(--red);
      font-weight: 700;
    }}

    .warning {{
      margin-top: 10px;
      color: var(--red);
      font-size: 13px;
      line-height: 1.5;
    }}

    @media (max-width: 760px) {{
      header {{
        flex-direction: column;
      }}

      .span-4,
      .span-6,
      .span-8,
      .span-12 {{
        grid-column: span 12;
      }}

      main {{
        width: min(100% - 20px, 1120px);
        padding-top: 16px;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>{_escape(result.get("symbol", "-"))} 智能体信号</h1>
        <p class="subtitle">周期 {_escape(result.get("interval", "-"))} · 数据源 {_escape(result.get("data_source", "-"))} · 最新 K 线 {_escape(result.get("latest_candle_time", "-"))}</p>
        {source_warning_html}
      </div>
      <span class="{_badge_class(decision)}">{_format_value(decision)}</span>
    </header>

    <div class="grid">
      <section class="span-4">
        <h2>置信度</h2>
        <p class="big-number">{_format_value(result.get("confidence", 0))}</p>
        <p class="muted">最低阈值由配置文件控制。</p>
      </section>

      <section class="span-4">
        <h2>风险分数</h2>
        <p class="big-number">{_format_value(result.get("risk_score", 0))}</p>
        <p class="muted">分数越高，越需要谨慎。</p>
      </section>

      <section class="span-4">
        <h2>风控状态</h2>
        <p class="big-number {'risk-ok' if result.get('risk_allowed') else 'risk-blocked'}">
          {'通过' if result.get('risk_allowed') else '拦截'}
        </p>
        <p class="muted">第一版宁愿少交易，也不追高。</p>
      </section>

      <section class="span-6">
        <h2>技术指标</h2>
        <div class="metric-list">{indicator_rows}</div>
      </section>

      <section class="span-6">
        <h2>交易计划</h2>
        <div class="metric-list">
          <div><span>{_label("entry")}</span><strong>{_format_value(trade_plan.get("entry"))}</strong></div>
          <div><span>{_label("stop_loss")}</span><strong>{_format_value(trade_plan.get("stop_loss"))}</strong></div>
          <div><span>{_label("take_profit")}</span><strong>{_format_value(trade_plan.get("take_profit"))}</strong></div>
        </div>
      </section>

      <section class="span-6">
        <h2>风控说明</h2>
        <ul>{block_items}</ul>
      </section>

      <section class="span-6">
        <h2>判断理由</h2>
        <ul>{reason_items}</ul>
      </section>

      <section class="span-12">
        <h2>纸上交易订单</h2>
        {paper_order_html}
      </section>
    </div>
  </main>
</body>
</html>
"""

    path.write_text(document, encoding="utf-8")
