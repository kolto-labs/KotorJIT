# Task 7: failed Gamescope boot diagnosis

Run: `/home/brunner56/kp-live-20260922/private-gpu-runs/20260927-081255-56942ef0`.
Inspected implementation: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/scripts/harness/kpharness/`.
Read-only diagnosis; no game, display, Wine, or test processes launched, no signals sent, no product files changed. This report is the only authored artifact.

## Finding and confidence

The strongest supported original-boot diagnosis is **the readiness payload lacked XAUTHORITY and was rejected as `Gamescope child published invalid X11 authority`**. This is a deterministic consequence of the retained payload and inspected validator, but it is **not a recovered historical traceback**. The failed run persisted only cleanup errors. The adapter is not in this worktree's HEAD, and the currently inspected implementation already includes newer preliminary-receipt changes; the failed run contains no such lease receipt or executed Python snapshot. Exact historical implementation identity remains unproven.

The retained `gamescope-b12ab845ccbc4a5e9efe224f4d6cc26b.ready.json` is exactly:

```json
{"pid": 486796, "start": "59098686", "environment": {"DISPLAY": ":1"}}
```

In `gamescope_xwayland.py:217-223`, missing XAUTHORITY satisfies `not isinstance(authority.get("XAUTHORITY"), str)` and raises the quoted exception. This validation runs **before** readiness-child identity/ancestry checks, display geometry probing, renderer probing, and the game launch. Therefore gamescopereaper ancestry cannot explain rejection of this particular payload under this validator. An earlier leader-exited check could theoretically win the race before payload consumption; the logs cannot eliminate that possibility.

The compositor log shows hardware device selection, a running headless compositor, Xwayland starting on `:1`, PipeWire paused/available, and the vblank timer. The X0 bind message is followed by successful selection of X1; it is not evidence that boot failed because all displays were unavailable. The final reaper and X11-I/O messages occur after those startup messages and are compatible with harness teardown. They do not establish that an independent compositor crash preceded cleanup.

## Why cleanup can report a dead group as surviving SIGKILL

`display_backends.py:172-187` parses `/proc/PID/stat` into start time and relationships but discards the state field (`fields[0]`). A zombie retains its PID, start time, process group, and session until its parent reaps it. In `gamescope_xwayland.py:317-350`, `owned_group_alive()` returns an identity whenever those values match, regardless of zombie state.

After SIGTERM, `_close()` repeatedly calls that relationship reader for five seconds, then sends SIGKILL and repeats for another five seconds. It does **not** call `Popen.poll()` or `Popen.wait()` during either loop when an identity is present. The reaping call appears only after `if owned_group_alive() is not None: raise RuntimeError("owned Gamescope process group survived SIGKILL")`. Thus a normally terminated but unreaped direct Gamescope child can deterministically block its own reaping and produce this error. SIGKILL cannot remove an already dead zombie. The message proves only that the identity predicate remained true, not that executable compositor work survived SIGKILL.

This is a code-proven failure mechanism, not proof that the historical leader was a zombie at that moment: the run saved neither its PID/stat nor a process-tree snapshot. A current read-only `ps` lookup found no Gamescope or PID 486796 process and cannot reconstruct the earlier state.

`ready_child` is assigned only after authority and ancestry verification. If missing authority was the original rejection, cleanup tracked only the leader identity, although a readiness child had already published its PID. This makes leader reaping and retained preliminary child evidence particularly important.

## How the original error disappears

The session `boot()` handler in `creative_wine.py:236-238` calls `teardown(graceful=False)` before its bare `raise`. If teardown raises, execution never reaches that bare raise; the cleanup exception becomes the exception delivered to `creative.py`, whose route failure receipt serializes only its type and string. `creative.py` then runs teardown again in its finalization path. The actual receipt shows order `recorder, game_wine, display, display`, and the final cleanup string contains the same display failure twice. Failed display cleanup never marks `_lease_closed`, and `_cleanup_errors` retains the first error, so retrying repeats both the display action and the stored error. The persisted route error is consequently a secondary cleanup failure.

Current lease `start()` catches cleanup exceptions and reraises the startup exception, but the enclosing session handler still masks it as above. Also, `_write_evidence(error=...)` currently uses one mutable failure slot, so cleanup can overwrite the final top-level failure; the event history is required to retrieve the original. Separate boot and cleanup error fields are clearer.

## Gamescopereaper ancestry limit

The log establishes that gamescopereaper participated and reported its parent killed. It does not record its PID, PPID, PGID, SID, or start time, nor the readiness child's ancestry. The current validator walks through intermediate parents, so a reaper intermediary is allowed **if** the chain reaches Gamescope and the readiness child shares the recorded PGID/SID. A reaper-created session or process group could fail the later check, but the historical topology is absent. Do not report an observed ancestry mismatch or change ownership policy based only on this log.

## Concrete regression recommendation

Add a single bounded host-only fixture that reproduces this exact sequence, with fake time and injected process/relationship readers; no Gamescope or game launch is needed:

1. Have fake Popen publish the exact retained readiness JSON, with only DISPLAY and the recorded child fields. Assert authority validation raises the expected original exception and the X11/renderer runners and game-launch path are never invoked.
2. On fake SIGTERM, change the leader's synthetic `/proc` state from S to Z while preserving PPID/PGID/SID/start. Keep the entry until fake `poll()`/`wait()` reaps it. Assert cleanup reaps the owned leader, never calls SIGKILL solely because a zombie entry exists, terminates promptly, and reports no runnable survivor. Include a truly live matching descendant as a countercase so zombie handling cannot silently discard a live child.
3. Force cleanup to fail with a separate sentinel error. Assert the session/creative receipt preserves both the original authority rejection and cleanup failure distinctly; repeat teardown and assert no duplicate error/order entry from already completed phases.
4. Add small topology fixtures for leader -> reaper -> ready child with a shared group/session (accepted), changed group/session (rejected), and reused ancestor identity (rejected or explicitly diagnosed). These fixtures establish behavior without asserting which topology existed in this run.

The existing success fixture (`tools/kpharness_gamescope_backend_test.py`, `test_lease_start_receipt_and_owned_group_cleanup`) clears all relationships immediately on killpg. That avoids the real zombie interval and therefore cannot catch the reaping-order defect. Its authority fixture always injects `/private/auth`, so it also misses this actual DISPLAY-only payload.

Before another live run, resolve the authority contract explicitly: either construct and verify a private authority mechanism for the owned Xwayland, or support its observed DISPLAY-only environment with equivalent independently proven isolation. Blindly relaxing XAUTHORITY validation would erase an ownership boundary without establishing the replacement. The report does not prescribe or authorize that product-policy change.
