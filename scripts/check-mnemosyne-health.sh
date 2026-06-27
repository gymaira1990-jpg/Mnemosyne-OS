#!/bin/bash
# Mnemosyne 健康检查 (每30分钟) — v5.1 全豆包
API_BASE="http://127.0.0.1:8010"
LOG="/var/log/mnemosyne-health.log"

# 1. Mnemosyne API
api_ok=$(curl -s --max-time 10 -o /dev/null -w "%{http_code}" "$API_BASE/api/v1/health/default" 2>/dev/null)
# 2. 豆包 Embedding (通过 Mnemosyne 内部调用, 检查 API 连通性)
embed_test=$(curl -s --max-time 10 -X POST "$API_BASE/api/v1/memories/search" -H "Content-Type: application/json" -d '{"query":"health_check","user_id":"default","top_k":1}' -o /dev/null -w "%{http_code}" 2>/dev/null)

echo "$(date '+%Y-%m-%d %H:%M:%S') api=$api_ok search=$embed_test" >> $LOG

if [ "$api_ok" != "200" ] || [ "$embed_test" != "200" ]; then
  echo "WARNING: mnemosyne health degraded" >> $LOG
fi
