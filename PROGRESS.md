# Mnemosyne v5.0 进度

## 当前: ✅ Phase 1 完成 — 下一步 Phase 2 (三馆闭环)
## 日期: 2026-06-25

## 已完成
- [x] P1.1 GZ 环境确认 — pgvector 0.8.2 ✅ / 179G 磁盘 / 15.5G 内存
- [x] P1.2 豆包 API 调通 — embedding-vision 1024d + seed-2.0-mini + seed-2.0-lite JSON
- [x] P1.3 更新代码+配置 — config.py + core/{embedding,llm}.py + 主模块改造
- [x] P1.4 部署 GZ — scp 代码 + PG restore (1257条) + systemd mnemosyne running
- [x] P1.5 WSL 适配 — MNEMOSYNE_ENDPOINT→:18010 + mnemosyne-local 已停用

## 关键变更
- embed: Qwen3 local → 豆包 embedding-vision-251215 (1024d)
- LLM: Qwen3.5-4B GPU → 豆包 seed-2-0-lite (JSON mode)
- Reranker: 已移除 (豆包 embedding 质量足够)
- SSH 反向隧道: 不再需要 (-R 11434/11435/11436)
- GZ 独立运行: 7×24, 笔记本关机不影响

## 下一步
- [ ] P2.1 数据库迁移 (hall/gate/projects 表)
- [ ] P2.2 三馆流转 API
- [ ] P2.3 三级门闸
- [ ] P2.4 工具归档接口
- [ ] P2.5 项目管理

## Git checkpoint
- git tag: v5.0-p1
