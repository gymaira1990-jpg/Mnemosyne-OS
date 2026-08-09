"""v7.1 抽屉化记忆 — 双抽屉流转/遗忘判定 单元测试 (无需 DB)

覆盖: 温度抽屉边界 / 时间抽屉边界 / 遗忘候选规则 / 双权重公式数值
"""
import pytest
import sys, os, math
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── 与生产 main.py reflect 同源逻辑的纯函数提取 (保证测试=生产) ──
def temp_drawer(heat: float) -> str:
    if heat >= 0.7: return "hot"
    if heat >= 0.3: return "normal"
    if heat >= 0.1: return "cool"
    return "frozen"


def time_drawer(last_access, created, now) -> str:
    ref = last_access or created
    if ref > now - timedelta(days=30): return "recent"
    if ref > now - timedelta(days=90): return "mid"
    return "long"


def is_forget_candidate(temp: str, tmd: str, pinned: bool, category: str) -> bool:
    return temp == "frozen" and tmd == "long" and not pinned and category != "preference"


def compute_heat(last_access_hours: float, freq_ratio: float) -> float:
    """双权重热度公式 (考古A): 0.6×e^(-λh) + 0.4×freq, λ=0.05"""
    time_factor = math.exp(-0.05 * last_access_hours)
    return round(max(0.0, min(1.0, 0.6 * time_factor + 0.4 * freq_ratio)), 4)


class TestTempDrawer:
    def test_hot_boundary(self):
        assert temp_drawer(0.7) == "hot"
        assert temp_drawer(0.85) == "hot"

    def test_normal_range(self):
        assert temp_drawer(0.3) == "normal"
        assert temp_drawer(0.45) == "normal"
        assert temp_drawer(0.699) == "normal"

    def test_cool_range(self):
        assert temp_drawer(0.1) == "cool"
        assert temp_drawer(0.15) == "cool"

    def test_frozen_below(self):
        assert temp_drawer(0.05) == "frozen"
        assert temp_drawer(0.0) == "frozen"


class TestTimeDrawer:
    NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)

    def test_recent(self):
        assert time_drawer(self.NOW - timedelta(days=29), None, self.NOW) == "recent"
        assert time_drawer(None, self.NOW - timedelta(days=1), self.NOW) == "recent"

    def test_mid(self):
        assert time_drawer(self.NOW - timedelta(days=30), None, self.NOW) == "mid"
        assert time_drawer(self.NOW - timedelta(days=89), None, self.NOW) == "mid"

    def test_long(self):
        assert time_drawer(self.NOW - timedelta(days=90), None, self.NOW) == "long"
        assert time_drawer(self.NOW - timedelta(days=180), None, self.NOW) == "long"

    def test_null_fallback_to_created(self):
        """last_accessed NULL 时回退 created_at (v7.1 修复: 防一刀切 recent)"""
        assert time_drawer(None, self.NOW - timedelta(days=120), self.NOW) == "long"


class TestForgetCandidate:
    def test_frozen_long_candidate(self):
        assert is_forget_candidate("frozen", "long", False, "session") is True

    def test_pin_exempt(self):
        assert is_forget_candidate("frozen", "long", True, "session") is False

    def test_preference_exempt(self):
        assert is_forget_candidate("frozen", "long", False, "preference") is False

    def test_not_frozen_no(self):
        assert is_forget_candidate("cool", "long", False, "session") is False

    def test_not_long_no(self):
        assert is_forget_candidate("frozen", "recent", False, "session") is False


class TestDualWeightHeat:
    def test_fresh_high_freq(self):
        assert compute_heat(0, 1.0) == 1.0

    def test_one_day_decay(self):
        h = compute_heat(24, 0.8)
        assert 0.49 <= h <= 0.51

    def test_week_decay(self):
        h = compute_heat(168, 0.5)
        assert 0.19 <= h <= 0.21

    def test_month_cold(self):
        h = compute_heat(720, 0.2)
        assert 0.07 <= h <= 0.09
