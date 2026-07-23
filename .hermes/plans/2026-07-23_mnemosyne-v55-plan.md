# Mnemosyne OS v5.5 技术基础迭代方案

> 不做市场、不搞对标。只做三个有实际价值的技术改进。

---

## 1. 时间有效性窗口 (Temporal Validity)

### 现状

数据已有：67 条记忆 marked as expired (valid_to < NOW)，但搜索照样返回它们。

```sql
-- 当前查询: 不过滤过期记忆
FROM memories WHERE user_id=$1 AND is_deleted=FALSE

-- 应该: 加上时间过滤器
FROM memories WHERE user_id=$1 AND is_deleted=FALSE AND (valid_to IS NULL OR valid_to > NOW())
```

### 改动点

**A. 搜索层 (3处 SQL)**

| 位置 | 文件 | 改动 |
|:---|:---|:---|
| `search_memories` hybrid | main.py:653 | WHERE 加 `AND (m.valid_to IS NULL OR m.valid_to > NOW())` |
| `search_memories` time-ordered | main.py:603 | WHERE 加 `AND (valid_to IS NULL OR valid_to > NOW())` |
| `list_memories` | main.py:~700 | WHERE 加有效时间过滤 |

**B. 权重惩罚 (hybrid search)**

在五维评分中增加 temporal_validity 维度，替换当前的纯时间衰减：
```
当前: temporal = 7天内0.15 / 30天内0.08 / 其他0
改为: temporal = 7天内0.15 / 30天内0.08 / 其他0
      + validity_boost = valid_to IS NULL ? 0 : -0.05  (过期记忆轻惩罚)
```

**C. list_memories 返回字段**

在列表 API 中增加 `valid_to` 和 `expired` 标记，让调用方能区分。

### 验证
- curl 搜索时，67条过期记忆不再出现在结果中
- 测试用例: 创建一条 valid_to=past 的记忆，搜索不返回它

---

## 2. 记忆质量基准测试 (Memory Benchmark)

### 目标

不跟竞品比，跟自己比。建立一套可重复的记忆质量测量标准。

### 测试场景 (3个)

**场景 1: 长期记忆保持率**
- 插入 50 条知识 → 模拟 30 天 → 查询 10 个问题
- 测量: 正确答案是否在 Top 5 结果中

**场景 2: 矛盾检测准确率**
- 插入 20 对矛盾知识 → 触发 detect_conflict
- 测量: merge/conflict/fresh 分类准确率

**场景 3: 热度 + 可信度加权效果**
- 插入 30 条混合质量记忆 → 调整部分 heat/reliability
- 测量: 高质量记忆是否排位更靠前

### 实现

新建 `tests/benchmark/`:
```
tests/benchmark/
├── conftest.py      ← 共享 fixture (填充mock数据)
├── test_recall.py   ← 场景1: 召回精度
├── test_conflict.py ← 场景2: 矛盾检测
└── test_weighting.py ← 场景3: 热度/可信度加权
```

不 mock LLM/embedding 调用 — 用确定性替代数据（预设 embedding 向量距离）。

### 运行
```bash
python -m pytest tests/benchmark/ -v
```

---

## 3. 简易记忆浏览器 (Memory Browser)

### 目标

一个单 HTML 页面，无需后端改动，通过现有 API 浏览记忆。

### 功能

```
┌─ Mnemosyne Browser ───────────────────┐
│ [研究馆 2088] [工程馆 3] [档案馆 2]   │  ← 馆过滤
│                                        │
│ 搜索: [____________] [搜索]            │  ← 关键词搜索
│ 排序: ○ 时间 ○ 热度 ● 可信度           │
│                                        │
│ ┌── 记忆列表 ──────────────────────┐  │
│ │ id:2142  [研究馆] reliability=0.5│  │
│ │ 内容预览...                      │  │
│ │ 创建: 2026-07-16 heat=0.0       │  │
│ ├──────────────────────────────────┤  │
│ │ id:2143  [档案馆] reliability=0.9│  │
│ │ ...                              │  │
│ └──────────────────────────────────┘  │
└────────────────────────────────────────┘
```

### 技术方案

- 纯静态 HTML + vanilla JS（无框架依赖）
- 通过 Hermes Web UI 或本地文件打开
- API 调用: `/api/v1/memories` + `/api/v1/halls/{hall}` + `/api/v1/memories/search`
- 不新增后端端点

### 部署

放在 `docs/browser.html`，可直接用浏览器打开或托管在 my.g-cat.cn 子路径下。

---

## 版本: v5.5.0

```
v5.4.0 (当前) → v5.5.0 (本方案)
  改动量: 约 200 行 Python + 200 行测试 + 300 行 HTML
  工期: 2-3 天
  风险: 极低（不改 API 签名，只改 SQL WHERE 条件）
```

---

## 执行清单

```
[ ] 1A: 修复 3 处搜索 SQL，加 valid_to 过滤
[ ] 1B: 五维搜索增加 validity_boost 维度
[ ] 1C: list_memories 返回 expired 标记
[ ] 1D: 新增 test_temporal_validity.py
[ ] 2A: tests/benchmark/ 目录 + fixture
[ ] 2B: test_recall.py (场景1)
[ ] 2C: test_conflict.py (场景2)
[ ] 2D: test_weighting.py (场景3)
[ ] 3A: docs/browser.html
[ ] 3B: 部署到 GZ my.g-cat.cn
[ ] --- Phase 2: 安全扫描 ---
[ ] --- Phase 4: git tag + push ---
[ ] --- Phase 5: GZ 部署 + verify ---
[ ] --- Phase 6: GitHub Release ---
```
