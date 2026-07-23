# Mnemosyne OS v5.4 优化落地方案 (修正版)

> **基于**: miaoda-code 报告 + 实际生产数据 (三馆几乎未激活)
> **核心原则**: 不盲从报告建议。只做对「我们」有实际价值的事。
> **数据基线**: 2088 研究馆 / 3 工程馆 / 2 档案馆 / 3 tool_archives / 2 gates

---

## 被砍掉的建议及理由

| 建议 | 理由 |
|:---|:---|
| Redis 缓存 | 1用户/200ms/零投诉。加Redis=多一个故障点 |
| arq 任务队列 | cron 零维护，对单人运维最优 |
| API Key 认证 | SSH隧道+Nginx已封死，无人可触API端口 |
| 插件接口 | 只有PG一个后端，永不换，纯过度设计 |
| Prometheus | 单人用户，挂了立刻知道，/health足矣 |
| main.py 拆分 | 1362行，solo dev 单文件反更好调，痛了再拆 |
| 全量单元测试 | 端点测试ROI极低，只测核心算法 |

---

## 线 1: 三馆激活 (核心价值)

### 1.1 闸机接入异构审计

**文件**: `api/halls.py` promote_memory()

**改动**: promote 时调用 `security/audit.py` 的 audit_memory()，替代当前的直通模式。

```python
# 当前 (直通):
await conn.execute("INSERT INTO gates (..., passed, ...) VALUES (..., true, ...)")

# 改为:
from security.audit import audit_memory
audit_result = await audit_memory(conn, memory_id, user_id)
passed = audit_result.get("verdict") == "consistent_pass"

# gates 记录实际评审结果
await conn.execute(
    "INSERT INTO gates (memory_id, gate_type, passed, checks, auditor_model) "
    "VALUES ($1, $2, $3, $4, 'doubao-lite+doubao-code')",
    memory_id, gate_type, passed, json.dumps(audit_result)
)
```

**降级兼容**: 如果 audit 调用失败（网络/API 超时），降级为当前直通行为 + 记录 warning。

### 1.2 建议清单端点

**新建**: `GET /api/v1/halls/suggestions?user_id=default`

只读报告，不自动执行。返回三类建议：

```json
{
  "promote_candidates": [
    {"id": 123, "reason": "reliability=0.9, 停留15天, 建议研究→工程"}
  ],
  "demote_candidates": [
    {"id": 456, "reason": "工程馆停留62天, heat=0.05, 建议退回研究"}
  ],
  "forget_candidates": [
    {"id": 789, "reason": "研究馆停留35天, heat=0.02, 建议遗忘"}
  ]
}
```

Agent 定期读取此端点，自主决定是否执行 promote/demote/delete。**人不审批，AI 审批。**

### 1.3 工具归档修复

**文件**: `api/tools.py`

改动一行：成功→工程馆（不再直接进档案馆）。archive 只接受 promote。

```python
# 旧: hall = "archive" if req.success else "engineering"
# 新: hall = "engineering"  # 统一先入工程馆，archive 只通过 promote 进入
```

---

## 线 2: 核心算法加固

### 2.1 测试框架

**依赖**: `pip install pytest pytest-asyncio`

**结构**:
```
tests/
├── conftest.py                  ← async mock pool + 测试数据 fixtures
├── test_detect_conflict.py      ← 6个用例
├── test_heat_propagation.py     ← 4个用例
└── test_hall_flow.py            ← 6个用例
```

### 2.2 test_detect_conflict.py (6个用例)

| 用例 | 输入 | 预期 |
|:---|:---|:---|
| 完全重复 | 相同内容 + 向量距离<0.12 | action=merge |
| 矛盾知识 | 相似语义 + 文本差异>0.5 + 距离<0.12 | action=conflict |
| 不相关 | 向量距离>0.15 | action=fresh |
| 中间地带 | 距离<0.15 但文本相似度 0.5~0.85 | action=fresh (算补充) |
| 边界:距离恰好0.15 | 距离=0.15 | >0.15 → fresh |
| 边界:文本相似度恰好0.85 | 相似度=0.85, 距离<0.12 | >0.85 → merge |

### 2.3 test_heat_propagation.py (4个用例)

| 用例 | 输入 | 预期 |
|:---|:---|:---|
| 三个子节点热度均匀 | [0.8, 0.8, 0.8] | parent=0.8×0.6+0.8×0.3+0=0.72 |
| 子节点热度差异大 | [0.9, 0.1, 0.1] | parent=0.9×0.6+0.37×0.3+0=0.65 |
| 全同热度 | [0.5, 0.5, 0.5] | parent=0.5×0.6+0.5×0.3+0=0.45 |
| agreement bonus | 子节点全部agreement | parent+=0.1 |

### 2.4 test_hall_flow.py (6个用例)

| 用例 | 操作 | 预期 |
|:---|:---|:---|
| 正常:研究→工程 | promote(research, engineering) | ✅ hall=engineering + gate记录 |
| 正常:工程→归档 | promote(engineering, archive) | ✅ hall=archive + gate记录 |
| 退回:工程→研究 | demote(engineering) | ✅ hall=research |
| 拒绝:归档→任何 | promote(archive, *) | ❌ 400 |
| 拒绝:研究→归档 | promote(research, archive) | ❌ 400 (必须经过工程) |
| 拒绝:非工程退回 | demote(research) 或 demote(archive) | ❌ 400 |

---

## 线 3: 顺手小修

### 3.1 AGE Cypher 参数安全

**文件**: `main.py` sync_entities_to_age()

实体名和 entity_id 增加:
- `replace("'", "\\'")` 转义
- entity_id 限制 [a-zA-Z0-9_-]+
- name 截断 200 字符

### 3.2 版本文件更新

- `VERSION`: 5.3.2 → 5.4.0
- `CHANGELOG.md`: 新增 v5.4.0 条目
- `PROGRESS.md`: 更新状态
- `ROADMAP.md`: v5.3.x ✅, v5.4 标记当前

---

## 执行顺序

```
Day 1: 线1 — 闸机接审计 + 建议端点 + 工具修复
Day 2: 线2 — 测试框架 + 16个测试用例
Day 3: 线3 — AGE修复 + 版本更新 + 安全扫描 + GZ部署
```

---

## 验证清单

```
[ ] promote 时 gates 表有 passed=false 记录 (双模型分歧时)
[ ] GET /api/v1/halls/suggestions 返回合理建议
[ ] pytest tests/ -v → 16 passed
[ ] 测试覆盖率: 核心算法 >90%
[ ] AGE 查询对含单引号的实体名不报错
[ ] GZ echo v5.4.0
[ ] Phase 2 安全扫描零输出
```

---

## 被拒绝的「好建议」

这些建议对「多用户 SaaS 产品」是正确的，但对「单人基础设施」是过度设计：

- Redis: 加一个服务=多一个故障点。当前无性能问题，不加。
- arq: cron 简单可靠，零维护。不加。
- API Key: SSH 隧道已封死外部访问。不加。
- Prometheus: 挂了立刻知道，不需要仪表盘报警。
- 插件接口: 只有一个后端。真需要时再抽象。
- main.py 拆分: 不痛不拆。单文件对 solo dev 反更好维护。
