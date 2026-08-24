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
  # A save sitting still fires heartbeats and almost nothing else, so it proves
  # one hook works and says nothing about the rest. This sequence deliberately
  # moves, fights and mutates state, because those drive the events the caves
  # exist to intercept:
  #
  #   warp         tears a module down and builds another: module load/unload,
  #                area enter/exit, creature spawn, trigger setup
  #   end_m01aa    the Endar Spire, which has hostile Sith aboard, so arriving
  #                starts real combat: attack rounds, damage, death
  #   heal etc.    mutate creature and party state, which drives the stat and
  #                effect paths rather than only the idle ones
  #
  # Short on purpose. Every warp costs a module load under llvmpipe, so the value
  # is in variety rather than repetition.
  COMMANDS=(
    "lua status"
    "warp end_m01aa"     # combat module: Sith aboard
    "heal"
    "addlevel"
    "givecredits 5000"
    "revealmap"
    "lua status"
    "warp tar_m02aa"     # Taris apartments: transition, no combat
    "lua status"
    "warp danm13"        # Dantooine: a third, different area type
    "lua status"
  )
fi

# A previous run that was interrupted leaves the game and its Xvfb alive. The
# next run then shares the display and the log files with a process it does not
# know about, and the two interleave: one writes "loading..." while the other
# waits for a window it will never own. That is a confusing hour, so refuse to
# start rather than inherit it.
if pgrep -f "swkotor.exe" >/dev/null 2>&1 || pgrep -f "Xvfb :$DISPLAY_NUM" >/dev/null 2>&1; then
  if [[ "${FORCE:-0}" == "1" ]]; then
    echo "killing a previous run (FORCE=1)" >&2
    pkill -f 'swkotor.exe' 2>/dev/null; pkill -f "Xvfb :$DISPLAY_NUM" 2>/dev/null
    WINEPREFIX="$PREFIX" wineserver -k 2>/dev/null
    sleep 3
  else
    echo "a game or Xvfb from a previous run is still alive; re-run with FORCE=1" >&2
    exit 6
  fi
fi

mkdir -p "$OUT"
rm -f "$OUT"/drive.log "$OUT"/wine.log     # never append across runs
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
    # skip the intro movie window; see the note in spike_headless_k1.sh
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
import -window "$WID" "$OUT/00_menu.png" 2>/dev/null

xdotool windowactivate --sync "$WID" 2>/dev/null || xdotool windowfocus "$WID" 2>/dev/null

# Input has to look real. xdotool's --window form uses XSendEvent, and the game
# reads input through DirectInput, which ignores synthetic events -- the menu
# renders, the keystrokes land nowhere, and it looks like the game hung. Driving
# the pointer and keyboard through XTEST instead produces events indistinguishable
# from a person, at the cost of needing the window focused and real coordinates.
read -r WX WY WW WH < <(xdotool getwindowgeometry --shell "$WID" 2>/dev/null |
                        sed -n 's/^X=//p;s/^Y=//p;s/^WIDTH=//p;s/^HEIGHT=//p' | paste -sd' ')
click_at() {  # $1,$2 = fraction of the window, 0..1
  local x y
  x=$(python3 -c "print(int($WX + $WW * $1))")
  y=$(python3 -c "print(int($WY + $WH * $2))")
  log "  click ($x,$y)"
  # Separate invocations on purpose. Chaining move and click in one xdotool
  # command sends them faster than the game samples the pointer, and the click
  # lands at the old position or is missed entirely -- which looks exactly like
  # bad coordinates and sent me hunting the wrong thing twice.
  xdotool mousemove --sync "$x" "$y"
  sleep 0.4
  xdotool click --clearmodifiers 1
  sleep 0.4
}

# Click, then check the picture actually changed. A menu button that swallows a
# click leaves the harness waiting on something that already failed.
click_until_changed() {  # $1,$2 = fraction, $3 = attempts, $4 = what it is
  local before after
  for attempt in $(seq 1 "${3:-3}"); do
    before=$(identify -format "%#" <(import -window "$WID" png:- 2>/dev/null) 2>/dev/null || echo a)
    click_at "$1" "$2"
    sleep 2
    after=$(identify -format "%#" <(import -window "$WID" png:- 2>/dev/null) 2>/dev/null || echo b)
    if [[ "$before" != "$after" ]]; then
      log "  $4 took effect (attempt $attempt)"
      return 0
    fi
    log "  $4 did not change the screen, retrying"
  done
  return 1
}

# The console only exists in gameplay, so a save has to be loaded first. Without
# one, this stops at the menu and says so rather than typing into nothing.
if [[ -d "$GAME_DIR/Saves" ]] && [[ -n "$(ls -A "$GAME_DIR/Saves" 2>/dev/null)" ]]; then
  log "loading a save to reach gameplay (window ${WW}x${WH} at ${WX},${WY})"
  click_until_changed 0.583 0.530 3 "LOAD GAME" || { log "main menu did not respond"; exit 5; }
  import -window "$WID" "$OUT/01a_loadmenu.png" 2>/dev/null
  # Coordinates read off tmp/drive-k1/01a_loadmenu.png at 1024x768: the first
  # save entry sits at (383,256) and the LOAD button at (512,568). The topmost
  # save is already selected when the menu opens, so clicking it is belt and
  # braces rather than required.
  click_at 0.374 0.333        # first save in the list
  click_until_changed 0.500 0.740 4 "LOAD" || { log "LOAD never took"; exit 5; }

  # Waiting on the picture does not work. A fixed sleep either wastes time or
  # gives up mid-load; "wait for colour" fires instantly because the menu is
  # still up when LOAD is clicked; and "wait for dark then colour" fires on
  # KOTOR's own loading screen, which has art on it.
  #
  # So ask the game instead of looking at it. k_def_heartbt01 is the stock
  # creature heartbeat: it cannot run until the module is up and creatures
  # exist, and the runtime already logs every script the engine runs. That is an
  # oracle for "we are in gameplay" rather than a proxy for it.
  LOADED=0
  for i in $(seq 1 "${LOAD_WAIT:-180}"); do
    if grep -qE "k_def_heartbt01|k_ai_master" "$OUT/wine.log" 2>/dev/null; then
      LOADED=1; log "  in gameplay at t+${i}s (heartbeat script seen)"; break
    fi
    if (( i % 15 == 0 )); then log "  loading... t+${i}s"; fi
    sleep 1
  done
  import -window "$WID" "$OUT/01_loading.png" 2>/dev/null
  if (( LOADED == 0 )); then
    log "no gameplay script ran within ${LOAD_WAIT:-180}s; the console needs"
    log "gameplay, so stopping rather than typing into the menu"
    exit 4
  fi
  sleep 3   # let a few more heartbeats run before typing
else
  log "no saves present: the console needs gameplay, so stopping at the menu"
  log "put a save in $GAME_DIR/Saves to drive the console"
  exit 3
fi

log "opening console ($CONSOLE_KEY)"
xdotool key --clearmodifiers "$CONSOLE_KEY"; sleep 1
import -window "$WID" "$OUT/02_console.png" 2>/dev/null

n=3
for cmd in "${COMMANDS[@]}"; do
  log "typing: $cmd"
  xdotool type --clearmodifiers --delay 60 "$cmd"
  sleep 0.5
  xdotool key --clearmodifiers Return
  # A warp is a whole module load, so it needs far longer than a status query.
  case "$cmd" in
    warp*) log "  warping, waiting for the module"; sleep "${WARP_WAIT:-45}" ;;
    *)     sleep 3 ;;
  esac
  import -window "$WID" "$(printf '%s/%02d_after.png' "$OUT" "$n")" 2>/dev/null
  n=$((n+1))
done

log "--- kotorphasor.log ---"
tail -40 "$GAME_DIR/kotorphasor.log" 2>/dev/null | tee -a "$OUT/drive.log" ||
  log "(no kotorphasor.log -- runtime did not start)"
log "screenshots in $OUT"
