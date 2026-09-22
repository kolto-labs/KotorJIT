#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
DIR="$TMP/a/b/c/gameplay_tests"
mkdir -p "$DIR"
cp "$ROOT/scripts/harness/gameplay_tests/run_all.sh" "$DIR/run_all.sh"

names=(test_arbitration.sh test_quarantine.sh test_battle_meditation.sh
  test_alignment_drift.sh test_enclave_arrival.sh test_sith_patrol_alarm.sh
  test_ahto_city_law.sh test_party_wounded.sh)
for name in "${names[@]}"; do
  cat >"$DIR/$name" <<'EOF'
#!/usr/bin/env bash
set -eu
name="$(basename "$0")"
if [[ "$name" != test_arbitration.sh && "$name" != test_quarantine.sh ]]; then
  if flock -n "${EXPECTED_LOCK}" true; then
    echo "shared live lock is not held for ${name}" >&2; exit 8
  fi
  mkdir "${TRACE_DIR}/live-active" 2>/dev/null || { echo overlap >&2; exit 9; }
  printf 'live:%s\n' "$name" >>"${TRACE_DIR}/trace"
  sleep 0.03
  rmdir "${TRACE_DIR}/live-active"
else
  printf 'fast:%s\n' "$name" >>"${TRACE_DIR}/trace"
fi
EOF
  chmod +x "$DIR/$name"
done

run_case() {
  local expected=$1 identities=$2; shift 2
  : >"$TMP/trace"
  TRACE_DIR="$TMP" EXPECTED_LOCK="$TMP/a/tmp/harness-locks/live-game.lock" \
    KP_FAST_JOBS=8 bash "$DIR/run_all.sh" "$@" >/dev/null
  [[ "$(wc -l <"$TMP/trace")" -eq "$expected" ]]
  diff -u <(printf '%s\n' "$identities" | sort) <(sort "$TMP/trace")
}
fast=$'fast:test_arbitration.sh\nfast:test_quarantine.sh'
live=$'live:test_alignment_drift.sh\nlive:test_battle_meditation.sh\nlive:test_enclave_arrival.sh'
wip=$'live:test_ahto_city_law.sh\nlive:test_party_wounded.sh\nlive:test_sith_patrol_alarm.sh'
run_case 2 "$fast"
run_case 5 "$fast"$'\n'"$live" --live
run_case 8 "$fast"$'\n'"$live"$'\n'"$wip" --live-all

set +e
TRACE_DIR="$TMP" KP_FAST_JOBS=0 bash "$DIR/run_all.sh" >/dev/null 2>&1; jobs_status=$?
TRACE_DIR="$TMP" bash "$DIR/run_all.sh" --bogus >/dev/null 2>&1; mode_status=$?
set -e
[[ "$jobs_status" -eq 2 ]] || { echo "invalid jobs status: $jobs_status" >&2; exit 1; }
[[ "$mode_status" -eq 2 ]] || { echo "invalid mode status: $mode_status" >&2; exit 1; }
echo "gameplay scheduler regression: PASS"
