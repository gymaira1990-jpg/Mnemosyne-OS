#!/bin/bash
# 记忆宫殿 · 自动同步脚本
# 1. 更新状态报告
# 2. 更新进度条（基于 CHANGELOG 最新条目）
# 3. Git 提交

set -euo pipefail

WORKSPACE="/opt/data/workspace/记忆宫殿"
CHANGELOG="$WORKSPACE/CHANGELOG.md"
ROADMAP="$WORKSPACE/架构设计/升级路线图_v3.0.md"
STATUS_SCRIPT="$WORKSPACE/日常运维/status.sh"

cd "$WORKSPACE"

echo "╔══════════════════════════════════╗"
echo "║   记忆宫殿 · 自动同步             ║"
echo "╚══════════════════════════════════╝"

# 1. 运行状态报告
echo ""
echo "━━━ 当前状态 ━━━"
if [ -f "$STATUS_SCRIPT" ]; then
    bash "$STATUS_SCRIPT"
fi

# 2. 检查是否有未提交变更
if [ -z "$(git status --porcelain 2>/dev/null)" ]; then
    echo ""
    echo "✅ 工作区干净，无变更"
    exit 0
fi

# 3. 列出待提交文件
echo ""
echo "━━━ 待同步文件 ━━━"
git status --short

# 4. 自动生成提交信息
TIMESTAMP=$(date "+%Y-%m-%d %H:%M")
# 提取最新 CHANGELOG 条目标题（如果有）
if [ -f "$CHANGELOG" ]; then
    LATEST=$(grep "^## " "$CHANGELOG" | head -1 | sed 's/^## //')
else
    LATEST=""
fi

if [ -n "$LATEST" ]; then
    COMMIT_MSG="sync: $TIMESTAMP — $LATEST"
else
    COMMIT_MSG="sync: $TIMESTAMP — 自动工作区同步"
fi

# 5. 排除不必要的文件
if [ ! -f ".gitignore" ]; then
    cat > .gitignore << 'EOF'
__pycache__/
*.pyc
*.pyo
.DS_Store
*.swp
*.swo
EOF
fi

# 6. Git 提交
git add -A 2>/dev/null
# 排除 __pycache__
git reset -- __pycache__/ 2>/dev/null || true
find . -name "__pycache__" -type d -exec git reset -- {} + 2>/dev/null || true

if git diff --cached --quiet; then
    echo ""
    echo "⏭️  没有实质变更需要提交"
else
    git commit -m "$COMMIT_MSG"
    echo ""
    echo "✅ 已提交: $COMMIT_MSG"
    echo ""
    echo "━━━ 提交详情 ━━━"
    git show --stat HEAD
fi

echo ""
echo "━━━ 自动同步完成 ━━━"
echo "📅 $TIMESTAMP"
