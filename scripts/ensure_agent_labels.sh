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
  # Idempotent upsert that is safe under concurrent workflow runs.
  gh label create "${name}" --color "${color}" --description "${desc}" --force >/dev/null
done
