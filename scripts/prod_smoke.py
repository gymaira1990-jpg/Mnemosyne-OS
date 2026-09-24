#!/usr/bin/env python3
"""
scripts/prod_smoke.py — 正式环境冒烟测试（P4 阶段门禁命令）
===========================================================

为什么要有它
------------
2026-09-25：我在终端里手敲的 P4 验证，第一次**测法本身就是错的**
（给 L1 用的测试内容与 L0 的只差 2 字符，被 detect_conflict 判为近重复，
 于是"L1 首次应 stored"这条假失败）。手敲的测试既不可复现、也无法进闸门。
所以把它固化成脚本：**每次部署后都能一键复验，且失败退出码非 0**。

覆盖（分层写入契约）
  S1 L0 同来源重试      → duplicate 且 id 相同（幂等）
  S2 L0 跨来源          → **各存一条**（L0 只增不改、允许矛盾；旧版会误杀）
  S3 L1 首次            → stored
  S4 L1 重复            → duplicate 且 id 相同
  S5 落库 layer 标记正确（L0/L0/L1）
  S6 测试件清场（软删）

⚠️ 测试内容必须**互不相似**：S1/S2 与 S3 若只差几个字符，会被语义合并吃掉而假失败
   （这不是 bug，是 detect_conflict 的正常行为 —— 但它会让测试骗人）。

用法: python3 scripts/prod_smoke.py [BASE_URL]     默认 http://127.0.0.1:18010
退出码: 0 全过 / 1 有不过 / 2 环境不可达
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18010"


def req(method: str, path: str, body=None, timeout: int = 45):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]
    except Exception as e:  # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"


def main() -> int:
    s, v = req("GET", "/", timeout=15)
    if s != 200 or not isinstance(v, dict):
        print(f"❌ 服务不可达: {s} {v}")
        return 2
    print(f"  服务自报: {json.dumps(v, ensure_ascii=False)}")

    ts = time.strftime("%H%M%S")
    # 两段内容**刻意互不相似**，避免被语义合并干扰判据
    c_l0 = (f"smoke-alpha-{ts}: 记录一条临时便签，用于验证日志层的跨来源保留行为与幂等重试语义")
    c_l1 = (f"smoke-beta-{ts}: 关于向量索引维护窗口的技术结论，属知识类，须版本化只认最新")

    _, a1 = req("POST", "/api/v1/memories", {"user_id": "default", "content": c_l0,
                                            "category": "temp", "source": "smoke-A"})
    _, a2 = req("POST", "/api/v1/memories", {"user_id": "default", "content": c_l0,
                                            "category": "temp", "source": "smoke-A"})
    _, a3 = req("POST", "/api/v1/memories", {"user_id": "default", "content": c_l0,
                                            "category": "temp", "source": "smoke-B"})
    _, b1 = req("POST", "/api/v1/memories", {"user_id": "default", "content": c_l1,
                                            "category": "knowledge"})
    _, b2 = req("POST", "/api/v1/memories", {"user_id": "default", "content": c_l1,
                                            "category": "knowledge"})

    for tag, r in (("L0·同来源 第1发", a1), ("L0·同来源 第2发", a2), ("L0·跨来源 第1发", a3),
                   ("L1·知识 第1发", b1), ("L1·知识 第2发", b2)):
        print(f"    {tag:<14}: {json.dumps(r, ensure_ascii=False)}")

    def ok_id(x, y, status):
        if not (isinstance(x, dict) and isinstance(y, dict)):
            return False
        return x.get("status") == status and x.get("id") is not None and x.get("id") == y.get("id")

    checks = [
        ("S1 L0 同来源重试 → duplicate 同 id", ok_id(a2, a1, "duplicate")),
        ("S2 L0 跨来源 → 各存一条（L0 允许矛盾）",
         isinstance(a3, dict) and a3.get("status") == "stored" and a3.get("id") != a1.get("id")),
        ("S3 L1 首次 → stored", isinstance(b1, dict) and b1.get("status") == "stored"),
        ("S4 L1 重复 → duplicate 同 id", ok_id(b2, b1, "duplicate")),
    ]

    ids = ([i for i in {x.get("id") for x in (a1, a3, b1)
                        if isinstance(x, dict) and isinstance(x.get("id"), int)}]
           if all(c for _, c in checks[:4]) else [])
    ids.sort()
    if ids:
        q = ("SELECT id||'|'||COALESCE(metadata->>'layer','NULL') FROM memories WHERE id IN ("
             + ",".join(map(str, ids)) + ") ORDER BY id")
        p = subprocess.run(["ssh", "gz", f'sudo -u postgres psql -d mnemosyne -tAc "{q}"'],
                           capture_output=True, text=True, timeout=60)
        rows = [l.strip() for l in p.stdout.splitlines()
                if l.strip() and not any(k in l for k in ("perl", "LANG", "LC_", "supported", "Falling"))]
        layers = [r.split("|")[-1] for r in rows]
        print(f"    落库 layer: {rows}")
        checks.append(("S5 落库 layer 标记 = L0/L0/L1", len(layers) == 3 and
                       layers.count("L0") == 2 and layers.count("L1") == 1))

    # 清场（无论如何都清）
    cleaned = 0
    for mid in ids:
        st, _ = req("DELETE", f"/api/v1/memories/{mid}?user_id=default")
        cleaned += 1 if st == 200 else 0
    checks.append((f"S6 测试件清场（{cleaned}/{len(ids)}）", ids and cleaned == len(ids)))

    print()
    bad = [n for n, c in checks if not c]
    for n, c in checks:
        print(f"  {'✅' if c else '❌'} {n}")
    if bad:
        print(f"\n  ══ 正式环境冒烟：未通过（{len(bad)} 项）══")
        return 1
    print(f"\n  ══ 正式环境冒烟：全通过（{len(checks)}/{len(checks)}）══")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
