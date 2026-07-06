# 贡献指南

## 开发流程 (铁律)

```
WSL本地开发 → GZ验证 → 安全审计 → git tag → push
```

## 红线

1. **绝不从 GZ 裸导直推**
2. **绝不跳过隐私扫描** (`git-privacy-audit`)
3. **禁止**: API Key / 真实IP / 域名 / 密码 / Windows路径

## 提交规范

- `feat:` 新功能
- `fix:` 修复
- `docs:` 文档
- `chore:` 杂项
- `release:` 版本发布

## 版本管理

- 语义化版本: MAJOR.MINOR.PATCH
- VERSION 文件 + CHANGELOG.md 同步更新
- Tag: `git tag -a vX.Y.Z -m "说明"`

## 安全

- 每次 push 前执行隐私扫描
- GitHub Secret Scanning 已启用
- 参考 AGENTS.md 了解更多
