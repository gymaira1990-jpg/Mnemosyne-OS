# 📜 记忆宫殿 · 变更日志

## 2026-06-07 — Phase 3.5 执行断层修复 🚀

> 审计发现三大执行断层，一次修通。TMT 蒸馏管道首次真正运转。

### 🔴 P3.5-T1: TMT 蒸馏管道挂载
- **问题**: `tmt.py` 的 `APIRouter(prefix="/api/v1/tmt")` 从未在 `main.py` 中 `include_router`
  - L2/L3/L4/L5 蒸馏代码完整但 HTTP 层根本不存在这些路由
  - cron 脚本调的是 `/memories/evolve`（去重），不是 TMT 蒸馏
- **修复**: `main.py` 增加 `from tmt import router as tmt_router` + `app.include_router(tmt_router)`
  - startup 时注入 `tmt_module.pool` / `embed_fn` / `llm_url`
  - 修复 `/consolidate/session` 不读取 interval 参数的 bug
  - 修复 L2 查询过滤条件（只查 `tmt_level=1` 的孤儿碎片）
- **验证**: L2 首条蒸馏成功 (9碎片→1会话) + L3 首条日报蒸馏成功 (8会话→1日报)

### 🔴 P3.5-T2: -R 11435 反向隧道
- **问题**: GZ 无法访问 WSL GPU LLM（端口 11435），蒸馏走 CPU Qwen3.5-2B（单次 90s+）
- **修复**: autossh 加入 `-R 127.0.0.1:11435:127.0.0.1:11435`，更新 systemd user service
- **效果**: 蒸馏从 CPU 90s+ 转为 GPU ~20s

### 🟡 P3.5-T3: 搜索权重修正
- **问题**: 排序公式中 `0.15 * (reliability * 0.15)` 和 `0.15 * (heat * 0.10)` 实际贡献仅 2.25% 和 1.5%
- **修复**: 去除内部乘系数 → `0.15 * reliability` + `0.15 * heat`
- **效果**: 热度/可信度真正参与排序

### 🟢 P3.5-T4: JSON 解析容错
- **问题**: `parse_json_response` 遇到 reasoning 模型输出崩溃
- **修复**: 增加 reasoning 前缀去除 + 尾逗号清洗 + 单引号转义 + `json.JSONDecodeError` 兜底返回

### 📋 变更文件

| 文件 | 变更 |
|:-----|:-----|
| GZ `main.py` | 🆕 tmt 模块引用 + include_router + startup 注入 + 搜索权重修正 (3处) |
| GZ `tmt.py` | 🆕 解析逻辑加强 + session 路由接受 interval + L2 过滤条件修正 |
| WSL `autossh-gz-tunnel.service` | 🆕 ExecStart 加入 `-R 11435` |
| WSL `tmt-consolidate-session.sh` | 🔄 目标从 `/memories/evolve` 改为 `/tmt/consolidate/session` |

### 📊 当前系统状态

| 指标 | 数值 |
|:-----|:-----:|
| Memories | 338 条 |
| Entities | 295 个 |
| Memory-Entity 关联 | 238 条 |
| TMT Sessions (L2) | 16 条 (15 default + 1 g-cat) |
| TMT Daily (L3) | 2 条 (6/2 + 6/3) |
| TMT Weekly (L4) | 0 条（等积累） |
| TMT Profiles (L5) | 0 条（等积累） |
| API 路由 | 43 条 (33 main + 10 tmt) |
| 热度分布 | 🔥36 / 👍44 / ❄️56 / 💀177 |

### 📝 文档更新

| 文件 | 变更 |
|:-----|:-----|
| `README.md` | 数据对齐 + 新增修复记录 |
| `产品说明书.md` | 版本升 v3.0 + 功能校正 + 已知问题章节 |
| `架构设计/升级路线图_v3.0.md` | 新增 Phase 3.5 完整记录 |

---

## 2026-06-04 — Phase 3 启动：矛盾检测 + Wiki 知识库 🚀

### ✨ P3-T1: 矛盾检测 (Conflict Detection) ✅
- **写入时自动检测**：`detect_conflict` 函数对比语义相似度 + 文本差异
  - `dist < 0.15 + ratio > 0.85` → 合并：增加访问计数
  - `dist < 0.12 + ratio < 0.5` → 矛盾：旧标记过期 + 新标记 `metadata.conflicts_with`
- **查询端点** `GET /api/v1/memories/conflicts` — 列出所有带矛盾标记的记忆
- **Hermes 工具** `mnemosyne_conflicts(limit)` — 新会话可用

### ✨ P3-T3: LLM Wiki 知识库 ✅
- **表已存在** `wiki_pages` — 含 title/content/user_id
- **端点三件套**：list / get / create
- **Hermes 工具** `mnemosyne_wiki(action=list|get, page_id, limit)`

### 📋 变更文件
| 文件 | 变更 |
|:----|:----:|
| GZ `main.py` | 🆕 矛盾metadata存储 + conflicts端点 + wiki三端点 + media四端点 |
| `mnemosyne_provider.py` | 🆕 CONFLICT_SCHEMA + WIKI_SCHEMA + MEDIA_SCHEMA + preheat初始化 |

---

## 2026-06-04 — Phase 2 T1+T2+T3 完成

### ✨ P2-T1: 辨证推理层
- **GZ 端点** `POST /api/v1/dialectic` — 搜索 + L2 会话上下文综合
- **Hermes 工具** `mnemosyne_dialectic` — 返回结构化记忆树

### ✨ P2-T2: 三级读取 (Tiered Read)
- **L5 摘要** (200字) / **L3 概览** (800字) / **L1 全文**
- **Hermes 工具** `mnemosyne_tiered_read(memory_id, level)`

### ✨ P2-T3: 会话切换 (Session Switch)
- `on_session_switch` 回调 + 队列检查

### 📊 GZ 路由扩展
```
GZ main.py: 34 路由 (from 27)
```

---

## 2026-06-03 — Phase 1 完成 · 系统全面上线

### 基础设施建设
- systemd 三层常驻 + GPU 加速 (llama-server-gpu + CUDA 12.6)
- SSH 隧道 -R 11435 修复（GZ→WSL LLM 反向代理）
- Mnemosyne 搜索挂死修复（BM25 参数索引 bug）
- GZ Search 全面修复（rerank_lock 死锁 + 5路并发）
- TMT L2/L3 蒸馏修复、热度衰减触发
- 一键验证 13/13

### 初版文档建设
- `README.md` / `产品说明书.md` / `升级路线图_v3.0.md` / `CHANGELOG.md`
- `架构设计/外部系统调研.md` / `v4.0_升级方案_专家团队.md`
- 日常运维/ 一键验证 + 故障排查手册

---

## 2026-06-01 — 项目启动

- 基于 `noah-gen3-type2` 项目初始化记忆宫殿工作区
- 构建 GZ 服务端 (FastAPI + PostgreSQL 16 + pgvector)
- 构建 MCP 桥接 (write_queue + message_cleaner + mnemosyne_provider)
- 构建 TMT 蒸馏引擎 (tmt.py, APIRouter)
- 部署 Hermes Provider (memory 工具链)
