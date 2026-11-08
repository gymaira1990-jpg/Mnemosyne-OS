"""检索通道覆盖（2026-11-08 深度审计发现的系统性盲区）

发现的 bug：`_multi_kw`（C 通道）和 `_recent`（T 通道）里写死了

    AND m.content LIKE '[结果卡]%'

而库里 33,165 条未删除记忆中只有 3,622 条（11%）是这个形态
⇒ **29,543 条（89%）在关键词/时间通道里彻底搜不到**，其中包含全部 4,375 条蒸馏知识
（它们当时还缺向量，等于双重隐形）。

这两个测试直接打真库，锁住「非结果卡记忆也必须能被关键词通道取到」。
"""
import asyncio
import os

import pytest

ITEST_DSN = os.environ.get("MNEMOSYNE_ITEST_DSN", "postgresql:///mnemosyne_itest")
USER = "itest-kw"


def _run(coro):
    return asyncio.run(coro)


async def _connect():
    import asyncpg
    return await asyncpg.connect(ITEST_DSN)


@pytest.fixture(scope="module")
def seeded():
    async def prep():
        c = await _connect()
        try:
            await c.execute("DELETE FROM memories WHERE user_id = $1", USER)
            # 一条普通记忆（不是 [结果卡] 形态）
            await c.execute(
                "INSERT INTO memories (user_id, content, category) VALUES ($1,$2,'knowledge')",
                USER, "普通记忆：通道覆盖探针 KWP-2026 主题是审计")
            # 一条结果卡形态
            await c.execute(
                "INSERT INTO memories (user_id, content, category) VALUES ($1,$2,'knowledge')",
                USER, "[结果卡] 档号：K·IT·KW 题名：通道覆盖探针 摘要：卡片形态 KWP-2026")
        finally:
            await c.close()

    try:
        _run(prep())
    except Exception as e:  # pragma: no cover
        pytest.skip(f"测试库不可用: {e}")
    yield True


def _call(fn, *args, **kw):
    import asyncpg
    from api import memory_os

    async def go():
        pool = await asyncpg.create_pool(ITEST_DSN, min_size=1, max_size=2)
        try:
            memory_os.pool = pool
            return await fn(*args, **kw)
        finally:
            await pool.close()

    return _run(go())


def test_keyword_channel_finds_non_card_memory(seeded):
    """非结果卡形态的记忆必须能被关键词通道取到（原来被 LIKE '[结果卡]%' 挡掉）。"""
    from api.memory_os import _multi_kw
    rows = _call(_multi_kw, ["KWP-2026"], USER, 50)
    contents = " ".join(r.get("head") or "" for r in rows)
    assert "普通记忆" in contents, f"非结果卡记忆在 C 通道里消失了，实际取到 {len(rows)} 条"


def test_keyword_channel_still_prefers_cards_on_tie(seeded):
    """C 通道不许「按命中个数截窗口」，也不许再拿档号当相关性信号。

    2026-11-08 第二轮：`ORDER BY kw_hit DESC ... LIMIT 60/300` 仍然会把命中稀有锚点的记忆挡在池外
    （实测「TMT 的 L3 表缺哪个字段」—— 命中的是只因含「字段」二字的 SVG 卡）。
    现改为：一次正则粗筛 + 全量候选 + 调用方按 IDF 打分。
    """
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1] / "api" / "memory_os.py").read_text(encoding="utf-8")
    multi = src.split("async def _recent")[0]

    assert "ORDER BY kw_hit DESC" not in multi, \
        "C 通道不许再按命中个数截窗口：泛词卡片会把稀有锚点的真答案挤出去"
    assert "~*" in multi, "C 通道必须用一次正则粗筛（N 次 ILIKE 在中文语料上是 N 次全表扫描）"
    assert "hit_kws" in multi, "C 通道必须把命中了哪几个词带回去，交给 IDF 打分"
    # 注意：注释里会引用旧 SQL 原文做说明，所以只匹配真正的 WHERE 子句写法
    assert "AND m.content LIKE '[结果卡]%'" not in multi, \
        "C 通道不许再有『只认结果卡』的硬过滤"
    assert "base *= 0.75" not in src, \
        "不许再按「无档号」降权 —— 档号是元数据不是相关性信号，89% 的非卡片语料会先天少 25%"


def test_time_channel_has_no_card_only_filter(seeded):
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1] / "api" / "memory_os.py").read_text(encoding="utf-8")
    recent = src.split("async def _recent")[1].split("async def ")[0]
    assert "[结果卡]" not in recent, "时间通道同样不能只认结果卡形态"
