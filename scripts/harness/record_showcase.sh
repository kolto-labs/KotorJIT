#!/usr/bin/env bash
# Record gameplay mp4 (and a short gif) for one showcase example script.
#
#   RECORD=1 ./scripts/harness/record_showcase.sh 10_ahto_city_law
#   RECORD=1 ./scripts/harness/record_showcase.sh all
#
# Uses live_session.sh + x11grab. Output: tmp/demos/<name>.{mp4,gif}
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/scripts/harness/harness_paths.sh"
preflight_tmp_write || exit 1

GAME_DIR="${GAME_DIR:-$ROOT/tmp/k1_harness}"
DEMO_DIR="${DEMO_DIR:-$ROOT/tmp/demos}"
DISPLAY_NUM="${DISPLAY_NUM:-92}"
TARGET="${1:-}"

[[ -f "$GAME_DIR/swkotor.exe" ]] || {
  echo "record_showcase: no game copy at $GAME_DIR (run spike_headless_k1.sh first)" >&2
  exit 1
}

source "$ROOT/scripts/harness/record.sh"

run_demo() {
  local base="$1"   # e.g. 10_ahto_city_law
  local script="$ROOT/scripts/examples/showcase/${base}.lua"
  [[ -f "$script" ]] || { echo "no script: $script" >&2; return 1; }

  local out="$DEMO_DIR/$base"
  local session="$out/session"
  mkdir -p "$DEMO_DIR" "$(dirname "$session")"
  rm -f "$GAME_DIR/kotorphasor.log"

  mkdir -p "$GAME_DIR/kotorphasor/scripts"
  rm -f "$GAME_DIR/kotorphasor/scripts"/*.lua
  cp "$ROOT/scripts/examples/probe/00_probe.lua" \
     "$ROOT/scripts/examples/probe/10_position_trace.lua" \
     "$script" "$GAME_DIR/kotorphasor/scripts/"

  rm -rf "$out"
  mkdir -p "$out"

  GAME_DIR="$GAME_DIR" OUT="$out" DISPLAY_NUM="$DISPLAY_NUM" RECORD=1 \
    "$ROOT/scripts/harness/live_session.sh" >"$out.nohup.log" 2>&1 &
  local pid=$!
  cleanup() { touch "$out/stop" 2>/dev/null; wait "$pid" 2>/dev/null; }
  trap cleanup EXIT

  for _ in $(seq 1 300); do [[ -f "$out/ready" ]] && break; sleep 1; done
  [[ -f "$out/ready" ]] || { echo "boot failed - see $out.nohup.log"; return 1; }

  Q="$out/queue"; D="$out/done"
  send() {
    echo "$1" >> "$Q"
    local n; n=$(wc -l < "$Q")
    for _ in $(seq 1 240); do [[ "$(cat "$D" 2>/dev/null)" == "$n" ]] && break; sleep 0.5; done
  }

  case "$base" in
    10_ahto_city_law)
      send "warp manm26ad"; send "#sleep 45"; send "#console"
      send "lua exec nwscript.call('GetModuleName')"; send "#console"
      send "#key w"; send "#sleep 1.5"; send "#key w"; send "#sleep 1.5"
      send "#key w"; send "#sleep 1.5"; send "#key w"; send "#sleep 1.5"
      send "#key w"; send "#sleep 1.5"; send "#key w"; send "#sleep 5"; send "#console"
      ;;
    20_sith_patrol_alarm)
      send "warp end_m01aa"; send "#sleep 5"; send "#console"
      send "#console"; send "#key w"; send "#sleep 1.3"; send "#key w"; send "#sleep 1.3"
      send "#key w"; send "#sleep 1.3"; send "#key w"; send "#sleep 4"; send "#console"
      ;;
    30_battle_meditation)
      send "warp end_m01aa"; send "#sleep 5"; send "#console"
      send "#console"; send "#key w"; send "#sleep 1.5"; send "#key w"; send "#sleep 1.5"
      send "#key w"; send "#sleep 3"; send "#console"
      send "lua exec nwscript.call('ExecuteScript','k_def_attacked01', nwscript.call('GetFirstPC'), 0)"
      send "#sleep 2"
      ;;
    40_alignment_drift)
      send "lua exec nwscript.call('AdjustAlignment',nwscript.call('GetFirstPC'), 2, 30)"
      send "#sleep 55"
      ;;
    50_enclave_arrival)
      send "warp danm13"; send "#sleep 55"
      send "warp manm26ad"; send "#sleep 55"
      ;;
    60_party_wounded)
      send "warp end_m01aa"; send "#sleep 5"; send "#console"
      send "#console"; send "#key w"; send "#sleep 1.5"; send "#key w"; send "#sleep 1.5"
      send "#key w"; send "#sleep 1.5"; send "#key w"; send "#sleep 5"; send "#console"
      ;;
    *)
      echo "no drive script for $base" >&2; return 1 ;;
  esac

  send "#screenshot"
  touch "$out/stop"
  wait "$pid" 2>/dev/null
  trap - EXIT

  if [[ -s "$session.mp4" ]]; then
    cp -f "$session.mp4" "$DEMO_DIR/${base}.mp4"
    local start="00:01:00" dur=8
    if [[ -f "$session.marks" ]]; then
      local mark_line
      mark_line=$(grep -E 'gameplay reached|game launched' "$session.marks" | tail -1)
      if [[ -n "$mark_line" ]]; then
        start="${mark_line%%$'\t'*}"
        dur=12
      fi
    fi
    rec_gif "$DEMO_DIR/${base}.mp4" "$DEMO_DIR/${base}.gif" "$start" "$dur" 720
    echo "demo: $DEMO_DIR/${base}.mp4 (+ .gif if palette pass succeeded)"
  else
    echo "record_showcase: no mp4 produced for $base" >&2
    return 1
  fi
}

if [[ "$TARGET" == "all" ]]; then
  fail=0
  for s in 30_battle_meditation 40_alignment_drift 50_enclave_arrival; do
    run_demo "$s" || fail=1
    DISPLAY_NUM=$((DISPLAY_NUM + 1))
  done
  exit "$fail"
fi

[[ -n "$TARGET" ]] || {
  echo "usage: record_showcase.sh <30_battle_meditation|40_alignment_drift|50_enclave_arrival|all>" >&2
  echo "WIP (not in all): 10_ahto_city_law 20_sith_patrol_alarm 60_party_wounded" >&2
  exit 2
}
run_demo "$TARGET"
