# Mnemosyne OS v5.0 进度

## 状态: ✅ 全部缺口修复完成 (2026-06-25)
## 版本: v5.0.4 — Release Candidate

## 已完成 Phase
- [x] P1 地基 — GZ迁移 + 豆包API全替代
- [x] P2 灵魂 — 三馆闭环 + 工具归档 + 项目管理
- [x] P3 算力 — 模型路由Tier1-5 + 异构审计 + 哈希净化
- [x] P4 集成 — Hermes SDK + MCP + API规范
- [x] P5 打磨 — GitHub开源 + 安装指引 + 使用技能
- [x] Reranker — Qwen3-Embed 0.6B (GZ:11436, 3.7G)
- [x] 🔧 v5.0.1: AGE ag_label
- [x] 🔧 v5.0.2: TMT 蒸馏恢复
- [x] 🆕 v5.0.3: RAG Chunking
- [x] 🆕 v5.0.4: 端云增量同步

## 端云同步架构
```
WSL ──[GZ在线→直写]──→ GZ Mnemosyne
  │
  └──[GZ离线→SQLite]──→ 本地缓存 (sync/local_cache.db)
                            │
        cron每10min ← sync_push.py ←──┘ (GZ恢复后自动推送)
```

## 新增文件
- sync/local_cache.py — SQLite 本地缓存引擎
- sync/memory_gateway.py — 智能路由(store/status/push/check)
- sync/sync_push.py — 批量推送到 GZ

## Cron 总览
| 位置 | 任务 | 频率 |
|------|------|------|
| GZ | Reflector light (衰减+去重) | 每4h |
| GZ | Reflector deep (实体提取) | 每天4am |
| GZ | TMT session→daily | 每天1am |
| GZ | TMT daily→weekly | 周日1:30 |
| GZ | TMT weekly→profile | 1号2am |
| GZ | RAG auto-chunk | 每2h |
| WSL | 端云同步推送 | 每10min |

## 版本链
- v5.0.1 → v5.0.2 → v5.0.3 → v5.0.4
- GitHub: github.com/gymaira1990-jpg/Mnemosyne-OS
