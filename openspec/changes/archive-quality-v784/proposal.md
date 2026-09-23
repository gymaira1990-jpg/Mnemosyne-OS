# change: archive-quality-v784 — 归档质量：收尾汇报不再被切 + 汇报卡入库

- **状态**：已实现（测试全绿），**待发布**（未 tag / 未推送 / 未部署）
- **日期**：2026-09-24
- **目标版本**：v7.8.4
- **影响面**：采集端（Hermes → Mnemosyne 归档链路）。**不动服务端** `main.py` 的检索/存储行为。

## 为什么（触发）

用户问「生产服务器上那个几百兆的文件是什么」，全线查不到 —— 后果是两次误判（先说"我没说过"，再纠正错归属日期）。

实测根因（写入前先取证，不猜）：

| 事实 | 证据 |
|---|---|
| 原话**一条没少** | `~/.hermes/state.db` 296 会话 / 42,565 条消息 |
| 语义层**查不到** | `archive_session.py` 对每条消息一刀切 `content[:2000] + "(截断)"`，而收尾汇报常 >2000 字 |
| 切掉的恰是精华 | 交付物**绝对路径 / URL / 哈希 / 实测数字**都在汇报后半段 |
| 工具证据**全丢** | 归档只取 `content`，`tool_calls` 不入库（本机 17,486 条消息带工具调用） |
| 小任务**无痕** | `auto_mode()` 里 `message_count < 5: continue` |
| 生产有、仓库无 | 部署副本 2026-09-04 的 `_detect_project` 接线未回库（漂移） |

与 (v7.8.2)「语义等价 ≠ 可用」同源：**改了粒度而消费端没跟上，不报错、只失真**。

## MODIFIED

`scripts/archive_session.py`
- 分级截断：收尾汇报（会话最后一条有正文的 AI 消息）与用户消息**全文保留**；过程消息压缩到 `LIMIT_PROCESS=1200`；总预算 `MAX_TOTAL=120000` 超限时**只压缩过程消息**，汇报永不裁剪（预算不低于旧版实际入档量级）。
- 证据签名：带 `tool_calls` 的消息附 `⟪工具: terminal×3, read_file×2⟫`（上限 `TOOL_SIG_MAX=5` 种，容错坏 JSON）。
- 短会话：`message_count < SHORT_SESSION(5)` 不再跳过，入库并打 `[短]` 前缀；`--skip-short` 还原旧行为。
- 标题：`_compose_title()` 把 `[项目]` / `[短]` 合成**单个**标签（`[短·relife]`），且**幂等**（重复处理不叠加）。
- 回库：部署副本已验证的 `_detect_project` 接线并入（命中关键词 ≥2 才打项目前缀）。

## ADDED

`scripts/report_card.py` — 汇报卡抽取器
- 信号：路径（Win/Unix）· URL · 哈希（≥16 hex）· 实测数字 · 收尾语 · 校验语；命中 **≥2 类**才认作交付级汇报。
- 落点：`~/.hermes/reports/cards.jsonl`（一行一卡，含 session/msg_id/时间/信号统计/路径/URL/哈希/数字/原文摘录）。
- 入宫：`POST /api/v1/memories`，`category=worklog`（**capabilities 受控词表内**；自造值会被服务端静默归一化为 `knowledge`）。
- 幂等：卡片指纹（session+msg_id+原文）入 `.index.json`，重复跑不重复入库。
- `--dry-run` 不写任何东西。

`tests/test_archive_quality_v784.py` — 29 例契约测试（不依赖数据库/网络）

## REMOVED

无（`--skip-short` 保留旧行为开关）。

## 实现中实测踩到并修掉的坑（写在这里，别重犯）

1. **宽松阈值会污染记忆**：初始 `>=2 类信号` 在最近 3 场抽出 **66 张**卡。→ 默认改为「每场会话只取收尾汇报」(final 模式)，实测 3 张。
2. **`role='tool'` 的工具回显会被当成交付汇报**：工具输出里全是路径/哈希/数字。→ SQL 收紧为 `role='assistant'`。
3. **diff/日志噪声被当路径**：`/path/a.py\n+++ b/a.py` 整段被匹配。→ 路径正则排除反斜杠/加号/反引号，片段上限 `MAX_SIG_LEN=160`。
4. **汇报不在最后一句**：会话常以「好的，就这样吧」收尾。→ final 模式向前回看 `FINAL_LOOKBACK=3` 条。
5. **让位计数语义错**（迭代次数 4227 而非消息数）+ 净减量少算后缀 → 循环多跑。→ 改为集合计数 + 含后缀净减量。

## 不变量（回归护栏）

- 会话归档推送形态不变：`POST /api/v1/sessions/archive`，json body，四字段 `user_id/session_id/title/content`。
- `category` 只许取受控词表 10 类。
- 服务端代码零改动；本变更只影响"喂给记忆宫殿的内容质量"。

## 验证

```
$ .venv/bin/python -m pytest tests/test_archive_quality_v784.py -q
29 passed
$ .venv/bin/python -m pytest tests/ -q
228 passed, 6 skipped
```

生产链路端到端验证（真写入 + 回读）：

```
$ report_card.py --last 3 --push     → pushed: 3
$ GET /api/v1/memories?user_id=default&category=worklog&limit=5
  #20077 [汇报卡] 交付物路径: C:\Users\<user>\Desktop\…\公众号版_AI小镇第一批居民_双击看.html
               URL: https://your-site.example.com/news/example-page.html
```
→ 语义层从此可回答「上次交付了什么、在哪儿」。

真数据干跑（本机会话 `20260924_043847_cafcc2`，155 条消息）：

| 指标 | 旧版 | 新版 |
|---|---|---|
| 收尾汇报入档 | 前 2000 字 | **5,924 字全文** |
| 过程消息 | 每条 ≤2000 | 每条 ≤1200 |
| 工具证据 | 无 | `⟪工具: …⟫` 签名 |
| 入档总量 | 125,782 字符 | 99,041 字符（更少但更有价值） |

汇报卡实测（最近 3 场）：宽松阈值 **66 张**（会污染记忆）→ 默认 final 模式 **3 张**（每场 1 张）。

隐私门禁自检（`privacy.yml` 同款扫描）：域名 / 真实用户名 零输出。

## 发布门禁（未走）

按项目红线，以下动作**未执行**，等显式批准：`git tag v7.8.4` · push 公开仓库 · 部署到生产服务器。
发布顺序遵既有约定：**先部署验稳 → 才 tag/Release**（避免"文档写了、实际没发布"）。
