# 日常运维

## 一键验证

```bash
bash /opt/data/workspace/记忆宫殿/日常运维/一键验证.sh
```

检查：隧道 · Mnemosyne · LLM · Embed · Rerank · PO · SOCKS5 · TMT

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

## 查看记忆树

```bash
curl -s http://127.0.0.1:18010/api/v1/tmt/tree/default | python3 -m json.tool
```

## 热度衰减触发

```bash
curl -X POST http://127.0.0.1:18010/api/v1/tmt/decay \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"default"}'
```

## Hermes Cron 配置

| 任务 | 频率 | API |
|------|------|-----|
| L2 蒸馏 | 每10分钟 | `POST /tmt/consolidate/session` |
| L3 每日 | 每天23:50 | `POST /tmt/consolidate/daily` |

## 故障排查

见 `SSH隧道管理/autossh配置.md` → 故障排查章节
