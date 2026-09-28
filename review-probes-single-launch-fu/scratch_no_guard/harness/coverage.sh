#!/usr/bin/env bash
# Static soft-lock scan for one module (default: Endar Spire).
#
#   ./scripts/harness/coverage.sh
#   ./scripts/harness/coverage.sh danm13
#   ./scripts/harness/coverage.sh end_m01aa --json
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export TMPDIR="${TMPDIR:-$ROOT/tmp/scratch}"
mkdir -p "$TMPDIR" "$ROOT/tmp/coverage"
module="${1:-end_m01aa}"
shift || true
out="$ROOT/tmp/coverage/${module}.json"
walk="$ROOT/tmp/coverage/${module}.walk"
python3 "$ROOT/tools/coverage_scan.py" -m "$module" -o "$out" "$@"
python3 "$ROOT/tools/coverage_walk.py" "$out" -o "$walk"
echo "walk -> $walk"
