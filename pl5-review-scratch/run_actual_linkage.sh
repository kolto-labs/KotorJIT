#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0
SCR=/home/brunner56/kp-live-20260922/pl5-review-scratch
WS=/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation
SRC=/home/brunner56/kp-live-20260922/pl5-scratch/src
CXX=clang++

$CXX -m32 -std=c++20 -O0 -ffunction-sections -fdata-sections \
  -I"$SRC" -I"$WS/src" -I/home/brunner56/kp-live-20260922/pl5-scratch -I"$WS" \
  -c "$SCR/actual_finish_fixture.cpp" -o "$SCR/actual_finish_fixture.o"
$CXX -m32 -std=c++20 -O0 -ffunction-sections -fdata-sections \
  -I"$SRC" -I"$WS/src" \
  -c "$SCR/actual_stubs.cpp" -o "$SCR/actual_stubs.o"
$CXX -m32 -std=c++20 -O0 -ffunction-sections -fdata-sections \
  -I"$SRC" -I"$WS/src" \
  -c "$SRC/harness/pause_lease.cpp" -o "$SCR/pause_lease.o"
$CXX -m32 -Wl,--gc-sections \
  "$SCR/actual_finish_fixture.o" "$SCR/actual_stubs.o" "$SCR/pause_lease.o" \
  -o "$SCR/actual_finish_fixture"
timeout 10s "$SCR/actual_finish_fixture"

$CXX -m32 -std=c++20 -O0 -ffunction-sections -fdata-sections \
  -I"$SRC" -I"$WS/src" -I/home/brunner56/kp-live-20260922/pl5-scratch -I"$WS" \
  -c "$SCR/actual_finish_fixture_expectation_mutant.cpp" \
  -o "$SCR/actual_finish_fixture_expectation_mutant.o"
$CXX -m32 -Wl,--gc-sections \
  "$SCR/actual_finish_fixture_expectation_mutant.o" "$SCR/actual_stubs.o" "$SCR/pause_lease.o" \
  -o "$SCR/actual_finish_fixture_expectation_mutant"
set +e
timeout 10s "$SCR/actual_finish_fixture_expectation_mutant" > "$SCR/actual-mutant-run.log" 2>&1
rc=$?
set -e
cat "$SCR/actual-mutant-run.log"
if [ "$rc" -ne 134 ] || ! grep -Fq 'adapter.pause_machine_.loading()' "$SCR/actual-mutant-run.log"; then
  echo "ERROR: production cleanup mutant did not produce required rc=134/loading assertion (rc=$rc)" >&2
  exit 1
fi
echo "production finish_load cleanup mutant: red as expected"

sha256sum "$SRC/harness/engine_k1.cpp" "$SRC/harness/fields.hpp" \
  "$SRC/harness/pause_lease.hpp" "$SRC/harness/pause_lease.cpp" \
  "$SRC/../armed_timeout.hpp" "$WS/src/harness/chargen.hpp" \
  "$WS/src/runtime/internal.hpp" "$WS/src/runtime/runtime.hpp" \
  "$WS/src/platform/platform.hpp" "$WS/src/lua/host.hpp" "$WS/src/hooks/registry.hpp" \
  "$SCR/actual_finish_fixture.cpp" "$SCR/actual_finish_fixture_expectation_mutant.cpp" \
  "$SCR/mutant-engine.cpp" "$SCR/actual_stubs.cpp" "$SCR/run_actual_linkage.sh" \
  "$SCR/actual_finish_fixture" "$SCR/actual_finish_fixture_expectation_mutant" \
  > "$SCR/actual-linkage-manifest.sha256"
