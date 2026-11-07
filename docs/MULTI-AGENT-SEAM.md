# 多 Agent 口子（不是多租户）

> 2026-11-07 定：**不做商用多租户**（不做计费 / SLA / 租户管理）。
> 但**多 Agent 写入是现实**：dsh-* / nen-* / catnest-agent / content-agent 已经在写库了。
> 所以留「口子」而不是留「功能」—— 数据模型与接口按 `user_id` 隔离，将来要真做多租户时不用改表。

## 契约（三条）

1. **每条记忆都有 `user_id`**，缺省 `default`。写入方必须显式传自己的名字（禁止靠默认值蒙混）。
2. **任何按 id 操作数据的端点，必须同时限定 `user_id`**。只按 `memory_id` 定位 = 越权。
3. **跨用户操作只能是显式批处理**（如归档巡检），且必须能说出「为什么跨」，不能靠写死某个 uid 实现。

## 现状（2026-11-07 实测）

| 面 | 状态 | 说明 |
|---|---|---|
| `POST /memories` | ✅ 按 user | 缺省 default，写入即入库 |
| `POST /memories/search` | ✅ 按 user | 且 `category_filter` 已真生效（9.0.18） |
| `GET /memories/heat-top` | ✅ 按 user | — |
| `POST /palace/archive` | ✅ 全用户 | 9.0.18 起不再硬编码 `default`：归档是「给记忆建卡」，与谁写无关 |
| `POST /security/purify` | ✅ 按 user | 9.0.19 起限定范围；不可逆操作不能跨用户 |
| `GET /security/fossils` | ⚠️ `tenant_id`（默认 default） | 参数名与 `user_id` 不一致，语义上等价；暂不统一，避免破坏已有调用 |
| `GET /security/costs` | ⚠️ 进程级全局 | 成本统计没有按 user 分账（单用户系统无意义） |
| `GET /health` | ⚠️ 全局 | 健康检查，不涉及数据 |

## 已知的、故意没做的

- **按 user 分账 / 配额**：没有计费就没有分母，做了也是假功能。
- **跨 user 的可见性策略**（谁能看谁）：现在默认「各看各的」，没有任何共享语义。
- **`tenant_id` 与 `user_id` 合并**：改名会破坏现存调用，等真有第二个租户再说。

## 加新端点时照这个检查

```bash
# 1) 端点是否收 user_id（或等价的范围参数）
grep -n "user_id" <文件>

# 2) 凡是 UPDATE/DELETE，WHERE 里必须同时有 user_id
grep -nE "UPDATE|DELETE" -A4 <文件>

# 3) 跑一遍越权反证：拿 A 的 id、用 B 的 user_id 调，必须返回 not found
```

第 3 条已有现成样例：`tests/test_security_purify.py::test_purify_rejects_other_users_memory`
（把范围条件去掉，这条测试会红 —— 这就是它的价值）。
