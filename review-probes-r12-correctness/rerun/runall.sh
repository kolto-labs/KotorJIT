#!/bin/sh
cd "$(dirname "$0")"
for p in probe_r11 probe_r10 replay_r0_r7 spawn_race p11b_supervisor_spawn_window p12_child_token p13_lock_inheritance p14_content_attacks p11a_popen_signal_window p11c_signals_per_phase p10_preflight; do
  timeout 900 python3 $p.py > $p.out 2>&1; echo "$p rc=$?" >> rc.txt
done
