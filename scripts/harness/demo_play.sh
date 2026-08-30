#!/usr/bin/env bash
# Drive one showcase demo: real gameplay (~60s), verify the script fired, record mp4/gif.
#
# Uses drive_k1_console.sh (proven console path) with RECORD=1 rather than
# live_session queue driving.
#
#   ./scripts/harness/demo_play.sh 40_alignment_drift
#   ./scripts/harness/demo_play.sh all          # ship set only (30/40/50)
#   ./scripts/harness/demo_play.sh all-wip      # 10/20/60 — not release-ready
set -uo pipefail

# Oracle-verified on a real Game37/Dantooine or alignment run. Do not add a
# name here until demo_play.sh prints OK <name> for that basename.
SHIP_DEMOS=(30_battle_meditation 40_alignment_drift 50_enclave_arrival)
# Scripts exist; harness sequences do not reliably hit the oracle.
WIP_DEMOS=(10_ahto_city_law 20_sith_patrol_alarm 60_party_wounded)

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/scripts/harness/harness_paths.sh"
preflight_tmp_write || exit 1
source "$ROOT/scripts/harness/record.sh"

GAME_DIR="${GAME_DIR:-$ROOT/tmp/k1_harness}"
DEMO_DIR="${DEMO_DIR:-$ROOT/tmp/demos}"
DISPLAY_NUM="${DISPLAY_NUM:-93}"
TARGET="${1:-}"
LOG="$GAME_DIR/kotorphasor.log"

[[ -f "$GAME_DIR/swkotor.exe" ]] || { echo "no game at $GAME_DIR" >&2; exit 1; }

demo_preflight() {
  pkill -9 -f 'drive_k1_console|live_session' 2>/dev/null || true
  pkill -9 -x swkotor.exe 2>/dev/null || true
  pkill -9 -f wineserver 2>/dev/null || true
  wineserver -k 2>/dev/null || true
  rm -f "$ROOT/tmp/harness-locks/display-${DISPLAY_NUM}.lock" 2>/dev/null || true
  sleep 2
}

walk_clicks_cmds() {
  local n="${1:-6}" i
  for (( i=0; i<n; i++ )); do
    cmds+=("#click 0.52 0.62" "#sleep 1")
  done
}

walk_keys_cmds() {
  local n="${1:-6}" i
  for (( i=0; i<n; i++ )); do
    cmds+=("#key w" "#sleep 1.5")
  done
}

fight_clicks_cmds() {
  local rounds="${1:-8}" i
  for (( i=0; i<rounds; i++ )); do
    cmds+=("#key Tab" "#sleep 0.4" "#click 0.50 0.38" "#sleep 0.5" "#click 0.50 0.38" "#sleep 3.5")
  done
}

oracle_for() {
  case "$1" in
  10_ahto_city_law)       echo '\[ahto\] strike [0-9]+ witnessed' ;;
  20_sith_patrol_alarm)   echo '\[alarm\]' ;;
  30_battle_meditation)   echo '\[meditation\] round [0-9]+: steadied' ;;
  40_alignment_drift)     echo '\[conscience\] \+[0-9]+, now [0-9]+' ;;
  50_enclave_arrival)     echo '\[arrival\] (dan|man)' ;;
  60_party_wounded)       echo '\[wounded\]' ;;
  esac
}

play_demo() {
  local base="$1"
  local out="$DEMO_DIR/$base"
  local -a cmds=()
  local oracle

  case "$base" in
  10_ahto_city_law)       "$ROOT/scripts/harness/pick_save.sh" any ;;
  20_sith_patrol_alarm)   "$ROOT/scripts/harness/pick_save.sh" endar ;;
  30_battle_meditation)   "$ROOT/scripts/harness/pick_save.sh" dantooine_party ;;
  40_alignment_drift)     "$ROOT/scripts/harness/pick_save.sh" dantooine_party ;;
  50_enclave_arrival)     "$ROOT/scripts/harness/pick_save.sh" dantooine_party ;;
  60_party_wounded)       "$ROOT/scripts/harness/pick_save.sh" dantooine_party ;;
  *) echo "unknown demo: $base" >&2; return 1 ;;
  esac

  demo_preflight
  "$ROOT/scripts/harness/deploy_showcase.sh" "$base"
  rm -f "$LOG"
  rm -rf "$out"
  mkdir -p "$out"

  local boot_wait=300
  case "$base" in
  10_ahto_city_law) boot_wait=360 ;;
  esac

  case "$base" in
  10_ahto_city_law)
    cmds=("heal" "addlevel" "warp manm26ad" "#sleep 10")
    walk_clicks_cmds 14
    fight_clicks_cmds 8
    cmds+=(
      "#console"
      "lua exec local pc=kotor.GetFirstPC(); local t=kotor.GetNearestCreature(3,1,pc,1,0,0,0,0); if t and t~=0 then kotor.ActionAttack(t,pc,0) end"
      "#console"
      "#sleep 6"
    )
    fight_clicks_cmds 4
    ;;
  20_sith_patrol_alarm)
    local round
    for round in 1 2 3; do
      cmds+=("warp end_m01aa" "#sleep 4" "#console")
      walk_keys_cmds 4
      cmds+=("#sleep 3" "#console")
    done
    cmds+=("warp tar_m02aa" "#sleep 4" "#console")
    walk_keys_cmds 6
    cmds+=("#sleep 3" "#console")
    walk_clicks_cmds 6
    ;;
  30_battle_meditation)
    cmds=(
      "heal"
      "#console"
      "lua exec kotor.ExecuteScript('k_def_attacked01', kotor.GetFirstPC(), 0)"
      "#sleep 8"
      "warp manm26ad"
    )
    cmds+=("#sleep 5" "#console")
    walk_keys_cmds 6
    cmds+=("#console")
    fight_clicks_cmds 6
    ;;
  40_alignment_drift)
    cmds=(
      "lua status"
      "lua exec kotor.AdjustAlignment(kotor.GetFirstPC(), 2, 30)"
      "#sleep 90"
      "lua exec kotor.AdjustAlignment(kotor.GetFirstPC(), 1, 30)"
      "#sleep 90"
    )
    walk_clicks_cmds 6
    ;;
  50_enclave_arrival)
    cmds=(
      "#sleep 55"
      "warp manm26ad" "#sleep 70"
    )
    cmds+=("#console")
    walk_clicks_cmds 10
    cmds+=("#sleep 20")
    ;;
  60_party_wounded)
    cmds=(
      "heal"
      "#console"
      "lua exec local pc=kotor.GetFirstPC(); for i=0,kotor.GetPartyMemberCount()-1 do local m=kotor.GetPartyMemberByIndex(i); if m~=pc and kotor.IsObjectPartyMember(m)==1 then kotor.ApplyEffectToObject(1, kotor.EffectDamage(999,1,0), m, 0); break end end"
      "#sleep 3"
      "lua exec local pc=kotor.GetFirstPC(); for i=0,kotor.GetPartyMemberCount()-1 do local m=kotor.GetPartyMemberByIndex(i); if m~=pc and kotor.IsObjectPartyMember(m)==1 then kotor.ExecuteScript('k_def_damage01', m, 0); break end end"
      "#sleep 5"
      "warp end_m01aa"
    )
    walk_keys_cmds 6
    cmds+=("#sleep 4")
    fight_clicks_cmds 8
    ;;
  esac

  oracle=$(oracle_for "$base")
  if ! GAME_DIR="$GAME_DIR" OUT="$out" DISPLAY_NUM="$DISPLAY_NUM" RECORD=1 \
       WARP_WAIT=45 BOOT_WAIT="$boot_wait" LOAD_WAIT=600 POST_LOAD_WAIT="${POST_LOAD_WAIT:-2}" \
       SPLASH_WAIT="${SPLASH_WAIT:-120}" \
       "$ROOT/scripts/harness/drive_k1_console.sh" "${cmds[@]}" >"$out.nohup.log" 2>&1; then
    echo "boot/drive failed — see $out.nohup.log" >&2
    return 1
  fi

  if [[ -s "$out/session.mp4" ]]; then
    [[ -f "$DEMO_DIR/${base}.mp4" ]] && mkdir -p "$DEMO_DIR/_discarded" &&
      mv -f "$DEMO_DIR/${base}.mp4" "$DEMO_DIR/_discarded/${base}.$(date +%s).mp4" 2>/dev/null || true
    cp -f "$out/session.mp4" "$DEMO_DIR/${base}.mp4"
    rec_gif "$DEMO_DIR/${base}.mp4" "$DEMO_DIR/${base}.gif" "00:00:15" 50 720
    if grep -qE "$oracle" "$LOG" 2>/dev/null; then
      echo "OK $base: script fired — $DEMO_DIR/${base}.mp4"
      return 0
    fi
    if grep -qE "$oracle" "$out/drive.log" 2>/dev/null; then
      echo "OK $base: script fired (oracle in drive.log) — $DEMO_DIR/${base}.mp4"
      return 0
    fi
    echo "WARN $base: mp4 recorded but oracle missing — check $LOG" >&2
    return 1
  fi
  echo "FAIL $base: no mp4 — see $out.nohup.log" >&2
  return 1
}

if [[ "${TARGET:-}" == "all" ]]; then
  fail=0
  for s in "${SHIP_DEMOS[@]}"; do
    play_demo "$s" || fail=1
    DISPLAY_NUM=$((DISPLAY_NUM + 1))
  done
  exit "$fail"
fi

if [[ "${TARGET:-}" == "all-wip" ]]; then
  fail=0
  for s in "${WIP_DEMOS[@]}"; do
    play_demo "$s" || fail=1
    DISPLAY_NUM=$((DISPLAY_NUM + 1))
  done
  exit "$fail"
fi

[[ -n "${TARGET:-}" ]] || { echo "usage: demo_play.sh <name|all|all-wip>" >&2; exit 2; }
play_demo "$TARGET"
