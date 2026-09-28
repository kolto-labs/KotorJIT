#!/usr/bin/env bash
# Run the kq (KotOR Query) CLI against the local K1 install.
#
#   ./scripts/harness/kq.sh grep '\.Tag =' -t utc -m manm26ad
#   ./scripts/harness/kq.sh cat p_bastilla.utc -f gron
#
# Resolves the game tree from KQ_INSTALL, then kpdiscover, then kotorphasor.toml.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

if [[ -z "${KQ_BIN:-}" ]]; then
  for candidate in \
    "$ROOT/../bioware_projects/cleanhouse/target/release/kq" \
    "${HOME}/.cargo/bin/kq" \
    "$(command -v kq 2>/dev/null)"; do
    [[ -n "$candidate" && -x "$candidate" ]] && KQ_BIN="$candidate" && break
  done
fi
[[ -n "${KQ_BIN:-}" && -x "$KQ_BIN" ]] || {
  echo "kq: no binary found. Build cleanhouse/kq-cli or set KQ_BIN." >&2
  exit 1
}

if [[ -z "${KQ_INSTALL:-}" ]]; then
  KQ_INSTALL="$(python3 "$ROOT/tools/kpdiscover.py" --app k1 2>/dev/null || true)"
fi
[[ -n "${KQ_INSTALL:-}" && -d "$KQ_INSTALL" ]] || {
  echo "kq: no K1 install. Set KQ_INSTALL or add [paths] k1 to kotorphasor.toml." >&2
  exit 1
}

export KQ_INSTALL
exec "$KQ_BIN" "$@"
