#!/usr/bin/env bash
# Deploy probe scripts plus one showcase example for live discovery/recording.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GAME_DIR="${GAME_DIR:-$ROOT/tmp/k1_harness}"
BASE="${1:?usage: deploy_showcase.sh <demo_basename>}"

SCRIPT="$ROOT/scripts/examples/showcase/${BASE}.lua"
[[ -f "$SCRIPT" ]] || { echo "deploy_showcase: missing $SCRIPT" >&2; exit 1; }

mkdir -p "$GAME_DIR/kotorphasor/scripts"
rm -f "$GAME_DIR/kotorphasor/scripts"/*.lua
cp "$ROOT/scripts/examples/probe/00_probe.lua" \
   "$ROOT/scripts/examples/probe/10_position_trace.lua" \
   "$SCRIPT" "$GAME_DIR/kotorphasor/scripts/"
rm -f "$GAME_DIR/kotorphasor.log"
echo "deploy_showcase: $BASE -> $GAME_DIR/kotorphasor/scripts/"
