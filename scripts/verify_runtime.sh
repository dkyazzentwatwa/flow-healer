#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_PATH="${1:-$HOME/.flow-healer/config.yaml}"
REPO_NAME="${2:-}"

if [[ ! -f "${CONFIG_PATH}" ]]; then
  printf "Config file not found at %s\n" "${CONFIG_PATH}" >&2
  exit 1
fi

repo_args=()
if [[ -n "${REPO_NAME}" ]]; then
  repo_args=(--repo "${REPO_NAME}")
fi

run_cli() {
  PYTHONPATH="${ROOT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}" python3 -m flow_healer.cli --config "${CONFIG_PATH}" "$@"
}

doctor_file="$(mktemp)"
status_file="$(mktemp)"
trap 'rm -f "${doctor_file}" "${status_file}"' EXIT

if (( ${#repo_args[@]} )); then
  run_cli doctor "${repo_args[@]}" >"${doctor_file}"
  run_cli status "${repo_args[@]}" >"${status_file}"
else
  run_cli doctor >"${doctor_file}"
  run_cli status >"${status_file}"
fi

if command -v launchctl >/dev/null 2>&1; then
  uid="$(id -u)"
  for label in local.flow-healer local.apple-flow; do
    if ! launchctl print "gui/${uid}/${label}" >/dev/null 2>&1; then
      printf "Required launchd service is not loaded: %s\n" "${label}" >&2
      exit 1
    fi
  done
fi

if [[ -f "${HOME}/Documents/code/codex-flow/.env" ]]; then
  auto_healer="$(grep -E '^apple_flow_enable_autonomous_healer=' "${HOME}/Documents/code/codex-flow/.env" | tail -n 1 | cut -d'=' -f2- | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
  scheduled_scans="$(grep -E '^apple_flow_enable_healer_scheduled_scans=' "${HOME}/Documents/code/codex-flow/.env" | tail -n 1 | cut -d'=' -f2- | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
  if [[ "${auto_healer}" != "false" ]]; then
    printf "apple_flow_enable_autonomous_healer must be false for service isolation.\n" >&2
    exit 1
  fi
  if [[ "${scheduled_scans}" != "false" ]]; then
    printf "apple_flow_enable_healer_scheduled_scans must be false for service isolation.\n" >&2
    exit 1
  fi
fi

python3 - "${doctor_file}" "${status_file}" <<'PY'
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys


def load_many(path: str) -> list[dict]:
    text = pathlib.Path(path).read_text()
    decoder = json.JSONDecoder()
    idx = 0
    items: list[dict] = []
    while idx < len(text):
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx >= len(text):
            break
        item, idx = decoder.raw_decode(text, idx)
        if isinstance(item, dict):
            items.append(item)
    return items


doctor_rows = load_many(sys.argv[1])
status_rows = load_many(sys.argv[2])
if not doctor_rows:
    raise SystemExit("No doctor rows returned.")
if not status_rows:
    raise SystemExit("No status rows returned.")

failures: list[str] = []
for row in doctor_rows:
    repo = str(row.get("repo") or "<unknown>")
    for key in ("path_exists", "git_repo", "default_branch_ok", "github_token_present", "codex"):
        if not bool(row.get(key)):
            failures.append(f"{repo}: doctor check '{key}' is false")
    if bool(row.get("circuit_breaker_open")):
        failures.append(f"{repo}: circuit breaker is open")

for row in status_rows:
    repo = str(row.get("repo") or "<unknown>")
    connector = row.get("connector") if isinstance(row.get("connector"), dict) else {}
    if not bool(connector.get("available")):
        failures.append(f"{repo}: connector.available is false")
    breaker = row.get("circuit_breaker") if isinstance(row.get("circuit_breaker"), dict) else {}
    if bool(breaker.get("open")):
        failures.append(f"{repo}: status reports the circuit breaker as open")

launch_snapshots: dict[str, str] = {}
if shutil.which("launchctl"):
    uid = os.getuid()
    for label in ("local.flow-healer", "local.apple-flow"):
        proc = subprocess.run(
            ["launchctl", "print", f"gui/{uid}/{label}"],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            failures.append(f"{label}: launchctl print failed")
            continue
        launch_snapshots[label] = proc.stdout or ""

flow_dump = launch_snapshots.get("local.flow-healer", "")
apple_dump = launch_snapshots.get("local.apple-flow", "")

def extract(field: str, dump: str) -> str:
    match = re.search(rf"^\s*{re.escape(field)} = (.+)$", dump, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""

flow_working_dir = extract("working directory", flow_dump)
apple_working_dir = extract("working directory", apple_dump)
if not flow_working_dir:
    failures.append("local.flow-healer: missing working directory in launchctl output")
if not apple_working_dir:
    failures.append("local.apple-flow: missing working directory in launchctl output")
if flow_working_dir and apple_working_dir and flow_working_dir == apple_working_dir:
    failures.append("launchd isolation failure: both services share the same working directory")
if flow_working_dir and "flow-healer" not in flow_working_dir:
    failures.append(f"local.flow-healer: unexpected working directory '{flow_working_dir}'")
if apple_working_dir and "codex-flow" not in apple_working_dir:
    failures.append(f"local.apple-flow: unexpected working directory '{apple_working_dir}'")

if failures:
    print("Runtime verification failed:")
    for item in failures:
        print(f"- {item}")
    raise SystemExit(1)

repos = ", ".join(str(row.get("repo") or "<unknown>") for row in doctor_rows)
print(f"Runtime verification passed for: {repos}")
PY
