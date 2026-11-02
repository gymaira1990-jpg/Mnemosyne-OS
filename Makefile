# mnemosyne-dev 的 canonical 入口。
#
# 为什么不是 pytest：运行时 venv 没有 pytest（No module named pytest），
# tests/ 下 241 个用例大量依赖真库/真服务，本地跑不起来。
# `make verify` 做的是真能做的三段：语法 → 服务状态 → 5 个新端点逐个实测。

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

## test: 同 verify（保持通用命令名可被自动识别）
test: verify

clean:
	@find . -name '__pycache__' -type d -not -path '*/node_modules/*' -exec rm -rf {} + 2>/dev/null || true
	@echo cleaned
