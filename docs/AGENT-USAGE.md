# Agent 使用最佳实践

> 从 `AGENTS.md` 下沉。
> 返回 [AGENTS.md](../AGENTS.md)

## 最佳实践（Agent 用）

1. **存**：重要决策/踩坑/用户偏好 → `POST /memories`，带 `category`（10 类词表见下）
2. **取**：日常查询用 `POST /memories/search`；宫殿能力用 `palace/summon`；时间问题用 `GET /memories?sort=created_at`（**热度≠时间**）
3. **分类词表**（10 类，数据库 CHECK 约束）：
   `knowledge` 知识 · `pitfall` 踩坑 · `reference` 资料 · `project` 项目 · `ops` 运维 · `deploy` 部署 · `preference` 偏好 · `session` 会话 · `worklog` 日志 · `temp` 临时
4. **多用户**：`user_id` 天然隔离（`alice` / `bob` 互不可见）
5. **蒸馏**：定时 `POST /reflect?mode=light`（无 LLM 成本）；深度凝练用 `mode=deep`
6. **不要存**：代码/脚本（放 git）；临时状态（放会话）；可直接重算的中间值

---
