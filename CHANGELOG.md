# Changelog

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
