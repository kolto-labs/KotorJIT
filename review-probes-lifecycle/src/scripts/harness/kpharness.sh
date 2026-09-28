#!/usr/bin/env bash
# Launch the harness driver under the system interpreter.
#
# The python3 first on PATH may be a package manager's build without Pillow
# or pytesseract; the system one has them, and the driver degrades without
# them anyway. This just sets PYTHONPATH to the package's parent and execs
# `python3 -m kpharness` so the package needs no install step.
#
#   scripts/harness/kpharness.sh run k1_smoke
#   scripts/harness/kpharness.sh boot --target k1
#   scripts/harness/kpharness.sh exec 'return nwscript.call('GetModuleName')'
#   scripts/harness/kpharness.sh down
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${KP_PYTHON:-/usr/bin/python3}"
[[ -x "$PY" ]] || PY="$(command -v python3)"
export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"
exec "$PY" -m kpharness "$@"
