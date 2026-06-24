"""
项目注册 — 扫描 /opt/data/workspace/ → 记忆宫殿
用法: python3 register_projects.py [--dry-run]
"""
import sys, os, json, argparse, urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from archive_session import MNEMOSYNE_API as API_BASE

API_BASE = "http://127.0.0.1:18010"
WORKSPACE = os.path.expanduser("/opt/data/workspace")


def scan_workspace() -> list:
    """扫描工作区，收集项目信息"""
    projects = []
    for d in sorted(Path(WORKSPACE).iterdir()):
        if not d.is_dir() or d.name.startswith('.'):
            continue
        if (d / '.git').exists():
            info = {
                "name": d.name,
                "path": str(d),
                "description": "",
                "has_progress": False,
            }
            progress = d / "PROGRESS.md"
            if progress.exists():
                info["description"] = progress.read_text()[:500]
                info["has_progress"] = True
            projects.append(info)
    return projects


def register_project(name: str, path: str, description: str = "", dry_run: bool = False) -> dict:
    """注册项目到记忆宫殿"""
    payload = json.dumps({
        "name": name,
        "workspace_path": path,
        "description": description,
        "tenant_id": "default",
    }).encode()
    
    if dry_run:
        return {"dry_run": True, "name": name, "path": path}
    
    try:
        req = urllib.request.Request(
            f"{API_BASE}/api/v1/projects/register",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return {"registered": False, "name": name, "error": body[:100]}
    except Exception as e:
        return {"registered": False, "name": name, "error": str(e)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    
    projects = scan_workspace()
    print(f"Found {len(projects)} projects")
    print()
    
    results = []
    for p in projects:
        r = register_project(p["name"], p["path"], p["description"], args.dry_run)
        results.append(r)
        status = "📋" if args.dry_run else ("✅" if r.get("action") in ("created","updated") else "⏭️")
        detail = r.get("action", "") if not args.dry_run else "dry-run"
        desc = p["description"][:60].replace('\n',' ') if p["description"] else "(无PROGRESS)"
        print(f"  {status} {p['name']:<20} {detail:<10} {desc}")
    
    created = sum(1 for r in results if r.get("action") == "created")
    updated = sum(1 for r in results if r.get("action") == "updated")
    print(f"\nDone: {created} new, {updated} updated, {len(results)-created-updated} skipped")
