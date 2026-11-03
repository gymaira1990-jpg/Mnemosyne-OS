# 端口与页面：这套东西对外长什么样

> 目标：搞清楚「哪个端口干什么」「仓库里有没有前端」「自己怎么做一个入口页」。
> 前置：[`INSTALL.md`](../INSTALL.md) 已跑通；想让外人看不到内容 → 先看 [`DEPLOY-PRIVATE.md`](DEPLOY-PRIVATE.md)。

## 1. 端口表（默认值，均可用环境变量改）

| 端口 | 谁在听 | 对外？ | 用途 | 改法 |
|---|---|---|---|---|
| **8010** | Mnemosyne 本体 | **不对外**（只绑 `127.0.0.1`） | REST API | `MNEMOSYNE_PORT` |
| **9091** | Authelia（可选） | **不对外**（只绑 `127.0.0.1`） | 登录门户 | 见 DEPLOY-PRIVATE |
| **443** | nginx | **对外** | 唯一入口：登录页 / 页面 / API 反代 | nginx 配置 |
| 5432 | PostgreSQL | 不对外 | 数据库 | `PGPORT` |

**原则**：对外只开 443。8010 与 9091 永远只绑回环，外部要访问就经 nginx 进来。

## 2. 仓库里有前端吗

**没有。** 本仓库只提供 API + 服务 + 作业脚本；页面属于「用量身定做的」那一层，你自己写。
好处是不绑定审美、也不把你的数据默认暴露在某个固定界面上；代价是要自己搭一个入口。

最小可用入口只要一个文件（`/var/www/private/index.html`）：

```html
<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>我的记忆库</title></head><body>
<h1>我的记忆库</h1>
<ul>
  <li><a href="/diary/" target="_blank" rel="noopener">日记</a></li>
  <li><a href="/memory/" target="_blank" rel="noopener">记忆检索</a></li>
  <li><a href="/logout">退出</a></li>
</ul></body></html>
```

**两条交互规矩**（不是审美问题，是可用性问题）：

1. **独立功能一律新标签打开**（`target="_blank" rel="noopener"`）。
   否则用户点进去就「回不来」，只能按浏览器后退。
2. **每个跳出去的页面自带回路**：页面角落放一个「← 返回入口」，指向 `/` 或你的入口页。

## 3. 页面与接口对照

| 页面路径 | 类型 | 数据来源 |
|---|---|---|
| `/` | 登录页（Authelia 门户） | Authelia |
| `/diary/`（或 `/diary/index.html`） | 静态 HTML（渲染产物） | `data.json` → 渲染器 |
| `/diary/data.json` | 静态 JSON | `export_diary_data` 作业 |
| `/memory/` | 你自建的检索界面 | `/api/v1/...` |
| `/logout` | 退出 | Authelia |

## 4. 主要接口（都在 `/api/v1` 下）

**记忆本体**

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/memories` | 存一条（自动向量化 + 实体提取 + 冲突检测） |
| POST | `/memories/search` | 四维检索（语义 + BM25 + 时序 + 图谱） |
| GET | `/memories` | 列表 |
| GET | `/memories/stats` | 统计 |
| GET | `/memories/heat-top` | 热度榜 |
| GET | `/memories/{id}/traces` | 生命周期轨迹 |
| POST | `/memories/{id}/feedback` | 正/负反馈（影响排序） |

**面向「人来看」的一组（memory-os）**

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/memory-os/recall` | 深度召回（带上下文） |
| POST | `/memory-os/exact` | 精确/关键词命中 |
| POST | `/memory-os/keywords` | 纯关键词 |
| GET | `/memory-os/trace/{archive_no}` | 按档号查一条 |
| GET | `/memory-os/stats` | 卡片数/向量覆盖/实体率 |
| GET | `/memory-os/diary` | 日记列表（喂前端） |
| GET | `/memory-os/health` | 健康检查 |

完整清单见 [`API.md`](API.md)。

## 5. 前端怎么调（不出 CORS 的写法）

**推荐走同源反代**：页面和 API 都从 `https://mem.example.com/` 出发，
nginx 把 `/api/v1/` 反代到 `127.0.0.1:8010`（见 DEPLOY-PRIVATE 第 3 节）。
这样：

- 不需要给后端开 CORS
- `X-API-Token` 由 nginx 注入，**浏览器里没有 token**，页面被看到也不等于凭据泄露
- 登录态是 Cookie，`credentials: 'same-origin'` 就能带上

```js
const r = await fetch('/api/v1/memory-os/stats', { credentials: 'same-origin' });
const s = await r.json();     // {total_cards, with_vector, with_entities, ...}
```

## 6. 自检三行

```bash
curl -s -o /dev/null -w 'api %{http_code}\n' http://127.0.0.1:8010/api/v1/memory-os/health
curl -s -o /dev/null -w 'portal %{http_code}\n' http://127.0.0.1:9091/api/health
curl -s -o /dev/null -w 'public %{http_code}\n' https://mem.example.com/diary/   # 未登录应为 302
```
