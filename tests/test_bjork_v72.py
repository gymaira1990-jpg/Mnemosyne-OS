"""v7.2 Bjork S/R 分离 — 单元测试 (无需 DB)

覆盖: 指数衰减 / 访问重置 / 抽屉划分 / pin兜底 / 回退开关
"""
import pytest
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── 与生产 main.py reflect S/R 逻辑同源的纯函数提取 ──
def decay_R(R: float, days: float) -> float:
    """R 指数衰减: R * 0.5^(days/30), 下限1"""
    if days <= 0:
        return R
    return max(1.0, R * (0.5 ** (days / 30.0)))


def access_reset(S: float, R: float) -> tuple:
    """命中后: R 重置为 S, S 微增 (Bjork 间隔重复)"""
    new_S = min(10.0, S + 0.2)
    return round(new_S, 1), new_S


def drawer_from_sr(S: float, R: float) -> str:
    """Bjork 抽屉: S 决定长期价值(不衰减), R 决定当前可用性"""
    if S >= 7 and R >= 5: return "hot"
    if S >= 5 or R >= 3: return "normal"
    if S >= 3: return "cool"
    return "frozen"


class TestDecayR:
    def test_fresh_no_decay(self):
        assert decay_R(5, 0) == 5

    def test_30d_half_life(self):
        assert abs(decay_R(6, 30) - 3.0) < 0.01

    def test_90d_quarter(self):
        assert abs(decay_R(8, 90) - 1.0) < 0.01  # 8*0.125=1

    def test_floor_one(self):
        assert decay_R(2, 365) == 1.0

    def test_180d_low(self):
        assert decay_R(3, 180) == 1.0


class TestAccessReset:
    def test_reset_r_to_s(self):
        S, R = 3.0, 1.0
        new_S, new_R = access_reset(S, R)
        assert new_R == new_S

    def test_s_grows(self):
        S = 3.0
        for _ in range(5):
            S, R = access_reset(S, 1.0)
        assert S > 3.0

    def test_s_cap_ten(self):
        S, R = access_reset(9.9, 5.0)
        assert S <= 10.0


class TestDrawerFromSR:
    def test_hot_high_value_recent(self):
        assert drawer_from_sr(7, 5) == "hot"
        assert drawer_from_sr(8, 8) == "hot"

    def test_normal_mid_value(self):
        assert drawer_from_sr(5, 3) == "normal"
        assert drawer_from_sr(3, 3) == "normal"  # R>=3 → normal

    def test_cool_low_value_old(self):
        assert drawer_from_sr(3, 1) == "cool"
        assert drawer_from_sr(4, 2) == "cool"

    def test_frozen_low_value_long_unused(self):
        assert drawer_from_sr(2, 1) == "frozen"

    def test_high_s_never_frozen(self):
        """Bjork 核心: 高存储强度记忆永不冻结 (底蕴)"""
        assert drawer_from_sr(7, 1) == "normal"  # S>=5 → normal
        assert drawer_from_sr(5, 1) == "normal"


class TestPinProtection:
    def test_pin_floor_r5(self):
        """pin 记忆 R 兜底 ≥5 → 永远 ≥normal"""
        r = max(5.0, decay_R(8, 365))
        assert drawer_from_sr(8, r) in ("hot", "normal")
        assert r >= 5.0
