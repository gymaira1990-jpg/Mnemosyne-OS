# Mnemosyne OS v5.0 进度

## 状态: ✅ AGE ag_label 修复完成 (2026-06-25)
## 上次修复: AGE ag_label (2026-06-25)
## 下次: Obsidian 人用仪表盘 / RAG chunking / 端云同步

## 已完成 Phase
- [x] P1 地基 — GZ迁移 + 豆包API全替代
- [x] P2 灵魂 — 三馆闭环 + 工具归档 + 项目管理
- [x] P3 算力 — 模型路由Tier1-5 + 异构审计 + 哈希净化
- [x] P4 集成 — Hermes SDK + MCP + API规范
- [x] P5 打磨 — GitHub开源 + 安装指引 + 使用技能
- [x] Reranker — Qwen3-Embed 0.6B (GZ:11436, 3.7G)
- [x] 🔧 AGE ag_label — CREATE EXTENSION age + init_age_connection + mnemosyne_graph重建

## 关键端点
- GZ: http://127.0.0.1:8010 (隧道:18010)
- Reranker: http://127.0.0.1:11436
- GitHub: github.com/gymaira1990-jpg/Mnemosyne-OS
- AGE: ag_catalog schema, mnemosyne_graph (3 labels: _ag_label_vertex, _ag_label_edge, Entity)

## 版本
- git tag: v5.0-p1, v5.0-p2, v5.0-p3, v5.0-p4, v5.0-final
- v5.0.1: AGE ag_label 修复
- API: {"version":"5.0.0"}
- 白皮书: 产品白皮书_v5.0.md (1288行)

## AGE 修复记录 (2026-06-25)
- 问题: pg_dump 不包含 ag_label 扩展表，AGE extension 未在数据库中激活
- 解决:
  1. CREATE EXTENSION age → ag_label/ag_graph 就位
  2. DROP SCHEMA mnemosyne_graph → create_graph('mnemosyne_graph') 重建
  3. main.py 添加 init_age_connection 回调 → asyncpg pool 每连接自动 LOAD 'age' + SET search_path
  4. 验证: Cypher CREATE/MATCH/MERGE/DELETE 全部正常，Entity 标签已存在

## 使用
- AI: skill_view("mnemosyne-os-usage")
- 人: README + 白皮书第13章
- 代码: from integrations.sdk import MnemosyneHermesMemory
