#!/usr/bin/env bash
# scripts/examples/showcase/10_ahto_city_law.lua, against a real running game.
# Needs a Manaan module with something hostile in it -- manm26ad (the Sith
# base) has both, unlike Ahto City proper which is deliberately peaceful.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

GAME_DIR="${GAME_DIR:-$ROOT/tmp/k1_harness}"
OUT="${OUT:-$ROOT/tmp/gameplay-test-ahto-city-law}"
DISPLAY_NUM="${DISPLAY_NUM:-87}"

deploy_scripts "$GAME_DIR" "$ROOT/scripts/examples/showcase/10_ahto_city_law.lua"
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

send "warp manm26ad"
send "#sleep 5"
send "#console"
send "lua exec kotor.GetModuleName()"
send "#console"
send "#key w"; send "#sleep 1.5"
send "#key w"; send "#sleep 1.5"
send "#key w"; send "#sleep 1.5"
send "#key w"; send "#sleep 3"
send "#console"

assert_contains "$GAME_DIR/kotorphasor.log" "manm26ad" "warp landed on the Sith base module"
assert_contains_re "$GAME_DIR/kotorphasor.log" '\[probe\] script:k_def_attacked01' \
  "real combat happened (proves the module has something hostile to walk into)"
assert_contains_re "$GAME_DIR/kotorphasor.log" '\[ahto\] strike [0-9]+ witnessed on Manaan' \
  "10_ahto_city_law's own print line fired"

summary_and_exit
