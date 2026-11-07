# 自己验（Verification）

> 版本: v9.0.20
>
> 这份文档只有一个目的：**让「好不好」这件事有据可查，而不是靠猜。**
> 下面每条都给了命令和判据，跑完你会得到**你自己环境里的**数字 —— 那才有意义。

---

## 0. 三条命令

```bash
bash scripts/bootstrap.sh     # 幂等：建库 / 导 schema / 装依赖 / 自检
make demo                     # 灌 40 张演示卡（user_id=demo）
make eval                     # 跑 12 道中文题，看 recall@10
make eval-semantic            # 同上，叠加 S 语义通道（= 生产用的四通道）
```

清场：`python3 scripts/seed_demo.py --user demo --clean`（软删除，可恢复）

---

## 1. 我们实测的结果（2026-11-04）

**环境**：PostgreSQL 18 + pgvector 0.8.0，独立 demo 库，服务单实例
**数据**：40 张按 [CARD-SPEC.md](CARD-SPEC.md) 生成的演示卡，12 道中文问题，人工标注期望
**判据**：期望的关键词 / 数字 / 锚点是否出现在前 k 条里

| 组 | 通道 | k | 结果 |
|---|---|---|---|
| A | 只 E/C/T（`/memory-os/recall` 一次调用） | 10 | **11 / 12 = 92%** |
| B | E/C/T + S（客户端叠加语义后合并） | 10 | **12 / 12 = 100%** |
| C | E/C/T + S | 5 | **12 / 12 = 100%** |

原始输出在 `evals/`（`eval_ect.txt` / `eval_ects.txt` / `eval_ects5.txt`）。

### A 组唯一没命中的那题，说明通道为什么要四条

- 问题：**「海报用什么配色」**，期望命中 `FF9F43` / `墨黑`
- 语料：`客户要求海报走头版风，墨黑配暖橘 FF9F43。`
- 关键词通道只认「海报」，问题里的「配色」在正文里根本没出现 → **返回 0 条**
- 叠加语义通道 → **第 1 位命中**

**关键词通道跨不过近义改写，语义通道能。少一条，就少一类问题。**

---

## 2. 两个必踩的坑

### ① `/memory-os/recall` 只捞「卡」，不捞裸记忆

SQL 条件是 `content LIKE '[结果卡]%'`。直接 POST 一段普通文本再调 recall —— **返回 0 条，而且不报错**。
（我们第一次跑就是 0/12，查库才发现数据好好躺着，只是不会被这张网捞到。）

⇒ 这是设计：这套 API 服务的是**著录卡**。**要召回，先成卡。**
裸记忆用 `POST /api/v1/memories/search`（纯语义）查。

### ② S 语义通道在**客户端**，不在服务端那一次调用里

`/memory-os/recall` 一次只出 E/C/T（纯 SQL —— 同一请求里再调 embedding，超时就从「可测」变成「不可控」）。
S 由客户端取向量后与三路合并，四通道融合发生在客户端。上面 92% → 100% 的差距就是这条通道的价值。

---

## 3. 判据本身怎么验

评测脚本的判据（命中 / 位次 / 空结果）有离线自检，不联网：

```bash
make eval-selftest     # 或 python3 scripts/eval_recall.py --selftest
```

`make test` 会跑它 —— **判据错了，跑多少数据都没意义。**

---

## 4. 我们知道它还不够的地方

- 演示语料是**合成的 40 条**，题目与语料同源（同一人造语料、出题）⇒ **不能代表你的真实分布**
- 规模小，样本量不足以谈统计显著性
- 只测了**召回质量**；没测端到端延迟、并发、长时间运行稳定性
- 单机单用户：多租户与权限是 9.1 的事（现在 `user_id` 只是逻辑分组，谁连得上谁就能读）

README 里那句「两个评测集各 90%」是**第一方自测**，脚本在作者私有侧（标注指向真实记忆，无法脱敏）。
所以才需要这份文档：**判据给你，数字你自己量。**

---

## 5. 前置依赖：我们声明，不打包

| 需要什么 | 版本 | 谁负责 |
|---|---|---|
| PostgreSQL | 16+（实测 18） | **你** |
| pgvector 扩展 | 0.8.x | **你**（`CREATE EXTENSION vector;`） |
| Python | 3.11+ | **你** |
| embedding 端点 | 默认火山 ARK，或任意 OpenAI 兼容 | **你**（要 key） |

**明确不做**：不提供数据库镜像、不做 docker-compose 全家桶、不代装依赖。
数据库版本、备份策略、网络边界都是部署方自己的责任，替人打包等于把运维责任挪走一半。

---

## 6. 相关文件

| 文件 | 说明 |
|---|---|
| `evals/demo_cards.jsonl` | 40 张演示卡（全部通过 `scripts/card_check.py`） |
| `evals/demo_cases.jsonl` | 12 道问题 + 人工标注期望 |
| `scripts/eval_recall.py` | 评测器（`--semantic` 叠 S 通道，`--selftest` 验判据） |
| `scripts/seed_demo.py --cards` | 灌卡（recall 只认卡，见坑 ①） |
| `docs/CARD-SPEC.md` | 卡片规范 v1 |

---

## 7. 数字口径：README 里那两个数各自怎么算

对外写的「记忆总量」与「著录卡」是两个**不同口径**的数，必须按下面 SQL 复算才能对上。
口径不写清时，第三方拿 `tome_cards` 全表行数去比，会得出「差 10 倍 = 数字造假」的错误结论。

```sql
-- ① 记忆总量（README 的 Memories / 记忆总量）
SELECT count(*) FROM memories;

-- ② 著录卡 = 结果卡：标题带 [结果卡] 且必有 K· 档号（README 的 Catalog cards / 著录卡）
SELECT count(*) FROM tome_cards WHERE title LIKE '%结果卡%';

-- ③ tome_cards 全表（含汇报卡 / 问答卡 / 导入卡）—— 与 ② 不是一个东西
SELECT count(*) FROM tome_cards;

-- ④ 向量覆盖（分母用 ①）
SELECT count(*) FROM memories WHERE embedding IS NOT NULL;
```

**约定**：README 与 README_CN 的同一个指标必须同值、带快照日期、写清口径；
`python3 scripts/release_checks.py numbers-consistency` 会校验双语自洽与新鲜度，发版前必跑。
数字会随使用增长 —— **带日期的旧数字是历史，不带日期的旧数字是错话**。
