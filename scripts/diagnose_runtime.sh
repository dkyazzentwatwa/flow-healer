#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_PATH="${1:-$HOME/.flow-healer/config.yaml}"
REPO_NAME="${2:-}"

repo_args=()
if [[ -n "${REPO_NAME}" ]]; then
  repo_args=(--repo "${REPO_NAME}")
fi

run_cli() {
  PYTHONPATH="${ROOT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}" python3 -m flow_healer.cli --config "${CONFIG_PATH}" "$@"
}

section() {
  printf "\n== %s ==\n" "$1"
}

section "Runtime Context"
printf "repo_root: %s\n" "${ROOT_DIR}"
printf "config_path: %s\n" "${CONFIG_PATH}"
printf "repo_name: %s\n" "${REPO_NAME:-<all>}"
printf "timestamp_utc: %s\n" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

section "Command Resolution"
for cmd in python3 git docker codex launchctl; do
  printf "%s: %s\n" "${cmd}" "$(command -v "${cmd}" || echo '<missing>')"
done

section "PATH"
printf "%s\n" "${PATH}"

if command -v launchctl >/dev/null 2>&1; then
  uid="$(id -u)"
  for label in local.flow-healer local.apple-flow; do
    section "launchctl ${label}"
    dump_file="$(mktemp)"
    if launchctl print "gui/${uid}/${label}" >"${dump_file}" 2>/dev/null; then
      grep -E 'PATH =>|state =|pid =|last exit code' "${dump_file}" || true
    else
      printf "not loaded\n"
    fi
    rm -f "${dump_file}"
  done
fi

section "Doctor"
if [[ -f "${CONFIG_PATH}" ]]; then
  run_cli doctor "${repo_args[@]}" || true
else
  printf "Config file not found at %s\n" "${CONFIG_PATH}"
fi

section "Status"
if [[ -f "${CONFIG_PATH}" ]]; then
  run_cli status "${repo_args[@]}" || true
else
  printf "Config file not found at %s\n" "${CONFIG_PATH}"
fi
