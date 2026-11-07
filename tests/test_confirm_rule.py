"""求证判据：拿不准就把候选摆出来问人（2026-11-07）

主人原话方向：召回不可能触达 100%，与其硬给一个答案，不如多给候选让人裁；
裁完的结果回写系统，等于给自己当标注员。

两种「拿不准」：
  1. 并列：top1 与 top2 分数差 < margin —— 两条都像，选谁都是猜；
  2. 孤证：只有 1 条候选且分数偏低 —— 一条不足以支撑结论。
分数高且明显领先 → 不打扰人（问太多就是噪音，实测 margin=30 时求证率飙到 50%）。

实测（demo 16 题，margin=10）：求证率 19%（3/16），其中正好包含
「周报模板里财务数字怎么填」—— 弃权阈值搞不定、但问人一问就清楚的那条。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.memory_os import _needs_confirmation  # noqa: E402


def test_margin_zero_disables_confirmation():
    assert _needs_confirmation([{"score": 50}, {"score": 49.9}], 0) is False


def test_clear_winner_does_not_bother_the_user():
    assert _needs_confirmation([{"score": 78.5}, {"score": 30.0}], 10) is False


def test_close_call_asks():
    assert _needs_confirmation([{"score": 40.0}, {"score": 35.0}], 10) is True


def test_single_weak_candidate_asks():
    assert _needs_confirmation([{"score": 8.0}], 10) is True


def test_single_strong_candidate_does_not_ask():
    assert _needs_confirmation([{"score": 88.0}], 10) is False


def test_empty_does_not_ask():
    """没有候选是「没查到」，不是「拿不准」—— 那是弃权/空结果的场景。"""
    assert _needs_confirmation([], 10) is False


def test_malformed_scores_do_not_crash():
    assert _needs_confirmation([{"score": "abc"}, {"score": 1}], 10) is False
    assert _needs_confirmation([{}, {"score": 1}], 10) is False
