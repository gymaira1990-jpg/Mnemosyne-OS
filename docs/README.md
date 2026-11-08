# docs/ 索引

> 先看这几份就够了。带「历史」标记的是归档，保留是为了可追溯，不必从头读。

## 现在有效

| 文档 | 讲什么 | 什么时候看 |
|---|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 分层、召回融合、存储结构 | 想改代码之前 |
| [API.md](API.md) | REST 端点与参数 | 接入或写客户端 |
| [DEPLOY-PRIVATE.md](DEPLOY-PRIVATE.md) | 公网私人站：Authelia 通行密钥登录墙 + nginx auth_request（含三个实测坑） | 想让外人看不到内容 |
| [DIARY-PIPELINE.md](DIARY-PIPELINE.md) | 日记定时线：几点写、真源是谁、关机怎么办、产物保护 | 要「每天自动一篇」 |
| [PAGES-AND-PORTS.md](PAGES-AND-PORTS.md) | 端口表 + 页面与接口对照 + 自建前端最小示例 | 要摆页面 |
| [SECRETS-AND-PASSKEY.md](SECRETS-AND-PASSKEY.md) | 六类密钥、通行密钥注册顺序、轮换与丢失恢复 | 管密码/密钥 |
| [ENV.md](ENV.md) | 全部环境变量与默认值 | 部署调参 |
| [STAGING.md](STAGING.md) | 预发布环境：为什么必须有、隔离证明、四条判据、其他项目怎么套 | 任何上线前 |
| [RELEASE-PLAN.md](RELEASE-PLAN.md) | 版本规划与发布节奏（一个阶段 = 一个版本） | 想发版之前 |
| [AUDIT-20261108.md](AUDIT-20261108.md) | 流程与功能深度审计：13 个缺陷、反证记录、性能基线、已知边界 | 想确认「这东西可靠吗」 |
| [VERIFICATION.md](VERIFICATION.md) | 验收判据与复算 SQL（怎么自己核一遍） | 不信 README 的数字 |
| [MULTI-AGENT-SEAM.md](MULTI-AGENT-SEAM.md) | 多 Agent 的隔离口子：user_id 范围、可见域设计 | 要让多个 Agent 共用 |
| [CARD-SPEC.md](CARD-SPEC.md) | 著录卡规格：档号、实体、证据行、字段约定 | 写卡片/改召回 |
| [GATE-9.0.0.md](GATE-9.0.0.md) | 9.0 大版本的验收闸门清单 | 考古 9.0 怎么验的 |
| [INTEGRATION.md](INTEGRATION.md) | Hermes / MCP / Python SDK 接入 | 接到别的 Agent |
| [AGENT-USAGE.md](AGENT-USAGE.md) | 给 AI 助手看的最小用法 | 让 Agent 自己读 |
| [WHITEPAPER.md](WHITEPAPER.md) | 设计哲学（为什么是宫殿不是抽屉） | 想理解取舍 |
| [palace-architecture.md](palace-architecture.md) | 分类树 / 索书号的详细设计 | 用 Palace 层的人 |
| [schema.sql](schema.sql) | 完整表结构（21 张表） | 建库 |
| [en/](en/) | 英文版核心文档（ARCHITECTURE / API / STAGING） | 给不看中文的读者 |
| [adr/](adr/) | 架构决策记录 | 想知道「为什么不用 X」 |
| [design/](design/) | 逐版设计稿 | 考古 |

## 历史（归档，可跳过）

| 位置 | 是什么 |
|---|---|
| [archive/](archive/) | 旧版白皮书、已推翻的优化计划、8.x 以前的方案 |

**规矩**：新文档进这个索引；被推翻的不删，移到 `archive/` 并在本表标注 —— 判断依据留在世上，比删干净更有价值。
