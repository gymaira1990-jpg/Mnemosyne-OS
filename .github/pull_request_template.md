## 这个 PR 做了什么

<!-- 一句话说清。对应 issue 请写 Closes #xxx -->

## 类型

- [ ] `feat` 新功能
- [ ] `fix` 修复
- [ ] `docs` 文档
- [ ] `refactor` 重构（不改行为）
- [ ] `perf` 性能
- [ ] `test` 测试
- [ ] `chore` / `ci` / `build`

## 自查清单（合并前逐条确认）

- [ ] **本地全量测试绿**：`PYTHONPATH= .venv/bin/python -m pytest tests/ -q`
- [ ] **改行为的提交带了契约测试**（断言的是出网请求/解析的**形态**，不是内部实现细节）
- [ ] **反证跑过**：把修复临时撤掉，新测试必须变红（证明它真能拦住）
- [ ] **没碰硬编码**：API Key / 真实 IP / 域名 / 用户路径一律不进代码
- [ ] **隐私扫描零输出**：`python3 scripts/release_checks.py privacy`
- [ ] **版本落点未漂移**：`python3 scripts/release_checks.py version-consistency`（若本 PR 只是普通改动，此条应保持绿）
- [ ] 若涉及发版：`version-history` / `changelog` 也绿

## 影响面

- 是否改动服务端行为：<是/否>
- 是否需要部署：<是/否>
- 回滚方式：<一句话>

## 给评审者的提示

<!-- 建议重点看哪几处？哪部分你也不确定？直接写出来，不要藏 -->
