# SSH 隧道管理

## 隧道架构（8条全量）

```
Local (WSL) ←→ GZ Server (your-server-ip:2222)

-L 18010:127.0.0.1:8010  ← Mnemosyne API（正向）
-L 3333:127.0.0.1:3333   ← Prompt Optimizer MCP（正向）
-L 1081:127.0.0.1:1080   ← SOCKS5 → HK（正向）
-R 11434:127.0.0.1:11434 → Embedding（逆隧道，导出到GZ）
-R 11435:127.0.0.1:11435 → LLM（逆隧道，GZ可用WSL GPU↑）
-R 11436:127.0.0.1:11436 → Rerank（逆隧道，导出到GZ）
```

## 启动命令

```bash
autossh -M 0 -NT -i /path/to/your-key.pem \
  -L 1081:127.0.0.1:1080 \
  -L 3333:127.0.0.1:3333 \
  -L 18010:127.0.0.1:8010 \
  -R 127.0.0.1:11434:127.0.0.1:11434 \
  -R 127.0.0.1:11435:127.0.0.1:11435 \
  -R 127.0.0.1:11436:127.0.0.1:11436 \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  -p 2222 \
  ubuntu@your-server-ip
```

> **注意**: GZ 的 SSH 端口为 **2222**（非默认22）。22端口也开但主要用于 fail2ban 防扫描。
> **不设** `ExitOnForwardFailure`——防止单端口冲突导致全隧道挂死。

## 开机自启

crontab @reboot:
```
@reboot sleep 15 && /home/g-cat/.hermes/bin/start-gz-tunnels.sh
```

## 隧道脚本

```bash
# 脚本位置
/home/g-cat/.hermes/bin/start-gz-tunnels.sh

# 人工重启（连ssh -p 2222）
bash /home/g-cat/.hermes/bin/start-gz-tunnels.sh
```

## 运维命令

```bash
# 查看隧道进程
ps aux | grep autossh

# 强制重启（杀干净旧连接）
pkill -9 -f "autossh.*tencent-gz"
pkill -9 -f "ssh.*tencent-gz"
sleep 2
bash /home/g-cat/.hermes/bin/start-gz-tunnels.sh

# 测试各端口（本地）
for p in 18010 3333 11434 11435 11436 1081; do
  ss -tlnp | grep -q ":$p " && echo "✅ :$p" || echo "❌ :$p"
done

# 测试远程转发（从GZ角度）
ssh gz "for p in 11434 11435 11436; do
  curl -sf http://127.0.0.1:\$p/v1/models > /dev/null && echo \"✅ :\$p\" || echo \"❌ :\$p\"
done"
```

## 故障排查

| 症状 | 可能原因 | 解决 |
|------|---------|------|
| autossh 进程存在但端口不监 | 旧 SSH 进程占端口 | `pkill -9 -f "ssh.*gz"` 后重启 |
| `remote port forwarding failed` | GZ 端口被其他进程占 | `ssh gz "ss -tlnp | grep <PORT>"` 查占用 |
| `Address already in use` | 本地端口 CLOSE_WAIT | 等几秒或 `fuser -k <PORT>/tcp` |
| curl :18010 超时但 ssh 正常 | Mnemosyne 进程卡住 | `ssh gz "sudo kill -9 \$(pgrep -f main.py)" && sudo systemctl start mnemosyne` |
| 搜索 POST 挂死 | asyncpg 参数索引错误 | 重启 Mnemosyne 即可恢复 |
