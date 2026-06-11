from __future__ import annotations

import html
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from crypto_agent.config import AgentConfig
from crypto_agent.dual_timeframe import run_dual_timeframe_backtest
from crypto_agent.market_data import (
    Candle,
    fetch_binance_klines,
    resample_candles,
    save_candles_csv,
)
from crypto_agent.strategy import StrategyParams


def run_binance_strategy_optimization(
    config: AgentConfig,
    candle_limit: int = 3000,
    train_ratio: float = 0.7,
) -> dict[str, Any]:
    candles_15m = fetch_binance_klines(config.symbol, "15m", candle_limit)
    candles_1h = resample_candles(candles_15m, 4)
    save_candles_csv("data/real_binance_btcusdt_15m_latest.csv", candles_15m)
    save_candles_csv("data/real_binance_btcusdt_1h_from_15m_latest.csv", candles_1h)

    baseline_params = StrategyParams()
    baseline_all = run_dual_timeframe_backtest(config, candles_15m, candles_1h, baseline_params)

    split_index = _aligned_split_index(len(candles_15m), train_ratio)
    train_15m = candles_15m[:split_index]
    validate_15m = candles_15m[split_index:]
    train_1h = resample_candles(train_15m, 4)
    validate_1h = resample_candles(validate_15m, 4)
    if len(train_15m) < 160 or len(validate_15m) < 160:
        raise ValueError("Not enough candles after train/validation split.")

    candidates = []
    for params in _candidate_params():
        train_result = run_dual_timeframe_backtest(config, train_15m, train_1h, params)
        score = _score_result(train_result)
        candidates.append(
            {
                "params": asdict(params),
                "score": score,
                "train": _summary(train_result),
            }
        )

    candidates.sort(key=lambda item: item["score"], reverse=True)
    best_params = StrategyParams(**candidates[0]["params"])
    optimized_train = run_dual_timeframe_backtest(config, train_15m, train_1h, best_params)
    optimized_validate = run_dual_timeframe_backtest(config, validate_15m, validate_1h, best_params)
    optimized_all = run_dual_timeframe_backtest(config, candles_15m, candles_1h, best_params)
    baseline_train = run_dual_timeframe_backtest(config, train_15m, train_1h, baseline_params)
    baseline_validate = run_dual_timeframe_backtest(
        config,
        validate_15m,
        validate_1h,
        baseline_params,
    )

    result = {
        "symbol": config.symbol,
        "data_source": "binance_vision_public_klines",
        "requested_15m_candles": candle_limit,
        "actual_15m_candles": len(candles_15m),
        "actual_1h_candles": len(candles_1h),
        "first_candle": candles_15m[0].timestamp,
        "last_candle": candles_15m[-1].timestamp,
        "train_ratio": train_ratio,
        "train_first_candle": train_15m[0].timestamp,
        "train_last_candle": train_15m[-1].timestamp,
        "validate_first_candle": validate_15m[0].timestamp,
        "validate_last_candle": validate_15m[-1].timestamp,
        "candidate_count": len(candidates),
        "best_params": asdict(best_params),
        "top_candidates": candidates[:10],
        "baseline": {
            "all": _summary(baseline_all),
            "train": _summary(baseline_train),
            "validate": _summary(baseline_validate),
        },
        "optimized": {
            "all": _summary(optimized_all),
            "train": _summary(optimized_train),
            "validate": _summary(optimized_validate),
        },
        "assessment": _assess_optimization(baseline_validate, optimized_validate, optimized_all),
    }
    return result


def save_optimization_json(result: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def render_optimization_report(result: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    baseline = result["baseline"]
    optimized = result["optimized"]
    rows = "\n".join(
        [
            _result_row("原始策略-全量", baseline["all"]),
            _result_row("优化策略-全量", optimized["all"]),
            _result_row("原始策略-训练段", baseline["train"]),
            _result_row("优化策略-训练段", optimized["train"]),
            _result_row("原始策略-验证段", baseline["validate"]),
            _result_row("优化策略-验证段", optimized["validate"]),
        ]
    )
    params_rows = "\n".join(
        f"<tr><td>{_e(key)}</td><td>{_n(value)}</td></tr>"
        for key, value in result.get("best_params", {}).items()
    )
    assessment = "\n".join(f"<li>{_e(item)}</li>" for item in result.get("assessment", []))
    top_rows = "\n".join(_candidate_row(index + 1, item) for index, item in enumerate(result.get("top_candidates", [])))

    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Binance Strategy Optimization</title>
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
    main {{
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto;
      padding: 28px 0 40px;
    }}
    header {{
      padding-bottom: 18px;
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
    section {{
      margin-top: 16px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
    }}
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
      <h1>{_e(result.get("symbol", "-"))} Binance 策略优化</h1>
      <p class="subtitle">数据：{_e(result.get("first_candle", "-"))} 到 {_e(result.get("last_candle", "-"))}；前 {_n(result.get("train_ratio", 0) * 100)}% 训练，后段验证。</p>
    </header>

    <section>
      <h2>优化前后对比</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>口径</th>
              <th>交易次数</th>
              <th>胜率</th>
              <th>收益率</th>
              <th>净收益</th>
              <th>最大回撤</th>
              <th>盈亏比因子</th>
              <th>做多/做空</th>
              <th>正常成本收益率</th>
              <th>严苛成本收益率</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </section>

    <section>
      <h2>最佳参数</h2>
      <div class="table-wrap"><table><tbody>{params_rows}</tbody></table></div>
    </section>

    <section>
      <h2>候选参数前10</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>排名</th>
              <th>训练评分</th>
              <th>训练收益率</th>
              <th>训练胜率</th>
              <th>训练交易次数</th>
              <th>训练盈亏比</th>
            </tr>
          </thead>
          <tbody>{top_rows}</tbody>
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


def _candidate_params() -> list[StrategyParams]:
    params: list[StrategyParams] = []
    execution_filters = (
        (0.0, 0.0, 0.0),
        (0.03, 0.0, 0.0),
        (0.06, 0.0, 0.0),
        (0.10, 0.0, 0.0),
        (0.06, 0.04, 0.12),
        (0.10, 0.04, 0.18),
        (0.10, 0.08, 0.25),
    )
    hourly_filters = (
        (0.0, 0.0, 0.0),
        (0.03, 0.04, 0.0),
        (0.06, 0.04, 0.0),
        (0.06, 0.04, 0.12),
        (0.06, 0.04, 0.20),
    )
    for min_ema_gap, min_sma_gap, min_trend_efficiency in execution_filters:
        for atr_max in (1.0, 1.3, 1.7):
            for target_mult in (1.8, 2.2, 2.8):
                for hourly_ema_gap, hourly_sma_gap, hourly_trend_efficiency in hourly_filters:
                        params.append(
                            StrategyParams(
                                long_rsi_min=42,
                                long_rsi_max=66,
                                short_rsi_min=34,
                                short_rsi_max=58,
                                atr_pct_min=0.05,
                                atr_pct_max=atr_max,
                                min_ema_gap_pct=min_ema_gap,
                                min_sma_gap_pct=min_sma_gap,
                                min_trend_efficiency=min_trend_efficiency,
                                stop_atr_mult=1.2,
                                target_atr_mult=target_mult,
                                hourly_min_ema_gap_pct=hourly_ema_gap,
                                hourly_min_sma_gap_pct=hourly_sma_gap,
                                hourly_min_trend_efficiency=hourly_trend_efficiency,
                                hourly_long_rsi_max=70,
                                hourly_short_rsi_min=30,
                            )
                        )
    confirmation_filters = (
        (0.06, 0.04, 0.12, 1.10, 0.0),
        (0.06, 0.04, 0.12, 0.0, 1.10),
        (0.10, 0.04, 0.18, 1.10, 0.0),
        (0.10, 0.04, 0.18, 0.0, 1.15),
        (0.10, 0.08, 0.25, 1.20, 1.20),
    )
    for (
        min_ema_gap,
        min_sma_gap,
        min_trend_efficiency,
        min_volume_ratio,
        min_range_atr_ratio,
    ) in confirmation_filters:
        for atr_max in (1.0, 1.3):
            for target_mult in (1.8, 2.2, 2.8):
                for hourly_ema_gap, hourly_sma_gap, hourly_trend_efficiency in (
                    (0.03, 0.04, 0.0),
                    (0.06, 0.04, 0.12),
                    (0.06, 0.04, 0.20),
                ):
                    params.append(
                        StrategyParams(
                            long_rsi_min=42,
                            long_rsi_max=66,
                            short_rsi_min=34,
                            short_rsi_max=58,
                            atr_pct_min=0.05,
                            atr_pct_max=atr_max,
                            min_ema_gap_pct=min_ema_gap,
                            min_sma_gap_pct=min_sma_gap,
                            min_trend_efficiency=min_trend_efficiency,
                            min_volume_ratio=min_volume_ratio,
                            min_range_atr_ratio=min_range_atr_ratio,
                            stop_atr_mult=1.2,
                            target_atr_mult=target_mult,
                            hourly_min_ema_gap_pct=hourly_ema_gap,
                            hourly_min_sma_gap_pct=hourly_sma_gap,
                            hourly_min_trend_efficiency=hourly_trend_efficiency,
                            hourly_long_rsi_max=70,
                            hourly_short_rsi_min=30,
                        )
                    )
    directional_context_filters = (
        (0.06, 0.04, 0.12, 0.0, 0.0),
        (0.10, 0.04, 0.18, 0.0, 0.0),
        (0.10, 0.08, 0.25, 0.0, 0.0),
        (0.10, 0.08, 0.25, 1.10, 0.0),
        (0.10, 0.08, 0.25, 0.0, 1.15),
    )
    context_filters = (
        (0.0, 0.0),
        (0.5, -0.5),
        (1.0, -1.0),
        (1.5, -1.5),
    )
    for (
        min_ema_gap,
        min_sma_gap,
        min_trend_efficiency,
        min_volume_ratio,
        min_range_atr_ratio,
    ) in directional_context_filters:
        for min_long_3d_return_pct, max_short_3d_return_pct in context_filters:
            for target_mult in (1.8, 2.2, 2.8):
                params.append(
                    StrategyParams(
                        long_rsi_min=42,
                        long_rsi_max=66,
                        short_rsi_min=34,
                        short_rsi_max=58,
                        atr_pct_min=0.05,
                        atr_pct_max=1.0,
                        min_ema_gap_pct=min_ema_gap,
                        min_sma_gap_pct=min_sma_gap,
                        min_trend_efficiency=min_trend_efficiency,
                        min_volume_ratio=min_volume_ratio,
                        min_range_atr_ratio=min_range_atr_ratio,
                        min_long_3d_return_pct=min_long_3d_return_pct,
                        max_short_3d_return_pct=max_short_3d_return_pct,
                        stop_atr_mult=1.2,
                        target_atr_mult=target_mult,
                        hourly_min_ema_gap_pct=0.06,
                        hourly_min_sma_gap_pct=0.04,
                        hourly_min_trend_efficiency=0.20,
                        hourly_long_rsi_max=70,
                        hourly_short_rsi_min=30,
                    )
                )
    return params


def _aligned_split_index(length: int, train_ratio: float) -> int:
    raw = int(length * train_ratio)
    return max(160, raw - (raw % 4))


def _score_result(result: dict[str, Any]) -> float:
    trades = result["total_trades"]
    if trades < 12:
        return -9999.0
    normal_cost = _cost_case(result, "正常成本")
    normal_return = float(normal_cost.get("return_pct") or -99.0) if normal_cost else -99.0
    profit_factor = float(result.get("profit_factor") or 0.0)
    drawdown = float(result.get("max_drawdown_pct") or 0.0)
    win_rate = float(result.get("win_rate_pct") or 0.0)
    return normal_return * 4 + profit_factor * 1.8 + win_rate * 0.03 - drawdown * 0.7


def _summary(result: dict[str, Any]) -> dict[str, Any]:
    normal_cost = _cost_case(result, "正常成本")
    severe_cost = _cost_case(result, "严苛成本")
    return {
        "return_pct": result["return_pct"],
        "net_profit": result["net_profit"],
        "max_drawdown_pct": result["max_drawdown_pct"],
        "total_trades": result["total_trades"],
        "winning_trades": result["winning_trades"],
        "losing_trades": result["losing_trades"],
        "win_rate_pct": result["win_rate_pct"],
        "profit_factor": result["profit_factor"],
        "long_trades": result["long_trades"],
        "short_trades": result["short_trades"],
        "long_net_pnl": result["long_net_pnl"],
        "short_net_pnl": result["short_net_pnl"],
        "normal_cost_return_pct": normal_cost.get("return_pct") if normal_cost else None,
        "severe_cost_return_pct": severe_cost.get("return_pct") if severe_cost else None,
        "first_candle": result["first_candle"],
        "last_candle": result["last_candle"],
    }


def _assess_optimization(
    baseline_validate: dict[str, Any],
    optimized_validate: dict[str, Any],
    optimized_all: dict[str, Any],
) -> list[str]:
    notes: list[str] = []
    if optimized_validate["net_profit"] > baseline_validate["net_profit"]:
        notes.append("优化参数在验证段优于原始策略，但仍需继续做更长周期样本外验证。")
    else:
        notes.append("优化参数在验证段没有超过原始策略，不能采用。")
    normal_cost = _cost_case(optimized_all, "正常成本")
    if normal_cost and normal_cost.get("net_profit", 0) > 0:
        notes.append("优化后全量数据在正常成本下仍为正，可以进入更严格的分段验证。")
    else:
        notes.append("优化后全量数据在正常成本下仍不够稳，不能进入实盘。")
    if optimized_all["total_trades"] < 20:
        notes.append("优化后交易次数偏少，可能存在过拟合或样本不足。")
    notes.append("本优化只调整过滤和止盈止损参数，没有接入盘口深度、资金费率预测或宏观事件过滤。")
    return notes


def _cost_case(result: dict[str, Any], name: str) -> dict[str, Any] | None:
    for item in result.get("cost_stress", []):
        if item.get("name") == name:
            return item
    return None


def _result_row(label: str, item: dict[str, Any]) -> str:
    return f"""<tr>
      <td>{_e(label)}</td>
      <td>{_n(item.get("total_trades"))}</td>
      <td>{_n(item.get("win_rate_pct"))}%</td>
      <td class="{_pnl_class(item.get("return_pct"))}">{_n(item.get("return_pct"))}%</td>
      <td class="{_pnl_class(item.get("net_profit"))}">{_n(item.get("net_profit"))}</td>
      <td>{_n(item.get("max_drawdown_pct"))}%</td>
      <td>{_n(item.get("profit_factor"))}</td>
      <td>{_n(item.get("long_trades"))}/{_n(item.get("short_trades"))}</td>
      <td class="{_pnl_class(item.get("normal_cost_return_pct"))}">{_n(item.get("normal_cost_return_pct"))}%</td>
      <td class="{_pnl_class(item.get("severe_cost_return_pct"))}">{_n(item.get("severe_cost_return_pct"))}%</td>
    </tr>"""


def _candidate_row(rank: int, item: dict[str, Any]) -> str:
    train = item.get("train", {})
    return f"""<tr>
      <td>{rank}</td>
      <td>{_n(item.get("score"))}</td>
      <td class="{_pnl_class(train.get("return_pct"))}">{_n(train.get("return_pct"))}%</td>
      <td>{_n(train.get("win_rate_pct"))}%</td>
      <td>{_n(train.get("total_trades"))}</td>
      <td>{_n(train.get("profit_factor"))}</td>
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
