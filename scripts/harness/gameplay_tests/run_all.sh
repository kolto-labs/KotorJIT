#!/usr/bin/env bash
# Run every test in this directory and report a summary.
#
#   run_all.sh              fast tests only (kp_luatest, no game, seconds)
#   run_all.sh --live       fast tests + live-game tests (real Wine boots, ~15min)
#
# Live tests run one at a time, in series, on their own DISPLAY_NUM each -- see
# each test_*.sh for the number it uses -- so nothing here needs the locking
# in scripts/harness/lock.sh to coordinate between them.
set -uo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"

FAST=(test_arbitration.sh test_quarantine.sh)
LIVE=(test_battle_meditation.sh test_sith_patrol_alarm.sh test_ahto_city_law.sh test_alignment_drift.sh)

RUN=("${FAST[@]}")
[[ "${1:-}" == "--live" ]] && RUN+=("${LIVE[@]}")

total_pass=0 total_fail=0 failed_tests=()
for t in "${RUN[@]}"; do
  echo "=== $t ==="
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
[[ "${1:-}" == "--live" ]] || echo "(--live not passed: skipped ${#LIVE[@]} live-game test(s))"
[[ "$total_fail" -eq 0 ]]
