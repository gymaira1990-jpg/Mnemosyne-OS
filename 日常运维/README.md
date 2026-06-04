# 日常运维

## 一键验证

```bash
bash /opt/data/workspace/记忆宫殿/日常运维/一键验证.sh
```

检查：systemd三剑客 · SSH隧道 · LLM · Embed · Rerank · PO · SOCKS5 · TMT · 安全网

## 记忆写入 & 搜索

```bash
# 写入记忆
curl -X POST http://127.0.0.1:18010/api/v1/memories \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"default","content":"要记住的内容"}'

# 搜索记忆
curl -X POST http://127.0.0.1:18010/api/v1/memories/search \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"default","query":"搜索关键词","top_k":5}'
```

## 查看记忆树

```bash
curl -s http://127.0.0.1:18010/api/v1/tmt/tree/default | python3 -m json.tool
```

## 手动触发蒸馏

```bash
# L2 会话蒸馏
curl -X POST http://127.0.0.1:18010/api/v1/tmt/consolidate/session \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"default"}'

# L3 每日蒸馏
curl -X POST http://127.0.0.1:18010/api/v1/tmt/consolidate/daily \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"default"}'
```

## 热度衰减触发

```bash
curl -X POST http://127.0.0.1:18010/api/v1/tmt/decay \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"default"}'
```

## Hermes Cron 配置

| 任务 | 频率 | 脚本 | 状态 |
|------|------|------|:----:|
| L2 会话蒸馏 | 每10分钟 | `~/.hermes/scripts/tmt-consolidate-session.sh` | ✅ |
| L3 每日汇总 | 每天23:50 | `~/.hermes/scripts/tmt-consolidate-daily.sh` | ✅ |
| crash watchdog | 每分钟 | `watchdog.sh` | ✅ |

## 故障排查

| 症状 | 可能原因 | 解决 |
|------|---------|------|
| **搜索接口挂死** | asyncpg 参数索引错误 / BM25 关键词含中文 | 重启 Mnemosyne: `ssh gz sudo systemctl restart mnemosyne` |
| **一键验证 LLM 失败** | GPU 二进制未找到 / CUDA 路径 | 检查 systemd: `sudo systemctl status mnemo-qwen-4b` |
| **TMT L2 超时** | `-R 11435` 隧道未配，降级到 GZ CPU 模型太慢 | 检查隧道: `ssh gz 'curl -s :11435/v1/models'` |
| **autossh 端口冲突** | 旧 SSH 进程残留 / `ExitOnForwardFailure` 导致全挂 | 关 `ExitOnForwardFailure`，pkill 后重启 |
| **Hermes cron 报脚本未找到** | crontab script 字段被当文件路径解析 | 用 `hermes cron edit` 改为只传文件名 |

## 日志

```bash
# Mnemosyne 日志
ssh gz "journalctl -u mnemosyne.service -n 50"

# LLM 日志
tail -50 /home/g-cat/logs/qwen-4b.log

# 隧道日志
tail -20 /home/g-cat/logs/autossh.log

# watchdog 日志
tail -20 /home/g-cat/logs/watchdog.log
```

## GZ 保底

当 WSL 离线时，GZ 的 Qwen3.5-2B fallback (`:11437`) 自动接管 TMT 蒸馏任务：

```bash
ssh gz "systemctl status qwen3-fallback.service"
```
