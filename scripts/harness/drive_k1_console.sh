#!/usr/bin/env bash
# Boot KOTOR 1 headless, open the cheat console, and type commands into it.
#
# This is how the runtime gets demonstrated without a screen: the console is a
# real input path into the running game, so anything typed here exercises the
# same code a player would.
#
# Two things have to be true before the console accepts anything. `EnableCheats=1`
# must be in swkotor.ini, and the game must be past the main menu -- the console
# is a gameplay surface, so it does nothing on the menu.
#
#   drive_k1_console.sh                       boot, screenshot, type the defaults
#   drive_k1_console.sh "lua status" "lua reload"
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GAME_DIR="${GAME_DIR:-$ROOT/tmp/k1_harness}"
OUT="${OUT:-$ROOT/tmp/drive-k1}"
PREFIX="${WINEPREFIX:-$ROOT/tmp/wineprefix-k1}"
DISPLAY_NUM="${DISPLAY_NUM:-78}"
BOOT_WAIT="${BOOT_WAIT:-180}"
CONSOLE_KEY="${CONSOLE_KEY:-grave}"

COMMANDS=("$@")
if [[ ${#COMMANDS[@]} -eq 0 ]]; then
  COMMANDS=("lua status" "lua reload")
fi

mkdir -p "$OUT"
export WINEPREFIX="$PREFIX" WINEDEBUG="${WINEDEBUG:--all}"
export LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=":$DISPLAY_NUM"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$OUT/drive.log"; }
cleanup() {
  pkill -f 'swkotor.exe' 2>/dev/null
  wineserver -k 2>/dev/null || true
  [[ -n "${XVFB_PID:-}" ]] && kill "$XVFB_PID" 2>/dev/null
  return 0
}
trap cleanup EXIT

[[ -f "$GAME_DIR/swkotor.exe" ]] || { log "no game at $GAME_DIR (run spike_headless_k1.sh first)"; exit 1; }

# Cheats gate the console entirely; without this the key does nothing.
INI="$GAME_DIR/swkotor.ini"
if [[ -f "$INI" ]]; then
  grep -qi "EnableCheats" "$INI" || sed -i '/^\[Game Options\]/a EnableCheats=1' "$INI"
  sed -i 's/^EnableCheats=.*/EnableCheats=1/I' "$INI"
  log "EnableCheats: $(grep -i EnableCheats "$INI" | head -1)"
fi

Xvfb ":$DISPLAY_NUM" -screen 0 1024x768x24 -nolisten tcp >"$OUT/xvfb.log" 2>&1 &
XVFB_PID=$!
for _ in $(seq 1 30); do xdpyinfo >/dev/null 2>&1 && break; sleep 0.3; done
xdpyinfo >/dev/null 2>&1 || { log "Xvfb failed"; exit 1; }
ROOT_WID=$(( $(xwininfo -root 2>/dev/null | sed -n 's/.*Window id: \([0-9a-vx]*\).*/\1/p' | head -1) ))
log "Xvfb up, root $ROOT_WID"

wineboot -i >"$OUT/wineboot.log" 2>&1; wineserver -w
log "launching"
( cd "$GAME_DIR" && exec wine swkotor.exe ) >"$OUT/wine.log" 2>&1 &

# Wait for a real game window, not the prefix dialog and not the desktop.
WID=""
for i in $(seq 1 "$BOOT_WAIT"); do
  for w in $(xdotool search --onlyvisible --name '.*' 2>/dev/null); do
    (( w == ROOT_WID )) && continue
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
import -window "$WID" "$OUT/00_menu.png" 2>/dev/null

xdotool windowactivate --sync "$WID" 2>/dev/null || xdotool windowfocus "$WID" 2>/dev/null

# The console only exists in gameplay, so a save has to be loaded first. Without
# one, this stops at the menu and says so rather than typing into nothing.
if [[ -d "$GAME_DIR/Saves" ]] && [[ -n "$(ls -A "$GAME_DIR/Saves" 2>/dev/null)" ]]; then
  log "loading a save to reach gameplay"
  xdotool key --window "$WID" --clearmodifiers Down Down Return; sleep 12
  import -window "$WID" "$OUT/01_loading.png" 2>/dev/null
else
  log "no saves present: the console needs gameplay, so stopping at the menu"
  log "put a save in $GAME_DIR/Saves to drive the console"
  exit 3
fi

log "opening console ($CONSOLE_KEY)"
xdotool key --window "$WID" --clearmodifiers "$CONSOLE_KEY"; sleep 1
import -window "$WID" "$OUT/02_console.png" 2>/dev/null

n=3
for cmd in "${COMMANDS[@]}"; do
  log "typing: $cmd"
  xdotool type --window "$WID" --clearmodifiers --delay 40 "$cmd"
  sleep 0.5
  xdotool key --window "$WID" --clearmodifiers Return
  sleep 2
  import -window "$WID" "$(printf '%s/%02d_after.png' "$OUT" "$n")" 2>/dev/null
  n=$((n+1))
done

log "--- kotorphasor.log ---"
tail -40 "$GAME_DIR/kotorphasor.log" 2>/dev/null | tee -a "$OUT/drive.log" ||
  log "(no kotorphasor.log -- runtime did not start)"
log "screenshots in $OUT"
