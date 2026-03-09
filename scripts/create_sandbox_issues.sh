#!/usr/bin/env bash
set -euo pipefail

# Create healer-ready GitHub issues that are strictly sandbox-scoped.
# All generated Required code outputs + Validation commands stay under:
# - e2e-smoke/*
# - e2e-apps/*

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/create_sandbox_issues.py" "$@"
