# 安全政策

## 报告漏洞

请勿公开报告。请在 GitHub 上创建 [Security Advisory](https://github.com/gymaira1990-jpg/Mnemosyne-OS/security/advisories) 私下报告，或发送邮件至仓库主页显示的联系方式。

## 支持版本

| 版本 | 支持 |
|------|------|
| v7.x | ✅ 当前 |
| v6.x | ⚠️ 仅安全修复 |
| < v6 | ❌ |

## 安全措施

- GitHub Secret Scanning + Push Protection 已启用
- 每次 push 自动扫描密钥泄露
- `.gitignore` 排除 `.env`、`*.pem`、`*.key`
- 仓库只含 schema（零数据），不含任何真实记忆内容
