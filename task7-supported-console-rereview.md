# Task 7 supported physical-console re-review — fix round 1

Reviewed the appended implementation report and the current working bytes for
the original task paths, the scoped `session.py` window-producer hunk, and the
expanded host test. HEAD remains
`ca329e52dd27d1a3f5a56748d93c8ab0fd7f24f2`; the review concerns the interleaved
uncommitted package only.

No game or broad suite was run. I used two focused Python probes to settle
specific doubts: one proved `FrozenDict` can still be mutated with `|=` and
`dict.__setitem__`; the other proved a structurally identical `expect_values`
list now fails because the frozen outcome stores `values` as a tuple.
`git diff --check` on the scoped paths passed.

## Verdicts

**Spec Compliance: FAIL.** Nine prior findings are addressed. I1, I5, and M1
remain open, and the immutability fix introduces one new Important typed-result
regression. The mandatory installed-candidate K1 acceptance receipt also
remains outstanding and is not inferred from host code or reported tests.

**Task Quality: NOT READY.** The exact correlation and owned-window structure
is materially stronger, but the host oracle still does not assert complete
timeout/input-failure transcripts, evidence can still be made vacuous with an
empty substring, and `expect_values` is now unusable for matching TOML lists.

## Prior-finding checklist

### C1 — ADDRESSED: exact owned-display identity

**Evidence:** `scripts/harness/kpharness/owned_x11.py:19-20,41-62`

`DISPLAY` is parsed as local `:N` or `:N.S`, and the parsed display number must
equal the integer `session.display`. The former `startswith()` escape is gone;
`:97` no longer satisfies display 9, nor `:970` display 97. The focused display
probe from the prior review is covered by the new implementation and fixtures.

### I1 — NOT ADDRESSED: required result evidence can still be vacuous

**Evidence:** `scripts/harness/kpharness/console_steps.py:54-71` and
`scripts/harness/kpharness/physical_console.py:218-232`

The important kind separation is fixed: the driver now requires exact-request
`input` and `result` rows and searches their text separately. The scenario
layer also rejects an empty evidence container. It does not reject empty
elements. `contains = [""]` and `input_contains = [""]` pass the `not
result_evidence` / `not input_evidence` checks, and every string contains the
empty substring, so the later `missing` list is empty regardless of output
text. That still permits success without meaningful expected input/result
evidence.

Require bounded, non-empty strings for every evidence item after parsing and
before invoking the driver. Add cases for `[]`, `[""]`, mixed empty/non-empty,
and non-string values.

### I2 — ADDRESSED: post-baseline failures retain typed diagnostics

**Evidence:** `scripts/harness/kpharness/physical_console.py:65-72,
120-136,258-284`

The driver records the last response, preserves the baseline, and normalizes
post-baseline protocol parsing and input-port exceptions into
`PhysicalConsoleFailure`. Focus/F12/select/type/Enter failures and malformed
status/outcome/output responses now retain baseline and last observation.

### I3 — ADDRESSED: submitted regression refuses immediately

**Evidence:** `scripts/harness/kpharness/physical_console.py:148-167`

The driver explicitly compares current submitted against the baseline and
raises `SubmittedRegression` before any outcome/output lookup.

### I4 — ADDRESSED: public IDs remain canonical strings

**Evidence:** `scripts/harness/kpharness/console_protocol.py:32-46,70-83,
106-115` and `scripts/harness/kpharness/physical_console.py:57-62,148-172`

`canonical_u64` validates while returning the original string;
`ConsoleIdentity` and receipt request fields are strings. Integer conversion is
limited to checked arithmetic/comparison, including uint64 overflow refusal.

### I5 — NOT ADDRESSED: the host oracle still omits complete transcripts

**Evidence:** `tools/kpharness_physical_console_test.py:234-250,314-333`

The clean, already-open, regression, and most non-timeout failure paths now
assert exact protocol-call lists. The helper explicitly skips exact transcript
comparison for both `SubmissionTimeout` and `OutcomeTimeout` at lines 249-250,
even though timeout/replay behavior is one of the proof gate's required full
transcripts. The input-failure matrix checks failure type and metadata but does
not assert the exact protocol or input transcript for any failure point. Its
line 333 assertion always expects zero Enter records on both sides of the
conditional and checks none of the preceding input ordering.

Use declared expected protocol and input sequences for every case, including a
deterministic exact number of timeout polls. Assert no unconsumed scripted
response and no additional call after the expected terminal event.

### I6 — ADDRESSED: checked-in owned-window producer exists and is used

**Evidence:** `scripts/harness/kpharness/session.py:457-460,1056-1117` and
`scripts/harness/kpharness/owned_x11.py:41-62`

`GameSession` now owns a per-session captured window and PID. Discovery refuses
a missing/dead owned X server, requires the exact session display, restricts
visible candidates to live game/launcher PIDs, requires one candidate, and
revalidates cached PID/geometry. `OwnedX11Input.from_session()` invokes this
producer before accepting the target. Actual XTEST/game-window behavior remains
for the required live acceptance run.

### I7 — ADDRESSED: `advance_ticks` validates progress and reset

**Evidence:** `scripts/harness/kpharness/console_steps.py:112-135`

Ticks must now be a non-bool integer in 1..100000, and an observed counter below
the starting value fails immediately as a reset.

### I8 — ADDRESSED: identity is rechecked before edit input

**Evidence:** `scripts/harness/kpharness/physical_console.py:263-277`

After focusing and any F12-open wait, the driver performs a runtime-bound
status read, verifies `open=true`, and only then sends select/type/Enter. This
covers both initially closed and initially open routes.

### M1 — NOT ADDRESSED: the receipt remains mutable

**Evidence:** `scripts/harness/kpharness/physical_console.py:42-54`

`FrozenDict` blocks several ordinary methods but remains a `dict` subclass and
does not block `__ior__`. A focused probe successfully mutated it with
`x |= {"b": 2}`. A second probe successfully mutated it via
`dict.__setitem__(x, "b", 2)`. The added test covers indexed assignment only,
so the advertised deep immutability is not established.

Use a non-`dict` immutable `Mapping` implementation or preserve a canonical
serialized receipt as immutable bytes. Test every exposed mutation surface
that the chosen type supports; do not claim immutable evidence from a mutable
built-in subclass.

### M2 — ADDRESSED: F12 polling is runtime-bound

**Evidence:** `scripts/harness/kpharness/console_protocol.py:137-154` and
`scripts/harness/kpharness/console_steps.py:97-102`

`ConsoleClient.wait_open` now calls status with the captured runtime, and the
scenario action uses `PhysicalConsoleDriver.open_overlay`, whose post-baseline
polls are also runtime-bound.

### M3 — ADDRESSED: malformed `keys_before_submit` refuses

**Evidence:** `scripts/harness/kpharness/owned_x11.py:141-153`

Strings and non-list/tuple inputs now refuse; the array is bounded to 64
non-empty strings before constructing the immutable entry wrapper.

## New Important finding introduced by fix round 1

### N1. Freezing successful outcome lists makes matching `expect_values` fail

**Evidence:** `scripts/harness/kpharness/physical_console.py:49-54,183-190`
and `scripts/harness/kpharness/console_steps.py:39-44,68-72`

`_freeze` converts every protocol list into a tuple. The successful outcome is
frozen before it reaches `_expect_values`, while TOML `expect_values` remains a
list. Python sequence equality is type-sensitive here: a tuple of matching
typed-value mappings is not equal to the equivalent list. The focused probe
constructed identical expected/outcome values and reproduced
`ConsoleStepError: typed console returns do not match expect_values`.

This breaks the required typed-result assertion path for every otherwise
correct `expect_values` scenario. Normalize both sides to the same immutable
structural representation before comparison, while preserving type distinctions
inside each typed value. Add a scenario-layer test that passes matching
nil/false/number values and rejects one changed typed value.

## No new Critical findings

No new Critical breakage was found in the scoped fix-round changes. The owned
display prefix escape is closed, and no direct submit/Lua/exec/replay path was
introduced.

## Required disposition

Do not accept the slice yet. Fix I1, I5, M1, and N1; rerun the focused host
Python/CTest gates; then complete the separate owned K1 installed-candidate
acceptance receipt before any shipment claim.
