#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""doctor.py —— 部署前置自检：缺什么、怎么补，一次说清

为什么有这个脚本（2026-11-04，以「外人 clone 能不能自己部署」为标准做的演练结论）：
  新人最容易卡的不是代码，而是环境：PostgreSQL 连不上、pgvector 没装、.env 没生效、
  数据库结构导了个不完整的版本。这些失败的报错信息都指不到根因，人就走了。
  所以把「能不能跑」拆成一条条可执行检查，缺哪条直接给补的命令。

用法：
    python3 scripts/doctor.py          # 基础检查（不花钱、不调模型）
    python3 scripts/doctor.py --full   # 额外真调一次 embedding（会消耗极小额度）

退出码：0 = 全部通过（可能有提醒）；1 = 有硬失败，跑不起来。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import pathlib
import socket
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OK, WARN, FAIL = "✅", "⚠️ ", "❌"

fails: list[str] = []
warns: list[str] = []


def ok(msg: str) -> None:
    print(f"  {OK} {msg}")


def warn(msg: str, how: str) -> None:
    print(f"  {WARN}{msg}")
    print(f"      → {how}")
    warns.append(msg)


def bad(msg: str, how: str) -> None:
    print(f"  {FAIL} {msg}")
    print(f"      → {how}")
    fails.append(msg)


# ── 1. Python ──
def check_python() -> None:
    print("\n[1/8] Python 运行时")
    v = sys.version_info
    if v >= (3, 11):
        ok(f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        bad(f"Python {v.major}.{v.minor} 太旧", "需要 3.11+（推荐 3.11 / 3.12）")


# ── 2. 依赖 ──
def check_deps() -> None:
    print("\n[2/8] Python 依赖")
    missing = []
    for mod in ("fastapi", "uvicorn", "asyncpg", "dotenv", "pydantic", "numpy"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        bad(f"缺少依赖: {', '.join(missing)}", "pip install -r requirements.txt")
    else:
        ok("核心依赖齐全（fastapi / uvicorn / asyncpg / dotenv / pydantic / numpy）")


# ── 3. .env ──
def check_env_file() -> None:
    print("\n[3/8] 配置文件 .env")
    envf = ROOT / ".env"
    if not envf.exists():
        bad("项目根目录没有 .env", "cp .env.template .env，然后填进你的 key 与数据库口令")
        return
    ok(".env 存在")
    # .env 是否真的被读进来了（9.0.5 之前这里是空的：全仓库没有 load_dotenv）
    if os.getenv("PGDATABASE"):
        ok(f".env 已生效（PGDATABASE={os.getenv('PGDATABASE')}）")
    else:
        bad(".env 存在但配置没被读进来", "确认 config.py 里 load_dotenv() 存在；或 source .env 后重跑")


# ── 4. 数据库连接 ──
async def check_db() -> bool:
    print("\n[4/8] PostgreSQL 连接")
    try:
        import asyncpg
    except ImportError:
        bad("asyncpg 未安装，无法检查数据库", "pip install -r requirements.txt")
        return False
    host = os.getenv("PGHOST", "127.0.0.1")
    port = os.getenv("PGPORT", "5432")
    user = os.getenv("PGUSER", "postgres")
    db = os.getenv("PGDATABASE", "mnemosyne")
    pwd = os.getenv("PGPASSWORD", "")
    try:
        conn = await asyncpg.connect(host=host, port=int(port), user=user, password=pwd, database=db, timeout=5)
    except Exception as e:  # noqa: BLE001 —— 连接失败原因很多，原样展示最有信息量
        bad(f"连不上 {user}@{host}:{port}/{db}", f"{type(e).__name__}: {e}")
        print("      → 确认 PostgreSQL 已启动：sudo systemctl status postgresql")
        print("      → 确认库已建：sudo -u postgres psql -c '\\l'")
        return False
    ok(f"已连接 {user}@{host}:{port}/{db}")
    try:
        # 5. 扩展
        print("\n[5/8] 数据库扩展")
        exts = {r["extname"]: r["extversion"] for r in await conn.fetch(
            "select extname, extversion from pg_extension")}
        if "vector" in exts:
            ok(f"pgvector {exts['vector']}")
        else:
            bad("缺少 pgvector 扩展", "sudo -u postgres psql -d <库名> -c 'CREATE EXTENSION vector;'")
        if "pg_trgm" in exts:
            ok(f"pg_trgm {exts['pg_trgm']}")
        else:
            warn("缺少 pg_trgm（关键词模糊匹配会退化）",
                 "sudo -u postgres psql -d <库名> -c 'CREATE EXTENSION pg_trgm;'")
        if "age" in exts:
            warn("装了 Apache AGE，但 v7.8 起已不需要", "可以留着，也可以 DROP EXTENSION age CASCADE")

        # 6. 表结构完整性
        print("\n[6/8] 数据库结构（schema.sql 是否导全）")
        n_tables = await conn.fetchval(
            "select count(*) from information_schema.tables where table_schema='public'")
        need_tables = 23
        if n_tables >= need_tables:
            ok(f"{n_tables} 张表")
        elif n_tables == 0:
            bad("表是空的，schema 没导", "sudo -u postgres psql -d <库名> -f docs/schema.sql")
        else:
            bad(f"只有 {n_tables} 张表（应为 {need_tables}+）",
                "重新导入 docs/schema.sql（9.0.5 起的版本）")
        # 关键唯一索引：缺了解析会让「存第一条记忆」直接 500
        idx = await conn.fetch(
            "select indexname from pg_indexes where tablename='memories' and indexdef ilike '%unique%'")
        names = {r["indexname"] for r in idx}
        if "dedup_fingerprint_key" in names:
            ok("关键唯一索引 dedup_fingerprint_key 存在")
        else:
            bad("缺 dedup_fingerprint_key 唯一索引",
                "这是旧版 schema.sql 的已知缺陷（9.0.5 已修）：重新导入 docs/schema.sql")
    finally:
        await conn.close()
    return True


# ── 7. 模型后端 ──
def check_models(full: bool) -> None:
    print("\n[7/8] 模型后端（Embedding 是硬需求）")
    ark = bool(os.getenv("ARK_API_KEY"))
    oai = bool(os.getenv("OPENAI_API_KEY"))
    ds = bool(os.getenv("DEEPSEEK_API_KEY"))
    backend = (os.getenv("MODEL_BACKEND") or "ark").lower()
    if backend == "openai":
        if oai:
            ok("MODEL_BACKEND=openai，OPENAI_API_KEY 已配置")
        else:
            bad("MODEL_BACKEND=openai 但没有 OPENAI_API_KEY", "在 .env 填入 OPENAI_API_KEY")
    else:
        if ark:
            ok("ARK_API_KEY 已配置（向量化默认走火山引擎）")
        else:
            bad("没有 ARK_API_KEY，向量化无法工作", "在 .env 填 ARK_API_KEY，或改 MODEL_BACKEND=openai")
    if ds:
        ok("DEEPSEEK_API_KEY 已配置（蒸馏/审计可用）")
    else:
        warn("没有 DEEPSEEK_API_KEY（可选，只影响蒸馏与审计）", "需要时在 .env 补上")

    if full:
        print("  … 正在真调一次 embedding（--full）")
        try:
            sys.path.insert(0, str(ROOT))
            from core.embedding import get_embedding  # type: ignore
            res = get_embedding(["doctor 自检"])
            first = res[0]
            vec = first[2] if isinstance(first, tuple) else first
            dim = len(vec) if hasattr(vec, "__len__") else 0
            if dim:
                ok(f"Embedding 调用成功，维度 {dim}")
            else:
                bad("Embedding 返回异常", "看日志里的 HTTP 状态；常见是 key 无效或额度用尽")
        except Exception as e:  # noqa: BLE001
            bad(f"Embedding 调用失败: {type(e).__name__}: {e}",
                "检查 ARK_API_KEY 是否有效、是否开通 doubao-embedding 模型")


# ── 8. 端口 ──
def check_port() -> None:
    print("\n[8/8] 服务端口")
    port = int(os.getenv("MNEMOSYNE_PORT", "8010"))
    host = os.getenv("MNEMOSYNE_HOST", "127.0.0.1")
    s = socket.socket()
    s.settimeout(1)
    try:
        s.bind((host, port))
        ok(f"{host}:{port} 可用")
    except OSError:
        warn(f"{host}:{port} 已被占用",
             "改 .env 里的 MNEMOSYNE_PORT，或先停掉占用它的进程（lsof -i :%d）" % port)
    finally:
        s.close()


async def main_async(full: bool) -> int:
    print("Mnemosyne OS · 部署自检（doctor）")
    print(f"仓库版本: {(ROOT / 'VERSION').read_text().strip() if (ROOT / 'VERSION').exists() else '未知'}")
    check_python()
    check_deps()
    check_env_file()
    if await check_db():
        pass
    check_models(full)
    check_port()

    print("\n" + "─" * 46)
    if fails:
        print(f"结果：{len(fails)} 项必须修 / {len(warns)} 项提醒")
        for f in fails:
            print(f"  {FAIL} {f}")
        print("\n修完再跑一次 `python3 scripts/doctor.py`。")
        return 1
    print(f"结果：全部通过 ｜ {len(warns)} 项提醒")
    print("下一步：python3 main.py   → 打开 http://127.0.0.1:%s/" % os.getenv("MNEMOSYNE_PORT", "8010"))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Mnemosyne OS 部署前置自检")
    ap.add_argument("--full", action="store_true", help="额外真调一次 embedding（会消耗极小额度）")
    a = ap.parse_args()
    # 让 .env 生效（与 config.py 同一套逻辑，保证这里看到的就是服务看到的）
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    return asyncio.run(main_async(a.full))


if __name__ == "__main__":
    sys.exit(main())
