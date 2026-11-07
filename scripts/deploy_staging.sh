#!/usr/bin/env bash
# deploy_staging.sh —— 把当前仓库 HEAD 推到预发布环境并验收（2026-11-08）
#
# 为什么要有这个脚本：
#   规矩写在文档里会漂，写成命令才不会忘。这是「预发布」这条规则的可执行形态：
#       local 全量测试 → **staging 部署 + 冒烟** → 人看结果 → 才动生产
#   跳过一次，就等于回到「本地测完直接上生产」。
#
# 用法：
#   bash scripts/deploy_staging.sh            # 部署 + 冒烟
#   bash scripts/deploy_staging.sh --no-smoke # 只部署
#
# 判据（任何一条不过就退出非 0，不许继续往生产推）：
#   1. 本地 git 工作区干净（避免把半成品推上去）
#   2. staging 服务启动后 /api/v1/capabilities 返回 200
#   3. staging 冒烟 6/6 通过（DB 指向 mnemosyne_staging，不是生产库）
set -euo pipefail

REPO="${REPO:-$HOME/mnemosyne-dev}"
HOST="${HOST:-gz}"
STAGING_DIR="${STAGING_DIR:-/opt/mnemosyne-staging}"
STAGING_URL="${STAGING_URL:-http://127.0.0.1:18020}"
DB="${MEMOS_DB:-mnemosyne_staging}"
DO_SMOKE=1
[[ "${1:-}" == "--no-smoke" ]] && DO_SMOKE=0

cd "$REPO"

echo "── 1/4 前置检查 ──"
if [[ -n "$(git status --porcelain)" ]]; then
  echo "❌ 工作区不干净，先提交再部署（预发布必须是可追溯的提交）"
  git status --short | head -5
  exit 1
fi
HEAD_SHA="$(git rev-parse --short HEAD)"
echo "   部署版本: $HEAD_SHA（$(git log -1 --format=%s)）"

echo "── 2/4 打包并上传 ──"
git archive --format=tar.gz HEAD -o /tmp/mne-staging.tar.gz
scp -q /tmp/mne-staging.tar.gz "$HOST:/tmp/"

echo "── 3/4 解包并重启 staging ──"
ssh "$HOST" "set -e
  sudo tar -xzf /tmp/mne-staging.tar.gz -C $STAGING_DIR
  sudo chown -R ubuntu:ubuntu $STAGING_DIR
  sudo systemctl restart mnemosyne-staging
  for i in \$(seq 1 20); do
    if curl -sf -m 3 http://127.0.0.1:8020/api/v1/capabilities >/dev/null; then echo '   staging: active'; exit 0; fi
    sleep 1
  done
  echo '❌ staging 未起来'; systemctl status mnemosyne-staging --no-pager | tail -5; exit 1"

if [[ $DO_SMOKE -eq 1 ]]; then
  echo "── 4/4 冒烟（DB=$DB）──"
  MEMOS_DB="$DB" python3 scripts/prod_smoke.py "$STAGING_URL"
else
  echo "── 4/4 已跳过冒烟（--no-smoke）──"
fi

cat <<EOF

✅ 预发布就绪：$HEAD_SHA
   访问：ssh -L 8020:127.0.0.1:8020 $HOST  （或本机隧道 $STAGING_URL）
   下一步：人工看一眼 → 通过后再执行生产部署（deploy 到 /opt/mnemosyne）
   ⚠️ staging 库是 mnemosyne_staging，写它不会影响生产
EOF
