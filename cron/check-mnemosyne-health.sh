#!/bin/bash
# Mnemosyne 健康检查 v5.2 — 个人版监控
API_BASE="http://127.0.0.1:8010"
LOG="/var/log/mnemosyne-health.log"
FAIL_COUNT_FILE="/tmp/mnemosyne_fail_count"

# 1. 基础健康
api_code=$(curl -s --max-time 10 -o /dev/null -w "%{http_code}" "$API_BASE/api/v1/echo" 2>/dev/null)

# 2. 搜索可达性
search_code=$(curl -s --max-time 10 -X POST "$API_BASE/api/v1/memories/search" \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"health_check\",\"user_id\":\"default\",\"top_k\":1}" \
  -o /dev/null -w "%{http_code}" 2>/dev/null)

echo "$(date "+%Y-%m-%d %H:%M:%S") api=$api_code search=$search_code" >> $LOG

if [ "$api_code" != "200" ] || [ "$search_code" != "200" ]; then
  # 故障：累加计数 + 深度诊断
  count=$(cat $FAIL_COUNT_FILE 2>/dev/null || echo 0)
  count=$((count + 1))
  echo $count > $FAIL_COUNT_FILE

  echo "=== FAIL #$count $(date) ===" >> $LOG
  echo "  api=$api_code search=$search_code" >> $LOG
  echo "  --- system ---" >> $LOG
  uptime >> $LOG
  systemctl is-active mnemosyne postgresql 2>&1 >> $LOG
  echo "  --- memory ---" >> $LOG
  free -h | head -2 >> $LOG
  echo "  --- disk ---" >> $LOG
  df -h / | tail -1 >> $LOG
  echo "  --- process ---" >> $LOG
  ps aux | grep -E "uvicorn|mnemosyne" | grep -v grep | head -3 >> $LOG
else
  # 恢复：清零
  rm -f $FAIL_COUNT_FILE
fi
