#!/usr/bin/env python3
"""记忆回填: 根据关键词给旧记忆打项目标签 — CSV模式"""
import json, subprocess, sys, os, csv, io

sys.path.insert(0, os.path.dirname(__file__))
from backfill_projects import load_keywords, detect_project

import urllib.request
r = urllib.request.urlopen("http://127.0.0.1:18010/api/v1/projects/")
projects = {p["name"]: p["id"] for p in json.loads(r.read())["projects"]}
keywords = load_keywords()

tagged = 0
BATCH = 200

for offset in range(0, 2000, BATCH):
    sql = f"SET search_path=ag_catalog,public;\nCOPY (SELECT id,content FROM memories WHERE project_id IS NULL AND is_deleted=FALSE AND user_id='default' ORDER BY id LIMIT {BATCH} OFFSET {offset}) TO STDOUT WITH CSV;\n"
    subprocess.run(['ssh', 'gz', 'tee', '/tmp/backfill.sql'], input=sql.encode(), capture_output=True, timeout=5)
    result = subprocess.run(
        ['ssh', 'gz', 'sudo', '-u', 'postgres', 'psql', '-d', 'mnemosyne', '-A', '-t', '-f', '/tmp/backfill.sql'],
        capture_output=True, text=True, timeout=15
    )
    
    reader = csv.reader(io.StringIO(result.stdout))
    for row in reader:
        if len(row) < 2:
            continue
        try:
            mem_id = int(row[0])
            content = row[1]
        except (ValueError, IndexError):
            continue
        
        proj = detect_project(content, keywords)
        if not proj:
            continue
        pid = projects.get(proj)
        if not pid:
            continue
        
        upd = f"SET search_path=ag_catalog,public; UPDATE memories SET project_id={pid} WHERE id={mem_id};\n"
        subprocess.run(['ssh', 'gz', 'tee', '/tmp/backfill_upd.sql'], input=upd.encode(), capture_output=True, timeout=5)
        subprocess.run(['ssh', 'gz', 'sudo', '-u', 'postgres', 'psql', '-d', 'mnemosyne', '-f', '/tmp/backfill_upd.sql'],
                       capture_output=True, timeout=5)
        tagged += 1
        if tagged <= 20:
            print(f"  #{mem_id} → {proj}: {content[:60]}...")

print(f"\nDone: {tagged} memories tagged")

for proj, pid in projects.items():
    cnt_sql = f"SET search_path=ag_catalog,public; SELECT count(*) FROM memories WHERE project_id={pid} AND is_deleted=FALSE;\n"
    subprocess.run(['ssh', 'gz', 'tee', '/tmp/backfill_cnt.sql'], input=cnt_sql.encode(), capture_output=True)
    r = subprocess.run(['ssh', 'gz', 'sudo', '-u', 'postgres', 'psql', '-d', 'mnemosyne', '-A', '-t', '-f', '/tmp/backfill_cnt.sql'],
                      capture_output=True, text=True, timeout=5)
    print(f"  {proj}: {r.stdout.strip()}")
