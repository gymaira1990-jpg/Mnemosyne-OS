# Changelog

## v6.1-dev (2026-08-05)

### 🧪 知识蒸馏管道 (P0-1, MVP)

**动机**: 分类失衡 (session+worklog 88%, knowledge 9%) — 蒸馏只做了分类整理, 没做真正知识提炼。

**新增**: `tmt/distill.py` — 知识蒸馏管道 v0.1
- 设计来源: 爆炸遗产考古 (NCP-008 知识吸收七步 + 认知AI底座 TEL/MAIL 协议)
- 流程: 信号词候选筛选 → TEL 组装 → 豆包 Lite JSON 凝练 → ANN 去重闸机 (>0.92 跳过) → 入库 (knowledge→archive / pitfall→engineering) → metadata 溯源
- 用法: `python3 tmt/distill.py --batch N [--dry-run] [--stats]`

**部署**: GZ cron 每日 1:10 批量 60 条 (首轮 30 条: +22 knowledge, +1 pitfall, 5 fail 豆包偶发空返回下轮重捞)

## v6.0.1 (2026-08-02)

### ⚡ 生产性能与稳定性 — 双 worker + recall 容错

**并发隔离**
- `main.py` uvicorn `workers=1 → 2`：3 进程共享 8010（1父+2worker），慢请求（recall LLM 蒸馏）不再阻塞 search（实测 search 从排队 13s+ 降到 1.2-2.5s 恒定）

**recall 三层容错**（`tmt/router.py` + `core/llm.py`）
- 复杂度分类改**启发式**（关键词/长度判断 0/1/2），不再调 LLM：recall 常用查询 30s → 0.4s（embedding 缓存命中）
- gate 过滤 LLM 失败**降级保留全部候选**（try/except 包裹），不再 502
- `_call_ark` 豆包超时 60s → 15s；call_llm 连接类错误（URLError/TimeoutError/OSError）不升级 tier，直接快速失败（防 15s×3 重试放大）
- 效果：recall 新查询最坏 ~16s（豆包 embedding 慢，外部依赖），不再 60s 超时/502

**备注**
- 发布闭环：升级报告审阅 ✓ 用户验收 ✓ GitHub Release + tag ✓
- GZ 备份：`main.py.bak.20260802` / `core/llm.py.bak.20260802` / `tmt/router.py.bak.20260802(.2/.predegrade)`

## v6.0.0 (2026-08-02)

### 🎯 核心 — 概念模型重构：分类受控 + 管道修复 + 去重提速

**受控分类体系（解决分类混乱）**
- 新增受控词表 10 类：`knowledge` / `pitfall` / `reference` / `project` / `ops` / `deploy` / `preference` / `session` / `worklog` / `temp`
- 写入网关自动归一化：旧中英文分类（18 类）→ 10 类主键，未知分类 → knowledge（子串+全等双规则，24/24 用例）
- 数据库新增 `chk_memories_category` CHECK 约束，分类漂移从此被数据库层拦截
- 存量迁移：2295 条记忆 18 类 → 10 类，user_id 全收敛 `default`（单人使用语义）

**TMT 蒸馏管道修复（管道此前空转）**
- 修复 L2 会话蒸馏无参查询死锁：24h 窗口 + 最近 100 条未蒸馏碎片回退，管道不再空转
- 明确双层级语义：`tier`=价值分层（reflect 热度维护），`tmt_level`=TMT 时间树层（写入=1）
- reflect L4 不再直接软删记忆，改为 `forgotten_at` 标记（保留可恢复）

**Reflector 性能 + 去重修复**
- 冗余检测 O(n²) Python 逐对比较 → pgvector ANN 近邻查询：**33 分钟 → 5 秒（400 倍提速）**
- 相似度阈值 0.92 → 0.85：修复相似表述未合并的去重失效问题（首轮即合并 16 条冗余）

**Cron 修复**
- monthly 蒸馏 JSON decode error 根因：`date +%m` 前导零 `08` 非法 JSON 数字 → `date +%-m`

**运维清理**
- 删除历史遗留 `tmt_*_old` 表（4 张）
- 本地仓库归一：只保留 `~/mnemosyne-dev` 唯一真相源

## v5.5.2 (2026-07-29)

### 修复 — 语义搜索 NULL embedding 过滤

- **修复**: 5 处搜索 SQL 添加 `AND m.embedding IS NOT NULL`，防止 NULL 向量旧记录排在新记录前面
- **根因**: 迁移到豆包 embedding 后旧记录向量列为 NULL，SQL 排序把旧数据排到新数据前面
- **影响**: 修复后新记忆 100% 可搜索，不再被历史噪音淹没
