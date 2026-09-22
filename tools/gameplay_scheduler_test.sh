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
  local expected=$1; shift
  : >"$TMP/trace"
  TRACE_DIR="$TMP" KP_FAST_JOBS=8 bash "$DIR/run_all.sh" "$@" >/dev/null
  [[ "$(wc -l <"$TMP/trace")" -eq "$expected" ]]
}
run_case 2
run_case 5 --live
run_case 8 --live-all

if TRACE_DIR="$TMP" KP_FAST_JOBS=0 bash "$DIR/run_all.sh" >/dev/null 2>&1; then
  echo "invalid KP_FAST_JOBS was accepted" >&2; exit 1
fi
if TRACE_DIR="$TMP" bash "$DIR/run_all.sh" --bogus >/dev/null 2>&1; then
  echo "invalid mode was accepted" >&2; exit 1
fi
echo "gameplay scheduler regression: PASS"
