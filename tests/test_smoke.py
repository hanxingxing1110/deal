import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from crypto_agent.agent import analyze_market
from crypto_agent.backtest import render_backtest_report, run_backtest
from crypto_agent.config import AgentConfig
from crypto_agent.data_quality import review_candles
from crypto_agent.dashboard import render_dashboard
from crypto_agent.dual_timeframe import (
    run_dual_timeframe_backtest,
    run_cost_stress_test,
    run_sample_dual_timeframe_experiment,
)
from crypto_agent.history_completion import SourceCandles, complete_history
from crypto_agent.market_data import (
    FundingRateSnapshot,
    NewsItem,
    OrderBookLevel,
    OrderBookSnapshot,
    generate_intraday_sample_candles,
    generate_research_sample_candles,
    generate_sample_candles,
    load_csv,
    resample_candles,
    save_candles_csv,
)
from crypto_agent.market_intelligence import (
    build_market_intelligence,
    render_market_intelligence_report,
)
from crypto_agent.paper_ledger import append_ledger_entry, clear_ledger, read_ledger, summarize_ledger
from crypto_agent.prepare_data import prepare_market_data, prepare_sample_market_data
from crypto_agent.segmented_validation import run_segmented_strategy_validation
from crypto_agent.strategy import StrategyParams
from crypto_agent.strategy_profiles import get_profile, list_profiles
from crypto_agent.strategy_lab import run_timeframe_experiment
from crypto_agent.strategy_optimizer import _candidate_params
from crypto_agent.technical_analysis import build_technical_snapshot
from crypto_agent.trading_desk_server import (
    _coinbase_product,
    _interval_meta,
    _normalize_interval,
    _normalize_limit,
    _normalize_start,
    _okx_inst_id,
    _readiness_notes,
    _source_order,
)
from crypto_agent.walk_forward import run_walk_forward


class AgentSmokeTest(unittest.TestCase):
    def test_sample_market_analysis_returns_decision(self) -> None:
        config = AgentConfig()
        candles = generate_sample_candles(120)
        result, _ = analyze_market(config, candles)

        self.assertIn(result["decision"], {"LONG", "SHORT", "HOLD"})
        self.assertIn("risk_score", result)
        self.assertIn("indicators", result)

    def test_dashboard_is_written(self) -> None:
        config = AgentConfig()
        candles = generate_sample_candles(120)
        result, _ = analyze_market(config, candles)

        with TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "dashboard.html"
            render_dashboard(result, output)

            self.assertTrue(output.exists())
            self.assertIn("Crypto Agent Dashboard", output.read_text(encoding="utf-8"))

    def test_backtest_returns_summary_and_report(self) -> None:
        config = AgentConfig()
        candles = generate_sample_candles(120)
        result = run_backtest(config, candles)

        self.assertIn("ending_equity", result)
        self.assertIn("total_trades", result)
        self.assertIn("data_quality", result)
        self.assertIn("trades", result)
        self.assertIn("advanced_metrics", result)

        with TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "backtest_report.html"
            render_backtest_report(result, output)

            self.assertTrue(output.exists())
            self.assertIn("Crypto Agent Backtest", output.read_text(encoding="utf-8"))

    def test_data_quality_accepts_clean_sample(self) -> None:
        candles = generate_research_sample_candles(240)
        result = review_candles(candles, "1h")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["gap_count"], 0)

    def test_resample_15m_to_1h(self) -> None:
        candles = generate_intraday_sample_candles(16)
        hourly = resample_candles(candles, 4)

        self.assertEqual(len(hourly), 4)
        self.assertEqual(hourly[0].open, candles[0].open)
        self.assertEqual(hourly[0].close, candles[3].close)

    def test_strategy_lab_compares_timeframes(self) -> None:
        config = AgentConfig()
        result = run_timeframe_experiment(config, days=5)

        self.assertIn("15m", result["timeframes"])
        self.assertIn("1h", result["timeframes"])
        self.assertIn("assessment", result)

    def test_dual_timeframe_backtest_runs(self) -> None:
        config = AgentConfig()
        result = run_sample_dual_timeframe_experiment(config, days=5, save_data=False)

        self.assertEqual(result["execution_interval"], "15m")
        self.assertEqual(result["trend_interval"], "1h")
        self.assertIn("long_trades", result)
        self.assertIn("short_trades", result)
        self.assertIn("cost_stress", result)

    def test_cost_stress_reduces_profit(self) -> None:
        trades = [
            {
                "entry_time": "2026-01-01T00:00:00+00:00",
                "exit_time": "2026-01-01T08:00:00+00:00",
                "side": "SHORT",
                "entry": 100.0,
                "exit": 90.0,
                "quantity": 1.0,
                "net_pnl": 10.0,
            }
        ]
        result = run_cost_stress_test(trades, 1000.0)

        self.assertLess(result[0]["net_profit"], 10.0)
        self.assertGreater(result[-1]["total_extra_cost"], result[0]["total_extra_cost"])

    def test_csv_loader_accepts_aliases_and_unix_milliseconds(self) -> None:
        with TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "candles.csv"
            csv_path.write_text(
                "Open Time,Open,High,Low,Close,Volume\n"
                "1767225600000,100,110,90,105,12\n"
                "1767226500000,105,115,95,108,13\n"
                "1767227400000,108,118,100,112,14\n"
                "1767228300000,112,119,101,111,15\n"
                "1767229200000,111,120,102,116,16\n"
                "1767230100000,116,121,103,117,17\n"
                "1767231000000,117,122,104,118,18\n"
                "1767231900000,118,123,105,119,19\n"
                "1767232800000,119,124,106,120,20\n"
                "1767233700000,120,125,107,121,21\n"
                "1767234600000,121,126,108,122,22\n"
                "1767235500000,122,127,109,123,23\n"
                "1767236400000,123,128,110,124,24\n"
                "1767237300000,124,129,111,125,25\n"
                "1767238200000,125,130,112,126,26\n"
                "1767239100000,126,131,113,127,27\n"
                "1767240000000,127,132,114,128,28\n"
                "1767240900000,128,133,115,129,29\n"
                "1767241800000,129,134,116,130,30\n"
                "1767242700000,130,135,117,131,31\n"
                "1767243600000,131,136,118,132,32\n"
                "1767244500000,132,137,119,133,33\n"
                "1767245400000,133,138,120,134,34\n"
                "1767246300000,134,139,121,135,35\n"
                "1767247200000,135,140,122,136,36\n"
                "1767248100000,136,141,123,137,37\n"
                "1767249000000,137,142,124,138,38\n"
                "1767249900000,138,143,125,139,39\n"
                "1767250800000,139,144,126,140,40\n"
                "1767251700000,140,145,127,141,41\n",
                encoding="utf-8",
            )
            candles = load_csv(csv_path)

        self.assertEqual(len(candles), 30)
        self.assertIn("+00:00", candles[0].timestamp)

    def test_dual_timeframe_backtest_accepts_csv_loaded_candles(self) -> None:
        config = AgentConfig()
        candles_15m = generate_intraday_sample_candles(240)
        candles_1h = resample_candles(candles_15m, 4)

        with TemporaryDirectory() as temp_dir:
            path_15m = Path(temp_dir) / "fifteen.csv"
            save_candles_csv(path_15m, candles_15m)
            loaded_15m = load_csv(path_15m)

        result = run_dual_timeframe_backtest(config, loaded_15m, candles_1h)
        self.assertEqual(result["execution_interval"], "15m")
        self.assertIn("cost_stress", result)

    def test_dual_timeframe_backtest_accepts_strategy_params(self) -> None:
        config = AgentConfig()
        candles_15m = generate_intraday_sample_candles(240)
        candles_1h = resample_candles(candles_15m, 4)
        params = StrategyParams(min_ema_gap_pct=0.03, hourly_min_ema_gap_pct=0.03)

        result = run_dual_timeframe_backtest(config, candles_15m, candles_1h, params)

        self.assertEqual(result["strategy_params"]["min_ema_gap_pct"], 0.03)
        self.assertEqual(result["strategy_params"]["hourly_min_ema_gap_pct"], 0.03)

    def test_strategy_optimizer_has_candidate_params(self) -> None:
        candidates = _candidate_params()

        self.assertGreater(len(candidates), 0)
        self.assertTrue(all(isinstance(item, StrategyParams) for item in candidates))

    def test_strategy_profiles_are_available(self) -> None:
        profiles = list_profiles()

        self.assertGreaterEqual(len(profiles), 3)
        self.assertEqual(get_profile(None).id, "win_rate_60_v1")
        self.assertEqual(get_profile("win_rate_60_v1").params.target_atr_mult, 1.0)
        self.assertEqual(get_profile("high_win_rate_v1").params.min_trend_efficiency, 0.14)
        self.assertEqual(get_profile("strict_trend_v1").id, "strict_trend_v1")
        self.assertEqual(get_profile("unknown").id, "win_rate_60_v1")

    def test_history_completion_fills_missing_candles_from_secondary_source(self) -> None:
        candles = generate_sample_candles(6)
        primary = [candles[0], candles[1], candles[3], candles[4], candles[5]]
        completed, report = complete_history(
            [
                SourceCandles("okx", primary),
                SourceCandles("binance", candles),
            ],
            interval_seconds=3600,
            limit=6,
        )

        self.assertEqual(len(completed), 6)
        self.assertEqual(completed[2].timestamp, candles[2].timestamp)
        self.assertEqual(report["filled_from_secondary"], 1)
        self.assertEqual(report["gap_count"], 0)

    def test_segmented_validation_compares_strategies(self) -> None:
        config = AgentConfig()
        candles_15m = generate_intraday_sample_candles(7 * 24 * 4)
        result = run_segmented_strategy_validation(
            config,
            candles_15m,
            {
                "baseline": StrategyParams(),
                "trend_filter": StrategyParams(min_ema_gap_pct=0.03),
            },
            segment_days=7,
        )

        self.assertEqual(result["segment_count"], 1)
        self.assertIn("baseline", result["strategies"])
        self.assertIn("trend_filter", result["strategies"])
        self.assertEqual(len(result["comparison"]), 2)

    def test_walk_forward_splits_segments(self) -> None:
        config = AgentConfig()
        candles_15m = generate_intraday_sample_candles(14 * 24 * 4 * 2)
        result = run_walk_forward(config, candles_15m, segment_days=14)

        self.assertEqual(result["segment_count"], 2)
        self.assertIn("segments", result)
        self.assertIn("assessment", result)

    def test_prepare_market_data_outputs_standard_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            input_csv = Path(temp_dir) / "input.csv"
            output_15m = Path(temp_dir) / "prepared_15m.csv"
            output_1h = Path(temp_dir) / "prepared_1h.csv"
            save_candles_csv(input_csv, generate_intraday_sample_candles(240))

            result = prepare_market_data(input_csv, output_15m, output_1h)

            self.assertTrue(result["ready_for_backtest"])
            self.assertTrue(output_15m.exists())
            self.assertTrue(output_1h.exists())

    def test_prepare_sample_market_data_runs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            result = prepare_sample_market_data(
                output_15m=Path(temp_dir) / "sample_15m.csv",
                output_1h=Path(temp_dir) / "sample_1h.csv",
                source_csv=Path(temp_dir) / "source.csv",
                days=5,
            )

            self.assertTrue(result["ready_for_backtest"])
            self.assertEqual(result["data_source"], "sample")

    def test_trading_desk_source_helpers(self) -> None:
        self.assertEqual(_okx_inst_id("BTCUSDT"), "BTC-USDT")
        self.assertEqual(_okx_inst_id("ETH-USDT"), "ETH-USDT")
        self.assertEqual(_coinbase_product("BTCUSDT"), "BTC-USD")
        self.assertEqual(_coinbase_product("ETH-USD"), "ETH-USD")
        self.assertEqual(_source_order("auto"), ["okx", "binance", "coinbase"])
        self.assertEqual(_source_order("binance"), ["binance", "okx", "coinbase"])
        self.assertEqual(_normalize_limit("5"), 30)
        self.assertEqual(_normalize_limit("999"), 999)
        self.assertEqual(_normalize_limit("999999"), 500000)
        self.assertEqual(_normalize_limit("all", "1s"), 86400)
        self.assertEqual(_normalize_limit("all", "1M"), 2000)
        self.assertEqual(_normalize_interval("1M"), "1M")
        self.assertEqual(_normalize_interval("1min"), "1m")
        self.assertEqual(_normalize_interval("1year"), "1y")
        self.assertEqual(_normalize_start("2012-01-01"), "2012-01-01")
        self.assertEqual(_normalize_start(""), None)
        self.assertEqual(_interval_meta("1d")["seconds"], 86400)

    def test_trading_desk_readiness_notes(self) -> None:
        notes = _readiness_notes(
            {
                "total_trades": 5,
                "return_pct": -1.2,
                "max_drawdown_pct": 9.0,
            }
        )

        self.assertGreaterEqual(len(notes), 3)

    def test_paper_ledger_persists_entries(self) -> None:
        with TemporaryDirectory() as temp_dir:
            ledger = Path(temp_dir) / "ledger.jsonl"
            clear_ledger(ledger)
            entry = append_ledger_entry(
                {
                    "symbol": "BTCUSDT",
                    "interval": "15m",
                    "market_source": "okx",
                    "source": "智能体",
                    "side": "LONG",
                    "price": 60000,
                    "quantity": 0.01,
                    "note": "test",
                    "candle_time": 1780000000,
                },
                ledger,
            )
            rows = read_ledger(ledger)
            summary = summarize_ledger(rows)

        self.assertEqual(entry.side, "LONG")
        self.assertEqual(len(rows), 1)
        self.assertEqual(summary["by_side"]["LONG"], 1)
        self.assertEqual(summary["notional_usd"], 600.0)

    def test_market_intelligence_builds_full_view(self) -> None:
        config = AgentConfig(symbol="BTCUSDT", interval="1h", allow_short=True)
        candles = generate_sample_candles(160)
        book = OrderBookSnapshot(
            source="test",
            symbol="BTCUSDT",
            timestamp="2026-06-10T00:00:00+00:00",
            bids=[
                OrderBookLevel(price=70000 - index, quantity=1 + index * 0.1, notional=(70000 - index) * (1 + index * 0.1))
                for index in range(40)
            ],
            asks=[
                OrderBookLevel(price=70001 + index, quantity=0.8 + index * 0.05, notional=(70001 + index) * (0.8 + index * 0.05))
                for index in range(40)
            ],
        )
        funding = FundingRateSnapshot(
            source="test",
            symbol="BTCUSDT",
            timestamp="2026-06-10T00:00:00+00:00",
            funding_rate=0.0001,
            next_funding_time="2026-06-10T08:00:00+00:00",
        )
        news = [
            NewsItem(
                source="test",
                title="Bitcoin ETF inflows rise as traders watch Fed decision",
                link="https://example.com/news",
                published_at="2026-06-10",
            )
        ]

        result = build_market_intelligence(
            config,
            candles,
            order_book=book,
            funding=funding,
            news=news,
        )

        self.assertEqual(result["mode"], "research_paper_only")
        self.assertIn(result["trade_view"]["stance"], {"long", "short", "wait"})
        self.assertTrue(result["order_book"]["available"])
        self.assertTrue(result["funding"]["available"])
        self.assertTrue(result["risk_events"]["available"])
        self.assertIsNotNone(result["support_resistance"]["nearest_support"])
        self.assertIsNotNone(result["support_resistance"]["nearest_resistance"])

        with TemporaryDirectory() as temp_dir:
            report = Path(temp_dir) / "market_intelligence.html"
            render_market_intelligence_report(result, report)

            self.assertTrue(report.exists())
            self.assertIn("市场情报报告", report.read_text(encoding="utf-8"))

    def test_technical_snapshot_contains_chart_tools(self) -> None:
        candles = generate_intraday_sample_candles(320)
        snapshot = build_technical_snapshot(candles)

        self.assertIn("fibonacci", snapshot)
        self.assertIn("market_structure", snapshot)
        self.assertIn("bollinger", snapshot)
        self.assertIn("vwap", snapshot)
        self.assertIn("macd", snapshot)
        self.assertIn("divergence", snapshot)
        self.assertIn("candlestick_patterns", snapshot)
        self.assertIn("volume_profile", snapshot)
        self.assertGreater(len(snapshot["fibonacci"]["levels"]), 0)
        self.assertGreater(len(snapshot["volume_profile"]["bins"]), 0)
        self.assertIn(snapshot["market_structure"]["bias"], {"bullish", "bearish", "neutral"})


if __name__ == "__main__":
    unittest.main()
