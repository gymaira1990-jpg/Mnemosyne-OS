#!/bin/bash
# Git pre-commit hook: 自动更新升级路线图进度条
# 安装: ln -sf ../../../日常运维/pre-commit-hook.sh .git/hooks/pre-commit

set -euo pipefail

ROADMAP="架构设计/升级路线图_v3.0.md"
CHANGELOG="CHANGELOG.md"

# 只在路线图或 CHANGELOG 被 staged 时运行
if ! git diff --cached --name-only | grep -qE "$ROADMAP|$CHANGELOG"; then
    exit 0
fi

# 更新CHANGELOG日期格式（如果当前条目没有日期，加一个）
# 主要功能：确保每次提交前工作区是最新的

# 检查路线图进度条是否需要更新
if [ -f "$ROADMAP" ] && [ -f "$CHANGELOG" ]; then
    # 从 CHANGELOG 提取最新进展
    LATEST_PHASE=$(grep "^## " "$CHANGELOG" | head -1 | sed 's/^## //')
    
    # 如果有 Phase 2 的条目，更新进度条
    if echo "$LATEST_PHASE" | grep -qi "phase 2\|辨证推理\|二级读取\|会话切"; then
        # 路线图的进度条可能已经包含了更新，不需要修改
        # 这里留作将来自动计算进度
        true
    fi
fi

# 确保 staged 的是最新版本
git add -u "$ROADMAP" "$CHANGELOG" 2>/dev/null || true
