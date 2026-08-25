#!/usr/bin/env bash
# Boot KOTOR 1 headless once, leave it running, and drive its console live.
#
# scripts/harness/drive_k1_console.sh runs a fixed command list and exits. That
# is right for a regression check but wrong for exploration: three independent
# investigations (render debugging, movement, and example verification) each
# hand-rolled a "boot once, keep it running, feed it commands as I think of
# them" variant of the same script before this one existed. This is that
# script, kept in one place instead of three.
#
#   live_session.sh                 boot on the default sandbox, block until ready
#   echo "lua status" >> "$Q"       from another shell, once ready.txt exists
#   echo "#screenshot" >> "$Q"      captures the window to shot_NNN.png
#   echo "#console" >> "$Q"         toggles the console without typing into it
#   touch "$OUT/stop"               ends the session and tears down cleanly
#
# $OUT/ready appears once the console is open and the queue is being read.
# $OUT/done holds the count of queue lines processed so far, so a caller can
# `until [[ "$(cat done)" == "$N" ]]` instead of guessing a sleep.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GAME_DIR="${GAME_DIR:-$ROOT/tmp/k1_harness}"
OUT="${OUT:-$ROOT/tmp/live}"
PREFIX="${WINEPREFIX:-$ROOT/tmp/wineprefix-k1}"
DISPLAY_NUM="${DISPLAY_NUM:-78}"
BOOT_WAIT="${BOOT_WAIT:-300}"
LOAD_WAIT="${LOAD_WAIT:-600}"
CONSOLE_KEY="${CONSOLE_KEY:-grave}"

source "$ROOT/scripts/harness/lock.sh"
source "$ROOT/scripts/harness/env_isolate.sh"

# A lock per display, not per OUT dir: the display and the game process are
# what's actually contended, and two OUT dirs pointed at the same
# DISPLAY_NUM would otherwise silently collide.
LOCK_DIR="$ROOT/tmp/harness-locks"
if ! lock_acquire "$LOCK_DIR/display-$DISPLAY_NUM.lock" "$DISPLAY_NUM" swkotor.exe; then
  echo "a live session already owns display $DISPLAY_NUM; re-run with FORCE=1 to take it" >&2
  exit 6
fi

mkdir -p "$OUT"
rm -f "$OUT"/drive.log "$OUT"/wine.log "$OUT"/stop "$OUT"/ready "$OUT"/done
: > "$OUT/queue"
export WINEPREFIX="$PREFIX" WINEDEBUG="${WINEDEBUG:--all}"
export LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=":$DISPLAY_NUM"
isolate_desktop_env

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$OUT/drive.log"; }

if [[ "${RECORD:-0}" == "1" ]]; then
  source "$ROOT/scripts/harness/record.sh"
else
  rec_start() { :; }; rec_mark() { :; }; rec_stop() { :; }
fi

cleanup() {
  rec_stop
  pkill -x swkotor.exe 2>/dev/null
  wineserver -k 2>/dev/null || true
  [[ -n "${XVFB_PID:-}" ]] && kill "$XVFB_PID" 2>/dev/null
  lock_release
  return 0
}
trap cleanup EXIT

[[ -f "$GAME_DIR/swkotor.exe" ]] || { log "no game at $GAME_DIR"; exit 1; }

source "$ROOT/scripts/harness/ini_tune.sh"
ini_headless "$GAME_DIR/swkotor.ini"

Xvfb ":$DISPLAY_NUM" -screen 0 1024x768x24 -nolisten tcp >"$OUT/xvfb.log" 2>&1 &
XVFB_PID=$!
for _ in $(seq 1 40); do xdpyinfo >/dev/null 2>&1 && break; sleep 0.3; done
xdpyinfo >/dev/null 2>&1 || { log "Xvfb failed"; exit 1; }
ROOT_WID=$(( $(xwininfo -root 2>/dev/null | sed -n 's/.*Window id: \([0-9a-vx]*\).*/\1/p' | head -1) ))
log "Xvfb up, root $ROOT_WID"

rec_start "$DISPLAY_NUM" "$OUT/session"

wineboot -i >"$OUT/wineboot.log" 2>&1; wineserver -w
log "launching"
rec_mark "game launched"
( cd "$GAME_DIR" && exec wine swkotor.exe ) >"$OUT/wine.log" 2>&1 &

WID=""
for i in $(seq 1 "$BOOT_WAIT"); do
  for w in $(xdotool search --onlyvisible --name '.*' 2>/dev/null); do
    (( w == ROOT_WID )) && continue
    case "$(xdotool getwindowname "$w" 2>/dev/null)" in *Movie*) continue ;; esac
    read -r W H < <(xdotool getwindowgeometry --shell "$w" 2>/dev/null |
                    sed -n 's/^WIDTH=//p;s/^HEIGHT=//p' | paste -sd' ')
    [[ -z "${W:-}" ]] && continue
    if (( W >= 640 && H >= 480 )); then
      if [[ $(identify -format "%k" <(import -window "$w" png:- 2>/dev/null) 2>/dev/null || echo 0) -gt 64 ]]; then
        WID=$w; break 2
      fi
    fi
  done
  sleep 1
done
[[ -n "$WID" ]] || { log "no rendered game window in ${BOOT_WAIT}s"; exit 2; }
log "game window $WID ('$(xdotool getwindowname "$WID")')"
rec_mark "main menu"
import -window "$WID" "$OUT/00_menu.png" 2>/dev/null

xdotool windowactivate --sync "$WID" 2>/dev/null || xdotool windowfocus "$WID" 2>/dev/null
read -r WX WY WW WH < <(xdotool getwindowgeometry --shell "$WID" 2>/dev/null |
                        sed -n 's/^X=//p;s/^Y=//p;s/^WIDTH=//p;s/^HEIGHT=//p' | paste -sd' ')
echo "WID=$WID WX=$WX WY=$WY WW=$WW WH=$WH DISPLAY=:$DISPLAY_NUM GAME_DIR=$GAME_DIR" > "$OUT/session.env"

click_at() {
  local x y
  x=$(python3 -c "print(int($WX + $WW * $1))")
  y=$(python3 -c "print(int($WY + $WH * $2))")
  xdotool mousemove --sync "$x" "$y"; sleep 0.4
  xdotool click --clearmodifiers 1; sleep 0.4
}
click_until_changed() {
  local before after
  for attempt in $(seq 1 "${3:-3}"); do
    before=$(identify -format "%#" <(import -window "$WID" png:- 2>/dev/null) 2>/dev/null || echo a)
    click_at "$1" "$2"; sleep 2
    after=$(identify -format "%#" <(import -window "$WID" png:- 2>/dev/null) 2>/dev/null || echo b)
    [[ "$before" != "$after" ]] && { log "  $4 took effect (attempt $attempt)"; return 0; }
    log "  $4 did not change the screen, retrying"
  done
  return 1
}

if [[ -d "$GAME_DIR/Saves" ]] && [[ -n "$(ls -A "$GAME_DIR/Saves" 2>/dev/null)" ]]; then
  log "loading a save (window ${WW}x${WH} at ${WX},${WY})"
  click_until_changed 0.583 0.530 3 "LOAD GAME" || { log "main menu did not respond"; exit 5; }
  import -window "$WID" "$OUT/01a_loadmenu.png" 2>/dev/null
  click_at 0.374 0.333
  click_until_changed 0.500 0.740 4 "LOAD" || { log "LOAD never took"; exit 5; }

  # See scripts/examples/probe/00_probe.lua: the runtime does not itself log the
  # scripts the engine runs, so this oracle needs the probe deployed alongside
  # whatever else is loaded. Absent it, this waits the full LOAD_WAIT and exits 4.
  LOADED=0
  for i in $(seq 1 "${LOAD_WAIT:-180}"); do
    if grep -qE "k_def_heartbt01|k_ai_master|\\[probe\\] script:" "$GAME_DIR/kotorphasor.log" 2>/dev/null; then
      LOADED=1; log "  in gameplay at t+${i}s"; rec_mark "gameplay reached"; break
    fi
    if (( i % 15 == 0 )); then log "  loading... t+${i}s"; fi
    sleep 1
  done
  import -window "$WID" "$OUT/01_loading.png" 2>/dev/null
  if (( LOADED == 0 )); then
    log "no gameplay script ran within ${LOAD_WAIT:-180}s"
    log "(is scripts/examples/probe/00_probe.lua deployed to $GAME_DIR/kotorphasor/scripts/ ?)"
    exit 4
  fi
  sleep 3
else
  log "no saves present: the console needs gameplay, so stopping at the menu"
  exit 3
fi

rec_mark "opening console"
log "opening console ($CONSOLE_KEY)"
xdotool key --clearmodifiers "$CONSOLE_KEY"; sleep 1
import -window "$WID" "$OUT/02_console.png" 2>/dev/null

QUEUE="$OUT/queue"
sent=0
log "LIVE: append console commands to $QUEUE; touch $OUT/stop to end"
touch "$OUT/ready"
while [[ ! -f "$OUT/stop" ]]; do
  total=$(wc -l < "$QUEUE" 2>/dev/null || echo 0)
  if (( total > sent )); then
    line=$(sed -n "$((sent+1))p" "$QUEUE")
    sent=$((sent+1))
    [[ -z "$line" ]] && continue
    case "$line" in
    "#screenshot")
      import -window "$WID" "$(printf '%s/shot_%03d.png' "$OUT" "$sent")" 2>/dev/null
      log "screenshot -> shot_$(printf '%03d' "$sent").png" ;;
    "#console")
      xdotool windowactivate --sync "$WID" 2>/dev/null || true
      xdotool key --clearmodifiers "$CONSOLE_KEY"; log "toggled console" ;;
    "#focus")
      xdotool windowactivate --sync "$WID" 2>/dev/null || xdotool windowfocus "$WID" 2>/dev/null
      log "refocused" ;;
    "#key "*)
      xdotool windowactivate --sync "$WID" 2>/dev/null || true
      xdotool key --clearmodifiers "${line#\#key }"; log "key ${line#\#key }" ;;
    "#sleep "*)
      sleep "${line#\#sleep }" ;;
    *)
      xdotool windowactivate --sync "$WID" 2>/dev/null || xdotool windowfocus "$WID" 2>/dev/null
      sleep 0.2
      log "typing[$sent]: $line"
      xdotool type --clearmodifiers --delay 55 "$line"
      sleep 0.4
      xdotool key --clearmodifiers Return
      case "$line" in
        warp*) sleep "${WARP_WAIT:-45}" ;;
        *)     sleep 1.5 ;;
      esac
      ;;
    esac
    echo "$sent" > "$OUT/done"
  else
    sleep 0.5
  fi
done
log "LIVE: stop requested"
import -window "$WID" "$OUT/99_final.png" 2>/dev/null
log "--- kotorphasor.log tail ---"
tail -40 "$GAME_DIR/kotorphasor.log" 2>/dev/null | tee -a "$OUT/drive.log" || true
