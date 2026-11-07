"""冲突检测的判据（2026-11-07）

为什么要合成对照：本模块第一版因为一个缩进错误，`conflicts.append(...)` 掉进了
`if run < min_run:` 分支里成了死代码 —— 于是无论什么输入都返回「没冲突」。
在真实数据上跑，结果看起来非常合理（0 对，像「数据很干净」）。
**是合成对照拆穿的：该命中的样本它也不命中。**
⇒ 凡「检测器」，必须有一条「一定能检出来」的对照样例，否则它坏了你也不知道。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.conflict import detect_conflicts, extract_facts  # noqa: E402


def test_extract_facts_pulls_value_unit_and_context():
    facts = extract_facts("数据库备份保留最近 8 份")
    assert facts and facts[0]["value"] == "8" and facts[0]["unit"] == "份"
    assert "保留最近" in facts[0]["context"]


def test_same_phrase_different_value_is_flagged():
    """对照组：同一句话、不同数字 ⇒ 必须报出来。"""
    items = [{"no": "A", "head": "数据库备份策略：保留最近 8 份，存于 /var/backups"},
             {"no": "B", "head": "数据库备份策略：保留最近 5 份，存于 /var/backups"}]
    cs = detect_conflicts(items)
    assert len(cs) == 1, f"应命中 1 对，实际 {len(cs)}：{cs}"
    assert {cs[0]["a"]["value"], cs[0]["b"]["value"]} == {"8", "5"}


def test_same_value_is_not_a_conflict():
    items = [{"no": "A", "head": "保留最近 8 份"},
             {"no": "B", "head": "保留最近 8 份"}]
    assert detect_conflicts(items) == []


def test_different_unit_is_not_a_conflict():
    """8 份 vs 8 天：单位不同，不是同一件事。"""
    items = [{"no": "A", "head": "保留最近 8 份"},
             {"no": "B", "head": "保留最近 8 天"}]
    assert detect_conflicts(items) == []


def test_unrelated_phrasing_is_not_a_conflict():
    """单位相同、数值不同，但说的不是同一句话 ⇒ 不报（防误报的关键一条）。"""
    items = [{"no": "A", "head": "本次部署共改动 12 个文件，全部通过 lint"},
             {"no": "B", "head": "另一批改动：新增 3 个文件，删了 2 个文件"}]
    assert detect_conflicts(items) == [], "泛单位 + 语境不同，不该报"


def test_target_vs_actual_in_one_card_is_not_flagged():
    """「目标 200ms、实测 340ms」是目标与实测，不是冲突。"""
    items = [{"no": "A", "head": "召回延迟目标 200ms，当前实测 P95 是 340ms"}]
    assert detect_conflicts(items) == []


def test_min_run_guard_is_alive():
    """死代码回归测试：把 min_run 调到不可能满足的值 ⇒ 必须一条都不报。

    第一版的 bug 正是「append 掉进了这个分支」，那样调高阈值也照样返回空 —— 分不出来。
    """
    items = [{"no": "A", "head": "保留最近 8 份，存于 /var/backups"},
             {"no": "B", "head": "保留最近 5 份，存于 /var/backups"}]
    assert detect_conflicts(items, min_run=999) == []
    assert detect_conflicts(items, min_run=1) != [], "正常阈值下必须还能报出来"


def test_templated_metadata_does_not_create_false_conflict():
    """真实数据教训：模板尾部（证据/路径/URL）大量重复，数字撞车纯属格式巧合。

    实测过：不设主题约束时 3000 张卡报 5 对，人工看完 5/5 全假阳性
    （「2.2G 僵尸占用」vs「1.53 GMV 代币」、「22KB 帧」vs「158KB 帧」）。
    """
    items = [
        {"no": "C", "head": "[结果卡] 档号：K·C 题名：GZ 僵尸清理前先摸清 2.2G 占用 "
                            "摘要：先摸清 2.2G 里哪些是僵尸 证据：~/.hermes/scripts/ · 2.2G"},
        {"no": "D", "head": "[结果卡] 档号：K·D 题名：待铸 1.53 GMV 首铸验证 "
                            "摘要：约到 1.53 G 时执行 证据：~/.hermes/scripts/ · 1.53 G"},
    ]
    assert detect_conflicts(items) == [], "主题不同，光靠模板撞车不能算冲突"


def test_same_topic_different_value_still_flagged():
    """加了主题约束后，真冲突（同题名不同值）必须还能报出来。"""
    items = [
        {"no": "A", "head": "[结果卡] 档号：K·A 题名：数据库备份保留份数 摘要：保留最近 8 份 证据：无"},
        {"no": "B", "head": "[结果卡] 档号：K·B 题名：数据库备份保留份数 摘要：保留最近 5 份 证据：无"},
    ]
    cs = detect_conflicts(items)
    assert len(cs) == 1 and cs[0]["topic_overlap"] >= 0.4


def test_topic_of_extracts_title():
    from core.conflict import topic_of
    assert topic_of("[结果卡] 档号：K·X 题名：双经济体方案v6交付件 摘要：含 8 张图") == "双经济体方案v6交付件"
