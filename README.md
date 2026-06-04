# 🏰 记忆宫殿 · Mnemosyne 专属工作区

> Noah AI 基建 · 永久记忆系统
> 最新更新: 2026-06-03 (搜索修复 + GPU 常驻)
> 部署于 GZ 腾讯云 (your-server-ip:2222) | WSL (RTX 5070) 提供 LLM/Embedding/Rerank

## 目录索引

| 目录 | 内容 |
|------|------|
| `架构设计/` | Mnemosyne v2.1 + TMT 层级记忆系统设计文档 |
| `TMT层级记忆系统/` | 5级时间记忆树 · 蒸馏管道 · 热度体系 |
| `MCP桥接/` | Hermes ↔ Mnemosyne MCP 工具文件 |
| `SSH隧道管理/` | autossh 8条隧道配置 · 自启 (含-R 11435) |
| `GZ服务器/` | 远程服务清单 · 健康状态 |
| `日常运维/` | 一键验证脚本 · 故障排查手册 |
| `Noah生态/` | noah-factory · noah-archive 关联项目 |

## 核心架构速览

```
┌─────────────────────────────────────────────────────┐
│                  WSL (g-cat@G-Cat-PC-01)              │
│  ┌─────────────────────────────────────────────────┐  │
│  │  systemd 三剑客 (Restart=always)                 │  │
│  │  ├─ mnemo-qwen-4b  → Qwen3.5-4B GPU @ :11435    │  │
│  │  ├─ mnemo-embed    → Qwen3-0.6B CPU @ :11434    │  │
│  │  └─ mnemo-rerank   → Qwen3-0.6B CPU @ :11436    │  │
│  │  ┌─ cron watchdog  → 每分钟检测三大服务兜底      │  │
│  │  └─ autossh        → 8条隧道自动复活              │  │
│  └──────────┬──────────────────────┬───────────────┘  │
│             │ :18010 (隧道)         │ :3333 (MCP)       │
│         ┌───▼─────────┐      ┌──────▼──────┐        │
│         │ Mnemosyne    │      │ Prompt      │        │
│         │ FastAPI v2.1 │      │ Optimizer   │        │
│         │ :8010 (GZ)   │      │ GZ :3333    │        │
│         └───┬─────────┘      └─────────────┘        │
│             │                                         │
│    ┌────────▼────────────────────┐                   │
│    │   PostgreSQL (21表)          │                   │
│    │   - memories (L1) 61条      │                   │
│    │   - tmt_sessions (L2) 11条   │                   │
│    │   - tmt_daily (L3) 2条      │                   │
│    │   - tmt_weekly (L4) 0条     │                   │
│    │   - tmt_profiles (L5) 0条   │                   │
│    │   - tmt_tree_edges (跨层)    │                   │
│    └────────────────────────────┘                   │
│                                                    │
│   GZ Server (your-server-ip:2222)    WSL (RTX 5070)  │
│   ────────────────────────────    ────────────────  │
│   · Mnemosyne :8010                · LLM GPU :11435 │
│   · Optimizer :3333(MCP)          · Embed :11434    │
│   · PostgreSQL :5432              · Rerank :11436   │
│   · SOCKS5 :1080 → HK            · SOCKS5 :1081    │
│   · Qwen3.5-2B fallback :11437   · autossh持活     │
└─────────────────────────────────────────────────────┘
```

## TMT 5级记忆树

```
L1 碎片 (memories)    ← 单条对话记忆         [自动存储, 61条]
L2 会话 (tmt_sessions) ← 整轮对话摘要        [cron: */10 * * * *, 11条]
L3 每日 (tmt_daily)    ← 跨会话主题提炼      [cron: 50 23 * * *, 2条]
L4 每周 (tmt_weekly)   ← 模式/趋势综合       [cron: 55 23 * * 0, 0条]
L5 画像 (tmt_profiles) ← 人设/偏好固化       [cron: 59 23 28-31 * *, 0条]
```

## 系统常驻

| 组件 | 方式 | 自动复活 |
|------|------|---------|
| Qwen3.5-4B :11435 | systemd `mnemo-qwen-4b` + GPU 二进制 | Restart=always (5s) |
| Embedding :11434 | systemd `mnemo-embed` | Restart=always (5s) |
| Rerank :11436 | systemd `mnemo-rerank` | Restart=always (5s) |
| SSH 隧道 | autossh `start-gz-tunnels.sh`(cron @reboot) | 内置自动重连 |
| 安全网 | cron watchdog (每分钟) | 检测失败直接拉起 |

## 状态

- ✅ SSH 隧道 (autossh) — 8条全通，含 -R 11435 (GZ→WSL LLM)
- ✅ Mnemosyne v2.1.0 — 运行中，搜索功能正常
- ✅ LLM (Qwen3.5-4B GPU) :11435 — 运行中 (`--reasoning off`)
- ✅ Embed (Qwen3-0.6B) :11434 — 运行中 (dim=1024)
- ✅ Rerank :11436 — 运行中
- ✅ Prompt Optimizer MCP :3333 — 已注册
- ✅ Hermes Cron (L2每10分 + L3每天23:50) — 已配置
- ✅ Mnemosyne 搜索 — 已修复（原 BM25 参数索引错误）
- ✅ Hermes `memory` 工具 → 自动同步 Mnemosyne
- ✅ GZ 保底 LLM (Qwen3.5-2B fallback :11437) — 就绪
