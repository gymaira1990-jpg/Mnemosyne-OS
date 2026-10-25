# Security Policy

## Supported Versions

只有最新的次版本号接收安全修复：

| Version | Supported |
|---|---|
| 8.0.x | ✅ |
| 7.8.x 及更早 | ❌ |

## Reporting a Vulnerability

**请不要开公开 issue。**

请通过 GitHub 的私密渠道报告：

1. 打开仓库的 **Security** 标签页 → **Report a vulnerability**
   （即 GitHub Security Advisories，仅仓库维护者可见）
2. 说明：受影响的版本、复现步骤、影响面（数据泄露 / 越权 / 拒绝服务）、
   以及你建议的修复方向（可选）

我们会在收到后 **7 天内**给出初步回应，并在修复发布后于 Advisory 中致谢
（如果你希望匿名，请在报告中注明）。

## Scope

本项目的攻击面主要在以下几处，报告时请优先说明是否涉及：

- **HTTP API**：`/api/v1/*` 的鉴权与入参校验（含 `X-API-Token` 层）
- **记忆写入链路**：`POST /api/v1/memories`、`/sessions/archive` 的注入与幂等键
- **MCP 桥**：`integrations/hermes-mcp` 的契约与参数透传
- **客户端脚本**：`integrations/hermes-client`（会读取本地 `state.db`）
- **部署脚本**：`scripts/`、`deploy/` 中的提权与备份还原路径

## 请勿附带真实凭据

报告里**不要贴**真实的 API Key、数据库连接串、生产 IP / 域名或用户数据。
用占位符（如 `sk-XXXX` / `<db-host>`）表述即可；需要提供环境信息时请脱敏。

## 部署方自查清单

自建部署的用户建议确认：

- [ ] `X-API-Token` 已启用且不是默认值
- [ ] 数据库未监听公网（`MNEMOSYNE_HOST` 默认 `127.0.0.1`）
- [ ] 备份目录不在 Web 可访问路径下
- [ ] 升级前跑过 `scripts/release_checks.py privacy`（本地零输出）
