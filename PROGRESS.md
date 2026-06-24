# Mnemosyne OS v5.0 进度

## 状态: ✅ RAG Chunking 完成 (2026-06-25)
## 上次修复: RAG Chunking 管道 (2026-06-25)
## 下次: 端云增量同步

## 已完成 Phase
- [x] P1 地基 — GZ迁移 + 豆包API全替代
- [x] P2 灵魂 — 三馆闭环 + 工具归档 + 项目管理
- [x] P3 算力 — 模型路由Tier1-5 + 异构审计 + 哈希净化
- [x] P4 集成 — Hermes SDK + MCP + API规范
- [x] P5 打磨 — GitHub开源 + 安装指引 + 使用技能
- [x] Reranker — Qwen3-Embed 0.6B (GZ:11436, 3.7G)
- [x] 🔧 AGE ag_label — v5.0.1
- [x] 🔧 TMT 蒸馏恢复 — v5.0.2
- [x] 🆕 RAG Chunking — v5.0.3

## RAG Chunking 状态
```
覆盖记忆: 330/1166 条 (358条中长)
总 chunks: 765 块
算法: 段落→句子分割 + 50字重叠窗口
搜索降级: chunk级优先 → 记忆级兜底
```

## 新增端点
- POST /api/v1/memories/{id}/chunk     — 单条chunk
- POST /api/v1/memories/chunk-all       — 批量处理
- GET  /api/v1/memories/chunks/stats    — 覆盖率
- POST /api/v1/memories/search-chunks   — chunk级搜索

## Cron 总览
| 任务 | 频率 | 功能 |
|------|------|------|
| Reflector light | 每4h | 热度衰减+去重 |
| Reflector deep | 每天4am | 实体提取 |
| TMT daily | 每天1am | session→daily 蒸馏 |
| TMT weekly | 周日1:30 | daily→weekly |
| TMT monthly | 1号2am | weekly→profile |
| RAG chunk | 每2h | 新记忆自动chunk |

## 版本
- v5.0.1: AGE ag_label 修复
- v5.0.2: TMT 蒸馏恢复
- v5.0.3: RAG Chunking 管道
