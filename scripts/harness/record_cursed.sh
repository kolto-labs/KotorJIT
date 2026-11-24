#!/usr/bin/env bash
# Run one cursed demo as a state-gated route and record it.
#
#   ./scripts/harness/record_cursed.sh 30_necromancer
#   ./scripts/harness/record_cursed.sh all
#   RECORD=0 ./scripts/harness/record_cursed.sh 30_necromancer   # log proof only
#
# For each demo:
#   1. deploy scripts/examples/cursed/<name>.lua (alone) into the game copy's
#      hyperstim/scripts directory, so the curse is armed when the VM binds;
#   2. run scripts/harness/scenarios/cursed/<name>.toml through `kpharness run`
#      in the background (it boots its own Xvfb and writes session.json);
#   3. once session.json names the display, start x11grab on it;
#   4. wait for the run to end, stop the capture, cut a gif, and copy the
#      route report plus the "[cursed:*]" oracle lines next to the video.
#
# Output: tmp/demos/cursed/<name>.{mp4,gif,oracle.txt,report.json,run.log}
# Exit status is the route's: 0 only if every gate in the TOML passed.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
case "${1:-}" in
  50_chaos_roulette|60_rave)
    echo "record_cursed: retired public example; internal regression fixtures remain in tools/tests/examples/fixtures/legacy/cursed" >&2
    exit 2 ;;
esac
source "$ROOT/scripts/harness/harness_paths.sh"
preflight_tmp_write || exit 1
source "$ROOT/scripts/harness/record.sh"

GAME_DIR="${GAME_DIR:-$ROOT/tmp/k1_harness}"
DEMO_DIR="${DEMO_DIR:-$ROOT/tmp/demos/cursed}"
RECORD="${RECORD:-1}"
export KP_CHANNEL_TIMEOUT="${KP_CHANNEL_TIMEOUT:-90}"   # loaded host: a world observation can take >30s
GIF_SECONDS="${GIF_SECONDS:-12}"
TARGET="${1:-}"

[[ -f "$GAME_DIR/swkotor.exe" ]] || {
  echo "record_cursed: no game copy at $GAME_DIR (run spike_headless_k1.sh first)" >&2
  exit 1
}

deploy() {
  local script="$1"
  mkdir -p "$GAME_DIR/hyperstim/scripts"
  rm -f "$GAME_DIR/hyperstim/scripts"/*.lua
  cp "$script" "$GAME_DIR/hyperstim/scripts/"
}

# rec_mark hook: the run log is polled for the first oracle line so the gif
# can be cut at the first curse rather than at the load screen.
watch_oracle() {
  local pid="$1"
  while kill -0 "$pid" 2>/dev/null; do
    if grep -aq '\[cursed:' "$GAME_DIR/hyperstim.log" 2>/dev/null; then
      rec_mark "first curse"
      return
    fi
    sleep 1
  done
}

run_demo() {
  local base="$1"
  local script="$ROOT/scripts/examples/cursed/${base}.lua"
  local route="$ROOT/scripts/harness/scenarios/cursed/${base}.toml"
  [[ -f "$script" ]] || { echo "no script: $script" >&2; return 1; }
  [[ -f "$route" ]] || { echo "no route: $route" >&2; return 1; }

  mkdir -p "$DEMO_DIR"
  local out="$DEMO_DIR/$base"
  rm -f "$out".{mp4,gif,oracle.txt,report.json,run.log,marks,ffmpeg.log}
  rm -f "$GAME_DIR/hyperstim.log"
  deploy "$script"

  "$ROOT/scripts/harness/kpharness.sh" run "$route" >"$out.run.log" 2>&1 &
  local pid=$!

  local disp=""
  for _ in $(seq 1 600); do
    if [[ -f "$GAME_DIR/session.json" ]]; then
      disp=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["display"])' \
             "$GAME_DIR/session.json" 2>/dev/null)
      [[ -n "$disp" && "$disp" != "-1" ]] && break
    fi
    kill -0 "$pid" 2>/dev/null || break
    sleep 1
  done

  local recording=0
  if [[ "$RECORD" == "1" && -n "$disp" && "$disp" != "-1" ]]; then
    # give Xvfb a moment to come up with the game window before grabbing
    for _ in $(seq 1 30); do
      DISPLAY=":$disp" xdpyinfo >/dev/null 2>&1 && break
      sleep 1
    done
    rec_start "$disp" "$out" && recording=1
  fi
  local watcher=""
  if [[ "$recording" == 1 ]]; then
    watch_oracle "$pid" &
    watcher=$!
  fi

  # The runner writes report.json before the session tears down its Xvfb.
  # Stop the capture on that, not on process exit: x11grab dies uncleanly
  # (no moov atom, unplayable file) if the display vanishes under it.
  if [[ "$recording" == 1 ]]; then
    local run_dir
    run_dir=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["run_dir"])' \
              "$GAME_DIR/session.json" 2>/dev/null)
    while kill -0 "$pid" 2>/dev/null; do
      [[ -n "$run_dir" && -f "$run_dir/report.json" ]] && break
      sleep 1
    done
    [[ -n "$watcher" ]] && { kill "$watcher" 2>/dev/null; wait "$watcher" 2>/dev/null; }
    rec_stop
  fi

  wait "$pid"
  local rc=$?

  grep -a '\[cursed:' "$GAME_DIR/hyperstim.log" > "$out.oracle.txt" 2>/dev/null
  local run_dir
  run_dir=$(sed -n 's/.*-> \(.*\)\/report.json$/\1/p' "$out.run.log" | tail -1)
  [[ -n "$run_dir" && -f "$run_dir/report.json" ]] && cp "$run_dir/report.json" "$out.report.json"

  if [[ "$recording" == 1 && -s "$out.mp4" ]]; then
    # the gif starts where the first curse fired, from the recording marks
    local first
    first=$(awk -F'\t' 'NR==1{print $1}' "$out.marks" 2>/dev/null)
    rec_gif "$out.mp4" "$out.gif" "${first:-00:00:05}" "$GIF_SECONDS" 640
  fi

  echo "== $base: $(tail -2 "$out.run.log" | head -1)"
  echo "   oracle lines: $(wc -l < "$out.oracle.txt" 2>/dev/null || echo 0)  -> $out.oracle.txt"
  return "$rc"
}

status=0
if [[ "$TARGET" == "all" ]]; then
  for f in "$ROOT"/scripts/examples/cursed/*.lua; do
    b=$(basename "$f" .lua)
    run_demo "$b" || status=1
  done
elif [[ -n "$TARGET" ]]; then
  run_demo "$TARGET" || status=1
else
  echo "usage: $0 <name|all>   (names: $(ls "$ROOT"/scripts/examples/cursed/*.lua | xargs -n1 basename | sed 's/\.lua$//' | tr '\n' ' '))" >&2
  exit 2
fi
exit "$status"
