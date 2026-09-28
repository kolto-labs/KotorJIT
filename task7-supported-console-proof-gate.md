# Task 7 supported-console proof gate

## Verdict

**Do not ship a supported Python physical-console extraction yet.** The native
Console and `kp.console.v1` adapter have meaningful offline coverage, and the
private GPU receipt proves one real K1 happy path. Neither is a deterministic
test of the proposed Python boundary from owned keyboard input to the exact
`(runtime, session, request)` outcome. Shipping first would turn the private
controller's assumptions into a public API without the one oracle that can
reject the dangerous ambiguous cases.

The gate is one new host-only test module for the extracted adapter. It must
use scripted protocol and input ports, prove the acceptance and refusal matrix
below, and run in the normal offline CTest/Python gate. A separate real K1 run
remains required to prove that the production input port actually reaches F12;
it cannot substitute for this host oracle.

## What the present evidence proves

The native protocol implementation makes the required information available:

* `status` returns opaque `runtime`, `session`, `submitted`, `last_line`,
  `open`, and `input_calls`; other operations require runtime and session.
* `outcome` is exact by session and request, and terminal result data is
  separate from the legacy `completed` watermark.
* `output` supplies session/request-labelled lines and `dropped_through`, so a
  client can reject a cursor whose requested range has been evicted.

`tools/kp_consoleprotocoltest.cpp` tests many native-wire properties,
including stale runtime/session refusal, exact lookup expiration, and output
eviction. `tools/kp_consoletest.cpp` tests native Console lifecycle and
watermark behavior. They do not import a Python physical-console adapter, do
not drive an input port, and cannot prove what a supported Python extraction
does after an input race.

The private K1 receipt at
`private-gpu-runs/20260927-003752/protocol-wire.jsonl` is a valid happy-path
receipt only. It shows one identity throughout, F12 opening, then
`submitted` moving from 5 to 6, exact outcome request 6, and undropped output
lines 19--22 labelled session 1/request 6. `protocol-result.json` records
the same terminal typed result. This is good live evidence that the current
private controller can physically type one command; it does not exercise any
fault path.

The private controller infers its request as `before.submitted + 1` after
keyboard entry, polls until `submitted >= expected`, then asserts equality.
That is the correct core idea, but it is embedded in a private script rather
than a product adapter and has no deterministic race fixtures. Its preceding
stale-runtime/stale-session checks are direct protocol `submit` calls, not
failures observed by the physical-input flow. No current supported Python code
or test exposes `console_open`, `console_command`, or `owned_input`; the
checked-in `kpharness` client is a generic request channel.

## Required extracted boundary

Keep the extraction small and make it dependency-injected. The production
wrappers may use the existing `Channel` and `xdotool`/display code, but the
correlation algorithm must depend only on these narrow ports:

```python
class ConsoleProtocolPort(Protocol):
    def status(self, runtime: str | None = None) -> Status: ...
    def outcome(self, runtime: str, session: str, request: str) -> OutcomeReply: ...
    def output(self, runtime: str, session: str, after_sequence: str) -> OutputReply: ...

class OwnedInputPort(Protocol):
    def focus_owned_game_window(self) -> None: ...
    def press_f12(self) -> None: ...
    def select_all(self) -> None: ...
    def type_text(self, source: str) -> None: ...
    def press_enter(self) -> None: ...

class Clock(Protocol):
    def monotonic(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...
```

There must be no `submit`, `lua`, `exec`, or replay method on the physical
route. The test double must fail immediately if the implementation sends a
wire `submit` operation. `advance_ticks` remains a scenario predicate outside
this boundary: it may wait for game state after a verified console completion,
but cannot establish console acceptance or select a request.

The entry point should return an immutable receipt containing the captured
runtime, session, exact request, terminal outcome, and filtered output lines.
On every non-success it must return/raise a distinct typed failure with that
baseline and the last observation for diagnosis. It must not run a second
input sequence, submit a wire command, or promote a later/highest completed
request.

Required algorithm:

1. Discover a `Found` baseline, validate canonical decimal fields, and retain
   `runtime`, `session`, `submitted`, and `last_line` before any keyboard
   action.
2. Focus the owned game window. If the baseline says the overlay is closed,
   press F12 and wait for a `Found`, same-runtime, same-session status with
   `open=true`. If it is already open, retain the same identity check.
3. Send `select_all`, `type_text(source)`, and exactly one `press_enter` via
   `OwnedInputPort`.
4. Poll only `status(runtime=baseline.runtime)`. A `StaleRuntime`, a different
   returned runtime, a non-Found status, or a different session is failure.
   Compute exactly `candidate = baseline.submitted + 1`. Accept a candidate
   only when `submitted == candidate`; `submitted > candidate` is
   `DuplicateSubmission`, and a regression is failure. Do not consult
   `completed` to choose or validate a request.
5. Poll only `outcome(baseline.runtime, baseline.session, candidate)`. Require
   response and embedded outcome identities to equal the baseline/candidate.
   `Pending` and `Running` may wait. `Expired`, `Unavailable`, stale results,
   timeout, `Cancelled`, and `Failed` are distinct failures. Only the exact
   terminal `Succeeded` can continue.
6. Query only `output(baseline.runtime, baseline.session,
   baseline.last_line)`. Require `Found`, same session, and
   `dropped_through <= baseline.last_line`; otherwise fail `DroppedOutput`.
   Filter lines by both baseline session and candidate request. Require the
   expected console input evidence and required result evidence among those
   lines. Wrong-session/request rows, even with matching readable text, do not
   count. An empty filtered set is `MissingOutput`.

All protocol identifiers must stay canonical decimal strings. The adapter must
not coerce them through floating-point values.

## Smallest decisive host-test matrix

One parameterized offline test file with a scripted fake protocol, fake owned
input port, and fake monotonic clock is sufficient. It must assert the full
wire and input transcript, not just the final exception.

| Case | Scripted fixture | Required assertion |
| --- | --- | --- |
| Clean physical route | Baseline A/7/40/100 closed; open status A/7; Enter emits exactly request 41; exact outcome succeeds; output after 100 contains input and result rows tagged A/7/41. | Success receipt is `(A,7,41)`; input transcript is focus, F12, select-all, type, Enter; no wire `submit`; no use of `completed`. |
| Already-open route | Baseline/open status A/7/40/100 with `open=true`; one physical entry as above. | No F12 toggle; same correlation and success rules. |
| Stale runtime | After Enter, status with the captured runtime returns `StaleRuntime` or a different runtime. | `StaleRuntime`; no outcome/output lookup, no second Enter, no replay. |
| Reset/session change | After Enter, `Found` status returns A/8 (or exact lookup returns `StaleSession`). | `StaleSession`; it never queries/replays against A/8. |
| Duplicate/interleaved submission | After the single Enter, status reports submitted 42 when baseline is 40. Fixture may make 41 look successful and 42 successful. | `DuplicateSubmission`; neither request is claimed, and no outcome lookup selects 42 or the highest completed ID. |
| Exact outcome unavailable despite a high watermark | Candidate 41 is observed, `completed` is 999, but `outcome(A,7,41)` is `Unavailable` or `Expired`. | Typed lookup failure; no success based on `completed`, 999, or a later result. |
| Exact terminal failure/cancellation | Candidate 41 outcome is `Failed` or `Cancelled`, optionally while a later request succeeds. | Preserve the exact terminal failure; do not inspect/promote later output. |
| Dropped output | Candidate 41 exact outcome succeeds, but output after 100 says `dropped_through=101` (with or without surviving matching rows). | `DroppedOutput`; outcome success alone is insufficient. |
| Missing or foreign output | Undropped output has no A/7/41 rows, or rows only use A/7/42 or B/7/41. | `MissingOutput`; readable text cannot establish correlation. |
| Timeout | Status never reaches exactly 41, or exact outcome stays Pending/Running. | `SubmissionTimeout`/`OutcomeTimeout`; exactly one Enter and no replay after clock expiry. |

The clean case is the concrete oracle that proves the intended information
flow. The remaining cases prevent future refactors from silently replacing it
with `completed`, a highest-number heuristic, retry, or output-text match.
They should be compact scripted transitions, not a fake Lua evaluator and not
a game/Wine launch.

## Fixtures that make the test load-bearing

`ScriptedConsoleProtocolPort` should consume a declared sequence of responses
and record every call as `(op, runtime, session, request/cursor)`. It exposes
only discovery/status, exact outcome, and output. If the implementation asks
for `submit` through a generic underlying channel, the double must raise. Its
status objects include `completed` deliberately in the duplicate and
unavailable cases, with values that would make a watermark fallback falsely
pass.

`ScriptedOwnedInputPort` records physical operations and advances protocol
state only on `press_enter`. In the clean fixture it creates one request; in
the duplicate fixture it creates two. This proves the extracted path uses its
physical-input dependency at the only action that may create the request. It
does **not** claim an in-process fake is the real overlay.

`FakeClock` advances only when the adapter sleeps. This makes pending, reset,
and timeout tests deterministic and permits an exact assertion that the input
sequence ran once. Include a source string whose expected typed result is
unambiguous; retain response fixtures as protocol-shaped dictionaries so field
omission/type errors are also caught.

## Remaining live-game acceptance

After the host matrix passes, run one owned K1 session against the installed
candidate artifact. The live acceptance needs: captured source/deployed hashes;
the owned window identity; baseline and post-input wire records; a nonzero
DirectInput-call delta as supporting evidence; actual F12 `open=true`; exactly
one `submitted` increment in the captured runtime/session; exact successful
outcome; and undropped, session/request-filtered input and result output. The
scenario must use the extracted production input adapter, never the protocol
`submit` operation for the physical command.

This live run proves integration with the game window, DirectInput/overlay,
and engine-owned Console. It does not prove reset, duplicate, stale-runtime,
output-eviction, or timeout refusal: those remain deliberate host fixtures.

## Load-bearing gaps before shipment

1. There is no checked-in supported Python physical-console adapter or host
   oracle; the present logic is private-controller code.
2. No existing Python test binds owned keyboard actions to the exact protocol
   identity or verifies that a direct `submit` fallback is impossible.
3. The live receipt is only a happy path. Its stale checks are direct wire
   submissions before physical input, and it never injects reset, duplicate,
   expiration, dropped output, or timeout into the physical flow.
4. `input_calls` is useful live evidence that DirectInput hooks ran, but it is
   not a request identity and cannot replace exact session/request lookup.

The implementation is ready to ship only when the host matrix is green, the
new adapter is the code used by the K1 acceptance run, and that run supplies
the bounded integration receipt described above.
