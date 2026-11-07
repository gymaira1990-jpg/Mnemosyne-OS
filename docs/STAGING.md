# 预发布环境（staging）· 所有项目标配

> 主人 2026-11-08 定：**「所有的项目都必须要有这个东西」** —— 本地改完直接上生产等于没有防线。
> 本文是 Mnemosyne 的落地实例；其他项目照抄结构，换目录/端口/库名即可。

## 一、为什么必须有

本地测试通过 ≠ 生产能跑。差在四处，且都只有真环境才暴露：

| 差异 | 后果（本项目的实例） |
|---|---|
| 真数据库 + 真数据 | `memory_labels` 只在 migration 里、schema 漏了 → 从零建库缺表，测试被 skip 成「绿」 |
| 真依赖与版本 | `pg_dump` 出来的 schema 在 PG16 导不进（`transaction_timeout`）→ CI 才红 |
| 真密钥与配置 | 摘要路径取不到向量 → 每天 55 条知识在语义检索里隐身（3000+ 条才被发现） |
| 真进程模型 | `ssh` 不可用、端口错、多 worker 竞争 —— 冒烟在错误宿主上跑会报「假红」 |

⇒ **预发布就是把这四处提前一次撞完，而不是让用户撞。**

## 二、本项目的预发布（GZ 同机隔离）

| 维度 | 生产 | 预发布 |
|---|---|---|
| 目录 | `/opt/mnemosyne` | `/opt/mnemosyne-staging` |
| 端口 | `127.0.0.1:8010` | `127.0.0.1:8020` |
| 数据库 | `mnemosyne` | `mnemosyne_staging`（生产克隆） |
| systemd | `mnemosyne` | `mnemosyne-staging` |
| 隧道 | WSL `127.0.0.1:18010` → 8010 | WSL `127.0.0.1:18020` → 8020 |
| 对外 | 不直接暴露（走隧道） | **绝不暴露** |
| venv | `/opt/mnemosyne/venv` | `/opt/mnemosyne-staging/venv`（独立，互不影响依赖） |
| `.env` | 生产密钥 | 同一批密钥 + `PGDATABASE/MNEMOSYNE_PORT` 覆盖 |

**隔离证明（必须能当场演示，不许只写在文档里）**

```bash
# 往 staging 写一条探针
curl -s -X POST http://127.0.0.1:8020/api/v1/memories \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"staging-probe","content":"隔离探针","category":"temp"}'
# staging 库应为 1，生产库必须为 0
ssh gz "sudo -u postgres psql -d mnemosyne_staging -tAc \"select count(*) from memories where user_id='staging-probe'\""
ssh gz "sudo -u postgres psql -d mnemosyne        -tAc \"select count(*) from memories where user_id='staging-probe'\""
```

2026-11-08 实测结果：`staging=1 / 生产=0` ✅

## 三、流程（缺一步就不许上生产）

```
本地改代码
  → make test / lint / 反证            （本地门禁，全绿）
  → bash scripts/deploy_staging.sh     （部署 staging + 冒烟 6/6）
  → 人工看一眼（关键功能/关键数据）
  → 部署生产（代码先上，版本号后置）
  → 生产冒烟（MEMOS_DB=mnemosyne python3 scripts/prod_smoke.py）
  → 阶段目标全绿 + 主人确认 → 才 tag/Release
```

`deploy_staging.sh` 自带三条守卫：工作区必须干净（可追溯的提交）、服务必须起来、冒烟必须 6/6。
任何一条不过就非 0 退出 —— **脚本比记性可靠**。

## 四、判据（怎么算「预发布通过」）

| # | 判据 | 命令 |
|---|---|---|
| 1 | 全量测试 0 失败 0 跳过 | `make test` |
| 2 | 冒烟 6/6，且查的是 staging 库 | `MEMOS_DB=mnemosyne_staging python3 scripts/prod_smoke.py http://127.0.0.1:18020` |
| 3 | 隔离成立：staging 写不进生产 | 上面那条探针（生产库必须 0） |
| 4 | 服务自报版本与代码一致 | `curl -s http://127.0.0.1:18020/api/v1/capabilities` |

## 五、已知边界（不粉饰）

- **数据是快照**：staging 库是某次全量克隆，不含之后的生产增量。验「历史数据损坏类」问题会失真，需要时重克隆。
- **同机部署**：共享 CPU/内存/磁盘。压测类问题不能在 staging 定论。
- **密钥相同**：staging 会真的调外部 API（豆包/DeepSeek），会产生少量费用。
- **不接自动部署**：故意保留人工关卡（主人定的减负原则：不要一动就加自动化）。

## 六、其他项目怎么套

把三件事换掉就能复用：目录（`/opt/<项目>-staging`）、端口（+10 偏移）、数据库（`<db>_staging`），
其余照抄：独立 venv、独立 systemd unit、只监听 127.0.0.1、`deploy_staging.sh` 守卫、冒烟判据。
