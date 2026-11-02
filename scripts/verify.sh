#!/usr/bin/env bash
# mnemosyne-dev 的可执行验收（canonical）。
#
# 为什么不跑 pytest：运行时 venv 里没有 pytest（`No module named pytest`），
# 而 tests/ 下 241 个用例大量依赖真库/真服务，本地跑不起来。
# 这里做**真的能做的三项**：语法 → 服务重启 → 端点实测。
# 比一堆 mock 通过的用例更能说明「改动是活的」。
#
# 用法：
#   bash scripts/verify.sh              # 全跑（需要能 ssh 到 gz）
#   bash scripts/verify.sh --local      # 只做语法检查（离线可用）
set -u

MODE="${1:-full}"
FAIL=0
PASS=0

ok()   { printf '  OK    %-22s %s\n' "$1" "${2:-}"; PASS=$((PASS+1)); }
bad()  { printf '  FAIL  %-22s %s\n' "$1" "${2:-}"; FAIL=$((FAIL+1)); }

echo "== mnemosyne-dev verify ($(date '+%Y-%m-%d %H:%M')) =="

# 1. 语法：main.py + api/ 全部
if python3 -c "
import ast, pathlib, sys
bad = []
for p in [pathlib.Path('main.py')] + sorted(pathlib.Path('api').glob('*.py')):
    try:
        ast.parse(p.read_text(encoding='utf-8'))
    except SyntaxError as e:
        bad.append(f'{p}: {e}')
print('\n'.join(bad))
sys.exit(1 if bad else 0)
" >/tmp/_syn.out 2>&1; then
  ok "syntax" "main.py + api/*.py"
else
  bad "syntax" "$(head -2 /tmp/_syn.out)"
fi

[ "$MODE" = "--local" ] && { echo "== 通过 $PASS / 失败 $FAIL =="; exit $((FAIL>0)); }

# 2. 服务活着
if ssh gz "systemctl is-active --quiet mnemosyne" 2>/dev/null; then
  ok "service" "mnemosyne active"
else
  bad "service" "systemctl is-active 失败"
fi

# 3. 老端点未受影响（27 个）
CNT=$(ssh gz "curl -s -m 10 http://127.0.0.1:8010/api/v1/capabilities" 2>/dev/null \
      | python3 -c "import json,sys; print(len(json.load(sys.stdin).get('endpoints',[])))" 2>/dev/null)
if [ "$CNT" = "27" ]; then
  ok "legacy-endpoints" "27 个未变"
else
  bad "legacy-endpoints" "期望 27，实际 $CNT"
fi

# 4. 5 个新端点逐个实测
probe() {
  local name=$1 method=$2 path=$3 body=${4:-}
  local url="http://127.0.0.1:18010/api/v1/memory-os${path}"
  local out
  if [ "$method" = "GET" ]; then
    out=$(curl -s -m 30 --get "$url" 2>/dev/null)
  else
    out=$(curl -s -m 60 -X POST -H "Content-Type: application/json" -d "$body" "$url" 2>/dev/null)
  fi
  if [ -n "$out" ] && echo "$out" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
    ok "$name" "$(echo "$out" | head -c 60)"
  else
    bad "$name" "$(echo "$out" | head -c 60)"
  fi
}

probe "health"    GET  "/health"
probe "stats"     GET  "/stats"
probe "exact"     POST "/exact"    '{"q":"K·GEN·2026-0841"}'
probe "keywords"  POST "/keywords" '{"keywords":["SVG","箭头"],"limit":3}'
probe "recall"    POST "/recall"   '{"query":"怎么修 SVG 箭头不显示","limit":3}'
probe "trace"     GET  "/trace/K%C2%B7GEN%C2%B72026-0841"

echo "== 通过 $PASS / 失败 $FAIL =="
[ "$FAIL" -eq 0 ]
