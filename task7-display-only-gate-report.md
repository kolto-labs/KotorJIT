# Task 7 display-only acceptance gate

**FAIL. One launch was attempted; no launch retry occurred.** On 2026-09-27 at 09:30 UTC, the reviewed lease failed Xwayland ancestry admission with `RuntimeError: process is outside the owned process group/ancestry`. Geometry, accelerated-renderer, and local-socket peer/handshake acceptance were not reached. This result does not permit a game retry or establish Task 7 live acceptance.

## Retained run and snapshot

- Run: `/home/brunner56/kp-live-20260922/display-only-runs/20260927-092903-52fe911a`
- Immutable-by-convention, filesystem-read-only snapshot: `/home/brunner56/kp-live-20260922/harness-snapshots/task7-display-only-20260927-092903-52fe911a`
- Snapshot manifest SHA-256: `a6ee7d28c4d282e20095d91409f1e04f68f33300ee406a7fcd1574fc0f9770a4`
- Source: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/scripts/harness`
- Private driver: `display_gate.py` inside the run; its launch digest and exact invocation are in `invocation.json`. Run artifact digests are in `artifact-hashes.json`.

The 26-module snapshot was created with the current production snapshot helper, verified against the current source closure before execution, and sealed with file modes 0444 and directory modes 0555. It is not claimed to be protected against its owner deliberately changing permissions. The manifest and every retained snapshot file had identical hashes after execution, and the production verifier again confirmed source equality and repository-input hashes. `snapshot-before.json` and `snapshot-after.json` preserve that evidence.

The private driver and actual readiness child both used absolute `/usr/bin/python3.14 -I -S -B`. The child driver inserted only the snapshot's `runtime` into its isolated standard-library import path. It imported `GamescopeXwaylandLease` from the snapshot and invoked it once at 1024×768. No creative game driver, Wine, game, FFmpeg, or visual-acceptance command was invoked. Product source was not edited.

## Preconditions and bounded execution

Read the implementer report at `.superpowers/sdd/lua-boundary-validation-plan/task-7-boot-repair-report.md`, the independent `task7-boot-repair-review.md` including its final PASS rereview, `task7-provenance-resume-review.md`, the snapshot implementation/documentation, and `task7-authority-mechanism-audit.md` before the launch.

The supervisor acquired and held the canonical repository lock `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/tmp/harness-locks/live-game.lock` with nonblocking exclusive flock throughout snapshot creation, the one lease execution, and the initial postchecks. Preflight recorded 23,736,446,976 bytes free against a 1 GiB minimum. No Gamescope, gamescopereaper, game, Wine, wineserver, or FFmpeg process was present. The existing host Xwayland PID 7277 served `:0` and was left untouched. Its authority path was redacted from retained pre/post process evidence.

The one `start()` call launched Gamescope PID 816616, start identity `59550695`, PGID/SID 816616. The retained rejected readiness child PID 816785, start `59550878`, published `DISPLAY=:1`. Its ancestry through intermediary PID 816778 to Gamescope was verified and retained as cleanup authority. It was never admitted as a ready display child.

The traceback identifies the failed predicate exactly:

1. `gamescope_xwayland.py:285` called `verify_private_xwayland`.
2. `gamescope_processes.py:104` called `verify_ancestry` for the Xwayland candidate.
3. `gamescope_processes.py:31` rejected a process relation whose group or session differed from the lease's recorded PGID/SID.

This is fresh runtime failure evidence, not an inferred replay of the older failure. The failing candidate's full live Xwayland relation was not retained before internal teardown, so this report does not identify which candidate/link differed or invent its actual PGID/SID. The readiness-child chain did pass. The log reports starting Xwayland on `:1`, and later a restart/X11 I/O abort during cleanup; the log alone does not establish the missing process relation or a successful renderer probe. No `renderer.txt` or successful geometry evidence was produced.

## Cleanup and postconditions

The production `start()` failure handler invoked `close()` internally. That single cleanup attempt passed, the lease became closed, and the private driver's `finally` correctly did not invoke it again. Had internal cleanup failed, the driver was prepared to retain that failure and make one distinct finally cleanup attempt; that path was not exercised. The original boot traceback is retained separately from `cleanup_error=null`, and the lease receipt retains `boot_phase=failed`, `cleanup_phase=passed`, and one passed cleanup attempt. The Gamescope leader was reaped with return code -6.

Both the initial postcheck and the later explicit rejected-display check found all six recorded owned PIDs absent: 816616, 816722, 816778, 816785, 816853, and 816854. No Gamescope, game, Wine, wineserver, or FFmpeg process remained. Only the original host Xwayland PID 7277 on `:0` remained. The canonical live-game lock was free after release.

At 09:30:43 UTC, `postcheck-rejected-display.json` explicitly checked rejected display `:1`: no Xwayland process for it and no pathname or abstract listener in `/proc/net/unix` remained. **The filesystem entry `/tmp/.X11-unix/X1` nevertheless still existed.** It was preserved, not unlinked. Absence of a live listener does not mean the pathname artifact was removed, so fully absent display artifacts are not claimed.

The initial `gate-result.json` has two conservative/limited aggregate fields that must not be overread: `no_game_wine_ffmpeg=false` reflects missing during-success evidence after boot failure, not an observed forbidden launch; `private_display_absent=true` used the null admitted-display field and did not inspect rejected `:1`. The supplemental rejected-display receipt corrects the latter evidentiary gap and is authoritative for the remaining socket pathname. Original receipts were not rewritten to conceal these limitations.

## Acceptance predicate and decision

The requested gate requires one successful lease start, live owned display identity, observed 1024×768 geometry, direct accelerated nonsoftware renderer, complete owned local no-cookie socket/peer evidence, successful bounded cleanup, absent owned processes/private display, unchanged source-equal snapshot, and a free canonical lock. The owned endpoint mode would be `owned-endpoint-host-local-no-cookie`; it would not imply exclusive access against other local users.

Here, startup/access verification failed, geometry and renderer were not reached, and a socket pathname remains. Cleanup of recorded processes, snapshot preservation, and lock release passed. **Final predicate: FAIL at Xwayland group/session ancestry admission, with full display-artifact cleanup also unproven because X1 remains.** No game acceptance, GPU-renderer acceptance, physical-console proof, media proof, or visual acceptance is claimed. No second launch was performed.

Primary receipts: `preflight.json`, `snapshot-before.json`, `invocation.json`, `driver-result.json`, `gamescope-lease.json`, `gamescope.log`, `driver.log`, `snapshot-after.json`, `gate-result.json`, `postcheck-rejected-display.json`, and `artifact-hashes.json` in the retained run directory.
