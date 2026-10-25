# 8.0.1 关卡阶段报告（P1 / P3 / P5）

- 版本：**8.0.1**
- 周期：用户 2026-10-26 令补齐完整发布流程（会话 msg 131245「有没有必要走完整的流程」/ 131256「跑通了证明了之后，你看要不要更新上去」/ 131312「你好好地检查一下」）
- 性质：**客户端改动**（`integrations/`）；服务端 `main.py` 未改

## 判据（各段可证伪，逐条给命令与期望值）

| 段 | 判据 | 命令 | 期望 |
|---|---|---|---|
| P1 | 工作区无未提交改动 | `git diff --quiet HEAD` | rc=0 |
| P2 | 全量套件绿 | `env -u PYTHONPATH .venv/bin/python -m pytest tests/ -q` | 0 failed |
| P2 | 分层规格自检 | `.venv/bin/python core/layers.py --self-check` | 输出 L0–L4，rc=0 |
| P2 | 回收干跑不改数据 | `jobs/compaction.py --dry-run …` | 打印「未做任何更改」 |
| P3 | 服务自报版号 == VERSION | `release_checks.py service-version <url>` | 含 `8.0.1` |
| P4 | 正式环境真链路 | `scripts/prod_smoke.py <url>` | 6/6 |
| P5 | 版本三处一致 | `release_checks.py version-consistency` | rc=0 |
| P5 | 隐私零输出 | `release_checks.py privacy` | rc=0 |
| P5 | 独立 clone 复扫 | clone 后 `git grep` 敏感 pattern | 零命中 |
| P6 | CHANGELOG 含版本 | `release_checks.py changelog 8.0.1` | rc=0 |


---

## P1 · 工作区开发（关卡）

| 项 | 值 |
|---|---|
| 门禁 | `git diff --quiet HEAD` → **rc=0，工作区干净** |
| 提交 | `release: 8.0.1 — Hermes 客户端工具（结果卡 + 检索路由）+ provider 190 行回流` |
| 改动面 | `integrations/hermes-client/`（4 新文件）+ `integrations/hermes-provider/__init__.py`（回流 +207/−25）+ `openspec/changes/memos-801-hermes-client/proposal.md` + 版本三处 |
| 未碰 | 服务端 `main.py` / 表结构 / 部署脚本 |
| 回滚 | `MEMORY_OS_V2=0` 停用客户端写入；已写入卡片可软删 |

## P3 · 部署（关卡）

| 项 | 值 |
|---|---|
| 门禁 | `scripts/release_checks.py service-version http://127.0.0.1:18010/` |
| 做法 | **只改版本标识文件，未重启服务** —— `_read_version()` 每次请求读 `VERSION`，故 `cp VERSION VERSION.bak-20261026` 后写入 `8.0.1` 即生效 |
| 证据 | `/` → `{"service":"Mnemosyne OS v8.0.1"}`；`/api/v1/capabilities` → `version: 8.0.1` |
| 回滚 | `cp /opt/mnemosyne/VERSION.bak-20261026 /opt/mnemosyne/VERSION` |
| 风险说明 | 服务端代码树未变动，本次仅为版本标识对齐；无行为变更 |

## P5 · 发布（关卡）

| 项 | 值 |
|---|---|
| 版本三处一致 | `VERSION=8.0.1` / `README.md`+`README_CN.md` badge `version-8.0.1` / `CHANGELOG` 含 `8.0.1` → `release_checks.py version-consistency` **rc=0** |
| 隐私扫描 | `release_checks.py privacy` → **rc=0（扫描 161 个追踪文件，零输出）** |
| 本地门禁复现 | `ci-workflow-replay.py .github/workflows/privacy.yml` → **合计失败步骤 0** |
| pre-push 门禁 | 上一笔 push 时输出「✅ 门禁通过」 |
| 独立 clone 复扫 | 已执行：`git clone --depth 1` → 新增目录扫描**零命中**；sha 对账一致（`4972665`） |
| 开源就绪 | README（英/中）已更新 badge；`integrations/hermes-client/README.md` 含环境变量表 + 已知限制 + 回滚 |

---

## 附 · P2 / P4 实测（非关卡，供核对）

| 段 | 命令 | 结果 |
|---|---|---|
| P2 | `pytest tests/ -q`（需 `env -u PYTHONPATH`） | **281 passed**，6.20s |
| P2 | `core/layers.py --self-check` | 输出 L0–L4 分层 JSON，rc=0 |
| P2 | `jobs/compaction.py --dry-run --dsn postgresql:///mnemosyne_v8test --limit 50` | 干跑未改数据，rc=0 |
| P4 | `scripts/prod_smoke.py http://127.0.0.1:18010` | **6/6 全通过**（L0 同来源→duplicate / L0 跨来源各存 / L1 stored→duplicate / 落库 layer=L0,L0,L1 / 测试件清场 3/3） |

### 环境坑（本轮实测，已记入结论）

`.venv` 的 Python 3.11 被注入 **Hermes 运行时 python3.14 的 site-packages**（`PYTHONPATH` 继承），
导致 `ModuleNotFoundError: pydantic_core._pydantic_core`。
**跑仓库测试必须 `env -u PYTHONPATH`** —— 否则 P2 全量必红，看起来像代码问题。
