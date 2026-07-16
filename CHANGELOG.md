# Changelog

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
