#!/usr/bin/env bash
# Step 0 spike: does KOTOR 1 reach a rendered game window under Xvfb + Wine, and
# can xdotool drive it? Gates Tier 2 verification, so it runs before any C++.
#
# Detection is deliberately strict: the Wine prefix-update dialog is 300x81 and
# will otherwise be mistaken for the game. We require a live swkotor.exe process
# AND a window at least 640x480 AND a non-uniform frame.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# Where the game is, without anyone writing down a path. KOTOR1_DIR overrides;
# otherwise kpdiscover walks Steam's own library list and the platform defaults,
# and identifies an install by the files it contains rather than its name.
if [[ -z "${VANILLA:-}" ]]; then
  VANILLA="$(python3 "$ROOT/tools/kpdiscover.py" --k1 2>/dev/null || true)"
fi
if [[ -z "${VANILLA:-}" || ! -d "$VANILLA" ]]; then
  echo "no KOTOR 1 install found." >&2
  echo "Set KOTOR1_DIR, or add [paths] k1 = \"...\" to kotorphasor.toml." >&2
  exit 1
fi
GAME_DIR="${GAME_DIR:-$ROOT/tmp/k1_harness}"
OUT="${OUT:-$ROOT/tmp/spike-k1}"
PREFIX="${WINEPREFIX:-$ROOT/tmp/wineprefix-k1}"
DISPLAY_NUM="${DISPLAY_NUM:-77}"
BOOT_WAIT="${BOOT_WAIT:-150}"

mkdir -p "$OUT"
export WINEPREFIX="$PREFIX"
export WINEDEBUG="${WINEDEBUG:--all}"
export LIBGL_ALWAYS_SOFTWARE=1
export DISPLAY=":$DISPLAY_NUM"
# Without this, wine inherits the real desktop's D-Bus session and Wayland
# display, and its portal calls (file dialogs, some DXVK paths) register
# against the REAL session -- see env_isolate.sh.
source "$ROOT/scripts/harness/env_isolate.sh"
isolate_desktop_env

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$OUT/spike.log"; }

cleanup() {
  log "cleanup"
  # Match the process NAME, not the whole command line. -f matches any process
  # whose arguments merely mention the game -- on this machine an unrelated
  # analysis job runs with the executable's path in its argv, and killing on -f
  # would have killed that. -x on the name matches only the game itself.
  pkill -x swkotor.exe 2>/dev/null
  wineserver -k 2>/dev/null || true
  [[ -n "${XVFB_PID:-}" ]] && kill "$XVFB_PID" 2>/dev/null
  return 0
}
trap cleanup EXIT

log "=== Hyperstim Step 0 spike ==="

# 0. writable working copy -----------------------------------------------------
# The vanilla reference stays pristine; the game writes ini/saves/logs.
if [[ ! -f "$GAME_DIR/swkotor.exe" ]]; then
  log "creating writable game copy (first run, ~3.4G)"
  mkdir -p "$GAME_DIR"
  rsync -a --info=none "$VANILLA/" "$GAME_DIR/" || { log "FAIL: rsync"; exit 1; }
fi
log "game dir: $GAME_DIR"

# Windowed at the Xvfb size, so no mode switch is attempted.
INI="$GAME_DIR/swkotor.ini"
if [[ -f "$INI" ]]; then
  sed -i 's/^FullScreen=.*/FullScreen=0/I; s/^Width=.*/Width=800/I; s/^Height=.*/Height=600/I' "$INI"
  grep -iE "^(FullScreen|Width|Height|Disable Movies)=" "$INI" | while read -r l; do log "  ini: $l"; done
fi
source "$ROOT/scripts/harness/ini_tune.sh"
ini_headless "$INI"   # EnableCheats + Frame Buffer=0, see ini_tune.sh

# 1. virtual display -----------------------------------------------------------
Xvfb ":$DISPLAY_NUM" -screen 0 1024x768x24 -nolisten tcp >"$OUT/xvfb.log" 2>&1 &
XVFB_PID=$!
for _ in $(seq 1 30); do
  xdpyinfo -display ":$DISPLAY_NUM" >/dev/null 2>&1 && break
  sleep 0.3
done
xdpyinfo -display ":$DISPLAY_NUM" >/dev/null 2>&1 || { log "FAIL: Xvfb never came up"; exit 1; }
# The root window is screen-sized and unnamed; without excluding it every scan
# reports a 1024x768 "candidate" that is really just the empty desktop.
ROOT_WID=$(xwininfo -root 2>/dev/null | sed -n 's/.*Window id: \([0-9a-vx]*\).*/\1/p' | head -1)
ROOT_DEC=$(( ROOT_WID ))
log "Xvfb up (pid $XVFB_PID), root window $ROOT_DEC"

# 2. wine prefix — fully settle BEFORE launching -------------------------------
# Deliberately NOT setting WINEARCH. Wine 11's wow64 runs 32-bit PE inside a
# win64 prefix (verified: our i686 LuaJIT build runs there). Forcing win32 onto
# an existing win64 prefix yields "could not load kernel32.dll, status c0000135".
log "initialising wine prefix (blocking)"
wineboot -i >"$OUT/wineboot.log" 2>&1
wineserver -w
ARCH=$(grep -m1 '#arch' "$PREFIX/system.reg" 2>/dev/null)
log "prefix settled ($ARCH)"

# 3. launch --------------------------------------------------------------------
log "launching swkotor.exe"
( cd "$GAME_DIR" && exec wine swkotor.exe ) >"$OUT/wine.log" 2>&1 &
LAUNCH_PID=$!

# 4. wait for a real game window ----------------------------------------------
RENDERED=0
for i in $(seq 1 "$BOOT_WAIT"); do
  ALIVE=no; pgrep -x swkotor.exe >/dev/null 2>&1 && ALIVE=yes

  best_w=0; best_id=""
  for WID in $(xdotool search --onlyvisible --name '.*' 2>/dev/null); do
    (( WID == ROOT_DEC )) && continue          # skip the desktop itself
    # The game opens a separate "SW Movie Player Window" for the intro before it
    # opens the real one. A scan that takes the first large window gets the movie
    # and then waits forever for something that already happened.
    case "$(xdotool getwindowname "$WID" 2>/dev/null)" in
      *Movie*) continue ;;
    esac
    GEO=$(xdotool getwindowgeometry --shell "$WID" 2>/dev/null)
    W=$(sed -n 's/^WIDTH=//p' <<<"$GEO"); H=$(sed -n 's/^HEIGHT=//p' <<<"$GEO")
    [[ -z "${W:-}" || -z "${H:-}" ]] && continue
    if (( W >= 640 && H >= 480 && W > best_w )); then best_w=$W; best_id=$WID; fi
  done

  if [[ -n "$best_id" ]]; then
    NAME=$(xdotool getwindowname "$best_id" 2>/dev/null)
    log "t+${i}s candidate id=$best_id name='$NAME' ${best_w}px alive=$ALIVE"
    import -display ":$DISPLAY_NUM" -window "$best_id" "$OUT/game_${i}.png" 2>/dev/null
    if [[ -f "$OUT/game_${i}.png" ]]; then
      COLORS=$(identify -format "%k" "$OUT/game_${i}.png" 2>/dev/null || echo 0)
      log "  colours: $COLORS"
      if [[ "${COLORS:-0}" -gt 64 ]]; then
        RENDERED=1; log "RENDERED game window at t+${i}s"; break
      fi
    fi
  elif (( i % 10 == 0 )); then
    log "t+${i}s no game window yet (swkotor alive=$ALIVE)"
  fi

  # A loader failure keeps a stub process alive forever; fail fast on it instead
  # of burning the whole timeout staring at a black screen.
  if grep -qE "could not load|err:module|Application could not be started" "$OUT/wine.log" 2>/dev/null; then
    log "t+${i}s: FATAL loader error in wine.log"
    grep -m5 -E "could not load|err:module|Application could not" "$OUT/wine.log" | while read -r l; do log "  $l"; done
    break
  fi
  if [[ "$ALIVE" == "no" ]] && (( i > 12 )); then
    log "t+${i}s: swkotor.exe is not running"; break
  fi
  sleep 1
done

# 5. report --------------------------------------------------------------------
log "--- wine.log (last 40) ---"
tail -40 "$OUT/wine.log" 2>/dev/null | tee -a "$OUT/spike.log"

if [[ "$RENDERED" -eq 1 ]]; then
  log "RESULT: PASS - game rendered under Xvfb"
  exit 0
fi
log "RESULT: FAIL - no rendered game window within ${BOOT_WAIT}s"
exit 2
