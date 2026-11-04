#!/usr/bin/env bash
# bootstrap.sh —— 从零到「跑得起来」，交给 AI 执行的一条命令
#
# 设计给谁来跑：一个拿到这个仓库的 AI Agent（Hermes / Claude Code / Cursor / Codex）。
#   原则：**能自动做的自动做，做不了的把命令原样打出来**，每步都有机器判据，别让它猜。
#   KISS：只依赖 bash + python3 + psql，不引入新工具链（单人维护，别给自己加负担）。
#
# 用法：
#   bash scripts/bootstrap.sh            # 一路做到 doctor 通过
#   bash scripts/bootstrap.sh --check    # 只体检，不改任何东西
#
# 退出码：0 = 全部就绪；1 = 有步骤没做完（会打印下一步该执行什么）。
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

PY=${PY:-python3}
NEED_TABLES=23
FAILED=0

say()  { printf '\n── [%d/6] %s\n' "$1" "$2"; }
ok()   { printf '   ✅ %s\n' "$1"; }
warn() { printf '   ⚠️  %s\n' "$1"; }
bad()  { printf '   ❌ %s\n' "$1"; FAILED=1; }
todo() { printf '   → 执行: %s\n' "$1"; }

envval() {  # 从 .env 取值（不 source，避免把注释/特殊字符当命令执行）
  [ -f .env ] || return 0
  sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" .env | tail -1 | sed 's/[[:space:]]*$//'
}

DB=${PGDATABASE:-$(envval PGDATABASE)}; DB=${DB:-mnemosyne}
PGU=${PGUSER:-$(envval PGUSER)};        PGU=${PGU:-mnemosyne}
PGP=${PGPASSWORD:-$(envval PGPASSWORD)}; PGP=${PGP:-your-strong-password}

# ── 1. python ──
say 1 "Python 运行时"
if command -v "$PY" >/dev/null 2>&1; then
  v=$("$PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])')
  case "$v" in
    3.1[1-9]|3.[2-9][0-9]) ok "Python $v" ;;
    *) bad "Python $v 太旧（需 3.11+）"; todo "装 Python 3.11+ 后重跑" ;;
  esac
else
  bad "找不到 $PY"; todo "安装 Python 3.11+ 后重跑"
fi

# ── 2. PostgreSQL ──
say 2 "PostgreSQL"
HAVE_PSQL=0
if command -v psql >/dev/null 2>&1; then
  HAVE_PSQL=1; ok "psql 已安装"
  run_psql() {  # 以超级用户跑 SQL：能免密 sudo 就用 postgres，否则用当前用户
    if sudo -n true 2>/dev/null; then sudo -u postgres psql -tAq -c "$1" 2>&1
    else psql -tAq -c "$1" 2>&1; fi
  }
  if run_psql "select 1" >/dev/null 2>&1; then ok "能连上 PostgreSQL"
  else bad "连不上 PostgreSQL"; todo "sudo systemctl start postgresql   （macOS: brew services start postgresql@16）"; HAVE_PSQL=0; fi
else
  bad "没有 psql"; todo "Ubuntu: sudo apt install postgresql postgresql-contrib；macOS: brew install postgresql@16"
fi

# ── 3. .env（提前：后面建角色要读里面的账号密码）──
say 3 "配置文件 .env"
if [ -f .env ]; then
  ok ".env 已存在"
else
  if [ "$CHECK_ONLY" = "1" ]; then
    warn "没有 .env"; todo "cp .env.template .env 然后填 key"
  else
    cp .env.template .env && warn "已从模板创建 .env"
  fi
fi
if grep -qE '^(ARK_API_KEY|OPENAI_API_KEY)=.+' .env 2>/dev/null; then
  ok "已配置模型 key"
else
  bad "没有可用的模型 key（向量化是硬需求）"
  todo "编辑 .env 填 ARK_API_KEY（https://console.volcengine.com/ark），或 MODEL_BACKEND=openai + OPENAI_API_KEY"
fi

# ── 4. 数据库 + 应用角色 + 表结构 ──
say 4 "数据库 $DB / 角色 $PGU / 表结构"
if [ "$HAVE_PSQL" = "1" ]; then
  # 4a 库
  if [ "$(run_psql "select 1 from pg_database where datname='$DB'" 2>/dev/null)" = "1" ]; then
    ok "库 $DB 已存在"
  elif [ "$CHECK_ONLY" = "1" ]; then
    warn "库 $DB 不存在（--check 不创建）"; todo "sudo -u postgres createdb $DB"
  elif sudo -n true 2>/dev/null; then
    sudo -u postgres createdb "$DB" 2>/dev/null && ok "已创建库 $DB" || bad "建库失败"
  else
    bad "库 $DB 不存在"; todo "sudo -u postgres createdb $DB"
  fi

  # 4b 应用角色（模板默认 PGUSER=mnemosyne；不给它建，服务连上去就是 role does not exist）
  if [ "$PGU" != "postgres" ]; then
    if [ "$(run_psql "select 1 from pg_roles where rolname='$PGU'" 2>/dev/null)" = "1" ]; then
      ok "角色 $PGU 已存在"
    elif [ "$CHECK_ONLY" = "1" ]; then
      warn "角色 $PGU 不存在"; todo "sudo -u postgres psql -c \"create role $PGU login password '<口令>'\""
    elif sudo -n true 2>/dev/null; then
      sudo -u postgres psql -q -c "create role $PGU login password '$PGP'" 2>/dev/null \
        && ok "已创建角色 $PGU（口令取 .env 的 PGPASSWORD）" || bad "建角色失败"
    else
      bad "角色 $PGU 不存在"; todo "sudo -u postgres psql -c \"create role $PGU login password '<口令>'\""
    fi
  fi

  # 4c 表结构
  if sudo -n true 2>/dev/null; then
    n=$(sudo -u postgres psql -tAq -d "$DB" -c "select count(*) from information_schema.tables where table_schema='public'" 2>/dev/null)
  else
    n=$(psql -tAq -d "$DB" -c "select count(*) from information_schema.tables where table_schema='public'" 2>/dev/null)
  fi
  n=$(printf '%s' "${n:-0}" | tr -dc '0-9')
  if [ "${n:-0}" -ge "$NEED_TABLES" ] 2>/dev/null; then
    ok "表结构齐全（${n} 张表）"
  elif [ "$CHECK_ONLY" = "1" ]; then
    warn "只有 ${n:-0} 张表（需 $NEED_TABLES+）"; todo "sudo -u postgres psql -d $DB -f docs/schema.sql"
  elif sudo -n true 2>/dev/null; then
    sudo -u postgres psql -q -d "$DB" -f docs/schema.sql >/dev/null 2>&1 \
      && ok "已导入 docs/schema.sql" || bad "导入失败（看 psql 报错）"
  else
    bad "表结构不全（${n:-0} 张）"; todo "sudo -u postgres psql -d $DB -f docs/schema.sql"
  fi

  # 4d 授权给应用角色
  if [ "$PGU" != "postgres" ] && [ "$CHECK_ONLY" = "0" ]; then
    if sudo -n true 2>/dev/null; then
      sudo -u postgres psql -q -d "$DB" -c \
        "GRANT ALL ON SCHEMA public TO $PGU; GRANT ALL ON ALL TABLES IN SCHEMA public TO $PGU; GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO $PGU; GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO $PGU;" >/dev/null 2>&1 \
        && ok "已授权 $PGU 访问 $DB" || warn "授权失败，可能需手动执行 GRANT"
    fi
  fi
fi

# ── 5. Python 依赖 ──
say 5 "Python 依赖"
if [ ! -x .venv/bin/python3 ]; then
  if [ "$CHECK_ONLY" = "1" ]; then
    warn "没有 .venv"; todo "python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  else
    "$PY" -m venv .venv >/dev/null 2>&1 && ok "已创建 .venv" || bad "建 venv 失败"
  fi
fi
if [ -x .venv/bin/python3 ]; then
  if .venv/bin/python3 -c 'import fastapi,asyncpg,dotenv' 2>/dev/null; then
    ok "依赖已装"
  elif [ "$CHECK_ONLY" = "1" ]; then
    warn "依赖不齐"; todo ".venv/bin/pip install -r requirements.txt"
  else
    .venv/bin/pip install -q -r requirements.txt 2>&1 | tail -2
    .venv/bin/python3 -c 'import fastapi,asyncpg,dotenv' 2>/dev/null && ok "已安装依赖" || bad "依赖安装失败"
  fi
fi

# ── 6. doctor 验收 ──
say 6 "doctor 验收"
if [ -x .venv/bin/python3 ]; then
  .venv/bin/python3 scripts/doctor.py 2>&1 | tail -22
  .venv/bin/python3 scripts/doctor.py >/dev/null 2>&1 || FAILED=1
else
  warn "跳过（没有 .venv）"
fi

printf '\n%s\n' "──────────────────────────────────────────────"
if [ "$FAILED" = "0" ]; then
  printf '✅ 就绪。下一步：\n   .venv/bin/python3 main.py                # 起服务\n   .venv/bin/python3 scripts/seed_demo.py   # 塞几条示例看效果\n'
  exit 0
else
  printf '❌ 还没就绪：按上面每条的「→ 执行」处理，然后重跑 bash scripts/bootstrap.sh\n'
  exit 1
fi
