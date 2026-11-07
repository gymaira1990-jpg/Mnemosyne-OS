"""弃权判据（2026-11-07）

「库里没有这条」时，检索器应该能说出「没找到」，而不是拿勉强相关的卡凑数。
本文件锁住判据本身；同时用注释记下**否证**：分数阈值分不开正负样本。

实测（demo 40 张卡 / 16 题）最高分分布：
    正样本最低 16.2（海报配色，靠 S 通道命中）
    负样本仍失败 20.0（周报财务）
    ⇒ 任何阈值要么误杀正样本、要么拦不住负样本。所以默认关闭（0），
      参数保留，等换成更有区分度的信号（关键词覆盖度 / 问题类型 vs 卡片结构）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.memory_os import _should_abstain  # noqa: E402


def test_threshold_zero_disables_abstention():
    assert _should_abstain([{"score": 0.1}], 0) is False
    assert _should_abstain([{"score": 0.1}], -5) is False


def test_empty_never_abstains():
    """没候选就不用弃权 —— 那是「没查到」，不是「主动闭嘴」。"""
    assert _should_abstain([], 50) is False


def test_below_threshold_abstains():
    assert _should_abstain([{"score": 19.9}], 20.0) is True


def test_at_or_above_threshold_keeps_results():
    assert _should_abstain([{"score": 20.0}], 20.0) is False
    assert _should_abstain([{"score": 78.5}], 20.0) is False


def test_malformed_score_does_not_crash():
    """脏分数不能把端点搞 500 —— 宁可不弃权，也别炸。"""
    assert _should_abstain([{"score": "abc"}], 20.0) is False
    assert _should_abstain([{}], 20.0) is False


def test_documented_negative_result():
    """把否证写进测试：正样本 16.2 会比负样本 20.0 更早被弃权掉 ⇒ 阈值不可用。"""
    positive_low = [{"score": 16.2}]
    negative = [{"score": 20.0}]
    th = 20.0
    assert _should_abstain(positive_low, th) is True, "正样本被误杀"
    assert _should_abstain(negative, th) is False, "负样本仍放行"
