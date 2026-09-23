# 架构速览

> 从 `AGENTS.md` 下沉。详细设计见 [WHITEPAPER.md](WHITEPAPER.md) 与 [palace-architecture.md](palace-architecture.md)。
> 返回 [AGENTS.md](../AGENTS.md)

## 架构速览

```
Mnemosyne OS (FastAPI, 50+ 端点)
  ├── main.py            服务入口 + 核心路由 (memories/search/palace/wiki/...)
  ├── palace.py          🏰 宫殿核心 (分类/档号/卡片/召唤/生命周期)
  ├── core/              LLM / Embedding / Chunker 引擎
  ├── api/               REST API 模块
  ├── tmt/               蒸馏引擎 (factextract/distill)
  ├── wiki/              WIKI 知识库模块 (BM25/图谱/提取/评测)
  ├── security/          审计与净化
  ├── integrations/      Hermes 集成 (Memory Provider + MCP)
  │   └── hermes-provider/  Memory Provider v7 (11 工具, palace_summon)
  ├── sync/              端云同步 (SQLite ↔ PostgreSQL)
  └── docs/              白皮书 + 宫殿设计 + schema

数据层: PostgreSQL 16 + pgvector 1024d (HNSW)(v7.8: Apache AGE 图已切除 — 实体关联走 entities/memory_entities/wiki_entities 表)
模型层: 可插拔 —— 豆包 ARK / DeepSeek / 任意 OpenAI 兼容端点
```

---
