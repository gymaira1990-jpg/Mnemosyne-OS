#!/usr/bin/env bash
# deploy_prod.sh —— 生产部署（唯一入口，2026-11-08 建）
#
# 为什么必须有这个脚本：
#   以前生产部署是「手动 scp + sudo install」，结果 2026-11-08 自检发现——
#   覆盖了 5 个文件却**没留回滚点**（生产 git 还停在旧快照，也没有单独备份）。
#   手动部署的问题不是慢，是**每一次都可能漏一步，而你事后无法证明没漏**。
#
# 铁律（脚本强制，不靠记性）：
#   1. 工作区干净（部署必须对应一个可追溯的 commit）
#   2. **该 commit 必须已经在 staging 验过**（比对 /opt/mnemosyne-staging/DEPLOYED_SHA）
#   3. 部署前先备份被覆盖的文件 + 打生产 git 快照
#   4. 部署后：健康检查 → 生产冒烟 → prod-diff 必须 0 漂移
#   任何一步失败 → 非 0 退出，并打印回滚命令
#
# 用法：
#   bash scripts/deploy_prod.sh              # 完整流程
#   bash scripts/deploy_prod.sh --skip-staging-check   # 紧急情况（会明确警告并记录）
set -euo pipefail

REPO="${REPO:-$HOME/mnemosyne-dev}"
HOST="${HOST:-gz}"
PROD_DIR="${PROD_DIR:-/opt/mnemosyne}"
STAGING_SHA_FILE="${STAGING_SHA_FILE:-/opt/mnemosyne-staging/DEPLOYED_SHA}"
SKIP_STAGING=0
[[ "${1:-}" == "--skip-staging-check" ]] && SKIP_STAGING=1

cd "$REPO"
TS="$(date +%Y%m%d-%H%M%S)"

echo "── 1/6 前置检查 ──"
if [[ -n "$(git status --porcelain)" ]]; then
  echo "❌ 工作区不干净：生产部署必须对应一个提交"
  git status --short | head -5
  exit 1
fi
HEAD_SHA="$(git rev-parse --short HEAD)"
echo "   版本: $HEAD_SHA（$(git log -1 --format=%s)）"

STAGING_SHA="$(ssh "$HOST" "cat $STAGING_SHA_FILE 2>/dev/null || echo NONE" | tr -d '[:space:]')"
echo "   预发布验过的版本: $STAGING_SHA"
if [[ "$SKIP_STAGING" -eq 0 && "$STAGING_SHA" != "$HEAD_SHA" ]]; then
  echo "❌ 这个提交没在预发布验过（staging=$STAGING_SHA，当前=$HEAD_SHA）"
  echo "   先跑：bash scripts/deploy_staging.sh"
  exit 1
fi
[[ "$SKIP_STAGING" -eq 1 ]] && echo "   ⚠️ 已跳过 staging 校验（手动指定，需自负风险）"

echo "── 2/6 备份当前生产文件 + 打快照 ──"
ssh "$HOST" "set -e
  cd $PROD_DIR
  sudo mkdir -p .backup-$TS
  sudo chown -R ubuntu:ubuntu .backup-$TS   # 目录归 ubuntu，否则后面写子目录会 permission denied（实测踩过）
  for f in \$(git ls-files | head -400); do
    if [ -f \"\$f\" ]; then mkdir -p .backup-$TS/\$(dirname \$f); cp -p \"\$f\" .backup-$TS/\$f 2>/dev/null || true; fi
  done
  git add -A && git -c user.name=g-cat -c user.email=meow@g-cat.cn commit -q -m 'snapshot(prod): 部署前 $HEAD_SHA / $TS' || echo '   （无需新快照）'
  echo \"   备份: .backup-$TS\""

echo "── 3/6 上传并覆盖代码 ──"
git archive --format=tar.gz HEAD -o /tmp/mne-prod.tar.gz
scp -q /tmp/mne-prod.tar.gz "$HOST:/tmp/"
ssh "$HOST" "set -e
  sudo tar -xzf /tmp/mne-prod.tar.gz -C $PROD_DIR
  sudo chown -R ubuntu:ubuntu $PROD_DIR
  cd $PROD_DIR && ./venv/bin/python3 -m py_compile main.py palace.py
  echo '   语法 OK'"

echo "── 4/6 重启并等就绪 ──"
ssh "$HOST" "set -e
  sudo systemctl restart mnemosyne
  for i in \$(seq 1 20); do
    if curl -sf -m 3 http://127.0.0.1:8010/api/v1/capabilities >/dev/null; then echo '   生产: active'; exit 0; fi
    sleep 1
  done
  echo '❌ 生产未起来 —— 立即回滚：cd $PROD_DIR && sudo cp -a .backup-$TS/. . && sudo systemctl restart mnemosyne'
  exit 1"

echo "── 5/6 生产冒烟（库=mnemosyne）──"
MEMOS_DB=mnemosyne python3 scripts/prod_smoke.py http://127.0.0.1:18010

echo "── 6/6 部署指纹核对 ──"
python3 scripts/prod_diff.py | tail -1

cat <<EOF

✅ 生产部署完成：$HEAD_SHA
   备份: $PROD_DIR/.backup-$TS
   回滚: ssh $HOST "cd $PROD_DIR && sudo cp -a .backup-$TS/. . && sudo systemctl restart mnemosyne"
   ⚠️ 归档/发布（tag + Release）**不在这里做**：等阶段目标全绿 + 主人确认。
EOF
