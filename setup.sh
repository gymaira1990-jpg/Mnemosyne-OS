#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# Mnemosyne OS · 安装 / 自检脚本
#
# 用法：
#   ./setup.sh --check     # 只检查环境，不做任何改动（**建议先跑这个**）
#   ./setup.sh             # 完整安装：虚拟环境 + 依赖 + 配置模板 + 数据库初始化
#   ./setup.sh --start     # 启动服务并做健康自检
#
# 设计原则：
#   · 幂等 —— 可重复执行，已存在的不会被覆盖
#   · 只在 --check 之外才改动系统；--check 全程只读
#   · 不硬编码任何路径、用户名或凭据（全部走变量 / .env）
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${VENV_DIR:-$REPO_DIR/.venv}"
PY="${PYTHON:-python3}"
DB_NAME="${MNEMOSYNE_DB_NAME:-mnemosyne}"
DB_USER="${MNEMOSYNE_DB_USER:-mnemosyne}"
DB_HOST="${MNEMOSYNE_DB_HOST:-127.0.0.1}"
DB_PORT="${MNEMOSYNE_DB_PORT:-5432}"
HOST="${MNEMOSYNE_HOST:-127.0.0.1}"
PORT="${MNEMOSYNE_PORT:-8010}"

MODE="install"
case "${1:-}" in
  --check|-c) MODE="check" ;;
  --start|-s) MODE="start" ;;
  --help|-h) sed -n '2,14p' "$0"; exit 0 ;;
  "") ;;
  *) echo "未知参数：$1（用 --help 看用法）" >&2; exit 2 ;;
esac

ok(){   printf '  \033[32m✓\033[0m %s\n' "$1"; }
bad(){  printf '  \033[31m✗\033[0m %s\n' "$1"; }
warn(){ printf '  \033[33m!\033[0m %s\n' "$1"; }
step(){ printf '\n\033[1m%s\033[0m\n' "$1"; }

FAILED=0

# ── 1. 前置检查（check 模式到此为止）────────────────────────────────────────
step "① 环境检查"
if command -v "$PY" >/dev/null 2>&1; then
  PYV="$("$PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
  if "$PY" -c 'import sys;sys.exit(0 if sys.version_info>=(3,11) else 1)'; then
    ok "Python $PYV（要求 ≥3.11）"
  else
    bad "Python $PYV 版本过低（要求 ≥3.11）"; FAILED=1
  fi
else
  bad "找不到 $PY"; FAILED=1
fi

if command -v psql >/dev/null 2>&1; then
  ok "psql 可用（$(psql --version | awk '{print $3}')）"
else
  warn "psql 不在 PATH —— 数据库初始化会跳过（也可用远程库，配 .env 即可）"
fi

command -v git >/dev/null 2>&1 && ok "git 可用" || warn "git 不在 PATH（不影响运行）"

# pgvector 是硬依赖（向量检索）
if command -v psql >/dev/null 2>&1; then
  if PGPASSWORD="${PGPASSWORD:-}" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
       -tAc "SELECT 1 FROM pg_extension WHERE extname='vector'" 2>/dev/null | grep -q 1; then
    ok "pgvector 扩展已在库 $DB_NAME 中就绪"
  else
    warn "无法确认 pgvector（库未建 / 未装扩展 / 需凭据）—— 见 INSTALL.md 数据库章节"
  fi
fi

if [ -f "$REPO_DIR/requirements.txt" ]; then
  ok "requirements.txt 存在（$(( $(wc -l < "$REPO_DIR/requirements.txt") )) 行）"
else
  warn "未找到 requirements.txt"
fi

if [ "$MODE" = "check" ]; then
  step "检查完毕（未做任何改动）"
  [ "$FAILED" -eq 0 ] && echo "  环境可安装。" || { echo "  存在阻塞项，见上方 ✗。"; exit 1; }
  exit 0
fi

# ── 2. 虚拟环境 + 依赖 ──────────────────────────────────────────────────────
step "② 虚拟环境与依赖"
if [ -d "$VENV_DIR" ]; then
  ok "虚拟环境已存在：$VENV_DIR（跳过创建）"
else
  "$PY" -m venv "$VENV_DIR" && ok "已创建虚拟环境：$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
python -m pip install --quiet --upgrade pip && ok "pip 已更新"
if [ -f "$REPO_DIR/requirements.txt" ]; then
  python -m pip install --quiet -r "$REPO_DIR/requirements.txt" && ok "依赖已安装"
fi

# ── 3. 配置 ────────────────────────────────────────────────────────────────
step "③ 配置"
if [ -f "$REPO_DIR/.env" ]; then
  ok ".env 已存在（不覆盖，避免抹掉你的密钥）"
elif [ -f "$REPO_DIR/.env.template" ]; then
  cp "$REPO_DIR/.env.template" "$REPO_DIR/.env"
  warn "已从 .env.template 生成 .env —— **请填入你的 API Key**，否则模型调用会失败"
else
  warn "无 .env 也无 .env.template"
fi

# ── 4. 数据库 ──────────────────────────────────────────────────────────────
step "④ 数据库"
if command -v psql >/dev/null 2>&1 && [ -f "$REPO_DIR/docs/schema.sql" ]; then
  if PGPASSWORD="${PGPASSWORD:-}" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
       -tAc "SELECT to_regclass('public.memories')" 2>/dev/null | grep -q memories; then
    ok "库 $DB_NAME 已初始化（memories 表存在，跳过 schema）"
  else
    warn "库未就绪。请先建库并执行：psql ... -f docs/schema.sql（或用远程库，改 .env 即可）"
  fi
else
  warn "跳过数据库初始化（psql 缺失或找不到 docs/schema.sql）"
fi

# ── 5. 自检 ────────────────────────────────────────────────────────────────
step "⑤ 自检"
if [ -f "$REPO_DIR/tests/run_all.py" ]; then
  (cd "$REPO_DIR" && python tests/run_all.py --quick) && ok "快速自检通过" || warn "快速自检未全绿（见上方输出）"
else
  (cd "$REPO_DIR" && python -m pytest tests/ -q) && ok "pytest 通过" || warn "pytest 未全绿（见上方输出）"
fi

step "安装完成"
cat <<EOF
  下一步：
    1) 编辑 .env 填入模型 API Key
    2) 建库并导入 docs/schema.sql（若上一步提示未就绪）
    3) ./setup.sh --start   启动服务并健康自检
  默认监听：http://$HOST:$PORT
EOF

# ── 6. 启动（仅 --start）───────────────────────────────────────────────────
if [ "$MODE" = "start" ]; then
  step "⑥ 启动与健康检查"
  if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files 2>/dev/null | grep -q mnemosyne; then
    sudo systemctl restart mnemosyne && ok "已重启 systemd 服务 mnemosyne"
  elif [ -f "$REPO_DIR/main.py" ]; then
    nohup python "$REPO_DIR/main.py" >/tmp/mnemosyne.log 2>&1 &
    ok "已在后台启动（日志 /tmp/mnemosyne.log）"
  else
    warn "未找到启动入口（main.py / systemd 服务），请按 INSTALL.md 手动启动"
  fi
  sleep 3
  if curl -sf "http://$HOST:$PORT/api/v1/echo" >/dev/null 2>&1; then
    ok "健康检查通过：http://$HOST:$PORT"
  else
    warn "健康检查未通过 —— 看日志 /tmp/mnemosyne.log 或 journalctl -u mnemosyne"
  fi
fi
