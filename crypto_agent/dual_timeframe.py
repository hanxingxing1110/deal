from __future__ import annotations

import html
import json
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crypto_agent.backtest import (
    BacktestPosition,
    _close_position,
    _exit_for_candle,
    _gross_pnl,
)
from crypto_agent.config import AgentConfig
from crypto_agent.data_quality import review_candles
from crypto_agent.indicators import latest_indicator_snapshot
from crypto_agent.market_data import (
    Candle,
    generate_intraday_sample_candles,
    resample_candles,
    save_candles_csv,
)
from crypto_agent.paper_trading import build_paper_order
from crypto_agent.risk import review_signal
from crypto_agent.strategy import StrategyParams, build_signal
from crypto_agent.technical_analysis import build_technical_snapshot


COST_SCENARIOS = [
    {
        "name": "轻度成本",
        "slippage_bps": 2.0,
        "short_funding_bps_per_8h": 1.0,
    },
    {
        "name": "正常成本",
        "slippage_bps": 5.0,
        "short_funding_bps_per_8h": 3.0,
    },
    {
        "name": "严苛成本",
        "slippage_bps": 10.0,
        "short_funding_bps_per_8h": 8.0,
    },
]


def run_dual_timeframe_backtest(
    config: AgentConfig,
    candles_15m: list[Candle],
    candles_1h: list[Candle],
    strategy_params: StrategyParams | None = None,
) -> dict[str, Any]:
    if len(candles_15m) < 160 or len(candles_1h) < 40:
        raise ValueError("Need at least 160 15m candles and 40 1h candles.")

    trade_config = replace(config, interval="15m", allow_short=True)
    cash = trade_config.starting_cash
    equity = cash
    peak_equity = equity
    max_drawdown_pct = 0.0
    trades = []
    position: BacktestPosition | None = None
    trend_counts = {"LONG": 0, "SHORT": 0, "HOLD": 0}
    blocked_by_trend = 0
    blocked_by_risk = 0
    entry_signals = {"LONG": 0, "SHORT": 0}
    lookback_15m = 30
    lookback_1h = 30
    group_size = 4
    strategy_params = strategy_params or StrategyParams()

    for index in range(lookback_15m, len(candles_15m)):
        candle = candles_15m[index]

        if position and index > position.entry_index:
            exit_price, exit_reason = _exit_for_candle(position, candle)
            if exit_price is not None and exit_reason:
                trade = _close_position(
                    trade_config,
                    position,
                    candle,
                    exit_price,
                    exit_reason,
                )
                cash += trade.net_pnl
                equity = cash
                trades.append(trade)
                position = None

        if position and index > position.entry_index:
            _update_dynamic_stop(
                position,
                candles_15m[: index + 1],
                strategy_params,
            )

        completed_1h_count = (index + 1) // group_size
        if completed_1h_count >= lookback_1h:
            trend = _hourly_trend(candles_1h[:completed_1h_count], strategy_params)
        else:
            trend = "HOLD"
        trend_counts[trend] += 1

        if position is None and index < len(candles_15m) - 1:
            window_15m = candles_15m[: index + 1]
            indicators_15m = latest_indicator_snapshot(window_15m)
            technicals_15m = build_technical_snapshot(window_15m)
            signal = build_signal(
                indicators_15m,
                allow_short=True,
                params=strategy_params,
                technicals=technicals_15m,
            )

            if signal.decision in {"LONG", "SHORT"} and signal.decision != trend:
                blocked_by_trend += 1
            elif signal.decision in {"LONG", "SHORT"}:
                review = review_signal(trade_config, indicators_15m, signal)
                order = build_paper_order(trade_config, signal) if review.allowed else None
                if order:
                    entry_signals[order.side] += 1
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
                else:
                    blocked_by_risk += 1

        if position:
            unrealized = _gross_pnl(
                position.side,
                position.entry,
                candle.close,
                position.quantity,
            )
            equity = cash + unrealized - position.entry_fee

        peak_equity = max(peak_equity, equity)
        drawdown_pct = ((peak_equity - equity) / peak_equity) * 100 if peak_equity else 0.0
        max_drawdown_pct = max(max_drawdown_pct, drawdown_pct)

    if position:
        final_candle = candles_15m[-1]
        trade = _close_position(
            trade_config,
            position,
            final_candle,
            final_candle.close,
            "回测结束平仓",
        )
        cash += trade.net_pnl
        trades.append(trade)

    wins = [trade for trade in trades if trade.net_pnl > 0]
    losses = [trade for trade in trades if trade.net_pnl <= 0]
    longs = [trade for trade in trades if trade.side == "LONG"]
    shorts = [trade for trade in trades if trade.side == "SHORT"]
    gross_profit = sum(trade.net_pnl for trade in wins)
    gross_loss = abs(sum(trade.net_pnl for trade in losses))
    total_fees = sum(trade.fees for trade in trades)
    net_profit = cash - trade_config.starting_cash

    result = {
        "symbol": trade_config.symbol,
        "execution_interval": "15m",
        "trend_interval": "1h",
        "starting_cash": round(trade_config.starting_cash, 2),
        "ending_equity": round(cash, 2),
        "net_profit": round(net_profit, 2),
        "return_pct": round((net_profit / trade_config.starting_cash) * 100, 4),
        "max_drawdown_pct": round(max_drawdown_pct, 4),
        "total_trades": len(trades),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate_pct": round((len(wins) / len(trades)) * 100, 2) if trades else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else None,
        "total_fees": round(total_fees, 2),
        "long_trades": len(longs),
        "short_trades": len(shorts),
        "long_net_pnl": round(sum(trade.net_pnl for trade in longs), 2),
        "short_net_pnl": round(sum(trade.net_pnl for trade in shorts), 2),
        "trend_counts": trend_counts,
        "entry_signals": entry_signals,
        "blocked_by_trend": blocked_by_trend,
        "blocked_by_risk": blocked_by_risk,
        "data_quality_15m": review_candles(candles_15m, "15m"),
        "data_quality_1h": review_candles(candles_1h, "1h"),
        "first_candle": candles_15m[0].timestamp,
        "last_candle": candles_15m[-1].timestamp,
        "strategy_params": asdict(strategy_params),
        "trades": [asdict(trade) for trade in trades],
    }
    result["cost_stress"] = run_cost_stress_test(result["trades"], trade_config.starting_cash)
    result["assessment"] = _assess_dual_result(
        net_profit=net_profit,
        max_drawdown_pct=max_drawdown_pct,
        trades=trades,
        blocked_by_trend=blocked_by_trend,
        blocked_by_risk=blocked_by_risk,
        cost_stress=result["cost_stress"],
    )
    return result


def run_sample_dual_timeframe_experiment(
    config: AgentConfig,
    days: int = 60,
    save_data: bool = True,
) -> dict[str, Any]:
    candles_15m = generate_intraday_sample_candles(days * 24 * 4)
    candles_1h = resample_candles(candles_15m, 4)
    if save_data:
        save_candles_csv("data/sample_dual_15m_60d.csv", candles_15m)
        save_candles_csv("data/sample_dual_1h_60d.csv", candles_1h)
    result = run_dual_timeframe_backtest(config, candles_15m, candles_1h)
    result["days"] = days
    result["data_source"] = "sample_dual_timeframe"
    return result


def save_dual_timeframe_json(result: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def render_dual_timeframe_report(result: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    trades = result.get("trades", [])
    recent_trades = trades[-14:]
    rows = "\n".join(_trade_row(trade) for trade in recent_trades)
    if not rows:
        rows = "<tr><td colspan=\"8\">这段数据没有产生交易。</td></tr>"
    stress_rows = "\n".join(_stress_row(item) for item in result.get("cost_stress", []))
    if not stress_rows:
        stress_rows = "<tr><td colspan=\"9\">没有成本压力测试结果。</td></tr>"
    assessment = "\n".join(f"<li>{_e(item)}</li>" for item in result.get("assessment", []))
    if not assessment:
        assessment = "<li>没有额外评估。</li>"

    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Crypto Agent Dual Timeframe</title>
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
    .span-4 {{ grid-column: span 4; }}
    .span-6 {{ grid-column: span 6; }}
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

    .mini-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
    }}

    .mini-grid div {{
      border: 1px solid #edf0f4;
      border-radius: 8px;
      padding: 12px;
      min-height: 72px;
    }}

    .mini-grid span {{
      display: block;
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 8px;
    }}

    .mini-grid strong {{ font-size: 20px; }}

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
      .span-3, .span-4, .span-6, .span-12 {{ grid-column: span 12; }}
      .mini-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      main {{ width: min(100% - 20px, 1180px); padding-top: 16px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{_e(result.get("symbol", "-"))} 双周期多空回测</h1>
      <p class="subtitle">1小时 K 线判断趋势方向，15分钟 K 线执行入场；允许做多和做空。</p>
    </header>

    <div class="grid">
      <section class="span-3">
        <div class="metric">
          <span>收益率</span>
          <strong class="{_pnl_class(result.get("return_pct"))}">{_n(result.get("return_pct"))}%</strong>
        </div>
      </section>
      <section class="span-3">
        <div class="metric">
          <span>净收益</span>
          <strong class="{_pnl_class(result.get("net_profit"))}">{_n(result.get("net_profit"))}</strong>
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

      <section class="span-6">
        <h2>交易分布</h2>
        <div class="mini-grid">
          <div><span>总交易</span><strong>{_n(result.get("total_trades"))}</strong></div>
          <div><span>做多交易</span><strong>{_n(result.get("long_trades"))}</strong></div>
          <div><span>做空交易</span><strong>{_n(result.get("short_trades"))}</strong></div>
          <div><span>做多净盈亏</span><strong class="{_pnl_class(result.get("long_net_pnl"))}">{_n(result.get("long_net_pnl"))}</strong></div>
          <div><span>做空净盈亏</span><strong class="{_pnl_class(result.get("short_net_pnl"))}">{_n(result.get("short_net_pnl"))}</strong></div>
          <div><span>总手续费</span><strong>{_n(result.get("total_fees"))}</strong></div>
        </div>
      </section>

      <section class="span-6">
        <h2>趋势过滤</h2>
        <div class="mini-grid">
          <div><span>1小时多头状态</span><strong>{_n((result.get("trend_counts") or {}).get("LONG"))}</strong></div>
          <div><span>1小时空头状态</span><strong>{_n((result.get("trend_counts") or {}).get("SHORT"))}</strong></div>
          <div><span>1小时观望状态</span><strong>{_n((result.get("trend_counts") or {}).get("HOLD"))}</strong></div>
          <div><span>趋势拦截信号</span><strong>{_n(result.get("blocked_by_trend"))}</strong></div>
          <div><span>风控拦截信号</span><strong>{_n(result.get("blocked_by_risk"))}</strong></div>
          <div><span>盈亏比因子</span><strong>{_n(result.get("profit_factor"))}</strong></div>
        </div>
      </section>

      <section class="span-12">
        <h2>成本压力测试</h2>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>情景</th>
                <th>滑点</th>
                <th>做空资金费率</th>
                <th>收益率</th>
                <th>净收益</th>
                <th>胜率</th>
                <th>最大回撤</th>
                <th>盈亏比因子</th>
                <th>额外成本</th>
              </tr>
            </thead>
            <tbody>{stress_rows}</tbody>
          </table>
        </div>
        <p class="note">滑点按入场和出场各扣一次；资金费率按做空仓位持仓时长保守扣除。这里是压力测试，不代表真实交易所的准确费率。</p>
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
              </tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
        </div>
        <p class="note">做空只在回测中开启。真实做空通常涉及合约、保证金或借币机制，必须额外控制强平、资金费率和交易所风险。</p>
      </section>

      <section class="span-12">
        <h2>评估</h2>
        <ul>{assessment}</ul>
      </section>
    </div>
  </main>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")


def _hourly_trend(
    hourly_candles: list[Candle],
    strategy_params: StrategyParams | None = None,
) -> str:
    strategy_params = strategy_params or StrategyParams()
    indicators = latest_indicator_snapshot(hourly_candles)
    close = indicators["close"]
    ema_12 = indicators["ema_12"]
    ema_26 = indicators["ema_26"]
    sma_20 = indicators["sma_20"]
    rsi_14 = indicators["rsi_14"]
    trend_efficiency_20 = indicators.get("trend_efficiency_20", 0.0)
    ema_gap_pct = (abs(ema_12 - ema_26) / close) * 100 if close else 0.0
    sma_gap_pct = (abs(close - sma_20) / close) * 100 if close else 0.0
    trend_strength_ok = (
        ema_gap_pct >= strategy_params.hourly_min_ema_gap_pct
        and sma_gap_pct >= strategy_params.hourly_min_sma_gap_pct
        and trend_efficiency_20 >= strategy_params.hourly_min_trend_efficiency
    )

    if (
        trend_strength_ok
        and ema_12 > ema_26
        and close > sma_20
        and rsi_14 < strategy_params.hourly_long_rsi_max
    ):
        return "LONG"
    if (
        trend_strength_ok
        and ema_12 < ema_26
        and close < sma_20
        and rsi_14 > strategy_params.hourly_short_rsi_min
    ):
        return "SHORT"
    return "HOLD"


def _update_dynamic_stop(
    position: BacktestPosition,
    candles: list[Candle],
    strategy_params: StrategyParams,
) -> None:
    risk_per_unit = abs(position.entry - position.initial_stop_loss)
    if risk_per_unit <= 0:
        return

    close = candles[-1].close
    if position.side == "LONG":
        favorable_r = (close - position.entry) / risk_per_unit
    else:
        favorable_r = (position.entry - close) / risk_per_unit

    if strategy_params.breakeven_at_r > 0 and favorable_r >= strategy_params.breakeven_at_r:
        if position.side == "LONG":
            position.stop_loss = max(position.stop_loss, position.entry)
        else:
            position.stop_loss = min(position.stop_loss, position.entry)

    if strategy_params.trailing_start_r <= 0 or favorable_r < strategy_params.trailing_start_r:
        return

    indicators = latest_indicator_snapshot(candles)
    atr_14 = indicators.get("atr_14", 0.0)
    if atr_14 <= 0:
        return

    if position.side == "LONG":
        trailing_stop = close - strategy_params.trailing_atr_mult * atr_14
        position.stop_loss = max(position.stop_loss, trailing_stop)
    else:
        trailing_stop = close + strategy_params.trailing_atr_mult * atr_14
        position.stop_loss = min(position.stop_loss, trailing_stop)


def run_cost_stress_test(
    trades: list[dict[str, Any]],
    starting_cash: float,
) -> list[dict[str, Any]]:
    return [
        _apply_cost_scenario(
            trades=trades,
            starting_cash=starting_cash,
            name=scenario["name"],
            slippage_bps=scenario["slippage_bps"],
            short_funding_bps_per_8h=scenario["short_funding_bps_per_8h"],
        )
        for scenario in COST_SCENARIOS
    ]


def _apply_cost_scenario(
    trades: list[dict[str, Any]],
    starting_cash: float,
    name: str,
    slippage_bps: float,
    short_funding_bps_per_8h: float,
) -> dict[str, Any]:
    cash = starting_cash
    peak_equity = cash
    max_drawdown_pct = 0.0
    adjusted_pnls: list[float] = []
    total_slippage_cost = 0.0
    total_funding_cost = 0.0

    for trade in trades:
        entry = float(trade["entry"])
        exit_price = float(trade["exit"])
        quantity = float(trade["quantity"])
        entry_notional = abs(entry * quantity)
        exit_notional = abs(exit_price * quantity)
        slippage_cost = (entry_notional + exit_notional) * (slippage_bps / 10_000)
        funding_cost = 0.0

        if trade.get("side") == "SHORT":
            hours = _trade_duration_hours(
                str(trade.get("entry_time")),
                str(trade.get("exit_time")),
            )
            funding_cost = entry_notional * (short_funding_bps_per_8h / 10_000) * (hours / 8)

        adjusted_pnl = float(trade["net_pnl"]) - slippage_cost - funding_cost
        cash += adjusted_pnl
        adjusted_pnls.append(adjusted_pnl)
        total_slippage_cost += slippage_cost
        total_funding_cost += funding_cost
        peak_equity = max(peak_equity, cash)
        drawdown_pct = ((peak_equity - cash) / peak_equity) * 100 if peak_equity else 0.0
        max_drawdown_pct = max(max_drawdown_pct, drawdown_pct)

    wins = [pnl for pnl in adjusted_pnls if pnl > 0]
    losses = [pnl for pnl in adjusted_pnls if pnl <= 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    net_profit = cash - starting_cash
    total_extra_cost = total_slippage_cost + total_funding_cost

    return {
        "name": name,
        "slippage_bps": slippage_bps,
        "short_funding_bps_per_8h": short_funding_bps_per_8h,
        "ending_equity": round(cash, 2),
        "net_profit": round(net_profit, 2),
        "return_pct": round((net_profit / starting_cash) * 100, 4),
        "max_drawdown_pct": round(max_drawdown_pct, 4),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate_pct": round((len(wins) / len(adjusted_pnls)) * 100, 2)
        if adjusted_pnls
        else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else None,
        "total_slippage_cost": round(total_slippage_cost, 2),
        "total_funding_cost": round(total_funding_cost, 2),
        "total_extra_cost": round(total_extra_cost, 2),
    }


def _assess_dual_result(
    net_profit: float,
    max_drawdown_pct: float,
    trades: list[Any],
    blocked_by_trend: int,
    blocked_by_risk: int,
    cost_stress: list[dict[str, Any]],
) -> list[str]:
    notes: list[str] = []
    if net_profit > 0:
        notes.append("双周期过滤后样例回测为正，但仍需要真实历史数据和滑点压力测试。")
    else:
        notes.append("双周期过滤后样例回测仍为负，不适合进入实盘。")
    if not trades:
        notes.append("策略过于保守，没有产生交易，需要检查趋势或入场条件。")
    if max_drawdown_pct > 3:
        notes.append("最大回撤偏高，做空和短周期执行都需要更严格限额。")
    if blocked_by_trend:
        notes.append(f"1小时趋势过滤拦截了 {blocked_by_trend} 个15分钟信号，说明多周期过滤正在发挥作用。")
    if blocked_by_risk:
        notes.append(f"风控拦截了 {blocked_by_risk} 个信号，后续可以检查这些信号是否过度保守。")
    normal_cost = _find_stress_case(cost_stress, "正常成本")
    severe_cost = _find_stress_case(cost_stress, "严苛成本")
    if normal_cost and normal_cost.get("net_profit", 0) <= 0:
        notes.append("正常成本压力测试后收益转负，说明策略很可能经不起真实交易成本。")
    elif normal_cost:
        notes.append("正常成本压力测试后仍为正，可以继续用真实历史数据验证。")
    if severe_cost and severe_cost.get("net_profit", 0) > 0:
        notes.append("严苛成本压力测试后仍为正，样例上的成本韧性较好。")
    elif severe_cost:
        notes.append("严苛成本压力测试后收益转弱，后续要重点控制滑点和资金费率。")
    notes.append("下一阶段应接入更长真实历史数据，再考虑模拟盘连续运行。")
    return notes


def _find_stress_case(
    cost_stress: list[dict[str, Any]],
    name: str,
) -> dict[str, Any] | None:
    for item in cost_stress:
        if item.get("name") == name:
            return item
    return None


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
    </tr>"""


def _stress_row(item: dict[str, Any]) -> str:
    net_profit = item.get("net_profit", 0)
    return f"""<tr>
      <td>{_e(item.get("name", "-"))}</td>
      <td>{_n(item.get("slippage_bps"))} bps</td>
      <td>{_n(item.get("short_funding_bps_per_8h"))} bps / 8h</td>
      <td class="{_pnl_class(item.get("return_pct"))}">{_n(item.get("return_pct"))}%</td>
      <td class="{_pnl_class(net_profit)}">{_n(net_profit)}</td>
      <td>{_n(item.get("win_rate_pct"))}%</td>
      <td>{_n(item.get("max_drawdown_pct"))}%</td>
      <td>{_n(item.get("profit_factor"))}</td>
      <td>{_n(item.get("total_extra_cost"))}</td>
    </tr>"""


def _trade_duration_hours(entry_time: str, exit_time: str) -> float:
    entry = _parse_time(entry_time)
    exit_at = _parse_time(exit_time)
    duration = (exit_at - entry).total_seconds() / 3600
    return max(0.0, duration)


def _parse_time(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _side_label(value: object) -> str:
    if value == "LONG":
        return "做多（LONG）"
    if value == "SHORT":
        return "做空（SHORT）"
    return str(value)


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
