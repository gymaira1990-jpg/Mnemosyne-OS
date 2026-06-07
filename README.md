# 🏰 记忆宫殿 · Mnemosyne 专属工作区

> Noah AI 基建 · 私人专业记忆系统
> 最新更新: 2026-06-07 (TMT 管道修复 + 搜索权重修正 + 反向隧道补全)
> 部署于 GZ 腾讯云 (your-server-ip:2222) | WSL (RTX 5070) 提供 LLM/Embedding/Rerank

## 目录索引

| 目录 | 内容 |
|------|------|
| `架构设计/` | Mnemosyne 架构文档 · 升级路线图 · v4.0 调研方案 |
| `TMT层级记忆系统/` | 5级时间记忆树 · 蒸馏管道 · 热度体系 |
| `MCP桥接/` | Hermes ↔ Mnemosyne MCP 工具文件 |
| `SSH隧道管理/` | autossh 隧道配置 |
| `GZ服务器/` | 远程服务清单 · 健康状态 |
| `日常运维/` | 一键验证脚本 · 故障排查手册 |
| `Noah生态/` | noah-factory · noah-archive 关联项目 |

## 核心架构

```
                    ┌── Hermes Agent ──┐
                    │  CLI / Web UI    │
                    └────────┬─────────┘
                             │ MCP 协议
                    ┌────────▼─────────┐
                    │  Provider 层      │
                    │  11 个记忆工具    │
                    │  write_queue     │
                    │  message_cleaner │
                    └────────┬─────────┘
                             │ SSH 隧道 (autossh)
              ┌──────────────┼──────────────┐
              │              │              │
    ┌─────────▼──────┐  ┌───▼─────┐  ┌────▼────────┐
    │ GZ 腾讯云       │  │ WSL GPU │  │ WSL CPU     │
    │ Mnemosyne :8010 │  │LLM:11435│  │Embed:11434  │
    │ PostgreSQL 16   │  │         │  │Rerank:11436 │
    │ PGVector(1024d) │  │         │  │             │
    │ AGE 知识图谱    │  │         │  │             │
    │ Qwen3.5-2B CPU  │  │         │  │             │
    │   fallback:11437│  │         │  │             │
    └─────────────────┘  └─────────┘  └─────────────┘
```

## 当前数据

| 层级 | 表 | 条数 | 状态 |
|:----|:---|:----:|:-----|
| L1 碎片 | `memories` | **338** | ✅ 自动存储 + 热度衰减 |
| L2 会话 | `tmt_sessions` | **16** (15 default + 1 g-cat) | ✅ 蒸馏管道已修复, 每10min cron |
| L3 每日 | `tmt_daily` | **2** | ✅ 蒸馏管道已修复, 每日23:50 cron |
| L4 每周 | `tmt_weekly` | 0 | ⚪ 等数据积累 (需4周) |
| L5 画像 | `tmt_profiles` | 0 | ⚪ 等数据积累 (需1月) |

| 其他 | 条数 |
|:-----|:----:|
| 实体 (entities) | 295 |
| 实体关联 (memory_entities) | 238 |
| 信念 (beliefs) | 2 |
| Wiki 知识库 (wiki_pages) | 4 |
| 媒体记忆 (media_memories) | 4 |
| 层级边 (tmt_tree_edges) | 80 |

## 热度体系 (时序机制核心)

Memories 有 `heat_score [0,1]` 和 `tier (L1/L2/L3/L4)`，由 `POST /api/v1/reflect` 自动管理：

| 阈值 | 层级 | 行为 |
|:-----|:----|:-----|
| heat > 0.7 | L1 (热) | 高频访问记忆 |
| 0.2 ≤ heat ≤ 0.7 | L2 (温) | 常规记忆 |
| heat < 0.2 + 30天无访问 | L3 (冷) | 降级存储 |
| heat < 0.05 + 90天无访问 | L4 (遗忘) | 软删除 |

衰减规则：7天/30天/90天梯度衰减 + 高频加权 + 矛盾加速。

当前分布：🔥热36 / 👍温44 / ❄️冷56 / 💀遗忘177

## 系统常驻

| 组件 | 方式 | 自动复活 |
|------|------|---------|
| Qwen3.5-4B :11435 | systemd `mnemo-qwen-4b` + GPU (reasoning on) | Restart=always (8s) |
| Embedding :11434 | systemd `mnemo-embed` | Restart=always (8s) |
| Rerank :11436 | systemd `mnemo-rerank` | Restart=always (8s) |
| GZ Mnemosyne :8010 | systemd (GZ) | Restart=always (5s) |
| SSH 隧道 | systemd user service `autossh-gz-tunnel` | Restart=always (10s) |

## 隧道

WSL → GZ: `autossh -R 11434 -R 11435 -R 11436 -L 1081 -L 3333 -L 18010`

- `-R 11434` → GZ 通过 localhost:11434 用 WSL Embedding
- `-R 11435` → GZ 通过 localhost:11435 用 WSL LLM（GPU加速，6/7新增）
- `-R 11436` → GZ 通过 localhost:11436 用 WSL Reranker
- `-L 1081` → SOCKS5 代理
- `-L 3333` → Prompt Optimizer MCP
- `-L 18010` → Mnemosyne API

## 状态

- ✅ SSH 隧道 — 6条全通，含新增的 -R 11435
- ✅ Mnemosyne v2.1 — 43条REST API路由运行中
- ✅ TMT 蒸馏管道 — 已接通（6/7修复：tmt.py接入main.py）
- ✅ LLM (Qwen3.5-4B GPU) :11435 — 运行中 (reasoning on)
- ✅ Embed (Qwen3-0.6B) :11434 — 运行中 (dim=1024)
- ✅ Rerank :11436 — 运行中
- ✅ Prompt Optimizer MCP :3333 — 已注册
- ✅ Hermes Cron — L2每10分 + L3每天23:50
- ✅ Mnemosyne 搜索 — 已修复（6/7权重修正：reliability/heat 从2%→15%）
- ✅ GZ 保底 LLM (Qwen3.5-2B CPU :11437) — 就绪（但慢，仅离线兜底）
- ⚪ L4/L5 蒸馏 — 等数据积累
