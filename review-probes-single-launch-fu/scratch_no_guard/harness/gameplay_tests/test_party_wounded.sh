#!/usr/bin/env bash
# tools/tests/examples/fixtures/legacy/showcase/60_party_wounded.lua — k_def_damage01 on hurt companions.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

GAME_DIR="${GAME_DIR:-$ROOT/tmp/k1_harness}"
OUT="${OUT:-$ROOT/tmp/gameplay-test-party-wounded}"
DISPLAY_NUM="${DISPLAY_NUM:-90}"

deploy_scripts "$GAME_DIR" "$ROOT/tools/tests/examples/fixtures/legacy/showcase/60_party_wounded.lua" \
  "$ROOT/scripts/examples/probe/10_position_trace.lua"
rm -f "$GAME_DIR/kotorphasor.log"

start_live_session "$GAME_DIR" "$OUT" "$DISPLAY_NUM"

send "warp end_m01aa"
send "#sleep 5"
send "#console"
send "#console"
send "#key w"; send "#sleep 1.5"
send "#key w"; send "#sleep 1.5"
send "#key w"; send "#sleep 1.5"
send "#key w"; send "#sleep 4"
send "#console"

assert_contains_re "$GAME_DIR/kotorphasor.log" '\[probe\] script:k_def_damage01' \
  "real damage scripts fired during Endar Spire combat"
assert_contains_re "$GAME_DIR/kotorphasor.log" '\[wounded\]' \
  "60_party_wounded reacted when a companion dropped below 35%"

summary_and_exit
