# specs/ · 当前真相

存放**系统现在做什么**的规格，按领域切分。

写法（一条 Requirement = 一个可验证的行为）：

```markdown
## Requirement: <能力名>
系统 SHALL <具体行为>。
**验收**：<怎么判断做到了 —— 可测试、可观测>
```

建立时机：**第一次动到这个领域时**。改完把 `changes/<name>/specs/delta.md` 的 ADDED/MODIFIED
合进来，把 REMOVED 删掉。
