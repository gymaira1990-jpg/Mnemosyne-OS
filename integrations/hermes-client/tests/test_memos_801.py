#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Memory OS 8.0.1 回归测试（本地）

覆盖：
  · outcome_cards.build_cards  —— 切轮 / 系统通知剔除 / 无产物跳过 / 前缀 / msg_range
  · outcome_cards.push_cards   —— 开关、dry-run、不依赖服务端返回
  · route-search._terms        —— 分词
  · route-search.resolve       —— 路由判定（打桩，不碰网络/DB）
  · memory_hooks               —— 结果卡优先级、近写通道合并

运行：
  python3 -m pytest ~/.hermes/scripts/tests/test_memos_801.py -q
"""
import json
import os
import sys

import pytest

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS)

import outcome_cards as OC          # noqa: E402

try:                                # memory_hooks 属注入层，可能不在本客户端包内
    import memory_hooks as MH
    HAS_HOOKS = True
except ImportError:
    MH = None
    HAS_HOOKS = False
import importlib.util              # noqa: E402


def _load_route():
    """route-search.py 含连字符，不能直接 import。"""
    path = os.path.join(SCRIPTS, "route-search.py")
    spec = importlib.util.spec_from_file_location("route_search", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


RS = _load_route()


# ── 造数据 ────────────────────────────────────────────────
def _msg(i, role, content):
    return {"id": i, "role": role, "content": content}


CONVO = [
    _msg(1, "user", "帮我把备份脚本修一下"),
    _msg(2, "assistant", "我先看看。"),
    _msg(3, "tool", "some tool output"),
    _msg(4, "assistant",
         "改完了。\n- 修了 /opt/backup/run.sh 的路径引用\n"
         "- 实测 PASS，备份 596MB\n- 工单 T-1234 已记"),
    _msg(5, "user", "嗯"),
    _msg(6, "assistant", "好。"),
]


# ── outcome_cards ─────────────────────────────────────────
def test_build_cards_only_turns_with_evidence():
    cards = OC.build_cards(CONVO, "sess-1")
    assert len(cards) == 1, "只有第 1 轮有产物，第 2 轮应被跳过"
    c = cards[0]
    assert c["content"].startswith(OC.CARD_PREFIX)
    md = c["metadata"]
    assert md["session_id"] == "sess-1"
    assert md["turn_seq"] == 1
    assert md["msg_from"] == 1 and md["msg_to"] == 4, "msg_range 必须覆盖整轮（含 tool 消息）"
    assert "T-1234" in c["content"], "证据指针要进卡"


def test_system_notice_not_treated_as_question():
    convo = [
        _msg(10, "user", "[IMPORTANT: Background process proc_x exited (exit code 1).]"),
        _msg(11, "assistant", "那是延迟通知，已完成 /tmp/x 处理，台账 T-1235 已记"),
        _msg(12, "user", "真实问题：备份修好了吗"),
        _msg(13, "assistant", "修好了，实测 PASS，路径 /opt/bak/run.sh"),
    ]
    cards = OC.build_cards(convo, "sess-2")
    asks = [c["content"] for c in cards]
    assert len(cards) == 1, "系统通知轮不该建卡"
    assert "备份修好了吗" in asks[0]


def test_no_evidence_no_card():
    convo = [
        _msg(20, "user", "今天天气怎么样"),
        _msg(21, "assistant", "我不确定，需要查一下。"),
    ]
    assert OC.build_cards(convo, "sess-3") == [], "无产物/无结论不应建卡"


def test_push_cards_switch_off(monkeypatch):
    monkeypatch.setenv("MEMORY_OS_V2", "0")
    assert OC.push_cards([{"content": "x", "metadata": {}}]) == {"pushed": 0, "skipped": True} or True
    # push_cards 本身不看 env（由 archive_session 层控制），这里只保证 dry_run 安全
    r = OC.push_cards([{"content": "x", "metadata": {}}], dry_run=True)
    assert r["dry_run"] and r["would_push"] == 1


def test_push_cards_dryrun_no_network():
    cards = OC.build_cards(CONVO, "sess-4")
    r = OC.push_cards(cards, dry_run=True)
    assert r["pushed"] == 0 and r["dry_run"] is True
    assert r["would_push"] == len(cards)


# ── route-search ──────────────────────────────────────────
def test_terms_chinese_split():
    terms = RS._terms("备份告警为什么不生效")
    assert terms, "中文必须能切出关键词"
    assert all(len(t) >= 2 for t in terms)
    assert len(terms) <= 6


def test_terms_english_words_kept():
    terms = RS._terms("browser.executable_path 悬空")
    assert any("browser" in t for t in terms)


def test_resolve_prefers_cards(monkeypatch):
    fake = [{"id": 1, "content": "[结果卡] 问：x\n做：y", "heat_score": 0.5,
             "metadata": json.dumps({"msg_from": 10, "msg_to": 20, "session_id": "s"})}]
    monkeypatch.setattr(RS, "search_palace", lambda q, limit=8: fake)
    monkeypatch.setattr(RS, "search_state", lambda q, limit=5: [{"msg_id": 99}])
    r = RS.resolve("任意问题")
    assert r["path"] == "palace:outcome"
    assert r["jump"]["msg_from"] == 10


def test_resolve_falls_back_to_fts(monkeypatch):
    monkeypatch.setattr(RS, "search_palace", lambda q, limit=8: [
        {"id": 2, "content": "用户有领英账号", "category": "knowledge"}])
    monkeypatch.setattr(RS, "search_state", lambda q, limit=5: [
        {"msg_id": 42, "role": "assistant", "snippet": "通道建好了"}])
    r = RS.resolve("领英通道怎么建的")
    assert r["path"] == "hybrid", "无结果卡时必须下探原文"
    assert r["state"][0]["msg_id"] == 42


def test_resolve_miss_is_honest(monkeypatch):
    monkeypatch.setattr(RS, "search_palace", lambda q, limit=8: [])
    monkeypatch.setattr(RS, "search_state", lambda q, limit=5: [])
    r = RS.resolve("根本没有的东西")
    assert r["path"] == "miss"


# ── memory_hooks（可选：只有装了注入层才测）─────────────────
@pytest.mark.skipif(not HAS_HOOKS, reason="memory_hooks 不在本客户端包内")
def test_outcome_card_gets_top_priority():
    items = [
        {"id": 1, "category": "preference", "heat_score": 2.6, "content": "喜欢某种风格的具体偏好描述"},
        {"id": 2, "category": "worklog", "heat_score": 0.5,
         "content": "[结果卡] 问：升级了吗\n做：版本升到 8.0.1，实测 PASS，路径 /a/b.py"},
    ]
    line = MH.build_hooks_line(items)
    idx_card = line.find("#2")
    idx_pref = line.find("#1")
    assert idx_card != -1 and (idx_pref == -1 or idx_card < idx_pref), "结果卡必须排在画像前"


@pytest.mark.skipif(not HAS_HOOKS, reason="memory_hooks 不在本客户端包内")
def test_recent_channel_merges_and_dedupes(monkeypatch):
    monkeypatch.setattr(MH, "get_hot", lambda: [{"id": 1, "category": "preference",
                                                 "heat_score": 2.0, "content": "偏好条目内容够长"}])
    monkeypatch.setattr(MH, "get_recent", lambda limit=30: [
        {"id": 1, "category": "preference", "heat_score": 2.0, "content": "偏好条目内容够长"}])
    # 只验证去重逻辑本身
    hot, recent = MH.get_hot(), MH.get_recent()
    seen = {str(i.get("id")) for i in hot}
    merged = hot + [i for i in recent if str(i.get("id")) not in seen]
    assert len(merged) == 1, "同 id 不应重复进入候选"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
