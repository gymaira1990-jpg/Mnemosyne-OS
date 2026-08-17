#!/usr/bin/env python3
"""
skill_sync.py — Hermes 技能资产 → Mnemosyne skill_assets 同步器 (v7.7.0)
输入: ~/.hermes/skills/**/SKILL.md + .archive/**/SKILL.md + .usage.json
输出: GZ Mnemosyne POST /api/v1/skills/sync (批量幂等) 或 本地直写测试库

用法:
  python3 skill_sync.py --collect            # 收集本地技能 → skill_manifest.json
  python3 skill_sync.py --push               # 推送 manifest → Mnemosyne
  python3 skill_sync.py --verify             # 比对本地 vs 远端差异
  python3 skill_sync.py --test-db            # 直写本地测试库 (沙箱)
"""
import argparse, hashlib, json, os, re, sys

SKILLS_ROOT = os.path.expanduser("~/.hermes/skills")
USAGE_FILE = os.path.join(SKILLS_ROOT, ".usage.json")
MANIFEST_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skill_manifest.json")

# 纯函数区 (可单测, 不依赖 IO)

def parse_frontmatter(text):
    """提取 name/description/category (对齐 skill_sleeper_scan 但更稳)"""
    name = description = ""
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    if not m:
        return name, description
    fm = m.group(1)
    m2 = re.search(r"^name:\s*(.+)$", fm, re.M)
    if m2:
        name = m2.group(1).strip().strip("\"'")
    # block scalar 优先 (> 或 >- 或 |), 再退单行
    m4 = re.search(r"^description:\s*[>|]\-?\s*\n((?:\s+.+\n?)+)", fm, re.M)
    if m4:
        description = " ".join(l.strip() for l in m4.group(1).splitlines()).strip()
    else:
        m3 = re.search(r"^description:\s*(.+)$", fm, re.M)
        if m3:
            description = m3.group(1).strip().strip("\"'")
    if re.match(r"^Use when 使用 \S+ 技能处理相关任务", description) or description in (">-", ">", "|"):
        description = ""
    return name, description


def state_mapping(usage_rec):
    """curator .usage.json state → skill_assets state (对齐值域)
    缺失/未管理 → active (默认, 让 OS 侧不误杀)"""
    st = (usage_rec or {}).get("state", "active")
    return st if st in ("active", "stale", "archived") else "active"


def build_skill_items(skills_dir, usage_data):
    """扫描技能目录 → 统一 manifest item 列表
    - active 目录: skills/**/SKILL.md
    - 归档目录: skills/.archive/**/SKILL.md → state=archived
    - 未在 .usage.json 的 → active 默认
    """
    items = []
    for base, is_archive in ((skills_dir, False), (os.path.join(skills_dir, ".archive"), True)):
        if not os.path.isdir(base):
            continue
        for dirpath, _dirnames, filenames in os.walk(base):
            if "SKILL.md" not in filenames:
                continue
            path = os.path.join(dirpath, "SKILL.md")
            try:
                text = open(path, encoding="utf-8").read()
            except Exception:
                continue
            name, desc = parse_frontmatter(text)
            if not name:
                name = os.path.basename(dirpath)
            usage = usage_data.get(name, {})
            rel = os.path.relpath(dirpath, os.path.dirname(skills_dir))
            items.append({
                "skill_name": name,
                "description": desc,
                "category": os.path.basename(os.path.dirname(dirpath)),
                "state": "archived" if is_archive else state_mapping(usage),
                "pinned": bool(usage.get("pinned", False)),
                "source_path": rel,
                "use_count": int(usage.get("use_count", 0) or 0),
                "view_count": int(usage.get("view_count", 0) or 0),
                "last_used_at": usage.get("last_used_at"),
                "last_viewed_at": usage.get("last_viewed_at"),
                "archived_at": usage.get("archived_at"),
                "content_hash": hashlib.md5(text.encode("utf-8")).hexdigest()[:12],
            })
    return items


def dedup_items(items):
    """同名校验: 归档与活跃同名 → 活跃优先 (本地同名场景少, 防御)"""
    by_name = {}
    for it in items:
        key = it["skill_name"]
        if key not in by_name or (it["state"] == "active" and by_name[key]["state"] != "active"):
            by_name[key] = it
    return list(by_name.values())


def diff_manifest(local_items, remote_items):
    """变更检测: 返回需推送的项 (content_hash/state/usage 任一变化)"""
    remote_map = {r["skill_name"]: r for r in remote_items or []}
    to_push = []
    for it in local_items:
        r = remote_map.get(it["skill_name"])
        if r is None:
            to_push.append(it)  # 新增
            continue
        changed = any(
            r.get(k) != it[k]
            for k in ("description", "state", "use_count", "view_count", "content_hash")
        )
        if changed:
            it["_change"] = [k for k in ("description", "state", "use_count", "view_count", "content_hash")
                             if r.get(k) != it[k]]
            to_push.append(it)
    return to_push


# ── 主逻辑 (IO) ──

def collect():
    usage_data = {}
    if os.path.exists(USAGE_FILE):
        try:
            usage_data = json.load(open(USAGE_FILE, encoding="utf-8"))
        except Exception as e:
            print(f"[sync] usage.json 读取失败: {e}", file=sys.stderr)
    items = dedup_items(build_skill_items(SKILLS_ROOT, usage_data))
    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    states = {}
    for it in items:
        states[it["state"]] = states.get(it["state"], 0) + 1
    print(f"[sync] 收集 {len(items)} 技能 | 状态分布: {states} | → {MANIFEST_FILE}")
    return items


def push(endpoint="http://127.0.0.1:18010"):
    """推送到 Mnemosyne POST /api/v1/skills/sync (服务端算 embedding)"""
    if not os.path.exists(MANIFEST_FILE):
        print("[sync] 无 manifest, 先 --collect", file=sys.stderr)
        return
    items = json.load(open(MANIFEST_FILE, encoding="utf-8"))
    # 批量切片推送 (每批 50, 防 payload 过大)
    import urllib.request
    batch_size = 50
    total_new = total_upd = 0
    for i in range(0, len(items), batch_size):
        batch = items[i:i+batch_size]
        payload = json.dumps({"skills": batch, "tenant_id": "default"}).encode()
        req = urllib.request.Request(
            endpoint.rstrip("/") + "/api/v1/skills/sync",
            data=payload, method="POST",
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                d = json.loads(resp.read())
                total_new += d.get("new", 0)
                total_upd += d.get("updated", 0)
                print(f"[sync] 批次 {i//batch_size+1}: synced={d.get('synced')} new={d.get('new')} upd={d.get('updated')} embedded={d.get('embedded')}")
        except Exception as e:
            print(f"[sync] 批次 {i//batch_size+1} 失败: {e}", file=sys.stderr)
    print(f"[sync] 推送完成: {len(items)} 项, 新增 {total_new}, 更新 {total_upd}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    if args.collect:
        collect()
    elif args.push:
        collect()
        push()
    elif args.verify:
        items = collect()
        print(f"[sync] verify: manifest {len(items)} 项, 待与远端比对")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
