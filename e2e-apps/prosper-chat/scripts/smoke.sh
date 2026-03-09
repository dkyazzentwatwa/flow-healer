#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://localhost:8080}"

echo "Smoke checking ${BASE_URL}"
curl -fsS "${BASE_URL}/" >/dev/null
curl -fsS "${BASE_URL}/healthz" >/dev/null
curl -fsS "${BASE_URL}/auth" >/dev/null
curl -fsS "${BASE_URL}/widget/test-key" >/dev/null || true
echo "Smoke check complete"
