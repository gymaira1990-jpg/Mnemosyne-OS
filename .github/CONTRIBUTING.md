# 贡献指南

## 开发流程 (铁律)

```
本地开发 → 验证 → 安全审计 → 文档更新 → git tag → push
```

## 红线

1. **绝不硬编码密钥** — API Key / Token / 密码
2. **绝不泄漏环境信息** — 真实 IP / 域名 / 本地路径 / 用户名
3. **push 前必须隐私扫描**（参考 `git-privacy-audit` 流程）

## 提交规范

- `feat:` 新功能
- `fix:` 修复
- `docs:` 文档
- `chore:` 杂项
- `release:` 版本发布

## 版本管理

- 语义化版本: MAJOR.MINOR.PATCH
- VERSION 文件 + CHANGELOG.md + README badge 三处同步更新
- Tag: `git tag -a vX.Y.Z -m "说明"`

## 测试

```bash
pytest tests/          # 167+ 用例，必须全绿
```

## 安全

- 每次 push 前执行隐私扫描
- GitHub Secret Scanning 已启用
- 参考 AGENTS.md 了解更多
