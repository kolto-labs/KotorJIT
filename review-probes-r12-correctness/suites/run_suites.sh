#!/bin/sh
cd /run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation
for s in creative gamescope_boot_repair gamescope_backend capture_diagnostic; do
  PYTHONPATH=scripts/harness:tools timeout 3000 python3 tools/kpharness_${s}_test.py > /home/brunner56/kp-live-20260922/review-probes-r12-correctness/suites/$1-$s.txt 2>&1; echo "$s rc=$?" >> /home/brunner56/kp-live-20260922/review-probes-r12-correctness/suites/$1-rc.txt
done
