# Task 7 supported physical-console re-review — fix round 2

Reviewed only the round-2 report and current bytes bearing on I1, I5, M1, and
N1, plus the narrow tests for those fixes. HEAD is
`ca329e52dd27d1a3f5a56748d93c8ab0fd7f24f2`; the package remains interleaved
and uncommitted.

No game or broad suite was run. `git diff --check` on the scoped task paths
passed. Three focused probes confirmed evidence refusal and typed-value
matching, confirmed that the replacement receipt mapping refuses both `|=` and
`dict.__setitem__`, and exposed one new structured-receipt serialization bug.

## Verdicts

**Spec Compliance: FAIL.** I1, I5, M1, and N1 are all addressed, but round 2
introduces one new Important defect: successful receipt line objects are
serialized as Python object-description strings rather than structured JSON.
The separate installed-candidate K1 acceptance receipt also remains pending.

**Task Quality: NOT READY.** The four requested fixes are sound in memory and
the expanded transcript assertions are materially stronger. The on-disk
success receipt currently destroys the structure of the exact-request output
lines, so the delivered diagnostic/evidence artifact is not acceptable yet.

## Remaining-finding checklist

### I1 — ADDRESSED: input and result evidence is non-vacuous

**Evidence:** `scripts/harness/kpharness/console_steps.py:64-90` and
`tools/kpharness_physical_console_test.py:432-438`

`_evidence_strings` now accepts only one to 64 non-empty strings, each at most
8192 characters. Empty containers, empty or mixed-empty strings, non-string
members, and malformed containers refuse before the physical driver runs. A
focused probe confirmed `[]`, `[""]`, `["ok", ""]`, and `[42]` all refuse.
The driver still requires separately tagged exact-request `input` and `result`
rows.

### I5 — ADDRESSED: deterministic cases assert complete transcripts

**Evidence:** `tools/kpharness_physical_console_test.py:235-257,
320-354`

The common failure helper now builds and compares the exact protocol transcript
for submission and outcome timeouts, including every deterministic poll, and
compares the complete keyboard transcript. The post-baseline input-failure
matrix now declares and checks the exact protocol and keyboard prefix for
focus, F12, select-all, type, and Enter failures. No timeout or input-failure
path retains the former transcript-comparison exemption.

### M1 — ADDRESSED: receipt mappings are no longer mutable dictionaries

**Evidence:** `scripts/harness/kpharness/physical_console.py:44-84` and
`tools/kpharness_physical_console_test.py:409-430`

`FrozenMapping` implements `Mapping` rather than subclassing `dict`, stores a
private `MappingProxyType`, blocks mutation methods including in-place union,
and is applied recursively with tuples for sequences. Focused probes confirmed
that `|=` raises the intended immutability `TypeError` and
`dict.__setitem__` rejects the non-dict object. The tests cover both top-level
and nested receipt mappings.

### N1 — ADDRESSED: frozen typed values compare structurally

**Evidence:** `scripts/harness/kpharness/console_steps.py:41-61` and
`tools/kpharness_physical_console_test.py:440-459`

`_typed_value_equal` now recursively compares mapping keys/values and treats
list/tuple sequences as equivalent containers while requiring identical scalar
types. A focused probe confirmed that a TOML-style list of typed values matches
the frozen tuple representation. The new test covers matching nil/false/number
values, a changed-value refusal, and the exact protocol/keyboard transcript.

## New Important finding introduced by fix round 2

### R2-I1. Successful output lines are stringified in the JSON receipt

**Evidence:** `scripts/harness/kpharness/physical_console.py:78-84` and
`scripts/harness/kpharness/console_steps.py:25-34,95-99`

`thaw_receipt` recursively converts mappings and tuples but has no branch for
ordinary lists. `_console_command` constructs the success body with
`"lines": list(receipt.lines)`. The outer body mapping is thawed, but this
ordinary list is returned unchanged, leaving each element as a non-serializable
`FrozenMapping`. Because `_receipt` calls `json.dumps(..., default=str)`, every
line becomes a Python object-description string rather than a JSON object.

The focused probe produced this exact shape:

```json
{"lines": ["<kpharness.physical_console.FrozenMapping object at 0x...>"]}
```

This destroys the session, request, sequence, kind, and text evidence in the
retained success receipt even though the in-memory receipt was correct. Extend
`thaw_receipt` to recurse through both lists and tuples, or pass
`receipt.lines` without first wrapping it in a list. Remove `default=str` for
protocol evidence so an unhandled container fails loudly rather than silently
corrupting the receipt. Add a test that reads the written JSON and asserts each
line is an object with the exact identity and byte-object fields.

## New-breakage scan

No new Critical breakage was found. No direct submit/Lua/exec/replay path,
identity fallback, or receipt mutability escape was introduced by this round.

## Required disposition

Fix R2-I1 and verify the written success receipt structurally. After that, this
host slice can proceed to its separate owned K1 installed-candidate acceptance
gate; no shipment claim is supported before that live receipt exists.
