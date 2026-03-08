#!/usr/bin/env bash
set -euo pipefail

labels=(
  $'agent:ready\t0e8a16\tReady for agent processing'
  $'agent:running\t1f6feb\tAgent run in progress'
  $'agent:pr-open\t8250df\tAgent opened/updated PR'
  $'agent:blocked\td1242f\tAgent run blocked or failed'
  $'agent:done\t1a7f37\tAgent workflow completed'
  $'agent:codex\t5319e7\tUse Codex worker'
  $'agent:claude\tfb8c00\tUse Claude worker'
)

for item in "${labels[@]}"; do
  IFS=$'\t' read -r name color desc <<<"${item}"
  if ! gh label view "${name}" >/dev/null 2>&1; then
    gh label create "${name}" --color "${color}" --description "${desc}" >/dev/null
    continue
  fi

  current="$(gh label view "${name}" --json color,description)"
  current_color="$(jq -r '.color' <<<"${current}")"
  current_desc="$(jq -r '.description // ""' <<<"${current}")"
  desired_color="${color#\#}"
  desired_color="${desired_color,,}"

  if [[ "${current_color}" != "${desired_color}" ]] || [[ "${current_desc}" != "${desc}" ]]; then
    gh label edit "${name}" --color "${color}" --description "${desc}" >/dev/null
  fi
done
