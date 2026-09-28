# Pioneer playback: round 2 independent review

Date: 2026-09-27. Reviewer scope: correctness plus adversarial review of the Round-2 Pioneer playback changes. Source was read-only. This is the sole review artifact; probe copies/logs are under `/home/brunner56/kp-live-20260922/review-probes-pioneer-r2/`.

The writer report was read only after the independent source review. It has no `Grill me` section, so there was no writer-supplied weak claim to attack first. No Wine, game, Gamescope, Xvfb/Xwayland, mpv, or capture tool was run; the live-game lock was not read or touched. No process was signalled by this review.

## Resume receipt

There was no pre-existing `pioneer-round2-review.md`. The worktree was already intentionally dirty; `git status --short` showed the stated playback/CLI/test/documentation changes among many unrelated changes. The only pre-existing Round-2 artifact was `.superpowers/sdd/lua-boundary-validation-plan/pioneer-round2-report.md` (14,265 bytes). Round-1 report and probe were read.

I copied the Round-1 probe to `review-probes-pioneer-r2/probe_playback_round1_fixed.py`. Its Probe B now registers `detach(other)` for the successful other-route owner, in addition to the original owner cleanup. That fixes the known probe leak without changing production source.

## Direct checks

| Check | Result | Referent |
|---|---|---|
| I1/I3 speed restore policy | holds | `playback.py:294-337` journals prior speed and restores it without route/pending validation; `:440-450` uses it around execution. |
| I2 route edit does not block status/stop | holds | `playback.py:656-661` excludes `status`/`stop` from route digest validation. |
| I4 graceful signal/reclaim design | partially holds | `:627-636` turns TERM/HUP/INT into queued stop; `:726-787` takes engine then route locks non-blocking and checks recorded runtime before speed restore. SIGKILL necessarily requires reclaim. |
| I5 cleanup always requests server shutdown | holds in source | `:565-580`, including individually caught cleanup failures and unconditional `self.shutdown()`. |
| M5 general CLI engine exclusion | holds for listed commands | `cli.py:74-88` takes `PB.engine_guard`; `playback.py:619-620` owner holds it before opening the engine channel. |
| Owner-less `pioneer step` old compare-and-restore | residual, not new regression | `pioneer.py:478-486` still delegates to `runner.attached_execution`; CLI now wraps this path with `engine_guard` at `cli.py:241-245`. It has no owner journal/reclaim path, as the writer report acknowledges. |

The copied Round-1 probe was invoked in the container and through the mandated host command. Neither bounded invocation completed with a usable test receipt before the tooling return boundary on this heavily loaded host. The two log files are retained: container is 8 bytes and host 420 bytes. They are **not** counted as passes. I also did not claim the writer's prior suite results as a fresh rerun. Their report supplies prior claims of playback 32, policy 21, offline 150 and creative 33 tests passing in each environment, but those are writer evidence rather than this review's completed execution evidence.

## Findings

### Critical

None.

### Important

**I6 — unauthenticated idle connections can exhaust owner threads before token verification.**

Failure scenario: any local process that can connect to loopback discovers or scans the ephemeral control port and opens many TCP connections without sending a newline. `ThreadingMixIn` creates one unbounded daemon thread for each accepted socket. Only then does `Handler.handle()` apply the one-second read timeout, and only after reading a full line does it verify the secret token. At sufficient connection rate, threads/file descriptors/memory are exhausted; the legitimate owner cannot reliably receive `status` or `stop`, and it keeps the game and both locks attached. The one-idle-client test proves only that a single connection no longer serially blocks service; it does not bound this resource attack.

Referent: `scripts/harness/kpharness/playback.py:595-612` (thread work begins before authentication); `:615-618` (`ThreadingMixIn`, `daemon_threads=True`, no concurrency limit); `:47-50` (one-second timeout). The existing test named `test_probe_h_idle_connection_does_not_block_status` is consequently a single-client availability test, not a thread-exhaustion test.

Classification: **Important**. This is a local availability failure of the only safe stop/control path, not remote code execution. It directly matches the requested adversarial surface and leaves no bound on attacker-created handler threads. Fix with a bounded admission semaphore acquired before `process_request_thread` (close/reject excess sockets), plus a regression test that holds more idle sockets than the configured bound and confirms bounded thread count plus successful authenticated stop/status.

### Minor

None beyond the acknowledged owner-less authoring compare-and-restore residual. It is a null move for this round: it is outside the attached playback owner and now takes the engine guard. It should remain a separately designed recovery policy if authoring speed changes must survive abrupt process death.

## Requested attack outcomes

| Attack | Verdict | Evidence |
|---|---|---|
| Reclaim while owner alive but slow | holds | `reclaim()` acquires engine then route locks non-blocking at `playback.py:726-742`; an owner holds both for `serve()` lifetime at `:621-622`. |
| Lock-take race | holds | same lock order in owner and reclaim avoids inversion; lock acquisition is the gate before descriptor deletion at `:747-752`. |
| Wrong game process | holds | `_reclaim_locked()` only writes speed after `_same_session(recorded, session_proof(...))` at `:767-780`. |
| Descriptor from another user | holds | `private_read()` rejects foreign uid or group/other permissions at `:71-79`; control reads descriptor through it at `:648-649`. |
| Launcher orphan/zombie | holds by source and writer test referent | caller reaps launcher with `communicate()` at `:690-704`; launcher creates owner at `:711-713`; writer reports `test_owner_is_not_a_child_of_the_caller`. This review did not complete a fresh process probe. |
| Token check before any work | does not hold for connection/thread work | see I6. Token comparison itself is constant-time and occurs before `owner.command()` at `:603-608`. |
| Existing scripts depend on concurrent M5-bypassing commands | no contrary source path found in writer's cited grep; independently unverified due incomplete bounded grep | writer report says scripts use `run`; docs examples are manual. This is not used to close I6. |

## Grill questions

1. Why does one idle socket passing prove capacity? It does not: `ThreadingMixIn` has no maximum in `playback.py:615-618`. **Referent: I6.**
2. How does reclaim avoid touching a replacement game? `_same_session` compares the journaled identity and monotonic uptime before `speed` at `:767-780`. **That holds.**
3. Is graceful SIGTERM equivalent to a control stop? Both call `request_stop`; the signal handler queues `None` rather than shutting down server directly. **Referent: :627-636, :340-345.**
4. Why was Round-1 Probe B safe on rerun? The local copied probe adds `self.addCleanup(self.detach, other)` after a successful second attach. **Referent: review-probes-pioneer-r2/probe_playback_round1_fixed.py:75-86.**

Unsettled question: whether the current host can execute the full required container and host suite matrix without load-induced startup failure. The one check that settles it is serialized completion of the four named suites in each environment, retaining their logs. This review attempted the copied probe only; it did not manufacture passing counts.

Pioneer round 2 verdict: FAIL
