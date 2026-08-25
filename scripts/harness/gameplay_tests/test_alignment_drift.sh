#!/usr/bin/env bash
# scripts/examples/showcase/40_alignment_drift.lua, against a real running
# game. This one needs no combat and no warp: AdjustAlignment is a plain
# engine routine, callable straight from the console, and the tick loop
# (app.server_main_loop) is already hooked and running. The only real
# subtlety is the tick rate: ~4 ticks/second measured live, so tick%180==0
# lands roughly every 45 seconds -- the sleep below is sized for that, not
# guessed.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

GAME_DIR="${GAME_DIR:-$ROOT/tmp/k1_harness}"
OUT="${OUT:-$ROOT/tmp/gameplay-test-alignment-drift}"
DISPLAY_NUM="${DISPLAY_NUM:-86}"

deploy_scripts "$GAME_DIR" "$ROOT/scripts/examples/showcase/40_alignment_drift.lua"
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
  for _ in $(seq 1 200); do [[ "$(cat "$D" 2>/dev/null)" == "$n" ]] && break; sleep 0.5; done
}

# nAlignment 2 = shift toward light, verified live (50 -> 80 on a +30 shift);
# a shift that stays inside one decade (e.g. 58 -> 50) does not cross the
# threshold the example watches for, so this asks for a full 30-point move.
send "lua exec kotor.AdjustAlignment(kotor.GetFirstPC(), 2, 30)"
send "#sleep 55"

assert_contains_re "$GAME_DIR/kotorphasor.log" '\[conscience\] \+[0-9]+, now [0-9]+' \
  "40_alignment_drift's own print line fired after crossing a decade boundary"

summary_and_exit
