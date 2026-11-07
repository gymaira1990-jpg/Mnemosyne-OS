"""尺子自检：评测到底能不能分出好坏（2026-11-07）

为什么单独测这个：评测脚本本身是「测量工具」，工具不准，后面所有优化都是自我安慰。
这里不连服务、不打网络，只喂**构造好的候选列表**，验证三件事：

1. 负样本判据：禁词被顶上来就是不过；
2. 正向判据 + 位次：期望词在 k 之外不算命中；
3. 区分度：紧 k 必须比宽 k 严；全命中就判「尺子无效」。

⚠️ 走过一次弯路：最初想用「把结果倒序再判一次」来测区分度 —— 数学上错的，
   倒序不改变「是否在前 k 条」，差值恒为 0。真正的失效形态是「题太容易」。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.eval_recall import TIGHT_K, _score, judge  # noqa: E402


def test_negative_case_fails_when_forbidden_surfaces():
    ok, pos = judge(["客户违约金是 5%"], [], 10, ["违约金"])
    assert ok is False and pos == 1


def test_negative_case_passes_when_clean():
    ok, _ = judge(["今天天气不错"], [], 10, ["违约金"])
    assert ok is True


def test_positive_case_rank_sensitive():
    rows = ["无关", "无关", "答案在这里"]
    assert judge(rows, ["答案在这里"], 10)[0] is True
    assert judge(rows, ["答案在这里"], 2)[0] is False, "k=2 时第 3 条不该算命中"


def test_invalid_case_raises():
    try:
        judge(["x"], [], 10)
    except ValueError:
        return
    raise AssertionError("没有 expect/forbid 的用例必须报错，不能默默通过")


def test_tight_k_is_stricter_than_wide_k():
    """位次有区分：答案排在第 5 位 ⇒ recall@10 命中、recall@3 不命中。"""
    cases = [{"q": "q1", "expect": ["答案"]}]
    results = {0: ["1", "2", "3", "4", "答案这里"]}
    wide, _ = _score(cases, results, 10)
    tight, _ = _score(cases, results, TIGHT_K)
    assert wide == 1.0 and tight == 0.0, (wide, tight)


def test_full_marks_means_ruler_is_useless():
    """每条结果都命中 ⇒ recall@k=100% ⇒ 按判据必须判「尺子无效」。"""
    cases = [{"q": "q1", "expect": ["答案"]}]
    results = {0: ["答案", "答案", "答案"]}
    rate, _ = _score(cases, results, 10)
    assert rate >= 1.0


def test_return_everything_baseline_scores_badly_on_negatives():
    """「把库全倒出来」的假基线：正向也许蒙对，负样本必挂 —— 这正是加负样本的意义。"""
    cases = [
        {"q": "灾难恢复演练", "forbid": ["保留最近 8 份"]},
        {"q": "续期报错码", "forbid": ["acme.sh"]},
    ]
    dump_everything = {0: ["备份策略：保留最近 8 份"], 1: ["证书用 acme.sh 续期"]}
    rate, hits = _score(cases, dump_everything, 10)
    assert hits == 0, f"全量倾倒不该拿分，实际 {rate:.0%}"
