#!/usr/bin/env bash
# tools/tests/examples/fixtures/legacy/showcase/10_ahto_city_law.lua, against a real running game.
# Needs a Manaan module with something hostile in it -- manm26ad (the Sith
# base) has both, unlike Ahto City proper which is deliberately peaceful.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

GAME_DIR="${GAME_DIR:-$ROOT/tmp/k1_harness}"
OUT="${OUT:-$ROOT/tmp/gameplay-test-ahto-city-law}"
DISPLAY_NUM="${DISPLAY_NUM:-87}"

"$ROOT/scripts/harness/pick_save.sh" any

deploy_scripts "$GAME_DIR" "$ROOT/tools/tests/examples/fixtures/legacy/showcase/10_ahto_city_law.lua" \
  "$ROOT/scripts/examples/probe/10_position_trace.lua"
rm -f "$GAME_DIR/kotorphasor.log"

start_live_session "$GAME_DIR" "$OUT" "$DISPLAY_NUM"

send "warp manm26ad"
send "#sleep 5"
send "#console"
send "lua exec nwscript.call('GetModuleName')"
send "#console"
send "#key w"; send "#sleep 1.5"
send "#key w"; send "#sleep 1.5"
send "#key w"; send "#sleep 1.5"
send "#key w"; send "#sleep 1.5"
send "#key w"; send "#sleep 1.5"
send "#key w"; send "#sleep 3"
send "#console"
send "lua exec local pc=nwscript.call('GetFirstPC'); local t=nwscript.call('GetNearestCreature',3,1,pc,1,0,0,0,0); if t and t~=0 then nwscript.call('ActionAttack',t,pc,0) end"
send "#console"
send "#sleep 6"

assert_contains_re "$GAME_DIR/kotorphasor.log" 'manm26ad|MOD=manm26ad' "warp landed on the Sith base module"
assert_contains_re "$GAME_DIR/kotorphasor.log" '\[trace\]' \
  "the #key presses actually moved the character (not a stuck-console or lost-focus false pass)"
assert_contains_re "$GAME_DIR/kotorphasor.log" '\[probe\] script:k_def_attacked01' \
  "real combat happened (proves the module has something hostile to walk into)"
assert_contains_re "$GAME_DIR/kotorphasor.log" '\[ahto\] strike [0-9]+ witnessed on Manaan' \
  "10_ahto_city_law's own print line fired"

summary_and_exit
