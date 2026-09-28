# Task 7 Gamescope backend scoped re-review

## Verdict

**FAIL — 2 Critical and 4 Important findings remain.**

The fix round substantially improves the backend. Prior C3, C4's cross-lease
and early-exit defects, I1, I2, I4, I5, and CMake registration from I6 are
addressed. C1 is implemented at the backend/session level, but route-wide
failure timing and cleanup receipt detail remain incomplete. C2 remains open
because the schema validates declared capture fields without fully validating
the executed FFmpeg command.

No game, Wine, Xvfb, Gamescope, or real FFmpeg process was launched during
this re-review.

## Critical findings

### C1. Schema 2 still permits the FFmpeg command to capture a different display

`scripts/harness/kpharness/display_backends.py:266-282` validates the capture's
declared `input` field against `window.display`, and validates the command's
`-window_id` and `-video_size`, but it never parses or validates the command's
actual `-i` argument. It also does not reject duplicate input options that can
change FFmpeg's effective source.

The reviewer reproduced the false pass with a fully matching lease/window and
capture dictionary whose command was:

```text
ffmpeg -video_size 800x600 -window_id 0x2a -i :666
```

while `capture.input` and `window.display` both declared `:91`.
`schema2_receipt(..., visual_status="accepted")["ok"]` returned `True`.

This leaves prior C2 partially unresolved: the atomic receipt can certify one
display while FFmpeg actually reads another.

Required fix: parse the exact argument array fail-closed, require exactly one
input and one `-window_id`, require the effective `-i` value to equal
`window.display`, reject conflicting duplicates, and test mutations of `-i`
and duplicated options.

### C2. Visual acceptance can be pre-authorized before the recording exists

`scripts/harness/kpharness/creative.py:303-304` exposes
`--visual-status accepted` on the run command, and passes that caller-selected
value directly to schema success at `creative.py:269-282`. The option is known
before launch, capture, media hashing, and human review. A user or automation
can therefore predeclare acceptance for unseen media, and a successful run can
write `ok=true` immediately.

The implementation brief requires a separate explicit human decision about
the completed unaltered recording. A preflight CLI assertion is not evidence
that the resulting artifact was reviewed.

Required fix: creative execution must always emit `visual_review.status =
pending` and `ok=false`. Add a separate post-run acceptance operation that
loads the immutable receipt, verifies the continuous artifact path/hash and
run identity, records reviewer/time/scope, and only then derives the accepted
receipt. The run command must not accept an up-front `accepted` value.

## Important findings

### I1. Capture failure is not checked around every route step or during helper waits

`CreativeRunner._do()` checks capture only for `do` steps
(`scripts/harness/kpharness/creative_steps.py:23-39`). Scenario step kinds
handled directly by `ScenarioRunner.run_step()`—including screenshots and any
non-`do` step—do not receive the required before/after check.

Within `advance_ticks` and `await_log`, the polling loop at lines 59-87 never
calls `capture_check`; both success branches return directly at lines 66 and
81 without a post-check. A lost window/lease or dead recorder may therefore
wait for the route predicate/timeout instead of failing at the next 250 ms
watch observation. `creative.py` performs a final check after `runner.run()`,
which prevents a final success in many cases but does not satisfy route-step
failure responsiveness and can waste the full step timeout.

Required fix: override `run_step()` to check before and after every step kind,
and call `capture_check()` on every helper polling iteration and immediately
before all success returns. Add failure-in-wait and non-`do` step tests.

### I2. Schema-2 cleanup loses component and ordering evidence

The Gamescope session implements recorder -> game/Wine -> display order in
`creative_wine.py:247-264`, but `creative.py:235-240` reduces the result to
only `{"status": "passed"}` or one aggregate error. `schema2_receipt()` copies
that aggregate mapping.

The required receipt must retain recorder, game/Wine, and display results
individually so the artifact itself proves every cleanup phase was attempted
and passed in order. The unit test at
`tools/kpharness_gamescope_backend_test.py:296-305` proves call order in a fake
session, but the final receipt does not preserve it.

Required fix: have teardown return or expose immutable per-component results
and an ordered cleanup transcript, then require all three component statuses
in schema success. Cover success and each component-failure path.

### I3. Lease cleanup is not retryable and does not prove the group is gone after SIGKILL

`GamescopeXwaylandLease.close()` sets `_closed = True` before cleanup begins
(`gamescope_xwayland.py:214-218`). If signalling, polling, or final waiting
raises, every later `close()` returns immediately even if an owned process
remains. In the leader-dead/child-live path, the implementation sends SIGKILL
at lines 255-259 but does not perform a bounded post-kill verification that the
recorded group member disappeared.

The corresponding test at
`tools/kpharness_gamescope_backend_test.py:174-188` makes the mocked `killpg`
call erase `ready_child` and then checks only that SIGTERM was called. It does
not model or assert termination of a stubborn remaining child.

Required fix: track cleanup phases separately; mark the lease fully closed only
after verified termination and resource closure; permit unfinished safe phases
to retry; after SIGKILL, poll the recorded identities/group boundedly and fail
cleanup if any verified member remains.

### I4. Integrated receipt and failure lifecycle coverage is still incomplete

The focused suite now registers in CTest and covers backend selection plus one
teardown-order test. It still does not drive `run_creative()` with a fake
Gamescope session through schema-2 finalization, physical-console receipt
correlation, visual-pending behavior, asynchronous failure during a route
step, per-component cleanup failure, or the executed-command/display mismatch
above.

Required fix: add an offline end-to-end fake Gamescope creative run that
asserts the final serialized receipt, plus negative variants for each identity
link, asynchronous route failure, visual post-acceptance, and cleanup phase.

## Prior finding disposition

| Prior finding | Re-review disposition |
| --- | --- |
| C1 executable integration | **Partially addressed** — explicit backend, session, recorder, teardown, docs, and schema path exist; I1/I2 remain. |
| C2 atomic receipt | **Not fully addressed** — lease/window/geometry/`-window_id` checks added; actual FFmpeg `-i` remains unchecked. |
| C3 readiness ownership | **Addressed** — parent session/PGID, ancestry, child environment, distinct authority, and liveness are checked. |
| C4 cross-lease and early exit | **Addressed** — concrete lease binding and stop-time exit-0 failure are implemented and tested. |
| I1 environment allowlist | **Addressed** — strict allowlist replaces denylist and software overrides are excluded. |
| I2 `/proc` parsing | **Addressed** — parsing begins after the closing comm parenthesis. |
| I3 leader-dead cleanup | **Partially addressed** — recorded group can be signalled through a live child; retry/final disappearance proof remain open as I3. |
| I4 production revalidation | **Addressed** — stable verifier ignores discovery time and input revalidates before focus/action groups. |
| I5 deep immutability | **Addressed** for the reviewed records and schema snapshots. |
| I6 tests/CTest | **Partially addressed** — focused gate is registered and expanded; integrated final-receipt/failure cases remain open as I4. |

## Reviewer validation

* `python3 tools/kpharness_gamescope_backend_test.py`: **20/20 PASS**.
* `python3 tools/kpharness_creative_test.py`: **28/28 PASS**.
* `python3 tools/kpharness_physical_console_test.py`: **22/22 PASS**.
* `python3 -m py_compile` over the changed Gamescope/creative modules and
  focused test: **PASS**.
* Direct mismatched-command proof: schema returned **`True`** for declared
  display `:91` with FFmpeg command input `-i :666`.

The host suites prove their current assertions and Xvfb compatibility. They do
not close the two Critical or four Important findings above.
