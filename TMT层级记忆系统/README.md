# TMT 层级记忆系统

基于 TiMem (arXiv 2601.02845) 的 5 级时间记忆树，部署于 Mnemosyne 之上。

## 文件索引

| 文件 | 说明 |
|------|------|
| `cron配置/` | Hermes Cron 配置和手动触发脚本 |
| `验证脚本/` | 一键校验各层级蒸馏状态的脚本 |
| `蒸馏日志/` | L2-L5 蒸馏输出记录 |

## 核心公式

```
Φᵢ : (Cᵢ, Hᵢ, Iᵢ) → {m⁽ⁱ⁾}

Cᵢ = 子节点记忆
Hᵢ = 同层历史（滑动窗口）
Iᵢ = 层级特定的 LLM 指令
Φᵢ = LLM 蒸馏算子（Qwen3.5-9B, temperature=0.3）
```

## 关键文件路径

| 组件 | 路径 |
|------|------|
| TMT 主模块 | `/opt/mnemosyne/tmt.py`（GZ 服务器） |
| MCP 工具 | `/home/g-cat/.hermes/hermes-agent/tools/tmt_mcp.py` |
| SQL 迁移 | `/tmp/tmt_migration.sql` |
| 设计文档 | `/home/g-cat/mnemosyne_v2.1_timem_architecture.md` |

## API 端点

```
POST /tmt/consolidate/session  → L2 蒸馏
POST /tmt/consolidate/daily    → L3 每日
POST /tmt/consolidate/weekly   → L4 每周
POST /tmt/consolidate/monthly  → L5 画像
POST /tmt/recall               → 3阶段智能召回
POST /tmt/recall/simple        → 快速路径
POST /tmt/decay                → 热度衰减
POST /tmt/backfill             → 反填遗漏
GET  /tmt/tree/{user_id}       → 树结构概览
GET  /tmt/level/{l}/{id}       → 节点详情
```

## 热度体系

| 层级 | 初始值 | 每日衰减 |
|------|--------|---------|
| L1 | 0.5 | ×0.98 (2%) |
| L2 | 0.6 | ×0.97 |
| L3 | 0.7 | ×0.96 |
| L4 | 0.8 | ×0.95 |
| L5 | 1.0 | ×0.93 |
