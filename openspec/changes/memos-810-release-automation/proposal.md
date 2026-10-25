# change: memos-810-release-automation — 发布材料自动化 + 版本落点机器校验

- **状态**：已实现（294 passed），待 P3 部署 + 关卡
- **日期**：2026-10-26
- **目标版本**：v8.1.0
- **影响面**：仓库工具链与文档（`scripts/`、`.github/`、四份文档）。**不改服务端 `main.py` 行为**。

## 为什么

用户 2026-10-26：『你自己的东西每次都感觉有遗漏，这严重影响我们的项目发布。还有我们的成果总结。』
体检结论：**不是记性问题，是「判据在技能整合时丢失 + 全靠手写」**。

| 事实 | 证据 |
|---|---|
| 机器检查只覆盖 3/15 处版本落点 | `AGENTS.md` 红线写「三处一致」，于是只对齐三处 |
| ROADMAP 落后三个版本 | 停在 v7.8.3（应为 8.0.x） |
| Version History 连续两版未登记 | v8.0.0 / v8.0.1 都缺，badge 却已更新 |
| CI 发布零校验 | workflow 只在 `push main` / PR 触发，推 tag 不跑 |
| 发布材料全手写 | CHANGELOG 段、版本表行、badge 三处都靠敲 |
| 旧技能判据丢失 | `mnemosyne-version-publish` §3.2 本有 15 处清单，整合时缩水 |

## ADDED

| 文件 | 作用 |
|---|---|
| `scripts/gen-release-notes.py` | 从 conventional commits 自动产出：①语义化 bump 建议（breaking→major / feat→minor / fix→patch）②Keep a Changelog 分段 ③**双语版本表行** ④**双语 badge**（幂等）。借鉴 git-cliff / commitizen / towncrier 的规则，**标准库自实现零依赖** |
| `tests/test_gen_release_notes.py` | 13 项回归（bump 6 例 / 分段结构 / breaking 置顶 / 空集诚实 / 版本表幂等 / CHANGELOG 幂等 / badge 幂等 / 内置自检） |
| `.github/dependabot.yml` | pip 每周 + actions 每月，分组降噪，不自动合并 |
| `CODE_OF_CONDUCT.md` | Contributor Covenant v2.1 精简版，报告走 GitHub 私密渠道 |
| `.github/pull_request_template.md` | 自查清单（测试 / 反证 / 隐私 / 版本落点） |
| `SECURITY.md` | 漏洞报告渠道 + 攻击面范围 + 部署自查清单 |

## MODIFIED

- `scripts/release_checks.py`：`version-consistency` 从 3 处扩到 **9 处**机器校验
  （双语 badge / 双语版本表首行 / CHANGELOG / ROADMAP / AGENTS / PROGRESS / INSTALL）；
  新增 `version-history` 检查（README 有历史表则必须登记当前 VERSION）。
- `.github/workflows/{privacy,test}.yml`：`push` 增加 `tags: ['v*']` —— **发布这一刻也要有门禁**。
- `AGENTS.md`：红线「版本号三处一致」改写为「版本落点全部一致」并指向机器判据。
- `release-gate.json`：P6 挂上 `version-history`；`changelog` 去掉版本硬编码（自动读 VERSION）。

## 判据表（可证伪）

| # | 判据 | 命令 | 期望 | 实测 |
|---|---|---|---|---|
| 1 | 9 处版本落点一致 | `release_checks.py version-consistency` | exit=0 且打印「查了 9 处」 | ✅ 9 处全 = 8.1.0 |
| 2 | Version History 已登记 | `release_checks.py version-history` | exit=0 | ✅ |
| 3 | 隐私零输出 | `release_checks.py privacy` | exit=0 | ✅ 164 文件 |
| 4 | 全量测试 | `PYTHONPATH= .venv/bin/python -m pytest tests/ -q` | 0 failed | ✅ **294 passed** |
| 5 | 工具能自动生成三处落点 | `gen-release-notes.py --write` | CHANGELOG+badge+版本表都被改 | ✅ 三处均写入 |
| 6 | 反证：落点不一致必须红 | 把 ROADMAP 改回旧版号 | exit=1 | ✅ 抓到 |
| 7 | tag 触发 CI | `grep -A3 'push:' .github/workflows/*.yml` | 每份含 `tags: ['v*']` | ✅ 两份都有 |

## 不做清单（Out of Scope）

1. **不装外部工具**（git-cliff / commitizen / semantic-release）—— 只用标准库自实现，符合「只用官方件」铁律。
2. **不引入 release-please 的 PR 流程** —— 我们现在直接推 main，改工作方式成本大于收益；只借它的「机器算、人确认」思路。
3. **不改服务端 `main.py`** 的检索/存储行为，不动表结构。
4. **不动历史 tag**（v3.5 / v5.0-p1 等非严格 semver 属历史，不追溯重命名）。
5. **不做存量脱敏**（属独立批次，见台账）。
6. **不自动 bump VERSION** —— 版本号是人的决定，工具只给建议（`--bump`）与写材料。
