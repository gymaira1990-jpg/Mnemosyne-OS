# Mnemosyne OS 状态

## 当前版本: 9.1.2 — 里程碑：可度量 · 可求证 · 可预发布

## 状态（2026-11-08 实测，全部可复现）

| 面 | 事实 | 判据 |
|---|---|---|
| 生产 | `/opt/mnemosyne` 自报 **v9.1.2**，`mnemosyne` active | `curl /api/v1/capabilities` |
| 预发布 | `/opt/mnemosyne-staging`（`127.0.0.1:8020`，库 `mnemosyne_staging`）active | 同上 |
| 代码一致性 | 部署面 **82 个文件全部命中**，**0 处未登记漂移**、**0 条欠账**；6 条实配例外（`.env`/crontab 等主机配置） | `make prod-diff` |
| 测试 | **370 passed / 0 skipped**（空库只导 `docs/schema.sql` 也是全过） | `hermes verify --json` |
| 冒烟 | 生产 **6/6**、预发布 **6/6** | `scripts/prod_smoke.py` |
| 检索 | demo 16 题 recall@10 = **94%**（含 4 条负样本；区分度自检通过） | `make eval-semantic` |
| 数据 | 记忆 38,858（未删除 33,171）· 著录卡 35,075 · 结果卡 3,622 · 向量覆盖 **100%** | SQL 对拍 |
| 备份 | 本地 8 份 + 异地 HK 3 份；sha256 校验 OK、`pg_restore --list` 24 张表、异地字节数一致 | `noah-buffer/backups` |

## 部署流程（2026-11-08 起强制）

```
本地 make test / lint / 反证
  → bash scripts/deploy_staging.sh        （预发布 + 冒烟 6/6）
  → 人工看一眼
  → bash scripts/deploy_prod.sh           （要求该提交已在预发布验过）
  → 生产冒烟 + prod-diff 0 漂移
  → 阶段目标全绿 + 主人确认 → 才 tag / Release
```

## 下一步

1. **评测集补盲**：现有 16 题全是「结果卡」，量不到占 89% 的非卡片记忆（已知边界，不是 bug）
2. **跨进程查询向量缓存**：召回首问约 500ms 花在 embedding 往返，复问约 95ms（进程内缓存已生效）
3. **自动回滚与部署告警**：目前回滚靠人执行 `cp -a .backup-<ts>/. .`，部署失败靠人看脚本输出
4. **多 Agent 可见域**：`scope`（private/shared/project）设计已留口子，等主人拍板取值

> 历史状态与逐版明细在 `CHANGELOG.md` —— 本文件只留当前快照，不再累积。
