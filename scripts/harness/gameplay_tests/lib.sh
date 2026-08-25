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

# deploy_scripts <game-dir> <script-file>...
#
# Every live-game test needs 00_probe.lua deployed alongside whatever it is
# testing -- see scripts/examples/probe/00_probe.lua's own header for why: the
# runtime does not itself log which scripts the engine runs, only the probe
# does, and that is the gameplay-reached oracle live_session.sh depends on.
deploy_scripts() {
  local game_dir="$1"; shift
  mkdir -p "$game_dir/kotorphasor/scripts"
  rm -f "$game_dir/kotorphasor/scripts"/*.lua
  cp "$ROOT/scripts/examples/probe/00_probe.lua" "$@" "$game_dir/kotorphasor/scripts/"
}
