# Mnemosyne OS · 路线图

> v5.4.0 | 2026-07-23

## 版本路线

v5.2.x (稳定) → v5.3 (品质+治理) → v5.4 (三馆激活) ✅ → v6.0 (认知架构)

## v5.3.0 — 仓库治理 + Hermes 集成 ✅

- 统一仓库结构 (GitHub ↔ GZ 同步)
- MCP Bridge 纳入 (integrations/hermes-mcp/)
- Memory Provider v5.3.0 纳入 (integrations/hermes-provider/)
- Hermes Skills 纳入 (skills/)
- Cron 脚本纳入 (cron/)
- VERSION + 语义化版本
- AGENTS.md 分身使用手册
- 分支对齐 master→main

## v5.3.x — 品质提升 ✅

- 测试覆盖率 ≥ 核心算法 100% (18/18)
- 双轴检索协议 (热度轴/时间轴分离)
- 会话消息同步 (conversation_messages)
- AGE 查询安全加固

## v5.4.0 — 三馆激活 ✅

- 闸机接入异构审计 (双模型交叉验证)
- 建议清单端点 (GET /halls/suggestions)
- 工具归档路径修复 (统一入工程馆)
- pytest 测试框架 (18 用例)

## v6.0 — 认知架构

- 元认知层
- 信念系统重构
- 智能召回三阶段

## 迭代纪律

1. 不在 ROADMAP 的不做
2. PLAN→code→test→隐私扫描→文档→tag
3. 本地开发→GZ验证→仓库发布
