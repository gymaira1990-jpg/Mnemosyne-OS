# Mnemosyne OS · Agent 手册

> 给 AI 编码助手的操作手册。**保持瘦**：细节在 `docs/`，能力真相在 `openspec/specs/`，历史在 `CHANGELOG.md`。
> **目标**：任何 Agent（Hermes / Claude Code / Cursor / Codex）5 分钟完成对接。

> **你是来「部署」的，不是来「改代码」的？** 先读 [DEPLOY-FOR-AI.md](DEPLOY-FOR-AI.md)（命令 + 判据 + 边界），
> 再跑 `bash scripts/bootstrap.sh`。这份 AGENTS.md 是给**改代码**的 Agent 看的。

**定位**：认知型记忆操作系统 —— 给 AI Agent 的长期记忆宫殿。**不是**向量数据库，**不是** RAG 管道。
**当前版本**：v9.0.9（仓库 = 生产，`GET /` 自报一致） ｜ 详见 [PROJECT.md](PROJECT.md)

## 怎么跑

```bash
pip install -r requirements.txt
pytest tests/          # 294 用例（服务端 + MCP 桥契约；契约用例需 Hermes 侧 mcp SDK，无则自动 skip）
```

## 9.0 端点速查（记忆操作系统）

| 端点 | 用途 | 备注 |
|---|---|---|
| `POST /api/v1/memory-os/recall` | 四通道召回（E 精确 / C 关键词 / T 时间 / S 语义） | 返回 `channel_counts`，每条候选带命中通道 |
| `POST /api/v1/memory-os/exact` | 档号 / 台账号 / 提交 / 路径精确查 | 先锚定首行，再全文兜底 |
| `POST /api/v1/memory-os/keywords` | 多词 OR + 覆盖率排序 | 不调 embedding，最便宜 |
| `GET  /api/v1/memory-os/trace/{no}` | 档号 → 卡片 → `sid` → 原文 | 两级跳取证 |
| `GET  /api/v1/memory-os/stats` | 卡片体检 | 档号率 / 实体率 / 向量覆盖 |
| `GET  /api/v1/memory-os/diary` | 日记 / 心里话 / 流水 | 前端一次性取数 |
| `GET  /api/v1/memory-os/health` | 子系统自检 | 部署后第一件事 |

> 8.x 的 `/api/v1/palace/*`、`/api/v1/tmt/*` 等仍可用；9.0 与其**物理隔离**，互不影响。

## 集成契约（改 handler / 集成代码前必读）

> v7.8.2 教训：MCP 桥三个工具在生产必报 422（`feedback` 发成 JSON body + 漏传 `user_id`）；同源错误发生在**响应字段**上时连报错都没有。**语义等价 ≠ 可用**。

1. **入参位置以服务端为准**：需 query 的端点（`feedback`/`delete`/`restore` 的 `user_id`）发成 JSON body → 422。`GET /api/v1/capabilities` 是唯一权威。
2. **响应字段名不许猜**：如 `heat-top` 返回 `heat_score`（不是 `heat`）。读错字段**不报错**，只会静默取默认值 —— 比报错危险。
3. **改 integration 必须跑契约测试**：`tests/test_mcp_bridge_contract.py`（锁 outbound 形态，反证过 proven-red）。新端点照此加例。
4. **投影/缓存以终值为准**：消费端注入文件（MEMORY.md 等）是服务端数据的投影 —— 校验必须在**回写之后**复测。
5. **生成拦不住就上保险**：约束（标准形态/幂等/固定锚点）+ 审查（正反比对、契约测试）+ 终值复测。

## 开发贡献

```bash
git clone https://github.com/gymaira1990-jpg/Mnemosyne-OS.git
```

- 提交：`feat:` / `fix:` / `docs:` / `chore:` / `release:`
- 改行为 → 先写 `openspec/changes/<name>/proposal.md`；完工后合入 `openspec/specs/` 并归档
- 架构取舍 → 补 `docs/adr/NNNN-*.md`

**红线**
- ❌ 集成代码改动必须带契约测试（capabilities 为唯一权威，不许凭印象写字段名/参数位置）
- ❌ 绝不硬编码 API Key / 真实 IP / 域名 / 密码
- ❌ push 前必须隐私扫描（判据：零输出）
- ❌ 扫描/门禁 pattern 改动必须**本地按 workflow 逐步复现**（判据：旧 pattern 命中 → 新 pattern 零命中）**且**过 pattern 双向自检（合法写法绿 / 硬编码红）；本地复现须带反证（放入真样本必须判红后清场）—— 门禁只在 push 后才跑，本地复现是唯一的推送前证据。判红的必须是「写死的值」而非「关键词出现」
- ❌ **版本落点全部一致** —— 不是「三处」：`VERSION` / 双语 badge / 双语版本表首行 / CHANGELOG / ROADMAP / AGENTS / PROGRESS / INSTALL（共 10 类落点）。
  2026-10-26 实测：此条原写作「三处一致」，于是每轮只对齐三处 ⇒ ROADMAP 落后三个版本、AGENTS 落后一版全都没人发现。
  **判据由机器给**：`python3 scripts/release_checks.py version-consistency`（exit=0 且打印查了 10 处）。

## 文档导航

| 文档 | 内容 |
|---|---|
| [PROJECT.md](PROJECT.md) | 这是什么 / 为什么 / 到哪了 ← **接手先读** |
| [README.md](README.md) · [README_CN.md](README_CN.md) | 产品全景（英 / 中） |
| [INSTALL.md](INSTALL.md) | 分环境安装 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 架构速览 |
| [docs/INTEGRATION.md](docs/INTEGRATION.md) | 对接（REST / SDK / Hermes Provider + 钩子） |
| [docs/API.md](docs/API.md) | 端点速查（权威：`GET /api/v1/capabilities`） |
| [docs/ENV.md](docs/ENV.md) | 环境变量全表 |
| [docs/AGENT-USAGE.md](docs/AGENT-USAGE.md) | Agent 使用最佳实践 |
| [openspec/specs/](openspec/specs/) | **能力真相**（系统现在做什么）—— 含 [memory-layers.md](openspec/specs/memory-layers.md) 分层模型 |
| [openspec/changes/](openspec/changes/) | 在途变更 |
| [docs/adr/](docs/adr/) | 架构决策记录 |
| [docs/schema.sql](docs/schema.sql) · [docs/WHITEPAPER.md](docs/WHITEPAPER.md) | 库结构 · 设计理念 |
| [CHANGELOG.md](CHANGELOG.md) | 版本历史 |
