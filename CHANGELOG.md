## unreleased · 仓库装修 (2026-09-25) — 头版海报重设计 + 数据口径校正 + 安装脚本

> 依据：用户指令「GitHub 上的仓库要重新装修……海报要重新设计，**不要再沿用老的这样的一个设计了**」。
> 设计标准取自站内既有的「小小橘新闻」系列语言（米白纸面 + 暖橘 + 深棕 + 墨黑）。

### 海报重设计（`docs/poster.*`）

- **换设计语言**：由「超长信息图」改为**报纸头版风** —— 报眉 / 报头 / 头条（首字下沉双栏导语）/
  要闻数字 / 主笔专栏（配图）/ 三个版块 / 双栏图解 / 调查特稿 / 报尾。**信息板块数不减**（13 板块）。
- 配图新出：`docs/poster-mascot-8.0.png`（纯色底 → 抠图 → 合成；图内零文字）
- 成品尺寸 **1800×8281**（原 1800×7400）；文字 100% 走 HTML 排版（AI 生图不写字）
- 源码 `docs/poster.html` 保持**引用外部图**（diff 小、便于改版重渲染）

### 数据口径校正（`README.md` / `README_CN.md`）

- 记忆总量 `12,427+` → **`16,500+`**（口径：`GET /api/v1/metrics` + 记忆统计）
- 归档率 `99.9%` → **`99.4%`**；新增可溯源行「数据行 17,320（含墓碑 743）· 297 MB」
- **删除无实时口径的数字行**（structured facts / Tome cards）—— 状态表只放可溯源数字

### 安装件补齐

- 新增 **`setup.sh`**：`--check`（只读自检）/ 默认（venv + 依赖 + 配置模板 + 库初始化）/ `--start`（启动并健康检查）。
  幂等；**不覆盖已有 `.env`**；不硬编码路径与凭据。
- `INSTALL.md` 版本 `v7.8.3 → v8.0.0`（3 处漂移修正，命令示例同步）
- Python 门槛 `3.12+ → 3.11+`：实测本机 3.11.15 全绿、代码无 3.12 专属语法
  （原声明构成**不必要的外部门槛**）

### 修正

- `docs/poster.html` 主标题错字「记忆供电」→「记忆宫殿」（同批修复见上一提交）
- **海报页脚验证数字纠正**（跨仓库混淆 + 过时快照）：
  - `契约 45 通过` —— 那个 **45 属于 `gcat-std` 仓库**（其治理底座套件），误入了本仓库海报 →
    改为本仓库实测值 **`MCP 桥契约 6 通过`**（`tests/test_mcp_bridge_contract.py`）
  - `单元 267 通过`（v8.0.0 完成时的本地快照，依据 `PROGRESS.md`）→ **`273`**（`pytest` 全量实测，任何人可复现）
- **CI 隐私门禁误判修复**（`.github/workflows/privacy.yml`）：凭据类 pattern 原为「出现即报」写法
  `PGPASSWORD=[^y]`，把 `setup.sh` 里**合法的变量展开**判成泄露 → push 后 main 连续两次红灯（对外可见）。
  - 判据改为**只抓写死的值**（变量展开首字符是 `$`，天然不命中；真硬编码照旧抓得住）
  - pattern 由步骤内移到 workflow 级 `env`：**扫描与自检共用一处定义**，改一处两边同时生效
  - 新增「门禁自检 · pattern 双向验证」步骤：合法写法必须绿 + 硬编码必须红
    （拦截类规则也要反向验证，只测「抓得到坏样本」等于没测「不误杀好样本」）
  - 证据：本地按 YAML 逐步复现 —— 旧 pattern 命中 `setup.sh:66/114`，新 pattern 全绿；
    另行放入真硬编码样本后，凭据类与内部域名两道扫描**同时判红**（反证通过）
  - 该纪律同时写进 `AGENTS.md` 红线（pattern 改动：本地逐步复现 + 双向自检 + 反证清场）

## release · v8.0.0 (2026-09-25) — 记忆宫殿 OS 8.0：写得对 · 收得回 · 找得准 · 弄得清

> 立项依据: 提案 [P-20260925-01](openspec/changes/2026-09-25-v8-memory-os/proposal.md) · ADR [0002](docs/adr/0002-文件系统机制取舍与触发器.md)
> 与前一轮的《记忆文件系统研究报告》(20 维 FS 机制映射) 的关系: **收窄并制度化** ——
> 只补 PostgreSQL 没给且我们真缺的, 其余 17 维写进 ADR 触发器（未触发不得新增）。
> 原报告的价值被保留成闸门: 它的边界条件就是我们的触发阈值。

### 🛡 S1 可靠性 — 修真缺陷（有「数据会错」后果）

- **S1-1 写入原子性** (`main.py: create_memory`): 原实现 `pool.acquire()` 下顺序 `execute`
  三步 autocommit, 崩溃可留「有 memories 行、无 entities / 无 memory_keywords」的半成品。
  现改为 **单事务包裹**（矛盾检测读 + 主写入 + 实体同步 + 分词），任一步失败整体回滚。
- **S1-2 幂等键激活**: `dedup_fingerprint = sha256(content|category|user_id)`,
  建**部分唯一索引** `dedup_fingerprint_key` + `ON CONFLICT DO NOTHING`。
  语义: 崩溃重试 / 端云断线重发 / 重复 POST **返回原 id, 不再产生新行**。
  设计取舍: **不回填历史**（历史 0 行为空 → 唯一索引忽略 NULL；回填会暴露 132 组历史重复导致建索引失败）。
- **S1-3 记忆回收 (GC / compaction)** `jobs/compaction.py`: 原系统全仓无 `DELETE FROM memories`
  / 无 `VACUUM` → 软删即终点。现补 `tombstone → purged` 环节, **五道安全闸**:
  窗口(默认 30 天) → 保护位(permanent/pinned) → 引用完整性(beliefs 证据 / 存活子记忆) →
  **冷归档 `memories_archive`（含 traces 快照）** → **CSV 回滚凭证**。
  默认**干跑**，`--apply` 才真删；`--restore <batch>` 可整批还原。
  `memory_traces` 外键改 `ON DELETE CASCADE`（原为 NO ACTION，会挡住回收；改前先验孤儿）。
- **S1-3 完整性巡检** `jobs/scrub.py`（**只读**）: 6 类孤儿/异常（孤儿 inode / 孤儿引用 /
  悬空信念证据 / 到期未回收 / 缺指纹 / 活子挂死父）。
- **S1-4 可观测**: 写入/召回**延迟埋点**（p50/p95/p99，进程内环形缓冲，成本≈0）
  + `GET /api/v1/metrics` 一条请求看全（延迟 / 库规模 / tombstone 比 / 幂等索引自证 / 上次 GC）。
  此前 `perf_alert.py` 有 2000ms 阈值却**全无埋点** —— 阈值形同虚设。
- **S1-4 备份复验** `jobs/backup_verify.py`: 原备份只回答"跑没跑"（曾有**静默失败 36 天**）。
  现补**可恢复性**四验: 新鲜度 / 体积 / **结构（真读 pg_restore TOC）** / `--deep` 真恢复到临时库比对行数。

### 🔍 S2 检索质量

- **S2-0 先量后改**: 方案明确「改召回排序前必须先有评测基线」（红队原话：'RRF 更好'无评测支撑）。
- **S2-1 四通道 RRF 融合** `core/rrf.py` + `palace.summon_fused()`: 原 `summon()` 四通道
  (点名/引导/共鸣/文库) **各自独立返回、不融合、无统一截断**。现各取 candidate_k(50) 候选 →
  RRF 融合(k=60) → 统一截断 top_k。RRF 只按**排名**融合 → 量纲无关（原单条 SQL 线性加权
  把余弦距离/BM25/时间三种量纲直接相加）。
  **命名空间隔离**: `memories.id` 与 `wiki_pages.id` 是两套 id 空间，融合前分别加 `m:`/`w:` 前缀
  （否则不相关条目会互相加分）。`channels` 字段回答"这条为什么排上来"（可解释性）。
  **默认关闭**（`GET /api/v1/palace/summon?fused=true` 才启用）—— 评测数字出来之前零行为变化。

### 🗂 S3 治理

- **S3-1 记忆分层模型 → 可执行规格** `core/layers.py` + `openspec/specs/memory-layers.md`:
  5 层(L0 日志/L1 认知/L2 技能/L3 约束/L4 参考) + 横切产出物索引, 按**「允不允许矛盾」**分三族。
  **不是文档**: `classify_layer()` 在写入路径上真跑, 每条记忆落 `metadata.layer`;
  对外入口 `GET /api/v1/layers`(含 `self_check`) / `GET /api/v1/layers/classify`。
  诚实标注: **L3 约束层载体在 Hermes 侧(SOUL/MEMORY/config)，不在库内** —— 有断言锁住，防止被硬塞 category。
- **S3-2 发布流程状态机** `gcat-std/scripts/release-gate.py` + 本项目 `release-gate.json`:
  A 本地 → B 真实环境 → C 部署 → D 公开 → E 归纳, **未过上一段不进下一段**（越段被硬拒）。
  配套 `scripts/release_checks.py`（版本一致 / 隐私扫描 / 服务自报版号 / 变更日志 / 产出物指针）。
  本次 v8.0 发布即第一个回填样本。
- **S3-3 产出物指针策略**: 交付=箱子 / 检索=Wiki / 版本=仓库；**记忆里只放指针 + 指纹，不放实体**。

### ⚠️ 发布途中真实事故（已修，教训保留）

**现象**：部署到生产后，**第一发写入即 500**。
```
asyncpg.exceptions.InvalidColumnReferenceError:
there is no unique or exclusion constraint matching the ON CONFLICT specification
```
**根因**：`dedup_fingerprint_key` 是**部分唯一索引**（`WHERE dedup_fingerprint IS NOT NULL`），
而写入写的是 `ON CONFLICT (dedup_fingerprint)` —— PostgreSQL 的部分索引推断**要求谓词显式匹配**，
缺谓词直接报错，整条写入路径挂掉。
**修法**：`ON CONFLICT (dedup_fingerprint) WHERE dedup_fingerprint IS NOT NULL DO NOTHING`
（保留部分索引：只约束有指纹的行，1.6 万条历史 NULL 行无需回填）

**为什么既有单测没抓到（本版最重要的教训）**
- 已有测试只验证「索引能拦住重复指纹」（裸 `INSERT`），
  **从没跑过产品代码里那条真实的 `INSERT ... ON CONFLICT` 语句**。
- **测了索引 ≠ 测了使用索引的那条 SQL。**
  凡"代码里拼出来的 SQL"与"库里建的对象"有耦合，就必须把真实 SQL 拉出来跑一遍。
- 修法：新增 `tests/test_v8_write_path.py` —— **从 `main.py` 源码正则抽出真实 SQL**，
  绑上占位值投到库上执行。源码与库对象一旦不匹配立刻红。
  反证已验证：临时删掉谓词 → `test_w2` 立即失败。
- 本次由**发布的第三层（生产功能实测）**抓到 —— 这就是"三重验证"不是形式主义的证据。

### 🔧 发布后修正（**仍在 v8.0.0 内**，非新版本）

> 用户 2026-09-25 定调：这些缺陷发生在**测试阶段**，按正确节奏应在**同一版本号内吃掉**，
> 不该冒出「下一版修复」。故不新增版本号，修正直接并入 v8.0.0 并重切发布。

**🔴 修正一：记忆回收的「整批还原」是假安全（红队指出 → 我复现 → 修复）**

实测复现：
```
删前 → keywords: 1  tome_cards: 1
删后 → keywords: 0  tome_cards: 0        ← CASCADE 静默连带删除
还原后 → memories: 1  traces: 2  keywords: 0  tome_cards: 0   ← 没回来
```
记忆回到库里了，但 **BM25 再也搜不到它、著录卡片也没了**（僵尸记忆）。
根因：原实现只归档 `memories + memory_traces`，而 `memory_entities` / `memory_keywords` /
`tome_cards` 三张表都是 `ON DELETE CASCADE` —— 静默连带删除且还原时不重建。
修法：归档增列 `_entities/_keywords/_tome_cards` 四表全快照 → 还原重建四表 →
**完整性断言**（归档数 ≠ 还原数则整体回滚，僵尸记忆结构上不可能出现）。

**🔴 修正二：幂等键与 L0 契约矛盾（红队指出 → 复核 → 生产 P4 实测暴露「半修」）**

初版 `sha256(content|category|user_id)` 套用于**所有**分类，与自家分层模型直接矛盾：
L0 契约是「只增不改、允许矛盾」，但同一天说三次「好的，收到」会被并成一条。
根因把「幂等（同请求重试只生效一次）」与「去重（同内容多条合一条）」混为一谈。

修法**两处都要改，只改一处是半修**（生产 P4 实测抓到）：
1. **指纹分层** `compute_write_fingerprint()`：
   L1~L4 用内容指纹（版本化族，幂等不变）；L0 用**来源上下文**
   （有 session_id/source 用其区分；都无则用小时桶 — 秒级重试去重、跨小时保留）
2. **冲突检测分层** `should_run_conflict_detection()`：L0 **跳过** `detect_conflict` 的
   语义合并 —— 否则近重复内容在指纹判定**之前**就被 merge 掉，L0 日志仍被压缩

实测对照（生产）：旧行为跨会话=并成一条（误杀）→ 新行为=各存一条；
同来源重试仍去重；L1 同内容跨会话仍幂等。

**教训**：单测只测了 `compute_write_fingerprint` **纯函数**，没测**整条写入路径** ——
与「只测能用的那半」同源。**这正是正式环境测试（P4）存在的意义。**

### 🧪 测试

- 新增 **26 例**: `tests/test_v8_rrf.py`(8, 纯函数) · `tests/test_v8_layers.py`(10, 规格断言) ·
  `tests/test_v8_compaction.py`(8, 集成 — 需 v8.0 迁移库, 不可用则整体 skip)。
- 全量: **228 → 267 passed / 6 skipped**（含写入路径 SQL 契约、分层幂等键、L0 跳过分歧、GC 还原完整性 C9 等）
- gcat-std 治理底座: **45 tests OK**（release-gate 硬约束套件）
- **反证测试**（造违规样本证明真能拦住）: 干跑零改动 · 越段被拒 · 唯一索引拒重复指纹 ·
  截断/陈旧/空备份被拦 · 分层规格漂移被检出。

### 📌 三环境

| 环境 | 状态 |
|---|---|
| 本地 (WSL) | v8.0.0 已实现, 254 用例绿 |
| 正式 (GZ) | 部署后服务自报版号复验（**先部署验稳, 才公开**） |
| 仓库 (GitHub) | tag/Release v8.0.0, 隐私两层扫描零输出 |

---

## release · v7.8.4 (2026-09-24) — 归档质量: 收尾汇报不再被切 + 汇报卡入库 (+治理底座落地)

> 触发: 用户问「生产服务器上那个几百兆的文件是什么」, 全线查不到 —— 原话在 `state.db` 里**一条没少**, 但语义层查不到:
> 会话归档对**每条消息**一刀切 `content[:2000]`, 而收尾汇报常 >2000 字, 被切掉的恰是**交付物绝对路径 / 哈希 / 实测数字**。
> 同源毛病与 (v7.8.2)「语义等价 ≠ 可用」一致: **改了粒度而消费端没跟上, 不报错、只失真**。

### 🩹 修复 — 归档链路 (`scripts/archive_session.py`)
- **分级截断**: 收尾汇报(会话最后一条有正文的 AI 消息)与用户消息**全文保留**, 过程消息压缩到 `LIMIT_PROCESS=1200`;
  总预算 `MAX_TOTAL=120000` 超限时**只从过程消息让位**, 汇报永不裁剪 (旧版对每条消息一刀切 2000 字)
- **证据签名**: 带 `tool_calls` 的消息附 `⟪工具: terminal×3, read_file×2⟫` —— 语义层从此看得见"这轮干了什么"
  (本机实测 **17,486 条**消息带工具调用, 旧版全部丢弃)
- **短会话不弃**: `message_count < 5` 不再静默跳过, 改为入库并打 `[短]` 前缀; 保留 `--skip-short` 还原旧行为
- **修复回库**: 部署副本 2026-09-04 的 `_detect_project` 接线(项目前缀进 title)此前**只在生产、未回仓库**
- **标签合并且幂等**: `[项目]`/`[短]` 合成**单个**标签 `[短·relife]`, 重复处理不叠加(旧写法会方括号套娃)

### ➕ 新增 — 汇报卡 (`scripts/report_card.py`)
- **默认 final 模式: 每场会话只取收尾汇报**; `scan`/`all` 模式供分析(实测: 宽松阈值 3 场抽出 66 张卡 → 会污染记忆, final 模式 3 张) → `~/.hermes/reports/cards.jsonl`
- 入宫 `POST /api/v1/memories` + `category=worklog`(**capabilities 受控词表内** —— 自造值会被服务端**静默归一化为 knowledge**)
- 幂等: 卡片指纹(session+msg_id+原文)去重, 重复跑不污染记忆; `--dry-run` 不写任何东西

### 🧪 新增测试 (`tests/test_archive_quality_v784.py`, 29 例)
- 分级截断(汇报全文/用户全文/过程压缩/总预算不吞汇报) · 证据签名(含坏 JSON 容错) · 标题合成与幂等 ·
  短会话入库与 `--skip-short` 还原 · 汇报卡抽取/受控 category/请求形态/幂等/dry-run · 会话归档推送形态回归

### 🧪 实测踩坑并修掉（都在测试里锁住）
- 宽松阈值 3 场抽出 **66 张卡** → 默认改为「每会话只取收尾汇报」, 实测 3 张
- `role='tool'` 的工具回显被当交付汇报 → SQL 收紧 `role='assistant'`
- diff 噪声 `…a.py\n+++ b/a.py` 被当路径 → 路径正则排除反斜杠/加号/反引号 + 片段上限 160
- 汇报常不在最后一句 → final 模式回看 3 条
- 让位计数语义错(迭代次数 4227 ≠ 消息数) + 净减量漏算后缀 → 修正
- 生产端到端: `--push` 真写入 → `GET /api/v1/memories?category=worklog` 回读成功

### 📋 变更提案
- `openspec/changes/archive-quality-v784/proposal.md`(含发布门禁与验证记录)

### 🏗 治理底座落地 (同日, 项目层)
> **本次不改运行时行为**, 只补「事实底座」: 让任何会话接手 3 分钟知道这是什么、有什么能力、到哪了。

### Added
- `PROJECT.md` 项目宪章（这是什么/为什么/到哪了/范围边界/关键决策索引）
- `openspec/` 规格层：`specs/`（能力真相）+ `changes/`（变更提案，含 ADDED/MODIFIED/**REMOVED**）+ `archive/`
- `docs/adr/` 架构决策记录（首条：ADR-0001 采用项目治理标准）
- `CONTRIBUTING.md` 贡献指南（提交规范 / 分支 / 改动前必做 / 发版门禁 / 红线）
- `docs/` 下沉文档：`ARCHITECTURE.md` · `INTEGRATION.md` · `API.md` · `ENV.md` · `AGENT-USAGE.md`

### Changed
- `AGENTS.md` **瘦身 8,466 → 2,236 字符（-74%）**：根文件只留「构建 / 约定 / 红线 / 导航」，细节下沉 `docs/`

### Fixed
- `.gitignore` 补 `*.db` / `*.sqlite` / `*.dump` / `*.log` —— 此前 `sync/local_cache.db`（本地记忆缓存）未被忽略，误 `git add -A` 会把真实数据提交进公开库

## release · v7.8.3 (2026-09-12) — 服务端口 / 监听地址环境变量真正生效

> 触发: `MNEMOSYNE_PORT` / `MNEMOSYNE_HOST` 属于"文档写了、代码不读"的静默失效 —— `config.py` 早已 `os.getenv` 读取, 但服务入口 `main.py` 的 `__main__` 块**写死** `host="127.0.0.1", port=8010`, 环境变量被无声忽略(`INSTALL.md` / `AGENTS.md` 此前如实标注"暂未生效")。文档承诺的开关与实现不一致时, 使用者会照着配置然后困惑 —— 与 (v7.8.2) 的「语义等价 ≠ 可用」同源: **改了措辞/位置而消费端没跟上, 不报错、只失真**。

### 🩹 修复
- `main.py` 的 `__main__` 入口改用已导入的 `config.HOST` / `config.PORT`(默认值不变: `127.0.0.1:8010`) → `MNEMOSYNE_HOST` / `MNEMOSYNE_PORT` 自此真正生效
- 文档同步: `INSTALL.md`(端口说明改写 + 示例响应版本)、`AGENTS.md`(环境变量表去掉"暂未生效")

### 🧪 新增测试 (`tests/test_server_port_env.py`, 2 例)
- 契约: 未设环境变量 → `config.PORT == 8010`; `MNEMOSYNE_PORT=9123` → `9123`。**子进程验证**, 不污染本进程的模块级配置

### 🔁 兼容性
- 默认行为与 (v7.8.2) 完全一致(默认值未改); 只有显式设置了这两个变量的部署会改变监听地址 —— 那正是文档一直承诺的行为

## release · v7.8.2 (2026-09-12) — MCP 桥契约修复回库 + 契约自描述对齐

> 触发: 生产实测 MCP 桥三个管理型工具(feedback/delete/restore)必报 422 —— 桥把 feedback 发成 JSON body 且漏传 user_id, 而服务端 REST 要求二者都是 query 参数, 用户侧表现为"工具坏了"。同类风险落在**响应字段**上会静默失效(读 `heat` 而服务端返回 `heat_score` → 永远取默认值且不报错), 故一并锁契约。

### 🔌 修复回库 (生产已验证)
- `integrations/hermes-mcp/mnemosyne_mcp.py`: feedback / delete / restore 三个 handler 的 `user_id`(与 feedback 值)改走 **query 参数**; 生产三路实测通过 (feedback→feedback recorded / delete→soft-deleted / restore→restored)
- 脱敏 + 契约铁律段: 桥 docstring 内部代号 → "生产服务器"; 新增「入参位置按服务端要求 / 响应字段名以自描述为准 / 改 handler 必跑契约测试」三行铁律

### 🧪 新增契约测试 (tests/test_mcp_bridge_contract.py, 6 例)
- 锁死 outbound 请求形态: 3 个 query-参数端点 + 2 个 body 端点回归(防"修过头")
- **反证过**: 旧代码下 4 例失败(proven red), 修复后 6/6 绿
- mcp SDK 仅 Hermes 侧安装 → 最小安装自动 skip, 不阻塞服务端测试套件

### 📖 capabilities 自描述对齐 (API 门面)
- `category` 词表: `fact|experience|belief`(3 类) → 受控词表 **10 类** + 非法值归一化说明(此前门面文档与 DB CHECK 约束不一致, 对外使用者会照错文档写)
- `DELETE /memories/{id}`、`POST /{id}/restore`、`/{id}/feedback` 标注 `user_id (query 必填)` —— 正是本次踩坑点
- `GET /memories/heat-top` 补 `returns: memories[].heat_score (字段名是 heat_score, 不是 heat)`

### 🧰 工具链
- `scripts/version-scan.sh`: CHANGELOG / AGENTS 的匹配式对齐真实排版(此前恒判 MISSING, 形同虚设)

### 🧹 内部代号清理 (活跃代码/文案, 同批)
- **17 个活跃文件 / 43 行**: 注释、docstring、usage 与日志串里的内部代号 → 中性表述(`生产服务器 / 服务端 / 生产`), 覆盖 `sync/*`、`wiki/*`、`integrations/hermes-provider/`、`tmt/router.py`、`scripts/version-scan.sh`、`cron/*`、`memory_tokenize.py`、`skill_sync.py`、`palace.py` 示例
- **运行时语义不变**: 纯文案; `scripts/version-scan.sh` 的局部变量 `gz_ver`→`prd_ver`(脚本内自用); `palace.classify` 示例与 `tests/test_palace.py` **配对修改**, 测试 194 passed + 6 skipped(契约用例需 Hermes 侧 mcp SDK, 最小安装自动 skip)
- **有意保留**: `CHANGELOG` / `ROADMAP` / `docs/**` 中的历史记录 —— 它们是发布日志, 不改写历史(与「保留 git 历史」同一原则)
- **判据(本次审计)**: 全历史 + 全树**两层扫描** —— 云厂商访问密钥 / 代码托管平台令牌 / 模型服务类密钥 / 私钥头 / 协作平台令牌 / 云厂商 SecretId / Bearer-JWT / Windows 用户路径 / SSH 密钥名 / 本机家目录 / 邮箱 在当前树**均 0 命中**; 唯一的非回环 IP 是 `pg_dump` 版本注释里的 `16.14`(假阳性); 历史里的 SSH 隧道文档为 `your-server-ip` + `/path/to/your-key.pem` 占位, 端口方案属**侦察级**; 因此 git 历史整体保留, 不做 force-push 清史
- **历史残留(知情接受)**: 下列非凭据信息在清理前的历史快照中仍有留存, 经评估**保留**(与「保留 git 历史作发布日志」同一原则)。⚠️ **具体值不在本文件复述**(脱敏清单自身不得含真实值), 见内部审计记录 `Mnemosyne #18926`:
  1. **个人站点域名** — 仅 1 个快照的资产索引文档(`docs/github-assets-index.md` @ `2de398f`, 该文件当时即已删除); 同文档另含个人研究项目名与 DOI(作品集披露); 当前树已清
  2. `pg_dump` 的 `\restrict <随机串>` 会话标记 — 3 个快照的 schema dump(`442f333`/`515e437`/`63e8869`); **非真实凭据**(仅 pg_dump 的会话安全标记), 但形式像密钥; 当前 `docs/schema.sql` 已无
  3. 历史运维文档(已随文件删除)含部署路径、服务用户、回环地址与端口 —— 侦察级
  4. 判断依据: **任何历史快照中均未出现可用凭据**(访问密钥/密码/令牌/私钥/真实公网 IP)。彻底抹除的代价 = `git-filter-repo` + force push + 重建 39 个 tag/Release —— 破坏性动作, 需显式授权

## release · v7.8.1 (2026-08-24) — 当日失明修复回库 + MCP 2.0 适配

> 生产领先于仓库的漂移闭环: GZ 已跑两周的 v7.8.1 修复(新记忆当日失明 P0)正式入库发布, 并同步 MCP 桥 mcp 2.0 适配与测试断言修正。

### 🩹 修复回库 (GZ 生产已验证)
- **新记忆当日失明 P0 (v7.8.1 核心)**: 写入即分词 `_tokenize_on_write`(主写入+会话归档两处), 消除 BM25 最长 24h 失明窗口; BM25 平滑 `LEAST(1.0, 0.5+SUM/8)` 无关键词中性 0.5 分; 向量权重 0.40→0.50, rel/heat 0.15→0.10 (三处公式统一: dialectic/主搜索/fallback)
- **测试断言同步**: test_weighting.py reliability 权重 0.15→0.10 (v7.8.1 权重变更后测试过时, 194/194 全绿)

### 🔌 MCP 桥 mcp 2.0 适配 (Hermes 侧, 2026-08-24 实测)
- `integrations/hermes-mcp/mnemosyne_mcp.py`: mcp SDK 2.0 移除 `list_tools/call_tool` 装饰器 → 改构造回调注册 `Server(name, on_list_tools=..., on_call_tool=...)`; 15 工具完整保留; stdio 冒烟 + 端到端检索实测通过 (Hermes 0.20.5 上游固定 mcp==2.0.0)

### 🧹 生产仓库对齐
- tmt/router.py 注释脱敏 (GZ 服务器→生产服务器)
- integrations/hermes-provider 版本号同步 v7.8.1

---

## release · v7.8.0 (2026-08-18) — 精准排雷 + 架构瘦身

> 🔧 **发布后装修 (同日)**: ⑤ 删除已禁用的 Web 记忆浏览器(browser.html, API Key 明文风险弃用) ⑥ 新增 GitHub Actions CI(pytest 双 Python 版本) + README CI badge ⑦ 海报换代 v7.8.0(数据快照 12,427/8,299/12,646, v7.7 技能资产翼 + v7.8 真 BM25/排雷瘦身, 15 工具)

> 🔧 **发布后补丁 (同日)**: ① tome_links 残留补切 — palace.py 仍会重建该表(本地+GZ), 生产库残留空表, 已删代码+测试(195→194)+生产 DROP, 21 表=schema.sql 对齐 ② 版本号 9 处一致性修复(README_CN/PROGRESS/ROADMAP/INSTALL/provider VERSION/requirements) ③ 数据快照刷新(12,427 记忆 / 8,299 facts / 12,646 卡片) ④ optimize-plan-v8.md 过时标注

### 🧹 病灶切除 (三方专家审计 + 实修)
- **drawer_pipeline dedup 每日崩溃修复**: PostgreSQL `::` 优先级高于 `||` 致残缺 JSON 类型转换报错; 改 jsonb_build_object, merged_from 追加保留合并链; 合并后重算 embedding(list→str 传 vector)
- **entities 噪音清洗**: 43,256→21,113 条(纯词规则+wiki 豁免), 570MB→278MB
- **主搜索真 BM25**: jieba 分词 + memory_keywords TF 加权(替换 ILIKE 假 BM25), 精确数字查询质变; 每日 4am 增量分词
- **perf_alert 修复**: pg_stat_statements 累计均值误报 → 30min 时间窗 + 告警去重
- **589 条 NULL embedding 补齐** + **facts 模板前缀剥壳 7,528 条**(存 metadata.fact_type)
- **真 SQL 集成测试 5 条**(本地 mnemosyne_itest 库), 195 全绿; 修复前必须报错的防回归测试

### 🗡️ Apache AGE 切除 (PG 升级自由)
- 11 张业务表 ag_catalog→public; cypher 多跳/图写入全删; wiki_extract 只抽实体(省 LLM token); wiki_dedupe 删除
- PG shared_preload_libraries 去 age; DROP EXTENSION age; schema.sql 全 public 化 28 表
- graph/search 降级纯 SQL(entities→memory_entities 邻接)

### ✂️ 瘦身第二刀 (无消费端资产, 28→21 表)
- 切除: memory_chunks(231MB)+chunk 管道 / memory_pointer / conversation_messages(35MB, 双份存储) / tome_links / api-halls+gates / api-tools+tool_archives / api-projects / api-response(v5 遗留)
- provider on_session_end 移除会话全保真同步(Hermes state.db 为权威)

---
## release · v7.7.0 (2026-08-18) — 调度大厅: 注入智能内核

### 🆕 程序性记忆翼 (技能资产)
- 新表 `skill_assets`(技能名/描述/分类/状态/使用统计/embedding) + `skill_keywords`(BM25 索引, 租户隔离)
- 技能=可执行记忆: 与陈述性记忆并列, 状态机对齐 Hermes curator(active/stale/archived, 永不 DELETE 只流转)
- `POST /api/v1/skills/sync` 幂等批量同步(空描述用 name+category 兜底 embedding, 单条失败容错保留已有)
- `POST /api/v1/skills/search` 语义召唤(向量+BM25+RRF+状态权重 active 优先, 沉寂可唤醒)
- `PATCH /skills/{name}` 状态流转(唤醒) / `POST /skills/{name}/touch` 使用计数
- 配套 `skill_sync.py`(WSL 技能→GZ) + `skill_tokenize.py`(jieba 分词→skill_keywords)

### 🆕 注入调度大厅
- `POST /api/v1/injection/plan`: 按场景(查询)返回注入流 {相关技能+相关记忆+热点钩子}
- 注入=认知调度: 场景×价值 动态编译, 不再是固定热度 topN
- 服务端硬校验 limits(skills≤8/memories≤10/hooks≤10), 空 context 直接返回, 单通道失败静默降级

### 🆕 Embedding 深度优化
- 实测 ARK doubao-embedding-vision **不支持批量 input**(多 input 只返第一条) → 并发逐条替代(MAX_CONCURRENT=8, 环境变量可配)
- LRU 缓存(OrderedDict 标准实现: 命中 move_to_end + 超限淘汰最久未用) + 磁盘持久化(600 权限, 损坏自愈)
- 指数退避重试(429/5xx, 3 次) + 冷缓存 50 条 1.9s(旧串行 14.7s, **提速 7.7 倍**)

### 🔴 修复: RRF 融合 pid 空间不一致 (真 bug)
- BM25 通道 pid 是 DB skill_id, 向量通道误用列表 index → 融合后越界 IndexError 被静默吞掉 → 注入 plan 返回空
- 修复: 两通道统一用 skill_id, 新增 test_injection_plan_v77.py 固化防回归

### ✅ 验收
- pytest **190 passed**(167 原有 + 11 skill_sync + 7 embedding + 5 injection_plan)
- hermes verify ok=true, readiness 200
- 豆包 4 角色专家验收(架构/向量/运维/产品): 2 P0 + 8 P1 全部修复后通过

## release · v7.6.2 (2026-08-15)

### 🔴 修复: project_id 类型契约 (str→int)
- 根因: `MemoryCreate.project_id` / `MemorySearch.project_id` 模型定义 `Optional[str]`,但 DB 列是 bigint(int8)。写入时传档号字符串(如 'proj_xxx')→ asyncpg 500 崩溃
- 修复: 两处模型改为 `Optional[int]` — pydantic 自动解析,传档号字符串 → 422 友好报错,不再 500
- 实测: 复现场景 422 ✓ / 数字 id 写入 200 ✓

### 🔴 修复: 知识类误冻 frozen (高价值记忆隐身)
- 根因: v7.3 Rank 百分位分档 (PERCENT_RANK 后 30% → frozen),把 knowledge/pitfall/reference/preference 高价值记忆挤进 frozen 区;而搜索默认 `include_frozen=false` 排除 frozen → 该找的找不到
- 修复: main.py 两处 Rank 分档 CASE(常规 reflect + 周日强制全量)给知识类加保底 `cool`(永不 frozen,可降温不可隐身)
- 存量修复: 224 条误冻知识类已解冻回 cool
- 实测: frozen 2531→2307(仅剩 session/worklog 冷碎片),知识类默认搜索命中 ✓

## fix · 遗漏清理 (2026-08-11)

### 版本号修复 (对外 API 自描述)
- main.py: root 端点 / FastAPI title / capabilities service 名 — v6.x → v7.6.1
- GZ 已部署验证: capabilities 返回 Mnemosyne OS v7.6.1

### 内部代号脱敏 (代码注释)
- main.py: GZ → 生产服务器; Qwen3-Embed (GZ :11436) → 本地 fallback; noah 示例 → default
- palace.py / tmt/router.py: 示例与时区注释 GZ → 通用

### 废弃清理
- cron/cron-hermes-kanban.sh 删除 (kanban 派发模式已废弃)
- GZ crontab 移除 kanban dispatch 残留 (每2min)
- docs/requirements.txt 删除 (历史 pip freeze 快照, 含 llama_cpp_python 误导)
- docs/schema.sql 清理 4 个 tmt_*_old 残留表 + 6 索引 + 1 失效 FK (实测: 34→30 表, 0 残留)

### 数据同步
- README/README_CN/WHITEPAPER: 记忆数 8,873/8,647 → 9,952+
- INSTALL.md: 表数 32+ → 30
- PROGRESS.md: 运行状态 v7.0.0 → v7.6.1, 下一步对齐 v8.0

## docs · 仓库装修第二轮 (2026-08-11)

### 结构规整
- wiki_bm25/wiki_graph/wiki_extract/wiki_tokenize/wiki_dedupe/wiki_eval/wiki_sync_check + wiki_dict.txt → `wiki/` 子目录
- main.py: 3 处引用修复 (wiki.wiki_bm25 / wiki.wiki_graph / wiki/wiki_dict.txt)
- wiki/ 内 5 个独立脚本 sys.path 指向仓库根 (tmt/core 可导入)
- tests/test_wiki_bm25_v75.py: 引用更新
- GZ 生产同步: rsync wiki/ + main.py + crontab 4 条加 wiki/ 前缀 + 重启验证 ✅

### 元信息
- GitHub About 描述更新: v7.x 能力 + 中英双语

### 规则固化
- CONTRIBUTING.md: 新增「仓库结构规范」+「编辑发布规则」(版本三处一致/双语同步/文档表/CHANGELOG/ROADMAP/GZ同步/测试/审计)

### 海报
- docs/poster.html + poster.png: v7.6.1 重做 (暖色手绘风 + 姬卡立牌 + v7 系列 9 项新能力 + 860x1900)

## docs · 对外分享文档体系 (2026-08-11)

### 新增
- `INSTALL.md`: 分环境安装指南 (Linux/macOS/WSL + 数据库初始化 + 模型后端 + FAQ)
- `integrations/hermes-provider/README.md`: Hermes 适配文档 (11 工具 + 自动钩子 + 配置)

### 重写
- `AGENTS.md`: 76 → 236 行。AI 对接手册 (API 端点速查 / 环境变量全表 / Hermes/MCP 接入 / 最佳实践)
- `README.md` / `README_CN.md`: Quick Start 修正为可执行路径 (补数据库步骤 + INSTALL 入口) + Start-Here 路径分流表

### 移除
- Docker 相关规划 (docker-plan.md 及 README/ROADMAP/INSTALL 引用) — 用户决策暂不做 Docker

### 修复
- `docs/schema.sql`: pg_dump 外键顺序 bug (memory_pointer 引用未建 memories 表) + 宫殿段 search_path + 迁移残留表标注
- `requirements.txt`: 补 `jieba` (v7.5 WIKI BM25 硬依赖, 缺失会导致 ImportError)
- `integrations/hermes-provider`: 同步 Hermes 运行版本 (10 → 11 工具, 补 palace_summon)
- `deploy/mnemosyne.service`: 通用化 (原为生产环境专用, 且被 .gitignore 排除)

### 脱敏
- CHANGELOG/README/.gitignore 内部代号 GZ → 生产环境/生产服务器

## v7.6.1 · 三分类记忆打标 (2026-08-10)

### 新增
- `metadata['memory_type']` 三分类打标: episodic(情景: session/chat/worklog) / semantic(语义: fact/preference/knowledge) / procedural(程序: pitfall/ops/deploy/project)
- 新写入自动打标（category 规则映射, 零 LLM 成本）
- 存量 9952 条批量打标完成（semantic 7202 / episodic 2706 / procedural 45）

## v7.6.0 · 记忆隔离与来源追踪 (2026-08-10)

### 新增
- `MemoryCreate.source` 字段 → 写入 metadata['source']（支撑压缩归档/子代理批次召回）
- `GET /memories?source=` 过滤参数（metadata->>'source' 精确过滤，OVERFLOW 批次召回用）
- 分身记忆隔离：mnemosyne-agent/website-agent 不再收敛到 default（分区防污染）

### 配套（Hermes 集成层）
- 钩子机制 + on_pre_compress 防丢闭环（压缩前归档带 ID 钩子）
- prefetch 双因子优化（低热度过滤 + 上限 3 条）

### 修复
- content 分身 MNEMOSYNE_USER_ID 误配 catnest-agent → 改 content-agent

# Changelog

## v7.5.1 (2026-08-10) — 图谱质量 + 评测扩充 (专家评审验收)

### ✨ 新功能
- **eval 评测扩充**: 20 → 30 条查询 (长尾/跨域/边界), 指标 precision@3 + recall@3 + MRR
- **图谱边定期去重**: wiki_dedupe.py (生产 cron 周一 8am), 防 AGE 重复边积累

### 🔧 修复
- **图谱边去重**: 3,263 → 1,006 条 RELATED_TO (删 2,257 重复, 跨页通用实体对), wiki_extract 建边前查重防复发
- 图谱回归验证: 浑天芯算/记忆宫殿/诺亚 全部命中, 多跳跨页面正常

### 📦 其他
- 专家团 4 角色评审: 全部条件通过, P1 修复完成 (图谱回归/eval扩充/去重cron)
- 完整验收 12/12 全绿: 功能链路/数据完整/图谱质量/检索/质量
- 测试: 167 passed


## v7.5.0 (2026-08-10) — WIKI 检索优化 (存了要用起来)

### ✨ 新功能
- **BM25 关键词通道**: jieba 分词 → wiki_keywords 表 (71 页 47,619 tokens) → BM25 打分 → RRF 融合 (k=60), 补上纯向量的关键词盲区
- **专业词典**: wiki_dict.txt 145 词 (wiki 高频词 + 核心术语), 浑天芯算/金闪闪协议等术语正确切分
- **图谱扩展通道 P1**: 实体锚定 + AGE 1跳 RELATED_TO → 页面评分; 加成模式防噪音, 默认关 (可选增强)
- **palace summon 第4通道「文库」**: 查记忆顺带带出相关论文/方案
- **eval 定期评测**: 20 查询 × 三档 (纯向量/向量+BM25/全通道), 生产 cron 每周一 7am, 防漂移告警
- **rerank 可选**: 复用 rerank_docs (豆包 embedding 相似度重排, 默认关)

### 📈 效果
- A/B 评测 20 查询 precision@3: 纯向量 95% → 向量+BM25 **100%** (平均排名 1.20→1.00)
- 术语查询 BM25 强命中: 浑天芯算 8.15 / 金闪闪 15.25 / 概念裂变 14.75

### 🔧 修复
- create 关键词索引阈值 50→20 (短内容也要 BM25 索引)
- search 候选池 25→50 + BM25 独有页面补查 (防止新页面被向量排名挤出)
- BM25 IDF 逐行计算 (稀有词 IDF 正确)

### 📦 其他
- 专家团 4 角色评审: 全部条件通过, P1 修复完成 (词典)
- Hermes 适配测试 8/8 通过
- 测试: 167 passed (含 BM25/RRF 10 用例)
- hermes verify ok=true


## v7.4.0 (2026-08-10) — WIKI 知识图谱 MD 记忆

### ✨ 新功能
- **全文快照档案馆**: wiki_pages 加 source_path/source_url/content_hash/source_type/source_lost 列, 论文/文章全文入库防源损毁, 源地址仅作指针
- **md_ingest 导入管线** (`scripts/md_ingest.py`): 本地权威单向同步 — `--sync` 导入/更新 (hash 幂等: 同源同hash→exists, 异hash→updated+版本历史), `--verify` 校验 (一致/漂移/源丢失), 源丢失后线上快照仍可查证
- **LLM 实体+关系抽取** (`wiki_extract.py`): 替代正则粗提取, 每页抽 8-20 实体 + 5-15 关系 → entities + wiki_entities + AGE 图 (RELATED_TO / MENTIONS 边)
- **by-source 快速查证端点**: GET /api/v1/wiki/by-source 按来源路径/URL 精确查快照
- **语义搜索升级**: POST /api/v1/wiki/search 直查 wiki_pages.embedding HNSW (原查 versions 表, 基本搜不到)

### 🔧 修复
- 修 wiki 端点重复定义 bug: main.py 415 简单版 vs 1945 完整版同路径, 统一为 body model (WikiPageCreate/WikiSearchRequest), 行为一致

### 📦 其他
- wiki_entities 关联表 + wiki_pages.extracted_at 标记
- 测试: tests/test_wiki_v74.py 9 用例 (幂等/指纹/抽取解析), 全量 157 passed
- hermes verify ok=true


## v7.3.0 (2026-08-09) — 🧠 综合算法 + 高效检索 (从遗忘转向整理优化)

**核心理念**: 记忆不该强调遗忘, 该强调整理优化。提及即升级, 检索分区域, 指针快速定位。用户转向: 时间久远但总被提及→升级; 降级后被多次提起→再升级 (双向动态)。

### 🧠 综合记忆强度 Rank
- **Rank = 0.3S + 0.3R + 0.2ln(mention+1) + 0.2heat** (多维融合, 权重可配)
- **双向动态**: 提及→mention+1→R回弹→累计5次S+1 (降级可回弹)
- 提及信号: 显式(搜索/召唤命中) + 隐式(对话实体匹配, 阈值>0.85)
- 抽屉改 Rank 百分位分档: hot前10% / normal 10-30% / cool 30-70% / frozen 70%+

### ⚡ 快速全盘指针
- **memory_pointer 表**: 全库 1/10 体积, B树索引 <10ms
- `GET /pointers/top` (Rank topN, 可选分区) / `GET /pointers/search` (指针级检索)
- `POST /pointers/trigger-mention` (对话提及钩子)

### 🗂️ 区域化检索
- 混合搜索默认限定 hot/normal/cool (frozen 排除), 不足才全库兜底
- Type A 档号哈希 O(1) / Type B 分区指针 / Type C 全库向量兜底

### ⚠️ 发布途中真实事故（已修，教训保留）

**现象**：部署到生产后，**第一发写入即 500**。
```
asyncpg.exceptions.InvalidColumnReferenceError:
there is no unique or exclusion constraint matching the ON CONFLICT specification
```
**根因**：`dedup_fingerprint_key` 是**部分唯一索引**（`WHERE dedup_fingerprint IS NOT NULL`），
而写入写的是 `ON CONFLICT (dedup_fingerprint)` —— PostgreSQL 的部分索引推断**要求谓词显式匹配**，
缺谓词直接报错，整条写入路径挂掉。
**修法**：`ON CONFLICT (dedup_fingerprint) WHERE dedup_fingerprint IS NOT NULL DO NOTHING`
（保留部分索引：只约束有指纹的行，1.6 万条历史 NULL 行无需回填）

**为什么既有单测没抓到（本版最重要的教训）**
- 已有测试只验证「索引能拦住重复指纹」（裸 `INSERT`），
  **从没跑过产品代码里那条真实的 `INSERT ... ON CONFLICT` 语句**。
- **测了索引 ≠ 测了使用索引的那条 SQL。**
  凡"代码里拼出来的 SQL"与"库里建的对象"有耦合，就必须把真实 SQL 拉出来跑一遍。
- 修法：新增 `tests/test_v8_write_path.py` —— **从 `main.py` 源码正则抽出真实 SQL**，
  绑上占位值投到库上执行。源码与库对象一旦不匹配立刻红。
  反证已验证：临时删掉谓词 → `test_w2` 立即失败。
- 本次由**发布的第三层（生产功能实测）**抓到 —— 这就是"三重验证"不是形式主义的证据。

### 🧪 测试
- test_rank_v73.py 13 项 (Rank公式/S升级/抽屉分档)
- 全量 pytest 148 passed

## v7.2.0 (2026-08-09) — 🧠 Bjork S/R 分离 + 生产调优

**核心理念**: 遗忘 ≠ 丢失。存储强度 S 不衰减(信息永远在), 检索强度 R 衰减(访问性下降可恢复)。访问重置 R=S + S 微增(间隔重复效应)。网络调研: Bjork New Theory of Disuse + FSRS/Anki 间隔重复。

### 🧠 S/R 双强度 (Bjork 落地)
- **storage_strength S** (1-10, 不衰减): 手动/pin=7, 知识=5, 普通=3
- **retrieval_strength R** (1-10, 指数衰减半衰期30天): R*0.5^(days/30), 下限1
- **访问重置**: 命中后 R=GREATEST(R, S) (heat_hits)
- **抽屉划分新规则**: hot(S≥7且R≥5) / normal(S≥5或R≥3) / cool(S≥3) / frozen(S<3且R<2)
- **pin 兜底**: R 永不低于 5 (永久卷)
- **回退开关**: metadata->>'use_sr'='false' 恢复纯 heat 模式
- 效果: 高价值记忆永不冻结(底蕴), 低价值久未访问自动沉降

### 🔧 生产调优
- 启用 pg_stat_statements 慢查询监控 (原缺失, 最大隐性风险)
- uvicorn workers 2→4 (压测 234 req/s, 100/100 OK)
- perf_alert.py 每30分钟水位巡检 (内存/磁盘/PG连接/慢查询, 超阈值才告警)
- PG 参数确认合理 (shared_buffers 4G/effective 10G)

### ⚠️ 发布途中真实事故（已修，教训保留）

**现象**：部署到生产后，**第一发写入即 500**。
```
asyncpg.exceptions.InvalidColumnReferenceError:
there is no unique or exclusion constraint matching the ON CONFLICT specification
```
**根因**：`dedup_fingerprint_key` 是**部分唯一索引**（`WHERE dedup_fingerprint IS NOT NULL`），
而写入写的是 `ON CONFLICT (dedup_fingerprint)` —— PostgreSQL 的部分索引推断**要求谓词显式匹配**，
缺谓词直接报错，整条写入路径挂掉。
**修法**：`ON CONFLICT (dedup_fingerprint) WHERE dedup_fingerprint IS NOT NULL DO NOTHING`
（保留部分索引：只约束有指纹的行，1.6 万条历史 NULL 行无需回填）

**为什么既有单测没抓到（本版最重要的教训）**
- 已有测试只验证「索引能拦住重复指纹」（裸 `INSERT`），
  **从没跑过产品代码里那条真实的 `INSERT ... ON CONFLICT` 语句**。
- **测了索引 ≠ 测了使用索引的那条 SQL。**
  凡"代码里拼出来的 SQL"与"库里建的对象"有耦合，就必须把真实 SQL 拉出来跑一遍。
- 修法：新增 `tests/test_v8_write_path.py` —— **从 `main.py` 源码正则抽出真实 SQL**，
  绑上占位值投到库上执行。源码与库对象一旦不匹配立刻红。
  反证已验证：临时删掉谓词 → `test_w2` 立即失败。
- 本次由**发布的第三层（生产功能实测）**抓到 —— 这就是"三重验证"不是形式主义的证据。

### 🧪 测试
- 新增 test_bjork_v72.py 14 项 (衰减/重置/抽屉/pin兜底)
- 全量 pytest 128 passed

## v7.1.0 (2026-08-09) — 🗄️ 抽屉化记忆 (双轨制)

**核心理念**: 遗忘是检索质量干预,不是存储问题。温度抽屉(热/常温/冷却/冻结) × 时间抽屉(近期/中期/远期) 双轨制,热度轴+时间轴+特殊标记自动化遗忘。用户启发: 抽屉化记忆(热度/常温/冷藏 × 近期/中期/远期) + 压缩去噪/去重/蒸馏合并; 理论根基: Bjork 双强度理论(存储强度不衰减,检索强度衰减) + Mem0 四遗忘策略 + SCM 睡眠整合记忆。

### 🗄️ 双抽屉字段 (migration v7.1)
- **temp_drawer**: hot(≥0.7) / normal(0.3-0.7) / cool(0.1-0.3) / frozen(<0.1)
- **time_drawer**: recent(<30d) / mid(30-90d) / long(≥90d), 基于 COALESCE(last_accessed, created_at)
- CHECK 约束 + 局部索引 + 存量回填 (热75/常温1984/冷却5247/冻结2048)

### 🧠 reflect 增强
- 双抽屉随 reflect 自动流转 (每4h light / 每日 deep)
- **遗忘候选标记**: frozen+long+非pin+非preference → forget_candidate=true
- 遗忘候选每轮额外降温 -0.03 (加速沉降, 对应 Mem0 salience 思路)

### ✏️ 更新端点 (补齐记忆修改权)
- `PUT /api/v1/memories/{id}`: 修改 content/category/importance/heat_score/metadata/pin
- `PATCH`: 部分更新别名; content 变更自动重算向量+重分类+记 trace
- pin=true 强制 heat≥0.5 (钉卷至少回常温)

### 📊 抽屉 API
- `GET /drawers/status`: 双抽屉分布 + 遗忘候选数 + 钉卷数
- `GET /drawers/forget-candidates`: 列出遗忘候选
- `POST /drawers/forget`: 手动遗忘 (留统计指纹, 软删可恢复)

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
- 修复: 生产增强版之前未同步回仓库 (版本一致性)

### 📌 已知问题 (外部依赖, 不修)

- TMT L3 蒸馏连续 3 天失败 (豆包 API 400/超时波动) — 模型有效(直测 200), cron 每日自动重试 + health monitor 已告警

## v6.1-dev (2026-08-05)

### 🧪 知识蒸馏管道 (P0-1, MVP)

**动机**: 分类失衡 (session+worklog 88%, knowledge 9%) — 蒸馏只做了分类整理, 没做真正知识提炼。

**新增**: `tmt/distill.py` — 知识蒸馏管道 v0.1
- 设计来源: 爆炸遗产考古 (NCP-008 知识吸收七步 + 认知AI底座 TEL/MAIL 协议)
- 流程: 信号词候选筛选 → TEL 组装 → 豆包 Lite JSON 凝练 → ANN 去重闸机 (>0.92 跳过) → 入库 (knowledge→archive / pitfall→engineering) → metadata 溯源
- 用法: `python3 tmt/distill.py --batch N [--dry-run] [--stats]`

**部署**: 生产 cron 每日 1:10 批量 60 条 (首轮 30 条: +22 knowledge, +1 pitfall, 5 fail 豆包偶发空返回下轮重捞)

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
- 生产备份：`main.py.bak.20260802` / `core/llm.py.bak.20260802` / `tmt/router.py.bak.20260802(.2/.predegrade)`

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
