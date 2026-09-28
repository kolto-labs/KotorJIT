# Pioneer Stage 0 + Stage 5 independent review

Date: 2026-09-27. Reviewer: independent (ce-code-review lens, correctness and adversarial).
Worktree: /run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation
Source was not modified. Probes are in /home/brunner56/kp-live-20260922/review-probes-pioneer/.
No Wine, game, Gamescope or FFmpeg was used. The live-game lock was not touched.

Line numbers refer to the current files. `playback.py` is untracked, so the spec's references
(for example playback.py:226) point at an earlier draft, not at these lines.

Route filesystem: `findmnt -T <worktree>` gives `ext4 rw,noatime`. Mode-0600 sidecars work on
real routes. This is not an issue.

## Suites rerun

| Suite | Container (Py 3.12.3) | Host (Py 3.14.7, host-cmd) |
|---|---|---|
| kpharness_playback_test.py | Ran 17, OK (128.4s) | Ran 17, OK (117.4s), 28 `ResourceWarning: subprocess N is still running` lines |
| kpharness_pioneer_policy_test.py | Ran 21, OK | Ran 21, OK |
| kpharness_offline_test.py | Ran 150, OK | Ran 150, OK |

Logs: review-probes-pioneer/{offline-container,host-playback,host-pioneer_policy,host-offline}.log.
Host load average was about 228 during the runs.

## Stage 0 defects

| # | Defect | Verdict | Referent |
|---|---|---|---|
| 1 | A cancelled wait/expect sets world_uncertain | holds (fixed) | playback.py:138-140, :340-345. test :261 and :491. Probe I: world_uncertain from a real failure survives stop. |
| 2 | Validation errors mark uncertain | holds (fixed) | command() validates synchronously at :237-253. `mutation_started` is set at :322 and read at :424-429. test :327. Probe J: an immediate stop after play leaves boundary 0 and state execution_stopped. |
| 3 | effective_speed is published before readback | holds (fixed) | :317 clears it. :325-330 reads back, compares, then publishes. test :454 checks the engine log order. |
| 4 | pioneer step/commit open a Channel without engine_guard | holds for Pioneer | cli.py:227, :255, :290. test :429. Non-Pioneer `exec`/`reply`/`state`/`events` still bypass it; see M5. |
| 5 | Lifetime route_lock; step/commit go through the owner | holds | pioneer.py:253, :300 (`*_locked`). playback.py:366-414, :572. cli.py:219, :249, :267. tests :376 and :439. |
| 6 | Engine lock under /tmp | holds (fixed) | playback.py:71-93 uses a private XDG/`~/.local/state` directory with symlink and 0700/uid checks. test :364. |

## Stage 5 requirements

| Requirement | Verdict | Referent |
|---|---|---|
| Speed in (0,16], finite, not bool/str | holds | playback.py:114-117. test :327, :502. The CLI's `--speed nan/inf` becomes a float and is rejected at :115. |
| Readback before effective_speed | holds | :325-330 |
| Label "configured multiplier" | holds | :39, :173, :318 |
| Explicit speed step keeps its setting | holds | :351-352. test :483. |
| Restore on finish | holds | test :454 |
| Restore on stop (control op) | holds | test :491. Probe E: SIGINT also restores. |
| Restore on failure | **does not hold** | Probes A and C (I1, I3) |
| Restore on every exit path, including SIGTERM and SIGKILL | **does not hold** | Probes D and F (I4) |
| stop never claims pause | holds | `world_paused=False` at :173. :445. cli.py stop note. Docs. |
| Journal fallback in status | holds, with a caveat | :544-556. It falls back only when the descriptor is gone. With a stale descriptor, status raises and the CLI shows `unknown`. That is honest, but there is no recovery path (I4). |

## Findings

### Critical

None.

### Important

**I1. Speed is not restored when readback differs from an acknowledged request.**
Scenario: the engine acks `speed 8` but applies 3 (clamp). The job ends uncertain. The engine is
left at 3.0, not at the prior 2.0.
Cause: in scenario.py `attached_execution`, the finally block restores only when
`current == requested` (the compare-and-restore at about :559-566). The "another owner changed it"
rationale does not apply here, because this owner holds the engine lock.
Referent, Probe A (container and host):
`prior=2.0 op=uncertain observed=3.0 speed_after_job=3.0 engine_scale_now=3.0`.
Test gap: `test_acknowledged_but_not_applied_speed_is_not_published` (test:470-481) never
asserts `engine.scale()`.
Claims that do not hold:
- docs/pioneer-authoring.md: "The previous multiplier is restored when a job finishes, fails or is stopped."
- Writer report: "Stage 5 restore on finish/stop/failure".

Fix: under the owner, restore the previous speed unless a route `speed` step ran.

**I2. Editing the route while attached makes `stop` impossible.**
`control()` requires the descriptor's route_sha256 to equal the current file bytes
(playback.py:497). Any edit to the route (an editor save, a git checkout) makes `stop`/`status`
fail with "stale or invalid playback descriptor". The owner keeps both locks. The only way out
is `kill`, which then triggers I4.
Referent, Probe B:
`stop refused: PlaybackError: stale or invalid playback descriptor; owner_alive=True`. A second
route then gets `another playback owner ... holds engine`.
Fix: do not gate `stop`/`status` on the route hash. Owner-side validation already refuses new
jobs when the route has changed.

**I3. Speed is not restored when owner validation fails at job end.**
In the finally block of `attached_execution`, `validate_owner()` runs before the restore
(scenario.py about :556-558). If the route changed, or a pending receipt appeared, it raises and
the restore is skipped.
Referent, Probe C (route edit during a fastforward wait, then a raw stop):
`engine_scale_now=12.0 (prior 2.0) speed_after_job=12.0 last_error='PlaybackError: route changed while attached'`.
Fix: gate the restore only on runtime identity (`_same_session`), not on route bytes or pending
state.

**I4. SIGTERM or SIGKILL of the owner leaves 12x speed and a stale descriptor, with no recovery path.**
There is no signal handler (no `signal` import in playback.py). The journal does not record the
speed from before the job. A stale descriptor then makes `status`, `attach`/`play`, `step` and
`commit` for that route fail with ConnectionRefused. cli.py routes those to the owner whenever
`PB.attached(out)` is true. Recovery is not documented. The only way out is to delete
`R.toml.playback.json` by hand.
Referents:
- Probe D (SIGTERM): `engine_scale_now=12.0 (prior 2.0) descriptor_left=True journal_op=running reattach='ConnectionRefusedError'`
- Probe F (SIGKILL): the same, with `status='ConnectionResetError'`.
- Probe E (SIGINT) restores correctly: `engine_scale_now=2.0 descriptor_left=False`.

`start_new_session=True` (:531) keeps terminal Ctrl-C away from the owner. The realistic paths
are `kill`, logout and system shutdown.
Fix:
- Handle SIGTERM the same way as stop.
- Journal `speed_before_job` before the first speed write.
- Add an explicit reclaim. It is safe when both the engine lock and the route lock can be
  acquired, which proves the owner is dead without relying on its PID. On reclaim, report or
  restore the journaled prior speed.

**I5. A cleanup-path exception kills the worker but leaves the owner process alive, holding locks, and reporting `detached`.**
In the worker's finally block (playback.py:442-451), `publish()` and `private_read(descriptor)`
can raise PlaybackError. The code catches only OSError and ValueError, so `self.shutdown()` is
never reached. `run_job`'s own `publish` calls (:425-431) can also raise out of the loop.
The serve loop then keeps answering. Status says `execution_stopped`/`detached` while the
process still holds the engine lock and the route lock. `stop` returns `stop_pending` and nothing
happens.
Referents:
- Probe G (journal chmod 0644): `status_op=execution_stopped stop_reply_op=stop_pending owner_alive_3s_after_stop=True descriptor=True`
- Probe K (descriptor chmod 0644): the client `stop` gives `sidecar must be owned by this user with mode600`. After a raw stop, `owner_alive=True descriptor_left=True`.

The triggers are permission tampering or ENOSPC. The impact is that the reported state is false
and the process can only be killed, which then triggers I4.
Fix: wrap each cleanup step separately and always call `shutdown()`. If the journal cannot be
written, exit non-zero rather than serve on.

### Minor

- **M1. A policy test writes an engine lock into the real user state directory.**
  `~/.local/state/kpharness/playback-locks/localhost-12345.lock` exists, mode 0600, 0 bytes,
  mtime 11:02. That is before this review's runs. The source is
  kpharness_pioneer_policy_test.py:56 (`port=12345`) and :205-219: the CLI step/commit path now
  calls `PB.engine_guard` and the test does not set `XDG_STATE_HOME`.
  Impact:
  - The test is not hermetic.
  - It fails on a read-only HOME.
  - It contends with a real engine on port 12345.

  It does not affect correctness. Fix: set `XDG_STATE_HOME` to the temp dir in `setUp`, as
  kpharness_playback_test.py:178 does.
- **M2. `start()` never waits on its `Popen`.** See playback.py:529-541. The host run shows 28
  ResourceWarning lines. The CLI is short-lived and the owner is reparented, so no lasting zombie
  was observed. In a long-lived caller (the test runner), exited owners stay zombies until that
  caller exits. pgrep after all runs found no leftover owners or engines.
- **M3. The control server can be blocked by one idle connection.** The server is
  single-threaded. The per-connection read timeout (2s, :456) equals the client timeout (2s,
  :501). One idle connection from any local user makes `status`/`stop` time out.
  Probe H: `status_with_one_hog=TimeoutError after 2.00s`. Unauthenticated, wrong-token and
  truncated-token requests are all rejected (`control authentication failed`). The token is
  compared with `hmac.compare_digest`, stored at 0600, and sent over loopback only. That part
  holds.
- **M4. The 10s startup deadline flakes under load.** See :534-541. Container Probe E (reattach)
  and host Probes A/B/H hit `owner startup outcome uncertain` at load average about 228. They
  were clean on rerun. The behavior is honest, since it does not retry.
- **M5. Non-Pioneer commands bypass the engine lock.** `kpharness exec`, `reply`, `state`,
  `events` and `status` use `_channel()` (cli.py:69-75), which does not take `engine_guard`. The
  docs say "The owner opens the only engine connection". Only Pioneer paths enforce that. This is
  scope creep, so flag it rather than block on it.
- **M6. A cancelled wait is classed as read-only, but waits can mutate.** `_on_poll` can answer
  authored barks (`reply`) and fire the shooter (scenario.py:495-500). A cancel after such an
  action is still reported as clean (playback.py:138-140).
- **M7. The reference counts as a mutation even when nothing was written.** `mutation_started`
  is set before `attached_execution`'s own `validate_owner` and pre-read (:322). A precondition
  failure there is reported as uncertain although nothing was written. This errs on the safe side.
- **M8. `XDG_STATE_HOME` has a TOCTOU window if it points at a directory another user can
  write.** There is a gap between the stat at :90-92 and the open at :102. Swapping the directory
  in that gap could split or deny the lock. This is unlikely with the default `~/.local/state`.

### Null moves (checked, hold)

- **Two concurrent attaches on the same route.** Probe L:
  `[('ok','4e2cf0c8'), ('ok','4e2cf0c8')]; live_owner_procs=1 engine_connections=1`.
- **A second owner on another route is refused.** test :318, and Probe B.
- **Symlinked lock dir, lock file or sidecar is refused.** :55-56, :85-87, :100-102 (O_NOFOLLOW),
  and pioneer `_atomic_write`.
- **A stale descriptor is never replaced and no new owner is spawned.** test :294.
- **stop after an uncertain result.** Probe I: final `execution_stopped`, with
  `world_uncertain=True` kept. The next attach requires a restart (:285-287).
- **stop immediately after play.** Probe J: the speed is set and then restored, and no step
  runs.
- **Replay.** The token is per owner and dies with the owner. A port squatter after owner death
  gets a dead token and cannot forge `owner_id` (:509-511).

## Claims from the writer report

| Claim | Referent | Verdict |
|---|---|---|
| Suites green in both environments | Reruns above | holds |
| "Stage 5 restore on finish/stop/failure" | Probes A and C | does not hold for readback-mismatch and validation failures |
| ":470 covers an engine that acks 8 but reads back 3" | test:470-481 | holds for publishing. It does not check restore. |
| Stale descriptor handling | :294 | holds for rejection. Recovery is missing (I4). |
| "no leftover processes" | pgrep in the container and on the host after this review | holds |

Pioneer Stage 0+5 verdict: FAIL
