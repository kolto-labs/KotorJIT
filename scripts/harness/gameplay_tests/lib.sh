# Shared assertions and setup for scripts/harness/gameplay_tests/*.sh.
#
# See README.md in this directory before writing a new test -- it explains the
# two shapes (kp_luatest vs. live-game) and when each is the right choice.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PASS=0
FAIL=0

ok()   { PASS=$((PASS+1)); echo "  PASS: $*"; }
bad()  { FAIL=$((FAIL+1)); echo "  FAIL: $*" >&2; }

# assert_contains <haystack-file> <needle> <description>
assert_contains() {
  local file="$1" needle="$2" desc="$3"
  if grep -qF "$needle" "$file" 2>/dev/null; then ok "$desc"
  else bad "$desc -- '$needle' not found in $file"; fi
}

# assert_contains_re <haystack-file> <regex> <description>
assert_contains_re() {
  local file="$1" re="$2" desc="$3"
  if grep -qE "$re" "$file" 2>/dev/null; then ok "$desc"
  else bad "$desc -- /$re/ not found in $file"; fi
}

summary_and_exit() {
  echo
  echo "$PASS passed, $FAIL failed"
  [[ "$FAIL" -eq 0 ]]
}

# test_capture <command...>
#
# Some environments block or truncate shell redirects into /tmp (mktemp's
# default). Keep harness scratch under $ROOT/tmp so kp_luatest output is
# actually captured for assert_contains*.
test_capture() {
  mkdir -p "$ROOT/tmp"
  local out
  out=$(mktemp "$ROOT/tmp/gameplay-test.XXXXXX")
  "$@" > "$out" 2>&1
  echo "$out"
}

# deploy_scripts <game-dir> <script-file>...
#
# Every live-game test needs 00_probe.lua deployed alongside whatever it is
# testing -- see scripts/examples/probe/00_probe.lua's own header for why: the
# runtime does not itself log which scripts the engine runs, only the probe
# does, and that is the gameplay-reached oracle live_session.sh depends on.
#
# A test that drives movement (`#key w` and friends) should also pass
# 10_position_trace.lua -- see its own header. There is no visual way to
# confirm a keypress actually moved the character, so a test that drives
# movement and never checks for [trace] lines can pass on a hang.
deploy_scripts() {
  local game_dir="$1"; shift
  mkdir -p "$game_dir/kotorjit/scripts"
  rm -f "$game_dir/kotorjit/scripts"/*.lua
  cp "$ROOT/scripts/examples/probe/00_probe.lua" "$@" "$game_dir/kotorjit/scripts/"
}

# start_live_session <game-dir> <out-dir> <display-num>
#
# Boots live_session.sh in the background, waits for it to reach gameplay, and
# leaves send() ready to use. On failure to reach gameplay, records it and
# exits the whole test script -- there is nothing a caller can usefully do
# with a session that never came up.
#
# Every one of the four live tests had grown its own copy of this. Two of the
# numbers in it are not arbitrary: a GAME_DIR backed by real disk (as opposed
# to /dev/shm) has been observed taking close to two minutes just to reach
# gameplay. A flat 120s outer ceiling left effectively no margin against
# that -- one run failed with "session never reached gameplay" when the
# session was in fact seconds from succeeding: the outer poll gave up, its own
# EXIT trap touched `stop`, and live_session.sh saw that stop file the instant
# it opened its queue, before ever reading a command. 240s gives real headroom
# without letting a genuinely hung boot run forever.
start_live_session() {
  local game_dir="$1" out="$2" display="$3"
  # A global, not a local: cleanup() is invoked later by the EXIT trap, after
  # this function has already returned and its locals no longer exist. A
  # `local out` here reads fine at a glance but crashes under `set -u` the
  # first time the trap actually fires -- found by running this for real, not
  # by re-reading the script.
  LIVE_OUT="$out"
  GAME_DIR="$game_dir" OUT="$out" DISPLAY_NUM="$display" \
    BOOT_WAIT=300 LOAD_WAIT=600 POST_LOAD_WAIT="${POST_LOAD_WAIT:-2}" \
    SPLASH_WAIT="${SPLASH_WAIT:-120}" \
    "$ROOT/scripts/harness/live_session.sh" > "$out.nohup.log" 2>&1 &
  SESSION_PID=$!
  cleanup() { touch "$LIVE_OUT/stop" 2>/dev/null; wait "$SESSION_PID" 2>/dev/null; }
  trap cleanup EXIT

  for _ in $(seq 1 240); do [[ -f "$out/ready" ]] && break; sleep 1; done
  if [[ ! -f "$out/ready" ]]; then
    bad "session never reached gameplay -- see $out.nohup.log and $out/drive.log"
    summary_and_exit; exit $?
  fi

  rm -f "$out/done"
  echo "0" > "$out/done"

  Q="$(cd "$out" && pwd)/queue"
  D="$(cd "$out" && pwd)/done"
}

# send <console-line-or-control-line>
#
# Requires start_live_session first. Blocks until live_session.sh reports the
# line processed, or 90s pass. Generous on purpose: a warp or a multi-second
# #sleep genuinely takes a while, and a slow queue is a different, far more
# common failure than a truly hung one.
send() {
  [[ -n "${Q:-}" ]] || { echo "send: Q not set (call start_live_session first)" >&2; return 1; }
  local prev target
  prev=$(cat "$D" 2>/dev/null || echo 0)
  printf '%s\n' "$1" >> "$Q"
  target=$((prev + 1))
  for _ in $(seq 1 240); do
    [[ "$(cat "$D" 2>/dev/null || echo 0)" -ge "$target" ]] && return 0
    sleep 0.5
  done
  echo "send: timed out waiting for queue line $target (done=$(cat "$D" 2>/dev/null || echo missing))" >&2
  return 1
}
