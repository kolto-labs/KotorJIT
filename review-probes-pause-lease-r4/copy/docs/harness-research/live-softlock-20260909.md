# K1 softlock run, 2026-09-09

Command: `./scripts/harness/kpharness.sh run k1_softlock_detect --boot-timeout 180`.
Evidence: `tmp/k1_harness/runs/20260909-191940/` (report.json,
session.log, copied runtime log, and screenshots).

The complete scenario **failed**. The expected detection step passed;
the recovery step did not.

- Boot connected on attempt 2 with `k1_steam_103_unpacked`, 18 hooks,
  and `live=true`. Current driver code permits 3 attempts, not 2.
- Load reached `phase=gameplay`, `module=end_m01aa`. The AreaLoaded
  completion step ran. Screenshot `0002_periodic.png` was opened and
  visually confirmed the Endar Spire interior and HUD.
- The lock-and-move Lua command returned `end_door01` (with a trailing
  NUL). The player's position changed toward the door.
- Step 4 reported the expected softlock after 60 seconds with no
  fingerprint change (70.1 seconds total wait).
- Unlock/open/interact returned `GetLocked == 0`. Step 7 still reported
  softlock after 60 seconds. Final state was gameplay in `end_m01aa`,
  no dialog, no pending module move, and an advancing client loop.
- Teardown completed; the run's game and Xvfb processes were gone.

This proves live stagnation detection, not a causal door-lock/recovery
test. The scenario assumed the nearest door led to `end_m01ab` without
establishing that relationship. Unlocking alone did not prove the queued
open/interact actions completed. The scenario has since been corrected to
recover with an explicit harness warp; door transition behavior belongs in
a separate scenario with a verified module link and observable action
completion. No recovery screenshot was captured; the report references the
earlier softlocked frame.

Offline verification: build with `-j3` was current; CTest passed 10/10;
`kp_harnesstest` reported zero failures. The Python suite initially failed
because the exhausted-retry test supplied only two outcomes for a
three-attempt policy. Updated coverage checks final-attempt success and
final-failure propagation/cleanup. All 54 Python tests then passed.

Only one live scenario was run in this continuation. K2 gameplay and
`unpause_timers` remain untested live. Nothing was committed.
