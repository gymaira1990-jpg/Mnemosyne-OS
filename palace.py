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

# 房间关键词 → 房间 (从内容嗅探) — v7.0.1 扩充, 提高归类准确率
ROOM_KEYWORDS = [
    ("proxy", ["xray", "代理", "proxy", "2081", "2082", "1080", "clash", "分流", "geosite"]),
    ("deploy", ["部署", "deploy", "发布", "rsync", "scp", "systemd", "重启", "升级"]),
    ("secret", ["密钥", "key", "token", "保险柜", "password", "pat", "凭证", "api_key"]),
    ("security", ["安全", "审计", "漏洞", "扫描", "权限", "ssh", "入侵", "加固"]),
    ("domain", ["域名", "domain", "dns", "解析", "cdn"]),
    ("repo", ["仓库", "repo", "github", "git", "commit", "push", "分支"]),
    ("cron", ["cron", "定时", "任务", "调度", "schedule"]),
    ("database", ["数据库", "postgres", "psql", "pg", "sqlite", "sql", "表"]),
    ("memory", ["记忆", "mnemosyne", "memory", "蒸馏", "tmt", "宫殿", "召回", "检索"]),
    ("server", ["服务器", "server", "gz", "hk", "云", "vps", "lighthouse", "腾讯云"]),
    ("design", ["设计", "定妆", "海报", "形象", "brand", "立绘", "娘化"]),
    ("skill", ["技能", "skill", "流程", "workflow", "sop"]),
    ("lesson", ["坑", "教训", "pitfall", "踩过", "注意", "报错", "失败"]),
    ("idea", ["灵感", "idea", "方向", "迭代", "规划", "roadmap", "设想"]),
    ("user", ["用户", "user", "偏好", "喜欢", "主人", "想要"]),
    ("content", ["内容", "文章", "公众号", "小红书", "文案", "视频"]),
    ("billing", ["余额", "充值", "账单", "billing", "费用", "价格", "额度"]),
    ("model", ["模型", "model", "llm", "deepseek", "豆包", "doubao", "ark", "prompt"]),
    ("backup", ["备份", "backup", "归档", "存档"]),
    ("workspace", ["工作区", "workspace", "箱子", "桌面", "文件"]),
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


# ── 三通道召唤 (中药柜亮灯) ──
async def summon(pool, query: str, user_id: str = "default", top_k: int = 5) -> dict:
    """三通道召回:
    ① 点名(精确): 档号/题名/标签 直命中
    ② 引导(范围): 分类树翼/房 缩小
    ③ 共鸣(语义): 向量相似兜底
    返回按通道分组的命中
    """
    result = {"query": query, "summon": [], "guide": [], "resonate": []}

    # ① 点名: 档号/题名/标签 ILIKE
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT m.id, m.content, c.archive_no, c.title, c.wing, c.room, c.tags, m.heat_score "
            "FROM memories m JOIN tome_cards c ON c.memory_id = m.id "
            "WHERE m.user_id=$1 AND m.is_deleted=FALSE AND "
            "(c.archive_no ILIKE '%'||$2||'%' OR c.title ILIKE '%'||$2||'%' OR $2 = ANY(c.tags) OR m.content ILIKE '%'||$2||'%') "
            "ORDER BY m.heat_score DESC NULLS LAST LIMIT $3",
            user_id, query, top_k)
        result["summon"] = [{"id": r["id"], "content": r["content"][:120], "archive_no": r["archive_no"],
                             "title": r["title"], "wing": r["wing"], "room": r["room"],
                             "tags": r["tags"], "heat": r["heat_score"]} for r in rows]

        # ② 引导: 分类树匹配 (query 含翼/房关键词)
        cls = classify(query, "")
        if cls["room"] != "unfiled":
            rows = await conn.fetch(
                "SELECT m.id, m.content, c.archive_no, c.title, c.wing, c.room, c.tags "
                "FROM memories m JOIN tome_cards c ON c.memory_id = m.id "
                "WHERE m.user_id=$1 AND m.is_deleted=FALSE AND c.room=$2 "
                "ORDER BY m.heat_score DESC NULLS LAST LIMIT $3",
                user_id, cls["room"], top_k)
            result["guide"] = [{"id": r["id"], "content": r["content"][:120], "archive_no": r["archive_no"],
                                "title": r["title"], "room": r["room"], "tags": r["tags"]} for r in rows]

    # ③ 共鸣: 向量检索 (需 embedding; 失败则跳过)
    try:
        from core.embedding import get_embedding_async
        vec = (await get_embedding_async([query]))[0]
        q_str = "[" + ",".join(str(x) for x in vec) + "]"
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT m.id, m.content, c.archive_no, c.title, c.room, c.tags, (m.embedding <=> $2::vector) AS dist "
                "FROM memories m JOIN tome_cards c ON c.memory_id = m.id "
                "WHERE m.user_id=$1 AND m.is_deleted=FALSE AND m.embedding IS NOT NULL "
                "ORDER BY dist LIMIT $3",
                user_id, q_str, top_k)
            result["resonate"] = [{"id": r["id"], "content": r["content"][:120], "archive_no": r["archive_no"],
                                   "title": r["title"], "room": r["room"], "tags": r["tags"],
                                   "dist": round(float(r["dist"]), 4)} for r in rows]
    except Exception:
        pass

    return result


# ── 卡片精炼 (资料室: 题名/摘要/标签 生成) ──
def refine_prompt(content: str) -> str:
    return f"""你是记忆宫殿的图书管理员。给一条记忆生成著录卡片。
要求:
1. 题名: 10字以内, 概括主题 (如 "GZ xray部署")
2. 摘要: 30字以内, 一句话要点
3. 标签: 2-4个, 用中括号逗号分隔 (如 [GZ][xray][部署])

记忆内容:
{content[:500]}

输出严格JSON: {{"title":"...","summary":"...","tags":["a","b"]}}"""


async def refine_cards(pool, limit: int = 20) -> dict:
    """批量精炼著录卡片 (LLM 生成题名/摘要/标签), 只处理 created_by='backfill' 的"""
    import json
    from core.llm import call_llm_json
    done, failed = 0, 0
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT memory_id, title, summary, content FROM tome_cards c "
            "JOIN memories m ON m.id = c.memory_id "
            "WHERE c.created_by='backfill' AND m.user_id='default' AND m.is_deleted=FALSE "
            "ORDER BY m.heat_score DESC NULLS LAST LIMIT $1", limit)
        for r in rows:
            try:
                res = call_llm_json(refine_prompt(r["content"] or ""))
                # json_mode 时 content 已是提取好的 JSON 字符串
                raw = res.get("content", "") if isinstance(res, dict) else ""
                if not raw:
                    failed += 1
                    continue
                parsed = json.loads(raw) if isinstance(raw, str) else raw
                if not isinstance(parsed, dict) or not parsed.get("title"):
                    failed += 1
                    continue
                await conn.execute(
                    "UPDATE tome_cards SET title=$1, summary=$2, tags=$3::text[], created_by='refined' "
                    "WHERE memory_id=$4",
                    str(parsed["title"])[:50], str(parsed.get("summary", ""))[:200],
                    [str(t)[:20] for t in parsed.get("tags", [])[:4]], r["memory_id"])
                done += 1
            except Exception:
                failed += 1
    return {"refined": done, "failed": failed}


# ── 资料室: 事实提取管道 (对话→facts→建档) ──
async def extract_facts_pipeline(pool, batch: int = 20) -> dict:
    """从 session/worklog 提取事实 → 入 memories(preference/knowledge) → 自动建档
    复用 tmt/factextract.py 逻辑, 幂等 (metadata fact_extracted 标记)
    """
    from tmt import factextract
    from tmt.distill import get_pool  # noqa: F401 (确保环境)
    processed, facts_created = 0, 0
    try:
        candidates = await factextract.find_candidates(pool, batch)
        for c in candidates:
            if factextract.is_skip(c["content"] or ""):
                continue
            facts, status = await factextract.extract_facts(c["content"] or "")
            if facts:
                for f in facts:
                    ftype = factextract.classify_fact(f)
                    nid = await factextract.insert_fact(pool, c["id"], c["category"] or "", f, ftype)
                    if nid:
                        facts_created += 1
                        # 新事实自动建档 (分类+档号+卡片) — 直接用 insert 返回的 id, 无竞态
                        cls = classify(f, ftype)
                        archive_no = f"F·{cls['room'].upper()}·{datetime.now().year}-{nid % 100000:05d}"
                        try:
                            async with pool.acquire() as conn:
                                await conn.execute(
                                    "UPDATE memories SET archive_no=$1 WHERE id=$2 AND (archive_no IS NULL OR archive_no='')",
                                    archive_no, nid)
                                await conn.execute(
                                    "INSERT INTO tome_cards (memory_id, title, summary, archive_no, wing, room, shelf, tags, retention, source_session, created_by) "
                                    "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'long','', 'fact') ON CONFLICT (memory_id) DO NOTHING",
                                    nid, f[:30], f[:120], archive_no, cls["wing"], cls["room"], cls["shelf"], [ftype])
                        except Exception:
                            pass
            # 标记已提取 (无论有无事实)
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE memories SET metadata = COALESCE(metadata,'{}'::jsonb) || '{\"fact_extracted\":true}'::jsonb "
                    "WHERE id=$1", c["id"])
            processed += 1
    except Exception as e:
        return {"processed": processed, "facts_created": facts_created, "error": str(e)[:200]}
    return {"processed": processed, "facts_created": facts_created}


# ── 永恒分级生命周期 ──
RETENTION_RULES = {
    "permanent": {"decay": 0.0, "keep_days": None},   # 永久: 不衰减, 不清理
    "long":      {"decay": 0.999, "keep_days": None},  # 长期: 极慢衰减, 不自动清
    "short":     {"decay": 0.98, "keep_days": 90},     # 短期: 快衰减, 90天自动撤架
}

async def apply_lifecycle(pool, user_id: str = "default") -> dict:
    """永恒分级: 按保管期限调整热度 + 短期过期自动软删
    返回: {expired: N, degraded: N}
    """
    import json
    expired, degraded = 0, 0
    async with pool.acquire() as conn:
        # 1. 短期: 超过 keep_days 自动软删 (撤架)
        rows = await conn.fetch(
            "SELECT c.memory_id, m.created_at FROM tome_cards c "
            "JOIN memories m ON m.id = c.memory_id "
            "WHERE c.retention='short' AND m.user_id=$1 AND m.is_deleted=FALSE",
            user_id)
        for r in rows:
            if r["created_at"] and (datetime.now() - r["created_at"]).days > RETENTION_RULES["short"]["keep_days"]:
                await conn.execute(
                    "UPDATE memories SET is_deleted=TRUE, forgotten_at=NOW() WHERE id=$1", r["memory_id"])
                expired += 1
        # 2. 永久/长期: 热度保护 (permanent 不衰减, 已由 decay=0 表达; 这里给永久卷热度下限)
        await conn.execute(
            "UPDATE memories SET heat_score = GREATEST(heat_score, 0.8) "
            "WHERE id IN (SELECT memory_id FROM tome_cards WHERE retention='permanent') "
            "AND user_id=$1 AND is_deleted=FALSE", user_id)
        degraded = await conn.fetchval(
            "SELECT count(*) FROM tome_cards WHERE retention='permanent'")
    return {"expired": expired, "permanent_protected": degraded}


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
