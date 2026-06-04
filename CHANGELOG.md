# 📜 记忆宫殿 · 变更日志

## 2026-06-04 — Phase 3 启动：矛盾检测 + Wiki 知识库 🚀

### ✨ P3-T1: 矛盾检测 (Conflict Detection) ✅
- **写入时自动检测**：已有 `detect_conflict` 函数对比语义相似度 + 文本差异
  - `dist < 0.15 + ratio > 0.85` → 合并：增加访问计数
  - `dist < 0.12 + ratio < 0.5` → 矛盾：旧标记过期 + 新标记 `metadata.conflicts_with`
- **查询端点** `GET /api/v1/memories/conflicts` — 列出所有带矛盾标记的记忆
- **Hermes 工具** `mnemosyne_conflicts(limit)` — 新会话可用

### ✨ P3-T3: LLM Wiki 知识库 ✅
- **表已存在** `wiki_pages` — 含 title/content/user_id
- **端点三件套**：
  - `GET /api/v1/wiki` — 列表
  - `GET /api/v1/wiki/{id}` — 全文
  - `POST /api/v1/wiki` — 创建
- **Hermes 工具** `mnemosyne_wiki(action=list|get, page_id, limit)`

### 📋 变更文件
| 文件 | 变更 |
|:----|:----:|
| GZ `main.py` | 🆕 矛盾metadata存储 + conflicts端点 + wiki三端点 |
| `mnemosyne_provider.py` | 🆕 CONFLICT_SCHEMA + WIKI_SCHEMA + `_tool_conflicts` + `_tool_wiki` |

Line routing map update:
```
GZ main.py: 34 routes (from 30)
    memories/search, dialectic, tiered, conflicts
    wiki (list/get/create)
Provider: 10 tools (search/remember/recall/tree/hot/dialectic/tiered/conflicts/wiki)
```

---

## 2026-06-04 — Phase 2 T1+T2+T3 完成！三级读取 + 会话切换 🚀

### ✨ P2-T1: 辨证推理层
- **GZ 端点** `POST /api/v1/dialectic` — 搜索 + L2 会话上下文综合 ✅（上期）
- **Hermes 工具** `mnemosyne_dialectic` — 返回结构化记忆树供 LLM 综合分析

### ✨ P2-T2: 三级读取 (Tiered Read) ✅
- **GZ 端点** `GET /api/v1/memories/{id}/tiered?level=L5|L3|L1`
  - **L5 摘要** (200字)：截取内容 + session_label，快速回忆
  - **L3 概览** (800字)：内容 + session_summary，理解上下文
  - **L1 全文**：完整内容 + session 全信息 + **同会话其他片段列表**（自动图谱遍历）
    - 还抓取 daily 摘要（如果有）
- **Hermes 工具** `mnemosyne_tiered_read(memory_id, level)`

### ✨ P2-T3: 会话切换 (Session Switch) ✅
- **Provider 回调** `on_session_switch` — Hermes 原生接口
- 切换时检查写队列状态 + 触发 `replay_pending` 确保不丢数据
- 配合 systemd `Restart=always` + 持久队列，断电重启不丢记忆

### 🔧 Provider 持续迭代
- `mnemosyne_provider.py` 已 650+ 行：search → dialectic → tiered → session_switch
- 所有工具新会话自动生效

### 🤖 自动工作区同步
- 🆕 `日常运维/auto-sync.sh` — 一键状态报告 + Git 提交
- 🆕 `日常运维/pre-commit-hook.sh` — 提交前自动更新
- ⏰ Cron 每日 23:00 自动同步
- 📦 Git 完整可追溯

---

## 2026-06-03 — Phase 1 根基加固完成 + GZ Search 全面修复 🚀

### GZ Search 全面修复（最大坑）
- **根因**：`search_memories` 在 uvicorn 内因 `rerank_lock` + 复杂 SQL 组合导致异步死锁
- **修复历程**：async httpx ❌ → sync run_in_executor ❌ → threading ❌ → subprocess ❌
- **最终方案**：简化 SQL（内联 BM25 无参数冲突）、rerank 加 try/except 降级、去掉 module-level lock
- **五维排序**：语义(0.40) + BM25(0.15) + 时间(0.15) + 信任分(0.15) + 热度(0.15)
- **效果**：秒级返回，包含 id/content/category/tier/heat_score/reliability/access_count

### Phase 1 全部完成 ✅
- **P1-T1 持久写队列** 🆕 — `write_queue.py` SQLite 队列 + 熔断器（5次失败暂停120s）
- **P1-T2 熔断器** 🆕 — 内置于 write_queue，自动 OPEN→HALF_OPEN→CLOSE
- **P1-T3 信任评分** 🔧 — GZ search 排序含 `reliability`；feedback 端点正/负反馈
- **P1-T4 消息清理** 🆕 — `message_cleaner.py` 剥离注入标签 + 过滤无意义消息

### Provider 重构
- `mnemosyne_provider.py` sync_turn 改为 **先写持久队列再发**（crash-safe）
- 新版已复制到 `plugins/memory/mnemosyne/`（下次开新会话自动加载）
- 新增模块：`write_queue.py`, `message_cleaner.py`

### 文档新增
- 🆕 `架构设计/升级路线图_v3.0.md` — Phase 1→2→3 完整规划
- 🆕 `架构设计/外部系统调研.md` — 7 大内存系统源码分析 (11k+ 行代码)

### TMT 蒸馏增益
| 层级 | 6/2 初始 | 6/3 上午 | 6/3 晚间 |
|------|:--------:|:--------:|:--------:|
| L1 碎片 | 24 | 61 | 60+ |
| L2 会话 | 3 | 11 | 12 |
| L3 每日 | 0 | 2 | 2 |

---

## 2026-06-03 (上午) — 搜索修复 + GPU 加速常驻

### 修复
- **搜索端点挂死** 🔴
  - 根因：原始 `search_memories` 的 BM25 关键词用 `$idx` 参数绑定 + `ILIKE $N` 混用，asyncpg 参数索引紊乱导致 SQL 查询挂起
  - 修复：BM25 关键词改为内嵌 SQL（escape 注入），向量参数单独传 `$idx`，消除参数索引歧义
  - 效果：`POST /api/v1/memories/search` 恢复正常，返回 20 条语义搜索结果

- **SSH 隧道缺 `-R 11435`** 🔴
  - 根因：`start-gz-tunnels.sh` 没设 `-p 2222`，@reboot 启动时连接失败；WSL 重启后 -R 11435 一直未建立
  - 修复：脚本加 `-p 2222`，去 `ExitOnForwardFailure` 避免单端口失败连锁反应
  - 效果：GZ 可调 WSL GPU LLM，TMT 蒸馏不再降级到 CPU fallback

- **TMT cron 脚本路径错误** 🟡
  - 根因：Hermes cron `script` 字段把 inline curl 当文件路径解析
  - 修复：改为 `~/.hermes/scripts/tmt-consolidate-*.sh` shell 包装脚本

- **TMT L3 DB 缺列** 🟡
  - 根因：`tmt_daily` 表缺 `updated_at` 列，`INSERT ... ON CONFLICT ... SET updated_at=NOW()` 报错
  - 修复：`ALTER TABLE tmt_daily ADD COLUMN updated_at`

- **TMT L3+ child_id_ints 变量未定义** 🟡
  - 根因：`consolidate_level` 函数对 L3+ 使用 `child_id_uuids`，但后续代码引用 `child_id_ints`
  - 修复：改为 `edge_ids = child_id_ints if level <= 2 else child_id_uuids`

- **LLM 无 GPU 加速** 🟡
  - 根因：systemd 用 `/usr/bin/llama-server`(apt CPU 版)，非 GPU 二进制
  - 修复：改用 `~/.local/bin/llama-server-gpu`，加 `LD_LIBRARY_PATH`，`libggml-cuda.so` 复制到系统 ggml backends 目录

### 新增
- `mnemo-qwen-4b.service` — Qwen3.5-4B GPU，`Restart=always`，`--reasoning off`
- `mnemo-embed.service` — Embedding，`Restart=always`
- `mnemo-rerank.service` — Reranker，`Restart=always`
- `watchdog.sh` — cron 每分钟检测三大服务兜底
- `start-qwen-4b.sh` — GPU LLM 启动脚本

### TMT 蒸馏增益
| 层级 | 6/2 初始 | 6/3 当前 |
|------|:-------:|:--------:|
| L1 碎片 | 24 | 61 |
| L2 会话 | 3 | 11 |
| L3 每日 | 0 | 2 |

---

## 2026-06-04 — Phase 2 启动：辨证推理层 v1 + 隧道修复 + Provider 优化 🚀

### 🔧 环境修复（P0）
- **autossh 缺 -R 反向隧道**：当前进程少 `-R 11434/11435/11436` → 重启隧道加回
- **Embed 隧道恢复**：GZ → WSL :11434 搜索埋点恢复 ✅
- **Provider search 参数修复**：`limit` → `top_k`（GZ API 不匹配导致搜索空返回）

### ✨ 新增：辨证推理层 (P2-T1)
- **GZ 新端点** `POST /api/v1/dialectic` — 搜索 + L2 会话上下文综合
- **数据结构化**：返回 6 条记忆 + 4 条 L2 会话摘要，语义+BM25+时间五维排序
- **Hermes 工具**：`mnemosyne_dialectic` — 新会话自动可用
- **不依赖 LLM 调用**：GZ 只管取数据，Hermes 侧 LLM 做综合推理

### 🛣️ 图谱遍历（建设中）
- `edges` 查询因 tmt_tree_edges 表 parent_id/child_id 混用 bigint + UUID 暂跳
- 后续统一类型后开启

### 🤖 自动工作区同步
- 🆕 `日常运维/auto-sync.sh` — 一键状态报告 + Git 提交
- 🆕 `日常运维/pre-commit-hook.sh` — 提交前自动更新路线图
- ⏰ Cron 每日 23:00 自动同步（防止遗忘）
- 📦 Git 仓库完整（9 commits），`git log` 可追溯每次变更

### 📋 变更文件
| 文件 | 状态 |
|:----|:----:|
| `start-gz-tunnels.sh` | 🔧 确认含 -R |
| `mnemosyne_provider.py` | 🔧 加 dialectic_search + DIALECTIC_SCHEMA |
| GZ `main.py` | 🆕 dialectic 端点 + DialecticRequest |
| `升级路线图_v3.0.md` | 🔧 P2 进度更新 |

---

- MemoryProvider `OpenViking` → 自研 `Mnemosyne`
- TMT 级记忆树部署（L1-L5）
- GZ 离线 Qwen3.5-2B fallback
- Hermes cron 蒸馏定时任务
