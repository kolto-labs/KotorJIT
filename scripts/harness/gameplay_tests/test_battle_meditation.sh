#!/usr/bin/env bash
# scripts/examples/showcase/30_battle_meditation.lua, against a real running
# game. Boots once, drives real combat with real keyboard input, and asserts
# the script's own print line -- not merely that the underlying engine script
# ran, which a script can observe and correctly decline to act on.
#
#   GAME_DIR=/dev/shm/kp_k1 ./test_battle_meditation.sh
#
# Needs a save with Bastila in the party on a module with a scripted combat
# encounter reachable by walking forward -- the Endar Spire opening (module
# end_m01aa) is exactly that, and is what the default save in this repo's
# harness saves are set up for. See README.md for the pattern this follows.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

GAME_DIR="${GAME_DIR:-$ROOT/tmp/k1_harness}"
OUT="${OUT:-$ROOT/tmp/gameplay-test-battle-meditation}"
DISPLAY_NUM="${DISPLAY_NUM:-85}"

deploy_scripts "$GAME_DIR" "$ROOT/scripts/examples/showcase/30_battle_meditation.lua"
rm -f "$GAME_DIR/kotorphasor.log"

GAME_DIR="$GAME_DIR" OUT="$OUT" DISPLAY_NUM="$DISPLAY_NUM" \
  BOOT_WAIT=300 LOAD_WAIT=600 \
  "$ROOT/scripts/harness/live_session.sh" > "$OUT.nohup.log" 2>&1 &
SESSION_PID=$!

cleanup() { touch "$OUT/stop" 2>/dev/null; wait "$SESSION_PID" 2>/dev/null; }
trap cleanup EXIT

for _ in $(seq 1 120); do [[ -f "$OUT/ready" ]] && break; sleep 1; done
if [[ ! -f "$OUT/ready" ]]; then
  bad "session never reached gameplay -- see $OUT.nohup.log and $OUT/drive.log"
  summary_and_exit; exit $?
fi

Q="$OUT/queue"; D="$OUT/done"
send() {
  echo "$1" >> "$Q"
  local n; n=$(wc -l < "$Q")
  for _ in $(seq 1 120); do [[ "$(cat "$D" 2>/dev/null)" == "$n" ]] && break; sleep 0.5; done
}

# warp CLOSES the console; reopen it before typing anything else into it.
send "warp end_m01aa"
send "#sleep 3"
send "#console"
send "lua exec kotor.GetModuleName()"
# Real keyboard movement, console closed, into the module's scripted Sith
# encounter. Console-driven ActionAttack was tried first and did not reliably
# resolve; this did, every time it was tried live.
send "#console"
send "#key w"; send "#sleep 1.5"
send "#key w"; send "#sleep 1.5"
send "#key w"; send "#sleep 1.5"
send "#key w"; send "#sleep 3"
send "#console"

assert_contains_re "$GAME_DIR/kotorphasor.log" '\[probe\] script:k_def_attacked01' \
  "the stock attacked-script actually ran (proves real combat happened)"
assert_contains_re "$GAME_DIR/kotorphasor.log" '\[meditation\] round [0-9]+: steadied' \
  "30_battle_meditation's own print line fired"

summary_and_exit
