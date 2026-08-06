# Changelog

## v7.0.0 (2026-08-06) — 🏰 魔法记忆宫殿

**核心理念**: 记忆宫殿法空间编码(翼/房间/书架/书卷) + 档案学著录(档号) + 三室分工(资料室精炼/档案馆存档/图书馆检索/中药柜召唤)。
用户启发: 图书馆分类法 + 档案馆著录 + 中药柜斗谱 — 人类几百年验证的记忆物流智慧。

### 🏰 宫殿架构 (新模块 `palace.py`)
- **分类树**: 7 翼 (K知识/N网络/D开发/O运维/A资产/P人物/I灵感) × 20 房间, 对标中图法
- **档号体系**: `K·NET·PROXY·2026-0007` — 编号即位置, 精确定位
- **著录卡片** (`tome_cards`): 档号/题名/摘要/标签/保管期限/来源, 标准化著录
- **三通道召唤** (`/palace/summon`): ①点名(档号/题名/标签精确) ②引导(分类树缩小) ③共鸣(向量语义)
- **资料室事实提取** (`/palace/extract`): 对话→离散事实→自动建档 (复用 factextract)
- **LLM 卡片精炼** (`/palace/refine`): 题名/摘要/标签 自动生成
- **永恒分级** (`/palace/lifecycle`): 永久(不衰减)/长期(慢衰减)/短期(90天自动撤架)

### 📚 数据翻新
- 总记忆 2775 → **8647** (归档率 100%)
- 结构化 facts **6231** (knowledge 5230 + preference 1001), 对话碎片占比 88% → 27%
- 著录卡片 **8614** 张, 分类树 30 节点
- 全量事实提取: 2319 条对话 → 6231 facts (资料室管线)

### 🔌 Hermes 适配
- `sync_turn`: 对话存 session 类 (2000/3000 字符), 不再存 chat 碎片
- `on_session_end`: 会话结束自动触发资料室提取
- `mnemosyne_palace_summon` 工具: 三通道召唤直连 Hermes
- `system_prompt_block`: 显示宫殿状态 (覆盖率/卡片/分类树)

### 🛠 修复
- find_candidates 过滤短内容 + skip 标记已处理 (防死循环)
- SQL 显式 public schema (防 search_path 歧义)
- insert_fact 返回 id (消除 SELECT 竞态)
- 分类关键词 14→20 类, security 优先级 (unfiled 减半)

### 📈 性能
- 召唤实测: xray/部署/密钥/记忆宫殿 全命中 (0.1-0.4s)
- 卡片精炼: 380 张 0 失败

## v6.4.0 (2026-08-05)

### 🧬 事实提取管道 (Fact Extraction) — 补上"个人信息记忆"维度

**动机**: LongMemEval 评测归因 (#6293) — 真实差距 = 缺"事实提取"层 (对标 Mem0 extract)。
对话记忆 (session/worklog) 只有知识蒸馏, 没有个人信息 facts (毕业/通勤/轮班/偏好)。

**改动**:
- `tmt/factextract.py` 新增: 对话 → 提取用户事实 (个人信息/偏好/事件/安排/能力) → preference/knowledge 入库
  - 短文本逐条提取 (豆包 lite 长会话漏深处答案 — 评测实测)
  - 非 json 模式 (豆包 json_mode 长 prompt >2500 字符返回空 — 评测实测)
  - ANN 去重闸机 (>0.92) + 热度 0.65 + 溯源 metadata
  - 失败重试 1 次, 无事实标记跳过, 失败下轮重捞
- cron: 每日 02:00 批量 60 条 (成本 ~¥0.09/天)

**验证**: 真实批量 30 条 → +14 facts 入库 (质量抽检: 用户偏好/计划/事件准确)。
LongMemEval 复测: 提取层对超长会话 (1.3万字符) 仍漏深处细节 — 确认为豆包 lite 模型提取能力边界 (官方用 GPT-4 级), 管道本身对真实短对话记忆有效。

## v6.3.0 (2026-08-05)

### 🧠 认知写入信号 — 重要的记忆从出生就热

**动机**: v6.2 解决"命中不加热"，但写入端无认知信号——"待办"和"寒暄"初始热度相同，重要知识被时间冲淡。

**设计来源**: 诺亚三代「抽屉级联压缩引擎」温度=命中次数+重要性加分表（代码锁死不靠 LLM）。

**改动**:
- `main.py` compute_write_heat: 写入时正则信号检测 → 初始热度加分
  未完成任务+0.15 / 用户纠正+0.10 / 踩坑教训+0.10 / 决策方案+0.08 / 路径API+0.05 / 重要标记+0.05 / preference|knowledge|pitfall 类别+0.10（上限 0.8）
- `main.py` reflect 热度v2: 保护衰减 — pinned/preference 每次仅 -0.005（普通按时间 -0.01~-0.08）
- `tmt/distill.py`: pitfall 蒸馏入库 heat=0.70（坑天生重要）

**验证**: 写入信号(待办0.65/寒暄0.5/preference0.6) + 保护衰减(preference -0.005 vs session -0.02) 双实测通过。

### ⚠️ 关键认知修正

- reflect 实际执行的是 `main.py` 里的「热度v2 多维减法衰减」，`tmt/router.py` 的 `tmt_decay` 是独立 API 路径（乘法）——改热度必须先看 main.py reflect

## v6.2.0 (2026-08-05)

### 🔥 认知热度引擎 — 记忆越用越热

**动机**: 实测 avg_heat=0.10 / L1 热点仅 1 条。根因: 热度只有初始值+纯衰减, 无任何使用信号 (搜索命中不加热)。

**改动**:
- `main.py` search_memories: 命中 top5 → access_count+1 + heat+0.05 (LEAST 1.0)
- `tmt/router.py` tmt_recall: 最终返回 memories 源 top3 加热
- `tmt/router.py` tmt_decay: 差异化衰减 — 近 48h 访问记忆 ×0.995, 其余 ×0.98 (活跃保持热点)
- 设计来源: 爆炸遗产考古 noah 双权重热度公式 (0.6 时间衰减 + 0.4 频次) 的实用简化版

### 🧪 蒸馏增强 (distill.py)

- 蒸馏入库 heat_score=0.65 (新知识热度信号, 默认 0.5)
- 批内去重: 同批相似 summary 互查 (子串匹配), 防同批重复提炼

### 🛡️ 健康监控备份新鲜度

- `mnemosyne-health-monitor.sh` 新增备份新鲜度检查: >10 天无新 dump 或 0 备份 → 微信告警 (防静默丢记忆)
- 修复: GZ 增强版之前未同步回仓库 (版本一致性)

### 📌 已知问题 (外部依赖, 不修)

- TMT L3 蒸馏连续 3 天失败 (豆包 API 400/超时波动) — 模型有效(直测 200), cron 每日自动重试 + health monitor 已告警

## v6.1-dev (2026-08-05)

### 🧪 知识蒸馏管道 (P0-1, MVP)

**动机**: 分类失衡 (session+worklog 88%, knowledge 9%) — 蒸馏只做了分类整理, 没做真正知识提炼。

**新增**: `tmt/distill.py` — 知识蒸馏管道 v0.1
- 设计来源: 爆炸遗产考古 (NCP-008 知识吸收七步 + 认知AI底座 TEL/MAIL 协议)
- 流程: 信号词候选筛选 → TEL 组装 → 豆包 Lite JSON 凝练 → ANN 去重闸机 (>0.92 跳过) → 入库 (knowledge→archive / pitfall→engineering) → metadata 溯源
- 用法: `python3 tmt/distill.py --batch N [--dry-run] [--stats]`

**部署**: GZ cron 每日 1:10 批量 60 条 (首轮 30 条: +22 knowledge, +1 pitfall, 5 fail 豆包偶发空返回下轮重捞)

## v6.0.1 (2026-08-02)

### ⚡ 生产性能与稳定性 — 双 worker + recall 容错

**并发隔离**
- `main.py` uvicorn `workers=1 → 2`：3 进程共享 8010（1父+2worker），慢请求（recall LLM 蒸馏）不再阻塞 search（实测 search 从排队 13s+ 降到 1.2-2.5s 恒定）

**recall 三层容错**（`tmt/router.py` + `core/llm.py`）
- 复杂度分类改**启发式**（关键词/长度判断 0/1/2），不再调 LLM：recall 常用查询 30s → 0.4s（embedding 缓存命中）
- gate 过滤 LLM 失败**降级保留全部候选**（try/except 包裹），不再 502
- `_call_ark` 豆包超时 60s → 15s；call_llm 连接类错误（URLError/TimeoutError/OSError）不升级 tier，直接快速失败（防 15s×3 重试放大）
- 效果：recall 新查询最坏 ~16s（豆包 embedding 慢，外部依赖），不再 60s 超时/502

**备注**
- 发布闭环：升级报告审阅 ✓ 用户验收 ✓ GitHub Release + tag ✓
- GZ 备份：`main.py.bak.20260802` / `core/llm.py.bak.20260802` / `tmt/router.py.bak.20260802(.2/.predegrade)`

## v6.0.0 (2026-08-02)

### 🎯 核心 — 概念模型重构：分类受控 + 管道修复 + 去重提速

**受控分类体系（解决分类混乱）**
- 新增受控词表 10 类：`knowledge` / `pitfall` / `reference` / `project` / `ops` / `deploy` / `preference` / `session` / `worklog` / `temp`
- 写入网关自动归一化：旧中英文分类（18 类）→ 10 类主键，未知分类 → knowledge（子串+全等双规则，24/24 用例）
- 数据库新增 `chk_memories_category` CHECK 约束，分类漂移从此被数据库层拦截
- 存量迁移：2295 条记忆 18 类 → 10 类，user_id 全收敛 `default`（单人使用语义）

**TMT 蒸馏管道修复（管道此前空转）**
- 修复 L2 会话蒸馏无参查询死锁：24h 窗口 + 最近 100 条未蒸馏碎片回退，管道不再空转
- 明确双层级语义：`tier`=价值分层（reflect 热度维护），`tmt_level`=TMT 时间树层（写入=1）
- reflect L4 不再直接软删记忆，改为 `forgotten_at` 标记（保留可恢复）

**Reflector 性能 + 去重修复**
- 冗余检测 O(n²) Python 逐对比较 → pgvector ANN 近邻查询：**33 分钟 → 5 秒（400 倍提速）**
- 相似度阈值 0.92 → 0.85：修复相似表述未合并的去重失效问题（首轮即合并 16 条冗余）

**Cron 修复**
- monthly 蒸馏 JSON decode error 根因：`date +%m` 前导零 `08` 非法 JSON 数字 → `date +%-m`

**运维清理**
- 删除历史遗留 `tmt_*_old` 表（4 张）
- 本地仓库归一：只保留 `~/mnemosyne-dev` 唯一真相源

## v5.5.2 (2026-07-29)

### 修复 — 语义搜索 NULL embedding 过滤

- **修复**: 5 处搜索 SQL 添加 `AND m.embedding IS NOT NULL`，防止 NULL 向量旧记录排在新记录前面
- **根因**: 迁移到豆包 embedding 后旧记录向量列为 NULL，SQL 排序把旧数据排到新数据前面
- **影响**: 修复后新记忆 100% 可搜索，不再被历史噪音淹没
