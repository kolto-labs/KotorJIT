#!/usr/bin/env bash
# Shared helpers for demo_play.sh — wraps gameplay_tests/lib.sh send() with log oracles.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=gameplay_tests/lib.sh
source "$ROOT/scripts/harness/gameplay_tests/lib.sh"

wait_log() {
  local re="$1" secs="${2:-90}" log="${3:-$GAME_DIR/hyperstim.log}"
  for _ in $(seq 1 "$secs"); do
    grep -qE "$re" "$log" 2>/dev/null && return 0
    sleep 1
  done
  echo "wait_log: timed out waiting for /$re/ in $log" >&2
  return 1
}

# warp closes the console; live_session opens it once at boot. One #console after
# warp reopens it. Do not call before the first typed line at session start.
open_console() { send "#console"; send "#sleep 1"; }
close_console() { send "#console"; }

walk_keys() {
  local n="${1:-6}" i
  send "#console"
  for (( i=0; i<n; i++ )); do
    send "#key w"
    send "#sleep 1.5"
  done
  send "#sleep 2"
  send "#console"
}

walk_clicks() {
  local n="${1:-12}" i
  send "#console"
  for (( i=0; i<n; i++ )); do
    send "#click 0.52 0.62"
    send "#sleep 1.0"
  done
  send "#console"
}

fight_clicks() {
  local rounds="${1:-8}" i
  send "#console"
  for (( i=0; i<rounds; i++ )); do
    send "#key Tab"
    send "#sleep 0.4"
    send "#click 0.50 0.38"
    send "#sleep 0.5"
    send "#click 0.50 0.38"
    send "#sleep 3.5"
  done
  send "#console"
}

verify_module() {
  local expect="$1"
  open_console
  send "lua exec nwscript.call('GetModuleName')"
  close_console
  wait_log "lua exec: $expect" 30
}

pc_attack_nearest() {
  open_console
  send "lua exec local pc=nwscript.call('GetFirstPC'); local t=nwscript.call('GetNearestCreature',3,1,pc,1,0,0,0,0); if t and t~=0 then nwscript.call('ActionAttack',t,pc,0) end"
  close_console
  send "#sleep 6"
}

# Victim must be a party member; GetFirstPC() is one. Caller must have console open.
meditation_on_bastila() {
  send "lua exec nwscript.call('ExecuteScript','k_def_attacked01', nwscript.call('GetFirstPC'), 0)"
  send "#sleep 3"
}

warp_module() {
  local mod="$1" tries="${2:-3}" t
  for (( t=1; t<=tries; t++ )); do
    send "warp $mod"
    send "#sleep 8"
    open_console
    send "lua exec nwscript.call('GetModuleName')"
    close_console
    grep -qE "lua exec: $mod" "$LOG" 2>/dev/null && return 0
    sleep 2
  done
  echo "warp_module: $mod not confirmed after $tries tries" >&2
  return 1
}

wound_companion_fallback() {
  open_console
  send "lua exec local pc=nwscript.call('GetFirstPC'); for i=0,nwscript.call('GetPartyMemberCount')-1 do local m=nwscript.call('GetPartyMemberByIndex',i); if m~=pc and nwscript.call('IsObjectPartyMember',m)==1 then nwscript.call('ApplyEffectToObject',1, nwscript.call('EffectDamage',999,1,0), m, 0); nwscript.call('ExecuteScript','k_def_damage01', m, 0); break end end"
  close_console
  send "#sleep 4"
}
