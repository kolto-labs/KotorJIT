# Pioneer playback round 3 review (I6 bounded admission + alive() test fix)

Reviewer: independent, read-only on source. Worktree
`/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`.
Source under review: `scripts/harness/kpharness/playback.py` (mtime 13:43),
`tools/kpharness_playback_test.py` (mtime 14:16), `docs/pioneer-authoring.md`.
Probes and raw outputs: `/home/brunner56/kp-live-20260922/review-probes-pioneer-r3/`.
This review was resumed after a rate-limit cut; completed outputs from the first
pass were reused, and the missing probes were run.

No Wine or game. No live-game lock touched. No signals sent to processes this
review did not start. No git writes. No `kpharness.playback --serve` owner left
(`ps -eo pid,args | grep "[k]pharness.playback --serve"` empty after the last run).

## Suites (serial)

| Suite | Container | Host |
|---|---|---|
| kpharness_playback_test (34) | **34 OK** in 127.7s (`suite-container.txt`) | **34 OK** in 60.8s, Python 3.14.7 (`suite-host.txt`) |

Includes `Round3AdmissionTests` (2) and `Round2SignalTests.test_probe_f_*`.

## Stress: Grill item 1 (does a flood drop a legitimate client?)

Real owner subprocess + suite synthetic engine, out-of-process reconnecting
flood (idle / partial-line / 1-byte trickle mix), N authenticated `status`
calls through `playback.status` (`owner_stress_test.py`):

| Flooder procs | Calls | Flood connects | Failures | Peak owner threads | p50 / p99 / max (s) |
|---|---|---|---|---|---|
| 8 | 1000 | 9,662 | **0** | 18 | 0.007 / 1.03 / 2.00 |
| 32 | 2000 | 35,222 | **0** | 19 | 0.002 / 1.62 / 5.26 |
| 96 | 1000 | 150,876 | **4** (3 connect timeout, 1 empty reply) | 19 | 0.62 / 4.30 / 5.35 |

In-process (real `ControlServer`/`Handler`, fake owner): 1 flooder 0/1000,
4 flooders 0/1000, 0 of ~1,800 evictions touched a closed socket
(`inproc-baseline.txt`). 96 flood processes, `play` commands: 3/1000 client
timeouts; one of them (`n=100`) had executed on the owner (`inproc-attrib-96.txt`).

Thread bound holds at every scale (peak 19 = 2 base + 16 slots + 1 in handover).
Failures appear only at 96 reconnecting flood processes, as latency past the
5s client timeout, not as thread growth.

## Findings

### Critical
None.

### Important
None.

### Minor

**M1. Read-then-evict window: an authenticated command can run while its reply is dropped.**
`Handler.handle` consumes the line with `recv` (`playback.py:610`) and only then
calls `self.server.admitted()` (`:628`). In between, the socket is still in
`_idle`, and `_evict_one` (`:678-686`) judges it by `MSG_PEEK` (`:648`), which now
sees an empty buffer. So the socket is evictable. After eviction the handler still
parses, authenticates and calls `owner.command()`. `sendall` then fails, and that
failure is suppressed (`:638-640`). The client reads `b''`, and `control()`
raises a raw `JSONDecodeError`, not `PlaybackError` (`:772-773`).
The code comment at `:626-627` ("a new connection cannot evict it") is therefore
not exact.

Referent: `race_read_then_evict.py` → `race-read-then-evict.txt`. The only hook is a
sleep inside `admitted()` to hold the window open:
```
{"widen": 0.3, "legit_reply": "", "reply_wait": 0.53, "executed": ["play"]}
{"widen": 0.05, "legit_reply": "{\"ok\": true, ...}", "executed": ["play"]}
```
With a 0.02s widening, 2/300 status calls failed with an empty reply (`inproc-widen.txt`).
Without widening, the window lasts microseconds. It was not isolated as the cause of
any unwidened failure: the 96-flooder empty reply could also be the no-slot close
(`:691-693`).

Why Minor: it needs a hostile local flood already hitting the port. Nothing unsafe
runs: the op is one the user sent, with a valid token. `status` still shows the
true state, and the client does not retry.
Suggested fix, cheap: make `admitted()` return whether the socket was still in `_idle`.
If it was already evicted, the handler returns before `json.loads`/`command()`.
That turns "ran, but the reply was lost" into "not run, connection closed". Optionally,
map an empty reply in `control()` to `PlaybackError`.

**M2. Residual probe_f host flake, cause unknown.**
One early host batch after the `alive()` fix showed 2/10 ERROR (`probe-f-x10-host.txt`,
14:57, test file mtime 14:16). The error text was not kept. All later host runs passed:
12 + 20 + 30 + 12 under load + 10 under flood + 15 on resume (`probe-f-host-*.txt`),
plus 10/10 in the container. Total on host: 2 errors in 109 runs. The writer's
diagnosis (`probe-f-flake-diagnosis.txt`: a `('Z', 2)` zombie leader with a live
thread holding flocks) is plausible. It matches the fix, and the failure rate dropped
from 2/6 to 2/109. It is not proven complete.

## Grill items (writer's list, weakest first)

claim: (1) "A client that sends its request line at once ... is never the eviction victim."
referent: stress tables above; `race-read-then-evict.txt`
checked: `owner_stress_test.py` at 8/32/96 flooders; `race_read_then_evict.py`
verdict: holds while the line is still in the buffer (0 failures in 3000 calls at 8–32 flooders). Does not hold for the recv→admitted window (M1).
confidence: high for the window (it is deterministic with a widening hook); medium on real-world rate. A capture that tags the no-slot close path would change it.

claim: (4) "Eviction never touches a closed or reused fd."
referent: `playback.py:678-686` and `:703-713`. `shutdown_request` pops from `_idle` under `_guard` before `close()`, and `_evict_one` only shuts down members found under `_guard`. Sockets are keyed by object, not fd. `inproc-baseline.txt` reports `evict_saw_closed_socket: 0` over 1,796 evictions.
checked: source + instrumented run
verdict: holds
confidence: high

claim: (3) "The `alive()` change is not hiding a real bug."
referent: `kpharness_playback_test.py:531-544`. The change only makes a zombie *with remaining threads* count as alive. `alive()` has exactly three call sites: `wait_dead` (`:549`, `:551`) and `kill_owner` (`:557`). No test asserts liveness through it. So the change only makes the wait for death stricter, not weaker. A 20s `wait_dead` timeout still bounds it. `reclaim()` in product code gates on flocks, not on `alive()`.
checked: source read; probe_f repeat runs (M2)
verdict: holds
confidence: medium. The residual 2/109 host errors without saved text is the gap.

claim: (2) "16 slots are enough; authenticated handlers free in milliseconds."
referent: p50 2–7 ms at 8–32 flooders; peak threads 19 at every scale.
verdict: holds
confidence: high

claim: (5) "The total deadline does not break a slow legitimate client."
referent: `control()` sends the whole line in one `sendall` (`:770`); both suites are green.
verdict: holds
confidence: high

## Reviewer-added attacks

| Attack | Verdict | Evidence |
|---|---|---|
| Pre-auth parse cost (token check comes after `json.loads`) | holds, bounded | `preauth-payloads.txt`: at the 64 KiB limit, deep nesting gives a caught RecursionError in 0.017s. A huge int, many keys or a long string each take ≤0.009s. Handler threads return to baseline (3). |
| Huge complete lines | holds | exactly 65,536 bytes gets parsed then refused. 65,537 gives `invalid control message` (`:606`, `:617`). |
| Trickle past total deadline | holds | `test_trickling_client_is_dropped_by_total_deadline` green in both environments. A 1-byte trickle flooder at 96 procs still left peak threads at 19. |
| Backlog / fd exhaustion | holds | `request_queue_size = 128`. Accepts over the slot limit are closed within 0.5s with no thread started (`:689-693`). Writer measured 256 idle → fds 24. Our flood peaked at 19 threads. |
| Semaphore double-release / leak | holds | release only if the socket is in `_held` (`:708-713`). The no-slot path uses the base `shutdown_request` and never releases. The `process_request` exception path releases once. |
| Accept loop serialized by `CONTROL_EVICT_WAIT` | known degradation | at 96 flood procs, p99 is 4.3s and 0.3–0.4% of calls pass the 5s client timeout. This is bounded, not exhaustion. I6 asked for a bound, and it holds. |

## Handoff

The one question this review could not settle: what the 2 host probe_f errors at
14:57 were (M2). To settle it, rerun `Round2SignalTests.test_probe_f_*` on host
under comparable load, keep the full log of any non-OK run, and check the error text
for `cannot reclaim: another playback owner`.

I6 is closed. Owner threads stay bounded under every flood tried. Authenticated
`status` and `stop` stay reachable up to 32 reconnecting flood processes with zero
failures. Both suites are green in both environments. M1 and M2 are non-blocking.

Pioneer round 3 verdict: PASS
