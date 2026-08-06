#!/usr/bin/env python3
"""palace.py — 魔法记忆宫殿核心模块 v7.0
设计: 记忆宫殿法空间编码(翼/房间/书架/书卷) + 档案学著录(档号)
功能:
  1. 分类树: 翼/房间/书架 定义 + 归类
  2. 档号生成: K·NET·PROXY·2026-0007
  3. 存量归类: 按 category/内容 自动分类
  4. 著录卡片: 题名/摘要/标签/保管期限 (tome_cards)
  5. 生命周期: 永久/长期/短期 分级
"""
import os
import sys
import re
import json
from datetime import datetime

# ── 翼 (Wing) 定义 — 对标中图法大类, 贴合个人知识体系 ──
WINGS = {
    "K": {"name": "知识", "rooms": ["arch", "memory", "ai", "tools"]},
    "N": {"name": "网络", "rooms": ["proxy", "domain", "dns", "server"]},
    "D": {"name": "开发", "rooms": ["repo", "deploy", "code", "database"]},
    "O": {"name": "运维", "rooms": ["ops", "cron", "monitor", "backup"]},
    "A": {"name": "资产", "rooms": ["secret", "key", "account", "vault"]},
    "P": {"name": "人物", "rooms": ["user", "ai", "contact", "org"]},
    "I": {"name": "灵感", "rooms": ["idea", "design", "brand", "content"]},
    "S": {"name": "技能", "rooms": ["skill", "workflow", "procedure", "lesson"]},
    "M": {"name": "元", "rooms": ["meta", "config", "roadmap", "decision"]},
}

# 大类 → 翼 映射 (从现有 category)
CATEGORY_TO_WING = {
    "knowledge": "K", "reference": "K", "wiki": "K",
    "session": "M", "worklog": "O", "chat": "M",
    "preference": "P", "ops": "O", "pitfall": "S",
    "deploy": "D", "fact": "K",
}

# 房间关键词 → 房间 (从内容嗅探)
ROOM_KEYWORDS = [
    ("proxy", ["xray", "代理", "proxy", "2081", "clash"]),
    ("deploy", ["部署", "deploy", "发布", "rsync", "scp"]),
    ("secret", ["密钥", "key", "token", "保险柜", "password"]),
    ("domain", ["域名", "domain", "dns", "解析"]),
    ("repo", ["仓库", "repo", "github", "git"]),
    ("cron", ["cron", "定时", "任务"]),
    ("database", ["数据库", "postgres", "psql", "pg"]),
    ("memory", ["记忆", "mnemosyne", "memory", "蒸馏"]),
    ("server", ["服务器", "server", "gz", "hk", "云"]),
    ("design", ["设计", "定妆", "海报", "形象", "brand"]),
    ("skill", ["技能", "skill", "流程", "workflow"]),
    ("lesson", ["坑", "教训", "pitfall", "踩过", "注意"]),
    ("idea", ["灵感", "idea", "方向", "迭代"]),
    ("user", ["用户", "user", "偏好", "喜欢"]),
]


def classify(content: str, category: str = "") -> dict:
    """对一条记忆做分类: 返回 {wing, room, shelf}"""
    # 1. 翼: 优先从 category 映射
    wing = CATEGORY_TO_WING.get(category, "")
    # 2. 房间: 从内容关键词嗅探
    room = ""
    text = (content or "").lower()
    for r, kws in ROOM_KEYWORDS:
        if any(k in text for k in kws):
            room = r
            break
    # 3. 兜底: 无映射则入知识翼·未归类
    if not wing:
        wing = "K"
    if not room:
        room = "unfiled"
    # 4. shelf: 从标签/关键词生成 (简单版: 取第一个房间关键词)
    shelf = ""
    return {"wing": wing, "room": room, "shelf": shelf}


def gen_archive_no(wing: str, room: str, shelf: str, year: int = 0, seq: int = 0) -> str:
    """生成档号: K·NET·PROXY·2026-0007"""
    if not year:
        year = datetime.now().year
    return f"{wing}·{room.upper()}·{shelf.upper() + '·' if shelf else ''}{year}-{seq:04d}"


def build_taxonomy_table_sql() -> str:
    return """
CREATE TABLE IF NOT EXISTS archive_taxonomy (
    id SERIAL PRIMARY KEY,
    wing TEXT NOT NULL,
    room TEXT NOT NULL,
    shelf TEXT DEFAULT '',
    name TEXT DEFAULT '',
    UNIQUE(wing, room, shelf)
);
"""


def add_archive_no_column_sql() -> str:
    return """
ALTER TABLE memories ADD COLUMN IF NOT EXISTS archive_no TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_archive_no ON memories(archive_no) WHERE archive_no IS NOT NULL;
"""


def build_tome_cards_sql() -> str:
    return """
CREATE TABLE IF NOT EXISTS tome_cards (
    memory_id BIGINT PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    summary TEXT DEFAULT '',
    archive_no TEXT UNIQUE,
    wing TEXT, room TEXT, shelf TEXT,
    tags TEXT[] DEFAULT '{}',
    retention TEXT DEFAULT 'long',
    source_session TEXT DEFAULT '',
    created_by TEXT DEFAULT 'auto',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tome_wing_room ON tome_cards(wing, room);
CREATE INDEX IF NOT EXISTS idx_tome_tags ON tome_cards USING GIN(tags);
"""


def build_tome_links_sql() -> str:
    return """
CREATE TABLE IF NOT EXISTS tome_links (
    id SERIAL PRIMARY KEY,
    from_memory BIGINT REFERENCES memories(id) ON DELETE CASCADE,
    to_memory BIGINT REFERENCES memories(id) ON DELETE CASCADE,
    rel TEXT DEFAULT 'related',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
"""


async def init_palace(pool) -> dict:
    """宫殿初始化: 建表 + 存量记忆自动归类建档 (幂等, 可重复跑)
    返回: {tables: [...], classified: N, cards: N}
    """
    import asyncpg
    result = {"tables": [], "classified": 0, "cards": 0}
    async with pool.acquire() as conn:
        # 1. 建表
        for name, sql in [
            ("archive_taxonomy", build_taxonomy_table_sql()),
            ("archive_no_col", add_archive_no_column_sql()),
            ("tome_cards", build_tome_cards_sql()),
            ("tome_links", build_tome_links_sql()),
        ]:
            try:
                await conn.execute(sql)
                result["tables"].append(name)
            except Exception as e:
                result["tables"].append(f"{name}(err:{e})")

        # 2. 存量归类: 无档号的记忆 → 分类 + 生成档号 + 建卡片
        rows = await conn.fetch(
            "SELECT id, content, category FROM memories "
            "WHERE user_id=$1 AND is_deleted=FALSE AND (archive_no IS NULL OR archive_no='') "
            "ORDER BY id DESC LIMIT 500",
            "default"
        )
        for r in rows:
            cls = classify(r["content"] or "", r["category"] or "")
            # 生成档号: 翼·房·年-流水 (用 id 作流水, 保证唯一)
            archive_no = f"{cls['wing']}·{cls['room'].upper()}·{datetime.now().year}-{r['id']:04d}"
            try:
                await conn.execute(
                    "UPDATE memories SET archive_no=$1 WHERE id=$2 AND archive_no IS NULL",
                    archive_no, r["id"])
                # 著录卡片
                title = (r["content"] or "")[:30].replace("\n", " ")
                summary = (r["content"] or "")[:120].replace("\n", " ")
                await conn.execute(
                    "INSERT INTO tome_cards (memory_id, title, summary, archive_no, wing, room, shelf, tags, retention, source_session, created_by) "
                    "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'long','', 'backfill') "
                    "ON CONFLICT (memory_id) DO NOTHING",
                    r["id"], title, summary, archive_no, cls["wing"], cls["room"], cls["shelf"], [r["category"] or "unfiled"])
                result["classified"] += 1
                result["cards"] += 1
            except Exception:
                pass
    return result


if __name__ == "__main__":
    # 自测
    tests = [
        ("在GZ部署xray代理，2081端口，systemd服务", "ops"),
        ("用户喜欢红果短剧风格的AI美女图", "preference"),
        ("密钥在保险柜GITHUB/KEY.txt，line3细粒度PAT", "ops"),
        ("mnemosyne蒸馏链修复，双底座DeepSeek", "worklog"),
    ]
    print("=== 分类自测 ===")
    for content, cat in tests:
        r = classify(content, cat)
        print(f"  [{cat}] {content[:30]}... → {r}")
