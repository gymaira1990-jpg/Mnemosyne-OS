# Mnemosyne Memory Provider — CHANGELOG

## v5.3.0 (2026-07-06)

### 新增
- on_pre_compress: 上下文压缩前自动提取并保存关键洞察，返回摘要注入压缩 prompt。对标 Honcho dialectic + Mem0 fact extraction
- on_delegation: 子代理完成后自动存储任务+结果到记忆宫殿。对标 Zep temporal fact tracking
- prefetch 增强: 复杂查询自动追加辨证搜索（含 L2/L3 会话上下文），对标 Honcho dialectic
- system_prompt_block 增强: 新增 L1/L4/L5 TMT 层级显示、总记忆数、分类 TOP3 分布

### 技术指标
- 代码: 862 → 1011 行 (+149)
- ABC Hook 覆盖率: 8/10 → 10/10 (100%)
- 工具数: 10 (不变)
- 业界独有特性: 崩溃安全写队列 + 熔断保护 (保持)

---

## v5.2.1 (2026-06-27)

### 初始版本
- 10工具 (search/remember/recall/tree/hot/dialectic/tiered/conflicts/wiki/media)
- sync_turn 自动存储每轮对话 (写队列+熔断器)
- prefetch/queue_prefetch 后台预取+注入
- system_prompt_block 热点记忆注入 (时间衰减)
- on_session_end TMT L2蒸馏触发
- on_memory_write 内置memory镜像
- on_session_switch 队列刷新
