# 🏰 记忆宫殿 · Mnemosyne 专属工作区

> Noah AI 基建 · 永久记忆系统
> 部署于 GZ 腾讯云 (your-server-ip) | WSL (RTX 5070) 提供 LLM/Embedding/Rerank

## 目录索引

| 目录 | 内容 |
|------|------|
| `架构设计/` | Mnemosyne v2.1 + TMT 层级记忆系统设计文档 |
| `TMT层级记忆系统/` | 5级时间记忆树 · 蒸馏管道 · 热度体系 |
| `MCP桥接/` | Hermes ↔ Mnemosyne MCP 工具文件 |
| `SSH隧道管理/` | autossh 6条隧道配置 · 自启 |
| `GZ服务器/` | 远程服务清单 · 健康状态 |
| `日常运维/` | 一键验证脚本 · 故障排查手册 |
| `Noah生态/` | noah-factory · noah-archive 关联项目 |

## 核心架构速览

```
┌─────────────────────────────────────────────────────┐
│                    Hermes Agent                        │
│  ┌─────────────────────────────────────────────────┐  │
│  │  MCP 桥接 (mnemosyne_mcp + tmt_mcp)              │  │
│  └──────────┬──────────────────────┬───────────────┘  │
│             │ :18010                │ :3333            │
│         ┌───▼─────────┐      ┌──────▼──────┐        │
│         │ Mnemosyne    │      │ Prompt      │        │
│         │ FastAPI      │      │ Optimizer   │        │
│         │ :8010        │      │ :3333       │        │
│         └───┬─────────┘      └─────────────┘        │
│             │                                         │
│    ┌────────▼────────────────────┐                   │
│    │   PostgreSQL (21表)          │                   │
│    │   - memories (L1)           │                   │
│    │   - tmt_sessions (L2)       │                   │
│    │   - tmt_daily (L3)          │                   │
│    │   - tmt_weekly (L4)         │                   │
│    │   - tmt_profiles (L5)       │                   │
│    │   - tmt_tree_edges (跨层)    │                   │
│    └────────────────────────────┘                   │
│                                                    │
│   GZ Server                    WSL (←SSH-R隧道→)    │
│   ──────────                   ─────────────────    │
│   · Mnemosyne :8010            · LLM :11435 (GPU)   │
│   · Optimizer :3333            · Embed :11434 (CPU) │
│   · Redis :6379                · Rerank :11436 (CPU)│
│   · SOCKS5 :1080 → HK         · SOCKS5 :1081        │
└─────────────────────────────────────────────────────┘
```

## TMT 5级记忆树

```
L1 碎片 (memories)    ← 单条对话记忆        [在线即时]
L2 会话 (tmt_sessions) ← 整轮对话摘要       [cron: */10 * * * *]
L3 每日 (tmt_daily)    ← 跨会话主题提炼     [cron: 50 23 * * *]
L4 每周 (tmt_weekly)   ← 模式/趋势综合      [cron: 55 23 * * 0]
L5 画像 (tmt_profiles) ← 人设/偏好固化      [cron: 59 23 28-31 * *]
```

## 状态

- ✅ SSH 隧道 (autossh) — 运行中
- ✅ Mnemosyne v2.1.0 — 运行中
- ✅ Local LLM (Qwen3.5-4B) :11435 — 运行中
- ✅ Local Embed (Qwen3-0.6B) :11434 — 运行中
- ✅ Local Rerank :11436 — 运行中
- ✅ Prompt Optimizer :3333 — 运行中
- ✅ MCP Server (mnemosyne_mcp + tmt_mcp) — 已注册
- ✅ Hermes Cron (L2每10分 + L3每天23:50) — 已配置
