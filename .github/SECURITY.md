# 安全政策

## 报告漏洞

请勿公开报告。发送至安全邮箱或在 GitHub 上私下报告。

## 支持版本

| 版本 | 支持 |
|------|------|
| v5.3.x | ✅ |
| v5.2.x | ⚠️ 仅安全修复 |
| < v5.2 | ❌ |

## 安全措施

- GitHub Secret Scanning + Push Protection 已启用
- 每次 push 自动扫描密钥泄露
- `.gitignore` 排除 `.env`、`secrets/`
- API 文档已脱敏
