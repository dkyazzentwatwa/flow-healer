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

run_cli doctor "${repo_args[@]}" >"${doctor_file}"
run_cli status "${repo_args[@]}" >"${status_file}"

python3 - "${doctor_file}" "${status_file}" <<'PY'
import json
import pathlib
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

if failures:
    print("Runtime verification failed:")
    for item in failures:
        print(f"- {item}")
    raise SystemExit(1)

repos = ", ".join(str(row.get("repo") or "<unknown>") for row in doctor_rows)
print(f"Runtime verification passed for: {repos}")
PY
