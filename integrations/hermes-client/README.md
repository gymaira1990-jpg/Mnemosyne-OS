# Memory OS 8.0.1 · Hermes 客户端工具（结果卡 + 检索路由）

给 **Mnemosyne 记忆库 + Hermes** 这套组合用的两个客户端工具。解决一个具体问题：

> 会话原文存在 `state.db` 里（逐字、能 FTS 秒查），但**语义召回只捞得到碎片**；
> 真正有价值的「这轮做了什么、结果如何、证据在哪」反而查不到。

本工具把每轮对话**收成一张结果卡**（问 / 做 / 证据 / 原文指针 `msg_range`），并把检索改成
「先查结果卡 → 没有再下探原文」。

零模型调用（纯摘录），所以没有额外 API 成本。

---

## 一、它由什么组成

| 文件 | 作用 |
|---|---|
| `outcome_cards.py` | 按用户消息切轮 → 生成结果卡 → 写入 Mnemosyne |
| `route-search.py` | 检索路由：结果卡（语义）→ 不足则下探 `state.db` FTS |
| `tests/test_memos_801.py` | 回归测试（12 项） |
| 建议接线点 | `archive_session.py`（会话归档后推卡）、`memory_hooks.py`（钩子区优先展示结果卡） |

---

## 二、依赖

- **Mnemosyne 8.x**（默认 `http://127.0.0.1:18010`）
- **Hermes**（提供 `~/.hermes/state.db`）
- Python 3.11+（仅标准库；测试需 pytest）

---

## 三、按你自己的环境改这几处（重要）

所有本机路径/端点都可通过**环境变量**覆盖，**不要改源码**：

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `MNEMOSYNE_URL` | `http://127.0.0.1:18010` | 记忆库地址 |
| `MNEMOSYNE_API` | `$MNEMOSYNE_URL/api/v1/memories` | 写入端点 |
| `MEMOS_STATE_DB` | `~/.hermes/state.db` | Hermes 会话库路径 |
| `MEMOS_CARD_PREFIX` | `[结果卡] ` | 结果卡内容前缀；**非中文环境请改成 `[outcome] `** |
| `MEMOS_CARD_CATEGORY` | `worklog` | 写入类别；**请用你服务端白名单里的类别** |
| `MEMORY_OS_V2` | `1` | 置 `0` 整体关闭结果卡写入（回滚开关） |

### ⚠️ 一个必读的坑

Mnemosyne 的 `POST /api/v1/memories` 会**静默覆盖** `category` 与 `importance`
（实测 `outcome` → `knowledge`、`0.8` → `0.5`），但**保留 `metadata`**。

因此本工具**不依赖 category 做识别**，改用**内容前缀**（`MEMOS_CARD_PREFIX`）当锚点 ——
服务端不改内容，这条路它改不掉。你的检索侧也要按前缀（或 metadata 里的 `kind: outcome`）识别。

---

## 四、装法

```bash
# 1) 放到你的脚本目录
cp outcome_cards.py route-search.py  ~/.hermes/scripts/
cp tests/test_memos_801.py           ~/.hermes/scripts/tests/

# 2) 跑测试确认环境 OK
python3 -m pytest ~/.hermes/scripts/tests/test_memos_801.py -q     # 期望 12 passed

# 3) 自测一张卡（不写库）
python3 ~/.hermes/scripts/outcome_cards.py --selftest
```

### 接入归档管道（可选）

在你的归档脚本里，归档成功后加一行：

```python
from outcome_cards import build_cards, push_cards
cards = build_cards(session_messages, session_id)   # session_messages: [{id, role, content}, ...]
push_cards(cards)                                   # 干跑传 dry_run=True
```

### 接入注入钩子区（可选）

钩子区排序时让结果卡置顶，并**豁免热度门槛**（结果卡是新写入的，热度必然低于阈值，
不豁免就永远进不了注入位）：

```python
prio = 0 if content.startswith(CARD_PREFIX) else CAT_PRIORITY.get(category, 6)
# 另外：候选池要同时包含「热度 TopN」和「最近写入 TopN」——
#       只按热度取候选时，新内容永远排在后面（热度自增强）
```

---

## 五、用法

```bash
# 检索（先结果卡，没有则下探原文）
python3 route-search.py "上次那个悬空路径怎么发现的"

# 看结构化输出
python3 route-search.py "备份告警" --json
```

路由值含义：

| 值 | 含义 |
|---|---|
| `palace:outcome` | 命中结果卡，带 `msg_from/msg_to` 可直接跳原文（最优） |
| `hybrid` | 无结果卡，同时给「宫殿参考 + 原文命中」 |
| `state:fts` | 只在原文里命中 |
| `palace:weak` | 只有宫殿内容，原文未命中 |
| `miss` | 两路都空 —— **明说未命中，不做推测** |

---

## 六、已知限制（诚实清单）

1. **切轮以「用户消息」为界**，不依赖收尾语 —— 实测「汇报完毕请指示」类收尾语覆盖率仅 57%，不可作边界。
2. **中文切词是启发式**（2–4 字滑窗），其他语言只按空格切；FTS 兜底对长查询可能漏。
3. **轮次级实时写盘做不到** —— shell hook 只有会话级（`on_session_end`），所以卡片在会话结束时整批生成。
4. 摘录会把正文里的**示例文本**误当结论（已过滤缩进 4 空格行与引用块，仍可能有漏网）。
5. 结果卡命中率依赖语义相似度，**卡片内容越具体越好查**（把版本号/路径写进「做」那几行）。

---

## 七、回滚

```bash
export MEMORY_OS_V2=0        # 停止写入新卡（已有卡片不受影响）
```

已写入的卡可按 id 软删（Mnemosyne 的 `DELETE /api/v1/memories/{id}`），数据可恢复。

---

## 八、验证记录（本机实测，供参考）

| 项 | 结果 |
|---|---|
| 回归测试 | 12 passed |
| 卡体积 | 主档 107,428 字 → 6 张卡 1,815 字（**1.7%**） |
| 注入位 | 钩子区前两条即结果卡（结果类 2/6 = 33%） |
| 路由 | `palace:outcome` 真命中，返回交付物路径；`hybrid` 下探命中原文 `msg39334` |
| 幂等 | 钩子区重复执行「无变化」 |
