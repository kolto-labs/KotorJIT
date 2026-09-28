#!/usr/bin/env bash
# Usage: probe_f_loop.sh <worktree> <logdir> <iterations> <burners>
# Runs Round2SignalTests.test_probe_f_* N times with <burners> CPU busy loops
# it owns; keeps every per-run log; kills only the burners it started.
set -u
W=$1; D=$2; N=$3; B=$4
mkdir -p "$D"
pids=()
for _ in $(seq "$B"); do ( while :; do :; done ) & pids+=($!); done
trap 'kill "${pids[@]}" 2>/dev/null; wait 2>/dev/null' EXIT
ok=0; bad=0
for i in $(seq "$N"); do
  log="$D/run-$(printf %03d "$i").log"
  { date +%T.%N; cat /proc/loadavg; } > "$log"
  (cd "$W" && PYTHONPATH=scripts/harness timeout 300 python3 tools/kpharness_playback_test.py \
     Round2SignalTests.test_probe_f_sigkill_then_reclaim_restores_recorded_speed) >> "$log" 2>&1
  rc=$?
  if [ $rc -eq 0 ]; then ok=$((ok+1)); else bad=$((bad+1)); echo "FAIL run $i rc=$rc -> $log"; fi
  left=$(ps -eo pid,args | grep "[k]pharness.playback --serve" | wc -l)
  echo "run $i rc=$rc owners_left=$left load=$(cut -d' ' -f1 /proc/loadavg)"
done
echo "SUMMARY ok=$ok bad=$bad of $N burners=$B $(python3 --version)"
