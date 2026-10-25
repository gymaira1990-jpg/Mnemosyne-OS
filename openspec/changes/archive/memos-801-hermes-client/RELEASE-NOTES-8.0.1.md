## Hermes 客户端工具：结果卡 + 检索路由

给 **Hermes + Mnemosyne** 组合用的客户端工具。解决的痛点：会话原文存在 `state.db` 里（FTS 秒查），
但语义召回只捞得到碎片 —— 真正有价值的「这轮做了什么、结果如何、证据在哪」反而查不到。

### 新增 `integrations/hermes-client/`

- **`outcome_cards.py`** — 按**用户消息**切轮生成「结果卡」（问 / 做 / 证据 / `msg_range` 钩子），
  只收有可验证产物或明确结论的轮次；纯摘录，**零模型调用**
- **`route-search.py`** — 检索路由：先查结果卡（语义）→ 相关度不足再下探 `state.db` FTS →
  两路皆空时**明说未命中**，不做推测
- **`tests/test_memos_801.py`** — 12 项回归（切轮 / 系统通知剔除 / 无产物跳过 / 路由判定 / 钩子优先级）
- **`README.md`** — 环境变量配置表、接入说明、已知限制、回滚方式

### 回流 `integrations/hermes-provider/`

同步 2026-09-12 → 2026-10-13 期间积累的改进（+207 / −25）：

- 自回声过滤（防止把本会话自己的输出回灌成记忆）
- 片段降权（session / worklog ×0.5，避免流水账挤掉真知识）
- 会话收尾后台化（原来会话结束要卡约 15 秒）
- 事实提取默认关闭（避免与每日批处理重复劳动）
- upsert 语义（避免重复写入）
- 软删镜像（保证可恢复）

### 实测数据

| 项 | 结果 |
|---|---|
| 卡体积 | 会话主档 107,428 字 → 6 张卡 1,815 字（**1.7%**） |
| 注入位 | 钩子区前两条即结果卡（结果类 2/6 = 33%） |
| 路由 | `palace:outcome` 命中并返回交付物路径；`hybrid` 下探命中原文 |
| 回归 | 本机 12 passed；包内 10 passed + 2 skipped |
| 隐私门禁 | 本地复现全步 exit=0；pre-push 通过；独立 clone 复扫零命中 |

### 注意

服务端 `POST /api/v1/memories` 会**静默覆盖** `category` 与 `importance`（`metadata` 被保留）。
因此客户端一律用**内容前缀**（`MEMOS_CARD_PREFIX`，默认 `[结果卡] `）识别结果卡，不依赖 category。
非中文环境请改为 `[outcome] `。

### 环境要求

- Python 3.11+（仅标准库；测试需 pytest）
- 在 Hermes 会话内跑外部 venv 测试时，务必 `env -u PYTHONPATH`，否则会继承运行时 site-packages 导致二进制不兼容
