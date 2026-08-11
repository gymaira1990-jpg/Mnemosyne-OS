# Mnemosyne Memory Provider — CHANGELOG

## v7.6.1 (2026-08-11)

### 同步
- 同步 Hermes 实际运行版本（plugins/memory/mnemosyne）
- 新增 `mnemosyne_palace_summon` 工具（三通道召唤，v7 核心）
- 增强 wiki 方法（search_wiki / get_wiki_by_source）
- 写过滤（低价值消息跳过）+ 首轮冷启动
- 兼容 Hermes v0.19.0+

### 工具数
- 10 → 11

---

## v1.1.0 (2026-07-29)

### 新增
- 写过滤: 低价值消息跳过（避免噪音入宫）
- 首轮冷启动: 新会话首轮即注入相关记忆
- 格式优化: cat_emoji 摘要风格

---

## v1.0.0 (2026-07-06)

### 初始版本
- 10工具 (search/remember/recall/tree/hot/dialectic/tiered/conflicts/wiki/media)
- sync_turn 自动存储每轮对话 (写队列+熔断器)
- prefetch/queue_prefetch 后台预取+注入
- system_prompt_block 热点记忆注入 (时间衰减)
- on_session_end TMT L2蒸馏触发
- on_memory_write 内置memory镜像
- on_session_switch 队列刷新
- 崩溃安全写队列 + 熔断保护 (业界独有)
