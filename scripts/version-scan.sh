#!/bin/bash
# Mnemosyne 发布后版本一致性扫描
# 用法: bash scripts/version-scan.sh [旧版本号] [新版本号]
# 默认: 旧=5.5.0 新=5.5.1 (可从 VERSION 文件自动读取)

set -euo pipefail

OLD="${1:-}"
NEW="${2:-}"

if [ -z "$OLD" ] || [ -z "$NEW" ]; then
  # 尝试从 git tags 推断
  OLD=$(git tag --sort=-version:refname | head -2 | tail -1 | sed 's/^v//')
  NEW=$(git tag --sort=-version:refname | head -1 | sed 's/^v//')
  if [ -z "$OLD" ] || [ -z "$NEW" ]; then
    echo "用法: $0 <旧版本号> <新版本号>"
    echo "示例: $0 5.5.0 5.5.1"
    exit 1
  fi
fi

echo "🔍 扫描 $OLD → $NEW 版本残留..."

FOUND=0

# ── 1. 仓库文件 ──
echo ""
echo "=== 仓库文件 (mnemosyne-dev) ==="
for f in VERSION README.md README_CN.md CHANGELOG.md AGENTS.md; do
  if [ -f "$f" ]; then
    hits=$(grep -c "$OLD" "$f" 2>/dev/null || echo 0)
    if [ "$hits" -gt 0 ]; then
      echo "  ❌ $f: $hits 处残留 $OLD"
      FOUND=$((FOUND + 1))
    else
      echo "  ✅ $f"
    fi
  fi
done

# ── 2. 技能文档 ──
echo ""
echo "=== 技能文档 (~/.hermes/skills) ==="
SKILL_DIR="$HOME/.hermes/skills"
for skill in $(grep -rl "$OLD" "$SKILL_DIR" --include='*.md' 2>/dev/null | grep -v 'references/' | grep -v '.archive/' | grep -v 'CHANGELOG'); do
  # 区分功能标签(如 "(v5.5.0)") 和当前版本
  func_tags=$(grep -c "($OLD)" "$skill" 2>/dev/null || echo 0)
  other_hits=$(grep -c "$OLD" "$skill" 2>/dev/null || echo 0)
  if [ "$func_tags" -lt "$other_hits" ]; then
    echo "  ❌ $skill: $(basename "$skill")"
    FOUND=$((FOUND + 1))
  fi
done

# 检查所有技能
for skill in $(grep -rl "$OLD" "$SKILL_DIR" --include='SKILL.md' 2>/dev/null | grep -v 'references/' | grep -v '.archive/' | grep -v 'CHANGELOG'); do
  hits=$(grep -c "$OLD" "$skill" 2>/dev/null || echo 0)
  func_tags=$(grep -c "($OLD)" "$skill" 2>/dev/null || echo 0)
  if [ "$hits" -gt "$func_tags" ]; then
    echo "  ❌ $(basename $(dirname "$skill")): $((hits - func_tags)) 处非功能标签残留"
    FOUND=$((FOUND + 1))
  fi
done

# ── 3. Hermes Memory ──
echo ""
echo "=== Hermes Memory ==="
if grep -q "$OLD" "$HOME/.hermes/memories/MEMORY.md" 2>/dev/null; then
  echo "  ❌ MEMORY.md 残留 $OLD"
  FOUND=$((FOUND + 1))
else
  echo "  ✅ MEMORY.md"
fi

# ── 4. GZ 运行版本 ──
echo ""
echo "=== GZ 运行版本 ==="
gz_ver=$(curl -s --max-time 5 http://127.0.0.1:18010/api/v1/echo 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('version','?'))" 2>/dev/null || echo "unreachable")
echo "  GZ echo: $gz_ver"
if [ "$gz_ver" != "$NEW" ]; then
  echo "  ❌ GZ 运行 $gz_ver ≠ 预期 $NEW"
  FOUND=$((FOUND + 1))
fi

# ── 5. 工作区 PROGRESS ──
echo ""
echo "=== 工作区 ==="
if [ -f "/opt/data/workspace/记忆宫殿/PROGRESS.md" ]; then
  ws_ver=$(grep '当前版本' /opt/data/workspace/记忆宫殿/PROGRESS.md | grep -oP 'v?[\d.]+' | head -1 | sed 's/^v//')
  echo "  PROGRESS: v$ws_ver"
  if [ "$ws_ver" != "$NEW" ]; then
    echo "  ❌ 工作区 $ws_ver ≠ $NEW"
    FOUND=$((FOUND + 1))
  fi
else
  echo "  ⚠️ 工作区不可达"
fi

# ── 汇总 ──
echo ""
echo "════════════════════════════"
if [ "$FOUND" -eq 0 ]; then
  echo "✅ 版本扫描通过 ($OLD → $NEW)"
  exit 0
else
  echo "❌ 发现 $FOUND 处版本残留"
  exit 1
fi
