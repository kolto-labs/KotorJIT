# Task 7 supported-console extraction report

## Scope and result

Implemented the supported host-side physical-console boundary without running a
game.  The production path is a one-shot `PhysicalConsoleDriver`: it captures
the `kp.console.v1` runtime/session/submitted/last-line baseline before input,
focuses only a verified owned Linux X11 game window, opens F12 when necessary,
and sends exactly one physical Enter.  It then accepts only the exact
`(runtime, session, submitted + 1)` request's `Succeeded` outcome and its
undropped, session/request-filtered output.

`completed` is not consulted by production code.  There is no submit/Lua/exec
or replay operation on the physical boundary.  Failures retain a typed code,
the pre-input identity, and the last protocol response for a scenario receipt.

## Owned changed paths

* `scripts/harness/kpharness/console_protocol.py` -- canonical unsigned64 and
  lossless byte-object decoding plus strict versioned-response helpers.
* `scripts/harness/kpharness/physical_console.py` -- narrow protocol/input/
  clock ports, immutable successful receipt, typed failure receipt, production
  `ChannelConsoleProtocolPort`, and exact one-entry correlation.
* `scripts/harness/kpharness/owned_x11.py` -- Linux-only owned-X11 input
  adapter.  It refuses a missing/dead owned display, invalid/unverified window,
  and non-Linux platform.  Per-command immutable wrappers preserve Ctrl+Enter
  multiline editing, history/completion keys, suffix typing, and one Enter.
* `scripts/harness/kpharness/console_steps.py` -- scenario actions
  `console_open`, `console_command`, `owned_input`, and `advance_ticks`;
  physical command receipts and failure diagnostics are written under the run
  directory.  Keyboard/window ownership is separate from protocol semantics.
* `scripts/harness/kpharness/scenario.py` -- one narrow delegation branch for
  the four console actions.  Existing cancellation edits were present before
  this task and were preserved.
* `tools/kpharness_physical_console_test.py` -- deterministic injected-port
  matrix with no game, Wine, display, or Lua evaluator.
* `CMakeLists.txt` -- registers the new host test in the existing
  `offline;harness` CTest loop.  Other CMake changes were already interleaved
  and were not modified by this task.

## Host proof matrix

The new test verifies the complete acceptance/refusal matrix from the proof
gate:

* Clean closed and already-open physical routes: immutable receipt `A/7/41`,
  exactly one Enter, correct F12 behavior, typed nil/false/number result data,
  and filtered input/result output.
* Stale runtime; status-session reset and exact-outcome stale session.
* Duplicate/interleaved submission while the deliberately misleading legacy
  completed watermark is `999`.
* Exact `Expired` and `Unavailable` lookup failures despite that watermark.
* Exact `Failed` (including structured `lua_runtime` error) and `Cancelled`.
* Dropped cursor, missing output, and readable but foreign session/request
  output.
* Submission and pending-outcome timeouts, each proving no second Enter/replay.
* Ctrl+Enter multiline/history/completion/suffix editing remains inside one
  entry phase, and non-Linux input reports explicit unsupported behavior.

The fake protocol exposes only status, outcome, and output.  Tests assert its
whole transcript and fail if a submit operation appears, so a direct wire
submission fallback cannot satisfy this suite.

## Validation run

Commands and results:

```text
python3 tools/kpharness_physical_console_test.py
11 tests passed

cmake -S . -B /tmp/kphaser-task7.4XCbSv -G Ninja
ctest --test-dir /tmp/kphaser-task7.4XCbSv -R '^kpharness_physical_console_test$' --output-on-failure
1/1 test passed (offline;harness)

python3 tools/kpharness_offline_test.py
150 tests passed

python3 -m py_compile scripts/harness/kpharness/console_protocol.py \
  scripts/harness/kpharness/physical_console.py \
  scripts/harness/kpharness/owned_x11.py \
  scripts/harness/kpharness/console_steps.py \
  scripts/harness/kpharness/scenario.py \
  tools/kpharness_physical_console_test.py
passed

git diff --check
passed
```

## Concerns and remaining acceptance

No K1 process was launched, as required.  The host proof demonstrates the
Python boundary's exact identity/refusal behavior; it does not prove that a
given installed candidate's window discovery has supplied `session.capture_window`
or that XTEST reaches the live F12 overlay.  A separate owned K1 acceptance
must provide the captured source/deployed hashes, owned-window identity,
baseline/post-input wire transcript, supporting DirectInput-call delta,
actual `open=true`, exactly one submitted increment, exact successful outcome,
and undropped session/request-filtered source/result rows.  Mac and reused or
unowned desktop input remain explicitly unsupported.

## Review fix round 1/5

Addressed every Critical, Important, and Minor finding from the independent
supported-console review without launching a game.

* `OwnedX11Input` now parses only local `:N` or `:N.S` DISPLAY identities and
  requires the parsed number to exactly equal the session display.  Prefixes
  such as `:97` for display 9 and `:970` for display 97 refuse.
* `GameSession.capture_owned_game_window()` is the checked-in producer used by
  the input adapter.  It runs only against the session's live Xvfb, validates
  the exact display, finds visible windows only by known game/launcher PID,
  requires exactly one candidate, and revalidates its PID/geometry on every
  reuse.  Reused displays, lost windows, and replacement windows refuse.
* The physical driver now records public IDs as canonical decimal strings;
  private integer conversion is limited to checked comparison and `+1`.
  Successful nested receipts are deeply immutable JSON-compatible mappings.
* Post-baseline input and protocol failures are normalized to
  `PhysicalConsoleFailure` with a baseline and last immutable observation.
  Submitted-counter regression fails immediately, and focus is followed by a
  runtime/session/open recheck before any edit operation.
* Successful console commands require separately tagged exact-request
  `input` and `result` lines.  Input/source and result assertion evidence are
  both mandatory.  `keys_before_submit` rejects strings and malformed lists.
* `console_open` now uses the runtime-bound physical boundary; its post-
  baseline failures retain the same diagnostics.  `advance_ticks` requires an
  integer in 1..100000 and detects a clock reset.
* The fake protocol now asserts complete deterministic call transcripts for
  normal and refusal paths and adds malformed status/outcome/output,
  input-port failure, counter regression, canonical high-ID/uint64, receipt
  immutability, exact display, owned-window producer/replacement, distinct
  line-kind, and tick validation cases.

Exact fix-round validation commands and results:

```text
python3 tools/kpharness_physical_console_test.py
19 tests passed

cmake -S . -B /tmp/kphaser-task7.4XCbSv -G Ninja
ctest --test-dir /tmp/kphaser-task7.4XCbSv -R '^kpharness_physical_console_test$' --output-on-failure
1/1 test passed (offline;harness)

python3 tools/kpharness_offline_test.py
150 tests passed

python3 -m py_compile scripts/harness/kpharness/console_protocol.py \
  scripts/harness/kpharness/physical_console.py \
  scripts/harness/kpharness/owned_x11.py \
  scripts/harness/kpharness/console_steps.py \
  scripts/harness/kpharness/session.py \
  tools/kpharness_physical_console_test.py
passed

git diff --check
passed
```

## Review fix round 2/5

Addressed I1, I5, M1, and N1 from the independent re-review without launching
a game, staging, or committing.

* `input_contains` and `contains` now each require one to 64 non-empty string
  values (each at most 8192 characters). Empty arrays, empty strings, mixed
  empty values, non-string values, and malformed containers fail before the
  physical driver is invoked.
* The host oracle now asserts the complete protocol and keyboard transcript for
  every deterministic terminal path. This includes all three submission and
  outcome timeout polls and each individual focus, F12, select-all, type, and
  Enter failure prefix.
* Receipt mappings are now non-`dict` immutable mappings, recursively paired
  with immutable tuples. Both mapping union assignment and `dict.__setitem__`
  refuse for the top-level and nested evidence. Receipt writing explicitly
  materializes a JSON-safe copy only at the file boundary.
* Typed-return comparison recursively compares mappings and list/tuple
  sequences while preserving scalar types. TOML `expect_values` lists now match
  frozen nil/false/number outcomes, while a changed typed value still refuses.

Focused regression assertions cover every added boundary above. Exact
fix-round-2 validation commands and results:

```text
python3 tools/kpharness_physical_console_test.py
21 tests passed

ctest --test-dir /tmp/kphaser-task7.4XCbSv -R '^kpharness_physical_console_test$' --output-on-failure
1/1 test passed (offline; harness)

python3 tools/kpharness_offline_test.py
150 tests passed

python3 -m py_compile scripts/harness/kpharness/console_protocol.py \
  scripts/harness/kpharness/physical_console.py \
  scripts/harness/kpharness/owned_x11.py \
  scripts/harness/kpharness/console_steps.py \
  scripts/harness/kpharness/session.py \
  scripts/harness/kpharness/scenario.py \
  tools/kpharness_physical_console_test.py
passed

git diff --check
passed
```

## Review fix round 3/5

Addressed R2-I1 only, without launching a game, staging, or committing.

* `thaw_receipt` now recursively converts both lists and tuples, including a
  scenario receipt's list of immutable exact-request line mappings.
* Receipt JSON no longer uses `default=str`; unsupported data now fails at the
  serialization boundary instead of silently replacing protocol evidence with
  an object representation string.
* The new host regression invokes the scenario `console_command` path, parses
  the emitted success receipt, and verifies both lines are JSON objects with
  the exact `session`, `request`, and `sequence` identity plus nested base64
  `kind` and `text` byte objects.

Exact fix-round-3 validation commands and results:

```text
python3 tools/kpharness_physical_console_test.py
22 tests passed

ctest --test-dir /tmp/kphaser-task7.4XCbSv -R '^kpharness_physical_console_test$' --output-on-failure
1/1 test passed (offline; harness)

python3 tools/kpharness_offline_test.py
150 tests passed

python3 -m py_compile scripts/harness/kpharness/console_protocol.py \
  scripts/harness/kpharness/physical_console.py \
  scripts/harness/kpharness/owned_x11.py \
  scripts/harness/kpharness/console_steps.py \
  scripts/harness/kpharness/session.py \
  scripts/harness/kpharness/scenario.py \
  tools/kpharness_physical_console_test.py
passed

git diff --check
passed
```
