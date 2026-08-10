#!/usr/bin/env python3
"""md_ingest — WIKI 全文快照导入管线 (v7.4)

设计: 本地源 = 权威真相; 线上 wiki_pages = 防损毁档案馆快照 (单向同步)
- --sync   : 导入/更新本地 MD/txt/html → wiki_pages (hash 幂等, 漂移自动升级版本)
- --verify : 校验线上快照 vs 本地源 (一致/漂移/源已丢失)
- 用法:
    python3 md_ingest.py --sync items.json
    python3 md_ingest.py --verify items.json
    python3 md_ingest.py --list-sources   # 列出线上全部来源

items.json 结构:
[
  {"path": "/path/to/your/papers/xxx.md",
   "title": "可选(默认取文件名)",
   "url": "可选, 网站源URL",
   "type": "paper|article|novel|design|memo",
   "tags": ["标签1", "标签2"]},
  ...
]
"""
import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
import urllib.parse

ENDPOINT = os.environ.get("MNEMOSYNE_ENDPOINT", "http://127.0.0.1:18010")
USER_ID = "default"


def api(method, path, body=None, params=None, timeout=180):
    url = ENDPOINT + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def title_from_path(path: str) -> str:
    base = os.path.basename(path)
    name = os.path.splitext(base)[0]
    return name.replace("_", " ").replace("-", " ")


def sync_item(item: dict) -> dict:
    path = item["path"]
    if not os.path.exists(path):
        return {"path": path, "status": "source-missing",
                "msg": "本地源不存在, 线上快照仍可查证"}
    content = read_text(path)
    if len(content.strip()) < 20:
        return {"path": path, "status": "skipped-empty", "msg": f"内容过短({len(content)}字符)"}
    h = file_hash(path)
    body = {
        "title": item.get("title") or title_from_path(path),
        "content": content,
        "user_id": USER_ID,
        "tags": item.get("tags", []),
        "source_path": path,
        "source_url": item.get("url", ""),
        "source_type": item.get("type", "memo"),
        "content_hash": h,
    }
    start = time.time()
    resp = api("POST", "/api/v1/wiki", body)
    dt = round(time.time() - start, 1)
    return {"path": path, "status": resp.get("status", "?"),
            "id": resp.get("id"), "version": resp.get("version"),
            "chars": len(content), "sec": dt}


def verify_item(item: dict) -> dict:
    """校验: 线上 content_hash vs 本地源 hash"""
    path = item["path"]
    online = api("GET", "/api/v1/wiki/by-source", params={"source_path": path, "user_id": USER_ID})
    if not online.get("found"):
        return {"path": path, "status": "not-ingested", "msg": "线上无此来源快照"}
    if not os.path.exists(path):
        return {"path": path, "status": "source-lost",
                "online_id": online["id"], "version": online["version"],
                "msg": "本地源已丢失, 线上快照仍可查证 (source_lost 应标记)"}
    h = file_hash(path)
    online_hash = online.get("content_hash") or ""
    if online_hash and h == online_hash:
        return {"path": path, "status": "consistent", "online_id": online["id"],
                "version": online["version"], "msg": "线上快照与本地源一致"}
    return {"path": path, "status": "drifted", "online_id": online["id"],
            "version": online["version"],
            "msg": "本地源已修改(线上旧), 重跑 --sync 以本地为准更新"}


def list_sources():
    rows = api("GET", "/api/v1/wiki", params={"user_id": USER_ID, "limit": 500})
    out = []
    for r in rows:
        out.append({"id": r["id"], "title": r["title"],
                    "len": r["content_length"], "updated": r["updated"]})
    return out


def main():
    ap = argparse.ArgumentParser(description="WIKI 全文快照导入管线 v7.4")
    ap.add_argument("--sync", metavar="items.json", help="导入/更新快照")
    ap.add_argument("--verify", metavar="items.json", help="校验线上 vs 本地")
    ap.add_argument("--list-sources", action="store_true", help="列出线上来源")
    args = ap.parse_args()

    if args.list_sources:
        for r in list_sources():
            print(f"#{r['id']} [{r['len']}ch] {r['title']} (updated {r['updated']})")
        return

    if not (args.sync or args.verify):
        ap.print_help()
        sys.exit(1)

    items_file = args.sync or args.verify
    with open(items_file, "r", encoding="utf-8") as f:
        items = json.load(f)

    results = []
    for it in items:
        if args.sync:
            results.append(sync_item(it))
        else:
            results.append(verify_item(it))

    for r in results:
        print(json.dumps(r, ensure_ascii=False))

    # 汇总
    stats = {}
    for r in results:
        s = r.get("status", "?")
        stats[s] = stats.get(s, 0) + 1
    print("\n=== 汇总 ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
