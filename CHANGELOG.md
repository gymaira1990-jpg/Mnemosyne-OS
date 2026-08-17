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
