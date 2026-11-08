"""评测判据的行为测试 —— T-0684，2026-11-09。

锁住负样本的新口径：**返回空 或 全部 answerability < 0.3 才算弃权成功**。

为什么改：旧判据只看「有没有撞 forbid 词」。实测 4 条负样本里 3 条假通过 ——
问「灾难恢复演练上一次是什么时候做的」，系统返回「讨厌一动就加巡检」（score 65，
比正样本还高），只因不含 forbid 词就判 PASS。这样的尺子会把「顶了不相干内容」
记成「正确地弃权」。
"""
import importlib.util
import pathlib
import sys

# eval_recall.py 不在包内，用文件路径加载
_p = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "eval_recall.py"
_spec = importlib.util.spec_from_file_location("eval_recall", _p)
ev = importlib.util.module_from_spec(_spec)
sys.modules["eval_recall"] = ev
_spec.loader.exec_module(ev)

judge = ev.judge

UNRELATED = ["[结果卡] 题名：讨厌一动就加巡检\n摘要：减负第一，能靠自动恢复解决就不加监控。"]
RELEVANT = ["[结果卡] 档号：K·DEMO·2026-0038\n题名：火山引擎账户余额 225 元\n摘要：走按量计费。"]


class TestNegativeJudgement:
    """负样本：库里没有答案，系统应当弃权。"""

    def test_all_answerability_low_passes(self):
        """顶上了东西但全都答非所问 → 判通过（等于正确弃权）"""
        ok, _ = judge(UNRELATED, [], 10, forbid=["保留最近 8 份"], answerabilities=[0.0])
        assert ok is True

    def test_high_answerability_fails(self):
        """顶上的东西确实答到了问题 → 判失败（说明库里其实有答案，或它答错了别的）"""
        ok, pos = judge(RELEVANT, [], 10, forbid=["保留最近 8 份"], answerabilities=[0.8])
        assert ok is False
        assert pos == 1

    def test_empty_result_passes(self):
        """一条都没返回 → 正确弃权"""
        ok, _ = judge([], [], 10, forbid=["x"], answerabilities=[])
        assert ok is True

    def test_threshold_boundary(self):
        """0.3 是分界：0.29 通过、0.31 失败"""
        assert judge(UNRELATED, [], 10, forbid=["x"], answerabilities=[0.29])[0] is True
        assert judge(RELEVANT, [], 10, forbid=["x"], answerabilities=[0.31])[0] is False

    def test_picks_max_position(self):
        """多条里只要有一条答得上就算失败，位次报它的位置"""
        ok, pos = judge(["无关A", "无关B", "相关C"], [], 10,
                        forbid=["x"], answerabilities=[0.1, 0.2, 0.9])
        assert ok is False
        assert pos == 3

    def test_legacy_mode_without_answerabilities(self):
        """不传 answerabilities（selftest/老调用）→ 退回旧口径，保持向后兼容"""
        assert judge(["客户违约金是 5%"], [], 10, forbid=["违约金"])[0] is False
        assert judge(["今天天气不错"], [], 10, forbid=["违约金"])[0] is True

    def test_k_truncation(self):
        """只看前 k 条，k 之外的答非所问不算"""
        rows = ["无关"] * 5 + ["相关"]
        ans = [0.0] * 5 + [0.9]
        assert judge(rows, [], 5, forbid=["x"], answerabilities=ans)[0] is True
        assert judge(rows, [], 10, forbid=["x"], answerabilities=ans)[0] is False


class TestPositiveJudgement:
    """正样本：判据未变，防止被上面的改动误伤。"""

    def test_expect_hit(self):
        assert judge(["a", "b", "c-200ms"], ["200ms"], 10)[0] is True

    def test_expect_miss(self):
        assert judge(["不存在的词"], ["完全无关"], 10)[0] is False

    def test_invalid_case_raises(self):
        import pytest
        with pytest.raises(ValueError):
            judge(["x"], [], 10)
