#!/usr/bin/env python3
"""
v8.0 S3-1 · 记忆分层模型（可执行规格）测试

这一组测试的**存在本身就是判据** —— 它证明分层不是文档：
规格若只写在 md 里，没人能证伪"系统其实没按它跑"；写成可运行断言后，
任何词表/层定义漂移都会让这里变红。
"""
import pytest

from core import layers as L


def test_l1_self_check_passes():
    r = L.self_check()
    assert r["ok"], f"规格自检未通过: {r['problems']}"
    assert r["problems"] == []
    assert set(r["layers"]) == {"L0", "L1", "L2", "L3", "L4"}


def test_l2_every_controlled_category_maps_to_a_layer():
    for cat in L.KNOWN_CATEGORIES:
        info = L.classify_layer(cat)
        assert info["layer"] in L.LAYERS, f"{cat} 未归层"
        assert info["why"]


def test_l3_unknown_category_normalizes_like_the_api():
    """API 侧非法 category 归一化为 knowledge —— 判定器必须与之一致。"""
    info = L.classify_layer("totally-made-up")
    assert info["category"] == "knowledge"
    assert info["layer"] == "L1"
    assert "不在受控词表" in info["why"]


def test_l4_l3_constraint_layer_is_not_in_the_database():
    """诚实断言：约束层的载体在 Hermes 侧（SOUL/MEMORY/config），库里没有对应 category。

    若有人为了"整齐"给 L3 塞一个 category，这里会红 ——
    那是把「分层模型」与「存储载体」混同，会导致约束被当成普通记忆治理。
    """
    assert L.LAYERS["L3"]["categories"] == ()
    assert "L3" not in set(L.CATEGORY_TO_LAYER.values())


def test_l5_log_layer_allows_contradiction():
    for cat in ("session", "temp"):
        info = L.classify_layer(cat)
        assert info["layer"] == "L0"
        assert info["family"] == "只增不改"
        assert "允许矛盾" in info["conflict_policy"]


def test_l6_only_cognition_layer_requires_source():
    assert L.classify_layer("knowledge")["requires_source"] is True
    assert L.classify_layer("knowledge", source="session:abc")["source_provided"] is True
    for cat in ("session", "reference", "pitfall"):
        assert L.classify_layer(cat)["requires_source"] is False


def test_l7_artifact_pointer_only_when_artifact_present():
    with_art = L.classify_layer("worklog", has_artifact=True)
    assert with_art["artifact_pointer"] is True
    assert with_art["artifact_rule"], "带交付物时必须给出指针规则"
    without = L.classify_layer("worklog", has_artifact=False)
    assert without["artifact_pointer"] is False
    assert without["artifact_rule"] is None


def test_l8_reference_layer_points_not_copies():
    """参考层的关键规则：记忆里只放指针 + 指纹，不放实体。"""
    info = L.classify_layer("reference")
    assert info["layer"] == "L4"
    assert "指针" in info["write_policy"]
    assert set(L.ARTIFACT_INDEX["entity_home"]) == {
        "交付/双击打开/给外部看", "要被检索/被反复引用", "代码/仓库产物"}


def test_l9_self_check_detects_drift(monkeypatch):
    """反证：故意漏掉一个类的归层，自检必须报出来（而不是静默通过）。"""
    broken = dict(L.CATEGORY_TO_LAYER)
    broken.pop("worklog")
    monkeypatch.setattr(L, "CATEGORY_TO_LAYER", broken)
    r = L.self_check()
    assert not r["ok"]
    assert any("worklog" in p for p in r["problems"]), r["problems"]


def test_l10_conflict_policies_are_distinct_by_family():
    """三族冲突策略必须真的不同 —— 否则分族就没有意义。"""
    l0 = L.LAYERS["L0"]["conflict_policy"]
    l1 = L.LAYERS["L1"]["conflict_policy"]
    l3 = L.LAYERS["L3"]["conflict_policy"]
    assert l0 != l1 != l3
    assert "禁止并存" in l3, "约束层必须显式禁止并存"
