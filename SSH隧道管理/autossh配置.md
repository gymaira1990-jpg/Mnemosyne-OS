# SSH 隧道管理

## 隧道架构（6条全量）

```
Local (WSL) ←→ GZ Server (your-server-ip)

-L 18010:127.0.0.1:8010  ← Mnemosyne API（正向）
-L 3333:127.0.0.1:3333   ← Prompt Optimizer（正向）
-L 1081:127.0.0.1:1080   ← SOCKS5 → HK（正向）
-R 11434:127.0.0.1:11434 → Embed（逆隧道）
-R 11435:127.0.0.1:11435 → LLM（逆隧道）
-R 11436:127.0.0.1:11436 → Rerank（逆隧道）
```

## 启动命令

```bash
autossh -M 0 -NT -i /path/to/your-key.pem \
  -L 1081:127.0.0.1:1080 \
  -L 3333:127.0.0.1:3333 \
  -R 127.0.0.1:11434:127.0.0.1:11434 \
  -R 127.0.0.1:11436:127.0.0.1:11436 \
  -R 127.0.0.1:11435:127.0.0.1:11435 \
  -L 18010:127.0.0.1:8010 \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -o StrictHostKeyChecking=no \
  ubuntu@your-server-ip
```

## 开机自启

```bash
crontab -l | grep -q 'autossh.*gz-tunnel' || \
  (crontab -l 2>/dev/null; echo "@reboot autossh -M 0 -NT -i /path/to/your-key.pem -L 1081:127.0.0.1:1080 -L 3333:127.0.0.1:3333 -R 127.0.0.1:11434:127.0.0.1:11434 -R 127.0.0.1:11436:127.0.0.1:11436 -R 127.0.0.1:11435:127.0.0.1:11435 -L 18010:127.0.0.1:8010 -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=no ubuntu@your-server-ip") | crontab -
```

## 运维命令

```bash
# 查看隧道进程
ps aux | grep autossh

# 重启隧道
kill $(pgrep -f 'autossh.*18010') && \
autossh -M 0 -NT -i /path/to/your-key.pem ...（同上完整命令）

# 测试各端口
for p in 18010 3333 11434 11435 11436 1081; do
  ss -tlnp | grep -q ":$p " && echo "✅ :$p" || echo "❌ :$p"
done
```

## 故障排查

| 症状 | 可能原因 | 解决 |
|------|---------|------|
| autossh 进程存在但连接断开 | GZ fail2ban 封锁 | 等待10分钟自动解封 |
| `Connection refused` | fail2ban 或 SSH 服务未启动 | 控制台重启 GZ |
| 端口监听但 curl 超时 | 隧道挂起 | kill + 重启 autossh |
