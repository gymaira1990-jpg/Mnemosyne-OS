# docs/ 索引

> 先看这几份就够了。带「历史」标记的是归档，保留是为了可追溯，不必从头读。

## 现在有效

| 文档 | 讲什么 | 什么时候看 |
|---|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 分层、召回融合、存储结构 | 想改代码之前 |
| [API.md](API.md) | REST 端点与参数 | 接入或写客户端 |
| [ENV.md](ENV.md) | 全部环境变量与默认值 | 部署调参 |
| [INTEGRATION.md](INTEGRATION.md) | Hermes / MCP / Python SDK 接入 | 接到别的 Agent |
| [AGENT-USAGE.md](AGENT-USAGE.md) | 给 AI 助手看的最小用法 | 让 Agent 自己读 |
| [WHITEPAPER.md](WHITEPAPER.md) | 设计哲学（为什么是宫殿不是抽屉） | 想理解取舍 |
| [palace-architecture.md](palace-architecture.md) | 分类树 / 索书号的详细设计 | 用 Palace 层的人 |
| [schema.sql](schema.sql) | 完整表结构（21 张表） | 建库 |
| [adr/](adr/) | 架构决策记录 | 想知道「为什么不用 X」 |
| [design/](design/) | 逐版设计稿 | 考古 |

## 历史（归档，可跳过）

| 位置 | 是什么 |
|---|---|
| [archive/](archive/) | 旧版白皮书、已推翻的优化计划、8.x 以前的方案 |

**规矩**：新文档进这个索引；被推翻的不删，移到 `archive/` 并在本表标注 —— 判断依据留在世上，比删干净更有价值。
