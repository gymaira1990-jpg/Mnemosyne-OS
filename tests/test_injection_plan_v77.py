"""v7.7.0 注入调度 — 纯函数测试 (不依赖 DB)

覆盖: ①RRF pid 空间一致性(向量用 id 而非 index, 防越界) ②状态权重排序 ③limits 硬校验
生产逻辑同源复制 (见 api/skills.py / api/injection.py)
"""
import sys
sys.path.insert(0, ".")
from wiki.wiki_bm25 import rrf_fuse


def rank_skills(rows, bm25_scores, top_k=3, state_weight=None):
    """复刻 api/skills.py 的 RRF+状态权重排序逻辑 (生产同源)"""
    state_weight = state_weight or {"active": 1.0, "stale": 0.85, "archived": 0.7}
    vec_ranked = [(r["id"], r["dist"]) for r in rows]
    fused = rrf_fuse(vec_ranked, bm25_scores) if (bm25_scores or vec_ranked) else []
    id2row = {r["id"]: r for r in rows}
    scored = []
    for pid, rrf in fused:
        r = id2row.get(pid)
        if not r:
            continue
        w = state_weight.get(r["state"], 1.0)
        scored.append((rrf * w, r))
    scored.sort(key=lambda x: -x[0])
    return [r["skill_name"] for _s, r in scored[:top_k]]


class TestRRFIdSpace:
    """P0 回归: BM25 通道 pid 是 DB id, 向量通道必须也是 DB id (不能是 index)"""

    def test_no_index_out_of_range(self):
        """BM25 命中的 skill_id 大于候选列表长度也不越界 (旧 bug: 用 index 会 IndexError)"""
        rows = [
            {"id": 1, "skill_name": "skill-a", "state": "active", "dist": 0.1},
            {"id": 2, "skill_name": "skill-b", "state": "active", "dist": 0.2},
        ]
        # BM25 命中 id=18 (不在向量候选前2, 但合法 DB id)
        bm25 = {18: 20.0, 1: 10.0}
        names = rank_skills(rows, bm25, top_k=3)
        # 18 无对应 row → 跳过, 1 在 → 出现
        assert "skill-a" in names
        assert len(names) >= 1

    def test_pid_alignment(self):
        """同 id 双通道融合: BM25 高分 id 排前"""
        rows = [
            {"id": 5, "skill_name": "hot", "state": "active", "dist": 0.05},
            {"id": 9, "skill_name": "cold", "state": "active", "dist": 0.3},
        ]
        bm25 = {5: 50.0, 9: 1.0}
        names = rank_skills(rows, bm25, top_k=2)
        assert names[0] == "hot"


class TestStateWeight:
    def test_active_beats_archived(self):
        """同 rrf 分, active 排 archived 前 (权重 1.0 vs 0.7)"""
        rows = [
            {"id": 1, "skill_name": "archived-skill", "state": "archived", "dist": 0.1},
            {"id": 2, "skill_name": "active-skill", "state": "active", "dist": 0.11},
        ]
        names = rank_skills(rows, {}, top_k=2)
        # active 虽距离稍远但权重高 → 排前
        assert names.index("active-skill") < names.index("archived-skill")

    def test_archived_still_visible(self):
        """archived 只降权不屏蔽 (优化≠遗忘)"""
        rows = [
            {"id": 1, "skill_name": "only-archived", "state": "archived", "dist": 0.1},
        ]
        names = rank_skills(rows, {}, top_k=5)
        assert "only-archived" in names


class TestHardCaps:
    def test_cap_clamp(self):
        """limits 超上限截断到 HARD_CAPS"""
        def clamp(limits, hard=None):
            hard = hard or {"skills": 8, "memories": 10, "hooks": 10}
            return {k: max(1, min(int(limits.get(k, 3)), hard[k])) for k in hard}
        caps = clamp({"skills": 999, "memories": 999, "hooks": 999})
        assert caps == {"skills": 8, "memories": 10, "hooks": 10}
        caps2 = clamp({"skills": 0})
        assert caps2["skills"] == 1  # 下限 1
