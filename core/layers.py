#!/usr/bin/env python3
"""
core/layers.py — 记忆分层模型的**可执行规格**（v8.0 S3-1）
==========================================================

为什么要有代码
--------------
2026-09-24 用户口述了记忆分型（会话/认知/技能/约束/事实/参考/工作），
整理成 5 层 + 1 横切模型。但**规格写在文档里 = 没人执行** ——
红队的原话质疑就是：「这会不会变成『文档写了、系统一行没变』的空转？」

所以本模块把分层做成**可运行判定**：给定一条待写记忆，回答
「它落哪层 / 写规则是什么 / 冲突怎么办 / 载体在哪」。
判据（可证伪）: 任何新写入都能被 `classify_layer()` 给出唯一答案 ——
若某个 category 落不进任何层，或规则与该层声明矛盾，测试会红。

模型（用户 2026-09-24 口述 → 归一化）
------------------------------------
轴只有一条: **允不允许存在矛盾**。

  族「只增不改」     L0 日志层   —— append-only，允许矛盾，只去噪不压缩
  族「版本化·只认最新」 L1 认知层   —— 可更新，需来源，冲突 → 更新 + 留变更日志
                      L2 技能层   —— 文件版本化，.archive 留旧源
                      L3 约束层   —— 人工定稿，**禁止并存**，变更有记录
                      L4 参考层   —— 版本化 + 指针回链
  横切（不是一层）    产出物索引  —— 实体只有一份，指针可多处

关键事实（诚实标注）
--------------------
- **L3 约束层的载体不在 Mnemosyne 库里** —— 它是 `SOUL.md` / `MEMORY.md` /
  `config.yaml`（Hermes 侧，人工定稿）。库里的 `category` 10 类**没有**对应值。
  这不是模型缺陷，而是分层模型与存储载体本来就分离的证据。
- 「事实记忆」按用户原话（"技能、约束这些"）**并入 L2/L3**，不单列一层。
- 认知层目前归入「只认最新」族并允许带置信度；**是否保留"认知演进史"是待拍板项**
  （见提案 P-20260925-01 §7）—— 若拍板要保留，它将成为第三个族，本模块需相应扩展。
"""
from __future__ import annotations

from typing import Optional

# ── 层定义 ──────────────────────────────────────────────────────────────────
LAYERS: dict[str, dict] = {
    "L0": {
        "name": "日志层",
        "family": "只增不改",
        "carrier": "state.db（全量原文+tool_calls）+ Mnemosyne session 归档",
        "write_policy": "append-only；只去噪，不压缩正文",
        "conflict_policy": "允许矛盾，作参考（不覆盖、不判定谁对）",
        "categories": ("session", "temp"),
    },
    "L1": {
        "name": "认知层",
        "family": "版本化·只认最新",
        "carrier": "Mnemosyne knowledge / beliefs + MEMORY.md / USER.md",
        "write_policy": "可更新，须带来源；更新时留变更日志",
        "conflict_policy": "冲突 → 更新为新值 + 记录『从什么变成什么』",
        "categories": ("knowledge", "preference"),
    },
    "L2": {
        "name": "技能层",
        "family": "版本化·只认最新",
        "carrier": "skills/ 文件 + 触发式注入",
        "write_policy": "文件版本化；旧版进 .archive（不删，留源）",
        "conflict_policy": "只认最新；旧版可召回但不再注入",
        "categories": ("pitfall", "ops", "deploy"),
    },
    "L3": {
        "name": "约束层",
        "family": "人工定稿",
        "carrier": "SOUL.md / MEMORY.md / config.yaml（⚠️ 不在 Mnemosyne 库内）",
        "write_policy": "人工定稿；变更有记录",
        "conflict_policy": "**禁止并存** —— 不允许两条约束同时有效",
        "categories": (),  # 库里没有对应 category，这是事实而非遗漏
    },
    "L4": {
        "name": "参考层",
        "family": "版本化·只认最新",
        "carrier": "wiki_pages + 箱子文件 + 项目文档（N+EN / ADR）",
        "write_policy": "版本化；**记忆里只放指针 + 指纹，不放实体**",
        "conflict_policy": "只认最新 + 指针回链",
        "categories": ("reference", "project", "worklog"),
    },
}

ARTIFACT_INDEX = {
    "name": "产出物索引（横切，不是一层）",
    "rule": "实体只有一份，指针可多处；每条引用带 路径/URL + sha256 + 大小",
    "entity_home": {
        "交付/双击打开/给外部看": "箱子（收件箱 → 归档）",
        "要被检索/被反复引用": "Wiki（可版本化、可跨会话召回）",
        "代码/仓库产物": "仓库 + tag",
    },
}

# category → layer 反查表（由 LAYERS 生成，保证单一事实来源）
CATEGORY_TO_LAYER: dict[str, str] = {
    cat: lk for lk, spec in LAYERS.items() for cat in spec["categories"]
}

# 项目受控词表（docs/schema.sql chk_memories_category 的 10 类）
KNOWN_CATEGORIES = ("knowledge", "pitfall", "reference", "project", "ops",
                    "deploy", "preference", "session", "worklog", "temp")


def classify_layer(category: str, *, has_artifact: bool = False,
                   source: Optional[str] = None) -> dict:
    """判定一条记忆落哪一层，并给出该层的写规则与冲突策略。

    category     : 受控词表里的 10 类之一（未知值 → 归一化为 knowledge，与 API 一致）
    has_artifact : 是否伴随交付物/实体文件（决定是否挂产出物索引指针）
    source       : 来源标记（L1 要求带来源）

    返回: {layer, name, family, carrier, write_policy, conflict_policy,
           artifact_pointer, why}
    """
    cat = (category or "").strip().lower()
    normalized = cat in KNOWN_CATEGORIES
    cat_eff = cat if normalized else "knowledge"
    layer = CATEGORY_TO_LAYER.get(cat_eff, "L1")
    spec = LAYERS[layer]

    why = f"category={cat_eff} 属于 {layer} {spec['name']}（{spec['family']}）"
    if not normalized:
        why = f"category={cat!r} 不在受控词表 → 按 knowledge 归一化；" + why

    return {
        "category": cat_eff,
        "layer": layer,
        "name": spec["name"],
        "family": spec["family"],
        "carrier": spec["carrier"],
        "write_policy": spec["write_policy"],
        "conflict_policy": spec["conflict_policy"],
        "requires_source": layer == "L1",
        "source_provided": bool(source),
        "artifact_pointer": bool(has_artifact),
        "artifact_rule": ARTIFACT_INDEX["rule"] if has_artifact else None,
        "why": why,
    }


def self_check() -> dict:
    """规格自检：受控词表每类都必须落进某一层，且层内规则齐备。

    这是把"文档规格"变成"可证伪断言"的关键 —— 有人改了词表却忘了分层，
    这里会红。
    """
    problems = []
    for cat in KNOWN_CATEGORIES:
        if cat not in CATEGORY_TO_LAYER:
            problems.append(f"category={cat} 未归入任何层")
    for lk, spec in LAYERS.items():
        for f in ("name", "family", "carrier", "write_policy", "conflict_policy"):
            if not spec.get(f):
                problems.append(f"{lk} 缺字段 {f}")
    # L3 不应有库内 category —— 若有人硬塞，说明模型与载体被混同了
    if LAYERS["L3"]["categories"]:
        problems.append("L3 约束层不应映射库内 category（其载体在 Hermes 侧）")
    return {"ok": not problems, "problems": problems,
            "coverage": f"{len(CATEGORY_TO_LAYER)}/{len(KNOWN_CATEGORIES)} 类已归层",
            "layers": list(LAYERS.keys())}


if __name__ == "__main__":
    import json
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--self-check":
        r = self_check()
        print(json.dumps(r, ensure_ascii=False, indent=2))
        raise SystemExit(0 if r["ok"] else 1)
    print(json.dumps({"known_categories": KNOWN_CATEGORIES,
                      "category_to_layer": CATEGORY_TO_LAYER,
                      "artifact_index": ARTIFACT_INDEX}, ensure_ascii=False, indent=2))
