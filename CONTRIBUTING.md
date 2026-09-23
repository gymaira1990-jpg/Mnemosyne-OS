# 贡献指南

## 提交规范
Conventional Commits：`feat:` `fix:` `docs:` `style:` `refactor:` `perf:` `test:` `chore:` `release:`
标题命令式、英文短句；描述写**为什么**，不写「做了什么」。

## 分支与合并
1. `git fetch origin`，确认本地 `main` 与 `origin/main` 一致
2. 开功能分支：`git worktree add ../wt/mnemosyne-<topic> -b <type>/<topic> origin/main`
3. 改 → `pytest tests/` → commit → push → 开 PR → **盯 CI 全绿**

## 改动前必做
- 改**行为** → 先在 `openspec/changes/<name>/` 写 `proposal.md`，改完合入 `openspec/specs/` 并归档
- 改**对外接口 / 字段名 / 参数位置** → 必须加契约测试 + 反证（`git stash` 掉修复后必须红）
- **架构取舍** → 补 `docs/adr/NNNN-*.md`

## 发版
四段式门禁：A 开发 → B 测试全绿 → C 真实链路验收 → D tag/push/Release。
版本号**三处一致**：`VERSION` / 双语 README badge / `CHANGELOG.md`。发版前跑 `scripts/version-scan.sh`。

## 红线
- ❌ 绝不硬编码 API Key / 真实 IP / 域名 / 密码
- ❌ push 前必须隐私扫描（判据：**零输出**）
- ❌ 不得把 `AGENTS.md` / `CLAUDE.md` 交给 AI 静默改写（投毒攻击面，改动走 PR 审阅）
- ❌ 未过 B 段不进 C 段，未过 C 段不发 D 段
