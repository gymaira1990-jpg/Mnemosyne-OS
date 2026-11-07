"""三段式采样的判定逻辑（2026-11-07）

判据必须是**可计算的**，不能靠模型「感觉上下文够不够」：
    前段最高分 / 前段是否带档号 / 当前会话轮数 —— 三项都是数出来的。
这里只测纯函数 verdict()，不联网、不读库。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.context_pack import verdict  # noqa: E402


def _prior(score=60.0, with_no=3):
    return {"top_score": score, "with_no": with_no}


def _sess(turns=20):
    return {"turns": turns}


def test_sufficient_when_all_signals_good():
    v = verdict(_prior(), _sess(), min_score=25, min_turns=4)
    assert v["sufficient"] is True and v["gaps"] == []


def test_low_prior_score_flags_insufficient():
    v = verdict(_prior(score=18.0), _sess(), min_score=25, min_turns=4)
    assert v["sufficient"] is False
    assert any("最高分" in g for g in v["gaps"])


def test_no_archive_no_flags_untraceable():
    v = verdict(_prior(with_no=0), _sess(), min_score=25, min_turns=4)
    assert v["sufficient"] is False
    assert any("档号" in g for g in v["gaps"])


def test_thin_session_flags_insufficient():
    v = verdict(_prior(), _sess(turns=1), min_score=25, min_turns=4)
    assert v["sufficient"] is False
    assert any("会话" in g for g in v["gaps"])


def test_multiple_gaps_are_all_reported():
    v = verdict(_prior(score=5.0, with_no=0), _sess(turns=0), min_score=25, min_turns=4)
    assert len(v["gaps"]) == 3, v["gaps"]


def test_thresholds_are_configurable_not_magic():
    """同一份数据，阈值不同结论就不同 —— 证明阈值是参数，不是写死的直觉。"""
    p, s = _prior(score=30.0), _sess(turns=3)
    assert verdict(p, s, min_score=25, min_turns=4)["sufficient"] is False
    assert verdict(p, s, min_score=25, min_turns=3)["sufficient"] is True


# ── 话题漂移（2026-11-07 加）──

def test_drift_is_unknown_without_substantive_history():
    """最近的用户消息全是「继续推进」这类短指令 ⇒ 未知，不是「漂移」。"""
    from scripts.context_pack import topic_drift
    assert topic_drift("召回延迟多少", ["继续推进", "好", "OK"]) is None


def test_drift_high_when_unrelated():
    from scripts.context_pack import topic_drift
    d = topic_drift("K8s 集群有几个节点",
                    ["召回延迟的 P95 现在是 340 毫秒，比目标高不少"])
    assert d is not None and d > 0.8, d


def test_drift_low_when_same_topic():
    from scripts.context_pack import topic_drift
    d = topic_drift("召回延迟现在实测多少",
                    ["召回延迟现在实测 P95 是 340ms，比目标 200ms 高"])
    assert d is not None and d < 0.5, d


def test_drift_flags_verdict():
    """漂移高要能进 gaps —— 否则信号白算。"""
    v = verdict(_prior(), _sess(), min_score=25, min_turns=4, drift=0.95, drift_limit=0.85)
    assert v["sufficient"] is False
    assert any("漂移" in g for g in v["gaps"])
