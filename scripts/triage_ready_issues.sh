#!/usr/bin/env bash
set -euo pipefail

"$(dirname "$0")/ensure_agent_labels.sh"

issues_json="$(gh issue list --state open --limit 200 --json number,title,labels,state)"

echo "${issues_json}" | jq -c '.[]' | while read -r row; do
  issue_number="$(echo "${row}" | jq -r '.number')"
  issue_state="$(echo "${row}" | jq -r '.state')"
  [[ "${issue_state}" != "OPEN" ]] && continue

  if ! echo "${row}" | jq -e '[.labels[].name] | index("healer:ready")' >/dev/null; then
    continue
  fi
  if echo "${row}" | jq -e '[.labels[].name] | any(.=="agent:ready" or .=="agent:running" or .=="agent:pr-open")' >/dev/null; then
    continue
  fi

  issue_details="$(gh issue view "${issue_number}" --json title,body,state)"
  details_state="$(echo "${issue_details}" | jq -r '.state')"
  [[ "${details_state}" != "OPEN" ]] && continue

  issue_text="$(
    echo "${issue_details}" | jq -r '.title + "\n" + (.body // "")'
  )"
  if ! echo "${issue_text}" | grep -qi 'e2e-smoke/'; then
    echo "skip #${issue_number} (non-sandbox scope)"
    continue
  fi

  gh issue edit "${issue_number}" --add-label "agent:ready" --add-label "agent:codex" >/dev/null
  echo "triaged #${issue_number} -> agent:ready,agent:codex"
done
