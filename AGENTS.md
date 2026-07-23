# Mnemosyne OS · Agent 使用手册

> Hermes Agent / AI 编码助手 进入本仓库时自动加载。
> 解决"分身记不住怎么用"的问题。

## 项目定位

认知型记忆操作系统。AI 长期记忆宫殿。五层时间记忆树(TMT)，三馆闭环，知识图谱，端云同步。

## 架构

```
/opt/mnemosyne/ (GZ 生产) ← 本仓库 (唯一真相源)
  ├── main.py          FastAPI 服务 (38路由)
  ├── core/            核心引擎 (LLM/Embedding/Chunker)
  ├── api/             REST API
  ├── tmt/             时间记忆树 (L1-L5)
  ├── security/        安全审计
  ├── integrations/    Hermes 集成
  │   ├── hermes-mcp/      MCP Bridge (15 tools)
  │   └── hermes-provider/ Memory Provider v5.3.0 (10/10 Hooks)
  ├── skills/          Hermes 技能 (4个)
  ├── cron/            定时脚本
  ├── docs/            白皮书
  └── deploy/          systemd 部署
```

## 版本

当前: **v5.4.0**
- GZ 运行: v5.4.0
- 版本号: 语义化 (MAJOR.MINOR.PATCH)
- 版本文件: `VERSION`

## 开发流程 (铁律)

```
本地(WSL)开发 → GZ 验证 → 隐私扫描 → 文档更新 → git tag → push
```

### 红线

1. **绝不从 GZ 裸导直推** — 必须走本地构建
2. **绝不跳过隐私扫描** — `git-privacy-audit` 硬门禁
3. **禁止内容**: API Key / 真实IP / 域名 / 密码 / Windows路径
4. **教训 0702**: noah-gen3-type2 硬编码 DS Key → ¥500+ 被盗刷

### 提交规范

- `feat:` 新功能
- `fix:` 修复
- `docs:` 文档
- `chore:` 杂项
- `release:` 版本发布

## 部署到 GZ

```bash
# 同步代码
rsync -avz --exclude='.git' --exclude='venv' ./ gz:/opt/mnemosyne/

# 重启服务
ssh gz "sudo systemctl restart mnemosyne"
```

## 技能说明

本仓库含 4 个 Hermes 技能:
- `mnemosyne-os-usage` — 使用指南
- `mnemosyne-integration` — Hermes 集成
- `mnemosyne-progress` — 进度追踪
- `mnemosyne-version-publish` — 版本发布

## 相关仓库

- GitHub: gymaira1990-jpg/Mnemosyne-OS (官方)
- 历史: 从 noah-gen3-type2 子功能独立 (2026-06)
