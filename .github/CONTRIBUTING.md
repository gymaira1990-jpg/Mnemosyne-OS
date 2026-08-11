# 贡献指南

## 开发流程 (铁律)

```
本地开发 → 验证 → 安全审计 → 文档更新 → git tag → push
```

## 红线

1. **绝不硬编码密钥** — API Key / Token / 密码
2. **绝不泄漏环境信息** — 真实 IP / 域名 / 本地路径 / 用户名 / 内部代号（GZ 等）
3. **push 前必须隐私扫描**（参考 `git-privacy-audit` 流程）

## 仓库结构规范（新文件必须遵守）

```
Mnemosyne-OS/
  ├── main.py                 服务入口 + 核心路由（只放主逻辑）
  ├── config.py               统一配置中心（环境变量）
  ├── palace.py               宫殿核心（分类/档号/卡片/召唤）
  ├── api/                    REST API 模块
  ├── core/                   核心引擎（LLM/Embedding/Chunker/backends）
  ├── tmt/                    蒸馏引擎（factextract/distill/router）
  ├── wiki/                   WIKI 知识库模块（bm25/graph/extract/tokenize/dedupe/eval）
  ├── security/               安全审计与净化
  ├── integrations/           Hermes 集成（Memory Provider + MCP + SDK）
  ├── sync/                   端云同步（SQLite ↔ PG）
  ├── cron/                   定时脚本
  ├── docs/                   文档（白皮书/设计/schema）
  ├── deploy/                 systemd 部署模板
  ├── tests/                  pytest 用例
  └── scripts/                一次性运维脚本
```

**放置规则：**
- 模块代码 → 对应子目录（wiki 相关必须放 `wiki/`，不散落根目录）
- 运维独立脚本（reflector/drawer/perf_alert）→ 根目录（GZ crontab 绝对路径绑定）
- 文档 → `docs/`，海报源文件 `docs/poster.html`
- 新增模块先建目录再放文件，不堆积根目录

## 编辑发布规则（每次改动都遵守）

1. **版本号三处一致**：`VERSION` / README badge / CHANGELOG（改版本必须同步）
2. **双语同步**：README 与 README_CN 同步更新，链接互指
3. **文档表同步**：新增文档必须加入 README/README_CN 的 Documentation 表
4. **CHANGELOG 记录**：每次变更在顶部新增条目（新增/重写/修复/移除/脱敏分类）
5. **ROADMAP 对齐**：规划项完成时打勾并移到「已发布」区
6. **GZ 生产同步**：改了 main.py / wiki/ 等运行时文件，必须 rsync 到 GZ + 重启 + echo 验证；改了 wiki_* 路径必须同步 crontab
7. **测试**：`pytest tests/` 必须全绿（167+ 用例）
8. **安全审计**：push 前全量扫描，零命中才允许推送

## 提交规范

- `feat:` 新功能
- `fix:` 修复
- `docs:` 文档
- `chore:` 杂项
- `release:` 版本发布
- 提交信息含变更摘要 + 关键细节（参考 git log 历史风格）

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
