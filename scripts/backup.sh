#!/usr/bin/env bash
# backup.sh —— 可验证的 PostgreSQL 备份（生产脚本的通用化版本）
#
# 这份不是我凭空写的：来自生产服务器上跑了两个多月的 `/opt/mnemosyne/backup.sh`，
# 把那版踩过的坑原样带过来，只做三件事：写死的主机/路径改成环境变量、
# 补上「备份能不能读回来」的校验、把异地副本做成可选。
#
# 带着的历史（别删，都是真事）：
#   · 2026-09-23：日志文件属主被改成 root 后 `2>>$LOG` 打不开，`set -e` 直接退出，
#     **静默失败 36 天**（末次成功 08-18）→ 所以日志必须落在自己可写的目录，失败要显式写 ALERT。
#   · 2026-09-27：crontab 被重复注册，同一脚本被 cron 起两次抢同一个 dump → 后到者失败报假警
#     → 所以加 flock 自锁，拿不到锁**静默退出**（这不是故障）。
#
# 用法：
#   bash scripts/backup.sh                 # 备份 + 校验 + 本地保留 8 份
#   KEEP=14 bash scripts/backup.sh
#   OFFSITE_HOST=user@host OFFSITE_PORT=2222 OFFSITE_KEY=~/.ssh/id_offsite bash scripts/backup.sh
#   bash scripts/backup.sh --list          # 只看现状，不产出新文件
#
# 恢复（演练过再睡；务必用另一个库名，别在生产库上 --clean）：
#   pg_restore -h 127.0.0.1 -U mnemosyne -d mnemosyne_restore --clean --if-exists <dump>
#
# 退出码：0 = 成功（或并发跳过）；1 = 失败（已写 ALERT 文件 + 可选通知）
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

# ── 配置（全部可用环境变量覆盖）──
DB=${PGDATABASE:-mnemosyne}
BK_DIR=${BK_DIR:-$HOME/mnemosyne-backups}
KEEP=${KEEP:-8}
OFFSITE_HOST=${OFFSITE_HOST:-}          # 空 = 不做异地副本
OFFSITE_PORT=${OFFSITE_PORT:-22}
OFFSITE_KEY=${OFFSITE_KEY:-}
OFFSITE_DIR=${OFFSITE_DIR:-mnemosyne-backups}
OFFSITE_KEEP=${OFFSITE_KEEP:-3}
NOTIFY_CMD=${NOTIFY_CMD:-}              # 可选：告警命令，$SUBJECT/$BODY 会传进环境
LOG_FILE="$BK_DIR/backup.log"
ALERT_FILE="$BK_DIR/backup.alert"
STAMP=$(date +%Y%m%d_%H%M)
LOCK_FILE="${TMPDIR:-/tmp}/mnemosyne-backup.lock"
TMPD=${TMPDIR:-/tmp}

mkdir -p "$BK_DIR" 2>/dev/null || { echo "❌ 建不了备份目录 $BK_DIR"; exit 1; }
log() { echo "$(date '+%F %T'): $*" >> "$LOG_FILE" 2>/dev/null || echo "$*"; }

fail() {
  log "FAIL: $*"
  { echo "$(date '+%F %T') 备份失败"; echo "$*"; } > "$ALERT_FILE" 2>/dev/null
  if [ -n "$NOTIFY_CMD" ]; then SUBJECT="🚨 Mnemosyne 备份失败" BODY="$*" bash -c "$NOTIFY_CMD" >>"$LOG_FILE" 2>&1 || true; fi
  exit 1
}
trap 'fail "unexpected error at line $LINENO (script aborted)"' ERR

# ── --list：只看现状 ──
if [ "${1:-}" = "--list" ]; then
  ls -lh "$BK_DIR"/mnemosyne-*.dump 2>/dev/null | tail -10 || echo "   · 目录里还没有备份"
  latest=$(ls -1t "$BK_DIR"/mnemosyne-*.dump 2>/dev/null | head -1 || true)
  if [ -n "$latest" ]; then
    age_h=$(( ( $(date +%s) - $(stat -c %Y "$latest") ) / 3600 ))
    echo "   · 最近一份：$(basename "$latest")，${age_h} 小时前"
    [ "$age_h" -gt 48 ] && echo "   ❌ 超过 48 小时没备份了"
  fi
  [ -f "$ALERT_FILE" ] && echo "   ❌ 存在未清除的告警：$ALERT_FILE"
  exit 0
fi

# ── 0. 并发自锁：同一时刻只允许一个实例 ──
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  log "skip: 已有备份实例在运行（锁 $LOCK_FILE）—— 本次退出（不是故障）"
  exit 0
fi

# ── 1. dump（能免密 sudo 到 postgres 就走它，否则用 PG 环境变量）──
command -v pg_dump >/dev/null 2>&1 || fail "找不到 pg_dump（装 postgresql-client）"
OUT="$BK_DIR/mnemosyne-${STAMP}.dump"
TMP_FILE="$TMPD/mnemosyne-${STAMP}-$$.dump"   # $$ 防同名互撞

if sudo -n -u postgres true >/dev/null 2>&1; then
  sudo -u postgres pg_dump -d "$DB" --format=custom --file="$TMP_FILE" >>"$LOG_FILE" 2>&1 || fail "pg_dump 失败 —— 详见 $LOG_FILE"
  sudo chown "$(id -un):$(id -gn)" "$TMP_FILE" >>"$LOG_FILE" 2>&1 || true
else
  pg_dump -h "${PGHOST:-127.0.0.1}" -p "${PGPORT:-5432}" -U "${PGUSER:-postgres}" -d "$DB" \
    --format=custom --file="$TMP_FILE" >>"$LOG_FILE" 2>&1 || fail "pg_dump 失败 —— 详见 $LOG_FILE"
fi
mv "$TMP_FILE" "$OUT" || fail "移动 dump 到 $BK_DIR 失败"

SIZE_B=$(stat -c %s "$OUT" 2>/dev/null || echo 0)
[ "$SIZE_B" -gt 10240 ] || fail "dump 只有 $SIZE_B 字节，不正常"
log "backup OK -> $(basename "$OUT") ($((SIZE_B/1024)) KB)"

# ── 2. 立刻验：能被 pg_restore 读出来才算备份 ──
# （生产那版没有这一步。教训：磁盘上有文件 ≠ 有一个能恢复的备份。）
if command -v pg_restore >/dev/null 2>&1; then
  if pg_restore --list "$OUT" >"$TMPD/pg_restore.list" 2>>"$LOG_FILE"; then
    TBL=$(grep -c ' TABLE DATA ' "$TMPD/pg_restore.list" 2>/dev/null || echo 0)
    [ "${TBL:-0}" -gt 0 ] || fail "pg_restore 能读但没有 TABLE DATA 段 —— dump 不完整"
    log "verify OK: 含 $TBL 张表的数据段"
  else
    fail "pg_restore --list 失败 —— dump 不可读，别指望它能恢复"
  fi
else
  log "WARN: 没有 pg_restore，跳过可读校验（不推荐）"
fi
command -v sha256sum >/dev/null 2>&1 && sha256sum "$OUT" > "$OUT.sha256" 2>/dev/null

# ── 3. 异地副本（可选，OFFSITE_HOST 为空就跳过）──
if [ -n "$OFFSITE_HOST" ]; then
  SSH_OPTS=(-o ConnectTimeout=10 -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
  [ -n "$OFFSITE_KEY" ] && SSH_OPTS+=(-i "$OFFSITE_KEY")
  if ssh "${SSH_OPTS[@]}" -p "$OFFSITE_PORT" "$OFFSITE_HOST" true 2>/dev/null; then
    if scp -q "${SSH_OPTS[@]}" -P "$OFFSITE_PORT" "$OUT" "$OFFSITE_HOST:$OFFSITE_DIR/" 2>>"$LOG_FILE"; then
      ssh "${SSH_OPTS[@]}" -p "$OFFSITE_PORT" "$OFFSITE_HOST" \
        "ls -t $OFFSITE_DIR/mnemosyne-*.dump 2>/dev/null | tail -n +$((OFFSITE_KEEP+1)) | xargs -r rm -f" 2>>"$LOG_FILE" \
        && log "offsite copy OK -> $OFFSITE_HOST:$OFFSITE_DIR (keep $OFFSITE_KEEP)" \
        || log "WARN: 异地清理失败"
    else
      log "WARN: 异地 scp 失败 —— 本地 dump 已生成，下次重试"
    fi
  else
    log "WARN: 异地主机不可达 —— 跳过异地副本"
  fi
fi

# ── 4. 本地清理：只动自己命名的文件 ──
{ ls -t "$BK_DIR"/mnemosyne-*.dump 2>/dev/null || true; } | tail -n +$((KEEP+1)) | xargs -r rm -f
rm -f "$ALERT_FILE"
COUNT=$( { ls -1 "$BK_DIR"/mnemosyne-*.dump 2>/dev/null || true; } | wc -l )
log "cleanup done (keep $KEEP) — 现有 $COUNT 份"
echo "✅ 备份完成：$OUT（$((SIZE_B/1024)) KB，本地共 $COUNT 份）"
echo "   恢复演练：pg_restore -d mnemosyne_restore --clean --if-exists $OUT"
exit 0
