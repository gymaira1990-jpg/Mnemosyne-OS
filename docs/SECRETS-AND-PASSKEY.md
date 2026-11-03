# 密钥与通行密钥：怎么管、怎么换、丢了怎么办

> 目标：让「只有我能进」这件事可维护 —— 不是配一次就完事。
> 前置：[`DEPLOY-PRIVATE.md`](DEPLOY-PRIVATE.md) 已把登录墙立起来。

## 1. 这套系统里有几类密钥（先认清，别混）

| # | 密钥 | 存在哪 | 泄露后果 | 谁能看到 |
|---|---|---|---|---|
| 1 | **数据库密码** | `mnemosyne/.env`（600） | 记忆库被读/写 | 服务器 root 与你 |
| 2 | **API Token**（`X-API-Token`） | nginx 配置 + 客户端配置 | 绕过登录直接读写 API | 服务器 root |
| 3 | **模型 Key**（`ARK_API_KEY` / `DEEPSEEK_API_KEY`） | `.env`（600） | 别人烧你的额度 | 服务器 root |
| 4 | **Authelia 三把密钥**（encryption / session / storage） | `/opt/authelia/secrets/`（600） | 会话可伪造 / 数据可解密 | 服务器 root |
| 5 | **你的登录密码（argon2 哈希）** | `users_database.yml` | —（哈希不可逆） | 服务器 root |
| 6 | **通行密钥（Passkey）** | **你的设备本地**，服务器只存公钥 | 服务器被拖库也仿不出来 | 只有你的设备 |

**关键认知**：6 才是日常真正在用的那个；1~5 是「出事才用」的备用件。

## 2. 三条硬规矩

1. **`.env` 与 `secrets/` 永不进仓库**：`.gitignore` 里必须有 `.env`、`*.pem`、`secrets/`
2. **权限 600**：`chmod 600 .env /opt/authelia/secrets/* /opt/authelia/config/*.yml`
3. **前端不碰 token**：浏览器只跟 nginx 说话，token 在 nginx 里注入（见 PAGES-AND-PORTS 第 5 节）

## 3. 通行密钥的生命周期

### 注册（顺序不能反）

```
policy 临时改 two_factor → 账号密码登录 → 出现「注册设备」 → 按 PIN/指纹注册 → 把 policy 改回 one_factor
```

为什么：`one_factor` 下 Authelia 认为「不需要第二因素」，**根本不显示注册入口**
（页面会显示“没有需要第二因素方法的受保护应用程序”）。

### 日常

登录页点 **Sign in with a passkey** → 系统弹 PIN/指纹 → 进站。**不需要密码。**

### 建议做两枚

| 设备 | 用途 |
|---|---|
| 主力机（本机 PIN / Windows Hello / Touch ID） | 日常 |
| 手机（同一 iCloud/Google 账号或另一台设备） | **主力机坏了还能进** |

### 丢了 / 换电脑了

| 情况 | 怎么办 |
|---|---|
| 还有密码 | 直接用密码登录（策略 `one_factor` 下密码仍是合法第一因子），进去重新注册一枚 |
| 密码也忘了 | 服务器上重置：`docker run --rm authelia/authelia authelia crypto hash generate argon2 --password 'NEW'` → 写回 `users_database.yml` → 重启容器 |
| 想作废旧密钥 | 登录后进「二次验证」页删除对应设备条目；或直接删 `db.sqlite3` 里 `webauthn_credentials` 对应行（先停容器） |

> 所以：**密码不要删**。它是你把钥匙弄丢时唯一的那扇后门。

## 4. 轮换（建议每 6~12 个月，或怀疑泄露时立刻做）

| 对象 | 步骤 |
|---|---|
| API Token | 改 nginx 里的 `X-API-Token` → `nginx -t && systemctl reload nginx` → 逐处更新客户端 → 观察 401 是否归零 |
| 模型 Key | 控制台新建 Key → 写 `.env` → 重启服务 → 确认新 Key 生效 → 控制台删旧 Key |
| 数据库密码 | `ALTER USER ... PASSWORD` → 改 `.env` → 重启服务 → 用旧密码连接应失败 |
| Authelia 会话密钥 | 改 `session.secret` → 重启容器 → 所有会话失效（表现为所有人要重登，**属预期**） |
| 登录密码 | 生成新 argon2 哈希写入 `users_database.yml` → 重启容器 → 用新密码登录验证 |

轮换的判据一律是「**旧凭据必须失败，新凭据必须成功**」——只验新的是不算验过。

## 5. 备份（只备份两样就够）

```bash
# ① Authelia：配置 + sqlite（里面有你的通行密钥公钥与账号）
tar czf authelia-$(date +%F).tgz -C /opt authelia/config

# ② 数据库
pg_dump -Fc mnemosyne > mnemosyne-$(date +%F).dump
```

恢复顺序：先起 PostgreSQL → 灌 dump → 再起 Authelia（配置直接解包覆盖）。
**验证恢复**：能登录、能看到一条老记忆、日记页面能打开 —— 三条都过才算恢复成功。

## 6. 别犯这五个错

1. 把 `.env` 提交进 git（一次就够了，历史里永远删不干净）
2. 把 token 写进前端 JS（F12 就能看到）
3. 把 8010 / 9091 直接暴露公网「省事」
4. 只注册一枚通行密钥（设备一坏就锁死）
5. 把验证码写进聊天/工单里截图外发（一次性凭证也属于凭据）
