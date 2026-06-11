# Crypto Trading Agent MVP

这是一个安全优先的加密货币交易智能体第一版。它不会连接实盘账户，也不会保存交易所密钥；当前目标是完成“行情分析 -> 信号判断 -> 风险过滤 -> 纸上交易计划 -> 本地面板查看”的闭环。

## 你需要准备什么

1. Python 3.10 或更高版本。
2. 一个明确的交易标的，例如 `BTCUSDT`、`ETHUSDT`。
3. 第一版不需要交易所 API Key。
4. 如果之后要接实盘，需要单独准备交易所 API Key，并且只给最小权限，先不要开提现权限。

你当前电脑的系统 Python 启动器暂时不可用，所以脚本会自动使用 Codex 自带 Python 运行时。

## 已经包含的能力

- 读取样例 K 线数据，或从 CSV 读取你自己的行情数据。
- 可选拉取 Binance 公开 K 线行情，不需要 API Key。
- 可选拉取 Coinbase 公开 K 线行情，不需要交易权限。
- 计算 EMA、SMA、RSI、ATR 等基础指标。
- 根据趋势、动量和波动生成 `LONG` / `SHORT` / `HOLD` 建议。
- 默认禁止做空，适合第一版现货模拟。
- 风控模块会限制高风险信号、低置信度信号和过大仓位。
- 纸上交易模块会计算建议仓位，并把模拟订单写入 `runs/paper_ledger.jsonl`。
- 自动生成本地 HTML 面板：`runs/dashboard.html`。

## 快速运行

```powershell
powershell -ExecutionPolicy Bypass -File .\run_sample.ps1
```

运行后会生成：

- `runs/latest_signal.json`：最近一次智能体分析结果。
- `runs/dashboard.html`：本地可视化面板。
- `runs/paper_ledger.jsonl`：纸上交易记录。只有当信号通过风控时才会写入订单。

## 打开面板

在文件管理器里打开：

```text
C:\Users\MECHREVO\Desktop\AI\deal\runs\dashboard.html
```

也可以在 PowerShell 里运行：

```powershell
start .\runs\dashboard.html
```

## 打开量化交易工作台

更推荐启动本地行情服务：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_trading_desk_server.ps1
```

然后打开：

```text
http://127.0.0.1:8765
```

通过本地服务打开时，页面会走本地 `/api/candles` 接口获取 OKX、Binance、Coinbase 公开 K 线。默认选择“自动行情源”，会先尝试 OKX，失败时再尝试 Binance 和 Coinbase。

交易工作台支持：

- TradingView 风格 K 线图。
- 15分钟 / 1小时周期切换。
- 自动刷新行情。
- SMA20、EMA12、EMA26、RSI14、ATR 指标。
- 后端智能体信号、风控结果和模拟交易计划。
- 图表上的入场、止损、止盈计划线。
- 图表上的 `AI` / `ME` 操作记录点。
- 本人手动操作记录。
- 智能体建议记录。
- 操作记录 CSV 导出。
- 本地 CSV 导入。

注意：工作台不会真实下单，不需要 API Key，也不会连接你的交易所账户。所有手动记录和智能体记录都只保存在浏览器本地。

也可以直接打开静态工作台：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_trading_desk.ps1
```

然后在浏览器里打开：

```text
C:\Users\MECHREVO\Desktop\AI\deal\trading_desk.html
```

但静态文件方式不能使用后端统一分析，优先使用 `http://127.0.0.1:8765`。

## 跑测试

```powershell
powershell -ExecutionPolicy Bypass -File .\run_tests.ps1
```

看到 `OK` 就说明基础代码可以正常运行。

## 跑回测

```powershell
powershell -ExecutionPolicy Bypass -File .\run_backtest.ps1
```

运行后会生成：

- `runs/backtest_result.json`：回测明细数据。
- `runs/backtest_report.html`：本地回测报告。

打开报告：

```powershell
start .\runs\backtest_report.html
```

## 跑长周期样例回测

```powershell
powershell -ExecutionPolicy Bypass -File .\run_long_backtest.ps1
```

运行后会生成：

- `data/sample_btcusdt_1h_long.csv`：约 60 天的 1小时样例 K 线。
- `runs/backtest_long_result.json`：长周期样例回测数据。
- `runs/backtest_long_report.html`：长周期样例回测报告。

打开报告：

```powershell
start .\runs\backtest_long_report.html
```

回测报告会自动检查数据质量，包括时间断档、重复时间戳、K 线高低价异常和顺序异常。

## 对比 15分钟 和 1小时 K 线

```powershell
powershell -ExecutionPolicy Bypass -File .\run_strategy_lab.ps1
```

运行后会生成：

- `data/sample_btcusdt_15m_60d.csv`：约 60 天的 15分钟样例 K 线。
- `data/sample_btcusdt_1h_from_15m_60d.csv`：由同一段 15分钟数据聚合出的 1小时 K 线。
- `runs/strategy_lab_result.json`：周期对比数据。
- `runs/strategy_lab_report.html`：周期对比报告。

打开报告：

```powershell
start .\runs\strategy_lab_report.html
```

15分钟 K 线适合做更细的入场，但不等于真正的高频交易。第一版建议用 1小时 K 线判断大方向，再用 15分钟 K 线找入场，且只做模拟盘。

## 跑双周期多空回测

```powershell
powershell -ExecutionPolicy Bypass -File .\run_dual_timeframe.ps1
```

运行后会生成：

- `data/sample_dual_15m_60d.csv`：双周期回测用的 15分钟样例 K 线。
- `data/sample_dual_1h_60d.csv`：由同一段 15分钟数据聚合出的 1小时趋势 K 线。
- `runs/dual_timeframe_result.json`：双周期多空回测数据。
- `runs/dual_timeframe_report.html`：双周期多空回测报告。

打开报告：

```powershell
start .\runs\dual_timeframe_report.html
```

这个策略用 1小时 K 线判断做多或做空方向，用 15分钟 K 线寻找入场。做空只用于模拟和回测，不会改变默认现货模拟配置。

报告里还包含三档成本压力测试：

- 轻度成本：低滑点、低做空资金费率。
- 正常成本：更接近真实交易成本的保守估计。
- 严苛成本：用于检查策略是否过度依赖理想成交。

如果正常成本或严苛成本下收益转负，就不能进入实盘阶段。

## 用真实 15分钟 CSV 跑双周期回测

如果你有真实历史 15分钟 K 线 CSV，可以运行：

```powershell
python -m crypto_agent.dual_timeframe_cli --source csv --csv-15m path\to\your_15m.csv --output runs\real_dual_result.json --report runs\real_dual_report.html
```

CSV 至少需要时间、开、高、低、收、成交量六列。列名可以是：

```text
timestamp,open,high,low,close,volume
```

也兼容常见别名，比如 `Open Time`、`datetime`、`Open`、`High`、`Low`、`Close`、`Volume`。时间可以是 ISO 字符串，也可以是 Unix 秒/毫秒时间戳。

如果只有 15分钟 CSV，程序会自动聚合出 1小时趋势 K 线。如果你也有 1小时 CSV，可以额外传：

```powershell
python -m crypto_agent.dual_timeframe_cli --source csv --csv-15m path\to\your_15m.csv --csv-1h path\to\your_1h.csv
```

当前电脑系统 Python 不可用时，可以先用示例 CSV 脚本验证流程：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_dual_timeframe_csv.ps1
```

## 跑分段稳健性验证

```powershell
powershell -ExecutionPolicy Bypass -File .\run_walk_forward.ps1
```

运行后会生成：

- `runs/walk_forward_result.json`：分段稳健性数据。
- `runs/walk_forward_report.html`：分段稳健性报告。

打开报告：

```powershell
start .\runs\walk_forward_report.html
```

如果要用真实 15分钟 CSV：

```powershell
python -m crypto_agent.walk_forward_cli --source csv --csv-15m path\to\your_15m.csv --segment-days 14 --output runs\real_walk_forward_result.json --report runs\real_walk_forward_report.html
```

这个报告会把数据按固定时间段切开，每段独立跑双周期多空策略，并展示严苛成本下每段是否还赚钱。它的目标是发现过拟合：如果只有一段赚钱，其它分段都亏，就不能进入实盘阶段。

## 准备真实CSV数据

在拿真实历史数据回测前，先运行数据准备器：

```powershell
python -m crypto_agent.prepare_data_cli --source csv --input-csv path\to\your_15m.csv --output-15m data\prepared_15m.csv --output-1h data\prepared_1h.csv --output runs\prepare_data_result.json --report runs\prepare_data_report.html
```

它会做四件事：

- 标准化 15分钟 CSV。
- 自动聚合 1小时 K 线。
- 检查时间断档、重复时间戳、OHLC异常。
- 生成数据导入报告。

当前电脑系统 Python 不可用时，可以先运行样例脚本：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_prepare_data.ps1
```

打开报告：

```powershell
start .\runs\prepare_data_report.html
```

如果要用示例 CSV 测试真实 CSV 流程：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_prepare_data_csv.ps1
```

## 尝试公开实时行情

这个命令会尝试从 Binance 公开接口拉取 K 线，不需要 API Key：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_binance.ps1
```

也可以尝试 Coinbase 公开行情：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_coinbase.ps1
```

如果本地网络无法访问交易所接口，脚本会自动退回样例数据，并在输出里写 `data_source: sample_fallback`。

## 使用自定义 CSV

CSV 至少需要这些列：

```text
timestamp,open,high,low,close,volume
```

示例：

```powershell
python -m crypto_agent.cli --source csv --csv data/sample_btcusdt_1h.csv --paper-trade
```

如果系统 Python 还不能用，可以把 `python` 换成 Codex 自带 Python 路径，或者告诉我继续帮你做一个 CSV 专用脚本。

## 配置

编辑 `config.example.json` 可以调整：

- `symbol`：交易标的。
- `interval`：K 线周期。
- `risk_per_trade`：单笔最大风险比例。
- `max_position_usd`：单笔最大名义仓位。
- `min_confidence`：最低信号置信度。
- `max_risk_score`：最高允许风险分数。
- `allow_short`：是否允许做空建议，第一版默认 `false`。

## 市场情报报告

运行下面的命令可以拉取公开市场数据并生成综合观点：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_market_intelligence.ps1
```

它会尝试补齐这些信息：

- 实盘公开 K 线：默认自动尝试 OKX、Binance、Coinbase。
- 订单簿：统计近端买卖盘厚度、点差和大额挂单墙。
- 资金费率：判断合约多空拥挤度。
- 新闻风险：读取公开 RSS 新闻并标注风险关键词。
- 交易观点：汇总趋势、波动、支撑阻力、盘口、资金费率和事件风险。

输出文件：

- `runs/market_intelligence_result.json`
- `runs/market_intelligence_report.html`
- `data/market_intelligence_latest.csv`

注意：市场情报报告只生成研究观点和纸上动作，不连接交易所账户，不真实下单。

## 重要提醒

这个项目只用于研究、回测和模拟交易，不构成投资建议。不要把第一版直接改成自动实盘交易。接实盘前至少要补齐：历史回测、连续模拟盘、异常熔断、日志监控、人工确认和 API 权限隔离。
