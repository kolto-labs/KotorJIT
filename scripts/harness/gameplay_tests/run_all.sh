#!/usr/bin/env bash
# Run every test in this directory and report a summary.
#
#   run_all.sh              fast tests only (kp_luatest, no game, seconds)
#   run_all.sh --live       fast + ship live tests (30/40/50)
#   run_all.sh --live-all   also 10/20/60 live tests (not release-gated)
#
# Fast host-only tests are independent and run concurrently (bounded by
# KP_FAST_JOBS, default 3). Live tests remain serialized: they mutate staged
# game trees, saves, displays, and Wine state, so the shared live-game lock is
# deliberately a hard single slot.
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
FAST_JOBS="${KP_FAST_JOBS:-3}"
if ! [[ "$FAST_JOBS" =~ ^[1-9][0-9]*$ ]]; then
  echo "KP_FAST_JOBS must be a positive integer (got '$FAST_JOBS')" >&2
  exit 2
fi

# Run the host-only prefix in parallel, preserving each test's complete output
# and status for a deterministic summary. There are currently two fast tests,
# but the bounded scheduler also covers future additions without another edit.
fast_count=0
fast_tmp="$ROOT/tmp/gameplay-tests.$$"
mkdir -p "$fast_tmp"
cleanup_fast() { rm -rf "$fast_tmp"; }
trap cleanup_fast EXIT
reap_one_fast() {
  local pid_file pid
  for pid_file in "$fast_tmp"/*.pid; do
    [[ -e "$pid_file" ]] || continue
    pid=$(cat "$pid_file")
    wait "$pid" 2>/dev/null || true
    rm -f "$pid_file"
    fast_count=$((fast_count-1))
    return
  done
}
for t in "${RUN[@]}"; do
  is_live=0
  for live in "${LIVE[@]}"; do [[ "$t" == "$live" ]] && is_live=1; done
  [[ "$is_live" -eq 0 ]] || continue
  while (( fast_count >= FAST_JOBS )); do
    reap_one_fast
  done
  echo "=== $t (parallel host-only) ==="
  log="$fast_tmp/$t.log"
  (bash "$DIR/$t" >"$log" 2>&1; echo "$?" >"$fast_tmp/$t.status") &
  echo "$!" >"$fast_tmp/$t.pid"
  fast_count=$((fast_count+1))
done
while (( fast_count > 0 )); do
  reap_one_fast
done
for t in "${RUN[@]}"; do
  is_live=0
  for live in "${LIVE[@]}"; do [[ "$t" == "$live" ]] && is_live=1; done
  [[ "$is_live" -eq 0 ]] || continue
  log="$fast_tmp/$t.log"
  cat "$log"
  status=$(cat "$fast_tmp/$t.status")
  if [[ "$status" == 0 ]]; then
    total_pass=$((total_pass+1))
  else
    total_fail=$((total_fail+1))
    failed_tests+=("$t")
  fi
  echo
done

# Live tests are intentionally serial, regardless of KP_FAST_JOBS.
for t in "${RUN[@]}"; do
  is_live=0
  for live in "${LIVE[@]}"; do [[ "$t" == "$live" ]] && is_live=1; done
  [[ "$is_live" -eq 1 ]] || continue
  echo "=== $t ==="
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
