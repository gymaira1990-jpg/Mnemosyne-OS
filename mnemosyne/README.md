# Mnemosyne v5.0 — 认知型记忆操作系统

**全球首款认知级独立记忆操作系统 · Hermes 官方原生深度适配**

> 记忆是与推理引擎平级的底层基建；从存储、治理、验证、适配到涌现，构建完整的机器认知成长体系。

---

## 快速开始

```bash
# 1. 克隆
git clone https://github.com/gymaira1990-jpg/mnemosyne.git
cd mnemosyne

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env: 填入 ARK_API_KEY, PG 连接信息

# 3. 启动
python3 main.py
# Mnemosyne 运行在 http://127.0.0.1:8010
```

## 核心能力

- 🏛️ **三馆闭环**: 研究馆→工程馆→档案馆 知识生产流水线
- 🧠 **五级记忆蒸馏**: L1碎片→L2会话→L3每日→L4每周→L5画像
- 🔍 **五维修搜索**: 向量语义+BM25全文+时间衰减+信任评分+热度
- 🛡️ **三级安全纵深**: 入馆对抗+异构审计+哈希净化化石节点
- 🔌 **3行代码集成**: `pip install mnemosyne-hermes-sdk`
- 💰 **低成本**: 豆包 API (embedding 1024d + seed-2.0)，纯HDD可运行

## 架构

```
L7 认知涌现 ← 方案基因重组
L6 智能体接入 ← Hermes SDK + MCP
L5 运行时调度 ← 项目沙箱 + 会话管理
L4 核心业务 ← 三馆闭环知识生产
L3 算力安全 ← 模型路由 + 异构审计
L2 物理存储 ← PostgreSQL + pgvector
L1 端云协同 ← 增量同步 + 离线运行
```

## API

SDK 用法:
```python
from integrations.sdk import MnemosyneHermesMemory
m = MnemosyneHermesMemory(endpoint="http://127.0.0.1:8010")
m.add("记忆内容", category="note")
m.get_relevant("搜索关键词")
```

完整 API: 见 `产品白皮书_v5.0.md` §13章

## 部署

推荐 Docker:
```yaml
services:
  mnemosyne:
    image: mnemosyne/mnemosyne:v5.0
    ports: ["8010:8010"]
```

## 许可

MIT License — 详见 LICENSE
