#!/usr/bin/env bash
# tools/tests/examples/fixtures/legacy/showcase/20_sith_patrol_alarm.lua, against a real running
# game. Fires on k_def_percept01, which runs on the PERCEIVER, not the PC.
#
# Empirically the hardest of the four examples to catch firing live, and that
# is a fact about the encounter, not the mechanism: k_def_percept01 fires
# constantly as a squad's own troopers re-notice EACH OTHER (an ongoing squad-
# awareness loop, sampled well over a thousand times live), while the specific
# moment a HOSTILE first notices the PC is a one-shot, edge-triggered event.
# On the two encounters tried (Endar Spire's opening fight, the Manaan Sith
# base), hostiles appear to already be alerted by the time the party can reach
# them -- attacked01/damage01/combend01 all fire reliably, but the initiating
# percept-of-PC moment happens earlier than any script here could attach to it.
# GetIsEnemy and GetLastPerceived were both independently verified against real
# live values during this investigation (GetIsEnemy correctly returns 1 for a
# confirmed hostile and 0 for a party member; GetLastPerceived correctly
# reports the object a creature most recently noticed) -- the mechanism is
# sound. What this needs to reliably demonstrate is a roaming, not-yet-alerted
# patrol rather than a scripted combat start, which neither tested encounter
# is. Retrying across a few fresh module loads improves the odds without
# pretending the flakiness away.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

GAME_DIR="${GAME_DIR:-$ROOT/tmp/k1_harness}"
OUT="${OUT:-$ROOT/tmp/gameplay-test-sith-patrol-alarm}"
DISPLAY_NUM="${DISPLAY_NUM:-88}"

deploy_scripts "$GAME_DIR" "$ROOT/tools/tests/examples/fixtures/legacy/showcase/20_sith_patrol_alarm.lua" \
  "$ROOT/scripts/examples/probe/10_position_trace.lua"
rm -f "$GAME_DIR/kotorphasor.log"

start_live_session "$GAME_DIR" "$OUT" "$DISPLAY_NUM"

# A warp closes the console; one #console toggle per warp reopens it.
for round in 1 2 3; do
  send "warp end_m01aa"
  send "#sleep 4"
  send "#console"
  send "#key w"; send "#sleep 1.3"
  send "#key w"; send "#sleep 1.3"
  send "#key w"; send "#sleep 1.3"
  send "#key w"; send "#sleep 3"
  send "#console"
  grep -q '\[alarm\]' "$GAME_DIR/kotorphasor.log" 2>/dev/null && break
done

assert_contains_re "$GAME_DIR/kotorphasor.log" '\[probe\] script:k_def_percept01' \
  "the stock perception-script actually ran"
if grep -q '\[alarm\] .* raised the alarm' "$GAME_DIR/kotorphasor.log" 2>/dev/null; then
  ok "20_sith_patrol_alarm's own print line fired"
else
  bad "20_sith_patrol_alarm never fired across 3 fresh encounters -- see the" \
      "header comment; this needs an unaware patrol, not scripted-aggro combat"
fi

summary_and_exit
