#!/bin/bash
# 记忆宫殿 · 快速状态报告
# 用法: bash 日常运维/status.sh

echo "╔══════════════════════════════════════╗"
echo "║      🏰 记忆宫殿 · 状态报告          ║"
echo "╚══════════════════════════════════════╝"
echo ""

# 服务状态
echo "━━━ 服务状态 ━━━"
for svc in mnemo-qwen-4b mnemo-embed mnemo-rerank; do
  s=$(systemctl is-active "$svc" 2>/dev/null)
  icon="✅"; [ "$s" != "active" ] && icon="❌"
  echo "$icon $svc: $s"
done

# 隧道
echo ""
echo "━━━ SSH 隧道 ━━━"
if pgrep -f "autossh.*tencent-gz" >/dev/null 2>&1; then
  echo "✅ autossh (PID $(pgrep -f 'autossh.*tencent-gz' | head -1))"
else
  echo "❌ 隧道未运行"
fi

# GZ 可达
echo ""
echo "━━━ GZ Mnemosyne ━━━"
code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18010/api/v1/echo 2>/dev/null || echo "000")
[ "$code" = "200" ] && echo "✅ HTTP $code" || echo "❌ HTTP $code"

# 队列
echo ""
echo "━━━ 持久队列 ━━━"
pending=$(sqlite3 ~/.hermes/mnemosyne_queue.db "SELECT count(*) FROM pending WHERE status='pending'" 2>/dev/null || echo "?")
echo "📊 $pending 条待发送"

# 版本
echo ""
echo "━━━ 版本信息 ━━━"
grep "^v2\." /opt/data/workspace/记忆宫殿/架构设计/升级路线图_v3.0.md 2>/dev/null | head -1
echo ""
grep "Phase [12]" /opt/data/workspace/记忆宫殿/架构设计/升级路线图_v3.0.md 2>/dev/null | tail -3
