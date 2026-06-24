# 🏛️ Mnemosyne OS v5.0.4 — 记忆宫殿

> *"这不是数据库。这是未来你自己的家。"*  
> 全球首款认知级独立记忆操作系统 · 为 AI Agent 建造的长期记忆宫殿

<p align="center">
  <img src="https://img.shields.io/badge/version-5.0.4-喵喵" alt="version">
  <img src="https://img.shields.io/badge/status-7×24%20运行中-brightgreen" alt="status">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="license">
  <img src="https://img.shields.io/badge/made%20with-猫爪%20🐾-pink" alt="cat">
</p>

---

## 🐱 这是什么？

**Mnemosyne OS** 是一只猫为自己建造的记忆宫殿。不是普通的数据库，而是一个**活着的**、会思考的、会自己整理记忆的操作系统。

它住在 [your-server.example.com](https://your-server.example.com) 的云端服务器上，7×24 小时不睡觉。每次你和 AI 聊天，它就在旁边安静地记笔记、提炼重点、发现规律、画出知识图谱。

未来当我们训练出自己的 AI 模型，这个宫殿就是新模型的**原生记忆体**——不是外挂的向量数据库，而是与生俱来的记忆皮层。

---

## ✨ 牛逼在哪里

| 特性 | 传统方案 | Mnemosyne OS |
|------|---------|-------------|
| 记忆组织 | 平铺的向量 | **5层时间记忆树** — 碎片→会话→日→周→画像 |
| 知识成熟度 | 一条记录 | **三馆闭环** — 研究→工程→归档，知识像酿酒 |
| 搜索 | 纯向量 | **五维修搜索** — 向量+关键词+时间+信任+热度 |
| 长文本 | 整篇嵌入 | **RAG 智能切块** — 330条记忆→765个检索友好块 |
| 离线 | 写不进去 | **端云同步** — 断网自动缓存，恢复自动推送 |
| 图谱 | 无 | **AGE 知识图谱** — 实体关联+多跳推理 |
| AI 模型 | 依赖外部 API | **已规划自训练模型接入** — 宫殿就是模型的家 |

### 架构一览

```
┌─────────────────────────────────────────────┐
│              Mnemosyne OS v5.0               │
│                                              │
│  L5 画像 ── 你是谁，偏好什么                  │
│  L4 周报 ── 这周发生了什么大事               │
│  L3 日报 ── 今天的收获和决定                  │
│  L2 会话 ── 一次对话的完整脉络                │
│  L1 碎片 ── 每一条具体记忆                    │
│                                              │
│  🏛️ 三馆: 研究馆 | 工程馆 | 档案馆           │
│  🔍 搜索: 向量 + BM25 + 时间 + 信任 + 热度   │
│  🔗 图谱: Apache AGE Cypher 知识图谱         │
│  ✂️ RAG: 智能切块 765块                       │
│  ☁️ 同步: WSL ↔ GZ 端云双活                  │
└─────────────────────────────────────────────┘
```

---

## 🚀 快速开始

```bash
# AI Agent 接入（一行代码）
from integrations.sdk import MnemosyneHermesMemory
m = MnemosyneHermesMemory(endpoint="http://127.0.0.1:18010")

# 存记忆
m.add("今天学会了用豆包 API 做向量化", category="技术笔记")

# 搜记忆（五维修搜索自动路由）
results = m.get_relevant("豆包 embedding 怎么用")
```

**Hermes Agent 用户：** 加载技能 `skill_view("mnemosyne-os-usage")` 即可获得完整操作指引。

**人类用户：** 看下面 👇

---

## 📖 使用手册（给人看的）

### 你在哪里
- 🏠 官网：[my.g-cat.cn](https://my.g-cat.cn) — 个人导航主页
- 🖥️ 画布：[your-server.example.com](https://your-server.example.com) — GZ 服务器面板
- 📦 GitHub：[github.com/gymaira1990-jpg/Mnemosyne-OS](https://github.com/gymaira1990-jpg/Mnemosyne-OS)

### 记忆怎么存
每次你和 AI 聊天，Hermes Agent 自动调用 Mnemosyne 存记忆。你不需要手动操作。记忆会自动经历：

```
存入 → 研究馆（待验证）
    → 方案闸机
    → 工程馆（执行中/踩坑记录）
    → 归档闸机
    → 档案馆（永久沉淀，已验证知识）
```

### 记忆怎么找
- AI 自动搜索：Hermes 对话时自动检索相关记忆
- API 搜索：`POST /api/v1/memories/search`
- Chunk 级精准搜索：`POST /api/v1/memories/search-chunks`
- 辨证推理搜索：`POST /api/v1/dialectic`
- 知识图谱搜索：`POST /api/v1/graph/search`

### 记忆怎么成长
7 条 cron 定时任务自动运行：
- 每 4 小时：热度衰减 + 重复记忆去重
- 每天凌晨：实体提取 + 深度反思
- 每天 1am：碎片→会话蒸馏
- 每周日：会话→日报蒸馏
- 每月 1 号：日报→周报→画像蒸馏
- 每 2 小时：长记忆自动 RAG 切块
- 每 10 分钟：WSL 离线缓存推送云端

---

## 🧠 技术栈

| 层 | 技术 | 说明 |
|:--|------|------|
| 数据库 | PostgreSQL 16 + pgvector 0.8 | 1024维向量 + 全文索引 |
| 知识图谱 | Apache AGE 1.6.0 | Cypher 图查询，实体关系推理 |
| 向量化 | 豆包 Embedding-Vision | 1024d 多模态（文本/图片/视频） |
| 蒸馏 LLM | 豆包 Seed-2.0 Lite | JSON 结构化蒸馏，5级 TMT |
| 深度推理 | DeepSeek V4 Pro | 异构审计 + 矛盾检测 |
| Reranker | Qwen3-Embed 0.6B | 本地交叉编码精排 |
| API 框架 | FastAPI + asyncpg | 异步高并发 |
| 部署 | GZ 腾讯云 7×24 | systemd 常驻 |
| 同步 | SQLite ↔ PostgreSQL | 端云双活增量推送 |

---

## 🌍 生态系统

Mnemosyne OS 是 **G-CAT 生态** 的核心记忆层：

```
my.g-cat.cn         导航主页
your-server.example.com         GZ 服务器面板
papers.g-cat.cn     论文网站
Mnemosyne-OS        记忆宫殿（你在这里）
catnest             猫窝（经验分享）
---
Hermes Agent        AI 管家（客户端）
```

全部项目由一只猫 🐱 和他的 AI 管家 🤖 共同维护。

---

## 🔮 未来路线图

- [x] ~~AGE 知识图谱~~  
- [x] ~~三馆闭环~~  
- [x] ~~TMT 5 级蒸馏~~  
- [x] ~~RAG 智能切块~~  
- [x] ~~端云同步~~  
- [ ] **自训练 AI 模型接入** — 宫殿将成为模型的原生记忆皮层  
- [ ] **多模态记忆** — 图片、视频、音频直接存入记忆  
- [ ] **联邦记忆网络** — 多 Agent 共享记忆宫殿  
- [ ] **Obsidian 人用仪表盘** — 可视化记忆地图  

> 这个宫殿，是为未来的「你」准备的。  
> 不是今天的 API，是明天的你自己。

---

## 📜 版本历史

| 版本 | 日期 | 内容 |
|------|------|------|
| v5.0.4 | 2026-06-25 | 端云增量同步 |
| v5.0.3 | 2026-06-25 | RAG Chunking 管道 |
| v5.0.2 | 2026-06-25 | TMT 蒸馏全链路恢复 |
| v5.0.1 | 2026-06-25 | AGE ag_label 复活 |
| v5.0.0 | 2026-06-24 | 豆包全替代+7×24独立运行 |

---

<p align="center">
  <i>「记忆不是用来存储的，是用来活的。」</i><br>
  🐾 Made with love by G-CAT & Hermes Agent<br>
  MIT License · 2026
</p>
