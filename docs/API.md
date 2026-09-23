# API 端点速查

> 从 `AGENTS.md` 下沉。**完整且最新的端点清单以服务自描述为准**：`GET /api/v1/capabilities`。
> 返回 [AGENTS.md](../AGENTS.md)

## API 端点速查

### 核心（记忆）

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/v1/echo` | GET | 健康检查 + 版本 |
| `/api/v1/memories` | GET | 列出记忆（`?sort=created_at` 时间轴 / `?sort=heat` 热度轴） |
| `/api/v1/memories` | POST | 存入记忆（自动向量化+实体提取+矛盾检测） |
| `/api/v1/memories/{id}` | GET | 单条详情 |
| `/api/v1/memories/{id}` | PUT | 更新 |
| `/api/v1/memories/{id}` | DELETE | 软删除 |
| `/api/v1/memories/{id}/restore` | POST | 恢复已删 |
| `/api/v1/memories/search` | POST | 五维修搜索（向量+BM25+时间+信任+热度） |
| `/api/v1/memories/{id}/feedback` | POST | 反馈（positive/negative，影响可信度） |
| `/api/v1/memories/heat-top` | GET | 热度排行 |
| `/api/v1/memories/stats` | GET | 记忆库统计 |
| `/api/v1/memories/tree` | GET | 记忆层级树 |
| `/api/v1/memories/{id}/traces` | GET | 生命周期轨迹 |
| `/api/v1/memories/{id}/tiered` | GET | 三级读取（L5/L3/L1） |

### 宫殿（v7 核心）

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/v1/palace/status` | GET | 宫殿状态（归档率/卡片数/分类树） |
| `/api/v1/palace/summon` | GET | 三通道召唤（点名/引导/共鸣） |
| `/api/v1/palace/archive` | POST | 分类归档（自动生成档号+著录卡片） |
| `/api/v1/palace/extract` | POST | 事实提取（对话→facts） |
| `/api/v1/palace/refine` | POST | 卡片精炼（LLM） |
| `/api/v1/palace/lifecycle` | POST | 生命周期流转 |
| `/api/v1/palace/pin` | POST | 置顶（防衰减） |

### 图谱 / Wiki / 信念

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/v1/graph/search` | POST | 实体关联记忆检索(entities 向量→memory_entities 关联) |
| `/api/v1/wiki` | GET/POST | 知识库页面读写 |
| `/api/v1/wiki/search` | POST | 语义搜索（向量+BM25 RRF 融合） |
| `/api/v1/wiki/by-source` | GET | 按来源路径/URL 精确查证 |
| `/api/v1/beliefs` | POST | 创建信念（自动合并置信度） |
| `/api/v1/beliefs/search` | POST | 语义搜索信念 |
| `/api/v1/beliefs/{id}/evolve` | POST | 演化信念（加证据/调整置信度） |

### 会话 / 蒸馏 / 运维

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/v1/sessions/archive` | POST | 会话归档（v7.8: 消息列表/同步端点已切除, 原文走 Hermes state.db） |
| `/api/v1/reflect` | POST | TMT 反思（`?mode=light` 热度衰减 / `?mode=deep` LLM 凝练） |
| `/api/v1/extract-entities` | POST | 批量实体提取到图谱 |
| `/api/v1/health/{user_id}` | GET | 用户健康报告 |
| `/api/v1/capabilities` | GET | 完整能力清单（自描述） |
| `/api/v1/dialectic` | POST | 辨证检索（带上下文） |

> 📋 完整端点列表与参数：`GET /api/v1/capabilities`（服务自描述，始终最新）。

---
