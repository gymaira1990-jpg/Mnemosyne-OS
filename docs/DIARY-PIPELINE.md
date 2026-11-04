# 日记生产线：让「每天一篇」自己跑起来

> 目标：服务器自己每天写一篇日记、自己渲染成网页，**你的电脑关机也不影响**。
> 前置：已完成 [`INSTALL.md`](../INSTALL.md) 部署，`/api/v1/memory-os/diary` 能返回数据。
> 本文只讲「怎么排班、数据从哪来、坏了怎么办」；登录墙见 [`DEPLOY-PRIVATE.md`](DEPLOY-PRIVATE.md)。

> ⚠️ **先说实话：本文里的 `diary_daily.py`、`jobs/export_diary_data.py` 不在本仓库。**
> 它们是作者本机生产的实现（依赖真实语料、写入策略与私有调度）。本文交付的是**数据契约 + 调度形态 + 故障处理**，
> 你可以照着自己写一个 —— 判据在下面每节都写着。
> 仓库里**能直接跑的**是：`integrations/card-builder/`（对话→卡）与 `scripts/seed_demo.py --cards`（灌卡）、
> `scripts/eval_recall.py`（召回评测）。

## 1. 数据流（记住这一张图）

```
① 日常对话 → 写入记忆（category=session 的「结果卡」）
        ↓
② 每天 fixed 时间：读「昨天的结果卡」→ 大模型写成 100~180 字日记 → 写回记忆库
        ↓  （日记卡：content 以 “[每日日记] 日期：YYYY-MM-DD” 开头）
③ 导出：把日记/情感卡/流水打成 data.json（给前端用）
        ↓
④ 渲染：把 data.json + 会话骨架 → 一个自包含 HTML（或直接给前端读 data.json）
```

**真源只有一个：PostgreSQL 里的记忆卡。**
不要另建一份 Markdown 当真源——两边一旦漂移，你用旧的那份渲染一次，就会把完整版覆盖成残缺版。

## 2. 排班（时间可改，顺序不能反）

| 时间 | 作业 | 依赖 | 失败会怎样 |
|---|---|---|---|
| 03:20 | 精修卡片（可选） | — | 只是质量差一点 |
| **04:30** | **写昨天的日记** | 昨天的结果卡已入库 | 昨天没日记，次日可补跑 |
| **05:10** | **导出 data.json** | 04:30 已写完 | 前端看到的是旧数据 |
| **05:25** | **渲染页面** | 05:10 已导出 | 线上还是上一版（**不报错、只是旧**） |

用 `crontab -e` 加（下面是示例：`/opt/mnemosyne` 换成你自己的路径，`$HOME/logs` 必须是**该用户可写**目录）：

```cron
30 4 * * * cd /opt/mnemosyne && set -a && . .env && set +a && ./venv/bin/python3 diary_daily.py >> $HOME/logs/diary_daily.log 2>&1
10 5 * * * cd /opt/mnemosyne && ./venv/bin/python3 jobs/export_diary_data.py >> $HOME/logs/export_diary_data.log 2>&1
25 5 * * * bash /opt/mnemosyne/render_book.sh >> $HOME/logs/render_book.log 2>&1
```

> ⚠️ **日志路径必须是当前用户可写的目录。**
> 实测坑：把日志重定向到 `/var/log/`，普通用户打不开文件 → shell **整条命令都不执行**，而且 **crontab 不报错**。
> 排查口诀：`cron` 没效果 → 先看目标日志文件有没有被创建。

## 3. 三条设计原则（照抄也不会写歪）

1. **没有对话的日子也要写**
   读不到当天的结果卡时，写一条 40~80 字的「今天没人来」的短文（例如“屋子安静，我把昨天的事又理了一遍”），
   **绝不编造当天没发生的事**。日期过去了，日子本身也是一段记录。
2. **幂等判据要看「卡里的日期」，不是「入库时间」**
   反例：用 `created_at` 判断「今天写过没有」——批量回灌历史日记那天，所有卡都是同一天入库，
   于是当天的日记被判「已写过」永久跳过，而别的日子被重复写。
   正解：`content LIKE '[每日日记] 日期：' || $1 || '%'`（注意末尾的 `%`，漏了会退化成全等匹配）。
3. **渲染要有硬闸**
   产物小于某个体积（例如 `<300KB`）就**拒绝替换线上**，保留上一版。
   宁可旧一天，也不要把半成品顶上去。

## 4. render_book.sh（可直接用的骨架）

```bash
#!/bin/bash
set -euo pipefail
APP=/opt/mnemosyne
OUT=/tmp/book_$$.html
STATE_GZ=$(ls -1t /opt/backup/state-db/state-*.db.gz 2>/dev/null | head -1)   # 没有就跳过骨架
[ -n "$STATE_GZ" ] && gunzip -c "$STATE_GZ" > /tmp/state_$$.db

cd "$APP"
DIARY_STATE_DB="${STATE_DB:-}" \
DIARY_DAYS_JSON=/var/www/private/diary/data.json \
python3 render_book.py --out "$OUT"

SIZE=$(stat -c%s "$OUT")
if [ "$SIZE" -lt 300000 ]; then
  echo "产物只有 $SIZE 字节，放弃替换"; rm -f "$OUT"; exit 1
fi
install -o www-data -g www-data -m 644 "$OUT" /var/www/private/diary/index.html
rm -f "$OUT"
```

> 渲染器的输入统一走**环境变量**（`DIARY_STATE_DB` / `DIARY_DAYS_JSON` / `DIARY_FONTS`）。
> 谁把它们写死回 `$HOME`，在服务器上就会静默用错数据源，而且不报错。

## 5. 自检（三行命令，任何一天都能跑）

```bash
# ① 今天/昨天有没有日记卡（数字 >0 才算写过）
psql -d mnemosyne -c "select count(*) from memories where content like '[每日日记] 日期：%' and not is_deleted;"

# ② 三个作业的日志是否有今天的记录
ls -l $HOME/logs/{diary_daily,export_diary_data,render_book}.log

# ③ 线上产物是否是新的
ls -l /var/www/private/diary/index.html
```

## 6. 一句话总结

**排班在服务器、真源在数据库、兜底是「宁旧不烂」。** 做到这三点，你关机一周回来，日记还是齐的。
