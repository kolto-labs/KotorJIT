#!/usr/bin/env bash
# scripts/examples/showcase/30_battle_meditation.lua, against a real running
# game. Boots once, drives real combat with real keyboard input, and asserts
# the script's own print line -- not merely that the underlying engine script
# ran, which a script can observe and correctly decline to act on.
#
#   GAME_DIR=/dev/shm/kp_k1 ./test_battle_meditation.sh
#
# KNOWN UNVERIFIED, and honestly so rather than quietly flaky: this needs a
# real k_def_attacked01 event where a PARTY MEMBER is the victim -- Bastila's
# gate is IsObjectPartyMember(object_id), and object_id is the one who got
# hit, not the one swinging. Two encounters were tried live and neither
# reliably produces that:
#
#   end_m01aa (Endar Spire opening) -- warping in lands inside the module's
#   own scripted Trask dialogue sequence, which appears to hold input; no
#   character movement was observed for several seconds of #key presses.
#
#   manm26ad (Manaan Sith base) -- movement and real combat both confirmed
#   working (see test_ahto_city_law.sh, which uses the same module and DOES
#   pass), but the party wins fast enough that k_def_attacked01 fires with the
#   SITH TROOPER as victim every time it was observed live, never a party
#   member. That is the ahto test's own trigger condition, not this one's.
#
# GetIsEnemy, IsObjectPartyMember and the party-tag lookup were all
# independently verified correct against live values during this
# investigation (see docs/event-semantics.md) -- the script's own logic is
# sound. What is missing is an encounter that reliably lands a hit on the
# party before it wins, and finding one needs a live session, not a guess at
# which module might work. See scripts/examples/probe/10_position_trace.lua
# for confirming movement, and README.md's "engine bugs found on the way" for
# the technique.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

GAME_DIR="${GAME_DIR:-$ROOT/tmp/k1_harness}"
OUT="${OUT:-$ROOT/tmp/gameplay-test-battle-meditation}"
DISPLAY_NUM="${DISPLAY_NUM:-85}"

deploy_scripts "$GAME_DIR" "$ROOT/scripts/examples/showcase/30_battle_meditation.lua" \
  "$ROOT/scripts/examples/probe/10_position_trace.lua"
rm -f "$GAME_DIR/kotorphasor.log"

start_live_session "$GAME_DIR" "$OUT" "$DISPLAY_NUM"

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
send "#key w"; send "#sleep 1.5"
send "#key w"; send "#sleep 1.5"
send "#key w"; send "#sleep 3"
send "#console"

assert_contains_re "$GAME_DIR/kotorphasor.log" '\[trace\]' \
  "the #key presses actually moved the character"
assert_contains_re "$GAME_DIR/kotorphasor.log" '\[probe\] script:k_def_attacked01' \
  "the stock attacked-script actually ran (proves real combat happened)"

# Not assert_contains_re: see the header. This needs an encounter where the
# party takes a hit, and end_m01aa has not been confirmed to produce one, so a
# miss here is not yet known to mean the script is broken.
if grep -qE '\[meditation\] round [0-9]+: steadied' "$GAME_DIR/kotorphasor.log" 2>/dev/null; then
  ok "30_battle_meditation's own print line fired"
else
  bad "30_battle_meditation never fired -- see the header; this needs a" \
      "confirmed party-gets-hit encounter, which end_m01aa is not yet known to be"
fi

summary_and_exit
