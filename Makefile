# mnemosyne-dev 的 canonical 入口。
#
# .venv 里**有** pytest（2026-11-03 实测 294 用例全绿，6.5s）——
# 曾经这里写着「运行时 venv 没有 pytest / 241 个用例跑不起来」，是过时注释，
# 害我以为只能用弱门禁。教训：注释里的数字和事实也要被检查（见 consistency 目标）。
#
# make test      = 单元测试（pytest 全量）+ 文档一致性
# make verify    = 语法 → 服务状态 → 端点实测（需要能连生产）

PY ?= python3

.PHONY: verify lint test clean

## verify: 语法 + 服务状态 + 端点实测（需要能 ssh gz）
verify:
	bash scripts/verify.sh

## lint: 只做语法（离线可用）
lint:
	@$(PY) -c "import ast,pathlib,sys; \
	  [ast.parse(p.read_text(encoding='utf-8')) for p in [pathlib.Path('main.py')]+sorted(pathlib.Path('api').glob('*.py'))]; \
	  print('lint OK: main.py + api/*.py')"

## doctor: 部署前置自检（Python/依赖/.env/PG/pgvector/schema/模型 key/端口）
doctor:
	$(PY) scripts/doctor.py

## demo: 写入 5 条示例记忆并演示一次检索（真调 embedding，--clean 可删）
demo:
	$(PY) scripts/seed_demo.py

## consistency: 文档一致性（版本落点/用例数/落点数/待部署/链接）
consistency:
	$(PY) scripts/consistency_check.py

## test: 单元测试全量 + 文档一致性
test:
	.venv/bin/python3 -m pytest tests/ -q -p no:warnings
	$(PY) scripts/consistency_check.py

clean:
	@find . -name '__pycache__' -type d -not -path '*/node_modules/*' -exec rm -rf {} + 2>/dev/null || true
	@echo cleaned

## release-check: 版本三件套是否齐全（VERSION ↔ tag ↔ Release ↔ 已推送）
release-check:
	$(PY) scripts/release.py verify

## release: 一条命令发版（建 tag → 推 tag → 建 Release → 复验）
release:
	$(PY) scripts/release.py ship
