# Mnemosyne OS v5.0 进度

## 状态: ✅ TMT 蒸馏已恢复 (2026-06-25)
## 上次修复: TMT 蒸馏恢复 (2026-06-25)
## 下次: RAG chunking / 端云增量同步

## 已完成 Phase
- [x] P1 地基 — GZ迁移 + 豆包API全替代
- [x] P2 灵魂 — 三馆闭环 + 工具归档 + 项目管理
- [x] P3 算力 — 模型路由Tier1-5 + 异构审计 + 哈希净化
- [x] P4 集成 — Hermes SDK + MCP + API规范
- [x] P5 打磨 — GitHub开源 + 安装指引 + 使用技能
- [x] Reranker — Qwen3-Embed 0.6B (GZ:11436, 3.7G)
- [x] 🔧 AGE ag_label — CREATE EXTENSION age + init_age_connection + mnemosyne_graph重建
- [x] 🔧 TMT 蒸馏恢复 — 全链路 L1→L5 回填 + cron 自动化

## TMT 蒸馏当前状态
```
L1  碎片         0 条 (全部已蒸馏到 L2)
L2  会话 (sessions)  146 条
L3  每日 (daily)       6 条
L4  每周 (weekly)      3 条
L5  画像 (profile)     1 条
```

## Cron 自动化
- Reflector (已有): 每4h 热度衰减+去重, 每天4am 实体提取
- TMT 蒸馏 (新增): 每天1am session→daily, 周日1:30 weekly, 1号2am monthly

## 修复的 Bug
1. public schema 残留旧表 → 改名 _old 避免冲突
2. asyncpg search_path 不生效 → server_settings + init 双保险
3. L4 weekly INSERT `$4::vector` 错位 → 改为 `$5::vector`

## 关键端点
- GZ: http://127.0.0.1:8010 (隧道:18010)
- Reranker: http://127.0.0.1:11436
- GitHub: github.com/gymaira1990-jpg/Mnemosyne-OS
- AGE: ag_catalog schema, mnemosyne_graph (3 labels)

## 版本
- v5.0.1: AGE ag_label 修复
- v5.0.2: TMT 蒸馏恢复 (cron + bugfix)
- API: {"version":"5.0.0"}
