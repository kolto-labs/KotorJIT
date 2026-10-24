# Pioneer playback round 2: writer report

Date: 2026-09-27. Scope: fixes for `/home/brunner56/kp-live-20260922/pioneer-stage0-5-review.md`, covering I1-I5, M1, M2, M3 and M5, plus M4, M7 and M8 where cheap, with M6 documented.
No Wine, game, Gamescope or FFmpeg was used. `tmp/harness-locks/live-game.lock` was not touched.
Nothing was staged, committed, stashed or pushed.

## Files changed (only these)

- `scripts/harness/kpharness/playback.py`: owner speed guard, signals, reclaim, guarded cleanup, launcher, threaded control server, and a dir-fd engine lock.
- `scripts/harness/kpharness/cli.py`: `pioneer reclaim`. `_channel` now takes the engine lock. `stop` hints at reclaim. `status` handles a busy engine. `main` catches `PlaybackError`.
- `tools/kpharness_playback_test.py`: 15 new red-first tests, plus a 60s startup wait for the synthetic engine. The stale-descriptor test was adjusted for I2.
- `tools/kpharness_pioneer_policy_test.py`: `XDG_STATE_HOME` is set in `setUp` (M1), with an assertion that the lock lands there.
- `docs/pioneer-authoring.md`: covers the speed policy, recovery/reclaim, signals, the M6 limitation, the start timeout, the control-server timeouts and the lock on exec/state.

These files were not touched: `scenario.py`, `recording.py`, `display_backends.py`, `creative*.py`, `capture_diagnostic.py`, `session.py`, `pioneer.py` and `src/**`.
Their `M` status predates this session.
Note: `capture_diagnostic.py` (mtime 12:04) and `display_backends.py` (11:39) changed during this session. That was another writer, not me.

## Fixes

- **I1 and I3.** `Owner.speed_guard()` (playback.py) replaces `runner.attached_execution` in `execute()`.
  - Order of operations: `validate_owner`, then read the prior speed, then journal `speed_before_job` with `speed_restore_owed=true`, then set `mutation_started`, then `_configure_execution`.
  - At the end, `_finish_speed` restores the prior speed unless a route `speed` step ran. The only gate is `P._same_session`. It does not call `validate_owner`, and it ignores route bytes and pending receipts.
  - The result is confirmed by readback, not by the engine's acknowledgement.
  - A mismatch or failure sets `speed_restore_error` and marks the world uncertain.
  - The same guard wraps `author_step`, so owner-routed authoring steps also always restore.
  - `scenario.py` is unchanged.
- **I2.** `control()` no longer checks `route_sha256` for `status` or `stop`. Job operations still check it early, and the error still says "stale".
- **I4.**
  - SIGTERM, SIGHUP and SIGINT handlers call `request_stop()`. That sets cancel and queues a stop. It never calls `server.shutdown` from the handler.
  - `stop_reason` records the signal.
  - The journal also records `runtime_uptime_ms` so that reclaim can apply `_same_session`.
  - New `PB.reclaim(out, info)` and `kpharness pioneer reclaim --out R`. Reclaim takes the engine lock and then the route lock, both non-blocking. If either is held, it refuses and says to use `stop`.
  - Once it holds both locks, reclaim removes the descriptor.
  - Reclaim restores the prior speed only when a restore is owed and the engine is the same game process. The restore is checked by readback. Otherwise it reports `speed_restored: false` with a note.
  - If the owner died during a job, reclaim marks the world uncertain.
  - `status`, `start` and `stop` against an unreachable owner now name `pioneer reclaim`.
- **I5.**
  - `publish()` failure sets `fatal` and cancel, and raises `JournalError`.
  - Cleanup paths use `publish_quiet`.
  - `cleanup()` wraps closing the channel, writing the final journal and removing the descriptor, each on its own. It always calls `shutdown()`.
  - `remove_descriptor` removes a descriptor whose mode was tampered with if its `owner_id` is ours.
  - `serve()` raises on fatal or cleanup errors, so `main` exits 1.
  - `command()` refuses new jobs once the owner is fatal.
- **M1.** The policy test sets `XDG_STATE_HOME` to its temp dir. Referent: the new assertion at `test_cli_uses_transaction_and_labels_discard_metadata_only`, that `state_home/kpharness/playback-locks/localhost-12345.lock` exists.
  The pre-existing real `~/.local/state/kpharness/playback-locks/localhost-12345.lock` (mtime 11:02:49) was left in place. mtime is not a usable referent here, because flock and O_CREAT on an existing file do not change it.
- **M2.** `start()` runs a short-lived `--launch` process and waits on it with `communicate`. The launcher starts the `--serve` owner, then exits 0 (attached), 1 (failed) or 2 (unknown) through `os._exit`. The owner is never the caller's child.
- **M3.** `ControlServer` is a ThreadingMixIn with `daemon_threads` and without `block_on_close`. The handler read timeout is 1s and the client timeout is 5s.
- **M4.** The startup deadline is `KP_PLAYBACK_START_TIMEOUT`, default 30s (was 10s). The launcher wait adds 15s on top of that.
- **M5.** `cli._channel` is a context manager under `PB.engine_guard`. exec, reply, state, events and shots are refused while an owner is attached. `cmd_status` reports `engine_busy` and exits 0.
- **M6.** Documented, not fixed. A cancel during a wait that answered an authored bark is still reported as clean.
- **M7.** `mutation_started` is now set after the prior-speed read and journal write, just before the first speed write.
- **M8.** On POSIX, `engine_guard` opens the lock directory with `O_DIRECTORY|O_NOFOLLOW`, re-checks uid and mode with `fstat`, and opens the lock with `dir_fd`.

## Red, then green (the new tests)

The first red pass (`pioneer-round2-red.log`) was not clean evidence. Five tests failed for the right reason. The rest errored on the old 10s startup deadlines or on a journal `KeyError`.

So I redid it:
- I reordered the assertions so the engine speed is the first check that can fail. D and SIGHUP now save the journal before the signal and assert it after the engine check.
- C now uses a raw stop, so it isolates I3 from I2.
- I rebuilt the pre-change `playback.py` from the `cat -n` dump taken at session start (599 lines, parses) into `/tmp/old-tree`, alongside the current package and test file.

The only change to that temp copy was raising the old owner start deadline from 10s to 60s, for load.

Red pass 2, run with `-k` (`pioneer-round2-red2.log`): 10 run, 6 failures and 4 errors, each at the first failing line.

| Test | Pre-change failure |
|---|---|
| A readback mismatch | `AssertionError: 3.0 != 2.0 : engine left at the clamped speed` |
| B route edit then stop | `PlaybackError: stale or invalid playback descriptor` |
| C route edit mid-job (raw stop) | `AssertionError: 12.0 != 2.0 : route edit skipped the speed restore` |
| D SIGTERM | `AssertionError: 12.0 != 2.0` |
| SIGHUP | `AssertionError: 12.0 != 2.0` |
| F SIGKILL, then reclaim | `AttributeError: module 'kpharness.playback' has no attribute 'reclaim'` |
| reclaim on a different process | `ConnectionResetError` from `status` (no reclaim hint and no recovery path) |
| G unwritable journal | `AssertionError: owner kept serving with an unwritable journal` |
| K tampered descriptor | `AssertionError: owner alive after stop with a tampered descriptor` |
| H idle connection | `TimeoutError: timed out` |
| M2 not a child (`red2-m2.log`) | `AssertionError: 68164 == 68164` (PPid was the test process) |

In G and K the engine speed is 2.0 even on the old code. There the defect is an owner that stays alive and a descriptor left behind, and that is what goes red.
The CLI tests (`Round2CliTests`) were not run against the old tree, because the pre-change `cli.py` was not preserved.

New tests, each asserting `self.engine.scale()`:

| Probe | Test | Engine speed asserted |
|---|---|---|
| A | `test_probe_a_readback_mismatch_restores_prior_engine_speed` | 2.0 (was 3.0) |
| B | `test_probe_b_route_edit_does_not_block_stop` | 2.0, and a second route can attach |
| C | `test_probe_c_route_edit_mid_job_still_restores_speed` | 2.0 (was 12.0) |
| D | `test_probe_d_sigterm_behaves_like_stop`, `test_sighup_behaves_like_stop` | 2.0 |
| F | `test_probe_f_sigkill_then_reclaim_restores_recorded_speed` | 12.0 after SIGKILL, 2.0 after reclaim |
| F | `test_reclaim_refused_while_owner_alive` | connections unchanged |
| F | `test_reclaim_never_restores_on_a_different_game_process` | 5.0, no `speed` command sent |
| G | `test_probe_g_unwritable_journal_exits_owner` | 2.0, owner dead, descriptor gone |
| K | `test_probe_k_tampered_descriptor_mode_still_detaches` | 2.0, owner dead, descriptor gone |
| H | `test_probe_h_idle_connection_does_not_block_status` | 2.0, status under 1.5s |
| M2 | `test_owner_is_not_a_child_of_the_caller` | PPid is not the test process |
| M5 | `test_exec_refused_while_owner_holds_engine`, `test_exec_without_owner_still_works` | engine connections = 1 |
| I4 | `test_cli_reclaim_after_sigkill` | 2.0 |

## Suites

| Suite | Container (Py 3.12.3) | Host (Py 3.14.7, host-cmd) |
|---|---|---|
| kpharness_playback_test.py | Ran 32, OK (76.5s), 0 ResourceWarning (`playback-container3.log`, after the reorder) | Ran 32, OK (93.9s), 0 ResourceWarning (`playback-host3.log`, after the reorder) |
| kpharness_pioneer_policy_test.py | Ran 21, OK | Ran 21, OK |
| kpharness_offline_test.py | Ran 150, OK | Ran 150, OK (`offline-host2.log`) |
| kpharness_creative_test.py | Ran 33, OK | Ran 33, OK |

The first host pass ran all five jobs at once at load average about 230. Two things failed in that pass:
- In playback, 4 errors in `Round2CleanupTests`: `owner startup outcome uncertain`, where the launcher's wait timed out after 45s.
- In offline, 1 failure in `test_placeable_transaction_does_not_count_range_without_open`: "budget expired".

Isolated reruns are green: `Round2CleanupTests` 4/4 OK in 11.6s, the offline test 1/1 OK, then the full host playback and offline suites both OK.
I classed that pass as load-induced, not a defect: the same code passes each time it runs alone. The logs for both passes are kept.

Process checks after the runs:
- `pgrep -a python | grep kpharness.playback` shows no owners in the container or on the host.
- `ps -eo pid,ppid,stat,args | awk '$3 ~ /^Z/'` shows zombies, but none are kpharness owners or launchers. They are QtWebEngineProc, bash, git, python3.11 and host-spawn, whose parents are 20504, 359173 (Claude 2.1.283) and 38012.
- PID 1 is `systemd` in both environments (the container shares the host PID namespace).

M5 reach: `grep -rnE 'kpharness(\.cli)? (exec|state|events|reply|shots)' scripts/ docs/` and a grep of `scripts/harness/*.sh` find only documentation examples of a single manual `exec`/`state`. Scripts use only `run`, which is unaffected. No parallel scripted caller exists.

## Reviewer probe script (unmodified), rerun

Container (`probe-container.log`) and host (`probe-host.log`) give the same values. Host run:

```
PROBE A clamp: prior=2.0 op=uncertain observed=3.0 speed_after_job=2.0 engine_scale_now=2.0 world_uncertain=True
PROBE B route-edit-then-stop: stop accepted; owner_alive=False; descriptor=False
PROBE B other route attach: succeeded
PROBE C route-edit mid-job then raw stop ok=True: engine_scale_now=2.0 (prior 2.0) speed_after_job=2.0 op=execution_stopped last_error='PlaybackError: route changed while attached'
PROBE D SIGTERM: owner_alive=False engine_scale_now=2.0 (prior 2.0) descriptor_left=False journal_op=execution_stopped journal_active=None status='execution_stopped' reattach='reattach ok' journal_has_prior_speed=True
PROBE E SIGINT: owner_alive=False engine_scale_now=2.0 (prior 2.0) descriptor_left=False journal_op=execution_stopped journal_active=None status='execution_stopped' reattach='reattach ok' journal_has_prior_speed=True
PROBE F SIGKILL: owner_alive=False engine_scale_now=12.0 (prior 2.0) descriptor_left=True journal_op=running journal_active=1 status='PlaybackError: playback owner is not reachable ([Errno 111] Connection refused); if the owner is dead, run `kpharness pioneer reclaim --out ...`; it refuses while the owner still holds its locks' reattach='PlaybackError: ... reclaim ...' journal_has_prior_speed=True
PROBE G play accepted job=239ca719 state=queued
  -> ERROR FileNotFoundError: route.toml.playback.json (the owner exited and removed its descriptor; the probe's next PB.control(status) has nothing to read)
PROBE H unauth replies=['control authentication failed' x4] still_attached=True status_with_one_hog=0.01s ok
PROBE I stop after uncertain: pre=uncertain final_op=execution_stopped final_world_uncertain=True
PROBE J play-then-immediate-stop: final=execution_stopped boundary=0 mutations=[('lua','return true',None), ('speed','',16.0), ('speed','',2.0)]
PROBE K descriptor 0644: client stop -> PlaybackError: playback sidecar must be owned by this user with mode600; after raw stop owner_alive=False descriptor_left=False
PROBE L two concurrent attaches: [('ok','30439d5d'), ('ok','30439d5d')]; live_owner_procs=1 engine_connections=1
Ran 12 tests, FAILED (errors=1: probe G, expected after the I5 fix)
```

Notes:
- F: the probe never calls reclaim, so a speed of 12.0 is expected at that point. The recovery is proven by `test_probe_f_sigkill_then_reclaim_restores_recorded_speed` and `test_cli_reclaim_after_sigkill`.
- B (container run): `owner_alive=True` 1s after stop, with the descriptor already gone. That is a slow exit under load. The host run shows `False`. The regression test waits up to 20s and asserts that the owner is dead.
- Probe B now attaches a second route and never stops that owner. The probe leaked one idle owner in each environment. I sent both SIGTERM and they exited (`pgrep` found none afterwards, in the container or on the host), which also exercises the new handler. No synthetic engines were left running.

## Residuals (not fixed)

- M6 (a wait that answers a bark is still classed as read-only) is documented only.
- `pioneer.py`'s own compare-and-restore is still used for Pioneer `step` without an owner. That path holds the engine lock but not the owner journal.
- Reclaim trusts the journal's `runtime_identity` and `runtime_uptime_ms`. A journal from before this round lacks `runtime_uptime_ms`, so `_same_session` is false and reclaim only reports.
- The live-game proof of attach, play, stop and reclaim is still pending.

## Round 3

Scope: review I6 (idle unauthenticated sockets exhaust owner threads before
token check). Historical logs: [round 3 evidence bundle](pioneer-round3-evidence.log), with original paths and hashes in [the evidence index](evidence-index.json).

### Files changed (only these)

- `scripts/harness/kpharness/playback.py`: bounded admission for the control server.
- `tools/kpharness_playback_test.py`: `Round3AdmissionTests` (2 tests), `proc_count`, and a fix to the `alive()` death oracle.
- `docs/pioneer-authoring.md`: the control-server paragraph (old lines 96-97).

### Fix

- `CONTROL_SLOTS = 16` (playback.py:53). `ControlServer.process_request` (:688) takes a `BoundedSemaphore` without blocking before any handler thread starts. When all slots are full, `_evict_one` (:678) shuts down the oldest connection that has not yet sent a full line. It skips sockets that already hold a complete line (`_line_waiting`, :643, via `MSG_PEEK`). The new connection then waits up to `CONTROL_EVICT_WAIT = 0.5`s for the slot. If none frees, the socket is closed and no thread is started.
- This gives the authenticated path its reservation. A client that sends its request line at once (`status`, `stop`) is never the eviction victim, because idle attackers are older and have no line.
- Handlers remove themselves from the evictable set as soon as a full line arrives (`Handler.handle` -> `server.admitted`, :622). After that, `command()` never blocks. It only snapshots or queues work (playback.py `Owner.command`), so the slot frees quickly.
- The pre-auth deadline covers the whole line. `read_request_line` (:601) sets `settimeout(remaining)` on each recv, measured against one 1.0s monotonic deadline. The old per-read timeout let a client that trickles a byte every 0.3s hold a thread forever. The reply `sendall` resets the timeout to 1.0s first.
- Race hygiene: `shutdown_request` (:703) pops the socket from the idle and held sets under the same lock that eviction holds before `shutdown()`. Eviction therefore never touches a closed or reused fd. It releases the slot last, exactly once, and only for sockets that hold one.
- `request_queue_size = 128` (:665). With the default of 5, flood SYNs were dropped and retried after 1s.

### Red, then green

Red (round-2 `playback.py`, new tests), `red-round3-admission-before-fix.log`:
```
test_idle_flood_keeps_threads_bounded_and_control_working ... I6 pid=1086797 base=2/7 peak=34/39
AssertionError: 34 not less than or equal to 20 : 34 owner threads after 64 idle sockets
AssertionError: False is not true : trickling client kept its connection past the deadline
Ran 2 tests in 13.306s
FAILED (failures=2)
```
(The debug `I6 pid=` print was removed after this run.)

Green, `green-round3-admission-after-fix.log`: `Round3AdmissionTests` 2/2 plus `test_probe_h_idle_connection_does_not_block_status`. `Ran 3 tests in 50.120s OK`.

Measurement, 256 idle sockets at once (`measure-256-idle-after-fix.log`, ad-hoc script outside the repo):
```
MEASURE slots=16 base(threads,fds)=(2, 7) peak_after_256_idle=(19, 24) status=idle in 0.012s
```
19 = main + worker + 16 handlers + 1 thread finishing while its replacement starts.

What the flood test asserts: 64 idle sockets opened at once (half send a partial line). Peak owner threads and fds, sampled every 10ms, stay at or below baseline + 16 + 2. `status` answers in under 3s. A second flood of 64 then goes in, and `stop` still lands in under 3s. The owner dies, the descriptor is removed, and engine speed is back at 2.0.

### Pre-existing flake found and fixed: `test_probe_f`

The first container and host playback runs each had 1 error in `test_probe_f_sigkill_then_reclaim_restores_recorded_speed`. The error was `cannot reclaim: another playback owner ... holds engine`. Diagnosis (`probe-f-flake-diagnosis.txt`):
- Isolated, 6 runs each: round-3 code failed 2/6, and the round-2 `playback.py` backup also failed 2/6. So it is not caused by I6.
- A `/proc` trace after SIGKILL showed `('Z', 2)`: the group leader is a zombie while a second thread is still exiting and still holds the fds (and so the flocks).
- The test helper `alive()` counted any `Z` as dead. It now counts a zombie as dead only when it is the last task. After the fix: `probe-f-x8-after-alive-fix.log`, 8/8 OK.
- `reclaim()` itself behaved correctly: it refused while the locks were still held.

### Suites (serial, one at a time)

| Suite | Container | Host |
|---|---|---|
| kpharness_playback_test | first run: 34, FAILED (errors=1, probe_f); rerun: 34 OK in 119.1s; final after the `alive()` fix: **34 OK in 55.5s** | first run: 34, FAILED (errors=1, probe_f); final after the `alive()` fix: **34 OK in 134.0s** |
| kpharness_pioneer_policy_test | **21 OK** in 2.5s | **21 OK** in 0.15s |
| kpharness_offline_test | **150 OK** in 349.7s | first run: rc=0, but the log was cut before the summary line (host-cmd stream); rerun with a host-side redirect: **150 OK in 98.5s, rc=0** |
| kpharness_creative_test | **33 OK** in 18.3s | **33 OK** in 24.2s |

Logs: `container-*.log`, `container-rerun-*`, `container-final-*`, `host-*.log`, `host-final-*`, `host-rerun-kpharness_offline_test.log`, plus the `*-summary.txt` files. The policy, offline and creative suites ran before the `alive()` test-helper change. That change touches only the playback test file, and the playback suite was rerun after it in both environments.

Owner check after every suite: `ps -eo pid,args | grep "[k]pharness.playback --serve"`. None were left after the suites. One owner (pid 1712691, route under `/tmp/kpharness_playback_d20hi10h`) was seen right after the container probe run, left by probe B's second attach. It was gone by the next check without a signal from me. No owners are left now in either environment.

### Reviewer probe (round-1 fixed copy), rerun

`probe-container.log` and `probe-host.log`: both `Ran 12 tests`, `FAILED (errors=1)`. The one error is probe G `FileNotFoundError: route.toml.playback.json`, the same expected outcome as round 2 (the owner exits on journal failure and removes its descriptor). Host:
```
PROBE A clamp: prior=2.0 op=uncertain observed=3.0 speed_after_job=2.0 engine_scale_now=2.0 world_uncertain=True
PROBE B route-edit-then-stop: stop accepted; owner_alive=False; descriptor=False
PROBE C route-edit mid-job then raw stop ok=True: engine_scale_now=2.0 (prior 2.0) ... last_error='PlaybackError: route changed while attached'
PROBE D SIGTERM: owner_alive=False engine_scale_now=2.0 (prior 2.0) descriptor_left=False ... reattach='reattach ok'
PROBE E SIGINT: owner_alive=False engine_scale_now=2.0 (prior 2.0) descriptor_left=False ... reattach='reattach ok'
PROBE F SIGKILL: owner_alive=False engine_scale_now=12.0 (prior 2.0) descriptor_left=True journal_op=running ...
PROBE G play accepted job=fd654df1 state=queued   -> ERROR FileNotFoundError (expected)
PROBE H unauth replies=['control authentication failed' x4] still_attached=True status_with_one_hog=0.02s ok
PROBE I stop after uncertain: pre=uncertain final_op=execution_stopped final_world_uncertain=True
PROBE J play-then-immediate-stop: final=execution_stopped boundary=0 mutations=[('lua','return true',None), ('speed','',16.0), ('speed','',2.0)]
PROBE K descriptor 0644: client stop -> PlaybackError: ... mode600; after raw stop owner_alive=False descriptor_left=False
PROBE L two concurrent attaches: [('ok','77e7e79f'), ('ok','77e7e79f')]; live_owner_procs=1 engine_connections=1
```
Container: same values, except J `mutations=[]` (the stop landed before initialization) and probe B's `owner_alive=False`.

### Grill me

1. **Can a flood still evict the legitimate client before its handler reads?** Only if the client's line has not reached the owner's receive buffer when eviction runs. `_evict_one` skips any socket where `MSG_PEEK` shows a newline, and clients send the line right after connect. The remaining window is a client whose bytes are still in flight while more than 16 attacker accepts land. **Unverified under heavy load.** The flood test and the 256-socket measurement (status in 0.012s) show it does not happen at these scales.
2. **Why is 16 slots enough, and why do authenticated handlers not starve?** Handlers leave the evictable set after reading a line. `command()` only snapshots or queues and never waits on a job (playback.py `Owner.command`, "status"/"stop" return `snapshot()`, others `jobs.put`). So an authenticated slot frees in milliseconds. Referent: `test_idle_flood...` refills to 64 and `stop` lands under 3s.
3. **Is the `alive()` change hiding a real bug?** No. Round-2 `playback.py` failed probe_f at the same 2/6 rate, and the `/proc` trace shows `('Z', 2)`. Reclaim refusing while a thread still holds the flock is the designed behavior. Referent: `probe-f-flake-diagnosis.txt`.
4. **Could eviction call `shutdown()` on a reused fd?** No. `shutdown_request` removes the socket from `_idle` under `_guard` before closing it, and `_evict_one` only shuts down sockets it finds in `_idle` while holding `_guard` (playback.py:678-713). No test forces this interleaving: **unverified by test, holds by source.**
5. **Does the total deadline break a slow legitimate client?** Only a client that takes more than 1s to send one line. `control()` sends the line in a single `sendall` right after connect (playback.py `control`). Every suite passed, including under load in both environments.

Open question: whether eviction ever drops a legitimate client under real host load. The check that settles it: a stress loop of 1000 authenticated `status` calls against a continuous reconnecting flood, counting failures.

## Round 4

Follows the round 3 review (`/home/brunner56/kp-live-20260922/pioneer-round3-review.md`, PASS with M1 and M2). Historical logs: [round 4 evidence bundle](pioneer-round4-evidence.log), with original paths and hashes in [the evidence index](evidence-index.json). Pre-edit copies: `/home/brunner56/kp-live-20260922/pioneer-r4-backup/`.

### Files changed (only these)

- `scripts/harness/kpharness/playback.py`
- `tools/kpharness_playback_test.py`

### M1 fix: read and admit are now one step

- `read_request_line(sock, deadline, admit)` peeks (`MSG_PEEK`) until the newline is in the receive buffer. It calls `admit()` while the line is still there, and only then consumes it. A new connection's `_evict_one` checks `_line_waiting` under `_guard`, so it skips this socket for the whole gap.
- `ControlServer.admitted()` now returns False when eviction already removed the socket. The handler then returns before `json.loads` and `command()`. Nothing runs and no reply is sent.
- `control()` raises `PlaybackError` on an empty reply ("closed the control connection without a reply; check status before retrying"). Any other undecodable reply also raises `PlaybackError`, not `JSONDecodeError`.
- The handler comment now says what holds: either the socket leaves the evictable set first, or it was evicted first and the command never runs.

### Red, then green

New class `Round4ReadEvictTests` (in-process: real `ControlServer` and `Handler`, fake owner, one hook in `admitted()`):

| Test | Before fix (`red-container.txt`) | After fix |
|---|---|---|
| `test_eviction_during_widened_gap_keeps_the_reply` (0.3s hook, 15 idle + 1 evicting connect) | FAIL: `command ran ['play'] but the reply was dropped` | ok: reply `ok: true`, `executed == ['play']` |
| `test_socket_evicted_before_admission_never_runs_the_command` (hook evicts this socket first) | FAIL: `['play'] != []` | ok: empty reply, `executed == []` |
| `test_control_turns_an_empty_reply_into_a_playback_error` | ERROR: `JSONDecodeError` | ok |

The reviewer's unmodified probes against the fixed code:
- `race_read_then_evict.py` at 0.3, 0.05 and 0.02: all three `legit_reply` ok, `executed ['play']` (`reviewer-race-probe-after-fix.txt`). Before: 0.3 gave an empty reply.
- `inproc_stress.py 300 4 0.02`: **0 failures** in 300, 1,385 evictions, 0 on a closed socket (`reviewer-inproc-widen-after-fix.txt`). Before: 2/300.

### M2: probe_f on the host

`probe_f_loop.sh` ran `test_probe_f_sigkill_then_reclaim_restores_recorded_speed` 50 times on the host (Python 3.14.7). It added 12 CPU busy loops that it owned and killed at exit. The host load average during the loop ranged from 120 to 259 on 12 cores. Every run's full log is kept in `probe-f-host-x50/run-NNN.log`.

Result: **50/50 OK, 0 failures**, no owner left after any run (`probe-f-host-x50.txt`). The failure did not reproduce, so there is no new error text to diagnose. Host tally since the `alive()` fix: 2 errors in 159 runs (the review's 109 plus these 50). Both errors are in the one early batch at 14:57, and their text was not kept. The cause of those 2 stays unproven.

### Suites (serial, one at a time)

| Suite | Container | Host |
|---|---|---|
| kpharness_playback_test (37) | **37 OK** in 124.7s (`suite-container.txt`) | **37 OK** in 129.7s, Python 3.14.7, rc=0 (`suite-host.txt`) |

Owner check after each: `ps -eo pid,args | grep "[k]pharness.playback --serve"` is empty in both environments. No burner loops remain on the host.

### Grill me

1. **Can the peek loop be fooled into consuming bytes that are not the peeked ones?** Only one thread reads each socket, so `recv(n)` after a peek of n bytes returns exactly those bytes. The code still checks `data.endswith(b'\n')` after the final read. Referent: `playback.py` `read_request_line`; all 37 tests, including the 64 KiB and trickle cases, pass in both environments. Weakest point: no test forces a short `recv` after a peek. **Unverified by test, holds by source.**
2. **Can a client still get an empty reply for a command that ran?** Only if `sendall` fails after `command()`, for example when the client dies or the owner is SIGKILLed mid-request. Eviction can no longer do it: `test_eviction_during_widened_gap_keeps_the_reply` and `test_socket_evicted_before_admission_never_runs_the_command` cover both orders. So the `control()` message says "check status before retrying", not "not run".
3. **Is the M2 flake gone?** Not proven. 50/50 under load 120–259 is new evidence, not a diagnosis. Referent: `probe-f-host-x50.txt`.
4. **Does peeking change the byte limit?** No. A line of up to `LIMIT` bytes, including the newline, is accepted. Longer lines are refused, and so are unterminated inputs past `LIMIT`. This is the same boundary as before (`len(data) + end > LIMIT`).

Open question: what the 2 early host probe_f errors were. To settle it, catch a failing run with its log kept. The loop script is ready: `pioneer-round4-logs/probe_f_loop.sh <worktree> <logdir> <N> <burners>`.
