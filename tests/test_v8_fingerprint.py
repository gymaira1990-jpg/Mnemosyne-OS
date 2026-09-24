#!/usr/bin/env python3
"""v8.0.1 · 幂等键分层化测试（纯函数）

背景（红队指出 → 复核成立）：初版对所有分类一律用内容指纹，
与 L0 契约「只增不改、允许矛盾」直接矛盾 —— 同一文案在不同时刻出现会被误杀。
"""
import pytest

from main import compute_write_fingerprint as fp
from main import should_run_conflict_detection as det


def test_l0_same_session_retry_dedupes():
    """重试（同 session 同内容）必须去重 —— 这是幂等的本职。"""
    a = fp("好的，收到", "session", "default", session_id="s1", layer="L0")
    b = fp("好的，收到", "session", "default", session_id="s1", layer="L0")
    assert a == b


def test_l0_different_sessions_are_preserved():
    """**反证**：不同会话说同一句话，必须**各存一条**（L0 允许矛盾）。
    初版行为（不含上下文）在这里会把它们并成一条 —— 那就是误杀。"""
    a = fp("好的，收到", "session", "default", session_id="s1", layer="L0")
    b = fp("好的，收到", "session", "default", session_id="s2", layer="L0")
    assert a != b, "L0 把不同会话的同文案并成一条 —— 违反『只增不改、允许矛盾』"


def test_l0_source_also_distinguishes():
    a = fp("heartbeat ok", "session", "default", source="cron-A", layer="L0")
    b = fp("heartbeat ok", "session", "default", source="cron-B", layer="L0")
    assert a != b


def test_l0_without_context_uses_hour_bucket():
    """裸 L0（无 session/source）：同小时内重试去重，跨小时保留。"""
    same = fp("TODO: 检查备份", "temp", "default", layer="L0", now_ts=1_700_000_000)
    same2 = fp("TODO: 检查备份", "temp", "default", layer="L0", now_ts=1_700_000_059)
    later = fp("TODO: 检查备份", "temp", "default", layer="L0", now_ts=1_700_000_000 + 7200)
    assert same == same2
    assert same != later, "跨小时应视为不同事件（L0 允许矛盾）"


def test_non_l0_is_content_fingerprint_and_idempotent():
    """L1~L4：版本化族 → 内容指纹，与 session 无关（同内容必幂等）。"""
    for cat, layer in (("knowledge", "L1"), ("pitfall", "L2"),
                       ("reference", "L4"), ("worklog", "L4")):
        a = fp("同一个事实", cat, "default", session_id="s1", layer=layer)
        b = fp("同一个事实", cat, "default", session_id="s2", layer=layer)
        assert a == b, f"{layer}({cat}) 应内容幂等"


def test_fingerprint_is_64_hex():
    for layer in ("L0", "L1", "L4"):
        v = fp("x", "knowledge", "default", layer=layer)
        assert len(v) == 64 and all(c in "0123456789abcdef" for c in v)


def test_l0_skips_conflict_detection():
    """**P4 生产实测抓到的半修**：只改指纹不分流冲突检测，L0 仍会被 merge 压缩。

    契约依据：L0 = 只增不改、允许矛盾 → 语义合并在 L0 上等于压缩日志。
    """
    assert det("L0") is False, "L0 不该跑语义合并 —— 会违反『只增不改』"
    for layer in ("L1", "L2", "L3", "L4"):
        assert det(layer) is True, f"{layer} 应保留语义合并/覆盖"


def test_two_fixes_are_both_required():
    """反证：只做一半会怎样 —— 指纹不同但内容近重复，仍会被 merge 吃掉。"""
    a = fp("同一句话", "temp", "default", source="A", layer="L0")
    b = fp("同一句话", "temp", "default", source="B", layer="L0")
    assert a != b, "指纹已分层"
    assert det("L0") is False, "但若冲突检测不分流，这两条仍会被 merged —— 所以两处都要改"
