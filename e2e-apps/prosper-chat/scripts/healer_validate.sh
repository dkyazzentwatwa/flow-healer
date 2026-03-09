#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-full}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$ROOT_DIR/../.." && pwd)"
AUTO_STOP_SUPABASE="${FLOW_HEALER_AUTO_STOP_SUPABASE:-1}"
SUPABASE_STARTED_BY_SCRIPT=0
cd "$ROOT_DIR"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "required command missing: $1" >&2
    exit 127
  }
}

project_id() {
  sed -n 's/^project_id = "\([^"]*\)"$/\1/p' "$ROOT_DIR/supabase/config.toml" | head -n 1
}

cleanup_supabase() {
  if [ "$AUTO_STOP_SUPABASE" != "1" ] || [ "$SUPABASE_STARTED_BY_SCRIPT" -ne 1 ]; then
    return
  fi

  local pid
  pid="$(project_id)"
  if [ -n "$pid" ]; then
    supabase stop --project-id "$pid" >/dev/null 2>&1 || true
  else
    supabase stop >/dev/null 2>&1 || true
  fi
}

trap cleanup_supabase EXIT

ensure_node_deps() {
  need_cmd npm
  local missing_bin=0
  for bin in eslint vite vitest; do
    if [ ! -x "node_modules/.bin/${bin}" ]; then
      missing_bin=1
      break
    fi
  done

  if [ ! -d node_modules ] || [ "$missing_bin" -eq 1 ]; then
    rm -rf node_modules
    npm ci
  fi
}

ensure_supabase_stack() {
  need_cmd docker
  need_cmd supabase
  if ! supabase status >/dev/null 2>&1; then
    supabase start
    SUPABASE_STARTED_BY_SCRIPT=1
  fi
}

smoke_supabase_functions() {
  ensure_supabase_stack
  local serve_log
  serve_log="$(mktemp -t prosper-chat-functions.XXXXXX.log)"
  supabase functions serve --no-verify-jwt >"$serve_log" 2>&1 &
  local serve_pid=$!
  sleep 5
  if ! kill -0 "$serve_pid" >/dev/null 2>&1; then
    wait "$serve_pid" || true
    cat "$serve_log" >&2
    rm -f "$serve_log"
    return 1
  fi
  kill "$serve_pid" >/dev/null 2>&1 || true
  wait "$serve_pid" >/dev/null 2>&1 || true
  rm -f "$serve_log"
}

run_web() {
  ensure_node_deps
  npm run lint
  npm run test
  npm run build
}

run_backend() {
  run_db
  smoke_supabase_functions
}

run_db() {
  need_cmd python3
  python3 "$REPO_ROOT/scripts/flow_healer_sql_validate.py" \
    --project-dir "$ROOT_DIR" \
    --manifest "supabase/assertions/manifest.json"
}

case "$MODE" in
  web)
    run_web
    ;;
  db)
    run_db
    ;;
  backend)
    run_backend
    ;;
  full)
    run_web
    run_db
    ;;
  *)
    echo "usage: ./scripts/healer_validate.sh [web|db|backend|full]" >&2
    exit 2
    ;;
esac
