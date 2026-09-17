# Bitget AI Base Camp S2 — Google Form 提交文本（Alpha Factory）

> 赛道：🟦 Alpha Factory · 子主题：rToken Factor Strategies
> 表单：https://forms.gle/WxCSbXVEky5Z2oYN8 （中英文版本字段相同，任选其一粘贴）
> ⚠️ X 帖必填：下面链接列表里的 `<X_POST_URL>` 需替换为你的合规 X 帖（含 #BitgetHackathon @Bitget_AI）

---

## 一、项目说明（整段粘贴进「项目说明」框）

### 1 · 思路

**为什么做**：rToken 让美股变成 7×24 市场，但它是个散户主导、流动性严重分层的全新微观结构——传统美股因子在这里是否成立，没有任何公开答案。我们决定不猜，用一次系统性的因子迁移性检验来回答：**传统因子哪些会死、为什么、什么能幸存**。

**核心假设**：在流动性分层的 rToken 市场里，"低波动异象"是唯一能同时通过样本内/样本外双重检验的因子形态——前提是先做流动性过滤（不过滤时连它也是负的）。

**信号来源与决策逻辑**：每周一个决策时点，两步筛选——①流动性门槛：20 日成交额中位数 ≥ 全市场横截面中位数（剔除僵尸标的：价格长期不动的"安静"是无人交易，不是安全）；②波动排序：40 日已实现波动率最低的 20%。入选标的等权持有，周频调仓，全程纯多头现货、无杠杆、无做空。参数（40/20/20%、10bps）全部在样本内一次性设定，样本外零调参。

**风控设计**：a) 流动性门槛是第一道风控——它同时剔除了陈旧价格造成的"假低波"伪影；b) 衰减熔断机制（滚动 30 日 Sharpe < 0 → 次周空仓）已实现并实测（OS Sharpe 1.55→1.64，但 IS 0.89→0.30，净效果为负）——**默认不启用**，作为实盘尾部风险保险保留，拒绝在样本内调优阈值；c) 成本敏感性已验证：30bps/边 时 OS Sharpe 仍有 1.27。

### 2 · 目标用户与产品价值

**具体用户**：Bitget 上持有 100–5,000 USDT 的 rToken 散户（Retail），风险偏好中低，想要美股敞口但无法盯盘 7×24、也没有能力自建研究管线的人。他们当前的典型行为是追涨杀跌高波动标的（NVDA、TSLA 类 rToken），亏损主因不是选错股票，而是**每周忍不住折腾**。

**为什么需要它**：本策略把"每周该拿什么"压缩成一张 2~22 只标的的清单（当前 = RQQQ/RSPY/RTSM/RVOO 等权），纪律工具属性——用户每周日打开报告页抄一次作业即可，周换手仅 ~2.7%，几乎无操作摩擦。对 Pro/VIP 用户，同一套规则可作为低波动核心仓（core-satellite 的 core），与高波卫星策略搭配。产品形态三层：只看不动手（线上报告页）/ 手动跟单 / Playbook 订阅自动化（已发布）。

### 3 · 验证数据与关键指标（均为实测，非估算）

**回测设置**：113 个 rToken 全宇宙 · 2025-09-28 → 2026-09-07（316 交易日）· 样本内前 200 天（→2026-05-10）、样本外后 116 天 · 成本 10bps/边已计入 · 数据源为 Bitget 官方 V3 SDK 公共端点。

| 指标 | IS | OS | 全期 |
|---|---|---|---|
| Sharpe | 0.89 | **1.55** | 1.14 |
| 年化收益 | — | 11.6% | — |
| 最大回撤 | — | **-3.4%** | -6.3% |
| 周换手率 | — | ~2.7% | — |

对照组：等权全池基准 IS 1.55 / OS 1.76——本策略在 OS 以**一半的回撤**获得相近的风险调整收益；OS Sharpe > IS（未触发评委"OS < 0.5×IS"衰减预警线）。30bps 成本下 OS Sharpe 1.27（成本敏感性全表见报告页）。

**抗过拟合证据链**：20 个成熟因子（动量/反转/MAX 彩票/特质波动/Amihud 等，Jegadeesh-Titman、Bali、Amihud 等文献因子）经同一回测框架，19 个 OS 失败进"因子墓地"；4 个 rToken 原生周末因子（7×24 市场结构上才可能存在的因子）单独与叠加全部失败；门槛消融证明"去门槛"在周频 OS 崩至 0.19（频率脆弱），现行门槛是唯一周频/日频双口径 OS>IS 的配置。

**官方引擎交叉验证**：策略已发布为 Bitget Playbook（GetAgent，v1.0.0），官方沙箱（Nautilus 引擎）独立回测：2025-11-10→2026-09-07，**+5.19%，最大回撤 -4.02%**（8 只流动性池、双边 10bps）——独立引擎复现了低波篮子方向。

**有效性/分发证明**：策略已上架 Playbook 市场（可订阅、参数可调）；报告页实时持仓由评委浏览器直连 Bitget 公共 API 刷新。当前无真实订阅用户（如实申报）；分发验证计划：Playbook 订阅数与 GetAgent Studio 数据 + 报告页访问量，赛后以 Bitget 后台数据为准。

### 4 · 完成度

**已做**：全宇宙数据管线（官方 SDK、增量缓存、僵尸标的治理）→ 20+4 因子全量迁移性检验 → 旗舰策略 + 消融 + 熔断 → 单元测试 23 项全通过 → 一键复现（`python3 src/run.py`）→ 线上研究报告页（GitHub Pages，实时行情）→ **Playbook v1.0.0 正式发布**。

**未做**：真实资金实盘（只有官方沙箱回测）；X 传播素材视频；全宇宙版 Playbook（当前上架版为 8 只流动性池的可配置篮子形态）。

**遇到的问题与解法**：① rToken 无官方标识（R+ticker 与普通币混撞）→ 自建注册表与治理流程；② K 线 300 根上限且分页未文档化 → 分块拉取拼接；③ 2026-06 周六 K 线补齐的结构变更无任何 API 标记 → 周末特征工程按压缩序列处理；④ GetAgent 沙箱引擎 6 轮迭代（特征列冲突/时区/选择表传递通道）全部通过官方测试与诊断定位修复。

**下一步**：GetAgent Studio 开 Paper Trading 产出运行日志 → Agentic 账户实盘小额验证 → 依赖数据增强后扩展至全宇宙自动轮动。

**使用的技术栈**：Python（官方 Bitget V3 SDK、pandas/numpy、pytest）、Streamlit 与静态报告页、Plotly、GitHub Pages、GetAgent Playbook SDK（沙箱内 Nautilus 引擎）。模型：GLM 智能体（编码/研究/回测全流程），未使用其他模型。

### 5 · 材料清单（对应「提交材料链接」）

1. **线上报告 Demo**：https://tianzeteam.github.io/stillwater-alpha/ （净值/回撤/实时持仓/成本敏感性/因子墓地，打开即看）
2. **代码仓库**：https://github.com/tianzeteam/stillwater-alpha （含 `src/run.py` 一键复现、tests/、Playbook 包 `playbook/stillwater-lowvol/`、`data/report.json` 回测产物）
3. **回测数据/报告**：仓库内 `data/report.json` + 报告页 Factors & Ablation 章节（IS/OS 明细）
4. **Playbook 市场条目**：Stillwater Low-Vol Rotation (rTokens) v1.0.0（GetAgent 搜索 stillwater-lowvol）
5. **合规 X 帖**：<X_POST_URL>（发布后替换）

### 6 · 对 AI Trading 的看法（选填）

我们用 Bitget 全套工具真实走完一遍后的三条建议：① **数据是最大杠杆**——rToken 缺官方标识字段与可回放的 market replay API，官方自设的"跨发行商套利"子题因此无法交付；② **Paper 日志需要可信机制**——Agentic 赛道要求 ≥2 周日志但格式自定、真伪自证，建议 `bgc --paper-trading` 输出标准化 schema + 哈希存证；③ **Playbook→paper→实盘的命令化漏斗**是最高 ROI 投资——每个被上架的策略都是持续产生交易量的资产，本次我们从想法到上架走了 6 轮沙箱调试，一条命令的漏斗能把创作者摩擦减半。

---

## 二、「大模型在项目中的作用」框

大模型（GLM 智能体）承担了除交易思想外的全部工程与研究执行：① 数据管线编码（官方 V3 SDK 封装、增量缓存、僵尸标的治理）；② 20 个经典因子 + 4 个 rToken 原生周末因子的迁移性研究——假设、实现、统计检验、淘汰结论全部由 agent 生成并复核；③ 回测框架与消融实验（门槛强度扫描、调仓频率脆弱性检验）；④ 线上研究报告页与部署；⑤ GetAgent Playbook 包的编写、本地校验与 6 轮沙箱调试修复；⑥ 官方 SDK 疑难（分页、周末 K 线、特征帧契约）的文档挖掘与适配。策略思想与最终取舍由人决定。未领取 Qwen 额度（注：若你领取了，按手册要求补充 Qwen 的使用位置）。

---

## 三、「提交材料链接」框（逐行粘贴）

```
Demo（线上研究报告页，含实时行情）: https://tianzeteam.github.io/stillwater-alpha/
代码仓库（一键复现 python3 src/run.py）: https://github.com/tianzeteam/stillwater-alpha
回测数据与报告: https://github.com/tianzeteam/stillwater-alpha （data/report.json；报告页 Factors & Ablation 章节）
Bitget Playbook（已发布 v1.0.0）: https://www.bitget.com/zh-CN/activity/ai-get-agent/playbook?tab=explore （搜索 stillwater-lowvol）
合规 X 帖: <X_POST_URL>
```
