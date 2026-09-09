# Stillwater（静水）— Low-Volatility Alpha for Tokenized US Stocks

Bitget AI Base Camp Hackathon S2 · Alpha Factory 赛道 · rToken Factor Strategies 子题

*"Still waters run deep."* — 在代币化美股的横截面上，波动最小的 20% 长期跑赢；我们要做的只是先把浑水滤掉。

## 论点

Bitget rToken（代币化美股）市场由散户主导、流动性分层明显。在本市场的横截面上：

1. **低波动异象显著且跨期稳定**：做多低波动五分位组合，IS（2025-09→2026-05）与 OS（2026-05→2026-09）Sharpe 均为正，且回撤约为等权基准的一半
2. **动量类因子样本外完全失效**（IS Sharpe 1.4~3.3 → OS ≈0 或负）——市场结构切换导致，本身即是 rToken 与原生股行为差异的证据
3. **流动性筛选是前置必要条件**：原始池中的"僵尸"标的（成交崩塌、持续阴跌）会污染任何多头组合

## 核心结果（`data/report.json`，可一键复现）

| 策略 | IS Sharpe | OS Sharpe | OS 年化 | OS 最大回撤 |
|---|---|---|---|---|
| **vol_40 + 流动性门槛（选定）** | 0.89 | **1.55** | 11.6% | -3.4% |
| dnvol_20 | 1.26 | 0.86 | 7.2% | -4.7% |
| vol_20 | 0.95 | 0.25 | 1.8% | -4.2% |
| 等权全池基准 | 1.55 | 1.76 | 38.3% | -6.9% |

- 成本敏感性（vol_40，OS Sharpe）：10bps → 1.55，20bps → 1.41，30bps → 1.27
- 周换手率仅 ~3.6%（低频、容量友好）
- 组合波动 ~7.5%（基准 ~22%），风险调整后优于基准

## 已验证并淘汰的因子（含证据）

| 因子 | 结论 |
|---|---|
| 动量 20/60/5-25d | OS Sharpe ≈0 或负；IS/OS 衰减踩评审警报线（OS < 0.5×IS） |
| 短期反转 5d | IS/OS 符号翻转（-1.33 / +2.01），不稳定 |
| 波动率状态切换 | 叠加反转后 OS -0.97，弃 |
| 朴素 rank 等权合成 | IS/OS 双负，弃 |
| 成交量 z-score | 极端低量端被僵尸标的污染 |
| Walk-forward 变体选择 | 追踪 Sharpe 择优持续追选刚失效的变体（OS 0.51），固定 vol_40 更稳 |

## 复现

```bash
pip install requests numpy pandas pytest
python3 src/run.py        # 数据抓取(官方SDK,增量缓存) -> 因子回测 -> data/report.json
```

数据：Bitget 公开现货 API（无需 key），116 个 rToken，日线 300 天（2025-09 → 至今），1min 粒度可扩展。

## 结构

```
src/data.py       数据层：官方 Bitget V3 SDK 封装（断点续传/失败标的剔除/backoff 重试）
src/factors.py    面板构建 + 波动率因子族
src/backtest.py   组合构建（流动性门槛 + 低波动五分位）、回测、指标
src/run.py        全流程入口，输出 report.json
third_party/      vendor 的官方 SDK（BitgetLimited/v3-bitget-api-sdk，见其 README）
tests/            20 个单元测试（防前视、僵尸标的隔离、重试链、边界守卫）
```

运行测试：`python3 -m pytest tests/ -q`
