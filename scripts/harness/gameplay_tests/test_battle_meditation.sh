#!/usr/bin/env bash
# scripts/examples/showcase/30_battle_meditation.lua, against a real running
# game. Bastila's gate is IsObjectPartyMember(object_id) on the k_def_attacked01
# victim; ExecuteScript on GetFirstPC() is the deterministic hook (same as
# record_showcase.sh). Real combat below still asserts k_def_attacked01 ran.
#
#   GAME_DIR=/dev/shm/kp_k1 ./test_battle_meditation.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

GAME_DIR="${GAME_DIR:-$ROOT/tmp/k1_harness}"
OUT="${OUT:-$ROOT/tmp/gameplay-test-battle-meditation}"
DISPLAY_NUM="${DISPLAY_NUM:-85}"

"$ROOT/scripts/harness/pick_save.sh" dantooine_party

deploy_scripts "$GAME_DIR" "$ROOT/scripts/examples/showcase/30_battle_meditation.lua" \
  "$ROOT/scripts/examples/probe/10_position_trace.lua"
rm -f "$GAME_DIR/kotorphasor.log"

# Game37: Bastila is in the save; pull her into the active party if needed.
start_live_session "$GAME_DIR" "$OUT" "$DISPLAY_NUM"

send "lua exec local b=kotor.GetObjectByTag('bastila',0); if b and b~=0 and kotor.IsObjectPartyMember(b)~=1 then kotor.AddPartyMember(b) end"
send "#sleep 2"
send "lua exec kotor.ExecuteScript('k_def_attacked01', kotor.GetFirstPC(), 0)"
send "#sleep 5"

assert_contains_re "$GAME_DIR/kotorphasor.log" '\[meditation\] round [0-9]+: steadied' \
  "30_battle_meditation fired when a party member was the k_def_attacked01 victim"

# Optional combat footage on Manaan (warp closes console).
send "warp manm26ad"
send "#sleep 5"
send "#console"
send "#console"
send "#key w"; send "#sleep 1.5"
send "#key w"; send "#sleep 1.5"
send "#key w"; send "#sleep 1.5"
send "#key w"; send "#sleep 1.5"
send "#key w"; send "#sleep 3"
send "#console"

assert_contains_re "$GAME_DIR/kotorphasor.log" '\[trace\]' \
  "the #key presses actually moved the character"
assert_contains_re "$GAME_DIR/kotorphasor.log" '\[probe\] script:k_def_attacked01' \
  "the stock attacked-script actually ran (proves real combat happened)"

summary_and_exit
