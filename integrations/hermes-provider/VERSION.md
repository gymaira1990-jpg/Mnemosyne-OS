# Mnemosyne Memory Provider

版本: 5.3.0 | 状态: 已发布 | 日期: 2026-07-06

## 版本历史

| 版本 | 日期 | 核心变更 |
|------|------|---------|
| 5.2.1 | 2026-06-27 | 初始: 10工具 + sync_turn + prefetch + 写队列 + 熔断器 |
| 5.3.0 | 未发布 | on_pre_compress + on_delegation + prefetch增强 + prompt增强 |

## ABC 实现矩阵 (Hermes v0.18.0)

| Hook | 状态 |
|------|:---:|
| initialize | ✅ |
| system_prompt_block | ✅ (v5.3增强) |
| prefetch | ✅ (v5.3增强) |
| queue_prefetch | ✅ |
| sync_turn | ✅ |
| on_session_end | ✅ |
| on_pre_compress | ❌ → v5.3.0 |
| on_delegation | ❌ → v5.3.0 |
| on_memory_write | ✅ |
| on_session_switch | ✅ |
| get_tool_schemas | ✅ 10工具 |
| handle_tool_call | ✅ |
| shutdown | ✅ |

## 业界对标

| 能力 | Mem0 | Honcho | Zep | 我们 |
|------|:---:|:---:|:---:|:---:|
| 语义搜索 | ✅ | ✅ | ✅ | ✅ |
| 自动同步 | ❌ | ✅ | ✅ | ✅ |
| 预取注入 | ❌ | ✅ | ❌ | ✅ |
| 会话蒸馏 | ❌ | ✅ | ❌ | ✅ |
| 崩溃安全写队列 | ❌ | ❌ | ❌ | ✅ 独有 |
| 熔断保护 | ❌ | ❌ | ❌ | ✅ 独有 |
| on_pre_compress | ❌ | ❌ | ❌ | v5.3 ✅ |
| on_delegation | ❌ | ❌ | ❌ | v5.3 ✅ |
