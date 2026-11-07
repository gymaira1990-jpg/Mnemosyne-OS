# mnemosyne-dev 的 canonical 入口。
#
# .venv 里**有** pytest（2026-11-03 实测 294 用例全绿，6.5s）——
# 曾经这里写着「运行时 venv 没有 pytest / 241 个用例跑不起来」，是过时注释，
# 害我以为只能用弱门禁。教训：注释里的数字和事实也要被检查（见 consistency 目标）。
#
# make test      = 单元测试（pytest 全量）+ 文档一致性
# make verify    = 语法 → 服务状态 → 端点实测（需要能连生产）

PY ?= python3
BASE ?= http://127.0.0.1:8010
K ?= 10
LABEL_USER ?= demo

.PHONY: verify lint test clean backup card-check demo eval eval-semantic eval-live eval-selftest staging deploy-prod smoke

## card-check: 著录卡规范校验（Card Spec v1，内置正反例自检）
card-check:
	$(PY) scripts/card_check.py --selftest
	$(PY) integrations/card-builder/build_cards.py --selftest

## demo: 灌 40 张演示卡（recall 只捞卡，裸记忆它看不到 —— 想看效果用这个）
## 旧版「5 条裸记忆」保留为 demo-basic（它进不了 recall，只适合看写入链路）
demo:
	$(PY) scripts/seed_demo.py --cards evals/demo_cards.jsonl --user demo

## demo-basic: 写入 5 条示例裸记忆并演示一次语义检索（真调 embedding，--clean 可删）
demo-basic:
	$(PY) scripts/seed_demo.py

## eval: 召回评测 recall@k（需要服务在跑 + 已 `make demo`）
eval:
	$(PY) scripts/eval_recall.py --cases evals/demo_cases.jsonl --user demo --base-url $(BASE) --k $(K)

## eval-semantic: 同上，叠加 S 语义通道（四通道）
eval-semantic:
	$(PY) scripts/eval_recall.py --cases evals/demo_cases.jsonl --user demo --base-url $(BASE) --k $(K) --semantic

## eval-live: 先导出人工裁决的题，再跑「手写题库 + 裁决题」合并去重后的评测
## 这就是「使用即训练」：人每裁一次 → 多一道题 → 下次用同一把尺子量
LABELS_CASES ?= evals/labels_cases.jsonl
eval-live:
	-$(PY) scripts/labels_to_cases.py --user $(LABEL_USER) --out $(LABELS_CASES)
	$(PY) scripts/eval_recall.py --cases evals/demo_cases.jsonl $(LABELS_CASES) \
	  --user $(LABEL_USER) --base-url $(BASE) --k $(K) --semantic

## eval-selftest: 只验判据逻辑，不联网
eval-selftest:
	$(PY) scripts/eval_recall.py --selftest

## staging: 部署到预发布并冒烟（任何上线前必须走这一步，见 docs/STAGING.md）
staging:
	bash scripts/deploy_staging.sh

## deploy-prod: 生产部署（唯一入口；要求该提交已在预发布验过）
deploy-prod:
	bash scripts/deploy_prod.sh

## smoke: 生产冒烟（库=生产库）
smoke:
	python3 scripts/prod_smoke.py $(BASE)

## backup: 一次可验证的数据库备份（dump → pg_restore 校验 → 记 sha256 → 保留 KEEP 份）
backup:
	bash scripts/backup.sh

## verify: 语法 + 服务状态 + 端点实测（需要能 ssh gz）
verify:
	bash scripts/verify.sh

## lint: 只做语法（离线可用）
lint:
	@$(PY) -c "import ast,pathlib,sys; \
	  [ast.parse(p.read_text(encoding='utf-8')) for p in [pathlib.Path('main.py')]+sorted(pathlib.Path('api').glob('*.py'))]; \
	  print('lint OK: main.py + api/*.py')"

## bootstrap: 一条命令从零到可验收（建库/导 schema/建角色/装依赖/doctor）
bootstrap:
	bash scripts/bootstrap.sh

## doctor: 部署前置自检（Python/依赖/.env/PG/pgvector/schema/模型 key/端口）
doctor:
	$(PY) scripts/doctor.py

## consistency: 文档一致性（版本落点/用例数/落点数/待部署/链接）
consistency:
	$(PY) scripts/consistency_check.py

## test-db: 重建本地测试库（mnemosyne_itest / mne_ci_v8 / mne_ci_it）
## 为什么要有：本地库若只用半张 schema，连库测试会**静默 skip**——绿色不代表跑过。
test-db:
	@for db in mnemosyne_itest mne_ci_v8 mne_ci_it; do \
	  sudo -u postgres dropdb --if-exists $$db; \
	  sudo -u postgres createdb -O "$$USER" $$db; \
	  psql -q -d $$db -v ON_ERROR_STOP=1 -f docs/schema.sql >/dev/null || exit 1; \
	  echo "  rebuilt: $$db"; \
	done

## test: 单元测试全量 + 文档一致性 + 规范自检
test:
	.venv/bin/python3 -m pytest tests/ -q -p no:warnings
	$(PY) scripts/consistency_check.py
	$(PY) scripts/card_check.py --selftest
	$(PY) integrations/card-builder/build_cards.py --selftest
	$(PY) scripts/eval_recall.py --selftest

clean:
	@find . -name '__pycache__' -type d -not -path '*/node_modules/*' -exec rm -rf {} + 2>/dev/null || true
	@echo cleaned

## prod-diff: 仓库 ↔ 生产 内容级对拍（部署指纹；只比 deploy 清单里的运行面）
prod-diff:
	$(PY) scripts/prod_diff.py

## numbers-check: README 双语数据数字自洽 + 快照未过期 + 口径已写（默认阈值 90 天）
numbers-check:
	$(PY) scripts/release_checks.py numbers-consistency

## release-check: 版本三件套是否齐全（VERSION ↔ tag ↔ Release ↔ 已推送）+ 数据数字自洽
release-check:
	$(PY) scripts/release.py verify
	$(PY) scripts/release_checks.py numbers-consistency

## release: 一条命令发版（建 tag → 推 tag → 建 Release → 复验）
release:
	$(PY) scripts/release.py ship
