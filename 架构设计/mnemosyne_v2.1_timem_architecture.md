# Mnemosyne v2.1 — TiMem-Inspired 层级记忆架构设计

> 基于 TiMem (arXiv 2601.02845) Temporal Memory Tree (TMT)
> 设计用于 Noah 的 Mnemosyne v2.1（FastAPI + PGVector + Redis + Qwen3）

---

## 1. 5级记忆树 (TMT) 概览

```
L1: 碎片 (Fragment)   ← 单条记忆 / 对话轮次      [即时在线]
L2: 会话 (Session)    ← 整轮对话摘要              [会话结束时 / 每10分钟]
L3: 每日 (Daily)      ← 跨会话主题提炼            [每天 23:50]
L4: 每周 (Weekly)     ← 模式/趋势综合              [每周日 23:55]
L5: 画像 (Profile)    ← 人设/偏好固化              [每月最后一天 23:59]
```

### 核心公式：Φᵢ : (Cᵢ, Hᵢ, Iᵢ) → {m⁽ⁱ⁾}

- **Cᵢ** = 子节点记忆（来自低一级）
- **Hᵢ** = 同层历史（滑动窗口）
- **Iᵢ** = 层级特定的 LLM 指令
- **Φᵢ** = LLM 蒸馏（无需微调）

---

## 2. 数据库设计 (5张新表)

### 新增表

| 表名 | 层级 | 关键列 |
|------|------|--------|
| `tmt_sessions` | L2 | summary, embedding(VECTOR), heat_score, fragment_ids[] |
| `tmt_daily` | L3 | summary, embedding, themes(JSONB), session_ids[] |
| `tmt_weekly` | L4 | summary, embedding, patterns(JSONB), daily_ids[] |
| `tmt_profiles` | L5 | profile_json, summary, embedding, is_active, previous_id |
| `tmt_tree_edges` | 跨层 | (parent_level, parent_id, child_level, child_id) |

### 现有表增强

```sql
ALTER TABLE memories ADD COLUMN tmt_level SMALLINT DEFAULT 1;
ALTER TABLE memories ADD COLUMN session_id UUID;
ALTER TABLE memories ADD COLUMN turn_index INT;
```

---

## 3. 蒸馏管道核心算法

```python
async def consolidate_level(user_id, level, interval_start, interval_end):
    # 1. 收集子节点 Cᵢ(g)
    children = await get_child_memories(user_id, level, interval_start, interval_end)

    # 2. 同层历史 Hᵢ (滑动窗口)
    w_i = {2: 3, 3: 7, 4: 4, 5: 1}[level]
    history = await get_recent_same_level(user_id, level, limit=w_i)

    # 3. LLM 蒸馏
    prompt = build_consolidation_prompt(level, children, history)
    result = await qwen_client.generate(prompt, temperature=0.3)
    parsed = parse_output(level, result)

    # 4. 向量化 + 存储
    embedding = await embedder.embed(parsed["summary"])
    stored = await store_level_memory(level, user_id, interval, parsed, embedding)

    # 5. 热度传播
    await propagate_heat(level, stored["id"], children)
    await create_tree_edges(stored, children)
```

---

## 4. 热度体系

| 层级 | 初始值 | 每日衰减 | 含义 |
|------|--------|---------|------|
| L1 | 0.5 | ×0.98 (2%) | 关键事实 vs 琐事 |
| L2 | 0.5 | ×0.985 (1.5%) | 重要会话 vs 闲聊 |
| L3 | 0.5 | ×0.99 (1%) | 有意义的一天 vs 日常 |
| L4 | 0.5 | ×0.995 (0.5%) | 关键一周 vs 普通 |
| L5 | 1.0 | ×0.999 (0.1%) | 稳定人格 vs 初始 |

**热度传播公式**（子→父）：
```python
parent_heat = max(children) × 0.6 + mean(children) × 0.3 + agreement_bonus × 0.1
```

---

## 5. 智能召回 (3阶段)

### Stage 1: 查询复杂度分类
```
Simple (0) ← "X在哪工作？" → L5 + top L1
Hybrid (1) ← "X讨论了什么话题？" → L2~L5
Deep (2)  ← "X会喜欢这个吗？" → 全树搜索
```

### Stage 2: 层级传播
L1 语义搜索 → 沿着 `tmt_tree_edges` 向上传播 → 直接搜高层的向量

### Stage 3: LLM 门控过滤
对候选记忆做相关度过滤 + 时空一致性排序

---

## 6. API 端点 (新增12个)

```
# 蒸馏触发
POST /tmt/consolidate/session    {user_id, session_id?}
POST /tmt/consolidate/daily      {user_id, date?}
POST /tmt/consolidate/weekly     {user_id, week_start?}
POST /tmt/consolidate/monthly    {user_id, year?, month?}
POST /tmt/backfill               {user_id, from_date, to_date}
POST /tmt/decay                  {user_id}

# 智能召回
POST /tmt/recall                 {user_id, query, complexity_hint?}
GET  /tmt/recall/simple          ?user_id&q  (快速路径)

# 检查调试
GET  /tmt/tree/{user_id}
GET  /tmt/level/{level}/{id}
GET  /tmt/stats/{user_id}
```

---

## 7. Hermes 集成

### Cron 定时任务 (5个)
```yaml
- L2: 每10分钟 → /tmt/consolidate/session
- L3: 每天23:50 → /tmt/consolidate/daily
- L4: 每周日23:55 → /tmt/consolidate/weekly
- L5: 每月末23:59 → /tmt/consolidate/monthly
- 热度衰减: 每天03:00 → /tmt/decay
```

### MCP 工具 (5个)
```python
tmt_store(content, session_id?)        → 存储+触发蒸馏
tmt_recall(query, complexity_hint?)    → 智能召回
tmt_consolidate(level, date?)          → 手动触发蒸馏
tmt_get_active_profile()               → 获取用户画像
tmt_tree_explore(level, date_range?)   → 浏览记忆树
```

### OpenViking 注入 + TMT 召回融合
每次对话开始前，TMT 自动召回相关上下文 + OpenViking 同步注入

---

## 8. 分阶段实现路线

| 阶段 | 内容 | 预计 |
|------|------|------|
| **P1 基础** | 建5张表 + L2蒸馏端点 + Hermes cron | 3天 |
| **P2 全蒸馏** | 通用 consolidate_level() + L3~L5 + 树边管理 | 3天 |
| **P3 召回** | 复杂度分类 + 层级召回 + 门控过滤 | 2天 |
| **P4 热度** | 传播 + 衰减 + 强化 + 反馈集成 | 1天 |
| **P5 集成** | MCP工具 + OpenViking融合 + Redis缓存 | 2天 |
