#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0
SCR=/home/brunner56/kp-live-20260922/pl5-review-scratch
WS=/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation
SRC=/home/brunner56/kp-live-20260922/pl5-scratch/src
CXX=clang++

$CXX -m32 -std=c++20 -O0 -ffunction-sections -fdata-sections \
  -I"$SRC" -I"$WS/src" \
  -c "$SCR/actual_stubs.cpp" -o "$SCR/actual_stubs.o"
$CXX -m32 -std=c++20 -O0 -ffunction-sections -fdata-sections \
  -I"$SRC" -I"$WS/src" \
  -c "$SRC/harness/pause_lease.cpp" -o "$SCR/pause_lease.o"
$CXX -m32 -std=c++20 -O0 -ffunction-sections -fdata-sections \
  -I"$SRC" -I"$WS/src" -I/home/brunner56/kp-live-20260922/pl5-scratch -I"$WS" \
  -c "$SCR/onfail_fixture.cpp" -o "$SCR/onfail_fixture.o"
$CXX -m32 -Wl,--gc-sections \
  "$SCR/onfail_fixture.o" "$SCR/actual_stubs.o" "$SCR/pause_lease.o" \
  -o "$SCR/onfail_fixture"
timeout 10s "$SCR/onfail_fixture"

$CXX -m32 -std=c++20 -O0 -ffunction-sections -fdata-sections \
  -I"$SRC" -I"$WS/src" -I/home/brunner56/kp-live-20260922/pl5-scratch -I"$WS" \
  -c "$SCR/onfail_mutant_fixture.cpp" -o "$SCR/onfail_mutant_fixture.o"
$CXX -m32 -Wl,--gc-sections \
  "$SCR/onfail_mutant_fixture.o" "$SCR/actual_stubs.o" "$SCR/pause_lease.o" \
  -o "$SCR/onfail_mutant_fixture"
set +e
timeout 10s "$SCR/onfail_mutant_fixture" > "$SCR/onfail-mutant-run.log" 2>&1
rc=$?
set -e
cat "$SCR/onfail-mutant-run.log"
if [ "$rc" -ne 134 ] || ! grep -Fq 'a.pause_machine_.loading()' "$SCR/onfail-mutant-run.log"; then
  echo "ERROR: production on_fail mutant did not produce required rc=134/loading assertion (rc=$rc)" >&2
  exit 1
fi
echo "production on_fail cleanup mutant: red as expected"

sha256sum "$SRC/harness/engine_k1.cpp" "$SRC/harness/fields.hpp" \
  "$SRC/harness/pause_lease.hpp" "$SRC/harness/pause_lease.cpp" \
  "$SRC/../armed_timeout.hpp" "$WS/src/harness/chargen.hpp" \
  "$WS/src/runtime/internal.hpp" "$WS/src/runtime/runtime.hpp" \
  "$WS/src/platform/platform.hpp" "$WS/src/lua/host.hpp" "$WS/src/hooks/registry.hpp" \
  "$SCR/onfail_fixture.cpp" "$SCR/onfail_mutant_fixture.cpp" \
  "$SCR/onfail-mutant-engine.cpp" "$SCR/actual_stubs.cpp" "$SCR/run_onfail_linkage.sh" \
  "$SCR/onfail_fixture" "$SCR/onfail_mutant_fixture" \
  > "$SCR/onfail-linkage-manifest.sha256"
