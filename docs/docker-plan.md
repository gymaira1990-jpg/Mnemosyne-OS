# Mnemosyne OS · Docker 化方案（v8.0 规划）

> 状态: 📋 规划 | 目标版本: v8.0 | 依据: 2026-08-11 调研（Mem0/Honcho 安装体验 + PG/AGE 容器化实践）
> 目标: 朋友 `docker compose up` 一条命令跑起整个 Mnemosyne OS（PG16 + pgvector + Apache AGE + 服务）

---

## 为什么需要

- 裸机安装需要手动装 PG16 + pgvector + AGE + Python，门槛高，是朋友用不起来的最大障碍
- 行业标配（Mem0/Honcho）都提供 `docker compose up` 一键体验
- 用户决策（2026-08-11）: 本轮先文档化，Docker 列入 v8.0 工具化阶段

## 镜像选型（调研结论）

**`pgvector/pgvector:pg16` 不内置 Apache AGE**，无官方组合镜像。两条路径：

| 方案 | 基础镜像 | AGE 安装 | 推荐度 |
|---|---|---|---|
| **A. 源码编译** | `pgvector/pgvector:0.8.6-pg16-bookworm` | 镜像内 `make install` AGE | ⭐ 推荐（版本可控） |
| B. apt 安装 | `postgres:16` + PGDG 源 | `apt install postgresql-16-age` | ⚠️ 包名不稳定 |

> AGE 的 apt 包在 PGDG 中不稳定，实战社区均走源码编译路线（固定步骤、版本可控）。

## Dockerfile 蓝图

```dockerfile
FROM pgvector/pgvector:0.8.6-pg16-bookworm

# AGE 编译依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git postgresql-server-dev-16 \
    libreadline-dev zlib1g-dev flex bison ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 编译安装 Apache AGE（PG16 对应分支）
RUN git clone --branch release/PG16/1.5.0 --depth 1 \
    https://github.com/apache/age.git /tmp/age \
    && cd /tmp/age && make install && rm -rf /tmp/age

# 预加载 AGE（关键：避免每次会话手动 LOAD 'age'）
RUN echo "shared_preload_libraries = 'age'" \
    >> /usr/share/postgresql/postgresql.conf.sample

# 初始化脚本（仅空数据卷时执行一次）
COPY initdb/ /docker-entrypoint-initdb.d/
```

## 初始化脚本

```
initdb/
  01-extensions.sql   # CREATE EXTENSION vector; CREATE EXTENSION age; + search_path
  02-schema.sql       # 从 docs/schema.sql 复制
```

```sql
-- 01-extensions.sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS age;
ALTER DATABASE mnemosyne SET search_path = "$user", public, ag_catalog;
```

> ⚠️ AGE 函数在 `ag_catalog` schema 下，必须加入 search_path 才能直接写 Cypher 查询。

## docker-compose 蓝图

```yaml
services:
  db:
    build: ./postgres
    environment:
      POSTGRES_DB: mnemosyne
      POSTGRES_USER: mnemosyne
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data      # 命名卷，勿用 bind mount（权限坑多）
      - ./initdb:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U mnemosyne -d mnemosyne"]
      interval: 5s
      timeout: 5s
      retries: 10
      start_period: 10s

  api:
    build: .
    depends_on:
      db:
        condition: service_healthy        # 等 DB 就绪再起服务
    ports:
      - "8010:8010"
    environment:
      PGUSER: mnemosyne
      PGPASSWORD: ${DB_PASSWORD}
      PGDATABASE: mnemosyne
      ARK_API_KEY: ${ARK_API_KEY}
      # MODEL_BACKEND / OPENAI_* 按需注入

volumes:
  pgdata:
```

## 关键要点

1. **AGE 必须预加载**：`shared_preload_libraries = 'age'`，否则每个会话要手动 `LOAD 'age';`
2. **search_path**：AGENTS.md 提到 main.py 连接池已设 `server_settings={'search_path': 'ag_catalog, public'}`，容器内保持一致
3. **数据持久化**：命名卷 `pgdata`，重启秒起，initdb 只在首次空卷执行
4. **端口**: v7.6.1 main.py 硬编码 8010，Docker 化时一并改为环境变量读取（`MNEMOSYNE_PORT`）
5. **健康检查**：`depends_on: condition: service_healthy` 是标准模式，防 API 先于 DB 启动崩溃

## 实施检查清单（v8.0）

- [ ] postgres/Dockerfile（AGE 编译版）
- [ ] initdb/01-extensions.sql + 02-schema.sql
- [ ] docker-compose.yml（db + api 双服务 + healthcheck）
- [ ] main.py 端口环境变量化（配合 MNEMOSYNE_PORT）
- [ ] 真机验证：空环境 `docker compose up` → echo 200 → 存/搜记忆闭环
- [ ] README/INSTALL.md 补 Docker 快速开始章节
