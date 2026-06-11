from __future__ import annotations

import html
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from crypto_agent.config import AgentConfig
from crypto_agent.data_quality import review_candles
from crypto_agent.indicators import latest_indicator_snapshot
from crypto_agent.market_data import Candle
from crypto_agent.paper_trading import build_paper_order
from crypto_agent.risk import review_signal
from crypto_agent.strategy import build_signal
from crypto_agent.technical_analysis import build_technical_snapshot


@dataclass(frozen=True)
class BacktestTrade:
    entry_time: str
    exit_time: str
    side: str
    entry: float
    exit: float
    stop_loss: float
    take_profit: float
    quantity: float
    gross_pnl: float
    fees: float
    net_pnl: float
    return_pct: float
    exit_reason: str


@dataclass
class BacktestPosition:
    entry_index: int
    entry_time: str
    side: str
    entry: float
    stop_loss: float
    initial_stop_loss: float
    take_profit: float
    quantity: float
    entry_fee: float


def run_backtest(config: AgentConfig, candles: list[Candle]) -> dict[str, Any]:
    if len(candles) < 40:
        raise ValueError("Need at least 40 candles for a useful backtest.")

    cash = config.starting_cash
    equity = cash
    peak_equity = equity
    max_drawdown_pct = 0.0
    trades: list[BacktestTrade] = []
    position: BacktestPosition | None = None
    lookback = 30

    for index in range(lookback, len(candles)):
        candle = candles[index]

        if position and index > position.entry_index:
            exit_price, exit_reason = _exit_for_candle(position, candle)
            if exit_price is not None and exit_reason:
                trade = _close_position(config, position, candle, exit_price, exit_reason)
                cash += trade.net_pnl
                equity = cash
                trades.append(trade)
                position = None

        if position is None and index < len(candles) - 1:
            window = candles[: index + 1]
            indicators = latest_indicator_snapshot(window)
            technicals = build_technical_snapshot(window)
            signal = build_signal(
                indicators,
                allow_short=config.allow_short,
                technicals=technicals,
            )
            review = review_signal(config, indicators, signal)
            order = build_paper_order(config, signal) if review.allowed else None
            if order:
                position = BacktestPosition(
                    entry_index=index,
                    entry_time=candle.timestamp,
                    side=order.side,
                    entry=order.entry,
                    stop_loss=order.stop_loss,
                    initial_stop_loss=order.stop_loss,
                    take_profit=order.take_profit,
                    quantity=order.quantity,
                    entry_fee=order.estimated_fee,
                )

        if position:
            mark_price = candle.close
            unrealized = _gross_pnl(position.side, position.entry, mark_price, position.quantity)
            equity = cash + unrealized - position.entry_fee

        peak_equity = max(peak_equity, equity)
        drawdown_pct = ((peak_equity - equity) / peak_equity) * 100 if peak_equity else 0.0
        max_drawdown_pct = max(max_drawdown_pct, drawdown_pct)

    if position:
        final_candle = candles[-1]
        trade = _close_position(config, position, final_candle, final_candle.close, "回测结束平仓")
        cash += trade.net_pnl
        equity = cash
        trades.append(trade)

    wins = [trade for trade in trades if trade.net_pnl > 0]
    losses = [trade for trade in trades if trade.net_pnl <= 0]
    gross_profit = sum(trade.net_pnl for trade in wins)
    gross_loss = abs(sum(trade.net_pnl for trade in losses))
    total_fees = sum(trade.fees for trade in trades)
    net_profit = cash - config.starting_cash

    result: dict[str, Any] = {
        "symbol": config.symbol,
        "interval": config.interval,
        "starting_cash": round(config.starting_cash, 2),
        "ending_equity": round(cash, 2),
        "net_profit": round(net_profit, 2),
        "return_pct": round((net_profit / config.starting_cash) * 100, 4),
        "max_drawdown_pct": round(max_drawdown_pct, 4),
        "total_trades": len(trades),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate_pct": round((len(wins) / len(trades)) * 100, 2) if trades else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else None,
        "total_fees": round(total_fees, 2),
        "first_candle": candles[0].timestamp,
        "last_candle": candles[-1].timestamp,
        "data_quality": review_candles(candles, config.interval),
        "trades": [asdict(trade) for trade in trades],
    }
    return result


def save_backtest_json(result: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def render_backtest_report(result: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    trades = result.get("trades", [])
    recent_trades = trades[-12:]
    rows = "\n".join(_trade_row(trade) for trade in recent_trades)
    if not rows:
        rows = "<tr><td colspan=\"9\">这段数据没有产生交易。</td></tr>"
    data_quality = result.get("data_quality") or {}
    warning_items = "\n".join(
        f"<li>{_e(warning)}</li>" for warning in data_quality.get("warnings", [])
    )
    if not warning_items:
        warning_items = "<li>未发现明显数据质量问题。</li>"

    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Crypto Agent Backtest</title>
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
    .span-4 {{ grid-column: span 4; }}
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
    .status-ok {{ color: var(--green); }}
    .status-warning, .status-bad {{ color: var(--red); }}

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

    .table-wrap {{
      overflow-x: auto;
    }}

    .note {{
      margin-top: 12px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.55;
    }}

    .quality-grid {{
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 12px;
    }}

    .quality-grid div {{
      border: 1px solid #edf0f4;
      border-radius: 8px;
      padding: 12px;
      min-height: 72px;
    }}

    .quality-grid span {{
      display: block;
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 8px;
    }}

    .quality-grid strong {{
      font-size: 20px;
    }}

    .quality-notes {{
      margin: 14px 0 0;
      padding-left: 20px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.6;
    }}

    @media (max-width: 860px) {{
      .span-3, .span-4, .span-12 {{ grid-column: span 12; }}
      .quality-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      main {{ width: min(100% - 20px, 1180px); padding-top: 16px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{_e(result.get("symbol", "-"))} 回测报告</h1>
      <p class="subtitle">周期 {_e(result.get("interval", "-"))} · {_e(result.get("first_candle", "-"))} 到 {_e(result.get("last_candle", "-"))}</p>
    </header>

    <div class="grid">
      <section class="span-3">
        <div class="metric">
          <span>总收益率</span>
          <strong class="{_pnl_class(result.get("return_pct", 0))}">{_n(result.get("return_pct"))}%</strong>
        </div>
      </section>
      <section class="span-3">
        <div class="metric">
          <span>净收益</span>
          <strong class="{_pnl_class(result.get("net_profit", 0))}">{_n(result.get("net_profit"))}</strong>
        </div>
      </section>
      <section class="span-3">
        <div class="metric">
          <span>最大回撤</span>
          <strong>{_n(result.get("max_drawdown_pct"))}%</strong>
        </div>
      </section>
      <section class="span-3">
        <div class="metric">
          <span>胜率</span>
          <strong>{_n(result.get("win_rate_pct"))}%</strong>
        </div>
      </section>

      <section class="span-4">
        <div class="metric">
          <span>交易次数</span>
          <strong>{_n(result.get("total_trades"))}</strong>
        </div>
      </section>
      <section class="span-4">
        <div class="metric">
          <span>盈亏比因子</span>
          <strong>{_n(result.get("profit_factor"))}</strong>
        </div>
      </section>
      <section class="span-4">
        <div class="metric">
          <span>总手续费</span>
          <strong>{_n(result.get("total_fees"))}</strong>
        </div>
      </section>

      <section class="span-12">
        <h2>数据质量</h2>
        <div class="quality-grid">
          <div><span>状态</span><strong class="status-{_e(data_quality.get("status", "unknown"))}">{_quality_label(data_quality.get("status"))}</strong></div>
          <div><span>K线数量</span><strong>{_n(data_quality.get("candle_count"))}</strong></div>
          <div><span>时间断档</span><strong>{_n(data_quality.get("gap_count"))}</strong></div>
          <div><span>重复时间戳</span><strong>{_n(data_quality.get("duplicate_timestamps"))}</strong></div>
          <div><span>顺序异常</span><strong>{_n(data_quality.get("out_of_order_count"))}</strong></div>
          <div><span>OHLC异常</span><strong>{_n(data_quality.get("ohlc_error_count"))}</strong></div>
        </div>
        <ul class="quality-notes">{warning_items}</ul>
      </section>

      <section class="span-12">
        <h2>最近交易</h2>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>入场时间</th>
                <th>方向</th>
                <th>入场价</th>
                <th>出场价</th>
                <th>数量</th>
                <th>净盈亏</th>
                <th>收益率</th>
                <th>出场原因</th>
                <th>出场时间</th>
              </tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
        </div>
        <p class="note">回测是研究工具，不代表未来收益。第一版采用保守规则：同一根 K 线同时触及止损和止盈时，优先按止损处理。</p>
      </section>
    </div>
  </main>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")


def _exit_for_candle(
    position: BacktestPosition,
    candle: Candle,
) -> tuple[float | None, str | None]:
    if position.side == "LONG":
        if candle.low <= position.stop_loss:
            return position.stop_loss, "触发止损"
        if candle.high >= position.take_profit:
            return position.take_profit, "触发止盈"
        return None, None

    if candle.high >= position.stop_loss:
        return position.stop_loss, "触发止损"
    if candle.low <= position.take_profit:
        return position.take_profit, "触发止盈"
    return None, None


def _close_position(
    config: AgentConfig,
    position: BacktestPosition,
    candle: Candle,
    exit_price: float,
    exit_reason: str,
) -> BacktestTrade:
    gross_pnl = _gross_pnl(position.side, position.entry, exit_price, position.quantity)
    exit_fee = abs(exit_price * position.quantity) * (config.fee_bps / 10_000)
    fees = position.entry_fee + exit_fee
    net_pnl = gross_pnl - fees
    notional = position.entry * position.quantity
    return_pct = (net_pnl / notional) * 100 if notional else 0.0
    return BacktestTrade(
        entry_time=position.entry_time,
        exit_time=candle.timestamp,
        side=position.side,
        entry=round(position.entry, 2),
        exit=round(exit_price, 2),
        stop_loss=round(position.stop_loss, 2),
        take_profit=round(position.take_profit, 2),
        quantity=round(position.quantity, 8),
        gross_pnl=round(gross_pnl, 2),
        fees=round(fees, 2),
        net_pnl=round(net_pnl, 2),
        return_pct=round(return_pct, 4),
        exit_reason=exit_reason,
    )


def _gross_pnl(side: str, entry: float, exit_price: float, quantity: float) -> float:
    if side == "SHORT":
        return (entry - exit_price) * quantity
    return (exit_price - entry) * quantity


def _trade_row(trade: dict[str, Any]) -> str:
    pnl = trade.get("net_pnl", 0)
    return f"""<tr>
      <td>{_e(trade.get("entry_time", "-"))}</td>
      <td>{_e(_side_label(trade.get("side", "-")))}</td>
      <td>{_n(trade.get("entry"))}</td>
      <td>{_n(trade.get("exit"))}</td>
      <td>{_n(trade.get("quantity"))}</td>
      <td class="{_pnl_class(pnl)}">{_n(pnl)}</td>
      <td class="{_pnl_class(pnl)}">{_n(trade.get("return_pct"))}%</td>
      <td>{_e(trade.get("exit_reason", "-"))}</td>
      <td>{_e(trade.get("exit_time", "-"))}</td>
    </tr>"""


def _side_label(value: object) -> str:
    if value == "LONG":
        return "做多（LONG）"
    if value == "SHORT":
        return "做空（SHORT）"
    return str(value)


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
