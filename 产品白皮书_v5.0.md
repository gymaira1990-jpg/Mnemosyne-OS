# Mnemosyne OS v5.2 · 产品白皮书

**版本**: v5.2.0  
**更新**: 2026-06-25  
**定位**: 认知型记忆操作系统 · 个人AI长期记忆基建  
**网站**: [my.g-cat.cn](https://my.g-cat.cn) · [GitHub](https://github.com/gymaira1990-jpg/Mnemosyne-OS)

---

## 实现状态

| 模块 | 状态 | 说明 |
|------|:---:|------|
| PostgreSQL + pgvector + AGE | ✅ 运行中 | GZ 7×24，1024d 向量 |
| TMT 5级记忆蒸馏 | ✅ 运行中 | L1碎片→L2会话→L3日报→L4周报→L5画像 |
| 三馆闭环 | ✅ 运行中 | 研究馆→工程馆→档案馆 |
| RAG 智能切块 | ✅ 运行中 | 330条记忆→765块 |
| AGE 知识图谱 | ✅ 运行中 | Cypher 图查询 |
| 端云增量同步 | ✅ 运行中 | WSL↔GZ，每10min推送 |
| 会话自动归档 | ✅ 运行中 | Hermes对话→宫殿，每30min |
| 项目记忆绑定 | ✅ 运行中 | 9项目注册，关键词自动标签 |
| 豆包+DeepSeek驱动 | ✅ 运行中 | 可换模型，环境变量切换 |
| Qwen3 Reranker | ✅ 运行中 | GZ:11436 本地精排 |
| Docker部署 | 📝 规划中 | |
| 集群/分片 | 📝 远期 | |
| Redis缓存 | 📝 远期 | |
| 多模态记忆 | 📝 远期 | |

---

## 1. 这是什么

Mnemosyne OS 是一只猫为他的 AI 管家建造的记忆系统。不是向量数据库的外挂，而是一个会自己整理、提炼、发现规律的记忆 OS。

每次对话结束，系统自动把碎片蒸馏成会话→日报→周报→画像。知识在三馆里流转成熟。断网时自动缓存本地，恢复后静默推回云端。未来换上自己训练的模型，这座宫殿就是模型的原生记忆皮层。

---

## 2. 核心架构

```
L5 画像 —— 你是谁，偏好什么
L4 周报 —— 这周发生了什么
L3 日报 —— 今天的收获
L2 会话 —— 一次对话的脉络
L1 碎片 —— 具体记忆

🏛️ 三馆流转    🔍 五维修搜索    🔗 知识图谱    ✂️ RAG切块    ☁️ 端云双活
```

### 2.1 TMT 时间记忆树

5级蒸馏管道，基于时间维度组织记忆。记忆不是平铺的——碎片自然汇聚成会话，会话沉淀为日报，日报提炼为周报，最终形成用户画像。热度衰减机制让不重要的记忆自然降温，高频记忆自动浮现。

### 2.2 三馆闭环

知识像酿酒一样流转：研究馆（待验证）→ 工程馆（踩坑记录）→ 档案馆（已沉淀真理）。三道闸机保证质量：入馆闸过滤噪音，方案闸校验可行性，归档闸验证成果。

### 2.3 五维修搜索

向量语义 + BM25关键词 + 时间衰减 + 可信度 + 热度，五条线索同时搜。Chunk级精准检索把长记忆切成小块，找到最相关的片段。

### 2.4 知识图谱

Apache AGE Cypher 图引擎。记忆中的实体（项目名、技术名、人名）自动提取为图节点，关系构成知识网络。不是孤立的记忆卡片，而是一张网。

### 2.5 端云同步

WSL 笔记本离线时，记忆自动缓存到本地 SQLite。恢复连接后每 10 分钟静默推回 GZ 云端。GZ 是唯一真相源，WSL 只是离线缓冲。

---

## 3. 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| 数据库 | PostgreSQL 16 + pgvector 0.8 | 1024维向量 |
| 图谱 | Apache AGE 1.6.0 | Cypher 图查询 |
| 向量化 | 豆包 Embedding-Vision | 1024d，可换 |
| LLM | 豆包 Seed-2.0 + DeepSeek V4 | 分级调度 |
| Reranker | Qwen3-Embed 0.6B | GZ:11436 本地 |
| 框架 | FastAPI + asyncpg | Python |
| 部署 | GZ 腾讯云 7×24 | systemd |

---

## 4. API 概览

所有端点以 `http://127.0.0.1:8010` 为基准。

### 记忆
- `POST /api/v1/memories` — 存入记忆
- `POST /api/v1/memories/search` — 五维修搜索
- `POST /api/v1/memories/search-chunks` — Chunk级精准搜索
- `POST /api/v1/memories/chunk-all` — 批量RAG切块
- `GET /api/v1/memories/chunks/stats` — Chunk统计

### TMT蒸馏
- `POST /api/v1/tmt/consolidate/session` — L1→L2
- `POST /api/v1/tmt/consolidate/daily` — L2→L3
- `POST /api/v1/tmt/consolidate/weekly` — L3→L4
- `POST /api/v1/tmt/consolidate/monthly` — L4→L5
- `GET /api/v1/tmt/tree/{user_id}` — 查看记忆树

### 会话归档
- `POST /api/v1/sessions/archive` — 完整对话入宫

### 项目
- `POST /api/v1/projects/register` — 注册工作区项目
- `GET /api/v1/projects/` — 列出项目
- `GET /api/v1/projects/by-name/{name}` — 查项目记忆

### 图谱
- `POST /api/v1/graph/search` — 知识图谱搜索

---

## 5. SDK

```python
from integrations.sdk import MnemosyneHermesMemory
m = MnemosyneHermesMemory(endpoint="http://127.0.0.1:18010")
m.add("这条要记住", category="笔记")
m.get_relevant("那个怎么用来着")
```

Hermes Agent: `skill_view("mnemosyne-os-usage")`

---

## 6. 部署

当前运行在 GZ 腾讯云 (Ubuntu 24.04, PostgreSQL 16)，systemd 常驻，7×24。

```bash
# GZ 启动
sudo systemctl start mnemosyne

# WSL 同步 (cron自动)
python3 sync/memory_gateway.py push

# 会话归档 (cron自动)
python3 scripts/archive_session.py --auto
```

环境变量驱动，换模型只需改 `.env`：
```bash
EMBEDDING_MODEL=your-model
LLM_MODEL_LITE=your-model
LLM_MODEL_PRO=your-deep-model
```

---

## 7. 未来

- [x] AGE 知识图谱
- [x] 三馆闭环
- [x] TMT 5级蒸馏
- [x] RAG 智能切块
- [x] 端云同步
- [x] 会话归档
- [x] 项目记忆绑定
- [ ] 自训练模型接入 — 宫殿成为原生记忆皮层
- [ ] 多模态记忆 — 图片视频音频
- [ ] Docker 一键部署
- [ ] Obsidian 人用仪表盘

---

*「记忆不是用来存的，是用来活的。」*  
🐾 G-CAT & Hermes Agent · MIT · 2026
