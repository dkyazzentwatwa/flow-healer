#!/usr/bin/env bash
set -euo pipefail

"$(dirname "$0")/ensure_agent_labels.sh"

issues_json="$(gh issue list --state open --limit 200 --json number,title,labels,isPullRequest)"

echo "${issues_json}" | jq -c '.[]' | while read -r row; do
  issue_number="$(echo "${row}" | jq -r '.number')"
  is_pr="$(echo "${row}" | jq -r '.isPullRequest')"
  [[ "${is_pr}" == "true" ]] && continue

  labels="$(echo "${row}" | jq -r '[.labels[].name] | join(",")')"
  if [[ "${labels}" == *"agent:ready"* ]] || [[ "${labels}" == *"agent:running"* ]] || [[ "${labels}" == *"agent:pr-open"* ]]; then
    continue
  fi

  gh issue edit "${issue_number}" --add-label "agent:ready" --add-label "agent:codex" >/dev/null
  echo "triaged #${issue_number} -> agent:ready,agent:codex"
done
