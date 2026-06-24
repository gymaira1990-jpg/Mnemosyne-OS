#!/usr/bin/env python3
"""
记忆回填 — 根据关键词自动给旧记忆打项目标签
用法: python3 backfill_projects.py [--dry-run]
"""
import sys, os, json, argparse, urllib.request

API = "http://127.0.0.1:18010"
KEYWORDS_FILE = os.path.join(os.path.dirname(__file__), "project_keywords.json")


def load_keywords():
    with open(KEYWORDS_FILE) as f:
        return json.load(f)


def detect_project(content: str, keywords: dict) -> str:
    """根据内容检测所属项目"""
    content_lower = content.lower()
    scores = {}
    for project, words in keywords.items():
        score = sum(1 for w in words if w.lower() in content_lower)
        if score > 0:
            scores[project] = score
    if not scores:
        return None
    return max(scores, key=scores.get)


def get_project_id(name: str) -> int:
    """获取项目ID"""
    r = urllib.request.urlopen(f"{API}/api/v1/projects/by-name/{name}")
    data = json.loads(r.read())
    # The by-name endpoint returns memories, but we need the project ID
    # Use the list endpoint instead
    return None


def get_all_projects() -> dict:
    """获取所有项目 name→id 映射"""
    r = urllib.request.urlopen(f"{API}/api/v1/projects/?tenant_id=default")
    data = json.loads(r.read())
    return {p["name"]: p["id"] for p in data["projects"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch", type=int, default=100)
    args = parser.parse_args()
    
    keywords = load_keywords()
    projects = get_all_projects()
    print(f"Projects: {list(projects.keys())}")
    print(f"Keywords loaded for {len(keywords)} projects")
    
    # Get memories from GZ directly via SSH+psql
    import subprocess
    result = subprocess.run(
        ['ssh', 'gz', 'sudo -u postgres psql -d mnemosyne -t -c',
         "SET search_path=ag_catalog,public; SELECT id,content FROM memories WHERE project_id IS NULL AND is_deleted=FALSE AND user_id='default' ORDER BY id LIMIT 200"],
        capture_output=True, text=True
    )
    
    tagged = 0
    for line in result.stdout.strip().split('\n'):
        line = line.strip()
        if not line or '|' not in line:
            continue
        parts = line.split('|', 1)
        if len(parts) != 2:
            continue
        try:
            mem_id = int(parts[0].strip())
            content = parts[1].strip()
        except ValueError:
            continue
        
        project = detect_project(content, keywords)
        if not project:
            continue
        
        pid = projects.get(project)
        if not pid:
            continue
        
        if args.dry_run:
            print(f"  #{mem_id} → {project} [{content[:60]}...]")
        else:
            # Tag via direct SQL
            subprocess.run(['ssh', 'gz', 
                f'sudo -u postgres psql -d mnemosyne -c "SET search_path=ag_catalog,public; UPDATE memories SET project_id={pid} WHERE id={mem_id}"'],
                capture_output=True)
        tagged += 1
    
    print(f"\nTagged: {tagged} memories")
    if args.dry_run:
        print("(dry-run, no changes made)")
