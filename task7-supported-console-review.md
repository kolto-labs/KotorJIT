# Task 7 supported physical-console review

Reviewed the exact requested package against the current bytes at HEAD
`ca329e52dd27d1a3f5a56748d93c8ab0fd7f24f2` in the interleaved
`codex/lua-boundary-validation` worktree:

- `scripts/harness/kpharness/console_protocol.py`
- `scripts/harness/kpharness/physical_console.py`
- `scripts/harness/kpharness/owned_x11.py`
- `scripts/harness/kpharness/console_steps.py`
- only the task delegation hunk in `scripts/harness/kpharness/scenario.py`
- `tools/kpharness_physical_console_test.py`
- only the `kpharness_physical_console_test` registration in `CMakeLists.txt`

The pre-existing scenario cancellation hunks and unrelated CMake changes are
excluded. No game was run. I did not rerun the reported suites. I ran two
focused probes: one demonstrated that a session claiming display `9` accepts
`DISPLAY=:97`, and one confirmed that checked-in `kpharness` code never assigns
the `capture_window` attribute required by the new adapter.

## Verdicts

**Spec Compliance: FAIL.** The implementation satisfies much of the exact
request-correlation algorithm, but violates the owned-window safety boundary,
does not require distinct input and result output evidence, does not preserve a
typed baseline/last-observation failure for every post-baseline refusal, and
does not keep protocol identifiers as canonical decimal strings. The required
installed-candidate K1 acceptance receipt is also still outstanding, as the
implementation report acknowledges.

**Task Quality: NOT READY.** The decomposition is promising: the physical
driver has no submit/Lua/exec operation, uses exactly one Enter, binds outcome
and output to the captured identity, refuses duplicate/high-watermark
promotion, and keeps Linux input separate from protocol polling. The current
host test is useful but not yet the load-bearing oracle required by the proof
gate, and the supported ScenarioRunner path has no checked-in producer for its
required verified window identity.

## Critical findings

### C1. The owned-display guard can accept a different X server

**Evidence:** `scripts/harness/kpharness/owned_x11.py:55-58`

```python
expected_display = getattr(session, "display", None)
if isinstance(expected_display, int) and not display.startswith(f":{expected_display}"):
    raise OwnedInputError(...)
```

The prefix comparison is not an identity comparison. `DISPLAY=:97` passes for
`session.display == 9`; the focused probe constructed exactly that session and
`OwnedX11Input.from_session()` returned a usable target. The subsequent
`xdotool` commands therefore run against `:97`, despite the alleged owned
server belonging to display 9. This defeats the adapter's central safeguard and
can send focus, typing, clicks, or key-up/down operations to a different X
server.

Parse `DISPLAY` as an X display identifier and require its display number to
equal `session.display` exactly, allowing only a separately parsed screen
suffix such as `.0`. Add positive `:97`/97 and negative `:97`/9, `:970`/97,
missing-owner, dead-owner, and reused-display fixtures.

## Important findings

### I1. A console command can succeed without result-output evidence

**Evidence:** `scripts/harness/kpharness/console_steps.py:54-70` and
`scripts/harness/kpharness/physical_console.py:197-207`

`console_command` defaults `input_contains` to the source but defaults
`contains` to an empty sequence. The driver concatenates every matching row's
text and checks undifferentiated substrings; it does not require one `kind=input`
row and one `kind=result` row. Thus a Succeeded outcome plus only the echoed
input row passes by default. A requested result marker can also be satisfied by
the source echo itself when that marker occurs in the command text.

The host fixture hides this because both of its rows are labelled `result`
(`tools/kpharness_physical_console_test.py:92-108`), so it does not prove the
native `input`/`result` distinction. Require and decode the native line kinds,
require source evidence from an exact-request `input` row, and require result
evidence from an exact-request `result` row (or the explicitly expected error
kind when testing a failure). Make result evidence mandatory for the scenario
action.

### I2. Post-baseline input and parse failures lose the required typed diagnostic identity

**Evidence:** `scripts/harness/kpharness/physical_console.py:108-120,
209-224` and `scripts/harness/kpharness/console_steps.py:77-84`

After capturing a baseline, `focus_owned_game_window`, `press_f12`,
`select_all`, `type_text`, and `press_enter` can raise `OwnedInputError`
directly. `_require_protocol`, `_identity`, `_u64`, and `display_text` can raise
bare `ConsoleProtocolError` after the baseline exists. None is normalized into
`PhysicalConsoleFailure`, so `baseline` and `last` are absent. The scenario
failure receipt then records both as `null`, contrary to the proof gate's rule
that every non-success retain the pre-input identity and last observation.

Wrap every post-baseline boundary in a single typed failure conversion that
preserves the captured identity, phase-specific code, and last protocol
response. Add focused failures for focus/F12/type/Enter errors and malformed
status/outcome/output/byte-object responses.

### I3. A submitted-counter regression is polled until timeout instead of refused

**Evidence:** `scripts/harness/kpharness/physical_console.py:132-146`

The driver accepts `candidate`, rejects values above it as duplicates, and
treats every lower value alike. If the baseline is 40 and a later status says
39, the algorithm sleeps and eventually raises `SubmissionTimeout`. The proof
gate explicitly requires a counter regression to fail, because it is evidence
of an invalid observation rather than ordinary non-arrival.

Add a distinct typed regression/identity failure as soon as
`current.submitted < baseline.submitted`, and add a transcript fixture proving
there is no outcome lookup or replay.

### I4. Numeric protocol identities are converted to integers and exposed that way

**Evidence:** `scripts/harness/kpharness/console_protocol.py:32-40,
100-109`, `scripts/harness/kpharness/physical_console.py:43-48,91-98,
132-152`

The wire validator returns `int`, `ConsoleIdentity` stores those integers, the
candidate is computed as an integer, and `PhysicalConsoleReceipt.request` is an
integer. The driver later reconstructs strings with `str(...)`. This does not
currently lose precision in Python, but it violates the explicit public
contract that IDs/counters remain canonical unsigned64 decimal strings and
makes the receipt use a different representation from the wire identity it is
supposed to preserve.

Validate canonical strings without replacing them, use a bounded integer only
as a private checked arithmetic intermediate for `submitted + 1`, and return
the canonical candidate string. Assert exact string identities, including
values above 2^53 and the uint64 boundary.

### I5. The host oracle does not assert the complete wire transcript

**Evidence:** `tools/kpharness_physical_console_test.py:142-166,
168-199`

The clean case asserts the complete input transcript but only checks that one
specific output call appears somewhere in the protocol calls. Failure cases
mostly assert one Enter, no recorded `submit`, and selected absence/presence
checks. Extra status, wrong or duplicate outcome/output lookups, and lookups in
the wrong order would often leave the tests green. This misses the proof gate's
explicit requirement to consume a declared sequence and assert the whole wire
and input transcript.

The matrix also lacks the counter-regression case, malformed/omitted field
fixtures, post-baseline input-port failures, distinct input/result kinds, and a
receipt immutability check. Make the scripted protocol consume exact expected
calls and fail on any unexpected call or unconsumed response; then assert the
entire transcript per case.

### I6. The supported scenario route has no checked-in source for `capture_window`

**Evidence:** `scripts/harness/kpharness/owned_x11.py:41-58` and
`scripts/harness/kpharness/scenario.py:594-602`

The new public scenario verbs construct `OwnedX11Input` from the runner
session, and the adapter refuses unless `session.capture_window` already
exists. A bounded search of checked-in `scripts/harness/kpharness` found no
assignment to that attribute. The only discovered producer is the read-only
private GPU prototype, which assigns it dynamically after an ad hoc `xwininfo`
scan. Consequently the checked-in normal ScenarioRunner/GameSession path
cannot execute `console_command` or `owned_input` without an external caller
recreating the private assumption.

Integrate bounded game-window discovery/verification into the owned display
lifecycle, store the per-session verified identity, and fail if that window is
lost or replaced. The live acceptance must exercise this checked-in producer,
not monkey-patch the attribute from the prototype.

### I7. `advance_ticks` can report success without any tick advance

**Evidence:** `scripts/harness/kpharness/console_steps.py:111-128`

The implementation converts `ticks` with `int()` but applies no positive or
upper bound and does not reject a tick reset. `ticks = 0` or a negative value
returns on the first state read, producing a false predicate success; a reset
becomes a timeout instead of a distinct failure. The established creative
helper contract is 1..100000 ticks and explicitly refuses reset.

Validate integer type/range before reading state, compute a checked target, and
fail immediately when the observed clock regresses. Add host tests for zero,
negative, oversized, reset, and successful progress cases.

### I8. The already-open path performs keyboard mutation without a retained identity recheck

**Evidence:** `scripts/harness/kpharness/physical_console.py:213-221`

When the baseline says `open=true`, the driver focuses the window and proceeds
directly to select/type/Enter. It does not re-read `status(runtime=baseline)`
between focus and mutation. A reset, replacement, or close during that window
can therefore receive the physical input before the later submission poll
detects the changed identity. The proof gate requires the already-open path to
retain the same identity check.

Recheck exact runtime/session/open state after focus for both branches and
immediately before the edit sequence. A mismatch must refuse before select,
type, or Enter.

## Minor findings

### M1. The advertised immutable receipt is only shallowly frozen

**Evidence:** `scripts/harness/kpharness/physical_console.py:43-48`

The dataclass prevents attribute reassignment, but `outcome` and each `lines`
element are mutable dictionaries supplied by the protocol. A caller can alter
the evidence after success. Deep-copy and freeze the nested protocol data, or
serialize immutable receipt bytes at construction.

### M2. `console_open` polls discovery status instead of the captured runtime

**Evidence:** `scripts/harness/kpharness/console_protocol.py:131-147`

`wait_open` calls `capture()`, which issues status without the baseline runtime.
It compares the returned nonce afterward, so it usually detects replacement,
but it does not follow the versioned protocol rule that every post-discovery
status observation carries the captured runtime and allows the service to
return `StaleRuntime` directly. Use `status(baseline.runtime)` while preserving
the raw response needed for `open` and diagnostics.

### M3. A string `keys_before_submit` is split into one key per character

**Evidence:** `scripts/harness/kpharness/owned_x11.py:137-145`

`tuple(str(key) for key in keys_before_submit)` silently converts a mistaken
string such as `"ctrl+Up"` into eight separate key operations. Reject strings
and require a bounded list/tuple of non-empty key names.

## Positive findings and coverage limits

- `PhysicalConsoleDriver` has no wire `submit`, Lua, exec, or replay method.
- The clean physical path sends one Enter and computes only baseline submitted
  plus one; it never reads `completed`.
- Duplicate, stale runtime/session, expired/unavailable outcome, failed,
  cancelled, dropped-output, foreign-output, and timeout branches exist and do
  not promote a later request.
- Output filtering uses both session and request, and `dropped_through` is
  checked before output is accepted.
- Linux-only refusal and separation between the protocol, input, and clock
  ports are present.
- The CMake addition correctly registers the host test as `offline;harness`;
  no issue was found in that isolated hunk.
- No live K1, DirectInput delta, installed artifact/source hash, actual F12
  open, or exact live request/output receipt was reviewed. Those remain a
  mandatory separate acceptance gate and cannot be inferred from the host
  tests or the private earlier happy-path receipt.

## Required disposition

Do not accept or ship this slice yet. Fix C1 and I1-I8, strengthen the host
oracle so it would reject those defects, rerun the focused Python/CTest gates,
and then perform the proof-gate's single owned K1 installed-candidate run using
the checked-in window producer and extracted adapter. M1-M3 should be resolved
before treating the boundary as a stable supported API.
