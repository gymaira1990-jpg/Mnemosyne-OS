# openspec · 规格层

> 分两层：`specs/` = **系统现在做什么**（真相）；`changes/` = **正在改什么**（在途）。

```
openspec/
├── specs/                    # 当前真相（权威）
│   └── <领域>/spec.md
├── changes/                  # 在途变更，一个变更一个文件夹
│   ├── <change-name>/
│   │   ├── proposal.md       # 为什么改 / 改什么 / 不改什么 / 验收
│   │   ├── design.md         # 技术上怎么改
│   │   ├── tasks.md          # 可勾选任务
│   │   └── specs/delta.md    # 增量：ADDED / MODIFIED / REMOVED
│   └── archive/              # 已完结（日期前缀）
└── config.yaml
```

## 怎么用

1. **改行为前**：`mkdir -p openspec/changes/2026-09-24-<变更名>`，复制模板写 `proposal.md`（三行也成立）
2. **改完**：勾 `tasks.md` → 把 delta 合入 `specs/` → 整个变更目录移进 `archive/`
3. **永不**：为已经存在的代码补一份"全量基线"（没人验证过的文档从第一天就开始腐烂）

## 领域索引（当前能力地图，详见 [specs/](specs/)）

| 领域 | 内容 | 规格 |
|---|---|---|
| memory | 记忆写入/召回/生命周期 | 待写（下次改动时建立） |
| palace | 宫殿分类/档号/著录卡片/三通道召唤 | 待写 |
| distill | TMT 蒸馏/事实提取/合并 | 待写 |
| wiki | 知识库检索（BM25+向量 RRF） | 待写 |
| sync | 端云同步（SQLite↔PG） | 待写 |
| integrations | REST / SDK / MCP / Hermes Memory Provider | 待写 |
| ops | 定时任务/备份/健康监控 | 待写 |

> ⚠️ 上表是**能力地图**，不是规格。规格按 brownfield 原则**围绕真实改动逐步建立**。
