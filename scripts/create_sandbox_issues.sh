#!/usr/bin/env bash
set -euo pipefail

# Create healer-ready GitHub issues that are strictly sandbox-scoped.
# All generated Required code outputs + Validation commands stay under:
# - e2e-smoke/*
# - e2e-apps/*

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI is required" >&2
  exit 1
fi

COUNT="${1:-20}"
PREFIX="${2:-Sandbox stress task}"
READY_LABEL="${READY_LABEL:-healer:ready}"
EXTRA_LABELS="${EXTRA_LABELS:-}"

if ! [[ "${COUNT}" =~ ^[0-9]+$ ]] || [[ "${COUNT}" -lt 1 ]]; then
  echo "count must be a positive integer (got: ${COUNT})" >&2
  exit 1
fi

declare -a TEMPLATES=(
  "Node smoke regression|e2e-smoke/node/src/add.js|e2e-smoke/node/test/add.test.js|cd e2e-smoke/node && npm test -- --passWithNoTests"
  "Python smoke regression|e2e-smoke/python/smoke_math.py|e2e-smoke/python/tests/test_smoke_math.py|cd e2e-smoke/python && pytest -q"
  "Node app regression|e2e-apps/node-next/lib/todo-service.js|e2e-apps/node-next/tests/todo-service.test.js|cd e2e-apps/node-next && npm test -- --passWithNoTests"
  "FastAPI app regression|e2e-apps/python-fastapi/app/service.py|e2e-apps/python-fastapi/tests/test_domain_service.py|cd e2e-apps/python-fastapi && pytest -q"
  "Swift app regression|e2e-apps/swift-todo/Sources/TodoCore/TodoService.swift|e2e-apps/swift-todo/Tests/TodoCoreTests/TodoServiceTests.swift|cd e2e-apps/swift-todo && swift test"
)

build_labels_args() {
  local labels=("${READY_LABEL}")
  if [[ -n "${EXTRA_LABELS}" ]]; then
    IFS=',' read -r -a extra <<<"${EXTRA_LABELS}"
    for label in "${extra[@]}"; do
      label="$(echo "${label}" | xargs)"
      [[ -n "${label}" ]] && labels+=("${label}")
    done
  fi
  local args=()
  for label in "${labels[@]}"; do
    args+=(--label "${label}")
  done
  printf '%s\0' "${args[@]}"
}

mapfile -d '' LABEL_ARGS < <(build_labels_args)

for ((i = 1; i <= COUNT; i++)); do
  idx=$(( (i - 1) % ${#TEMPLATES[@]} ))
  IFS='|' read -r kind target_a target_b validation <<<"${TEMPLATES[$idx]}"

  title="${PREFIX} ${i}: ${kind}"
  body=$'Required code outputs:\n'
  body+="- ${target_a}"$'\n'
  body+="- ${target_b}"$'\n\n'
  body+=$'Validation:\n'
  body+="- ${validation}"$'\n'

  gh issue create \
    --title "${title}" \
    "${LABEL_ARGS[@]}" \
    --body "${body}" >/dev/null

  echo "created issue ${i}/${COUNT}: ${title}"
done

echo "done: created ${COUNT} sandbox-scoped issues"
