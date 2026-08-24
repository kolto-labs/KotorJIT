#!/usr/bin/env bash
# Measure where the time actually goes when booting the game headless.
#
# Written because "it is slow" was not a diagnosis. Module load was taking
# anywhere from thirty seconds to over ten minutes, and the obvious suspect --
# software rendering -- is only one of at least four candidates: the renderer,
# game logic on one core, disk, or our own hook doing work on every script the
# engine runs.
#
# So this samples CPU while the game boots and reports the shape of it. A
# renderer bottleneck pegs many cores; game logic pegs one; disk pegs none.
#
#   measure_boot.sh                 default settings
#   RES=640x480 measure_boot.sh     smaller framebuffer
#   NO_RUNTIME=1 measure_boot.sh    without our DLL, to price our own overhead
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GAME_DIR="${GAME_DIR:-$ROOT/tmp/k1_harness}"
OUT="${OUT:-$ROOT/tmp/measure}"
PREFIX="${WINEPREFIX:-$ROOT/tmp/wineprefix-k1}"
DISPLAY_NUM="${DISPLAY_NUM:-79}"
RES="${RES:-1024x768}"
BUDGET="${BUDGET:-240}"
LABEL="${LABEL:-default}"

mkdir -p "$OUT"
export WINEPREFIX="$PREFIX" WINEDEBUG="${WINEDEBUG:--all}" DISPLAY=":$DISPLAY_NUM"
[[ "${SOFTWARE:-1}" == "1" ]] && export LIBGL_ALWAYS_SOFTWARE=1 || unset LIBGL_ALWAYS_SOFTWARE
[[ -n "${LP_NUM_THREADS:-}" ]] && export LP_NUM_THREADS
[[ -n "${MESA_LOADER_DRIVER_OVERRIDE:-}" ]] && export MESA_LOADER_DRIVER_OVERRIDE

R="$OUT/$LABEL.txt"
: > "$R"
say() { echo "$*" | tee -a "$R"; }

cleanup() {
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

if pgrep -x swkotor.exe >/dev/null 2>&1; then
  echo "a game from a previous run is alive; refusing" >&2; exit 6
fi

# Our DLL is loaded by the proxy, so moving the proxy aside is enough to price a
# boot without it. Nothing else in the game folder changes.
if [[ "${NO_RUNTIME:-0}" == "1" && -f "$GAME_DIR/binkw32_real.dll" ]]; then
  cp -f "$GAME_DIR/binkw32.dll" "$OUT/.proxy.bak"
  cp -f "$GAME_DIR/binkw32_real.dll" "$GAME_DIR/binkw32.dll"
  restore_proxy=1
fi
restore() {
  [[ "${restore_proxy:-0}" == "1" ]] && cp -f "$OUT/.proxy.bak" "$GAME_DIR/binkw32.dll"
  return 0
}
trap 'cleanup; restore' EXIT

Xvfb ":$DISPLAY_NUM" -screen 0 "${RES}x24" -nolisten tcp >"$OUT/xvfb-$LABEL.log" 2>&1 &
XVFB_PID=$!
for _ in $(seq 1 40); do xdpyinfo >/dev/null 2>&1 && break; sleep 0.25; done
xdpyinfo >/dev/null 2>&1 || { say "Xvfb failed"; exit 1; }

say "=== $LABEL ==="
say "res=$RES software=${SOFTWARE:-1} LP_NUM_THREADS=${LP_NUM_THREADS:-unset} runtime=$([[ "${NO_RUNTIME:-0}" == "1" ]] && echo no || echo yes)"
say "renderer: $(glxinfo -B 2>/dev/null | grep -i 'OpenGL renderer' | head -1 | cut -c1-80)"

wineboot -i >/dev/null 2>&1; wineserver -w
START=$(date +%s)
( cd "$GAME_DIR" && exec wine swkotor.exe ) >"$OUT/wine-$LABEL.log" 2>&1 &

MENU_AT=""
PEAK_CPU=0
SAMPLES=0
CPU_SUM=0
for i in $(seq 1 "$BUDGET"); do
  # Total CPU across every wine thread of the game.
  CPU=$(ps -C swkotor.exe -o %cpu= 2>/dev/null | awk '{s+=$1} END {printf "%.0f", s+0}')
  [[ -z "$CPU" ]] && CPU=0
  (( CPU > PEAK_CPU )) && PEAK_CPU=$CPU
  CPU_SUM=$((CPU_SUM + CPU)); SAMPLES=$((SAMPLES + 1))

  if [[ -z "$MENU_AT" ]]; then
    for w in $(xdotool search --onlyvisible --name '.*' 2>/dev/null); do
      case "$(xdotool getwindowname "$w" 2>/dev/null)" in *Movie*) continue ;; esac
      read -r W H < <(xdotool getwindowgeometry --shell "$w" 2>/dev/null |
                      sed -n 's/^WIDTH=//p;s/^HEIGHT=//p' | paste -sd' ')
      [[ -z "${W:-}" ]] && continue
      if (( W >= 640 && H >= 480 )); then
        C=$(identify -format "%k" <(import -window "$w" png:- 2>/dev/null) 2>/dev/null || echo 0)
        if (( C > 2000 )); then MENU_AT=$(( $(date +%s) - START )); break; fi
      fi
    done
  fi
  [[ -n "$MENU_AT" ]] && (( i > 10 )) && break
  sleep 1
done

AVG=$(( SAMPLES > 0 ? CPU_SUM / SAMPLES : 0 ))
say "time to menu : ${MENU_AT:-never}s"
say "cpu peak     : ${PEAK_CPU}%  (100 = one core, 1200 = all twelve)"
say "cpu average  : ${AVG}%"
if (( PEAK_CPU > 400 )); then
  say "verdict      : many cores busy -- consistent with software rasterisation"
elif (( PEAK_CPU > 130 )); then
  say "verdict      : more than one core but not many -- mixed"
elif (( PEAK_CPU > 60 )); then
  say "verdict      : about one core -- game logic, NOT the renderer"
else
  say "verdict      : barely any CPU -- waiting on disk or stalled"
fi
