#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIG_PATH="${1:-$HOME/.flow-healer/config.yaml}"
REPO_NAME="${2:-}"
LAUNCH_LABEL="${3:-local.flow-healer}"

section() {
  printf "\n== %s ==\n" "$1"
}

section "Connector Resolution"
CODEX_PATH="$(command -v codex || true)"
if [[ -n "${CODEX_PATH}" ]]; then
  printf "Detected codex binary: %s\n" "${CODEX_PATH}"
else
  printf "codex is not currently resolvable from PATH.\n"
fi

section "Config Guidance"
printf "repo_root: %s\n" "${ROOT_DIR}"
printf "config_path: %s\n" "${CONFIG_PATH}"
printf "repo_name: %s\n" "${REPO_NAME:-<all>}"
if [[ -f "${CONFIG_PATH}" ]]; then
  if grep -Eq '^[[:space:]]*connector_command:[[:space:]]*codex[[:space:]]*$' "${CONFIG_PATH}"; then
    if [[ -n "${CODEX_PATH}" ]]; then
      printf "Suggested service.connector_command value: %s\n" "${CODEX_PATH}"
    else
      printf "Config uses bare 'codex' and no codex binary is visible in PATH.\n"
    fi
  else
    printf "Config already avoids a bare connector command, or the setting was not found.\n"
  fi
else
  printf "Config file not found at %s\n" "${CONFIG_PATH}"
fi

section "Verification Commands"
printf "%s/diagnose_runtime.sh %q %q\n" "${SCRIPT_DIR}" "${CONFIG_PATH}" "${REPO_NAME}"
printf "%s/verify_runtime.sh %q %q\n" "${SCRIPT_DIR}" "${CONFIG_PATH}" "${REPO_NAME}"

section "Optional Launch Agent Restart"
if [[ "${FLOW_HEALER_RESTART:-0}" == "1" ]]; then
  if command -v launchctl >/dev/null 2>&1; then
    printf "Attempting launchctl restart for %s\n" "${LAUNCH_LABEL}"
    launchctl stop "${LAUNCH_LABEL}" >/dev/null 2>&1 || true
    launchctl start "${LAUNCH_LABEL}" >/dev/null 2>&1 || true
    printf "Launch agent restart attempted.\n"
  else
    printf "launchctl is not available on this host; restart skipped.\n" >&2
  fi
else
  printf "Set FLOW_HEALER_RESTART=1 to attempt a launch agent restart for %s.\n" "${LAUNCH_LABEL}"
fi

section "Post-Remediation Verification"
"${SCRIPT_DIR}/verify_runtime.sh" "${CONFIG_PATH}" "${REPO_NAME}" || true
