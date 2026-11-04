#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""seed_demo.py —— 塞几条示例记忆，让你 1 分钟内看到「存进去 → 搜出来」的效果

为什么有它：新人跑通服务后是空库，`recall` 返回空、stats 全是 0，很容易以为装坏了。
  这个脚本只做两件事：写 5 条真实形态的记忆（真调 embedding，不是假向量），再搜一次给你看。
  不会污染你的真实数据：写入的每条都带 metadata.demo=true，--clean 可以一键删掉。

用法：
    python3 scripts/seed_demo.py            # 写入 5 条示例记忆 + 跑一次检索演示
    python3 scripts/seed_demo.py --clean    # 删掉所有示例数据
    python3 scripts/seed_demo.py --user me  # 指定 user_id（默认 demo）
    make demo                               # 写 40 张「著录卡」（= --cards evals/demo_cards.jsonl）

🔴 关键区别（第一次装最容易踩）：
   5 条示例记忆是**裸记忆**，`/memory-os/recall` **不捞它们**（它只查 `content LIKE '[结果卡]%'`）。
   想验证四通道召回，要用 `--cards` 灌卡片 —— 或者直接 `make demo && make eval`。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEMO_ROWS = [
    ("worklog", "周三 15:00 跟客户开会，讨论合同第二版，记得带上报价单。"),
    ("preference", "我喜欢早上喝黑咖啡，不加糖；开会前不要安排需要动脑的活。"),
    ("ops", "内网的 PostgreSQL 跑在 127.0.0.1:5432，每天 03:00 自动备份到 /var/backups。"),
    ("project", "记忆库项目下一步要把检索延迟压到 200ms 以内，优先改关键词通道。"),
    ("reference", "长期有效的经验：写周报时先写结论，再写三条证据，最后写风险。"),
]


async def connect():
    import asyncpg

    return await asyncpg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=int(os.getenv("PGPORT", "5432")),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", ""),
        database=os.getenv("PGDATABASE", "mnemosyne"),
    )


def to_pg_vector(vec) -> str:
    return "[" + ",".join(f"{float(x):.6f}" for x in vec) + "]"


async def run(user: str, clean: bool, cards: str | None = None) -> int:
    conn = await connect()
    try:
        if clean:
            n = await conn.execute(
                "delete from memories where user_id=$1 and metadata->>'demo'='true'", user)
            print(f"已删除示例数据：{n}")
            return 0

        exist = await conn.fetchval(
            "select count(*) from memories where user_id=$1 and metadata->>'demo'='true'", user)
        if exist:
            print(f"已有 {exist} 条示例数据（user_id={user}）。要重来先跑 --clean")
            return 0

        # ── 卡片模式：写「著录卡」，能让 /memory-os/recall（四通道）捞到 ──
        if cards:
            path = pathlib.Path(cards)
            if not path.exists():
                print(f"❌ 找不到卡片文件 {path}")
                return 2
            items = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
            from core.embedding import get_embedding

            print(f"正在生成向量（真调 embedding，{len(items)} 张卡）…")
            vecs = get_embedding([c["content"] for c in items])
            for c, v in zip(items, vecs):
                v = v[2] if isinstance(v, tuple) else v
                m = re.search(r"档号：(K·[^\s]+)", c["content"])
                await conn.execute(
                    """insert into memories
                         (user_id, content, category, embedding, tier, heat_score, metadata, archive_no)
                       values ($1, $2, 'session', $3::vector, 'L2', 0.6, $4::jsonb, $5)""",
                    user, c["content"], to_pg_vector(v),
                    json.dumps({"demo": "true", "card": "true"}),
                    m.group(1) if m else None)
            total = await conn.fetchval(
                "select count(*) from memories where user_id=$1 and content like '[结果卡]%'", user)
            print(f"✅ 已写入 {len(items)} 张卡（user_id={user}，库里该用户共 {total} 张卡）")
            print("下一步：make eval    # 跑 12 道题，看 recall@10（E/C/T 与叠加 S 两组）")
            return 0

        from core.embedding import get_embedding  # 真调 embedding，和正式写入同一条链路

        print("正在生成向量（真调 embedding，5 条）…")
        res = get_embedding([r[1] for r in DEMO_ROWS])
        vecs = [(x[2] if isinstance(x, tuple) else x) for x in res]

        for (cat, content), vec in zip(DEMO_ROWS, vecs):
            await conn.execute(
                """insert into memories (user_id, content, category, embedding, tier, heat_score, metadata)
                   values ($1, $2, $3, $4::vector, 'L2', 0.5, $5::jsonb)""",
                user, content, cat, to_pg_vector(vec), json.dumps({"demo": "true"}))
        total = await conn.fetchval("select count(*) from memories where user_id=$1", user)
        print(f"✅ 已写入 {len(DEMO_ROWS)} 条示例记忆（user_id={user}，库里该用户共 {total} 条）")

        # 演示一次检索
        q = "客户开会要带什么"
        qv = get_embedding([q])[0]
        qv = qv[2] if isinstance(qv, tuple) else qv
        rows = await conn.fetch(
            """select content, category, round((1 - (embedding <=> $1::vector))::numeric, 3) as sim
               from memories where user_id=$2 and is_deleted=false and embedding is not null
               order by embedding <=> $1::vector limit 3""",
            to_pg_vector(qv), user)
        print(f'\n🔍 检索演示："{q}"')
        for r in rows:
            print(f"   [{r['sim']}] {r['category']}: {r['content'][:40]}")
        print("\n下一步：起服务后调用 POST /api/v1/memories/search 就能搜到这些内容")
        return 0
    finally:
        await conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="写入/清理示例记忆")
    ap.add_argument("--user", default="demo", help="user_id，默认 demo")
    ap.add_argument("--clean", action="store_true", help="删除示例数据")
    ap.add_argument("--cards", metavar="FILE",
                    help="从 JSONL 灌著录卡（每行需含 content 字段）；recall 只捞卡，想验证四通道就用这个")
    a = ap.parse_args()
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    try:
        return asyncio.run(run(a.user, a.clean, a.cards))
    except Exception as e:  # noqa: BLE001
        print(f"❌ 失败：{type(e).__name__}: {e}")
        print("   先跑 `python3 scripts/doctor.py` 看看环境缺什么。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
