#!/bin/bash
# Mnemosyne 增强健康检查 v5.5.1
# 覆盖: API连通性 + TMT蒸馏健康 + 系统资源
# 告警: 通过 GZ security-guard Hermes 分身 → 微信
API_BASE="http://127.0.0.1:8010"
LOG="/var/log/mnemosyne-health.log"
ALERT_FLAG="/tmp/mnemosyne_alert"
USER_ID="default"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $1"; }

# ── 1. API 基础健康 ──
api_code=$(curl -s --max-time 10 -o /dev/null -w "%{http_code}" "$API_BASE/api/v1/echo" 2>/dev/null)
version=$(curl -s --max-time 10 "$API_BASE/api/v1/echo" 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('version','?'))" 2>/dev/null)

# ── 2. TMT 蒸馏健康 ──
tmt_tree=$(curl -s --max-time 10 "$API_BASE/api/v1/tmt/tree/$USER_ID" 2>/dev/null)
l3_count=$(echo "$tmt_tree" | python3 -c "import sys,json;print(json.load(sys.stdin)['levels']['L3']['count'])" 2>/dev/null || echo "0")

# 最后 L3 日期 (直接查 PostgreSQL)
last_l3_date=$(sudo -u postgres psql -d mnemosyne -t -c "SELECT date FROM ag_catalog.tmt_daily WHERE user_id='default' ORDER BY date DESC LIMIT 1;" 2>/dev/null | xargs)

# ── 3. 记忆库状态 ──
stats=$(curl -s --max-time 10 "$API_BASE/api/v1/memories/stats?user_id=$USER_ID" 2>/dev/null)
total=$(echo "$stats" | python3 -c "import sys,json;print(json.load(sys.stdin)['total'])" 2>/dev/null || echo "?")

# ── 4. 系统资源 ──
mem_used=$(free -h | awk '/Mem:/{print $3}')
disk_used=$(df -h / | awk 'NR==2{print $5}')
load=$(uptime | awk -F'load average:' '{print $2}' | xargs)

# ── 4.5 备份新鲜度 (v6.2 新增: 防备份静默失败丢记忆) ──
BK_DIR="/path/to/your/backups"
latest_backup=$(ls -t "$BK_DIR"/mnemosyne-*.dump 2>/dev/null | head -1)
if [ -n "$latest_backup" ]; then
  backup_days=$(( ($(date +%s) - $(date -r "$latest_backup" +%s 2>/dev/null || echo 0)) / 86400 ))
else
  backup_days=999
fi

# ── 日志 ──
{
  log "=== Mnemosyne Health v5.5.1 ==="
  log "API: $api_code | Version: $version"
  log "TMT: L3=$l3_count | Last L3: $last_l3_date"
  log "Memories: $total total"
  log "System: mem=$mem_used disk=$disk_used load=$load"
  log "Backup: latest=$latest_backup days=$backup_days"
} >> "$LOG"

# ── 告警判断 ──
ALERT=""
ALERT_ITEMS=""

if [ "$api_code" != "200" ]; then
  ALERT="true"
  ALERT_ITEMS="$ALERT_ITEMS\n  ❌ API 不可达 (HTTP $api_code)"
fi

# TMT 蒸馏告警：超过2天没有新 L3
if [ "$last_l3_date" != "unknown" ] && [ -n "$last_l3_date" ]; then
  days_since=$(( ($(date +%s) - $(date -d "$last_l3_date" +%s 2>/dev/null || echo 0)) / 86400 ))
  if [ "$days_since" -gt 2 ] 2>/dev/null; then
    ALERT="true"
    ALERT_ITEMS="$ALERT_ITEMS\n  ⚠️ TMT L3 蒸馏停摆 ${days_since} 天 (最后: $last_l3_date)"
  fi
fi

# 磁盘告警
disk_pct=$(echo "$disk_used" | tr -d '%')
if [ "$disk_pct" -gt 85 ] 2>/dev/null; then
  ALERT="true"
  ALERT_ITEMS="$ALERT_ITEMS\n  ⚠️ 磁盘使用率 $disk_used"
fi

# 备份新鲜度告警: >10 天无新备份 (backup.sh 每周日跑)
if [ "$backup_days" -gt 10 ]; then
  ALERT="true"
  if [ "$backup_days" -eq 999 ]; then
    ALERT_ITEMS="$ALERT_ITEMS\n  ❌ 未发现任何记忆备份文件"
  else
    ALERT_ITEMS="$ALERT_ITEMS\n  ⚠️ 记忆备份过期 ${backup_days} 天 (最新: $(basename "$latest_backup"))"
  fi
fi

# ── 告警触发 ──
if [ -n "$ALERT" ]; then
  alert_msg="🚨 Mnemosyne 健康告警 $(date '+%m-%d %H:%M')\n$ALERT_ITEMS"
  echo -e "$alert_msg" > "$ALERT_FLAG"
  echo -e "$alert_msg" >> "$LOG"
  
  # 通过 Hermes security-guard 发送微信通知
  # 条件：Hermes gateway 在运行且有 WeChat 通道
  if systemctl --user is-active hermes-gateway 2>/dev/null | grep -q active; then
    export PATH="$HOME/.hermes/hermes-agent/venv/bin:$PATH"
    hermes chat -q "发送健康告警到微信：$alert_msg" -p security-guard --provider deepseek 2>> "$LOG" &
  fi
else
  rm -f "$ALERT_FLAG"
fi

log "OK"
