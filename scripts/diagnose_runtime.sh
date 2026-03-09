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

section "Config Snapshot"
if [[ -f "${CONFIG_PATH}" ]]; then
  state_root_line="$(grep -E '^[[:space:]]*state_root:' "${CONFIG_PATH}" | head -n 1 || true)"
  connector_line="$(grep -E '^[[:space:]]*connector_command:' "${CONFIG_PATH}" | head -n 1 || true)"
  printf "flow_healer_%s\n" "${state_root_line:-state_root: <missing>}"
  printf "flow_healer_%s\n" "${connector_line:-connector_command: <missing>}"
else
  printf "Config file not found at %s\n" "${CONFIG_PATH}"
fi

APPLE_FLOW_ENV="${HOME}/Documents/code/codex-flow/.env"
if [[ -f "${APPLE_FLOW_ENV}" ]]; then
  section "Apple Flow Env Snapshot"
  for key in apple_flow_db_path apple_flow_enable_autonomous_healer apple_flow_enable_healer_scheduled_scans; do
    value="$(grep -E "^${key}=" "${APPLE_FLOW_ENV}" | tail -n 1 || true)"
    printf "%s\n" "${value:-${key}=<unset>}"
  done
fi

if command -v launchctl >/dev/null 2>&1; then
  uid="$(id -u)"
  for label in local.flow-healer local.apple-flow; do
    section "launchctl ${label}"
    dump_file="$(mktemp)"
    if launchctl print "gui/${uid}/${label}" >"${dump_file}" 2>/dev/null; then
      grep -E 'state =|pid =|last exit code|working directory =|stdout path =|stderr path =|program =|PATH =>' "${dump_file}" || true
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
