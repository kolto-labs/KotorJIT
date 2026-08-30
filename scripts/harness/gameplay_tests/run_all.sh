#!/usr/bin/env bash
# Run every test in this directory and report a summary.
#
#   run_all.sh              fast tests only (kp_luatest, no game, seconds)
#   run_all.sh --live       fast + ship live tests (30/40/50)
#   run_all.sh --live-all   also 10/20/60 live tests (not release-gated)
#
# Live tests run one at a time, in series, on their own DISPLAY_NUM each -- see
# each test_*.sh for the number it uses -- so nothing here needs the locking
# in scripts/harness/lock.sh to coordinate between them.
set -uo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$DIR/../../.." && pwd)"

FAST=(test_arbitration.sh test_quarantine.sh)
# Live tests whose matching demo_play oracle has been seen on a real boot.
LIVE=(test_battle_meditation.sh test_alignment_drift.sh test_enclave_arrival.sh)
# Implemented but not release-gated: perception/attacker-direction/companion-HP flakes.
LIVE_WIP=(test_sith_patrol_alarm.sh test_ahto_city_law.sh test_party_wounded.sh)

RUN=("${FAST[@]}")
[[ "${1:-}" == "--live" ]] && RUN+=("${LIVE[@]}")
[[ "${1:-}" == "--live-all" ]] && RUN+=("${LIVE[@]}" "${LIVE_WIP[@]}")

total_pass=0 total_fail=0 failed_tests=()
LIVE_LOCK="$ROOT/tmp/harness-locks/live-game.lock"
mkdir -p "$ROOT/tmp/harness-locks"
for t in "${RUN[@]}"; do
  echo "=== $t ==="
  is_live=0
  for live in "${LIVE[@]}"; do [[ "$t" == "$live" ]] && is_live=1; done
  if [[ "$is_live" -eq 1 ]]; then
    exec 9>"$LIVE_LOCK"
    flock 9 || { echo "another live gameplay test holds $LIVE_LOCK" >&2; exit 1; }
  fi
  if bash "$DIR/$t"; then
    total_pass=$((total_pass+1))
  else
    total_fail=$((total_fail+1))
    failed_tests+=("$t")
  fi
  echo
done

echo "======================================"
echo "$total_pass test file(s) passed, $total_fail failed"
[[ "$total_fail" -eq 0 ]] || printf 'failed: %s\n' "${failed_tests[@]}"
[[ "${1:-}" == "--live" || "${1:-}" == "--live-all" ]] || \
  echo "(--live not passed: skipped ${#LIVE[@]} ship live tests + ${#LIVE_WIP[@]} wip)"
[[ "$total_fail" -eq 0 ]]
