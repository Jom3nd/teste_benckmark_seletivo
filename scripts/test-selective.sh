#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

python_command="${PYTHON:-python}"
arguments=(--mode "${SELECTIVE_TEST_MODE:-indexed}")
if [[ -n "${SELECTIVE_TEST_BASE:-}" ]]; then
  arguments+=(--base-ref "$SELECTIVE_TEST_BASE")
fi

exec "$python_command" tools/analyzer.py "${arguments[@]}" "$@"