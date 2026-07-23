# Changelog

## v5.5.1 (2026-07-23)

### 修复 — TMT 蒸馏质量 + JSON 解析容错
- **L3 每日蒸馏加固** — Prompt 添加强制 JSON 输出指令，防止 LLM 返回思考过程
- **parse_json_response 增强** — 支持 markdown code block 提取、多语言思考前缀剥离、无 JSON 时智能文本摘要
- **回退链完善** — JSON 解析失败时二级回退（去除非ASCII → 文本摘要）

## v5.5.0 (2026-07-23)

### 核心 — 时间有效性 + Benchmark
- **时间有效性窗口** — 搜索/列表/统计 5处SQL 过滤过期记忆 (valid_to < NOW())
  - 67条已过期记忆不再出现在搜索结果中
  - list_memories 新增 `expired` 返回字段
- **记忆基准测试** — 39 用例覆盖 4 个模块
  - test_temporal_validity: 6 用例 (过期过滤 + SQL 验证)
  - benchmark/test_recall: 5 用例 (层级架构 + 权重)
  - benchmark/test_conflict: 5 用例 (merge/fresh/conflict)
  - benchmark/test_weighting: 5 用例 (热度+可信度)
- **Web 记忆浏览器** — 已开发但因安全原因禁用 (API Key 明文风险)
  - 文档保留于 docs/browser.html，待桌面端到端加密方案

## v5.4.0 (2026-07-23)

### 核心 — 三馆激活
- **闸机接入异构审计** — promote 时自动调用双模型 (豆包lite+code) 交叉验证
  - 一致通过 → 升级 + reliability 调整
  - 意见分歧 → 拒绝 + gates 记录失败原因
  - 审计调用失败 → 降级直通 + 记录 warning
- **建议清单端点** — `GET /api/v1/halls/suggestions` 只读返回升级/降级/遗忘候选项
- **工具归档路径修复** — 成功/失败统一先入工程馆，archive 仅通过 promote 进入

### 工程化
- **pytest 测试框架** — 18 个测试用例覆盖核心算法
  - test_detect_conflict: 文本差异 + 分类逻辑
  - test_heat_propagation: 热度传播公式 6 场景
  - test_hall_flow: 三馆流转规则矩阵 6 用例
- **AGE 查询安全加固** — 实体名/用户名单引号转义 + 截断

### 安全
- 隐私扫描通过 (零敏感泄露)

## v5.3.2 (2026-07-16)

### 核心
- **会话消息同步** — Hermes state.db → Mnemosyne conversation_messages 实时同步
  - 新增 `conversation_messages` 表 (session_id/role/content/tool_calls/timestamp/token_count/reasoning)
  - 新增 `POST /api/v1/sessions/{id}/messages` — Hermes 写入
  - 新增 `GET /api/v1/sessions/{id}/messages` — 前端读取（支持分页 before_id）
  - 新增 `GET /api/v1/sessions` — 会话列表
- Memory Provider `on_session_end` 增强：会话结束时自动推送全量消息到 Mnemosyne

## v5.3.1 (2026-07-16)

### 核心
- **时间排序检索** — 双轴检索协议后端支持
  - `GET /api/v1/memories` 新增 `sort` 参数：created_at(默认)/heat/updated_at
  - `GET /api/v1/memories` 新增 `search` 参数：关键词 ILIKE 过滤
  - `POST /api/v1/memories/search` 新增 `sort=created_at` 模式（纯时间排序，跳过 embedding）
  - 返回结构统一化：{memories, total, sort}
- 解决热度与时间维度混淆问题：热度=max(大事件)，时间=max(最近)

### 项目
- 本地 Workspace 文档同步至 v5.3.0（README/CHANGELOG/PROGRESS/ROADMAP）
- ROADMAP v5.3 新增时间排序检索任务 (#0, 🔧)
- 沙箱环境建立：~/mnemosyne-dev/

## v5.3.0 (2026-07-06)

### 仓库治理
- 分支对齐: master→main
- 统一仓库为唯一真相源 (GZ + WSL + GitHub)
- 删除顶层重复文件 (backends/llm/security/tmt)
- 目录重组: cron/ 集中管理定时脚本
- VERSION 文件 + 语义化版本规范
- AGENTS.md 分身使用手册
- ROADMAP.md 路线图
- .gitignore 增强 (IDE/OS/Deploy)
- LICENSE (MIT) + .github/ 社区健康模板

### Hermes 集成
- MCP Bridge 纳入 (integrations/hermes-mcp/) — 15 tools
  - 修复: 默认端口 8010→18010
- Memory Provider v5.3.0 纳入 (integrations/hermes-provider/)
  - 10/10 ABC Hook 全覆盖
  - message_cleaner + write_queue

### 安全性
- main.py API文档脱敏 (gz.g-cat.cn → your-server.example.com)
- mnemosyne_mcp.py 端口修复
- 隐私扫描通过 (零敏感泄露)
- GitHub Secret Scanning 已启用

## v5.2.2 (2026-06-27)

### 安全性
- 清除 `.env.example` 中的真实密码 → 通用模板 `env.template`
- 替换 `main.py` API 文档中的内部域名 `gz.g-cat.cn` → `your-server.example.com`
- `project_keywords.json` → `project_keywords.example.json`（通用示例）
- `archive_session.py` 从外部 JSON 文件加载项目关键词（不再硬编码）
- `.gitignore` 排除 `.env`、`project_keywords.json` 等私密文件

### 版本
- README badge: v5.0.5 → v5.2.2
- 版本历史补全 v5.1.0、v5.2.0、v5.2.1、v5.2.2
- PROGRESS.md 更新至当前状态

### 仓库
- 删除 `src/` 过期副本（25个文件）
- 删除 3个 `.bak` 备份文件
- 删除顶层重复文件 (`backends.py`, `llm.py`, `security.py`, `tmt.py`)
- `schema.sql` + `requirements.txt` 归档至 `docs/`

## v5.2.1 (2026-06-27)

### 核心
- 全模块豆包化 (5/5)：embedding/LLM/reflector/consolidate/reranker
- 零本地模型依赖：移除所有 Qwen/llama-server
- GZ 服务器释放 5.4GB RAM

### 基础设施
- systemd enabled（宕机自动恢复）
- SSH 隧道精简为 3条 -L（零 -R）

## v5.2.0 (2026-06-26)
- 项目记忆绑定：注册 + 搜索 + 自动标签 + 回填

## v5.1.0 (2026-06-26)
- 会话自动归档：Hermes 对话 → Mnemosyne 一键入宫

## v5.0.x (2026-06-24~25)
- v5.0.5: GitHub 打磨
- v5.0.4: 端云增量同步
- v5.0.3: RAG Chunking
- v5.0.2: TMT 蒸馏恢复
- v5.0.1: AGE 图修复
- v5.0.0: 7×24 独立运行

## v5.0-p1~p4 (2026-06-21~24)
- P1 地基：迁回 GZ + 豆包 API 全替代
- P2 灵魂：三馆闭环体系
- P3 算力：模型路由 Tier 1-5 + 审计 + 安全
- P4 集成：Hermes SDK + MCP + API 规范
