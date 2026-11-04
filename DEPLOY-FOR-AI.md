# 部署手册（写给「接到这个仓库的 AI」）

> 版本: v9.0.12
>
> 你可能是一个被叫来「把这个仓库搭起来」的 Agent。这份文件就是给你的执行清单：
> **每一步都有命令和判据，判据不过就不要往下走**。不要凭印象补步骤，也不要跳过验收。

---

## 0. 你先确认三件事（30 秒）

```bash
cat VERSION                      # 仓库版本
python3 --version                # 要 3.11+
psql --version 2>/dev/null || echo "没有 psql"
```

| 结果 | 你要做的 |
|---|---|
| Python < 3.11 | 停下来，先装 Python 3.11+（Ubuntu: `apt install python3.12`） |
| 没有 psql | 停下来，先装 PostgreSQL 16+（不需要 Apache AGE，本项目 **v7.8 起已移除**） |
| 都有 | 继续第 1 步 |

**这个项目是什么**：一个自托管的 AI 记忆库（PostgreSQL + pgvector），提供 REST API。
它**不是**向量数据库，也**不是** RAG 框架 —— 别按那两个的套路去接。

---

## 1. 一条命令跑到「可验收」

```bash
bash scripts/bootstrap.sh
```

它会**幂等地**依次做：检查 Python → 检查 PostgreSQL → 建库（不存在才建）→ 导入 `docs/schema.sql`（表不足才导）
→ 建 `.venv` 并装依赖 → 生成 `.env` → 跑 `doctor` 自检。

**判据**：最后一行是 `✅ 就绪`，退出码 0。

中途它会停在一件事上：**`.env` 里的模型 key**。这一步必须由你或用户提供，脚本不会自己编：

```bash
# .env 里二选一（向量化是硬需求，没有 key 存不了东西）
ARK_API_KEY=<火山引擎 ARK>
# 或者 MODEL_BACKEND=openai + OPENAI_API_KEY=<任意 OpenAI 兼容端点>
```

拿到 key 后重跑 `bash scripts/bootstrap.sh`，直到它说 `✅ 就绪`。

> 只想体检不想改任何东西：`bash scripts/bootstrap.sh --check`

---

## 2. 验收（三个判据，缺一不可）

```bash
.venv/bin/python3 scripts/doctor.py          # 判据 1：全部通过
.venv/bin/python3 main.py &                  # 判据 2：服务自报版本
curl -s http://127.0.0.1:8010/               #         → {"service":"Mnemosyne OS vX.Y.Z", ...}
.venv/bin/python3 scripts/seed_demo.py       # 判据 3：写入 5 条 + 检索演示成功
```

三条都过 = 部署完成。任何一条不过，跑 `doctor.py` 看它说缺什么，**按它给的命令修**，别自己发明方案。

---

## 3. 到哪一步就该停（别自作主张往下做）

| 形态 | 含义 | 边界 |
|---|---|---|
| **A · 只要 API** | 跑 `main.py`，调用 `/api/v1/*` | **到这就结束了**。默认就是这一档，做完第 2 步即可 |
| **B · API + 自己的页面** | 用户想要日记页 / 检索页 | 仓库**不含前端**。页面按 [docs/PAGES-AND-PORTS.md](docs/PAGES-AND-PORTS.md) 自己写，读 `data.json` 或 REST |
| **C · 公网私人站** | 要登录墙、通行密钥 | 按 [docs/DEPLOY-PRIVATE.md](docs/DEPLOY-PRIVATE.md) 做（Authelia + nginx `auth_request`）；`docs/SECRETS-AND-PASSKEY.md` 讲密钥与恢复 |

**用户没说要 B 或 C，你就停在 A。** 自己加 nginx、加反向代理、加 TLS 属于超出委派 —— 先问。

---

## 4. 硬边界（做了会坏）

- ❌ **不要改 `docs/schema.sql` 就为了"让它跑"**。表结构是服务端契约；缺表的正确做法是重新导入这份文件。
- ❌ **不要手工 UPDATE 业务表**去"修数据"。写入一律走 API（`POST /api/v1/memories`），它负责向量与去重指纹。
- ❌ **不要把 key 写进代码或提交到 git**。只放 `.env`（`.gitignore` 已排除）。
- ❌ **不要让服务跑在 `0.0.0.0` 且无鉴权就暴露公网**。默认监听 `127.0.0.1`，这是有意的。
- ❌ **不要用 `recall` 的空结果判断"装坏了"**。`memory-os/recall` 搜的是**著录卡**，全新库没有卡 ⇒ 返回空是正常的；
  验证写入用 `POST /api/v1/memories/search`（搜原始记忆）。

---

## 5. 常见失败 → 处置

| 症状 | 原因 | 处置 |
|---|---|---|
| `no unique or exclusion constraint matching the ON CONFLICT` | 用了旧版 `schema.sql`（少 22 个索引） | 重新导入 `docs/schema.sql`（9.0.5+） |
| `.env` 填了但配置不生效 | 版本早于 9.0.5（没有 `load_dotenv`） | 升级到 9.0.5+，或 `set -a; . ./.env; set +a` 后启动 |
| `embedding API 失败: HTTP 401` | key 无效 / 未开通 doubao-embedding | 换 key，或 `MODEL_BACKEND=openai` + 其他端点 |
| 端口被占用 | 已有实例在跑 | `ss -lntp \| grep 8010`；或改 `.env` 的 `MNEMOSYNE_PORT` |
| 表只有十几张 | schema 导入中断 | `sudo -u postgres psql -d <库> -f docs/schema.sql`，看有无 ERROR |

---

## 6. 想二开的话

- 能力清单（系统现在做什么）：`openspec/specs/`
- 端点权威：`GET /api/v1/capabilities`（**不要凭印象写字段名和参数位置**）
- 架构：`docs/ARCHITECTURE.md`；集成：`docs/INTEGRATION.md`
- 改行为的流程与红线：`AGENTS.md`（那是给改代码的 Agent 看的，不是部署用的）

---

**一句话总结**：`bash scripts/bootstrap.sh` → 填 key → 再跑一次 → 三条验收过 → 停。
