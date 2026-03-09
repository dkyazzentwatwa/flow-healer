#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-full}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "required command missing: $1" >&2
    exit 127
  }
}

ensure_node_deps() {
  need_cmd npm
  if [ ! -d node_modules ]; then
    npm ci
  fi
}

ensure_supabase_stack() {
  need_cmd docker
  need_cmd supabase
  if ! supabase status >/dev/null 2>&1; then
    supabase start
  fi
}

run_web() {
  ensure_node_deps
  npm run lint
  npm run test
  npm run build
}

run_backend() {
  ensure_supabase_stack
  supabase db reset --local --yes
}

case "$MODE" in
  web)
    run_web
    ;;
  backend)
    run_backend
    ;;
  full)
    run_web
    run_backend
    ;;
  *)
    echo "usage: ./scripts/healer_validate.sh [web|backend|full]" >&2
    exit 2
    ;;
esac
