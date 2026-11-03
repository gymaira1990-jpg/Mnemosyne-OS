# 私人部署：把记忆库变成「只有我能看」的网站

> 适用：你想把 Mnemosyne 的记忆检索、日记页面放到公网，但**不想让任何人看到内容**。
> 前置：已完成 [`INSTALL.md`](../INSTALL.md) 的「方式二：独立部署」，服务能在本机 `127.0.0.1:8010` 跑通。
> 本文所有示例值都是占位（`example.com` / `change-me` / `127.0.0.1`），照抄时替换成你自己的。

## 0. 为什么需要这一层

Mnemosyne 本身只监听本机端口，鉴权由**反向代理层的 Token**（`X-API-Token`）负责。
一旦你要把**网页**放上公网，只有 Token 是不够的：浏览器里没有地方安全地存 Token，链接一旦泄露就等于内容泄露。
所以要加一道**统一登录墙**——本方案用 [Authelia](https://www.authelia.com/) + nginx `auth_request`，登录方式是**通行密钥（Passkey / WebAuthn）**，日常只按一次指纹或 PIN。

```
浏览器 ──443──> nginx ──auth_request──> Authelia（127.0.0.1:9091）
                   │                        └─ 未登录 → 302 到登录页
                   └─ 已登录 → 反代到 127.0.0.1:8010（API）或静态页面
```

## 1. 准备

| 需要 | 说明 |
|---|---|
| 一个域名 | 例：`mem.example.com`，A 记录指向你的服务器 |
| 证书 | Let's Encrypt（certbot webroot 即可） |
| Docker | 跑 Authelia（单容器，无需 compose） |
| nginx | 已装，能做 `proxy_pass` / `auth_request` |

## 2. 起 Authelia（单容器）

```bash
sudo mkdir -p /opt/authelia/{config,data,secrets}
# 生成三把密钥（值自己保存，别提交到任何仓库）
openssl rand -base64 48   # ENCRYPTION_KEY
openssl rand -base64 48   # SESSION_SECRET
openssl rand -base64 48   # STORAGE_KEY
# 生成账号密码哈希（argon2）
docker run --rm authelia/authelia:latest \
  authelia crypto hash generate argon2 --password 'change-me-your-password'
```

`/opt/authelia/config/users_database.yml`：

```yaml
users:
  me:                                   # 用户名，随便取
    displayname: Me
    password: '$argon2id$v=19$m=65536,t=3,p=4$...'   # 上一条命令的输出
    email: me@example.com
```

`/opt/authelia/config/configuration.yml`（**关键三行标了 ★**）：

```yaml
theme: dark
default_redirection_url: 'https://mem.example.com/'

server:
  address: 'tcp://:9091'

log:
  level: info

totp:
  disable: true                # 只走通行密钥，不搞 TOTP

webauthn:
  disable: false
  enable_passkey_login: true   # ★ 允许「只用通行密钥」登录，不输密码
  display_name: 'My Memory'
  attestation_conveyance_preference: 'none'

authentication_backend:
  file:
    path: '/config/users_database.yml'

access_control:
  default_policy: 'deny'
  rules:
    - domain: 'mem.example.com'
      policy: 'one_factor'     # ★ 单因子：通行密钥一次即过（注册设备阶段见第 5 节）

session:
  name: 'mnemosyne_session'
  secret: 'REPLACE_WITH_SESSION_SECRET'
  expiration: '8h'
  cookies:
    - domain: 'mem.example.com'
      authelia_url: 'https://mem.example.com'   # ★ 门户就放在子域根，别加 /auth 前缀（原因见第 6 节）

storage:
  encryption_key: 'REPLACE_WITH_ENCRYPTION_KEY'
  local:
    path: '/config/db.sqlite3'

notifier:
  filesystem:
    filename: '/config/notifications.txt'   # 验证码写本地文件，见第 7 节

identity_validation:
  reset_password:
    jwt_secret: 'REPLACE_WITH_ANOTHER_RANDOM'
```

启动：

```bash
docker run -d --name authelia --restart unless-stopped \
  -v /opt/authelia/config:/config \
  -p 127.0.0.1:9091:9091 \
  authelia/authelia:latest
curl -s http://127.0.0.1:9091/api/health    # 期望 {"status":"OK"}
```

> 只绑 `127.0.0.1`：门户不需要对外暴露，外部一律经 nginx 443 进来。

## 3. nginx：三层职责分清

```nginx
server {
    listen 443 ssl;
    server_name mem.example.com;

    ssl_certificate     /etc/letsencrypt/live/mem.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mem.example.com/privkey.pem;

    root /var/www/private;

    # ① 内部子请求：问 Authelia「这个人登录了吗」
    location = /_authz {
        internal;
        proxy_pass http://127.0.0.1:9091/api/authz/forward-auth;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        proxy_set_header Accept "application/json";          # ★ 见第 6 节第 2 条
        proxy_set_header X-Original-URL $scheme://$http_host$request_uri;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $http_host;
        proxy_set_header X-Forwarded-URI $request_uri;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # ② 受保护：日记页面（静态）
    location /diary/ {
        auth_request /_authz;
        auth_request_set $target $scheme://$http_host$request_uri;
        error_page 401 =302 https://mem.example.com/?rd=$target;
        index index.html;
        try_files $uri $uri/ =404;
    }

    # ③ 受保护：记忆 API（反代，Token 只在服务端）
    location /api/v1/ {
        auth_request /_authz;
        auth_request_set $target $scheme://$http_host$request_uri;
        error_page 401 =302 https://mem.example.com/?rd=$target;
        proxy_set_header Host $host;
        proxy_set_header X-API-Token "REPLACE_WITH_YOUR_TOKEN";
        proxy_pass http://127.0.0.1:8010/api/v1/;
    }

    # ④ 门户本体（登录页 + 静态资源）——必须放最后、放根路径
    location / {
        proxy_pass http://127.0.0.1:9091;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 4. 期望行为（自检清单）

```bash
# 未登录访问任何受保护路径 → 302 到登录页
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' https://mem.example.com/diary/
# → 302 https://mem.example.com/?rd=https://mem.example.com/diary/

# 登录页本身 → 200
curl -s -o /dev/null -w '%{http_code}\n' https://mem.example.com/
# → 200
```

浏览器里再确认一遍：打开 `/diary/` 会被弹到登录页，登录后能进去；退出后再访问又会被拦。

## 5. 注册第一枚通行密钥（**顺序别搞反**）

这一步最容易卡住，原因见第 6 节第 3 条。

1. **临时**把 `access_control` 里那条规则的 `policy` 改成 `two_factor`，重启容器。
   （只有 `two_factor` 时 Authelia 才会给你「注册设备」的入口；`one_factor` 下它会认为无需第二因素，页面显示“没有需要第二因素方法的受保护应用程序”。）
2. 浏览器打开 `https://mem.example.com/`，用账号密码登录 → 出现注册设备页。
3. 按系统提示注册通行密钥（Windows Hello / Touch ID / 手机指纹）。
4. 注册成功后，**把 `policy` 改回 `one_factor`** 并重启。

此后日常登录：打开站点 → 点 **Sign in with a passkey** → 按 PIN/指纹，**不需要密码**。

> 密码不要删：换设备、丢密钥时它是唯一兜底，否则你会把自己锁在门外。

## 6. 三个必踩的坑（都是实测出来的）

1. **`auth_request` 的子请求路径不能落在 `/auth/` 下面**
   否则会被门户自己的放行规则匹配到，等于**没有鉴权**（现象：受保护页面直接 200）。
   正解：用 `location = /_authz { internal; ... }` 这种独立路径。
2. **Authelia 对 `Accept: text/html` 的未登录请求返回 302，而 nginx 只认 401/403**
   现象：本该跳登录页，结果 **500**。正解：子请求里强制 `proxy_set_header Accept "application/json";`。
3. **门户不要挂在 `/auth/` 前缀下**
   Authelia 的前端资源是相对路径（`./static/js/...`），`base href` 是 `/`。
   挂在 `/auth/` 时浏览器会去请求 `/static/...` → 命中受保护 location → 拿到 HTML 而不是 JS → **登录页白屏**。
   正解：门户放子域根（`authelia_url: 'https://mem.example.com'`）。

## 7. 验证码为什么「没发到邮箱」

本方案的通知通道是 `filesystem`（写本地文件），**不发邮件**。
需要验证码时（改安全设置、注册新设备）：

```bash
sudo grep -A2 'one-time code' /opt/authelia/config/notifications.txt | tail -5
```

要真的发邮件，把 `notifier` 换成 `smtp` 段并填 SMTP 凭据（自行参考 Authelia 文档）。
想改文案？把模板放进 `/config/email_templates/IdentityVerificationOTC.txt` 并在 `notifier` 里加 `template_path: '/config/email_templates'`。

## 8. 收尾建议

- 站点加 `add_header X-Robots-Tag "noindex, nofollow, noarchive" always;`，`robots.txt` 写 `Disallow: /`
- 证书续期：`certbot renew --dry-run` 验一次，确认 cron/systemd timer 已装
- 密钥文件权限：`chmod 600 /opt/authelia/config/*.yml /opt/authelia/secrets/*`
- 备份两样就够：`/opt/authelia/config`（含 sqlite）与 PostgreSQL 数据目录

---

**下一步**：页面怎么摆、端口怎么分 → [`PAGES-AND-PORTS.md`](PAGES-AND-PORTS.md)；日记怎么每天自动写 → [`DIARY-PIPELINE.md`](DIARY-PIPELINE.md)
