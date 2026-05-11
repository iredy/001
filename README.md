# 可复制的 GitHub 仓库模板：实盘风格月频投研回测

这个仓库提供了一个可直接运行的投研回测框架，核心技术栈是 **SQLite + Pandas + NumPy**。

## 功能覆盖

- SQLite 建表与本地数据库落盘
- Mock 数据自动生成（便于开箱即跑）
- 特征快照构建（按公告日可见，避免未来函数）
- 宏观状态机（A/B/C）
- 三层组合构建（防御 / 成长 / 战术）
- 权重约束（单票、行业、现金、换手）
- 成本模型（手续费 + 滑点 + 冲击）
- 月频调仓回测（信号日与执行日分离）
- 报表导出（`outputs/bt_result.csv`、`outputs/report.json`）

## 快速开始

```bash
git clone <your-repo-url>
cd 001
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python live_research_backtest.py
```

## 目录结构

```text
.
├── live_research_backtest.py  # 主程序（可直接运行）
├── requirements.txt           # 依赖
├── .gitignore
└── README.md
```

## 输出文件

运行后会生成：

- `outputs/bt_result.csv`：逐期回测结果
- `outputs/report.json`：绩效汇总（年化、波动、夏普、回撤、胜率等）

## 接入真实数据时的替换建议

1. 用交易所真实交易日历替换 `gen_trade_calendar()`。
2. 用真实行情/基本面/宏观数据替换 `seed_mock_data()`。
3. 用卖方一致预期或内部模型替换 `earnings_revision` 的示例近似。
4. 在 `load_return_and_adv()` 增加涨跌停、停牌、成交可达性约束。
5. 将 `est_cost()` 改为你们券商实测分桶冲击成本模型。

## 映射模块，有没有必要集成？

建议：**有必要，但作为可选增强模块**，不要强耦合到核心回测引擎。

- 这个仓库已经内置了可选映射模块开关（`Config.mapping_enabled`），用于把策略风格映射到 `defensive/growth/tactical` 三个 sleeve，再与宏观状态权重融合。
- 如果你的策略池只有 1~2 个简单策略，可先关闭映射模块，降低复杂度。
- 如果你有多策略并行（估值修复、确定增长、波段增强等），开启映射模块能让“策略意图 -> 组合权重”更透明、更易运维。

默认映射关系（可按团队口径改）：

- `估值修复 -> defensive`
- `确定增长 -> growth`
- `技术兼容 / 波段增强 / 业绩成长 -> tactical`

## 许可证

MIT


## OpenClaw 7模块可落地代码

新增 `openclaw_7m.py`：

- 7模块权重聚合（10/10/20/15/5/15/25）
- 模块7支持“非典型复苏”识别（信用脉冲>0 + PPI<0 + 高储蓄率）
- 宏观模块向估值模块下发微调系数（提升 FCF 权重、压低盈利增速权重）

运行：

```bash
python openclaw_7m.py
```


## RAG修正层（已集成）

新增：

- `unifiedinvestmentframework.py`：在“结构化信号 -> 最终加权”之间插入 RAG 置信度修正层。
- `tools/strategyragindexer.py`：SQLite FTS5 版本的轻量检索器。
- `tools/ingest_tradejournal.py`：优先灌入 `tradejournal.db` 的解析脚本。

### 为什么优先 tradejournal.db？

第一优先建议：**历史交易复盘日志（tradejournal.db）**。
原因：
1. 与你的真实交易决策闭环最一致（标签质量高）。
2. 能直接学到“同类宏观场景下，过往哪些信号是错的”。
3. 相比外部研报，噪声更低、风格更贴近你自己的策略执行。

### 快速运行

```bash
python unifiedinvestmentframework.py
python tools/ingest_tradejournal.py --source-db tradejournal.db --rag-db strategy_rag.sqlite3
```

## 宏观指标如何转成模块7信号

模块7不再只看单一“复苏/衰退”标签，而是把宏观指标拆成五组分项信号后加权：

| 指标组 | 输入字段 | 用法 | 方向 |
| --- | --- | --- | --- |
| 增长景气 | `pmi`, `gdp_yoy`, `retail_sales_yoy` | 判断真实需求与经济动能 | PMI>50、GDP/社零改善为正向 |
| 货币信用 | `credit_impulse`, `m2_yoy`, `lpr_1y` | 判断宽货币/宽信用是否形成 | 信用脉冲、M2上行与LPR较低为正向 |
| 通胀/通缩 | `cpi_yoy`, `ppi_yoy` | 判断盈利传导和价格环境 | CPI接近2%、PPI温和为正向，PPI<0扣分 |
| 外汇风险 | `usdcny_yoy` | 判断人民币贬值压力与外资风险偏好 | 同比贬值越大扣分越多 |
| 居民资产负债表 | `hh_credit_yoy`, `savings_rate` | 判断居民是否从防御性储蓄转向扩表 | 居民信贷改善为正向，高储蓄率扣分 |

落地规则：

1. `openclaw_7m.MacroStrategy` 会输出 `macro_component_scores`，便于投研复盘每组宏观指标对最终结论的贡献。
2. 若出现 `credit_impulse > 0`、`ppi_yoy < 0`、`savings_rate` 高于阈值的组合，系统判定为“非典型复苏”，不会简单给高置信 BUY。
3. 在“非典型复苏”中，宏观模块会向下游输出约束：提高 FCF 权重、降低盈利增速权重、提高现金缓冲，并限制成长暴露。
4. `live_research_backtest.py` 的 `macro_monthly` 已支持 `pmi/gdp_yoy/usdcny_yoy/lpr_1y`，回测状态机会结合 PMI、GDP、汇率和 LPR 判断是否进入信用扩张。
