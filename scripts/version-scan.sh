#!/bin/bash
# Mnemosyne 发布后版本一致性扫描 v2
# 用法: bash scripts/version-scan.sh [旧版本号] [新版本号]
# 区分 当前版本引用 vs 历史记录/功能标签

set -euo pipefail

OLD="${1:-}"
NEW="${2:-}"

if [ -z "$OLD" ] || [ -z "$NEW" ]; then
  OLD=$(git tag --sort=-version:refname 2>/dev/null | head -2 | tail -1 | sed 's/^v//')
  NEW=$(git tag --sort=-version:refname 2>/dev/null | head -1 | sed 's/^v//')
  if [ -z "$OLD" ] || [ -z "$NEW" ]; then
    echo "用法: $0 <旧版本号> <新版本号>"
    exit 1
  fi
fi

echo "🔍 版本扫描: $OLD → $NEW"
FAILS=0

# 辅助：计算非功能标签的残留次数
count_non_func() {
  local file=$1 total=0 func=0
  total=$(grep -cF "$OLD" "$file" 2>/dev/null) || total=0
  func=$(grep -cE "\(v?$OLD\)" "$file" 2>/dev/null) || func=0
  echo $((total - func))
}

# ── 1. 关键字段（必须无残留） ──
echo ""
echo "=== 关键版本字段 ==="
check_key() {
  local label=$1 file=$2 pattern=$3
  local actual
  actual=$(grep -oP "$pattern" "$file" 2>/dev/null | head -1 || echo "MISSING")
  if [ "$actual" != "$NEW" ] && [ "$actual" != "v$NEW" ]; then
    echo "  ❌ $label: $actual (expected $NEW)"
    FAILS=$((FAILS + 1))
  else
    echo "  ✅ $label: $actual"
  fi
}

check_key "VERSION"     "VERSION"           '.*'
check_key "README badge" "README.md"        '(?<=version-)[\d.]+'
check_key "README_CN"   "README_CN.md"      '(?<=version-)[\d.]+'
check_key "AGENTS.md"   "AGENTS.md"         '(?<=当前: \*\*v?)[\d.]+'
check_key "CHANGELOG最新" "CHANGELOG.md"     '(?<=^## v)[\d.]+'
check_key "README版本表"  "README.md"        '(?<=\| \[v)[\d.]+(?=\]\()'
check_key "CN版本表"      "README_CN.md"     '(?<=\| \[v)[\d.]+(?=\]\()'

# ── 2. 技能文档（只检查非功能标签残留） ──
echo ""
echo "=== 技能文档 ==="
SKILL_DIR="$HOME/.hermes/skills"
for skill in $(grep -rlF "$OLD" "$SKILL_DIR" --include='SKILL.md' 2>/dev/null | grep -v 'references/' | grep -v '.archive/' | grep -v 'CHANGELOG'); do
  nf=$(count_non_func "$skill")
  if [ "$nf" -gt 0 ] 2>/dev/null; then
    sname=$(basename $(dirname "$skill"))
    echo "  ❌ $sname: $nf 处非功能标签残留"
    FAILS=$((FAILS + 1))
  fi
done
# 如果没有残留，显示全通过
if [ "$FAILS" -eq 0 ] || ! grep -rlF "$OLD" "$SKILL_DIR" --include='SKILL.md' 2>/dev/null | grep -qv 'references/\|.archive/\|CHANGELOG'; then
  echo "  ✅ 全部通过"
fi

# ── 3. Hermes Memory ──
echo ""
echo "=== Hermes Memory ==="
if grep -qF "$OLD" "$HOME/.hermes/memories/MEMORY.md" 2>/dev/null; then
  echo "  ❌ MEMORY.md 残留 $OLD"
  FAILS=$((FAILS + 1))
else
  echo "  ✅ MEMORY.md"
fi

# ── 4. GZ 运行版本 ──
echo ""
echo "=== GZ 运行版本 ==="
gz_ver=$(curl -s --max-time 5 http://127.0.0.1:18010/api/v1/echo 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('version','?'))" 2>/dev/null || echo "unreachable")
if [ "$gz_ver" = "$NEW" ]; then
  echo "  ✅ GZ: $gz_ver"
else
  echo "  ❌ GZ: $gz_ver (expected $NEW)"
  FAILS=$((FAILS + 1))
fi

# ── 5. 工作区 ──
echo ""
echo "=== 工作区 PROGRESS ==="
ws_file="/opt/data/workspace/记忆宫殿/PROGRESS.md"
if [ -f "$ws_file" ]; then
  ws_ver=$(grep '当前版本' "$ws_file" | grep -oP 'v?[\d.]+' | head -1 | sed 's/^v//')
  if [ "$ws_ver" = "$NEW" ]; then
    echo "  ✅ v$ws_ver"
  else
    echo "  ❌ v$ws_ver (expected $NEW)"
    FAILS=$((FAILS + 1))
  fi
else
  echo "  ⚠️ 工作区不可达"
fi

# ── 汇总 ──
echo ""
echo "════════════════════════════"
if [ "$FAILS" -eq 0 ]; then
  echo "✅ 版本扫描全部通过"
  exit 0
else
  echo "❌ 发现 $FAILS 处不一致"
  exit 1
fi
