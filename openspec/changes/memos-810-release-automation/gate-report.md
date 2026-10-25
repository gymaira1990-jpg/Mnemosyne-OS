# 8.1.0 关卡阶段报告（P1 / P3 / P5）

- 版本：**8.1.0**
- 周期：用户 2026-10-26 令「赶紧优化掉」，并给出关卡确认码
- 性质：**仓库工具链 + 文档**；服务端 `main.py` 行为未改（仅版本标识）

## 判据（可证伪，逐条给命令与期望）

| 段 | 判据 | 命令 | 期望 | 实测 |
|---|---|---|---|---|
| P1 | 工作区无未提交改动 | `git diff --quiet HEAD` | rc=0 | ✅ |
| P1 | 9 处版本落点一致 | `release_checks.py version-consistency` | exit=0 且「查了 9 处」 | ✅ 全 = 8.1.0 |
| P2 | 全量套件绿 | `PYTHONPATH= .venv/bin/python -m pytest tests/ -q` | 0 failed | ✅ **294 passed** |
| P2 | 分层规格自检 | `.venv/bin/python core/layers.py --self-check` | rc=0 | ✅ |
| P2 | 回收干跑不改数据 | `jobs/compaction.py --dry-run …` | 未做任何更改 | ✅ |
| P3 | 服务自报版号 == VERSION | `release_checks.py service-version <url>` | 含 `8.1.0` | 见下 |
| P4 | 正式环境真链路 | `scripts/prod_smoke.py <url>` | 6/6 | 见下 |
| P5 | 版本三处→九处一致 | `release_checks.py version-consistency` | exit=0 | ✅ |
| P5 | Version History 已登记 | `release_checks.py version-history` | exit=0 | ✅ |
| P5 | 隐私零输出 | `release_checks.py privacy` | exit=0 | ✅ 164 文件 |
| P6 | CHANGELOG 含版本 | `release_checks.py changelog` | exit=0 | ✅ |

## 证据（原始命令输出摘录）

```
scripts/release_checks.py version-consistency
✅ 版本落点全部一致 = 8.1.0（查了 9 处：EN badge / CN badge / EN 版本表首行 / CN 版本表首行 /
   CHANGELOG 最新段 / ROADMAP 首行 / AGENTS 当前版本 / PROGRESS 当前版本 / INSTALL 版本行）

PYTHONPATH= .venv/bin/python -m pytest tests/ -q
294 passed, 4 warnings in 6.28s

scripts/gen-release-notes.py --selftest
SELFTEST OK — bump 规则 4 例 + 生成结构 4 项断言全过

scripts/gen-release-notes.py --since v8.0.1 --write
✅ 已写入: CHANGELOG.md, README.md, README_CN.md
```

- **反证 1**：把 ROADMAP 首行改回 `v7.8.3` → `version-consistency` 立刻 `exit=1` 并指出该行。
- **反证 2**（历史）：VERSION 临时改 `9.9.9` → `version-history` `exit=1`。还原后回绿。
- **反证 3**：改 badge 前 `version-consistency` 报「EN badge 是 8.0.1，应为 8.1.0」→ 说明 9 处检查真的覆盖 badge（并促成本轮把 badge 也做进工具）。

## P1 · 工作区开发

| 项 | 值 |
|---|---|
| 改动 | `scripts/gen-release-notes.py`（新增 bump_badge，三处落点自动写）+ `tests/test_gen_release_notes.py`（13 项）+ `scripts/release_checks.py`（version-consistency 3→9 处、新增 version-history）+ `.github/workflows/{privacy,test}.yml`（tag 触发）+ `.github/dependabot.yml` + `CODE_OF_CONDUCT.md` + `.github/pull_request_template.md` + `SECURITY.md` + 四份文档版本同步 |
| 未碰 | 服务端 `main.py` 检索/存储行为、表结构、部署脚本逻辑 |
| 回滚 | 全部为文件改动，`git revert` 即可；无数据面变更 |

## P3 · 部署

| 项 | 值 |
|---|---|
| 做法 | 仅同步版本标识 `VERSION` → 8.1.0（服务端 `_read_version()` 每请求读文件，无需重启） |
| 备份 | `/opt/mnemosyne/VERSION.bak-20261026-810` |
| 回滚 | `cp /opt/mnemosyne/VERSION.bak-20261026-810 /opt/mnemosyne/VERSION` |
| 风险 | 无行为变更（服务端代码未动） |

## P5 · 发布

| 项 | 值 |
|---|---|
| 版本落点 | 9 处全部 = 8.1.0（机器核，非人工看） |
| 隐私 | `release_checks.py privacy` exit=0；pre-push 钩子扫描 |
| 独立 clone | 推送后重 clone 复扫 + sha 对账 |
| CI | `test` + `privacy & version gates` 两个 workflow；本次起 **tag 也触发** |
| 开源就绪 | badge / Version History / SECURITY / CoC / PR template 齐备 |

## 附 · 本轮工具地址

- `scripts/gen-release-notes.py --since v8.0.1` → 本次 CHANGELOG 段与三处落点均由它生成（dogfooding）
