#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <issue-number> [codex|claude]" >&2
  exit 1
fi

ISSUE_NUMBER="$1"
WORKER="${2:-codex}"

if [[ "${WORKER}" == "claude" ]]; then
  gh issue comment "${ISSUE_NUMBER}" --body "Claude lane is not enabled in this MVP yet. Re-label with \\`agent:codex\\` to run now." >/dev/null
  gh issue edit "${ISSUE_NUMBER}" --remove-label "agent:running" --add-label "agent:blocked" >/dev/null || true
  exit 0
fi

REPO_SLUG="${GITHUB_REPOSITORY:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"
JOB_LABEL="agent:job-${ISSUE_NUMBER}"

if ! gh label view "${JOB_LABEL}" >/dev/null 2>&1; then
  gh label create "${JOB_LABEL}" --color "6e7781" --description "Temporary single-run routing label for issue ${ISSUE_NUMBER}" >/dev/null
fi

gh issue edit "${ISSUE_NUMBER}" --add-label "agent:running" --add-label "${JOB_LABEL}" --remove-label "agent:ready" >/dev/null || true

tmp_config="$(mktemp)"
cat > "${tmp_config}" <<YAML
service:
  github_token_env: GITHUB_TOKEN
  env_file: ""
  github_api_base_url: https://api.github.com
  poll_interval_seconds: 30
  state_root: ~/.flow-healer
  connector_command: codex
  connector_model: gpt-5.4
  connector_reasoning_effort: medium
  connector_timeout_seconds: 900
  connector_routing_mode: exec_for_code
  code_connector_backend: exec
  non_code_connector_backend: app_server
repos:
  - name: flow-healer
    path: $(pwd)
    repo_slug: ${REPO_SLUG}
    default_branch: main
    enable_autonomous_healer: true
    healer_mode: guarded_pr
    issue_required_labels:
      - ${JOB_LABEL}
    pr_actions_require_approval: false
    pr_auto_approve_clean: true
    pr_auto_merge_clean: true
    pr_merge_method: squash
    max_concurrent_issues: 1
    retry_budget: 2
    test_gate_mode: local_only
YAML

cleanup() {
  gh issue edit "${ISSUE_NUMBER}" --remove-label "${JOB_LABEL}" >/dev/null 2>&1 || true
  rm -f "${tmp_config}"
}
trap cleanup EXIT

flow-healer --config "${tmp_config}" start --repo flow-healer --once

status_json="$(flow-healer --config "${tmp_config}" status --repo flow-healer)"
latest_state="$(echo "${status_json}" | jq -r --arg id "${ISSUE_NUMBER}" '.recent_attempts[] | select(.issue_id == $id) | .state' | head -n1)"

if [[ "${latest_state}" == "pr_open" ]] || [[ "${latest_state}" == "resolved" ]]; then
  gh issue edit "${ISSUE_NUMBER}" --remove-label "agent:running" --add-label "agent:pr-open" >/dev/null || true
else
  gh issue edit "${ISSUE_NUMBER}" --remove-label "agent:running" --add-label "agent:blocked" >/dev/null || true
fi
