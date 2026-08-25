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

start_live_session "$GAME_DIR" "$OUT" "$DISPLAY_NUM"

# nAlignment 2 = shift toward light, verified live (50 -> 80 on a +30 shift);
# a shift that stays inside one decade (e.g. 58 -> 50) does not cross the
# threshold the example watches for, so this asks for a full 30-point move.
send "lua exec kotor.AdjustAlignment(kotor.GetFirstPC(), 2, 30)"
send "#sleep 55"

assert_contains_re "$GAME_DIR/kotorphasor.log" '\[conscience\] \+[0-9]+, now [0-9]+' \
  "40_alignment_drift's own print line fired after crossing a decade boundary"

summary_and_exit
