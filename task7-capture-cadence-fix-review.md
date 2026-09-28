# Task 7 capture-cadence fix review

Date: 2026-09-27

Worktree reviewed: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`

Specification: `/home/brunner56/kp-live-20260922/task7-capture-cadence-fix-brief.md`

Scope: `scripts/harness/kpharness/recording.py`, `scripts/harness/kpharness/display_backends.py`, `scripts/harness/kpharness/creative.py`, `scripts/harness/kpharness/creative_wine.py`, `tools/kpharness_creative_test.py`, `tools/kpharness_gamescope_backend_test.py`, and `docs/creative-runner.md`, including the boundary with the previously reviewed post-accept exporter. This review was read-only with respect to the worktree. No real FFmpeg, FFprobe, Gamescope, X11 server, Wine process, or K1 process was launched.

## Verdict

**Specification verdict: FAIL.** The private-root transport change and most fail-closed lifecycle mechanics are present, but the implementation does not yet meet the marker-clock, independent receipt-recomputation, route/capture separation, or typed-startup-evidence requirements.

**Code verdict: CHANGES REQUIRED.** The implementation is not ready for the bounded animated-pattern diagnostic or a K1 acceptance run. The focused mocked suites pass, but adversarial probes show that schema 2 can promote contradictory capture/cadence evidence to acceptance-ready.

## Findings

### Critical

#### 1. Schema-2 recomputation accepts contradictory cadence, marker, progress, and command evidence

`display_backends._cadence_evidence_passed()` (`display_backends.py:270-290`) trusts the serialized cadence status plus three summary numbers. It does not bind the acceptance interval to `capture.markers`, verify marker presence or order, recompute the interval arithmetic from frame/inter-frame/span/slot fields, or compare the acceptance drop value with terminal FFmpeg drops. `_root_capture_matches()` (`display_backends.py:293-330`) checks the required root flags but does not reject timestamp-policy additions such as `-r`, `-vsync`, `-fps_mode`, `fps=`, or `setpts`.

An inert probe started from the suite's otherwise-valid completed schema-2 fixture and changed one primitive at a time. `execution_evidence_ready(..., require_completion=True)` returned `true` for every case below:

- all capture markers absent;
- capture markers serialized in `complete` then `phase_1` order;
- terminal `drop_frames` changed from 0 to 999;
- interval fields changed to two frames over ten seconds with 599 missing slots while leaving the cached effective-FPS/drop summaries green;
- `-r 1` appended to the FFmpeg command.

This directly violates the requirement that schema-2 readiness be recomputed from primitive relationships and reject stale or manually edited booleans, counters, PTS metrics, marker order, and contradictory commands. It also crosses the previously reviewed exporter boundary: `creative_accept` and `creative_export` correctly call `execution_evidence_ready`, but that central gate can currently seal and export a bad receipt if the contradiction exists before visual acceptance. Their post-accept digest checks still prevent later tampering; the defect is in the evidence admitted into the digest.

Required repair: validate marker names, first-occurrence ordering, and acceptance endpoints against `capture.markers`; validate all cadence arithmetic from internally consistent primitive fields (or bind and re-read the retained raw PTS evidence); require terminal/progress duplicate and drop relationships; and reject every forbidden timestamp-rewrite form when recomputing the root command.

#### 2. Gamescope markers are polled at 250 ms but claim 100 ms uncertainty, and shutdown can skip the final marker read

The common marker receipt hardcodes `poll_interval_ms=100` and `uncertainty_ms=100` in `recording.py:303-308`. The Gamescope watcher actually waits `self._watch_interval`, whose default and enforced minimum are 250 ms (`recording.py:361-367`, `recording.py:693-696`). The resulting receipt understates marker uncertainty by 150 ms and can shift either cadence boundary by up to a quarter second while still evaluating a 50 ms maximum-gap gate.

There is also a deterministic finalization race. `X11WindowRecorder.stop()` sets the stop event and joins the watcher before reading final FFmpeg diagnostics (`recording.py:725-747`), but it never performs one final `observe(native_log, now)`. The recorder does not retain the native-log path outside the watcher thread. A complete `complete` line written after the last watcher poll and immediately followed by route return is therefore never observed; cadence reports `capture_markers_incomplete` even though the durable native log contains the required line. Conversely, understated boundary uncertainty can exclude or include a hitch near a marker and make a reported pass stronger than the measured clock supports.

This violates the brief's unchanged 100 ms marker polling, accurate uncertainty, first-complete-line evidence, and final marker completeness requirements. Use a distinct 100 ms marker poll from the 250 ms identity revalidation cadence, record the actual interval used, retain the native-log path, and perform a final complete-line read before freezing markers.

### Important

#### 3. A late capture failure overwrites an already-successful route result

In `creative.py:273-290`, the route runner returns its report, then `session.check_capture()` runs before `route_ok` and the route receipt are recorded. If the route predicates all passed but that final capture check raises, control jumps to the broad `except` and stores `route.status=failed` with a capture error.

That is the exact state the brief requires to preserve independently: `route.status=passed`, capture or cadence failed, retained failure recording, and overall `ok=false`. Record the route result immediately after `runner.run()` returns, then evaluate capture as a separate status. A capture exception must not relabel completed route predicates.

#### 4. FFmpeg process-creation failure has no typed capture failure artifact

`X11WindowRecorder.start()` constructs the capture receipt and calls `_popen()` inside `recording.py:664-671`, but its exception handler only closes the log and re-raises. It does not call `_fail()`, run startup cleanup, or write `capture-failure.json`.

An inert injected `OSError("spawn failed")` probe confirmed `recorder.failure is None` and no `capture-failure.json` exists. Route execution is correctly prevented and no foreign process is touched, but the required stable typed startup evidence is absent. Map process-creation failure to an explicit stable class (the brief's existing `capture_process_exited` class or a separately specified class), set it once, and retain the logs/progress/failure receipt.

#### 5. Marker-interval drop accounting uses whole-capture terminal drops rather than interval deltas

`recording.py:444-454` computes `missing_or_dropped` as the maximum of marker-interval missing slots and the terminal FFmpeg `drop_frames` total. That terminal counter covers the entire recording. A drop before `phase_1` or after `complete` therefore fails the selected marker interval even when the interval itself meets every threshold. The inverse consistency problem appears in finding 1 because schema recomputation ignores the terminal drop total entirely.

The brief calls for FFmpeg dup/drop deltas when progress samples bound an interval. The implementation retains parsed blocks but does not associate them with capture-clock observations, so it cannot compute those deltas. Preserve observation times for progress samples and use bounding deltas when available. If the interval cannot be bounded, mark that diagnostic unavailable or apply a clearly documented whole-run gate without presenting it as the interval's drop ratio.

### Minor

#### 6. Focused tests omit the highest-risk recomputation and shutdown edges

The tests cover root argv construction, non-root coverage refusal, a complete startup fallback warning, basic progress parsing, marker line splitting, PTS gaps, terminal duplicates, teardown order, and several schema mutations. They do not cover terminal drop contradiction, absent/out-of-order serialized markers, inconsistent frame/slot arithmetic, forbidden timestamp flags added to an otherwise-valid command, FFmpeg spawn failure evidence, actual Gamescope marker polling interval, or a final marker appended immediately before stop.

Add these cases as host-only regressions. In particular, build schema mutation tests around `execution_evidence_ready()` itself, because post-accept code relies on that function as the authoritative gate.

## Verified behavior

The following requested behavior is implemented correctly in the reviewed paths:

- Only the Gamescope recorder changes to private-root capture. Its argv uses normalized screen zero, `-draw_mouse 0`, and no `-window_id`; the legacy Xvfb recorder retains its earlier command path.
- Gamescope start revalidates the immutable `OwnedWindow`, lease identity/liveness, root dimensions, and exact window coverage at `0,0` before process creation. Continuous verification retains the single visible PID-owned window invariant through `OwnedWindowVerifier`.
- `:N` and `:N.0` normalize to `:N.0`; malformed and nonzero screen suffixes are rejected.
- Startup admission requires a complete progress block with `frame >= 1`, a regular non-symlink run-local output, a live lease/process, and no forbidden SHM fallback. The overlap scanner detects forbidden tokens split across reads, and the finalization path scans stderr once more after stopping the watcher.
- The progress parser rejects duplicate keys, noncanonical counters, regressions, unknown progress states, and data after a terminal block. Missing terminal diagnostics fail closed.
- Startup failures detected after process creation signal only the owned FFmpeg process, use the required two-second SIGINT/kill waits, retain typed evidence, and allow ordered session teardown.
- Cleanup order remains recorder, game/Wine, display, and earlier cleanup failures stay failed across retries.
- Capture and cadence statuses are separate in the recorder/schema path; a cadence threshold miss does not turn capture green through a cached overall boolean.
- Gamescope automatic representative rendering remains suppressed. The separately reviewed exporter continues to require accepted schema-2 evidence and an unchanged master before it publishes derivatives.
- PipeWire/GStreamer are documented as a separate future adapter and are not silently selected.

## Validation

Safe checks run from the isolated worktree:

```text
python3 tools/kpharness_creative_test.py
29 tests passed

python3 tools/kpharness_gamescope_backend_test.py
52 tests passed

python3 -m py_compile [six scoped Python files]
PASS

git diff --check [reviewed tracked files]
PASS

ad hoc mocked schema/startup probes
PASS as probes; exposed the failures documented above
```

The ad hoc probes used temporary directories and injected process/query doubles. They launched no external capture, display, Wine, or game process and did not modify the worktree.

## Residual proof boundary

After these findings are fixed and the mocked regressions pass, this review still would not establish live private-root acquisition, active MIT-SHM use, actual source cadence, visual framing, or K1 gameplay. The next valid step remains the separately authorized bounded animated-pattern diagnostic described by the brief. A real K1 acceptance run should remain blocked until that diagnostic passes the same root identity, startup, cadence, finalization, and cleanup gates.

---

# Round 1 re-review

Date: 2026-09-27

Implementation report reviewed: `.superpowers/sdd/lua-boundary-validation-plan/ta[REDACTED].md`

The same isolated worktree and scope were reviewed again after the round-1 fixes. This re-review also inspected `creative_accept.py` and `creative_export.py`, including acceptance metadata digests, atomic receipt publication, symlink rejection, and the private stable-copy encoder input. The worktree was not edited, and no real FFmpeg, FFprobe, Gamescope, X11 server, Wine process, Xvfb process, or K1 process was launched.

## Round 1 verdict

**Specification verdict: FAIL.** Round 1 closes several producer-side defects, but schema-2 readiness can still accept and seal explicit capture failure and contradictory cadence evidence.

**Code verdict: CHANGES REQUIRED.** The bounded animated-pattern diagnostic is **not authorized yet**. The remaining Critical findings can produce an accepted receipt whose own evidence says capture failed or whose cadence primitives do not support the claimed pass.

## Prior-finding disposition

- Prior Critical 1, authoritative schema recomputation: **partially fixed, still open**. Marker presence/order, basic frame/slot arithmetic, terminal-copy equality, and forbidden timestamp flags now receive checks. Explicit `capture_gate` failure, terminal duplicate totals, marker clock arithmetic, progress-bound relationships, and maximum-gap validity remain outside recomputation.
- Prior Critical 2, marker polling and final drain: **closed**. Marker polling now has a separate 100 ms schedule, receipts use that interval, byte/sequence order handles markers observed in one poll, and stop drains the native log synchronously.
- Prior Important 3, route/capture separation: **producer behavior fixed, acceptance integration still open**. The route result is preserved and `capture_gate` is separate, but readiness ignores a failed gate.
- Prior Important 4, typed FFmpeg spawn failure: **closed** for `_popen()` failure. A stable `capture_process_exited` record is written and tested.
- Prior Important 5, interval drop accounting: **producer calculation fixed, serialized proof still open**. Progress samples now produce interval deltas, but readiness does not verify that the serialized bounding samples actually surround the marker interval.
- Prior Minor 6, missing regressions: **partially closed**. The round adds strong mutation, marker-drain, spawn, output, acceptance, and stable-copy tests. The remaining cases below lack regressions.

## Remaining findings

### Critical

#### R1-1. A recorded failed capture gate can be accepted and exported

`creative.run_creative()` now correctly preserves a successful route and records a later verification error in `receipt.capture_gate` (`creative.py:274-297`). However, neither `schema2_receipt()` nor `execution_evidence_ready()` consumes that field (`display_backends.py:387-490`).

A direct completed-receipt probe added:

```json
{"capture_gate":{"status":"failed","error":"capture_binding_changed"}}
```

`execution_evidence_ready(..., require_completion=True)` still returned `true`. More importantly, `creative_accept.accept()` published the receipt with `ok=true`, and `verify_acceptance()` returned `true` while the accepted receipt still contained the failed capture gate.

This is not a cached-status issue: it is a contradictory primitive failure that the central gate omits. A transient final verifier timeout or identity error can be recorded at the orchestration boundary, later pre/post-finalization checks can succeed, and the run can become acceptance-ready despite the retained failure.

Required repair: make a capture-gate failure terminal in the recorder itself, or require `capture_gate.status == passed` in schema construction and execution recomputation. Add acceptance and export tests using an otherwise-valid completed receipt with a failed gate.

#### R1-2. Schema-2 cadence recomputation still accepts impossible or unbounded evidence

`_cadence_evidence_passed()` checks more arithmetic than before, but several acceptance-bearing values remain trusted (`display_backends.py:271-340`). Independent mutations of an otherwise-valid completed receipt produced these results:

- setting both terminal duplicate counters to 1 while leaving the bounded interval delta at 0: readiness `true`;
- setting `maximum_gap_seconds` to `-1.0`: readiness `true`;
- changing a marker's `detected_monotonic` from 12.0 to 200.0 while leaving `capture_seconds=2.0` and startup origin 10.0: readiness `true`;
- setting the interval progress bounds to 1.5 through 1.6 for a marker interval 1.0 through 2.0: readiness `true`;
- reversing the interval progress bounds to 3.0 through 0.0: readiness `true`.

The terminal-duplicate case directly violates the brief's `FFmpeg dup_frames == 0` acceptance rule. The gap case can turn a real gap failure green because readiness checks only `maximum_gap_seconds <= threshold`, without requiring a finite positive value or tying it to histogram/PTS evidence. The progress cases show that serialized interval deltas are not proven to bound the marker interval; their start/end times are not checked, and cumulative bounding counters are not serialized for recomputation. The marker case breaks the stated shared-process clock relationship.

Required repair: require total terminal duplicates to be exactly zero; validate every numeric cadence metric as finite and within its legal domain; bind marker capture time to detected monotonic time and startup origin within the declared uncertainty; require progress start at or before the start marker and progress end at or after the end marker; serialize and recompute cumulative bounding counters; and bind maximum gap, histogram, percentiles, and threshold status to primitive PTS evidence rather than accepting a cached maximum.

#### R1-3. An xdotool timeout escapes the continuous watcher without recording terminal failure

`_binding()` and `OwnedWindowVerifier` invoke subprocess queries with timeouts. `_watch_window()` catches `ValueError`, `OSError`, and `RuntimeError`, but not `subprocess.TimeoutExpired`/`subprocess.SubprocessError` (`recording.py:835-870`).

An inert watcher probe injected `subprocess.TimeoutExpired("xdotool", 5)` from the verifier. The exception escaped `_watch_window()` and `recorder.failure` remained `None`. In the real daemon thread this terminates the watcher, ending continuous lease/window/full-root verification without setting `capture_binding_changed` or another typed failure. A later synchronous check can succeed and allow the run to pass.

The brief explicitly makes a query timeout terminal. Catch `subprocess.SubprocessError` in the watcher and map it to the stable binding failure. The stop-time pre/post checks should use the same mapping, and the watcher thread must not be discarded after a timed join unless its termination is proven.

### Important

#### R1-4. Root-command recomputation does not enforce input-option ordering

`_root_capture_matches()` counts the required flags and checks their values, but `_single_flags()` discards their positions (`display_backends.py:259-268,343-383`). A command with `-i :91.0` before `-draw_mouse 0` was accepted by `execution_evidence_ready()`. FFmpeg options are positional; `-draw_mouse` is an x11grab input option and must precede the matching input.

The brief requires the source flags before/around the expected input position, not merely somewhere in the array. Recompute the ordered source segment, require exactly the specified x11grab sequence, and reject source/input options that occur after `-i` or apply to another input.

### Minor

#### R1-5. New regressions do not cover the remaining false-ready states

The direct mutation suite now covers missing/reversed markers, `-r`, a one-sided terminal-drop edit, contradictory frame counts, and a changed interval drop delta. It does not cover:

- failed `capture_gate` through readiness, acceptance, and export;
- consistent edits to both terminal duplicate copies;
- negative, NaN, or contradictory maximum-gap/histogram values;
- marker `detected_monotonic` versus `capture_seconds` and startup origin;
- progress bounds that fail to surround the acceptance interval;
- xdotool `TimeoutExpired` in the background watcher;
- source-option ordering around `-i`.

Add these as direct `execution_evidence_ready()` and lifecycle regressions.

## Acceptance and export re-review

The new post-accept hardening is correct within its intended boundary:

- `acceptance_receipt_sha256` binds status, reviewer, aware UTC time, media digest, execution digest, and review scope. Independent edits to reviewer, time, or scope invalidate verification.
- Acceptance reads and publishes only bounded regular non-symlink receipt files. Publication uses an unpredictable exclusive same-directory temporary file, file fsync, atomic replacement, directory fsync, and a byte-for-byte regular-file reopen check.
- Export rejects receipt symlinks, opens the master with `O_NOFOLLOW`, copies from the opened descriptor into a private staging file, fsyncs and hashes that stable copy, and passes only that copy to both encoders.
- Public-master swap/restore during rendering cannot alter encoder input. Provenance is still re-read before and after rendering, and failed exports publish no sidecar.
- Gamescope still creates no automatic representative derivative before acceptance, and legacy Xvfb rendering behavior remains covered by the creative suite.

These controls prevent post-accept metadata tampering, receipt-symlink publication, and encoder input swapping. They cannot compensate for a central execution gate that admits contradictory pre-accept evidence, which is why R1-1 and R1-2 remain Critical.

## Round 1 validation

```text
python3 tools/kpharness_creative_test.py
30 tests passed

python3 tools/kpharness_gamescope_backend_test.py
63 tests passed

python3 tools/kpharness_gamescope_boot_repair_test.py
41 tests passed

python3 -m py_compile [eight scoped Python files]
PASS

git diff --check [scoped tracked files]
PASS

ad hoc readiness, acceptance, command-order, and watcher-timeout probes
PASS as probes; reproduced R1-1 through R1-4
```

## Diagnostic authorization

**NOT AUTHORIZED.** Do not launch the animated-pattern diagnostic or K1 through this acceptance path yet. Round 1 materially improves the implementation, but an explicit capture verification failure can still be accepted and the cadence gate can still be made green by contradictory serialized evidence. Fix R1-1 through R1-4, add the listed regressions, rerun this static/mock review, and only then reconsider the separately serialized animated-pattern diagnostic. K1 must remain later than that diagnostic.

---

# Round 2 re-review

Date: 2026-09-27

Implementation report reviewed: `.superpowers/sdd/lua-boundary-validation-plan/ta[REDACTED].md`

This re-review inspected the actual round-2 producer, schema validator, acceptance, exporter, tests, and operator documentation. It reran the three focused host-only suites and direct capture-gate, route, argument-order, destination, marker-clock, progress-bound, cumulative-counter, timeout, and setup-failure probes. No real FFmpeg, FFprobe, Gamescope, X11/Xvfb server, Wine process, or K1 process was launched, and the isolated worktree was not edited.

## Round 2 verdict

**Specification verdict: FAIL.** The route/capture admission repair, marker and PTS recomputation, argument ordering, timeout handling, and stable-copy export behavior are now effective. The serialized cumulative progress evidence is still not authoritative because it can contradict the terminal block and remain acceptance-ready.

**Code verdict: CHANGES REQUIRED.** One bounded animated-pattern diagnostic is **not authorized yet**. Its receipt could be accepted even when its cumulative progress samples describe a state that cannot precede the claimed terminal FFmpeg state. The inherited-descriptor command contract also accepts an impossible role alias, and generic pre-spawn setup I/O failures still receive the process-exit class.

## Prior-finding disposition

- R1-1, failed capture gate accepted: **closed**. Readiness, acceptance, and export now require exactly `capture_gate == {"status":"passed"}`. False/failed predicates, empty route steps, and any non-`ok` route step also fail.
- R1-2, cadence recomputation: **partially fixed, still Critical**. Interval PTS, gaps, histogram, percentiles, maximum gap, threshold counts, rate/slot arithmetic, marker clocks, progress capture-time bounds, and interval dup/drop deltas are recomputed. The new cumulative samples are not related to the terminal cumulative counters, so impossible counter regressions across the final portion of the same stream pass.
- R1-3, timeout escapes watcher/finalization: **closed**. `subprocess.SubprocessError`, including `TimeoutExpired`, is caught and produces `capture_binding_changed` in both paths.
- R1-4, FFmpeg input-option ordering: **closed**. The validator now requires the complete ordered command and contiguous source segment, and rejects missing/appended output arguments.
- Prior producer-side marker polling/final drain, route/capture separation, interval drop accounting, legacy Xvfb behavior, and post-accept export separation remain preserved.

## Remaining findings

### Critical

#### R2-1. Interval cumulative samples can contradict the terminal FFmpeg block and still be accepted

`_cadence_evidence_passed()` verifies that the left sample's counters do not exceed the right sample and recomputes interval duplicate/drop deltas from them (`display_backends.py:334-368`). It then compares the two serialized terminal copies and checks only `terminal.frame >= frame_count`, `terminal.dup_frames == 0`, and `terminal.drop_frames >= interval_drop_delta` (`display_backends.py:383-386`). It never requires the terminal counters to be greater than or equal to the right cumulative sample.

Two independent mutations of an otherwise-valid completed receipt remained ready, were published by `creative_accept.accept()`, and passed `verify_acceptance()`:

```text
terminal frame in both copies: 600 -> 61
interval end-sample frame:     122 (unchanged)
result: accepted=true, verify=true

interval start/end dup_frames: 0/0 -> 100/100
terminal dup_frames:           0 (unchanged)
interval dup delta:            0
result: accepted=true, verify=true
```

Both receipts are impossible outputs of the monotonic parser. A terminal block cannot follow a cumulative frame count of 122 with frame 61, and cumulative duplicate count cannot fall from 100 to zero. The second mutation also bypasses the intended total-duplicate gate by hiding duplicates before the selected interval while claiming a zero terminal total.

Require complete canonical terminal counters and prove `right_sample[field] <= terminal[field]` for `frame`, `out_time_us`, `dup_frames`, and `drop_frames`. Keep the current left-to-right monotonic and delta checks. Add direct readiness, acceptance, and export mutations for terminal-versus-right counter regression and equal nonzero left/right duplicate counts.

### Important

#### R2-2. The inherited progress/output descriptor grammar accepts an impossible shared descriptor

`_root_capture_matches()` independently matches progress as `/proc/self/fd/<n>` and output as `/proc/self/fd/<n>/continuous.mp4`, but it does not require distinct descriptor numbers or serialize/cross-check their roles (`display_backends.py:392-425`). Changing only the valid fixture's progress target from fd 8 to fd 9, where fd 9 is already the output staging-directory descriptor, kept readiness true. Acceptance then published and verified the receipt.

The producer itself opens distinct descriptors, but the authoritative serialized validator accepts a command in which the same descriptor must simultaneously be a writable progress file and an output directory. That command cannot implement the claimed transport.

Parse descriptor numbers, require nonstandard positive descriptors with distinct progress-file and output-directory roles, and bind them to explicit serialized transport roles if the schema is meant to prove more than path syntax. Add same-descriptor and standard-descriptor mutations to the command-gate tests.

#### R2-3. Generic pre-spawn setup I/O errors are still mislabeled as recorder process exit

The guarded start lifecycle maps only `FileExistsError` and `PermissionError` to `capture_setup_failed`; every other exception before `_popen()` becomes `capture_process_exited` (`recording.py:817-833`). A mocked `OSError` from staging-directory creation produced:

```text
capture_process_exited: capture setup/start failed: OSError: simulated setup I/O failure
```

No process existed. Descriptor/staging cleanup did succeed, but the failure class contradicts the round-2 report's claim that all pre-spawn diagnostic/staging acquisition failures are typed as setup failures. Track whether spawn was attempted or completed and classify every earlier acquisition/open/mkdir error as `capture_setup_failed`; retain `capture_process_exited` for `_popen()` failure and actual recorder exit.

### Minor

#### R2-4. The new mutation suite omits the remaining counter/descriptor/setup contradictions

The added suite now covers all specific R1 false-ready mutations and passes. It does not mutate a right cumulative sample above the terminal block, place equal nonzero duplicate totals in both interval samples, alias progress and staging descriptor roles, or inject a generic pre-spawn `OSError`. These omissions explain why the remaining contradictions coexist with 69 passing Gamescope tests.

## Verified round-2 behavior

- Gamescope alone uses normalized private-root capture, `-draw_mouse 0`, full-root coverage at `0,0`, and no `-window_id`; the legacy Xvfb command and automatic representative rendering path remain unchanged.
- Capture admission and schema-2 readiness require the immutable window/lease chain, complete ordered root command, startup first-frame progress, continuous/final SHM fallback scanning, complete diagnostics, cadence pass, exact capture gate, route predicates, a nonempty all-`ok` step list, preservation, and ordered cleanup.
- The selected cadence interval is recomputed from strictly increasing finite serialized PTS. Histogram, percentiles, maximum gap, gap counts, frame/span/rate/slot math, and missing/drop ratio mutations fail closed.
- Marker byte/sequence order, shared monotonic origin, endpoint uncertainty, same-poll conservative bounds, and progress capture-time bounds are checked.
- Missing/appended/changed output, arbitrary progress paths, source-option drift, terminal duplicates, negative/NaN gaps, marker clock drift, unbounded/reversed progress times, and interval counter-delta contradictions all failed readiness in direct probes.
- Watcher and final binding `TimeoutExpired` paths are typed, and partial setup closes descriptors and removes the owned staging directory.
- Visual acceptance reruns completed execution readiness and binds execution/review/media digests. Export reruns acceptance, copies the accepted master through an `O_NOFOLLOW` descriptor into private staging, verifies the stable copy, and publishes derivatives separately.

## Round 2 validation

```text
PYTHONPATH=scripts/harness python3 tools/kpharness_creative_test.py
30 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_backend_test.py
69 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_boot_repair_test.py
41 tests passed

python3 -m py_compile [eight scoped Python files]
PASS

git diff --check [scoped implementation, test, and documentation files]
PASS

ad hoc readiness/acceptance/setup probes
PASS as probes; reproduced R2-1 through R2-3
```

Total focused tests: 140 passed.

## Diagnostic authorization

**NOT AUTHORIZED.** Close R2-1 through R2-3 and add the four direct regressions before launching the bounded animated-pattern diagnostic. After those fixes, rerun this host-only review. A K1 acceptance run remains later than a passing animated diagnostic and a fresh independent authorization.

---

# Round 3 re-review

Date: 2026-09-27

Implementation report reviewed: `.superpowers/sdd/lua-boundary-validation-plan/ta[REDACTED].md`

The round-3 code, tests, acceptance/export integration, and documentation were reviewed in the same isolated worktree. The review reran every prior mutation and added fresh policy, marker/PTS/whole-capture containment, interval completeness, terminal-clock/frame, descriptor-role, and setup-classification probes. No real FFmpeg, FFprobe, Gamescope, X11/Xvfb server, Wine process, or K1 process was launched. The worktree was not edited.

## Round 3 verdict

**Specification verdict: FAIL.** Round 3 closes every specific Critical and Important round-2 finding. The new whole-capture validator still proves only that the supplied whole summary is internally consistent. It does not prove that it is the superset from which the named intervals were selected, and terminal frame count need not cover its frame count.

**Code verdict: CHANGES REQUIRED.** The bounded animated-pattern diagnostic is **not authorized**. A receipt can replace the whole-capture sequence with a disjoint cadence-perfect sequence, or claim more whole-capture frames than the terminal FFmpeg counter, then pass readiness, acceptance publication, and acceptance verification.

## Prior-finding disposition

- R2-1, interval samples contradict terminal counters: **closed**. All four terminal counters are canonical nonnegative integers, terminal/right-sample monotonicity is enforced, terminal duplicates must be zero, and terminal encoded time must cover the supplied whole summary.
- R2-2, aliased/standard descriptor roles: **closed**. Command descriptor numbers are parsed, must be at least 3 and distinct, and must exactly match versioned progress-file/output-directory metadata.
- R2-3, generic pre-spawn setup classification: **closed**. A repeated injected `OSError` produced `capture_setup_failed`, did not call `_popen()`, and released acquired resources. `_popen()` failure remains `capture_process_exited`.
- Fixed 60 FPS policy and exact thresholds are authoritative. Lowered rates and fully recomputed degraded cadence under loosened thresholds fail.
- Acceptance-interval PTS displacement, duplicate marker-pair intervals, incomplete whole-summary objects, zero terminal encoded clock, and all earlier route/capture/order/destination mutations fail.

## Remaining findings

### Critical

#### R3-1. The claimed whole-capture PTS sequence need not contain the accepted interval

`_pts_summary_matches()` proves that a supplied summary is internally consistent and that its PTS lie within its own serialized bounds (`display_backends.py:33-76`). `_cadence_evidence_passed()` validates `whole_capture` and every named interval independently (`display_backends.py:327-368`). It never requires the whole bounds to equal its first/last PTS, never requires named-interval bounds to lie within the whole bounds, and never requires each named interval's PTS to be an ordered subset of the whole sequence that the producer probed.

The following independent mutations of an otherwise-valid receipt all kept readiness true:

```text
whole bounds widened from [1,2] to [0,3] while whole PTS remained [1,2]
whole PTS replaced with a cadence-perfect [3,4] sequence while acceptance stayed [1,2]
whole PTS replaced with a different 60 Hz lattice while acceptance PTS stayed unchanged
```

The fully disjoint `[3,4]` receipt was published by `creative_accept.accept()` and passed `verify_acceptance()`. Because the terminal encoded-clock check is performed against this freely replaceable whole summary, that check also does not bind the terminal clock to the same PTS source used by the accepted interval.

Require canonical whole bounds equal to the whole sequence's first and last PTS. Require every serialized interval's bounds and included PTS to be contained in, and drawn in order from, `whole_capture.included_pts_seconds`. Add disjoint, shifted-lattice, widened-bound, and omitted-subsequence acceptance/export regressions.

#### R3-2. Terminal frame count may be lower than the whole-capture decoded-frame count

The terminal validator requires `terminal.frame >=` the acceptance interval's frame count and validates terminal encoded time against the supplied whole PTS clock (`display_backends.py:466-476`). It does not require `terminal.frame >= whole_capture.frame_count`.

A direct probe replaced the whole summary with 1,201 valid 60 Hz frames over 20 seconds, left terminal frame at 600, and changed both terminal `out_time_us` copies to 20,000,000. Readiness remained true; acceptance published the receipt; and verification returned true. The receipt therefore claims 1,201 decoded whole-capture frames from a terminal encoder total of only 600 frames.

Require terminal frame count to cover the independently recomputed whole-capture frame count. Add readiness, acceptance, and export regressions with a sufficient terminal encoded clock but insufficient terminal frame total.

### Important

#### R3-3. Marker additions do not require the promised consecutive named intervals

The validator rejects duplicate interval pairs and checks every interval that is present, but it does not derive the required pair set from the ordered named markers. Adding a valid `phase_2` marker between `phase_1` and `complete` while leaving only the `phase_1 -> complete` acceptance interval kept readiness true, was accepted, and verified.

The producer normally emits consecutive configured pairs, but schema-2 cannot distinguish complete evidence from omitted phase evidence. Serialize the configured cadence-marker order and require exactly the acceptance pair plus every applicable consecutive named-marker pair. Add missing-middle-pair and extra-unconfigured-pair mutations.

### Minor

#### R3-4. Serialized route-interval cadence evidence remains outside authoritative validation

When present, `cadence.route_interval` is not inspected by `_cadence_evidence_passed()`. Replacing it with `{"status":"passed","nonsense":true}` kept readiness true. Route-interval cadence is supplementary rather than an acceptance condition, but the brief requires that interval when route times are available and the accepted receipt currently carries it as evidence.

Validate a present route interval with `_pts_summary_matches()` and require its PTS to be an ordered subset of whole-capture PTS. If route timing is mandatory for this schema version, serialize the route bounds authoritatively and require the interval rather than treating omission as equivalent to absence.

## Verified round-3 behavior

- All prior capture-gate, route-step, command-order, destination, cadence arithmetic, marker-clock, progress-bound, terminal/right-sample, descriptor-role, timeout, and setup-classification mutations fail closed.
- Gamescope remains the only private-root capture backend. Normalized screen zero, full-root `0,0` coverage, no `-window_id`, continuous SHM fallback scanning, and immutable window/lease verification remain intact.
- The versioned policy fixes Gamescope at 60 FPS, 99% minimum rate, 0.5% maximum missing/drop ratio, and 50 ms maximum gap. Producer and verifier agree on exact values.
- Named interval summaries recompute finite increasing PTS, counts, span, rate, slots, histogram, percentiles, maximum gap, threshold counts, and pass/fail status.
- Visual acceptance and export rerun the strengthened completed-execution gate; stable-copy export and legacy Xvfb behavior remain valid.

## Round 3 validation

```text
PYTHONPATH=scripts/harness python3 tools/kpharness_creative_test.py
30 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_backend_test.py
72 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_boot_repair_test.py
41 tests passed

python3 -m py_compile [eight scoped Python files]
PASS

git diff --check [scoped implementation, tests, and documentation]
PASS

ad hoc readiness/acceptance/setup probes
PASS as probes; closed all round-2 cases and reproduced R3-1 through R3-4
```

Total focused tests: 143 passed.

## Diagnostic authorization

**NOT AUTHORIZED.** Close R3-1 through R3-3 and add the listed direct regressions before launching the bounded animated-pattern diagnostic. R3-4 should also be resolved so a published schema-2 receipt does not carry unchecked route cadence evidence. A K1 acceptance run remains later than a passing animated diagnostic and a fresh independent authorization.

---

# Round 4 re-review

Date: 2026-09-27

Implementation report reviewed: `.superpowers/sdd/lua-boundary-validation-plan/ta[REDACTED].md`

This re-review traced the canonical artifact from final master publication through schema readiness, fresh visual acceptance, acceptance verification, and the export gate. It replayed all prior mutations and added alternate-history, master/artifact identity, whole/subsequence/route projection, marker topology, progress-prefix, terminal whole-count/clock, policy-scope, and acceptance-time replacement probes. No external FFmpeg, FFprobe, Gamescope, X11/Xvfb server, Wine process, or K1 process was launched. The worktree was not edited.

## Round 4 verdict

**Specification verdict: FAIL.** Round 4 closes every static receipt contradiction reported through round 3. The mandatory fresh acceptance probe still operates on the master by pathname after hashing it. A replace/probe/restore race can therefore make acceptance sign an alternate PTS history for the unchanged digest-bound master.

**Code verdict: CHANGES REQUIRED.** The bounded animated-pattern diagnostic is **not authorized**. The diagnostic is intended to establish real acquisition and cadence, but its acceptance boundary can still certify cadence observed from a temporary replacement file and subsequently export the restored master under that certification.

## Prior-finding disposition

- R3-1, whole history not bound to interval projections: **closed statically**. One hashed, bounded, no-follow canonical artifact now binds the master digest; whole capture equals its full list and bounds; named and route intervals equal exact inclusive projections.
- R3-2, terminal frame below whole count: **closed**. Terminal frame count covers canonical whole frame count and terminal encoded clock covers the whole PTS clock.
- R3-3, incomplete named-marker interval topology: **closed**. Required order, patterns, acceptance pair, optional marker set, captured names, and the exact consecutive/acceptance pair set are checked.
- R3-4, unchecked route interval: **closed**. Route bounds and route cadence presence agree, and the route PTS list is the exact canonical projection.
- All earlier capture/route gates, command order/destinations, descriptor roles, setup classification, marker clock, progress bounds/prefixes, duplicate policy, and fixed-threshold policy mutations remain closed.

## Remaining finding

### Critical

#### R4-1. Fresh acceptance probes a pathname that can be replaced and restored after the bound master is hashed

`creative_accept.accept()` first resolves and hashes the master (`creative_accept.py:120-129`). It later calls `pts_probe(media, executable)` using the pathname (`creative_accept.py:132-143`). The function does not keep an opened no-follow master descriptor across both operations, pass that descriptor to FFprobe, use a private stable copy, or revalidate an unbroken inode identity around the probe. The final `verify_acceptance()` reopens the path after the probe, so a replacement restored before the callback returns is invisible.

A host-only probe installed a fully coherent alternate canonical artifact and recomputed receipt summaries for an unchanged original master. Static readiness correctly considered that alternate artifact internally coherent, as intended before the fresh probe. The injected probe then:

1. observed the original master bytes;
2. renamed the original aside;
3. installed a temporary alternate master at the same pathname;
4. returned the alternate PTS history as the probe result;
5. removed the alternate and restored the original before returning.

The result was:

```text
coherent_alternative_ready=True
swap_restore_accept_ok=True
swap_restore_verify_ok=True
swap_restore_export_gate_ok=True
master_restored=True
```

This is the pathname race that the fresh probe is meant to prevent. The accepted receipt binds the alternate artifact and PTS history, while its media digest and subsequent export identify the restored original master. The existing alternative-history test rejects a stable mismatch or a replacement left in place; it does not cover replace/probe/restore.

Probe a stable master identity. A suitable implementation can open the master once with `O_NOFOLLOW`, verify a regular file, hash that descriptor, and either pass the same inherited descriptor to FFprobe or copy it into private acceptance staging and probe the stable copy. Keep the descriptor/copy through the artifact comparison and acceptance construction, then verify the published path still has the expected identity and digest. Add a callback regression that swaps and restores the public master during probing while returning the replacement's PTS; acceptance and export must reject it.

## Verified round-4 behavior

- The canonical artifact is bounded, regular, no-follow, hashed, master-digest-bound, and schema/version/method/frame-count checked.
- Whole, named, acceptance, and route summaries are internally recomputed and exact projections of the canonical PTS list.
- Exact marker topology, policy scope, terminal whole-count/clock coverage, and progress-prefix enclosure reject the prior false-ready states.
- Failed capture gates, terminal/right regressions, hidden duplicates, descriptor aliasing, weakened policy, widened/disjoint whole summaries, invented markers, zero progress, bad artifact digests, and malformed route intervals all returned false in direct replay.
- Acceptance and export bind the artifact digest after publication; stable-copy derivative encoding and legacy Xvfb behavior remain intact once acceptance itself is valid.

## Round 4 validation

```text
PYTHONPATH=scripts/harness python3 tools/kpharness_creative_test.py
30 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_backend_test.py
74 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_boot_repair_test.py
41 tests passed

python3 -m py_compile [eight scoped Python files]
PASS

git diff --check [scoped implementation, tests, and documentation]
PASS

ad hoc mutation and acceptance/export-gate probes
PASS as probes; all prior mutations closed and R4-1 reproduced
```

Total focused tests: 145 passed.

## Diagnostic authorization

**NOT AUTHORIZED.** Close R4-1 with a stable-master fresh-probe implementation and a swap/probe/restore acceptance regression, then rerun the host-only review. One bounded animated-pattern diagnostic can be reconsidered immediately after that closure. K1 remains later than a passing diagnostic and separate authorization.

---

# Round 5 re-review

Date: 2026-09-27

Implementation report reviewed: `.superpowers/sdd/lua-boundary-validation-plan/ta[REDACTED].md`

This review replayed all earlier receipt and acceptance mutations, then exercised public and private stable-copy replacement, canonical route-report files, report/receipt step agreement, coherent alternate route reports, FFprobe byte limits, timeout and nonzero-exit cleanup, acceptance verification, and the export gate. No external FFmpeg, FFprobe, Gamescope, X11/Xvfb server, Wine process, or K1 process was launched. The worktree was not edited.

## Round 5 verdict

**Specification verdict: FAIL.** The public-master race from round 4 is closed, but the fresh probe still opens the private copy by pathname. Renaming and restoring that private inode around the probe reproduces the same alternate-history acceptance. The new canonical route report is content-addressed and schema-checked, but it is not bound to the selected K1 route source; a coherently rehashed report for another target/scenario/build or arbitrary replacement steps is accepted.

**Code verdict: CHANGES REQUIRED.** The bounded animated-pattern diagnostic is **not authorized**. Both remaining gaps cross the final acceptance boundary and survive export admission.

## Prior-finding disposition

- R4-1 public master swap/probe/restore: **closed for the public pathname**. Acceptance copies from a retained `O_NOFOLLOW` descriptor, hashes the descriptor, probes only a private copy, and brackets the public identity/digest.
- All static cadence, whole/projection, marker topology, route interval, progress, terminal, policy, descriptor, startup, timeout, and cleanup mutations remain closed.
- Missing, symlinked, wrong-digest, oversized, malformed, and receipt-step-mismatched route reports now fail readiness.
- FFprobe timeout and oversized output kill and reap the mocked child; a nonzero exited child is reaped and reported as `CalledProcessError`.

## Remaining findings

### Critical

#### R5-1. The private acceptance copy is still probed through a replaceable pathname

`accept()` creates a private exclusive copy and records its inode/size/mtime/digest (`creative_accept.py:191-199`). It then passes the copy's pathname to `pts_probe()`. After probing, it reopens that pathname and compares the restored identity and digest. A rename/replacement/restore sequence therefore evades both checks just as it did on the public path.

A host-only probe installed a coherent alternate PTS artifact and receipt for the original master, then received the private stable-copy pathname. The callback renamed the original private copy aside, installed a temporary alternate file at the same name, returned the alternate PTS, removed the alternate, and restored the original inode before returning. The public master never changed.

```text
stable_swap_restore_accept=True
stable_swap_restore_verify=True
stable_swap_restore_export_gate=True
stable_probe_saw_replacement=True
```

The random mode-private directory narrows the race but does not make the probed file identity stable: the probe subprocess still resolves a pathname, and a same-user process can discover its command line and access the same user's directory. The receipt signs alternate cadence while verification and export use the original master.

Hold and probe an open descriptor rather than reopening a pathname. Pass `/proc/self/fd/<n>` with that exact descriptor in `pass_fds`, or use another descriptor-based FFprobe API, and retain/fstat/hash it through probe completion. The probe helper must accept the descriptor explicitly so tests can prove which inode the child receives. Add a private-copy rename/replacement/restore regression; public and private restoration must both fail to substitute probe input.

#### R5-2. A validly rehashed route report is not bound to the selected K1 route source

`_route_report_matches()` correctly binds `route.steps` to the report's step list and enforces a narrow successful-report shape (`display_backends.py:779-840`). It only requires `scenario`, `target`, and `build` to be nonempty strings. It does not bind `target` to K1 or `receipt.target`, bind `scenario` to the selected route, bind `build` to the selected build, validate `route_source`, or derive the allowed step sequence from that route source.

Two coherent mutations passed readiness, acceptance, verification, and the export gate after updating the report digest:

```text
report target/scenario/build = k2 / different / different
wrong_route_identity_accept=True
wrong_route_identity_verify=True
wrong_route_identity_export_gate=True

report and duplicated receipt steps = one fabricated unrelated successful action
arbitrary_matching_steps_ready=True
arbitrary_matching_steps_accept=True
arbitrary_matching_steps_verify=True
arbitrary_matching_steps_export_gate=True
```

The report is internally canonical but can describe an unrelated route. This defeats the route predicate gate because the accepted report need not be the execution of the route copied and hashed at run start.

Require `report.target == receipt.target == "k1"`, bind report scenario/build to the selected receipt fields, verify the run-local `route_source` artifact and parse it, and bind the report's step indices/descriptions or stable step identities to that parsed route. Add coherent wrong-target, wrong-scenario/build, and fully substituted matching-step-list tests through readiness, acceptance, and export.

### Minor

#### R5-3. The streaming probe can retain 64 KiB beyond the documented 16 MiB-plus-one bound

`probe_frame_pts()` reads fixed 64 KiB blocks and checks the total only after extending the bytearray (`recording.py:203-215`). With a stream containing at least 16 MiB plus 64 KiB, the measured retained total before rejection was 16,842,752 bytes: 65,536 bytes above the configured 16 MiB limit. The child was correctly killed and reaped.

The implementation remains bounded by roughly one read chunk, so this is not an unbounded-memory defect. It contradicts the round-5 report's stronger claim that Python reads at most 16 MiB plus one byte. Limit each `os.read()` to `MAX_CANONICAL_PTS_BYTES + 1 - len(raw)`, then reject at the first excess byte. Add a full-chunk producer regression rather than only a sparse file whose final excess is one byte.

## Verified round-5 behavior

- The public master is copied and hashed from an open no-follow descriptor, and public mutation is checked after probing.
- Route reports that are absent, symlinks, too large, malformed JSON, wrong-digest, schema-invalid, or different from duplicated receipt steps fail closed.
- Stable-copy export, acceptance digests, canonical PTS projections, exact marker topology, fixed policy scope, root-capture command, SHM scanning, typed cleanup, and legacy Xvfb behavior remain intact.
- Oversized and timed-out mocked FFprobe processes are killed and reaped. Nonzero exits are typed and reaped.

## Round 5 validation

```text
PYTHONPATH=scripts/harness python3 tools/kpharness_creative_test.py
30 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_backend_test.py
77 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_boot_repair_test.py
41 tests passed

python3 -m py_compile [eight scoped Python files]
PASS

git diff --check [scoped implementation, tests, and documentation]
PASS

ad hoc route, stream, acceptance, verification, and export-gate probes
PASS as probes; R5-1 through R5-3 reproduced
```

Total focused tests: 148 passed.

## Diagnostic authorization

**NOT AUTHORIZED.** Close R5-1 and R5-2 and add end-to-end regressions before launching the bounded animated-pattern diagnostic. Correct R5-3 in the same bounded probe helper. K1 remains later than a passing diagnostic and a fresh independent authorization.

---

# Round 6 re-review

Date: 2026-09-27

Implementation report reviewed: `.superpowers/sdd/lua-boundary-validation-plan/ta[REDACTED].md`

This review reran the complete 152-test focused set and the prior mutation boundaries, then directly exercised the unlinked inherited master descriptor, private descriptor write/restore detection, verified FFprobe executable identity, executable swap/probe/restore, parsed-route speed binding, exact 16 MiB-plus-one retention, and an unkillable mocked probe child. No external FFmpeg, FFprobe, Gamescope, X11/Xvfb server, Wine process, or K1 process was launched. The worktree was not edited.

## Round 6 verdict

**Specification verdict: FAIL.** R5-1 through R5-3 are closed as written: acceptance now probes a retained zero-link descriptor, private write/restore changes its ctime identity, route reports are bound to the parsed run-local route/target/build/runtime/steps, and probe output stops at exactly 16 MiB plus one byte. Two remaining contradictions cross the acceptance boundary. The supposedly verified FFprobe executable is reopened by pathname and can be replaced only for the fresh probe, then restored. The report's internally consistent requested/effective speed is never compared with the parsed route's `settings.game_speed`.

**Code verdict: CHANGES REQUIRED.** One bounded animated-pattern diagnostic is **not authorized**. The fresh-probe tool identity must be stable across process creation, and route speed must be derived from or compared with the parsed executed route.

## Prior-finding disposition

- R5-1, private stable-copy pathname substitution: **closed**. Acceptance gives the probe `/proc/self/fd/N`, explicitly inherits the same FD, requires link count zero, and rechecks the descriptor's full identity and digest afterward.
- R5-2, route report not bound to the selected route: **closed for scenario, target, build, runtime artifacts, route digest, and ordered step descriptions**. Missing/symlinked/malformed/wrong-digest/oversized reports and incoherent substitutions remain rejected.
- R5-3, FFprobe output retention beyond the promised ceiling: **closed**. The final read is one byte and the retained total is exactly 16 MiB plus one before rejection; the child is killed and reaped.
- The typed unkillable-child path performs only two bounded `wait(timeout=2)` calls, retains the exact child in `ProbeCleanupError`, and never performs an unbounded wait.
- Earlier root-capture, normalized display, command/destination, descriptor-role, progress-prefix, terminal-clock/count, cadence/marker topology, capture/route gate, schema-2 recomputation, legacy/Xvfb, acceptance, and export mutations remain covered by the passing focused suites.

## Remaining findings

### Critical

#### R6-1. Fresh acceptance verifies the FFprobe executable by path before probing, then executes the same mutable pathname

`_probe_tool_matches()` opens and hashes the recorded executable, then closes its descriptor (`display_backends.py:47-66`). `accept()` subsequently passes only `tool['resolved_path']` to the probe (`creative_accept.py:225-227`), and `probe_frame_pts()` gives that pathname to `Popen` (`recording.py:218-228`). No verified executable descriptor or private immutable tool copy spans the check and `execve`. The post-probe `verify_acceptance()` simply reopens the restored path.

A host-only probe configured a user-owned executable, produced a fully coherent receipt/artifact identity for it, and confirmed readiness. During the injected fresh-probe callback it renamed that executable aside, installed different executable bytes at the identical path, returned the canonical PTS list, removed the substitute, and restored the original before returning:

```text
tool_swap_ready_before=True
tool_original_sha=306c6ca7407560340797866e077e053627ad409277d1b9da58106fce4cf717cb
tool_alternate_sha=c08e2a9655a4803698ebb78cd8d2591876c9b294b9ccec7a9845b78f71e2da07
tool_swap_accepted=True
tool_restored_sha=306c6ca7407560340797866e077e053627ad409277d1b9da58106fce4cf717cb
```

The CLI explicitly supports `--ffprobe`, so a user-owned executable path is an ordinary supported configuration. A substitute tool can emit the artifact's expected PTS without probing the retained master at all; acceptance then signs the result and later verification sees the restored SHA. This defeats the fresh probe's independence even though the media FD is now stable.

Retain a verified no-follow executable identity through child creation and execute that identity, for example through a verified inherited descriptor or a private executable copy whose descriptor/path cannot be replaced by another same-user process. Recheck the retained tool identity after the child exits. Add a swap/execute/restore regression that exercises the real `probe_frame_pts` `Popen` boundary with a harmless fake executable and proves the replacement cannot supply accepted timestamps.

### Important

#### R6-2. Route execution speed is not bound to the parsed executed-route setting

`_route_report_matches()` parses the exact `executed-route.toml` and validates scenario, target, build, runtime hashes, and steps (`display_backends.py:807-925`). It calls `_route_execution_matches(execution)` without passing `scenario.settings['game_speed']` (`display_backends.py:894-900`). The helper only checks that requested equals effective and, when present, retained equals effective (`display_backends.py:931-951`). Any internally consistent value in `(0,16]` passes even when it contradicts the canonical route.

The standard fixture route parses to `game_speed=16.0`. Changing the hashed report to requested/effective `8.0`, updating only its recorded digest, and leaving the parsed route unchanged produced:

```text
speed_mismatch_ready=True
speed_mismatch_accepted=True
```

The production creative route contract is stricter still: the selected route must explicitly set `game_speed=1.0`. A coherently altered report can therefore claim execution at another speed while retaining the selected route's identity and passing acceptance/export recomputation. Existing tests reject requested/effective disagreement but never compare a consistent pair with the route setting.

Require `game_speed_requested` and `game_speed_effective` to equal the parsed scenario's configured speed within the existing exact tolerance. Add explicit-route fixtures for matching and mismatched internally consistent values, and drive the mismatch through readiness, acceptance verification, and export gating.

## Verified round-6 behavior

- The accepted master is copied from a retained no-follow public descriptor into an exclusive file, reopened read-only, unlinked, and probed only through its explicitly inherited zero-link descriptor.
- A private descriptor write/restore is rejected because ctime and the exact descriptor identity change even when bytes and mtime are restored.
- The route source is opened no-follow, bounded, identity/digest checked, parsed, and used to bind K1 target, scenario, build, runtime SHA map, and exact ordered steps.
- Probe failures and exact-size overflow retain bounded memory and bounded cleanup; an unreaped child remains available through the typed error.
- Acceptance publication, acceptance-digest verification, stable-copy export, and legacy paths remain green for valid fixtures.

## Round 6 validation

```text
python3 tools/kpharness_creative_test.py
30 tests passed

python3 tools/kpharness_gamescope_boot_repair_test.py
41 tests passed

python3 tools/kpharness_gamescope_backend_test.py
81 tests passed

targeted unlinked-descriptor/private-mutation, exact-cap, and unkillable-cleanup tests
3 tests passed

ad hoc speed-binding and executable swap/probe/restore probes
PASS as probes; R6-1 and R6-2 reproduced
```

Total focused tests: 152 passed.

## Diagnostic authorization

**NOT AUTHORIZED.** Close R6-1 and R6-2 and rerun the host-only acceptance/export probes before one bounded animated-pattern diagnostic. K1 remains later than a passing diagnostic and separate authorization.

---

# Round 7 re-review

Date: 2026-09-27

Implementation report reviewed: `.superpowers/sdd/lua-boundary-validation-plan/ta[REDACTED].md`

This review reran all 158 focused host-only tests and the prior mutation boundaries. It then exercised the retained native-ELF tool descriptor and FD closure paths, tool-path replacement/restoration, script refusal, independently supplied route SHA through acceptance/verification/export, coherent route substitution, parsed `game_speed` binding, and the durable unreaped-child state across a second acceptance attempt. No external FFmpeg, FFprobe, Gamescope, X11/Xvfb server, Wine process, or K1 process was launched. The worktree was not edited.

## Round 7 verdict

**Specification verdict: FAIL.** R6-1 and R6-2 are closed. Acceptance retains and probes the verified native ELF inode rather than reopening its configured pathname, and report speed is now bound to the parsed route setting. The independent route SHA is carried through acceptance, verification, export admission, and the derivative sidecar. However, a durable unreaped-child failure is write-only evidence: a later acceptance ignores the unresolved failure file and can publish a passing receipt and enter export while the retained child is still unresolved. The recorded fallback PID start parser is also wrong for legal Linux process names containing spaces.

**Code verdict: CHANGES REQUIRED.** One bounded animated-pattern diagnostic is **not authorized**. The unresolved probe-cleanup state must participate in acceptance verification/export admission, and its process identity must be parsed correctly before it can support owner-controlled recovery.

## Prior-finding disposition

- R6-1, mutable FFprobe pathname at fresh probe: **closed**. Acceptance opens the configured path no-follow, requires an executable native ELF regular file, hashes and fstats that descriptor, passes `/proc/self/fd/N` with the exact FD inherited, and rechecks both the retained descriptor and public pathname. Replacement/restoration cannot substitute the executed bytes and is detected through identity change. Script input fails closed, and both acceptance-owned descriptors close on exit.
- R6-2, route speed not bound to the parsed route: **closed**. Requested and effective speed must now equal `scenario.settings.game_speed`; the coherent `8.0/8.0` report against a parsed `16.0` route fails readiness.
- The external route commitment is present at all requested public boundaries. A coherently substituted route/report/steps/execution identity remains internally self-consistent but fails acceptance when the reviewer supplies the original launch digest. Wrong digests fail `verify_acceptance()` and `accepted_receipt()`, and the selected digest is included in the derivative sidecar.
- All earlier capture, cadence, marker, progress, terminal, route, schema-2, acceptance publication, stable export, exact buffer-cap, typed cleanup, and legacy/Xvfb tests remain green.

## Remaining findings

### Critical

#### R7-1. An unresolved unreaped FFprobe child does not block a later acceptance or export

When the fresh probe raises `ProbeCleanupError`, `accept()` atomically writes `ffprobe-cleanup-failure.json` and returns failure (`creative_accept.py:274-276`). No subsequent code reads that artifact. A new `accept()` invocation starts from the pending schema-2 receipt without checking for unresolved cleanup (`creative_accept.py:215-248`), while `verify_acceptance()` and `creative_export.accepted_receipt()` likewise ignore it (`creative_accept.py:165-184`, `creative_export.py:20-35`). There is no identity-checked recovery operation or resolved state in the implementation.

A host-only state-transition probe first injected a typed surviving child and confirmed the durable failed artifact. Without removing or resolving that artifact or its child identity, it invoked acceptance again with a successful probe:

```text
first_failure=ValueError: canonical PTS re-probe cleanup failed: survived
cleanup_after_failure.status=failed
cleanup_after_failure.pid=4242
cleanup_after_failure.pid_start=fixture-start
retry_accepted=True
retry_verifies=True
export_admission=True
cleanup_after_accept.status=failed
```

Thus the run simultaneously contains an unresolved cleanup failure and a signed accepted receipt that is eligible for export. With a real child, the original process remains owner-retained after both bounded waits; a retry can also overwrite the single cleanup-failure pathname with a later child and lose the first recovery identity.

Make unresolved cleanup durable state authoritative. Acceptance, `verify_acceptance()`, and export admission must reject while any cleanup-failure record is unresolved. Provide an explicit recovery path that parses the record no-follow, validates its schema and tool/command identity, compares the live PID's exact start time before signaling or reaping, and atomically records resolution without erasing the original failure. Add a two-attempt regression proving a successful second PTS callback cannot accept or export until recovery is independently completed.

### Important

#### R7-2. The fallback `/proc/<pid>/stat` parser records the wrong start identity when the process name contains spaces

`ProbeCleanupError` obtains field 22 with `Path(...).read_text().split()[21]` (`recording.py:194-200`). Linux `/proc/<pid>/stat` field 2 is a parenthesized process name that may contain spaces, so splitting the entire line shifts every later field. The repository already has the correct approach in `session.pid_start()`: locate the final closing parenthesis, split only the suffix, and take suffix field index 19.

A pure mocked-stat probe used a legal parenthesized name containing spaces and placed `424242` in the start-time field:

```text
expected_pid_start=424242
parsed_pid_start=20
```

The durable receipt therefore can misidentify precisely the process it tells the operator to recover. A safe recovery implementation should refuse a mismatch, leaving cleanup permanently blocked; an unsafe consumer could target the wrong reused PID.

Reuse the existing robust `session.pid_start()` parser or an equivalent final-parenthesis parser, require a nonempty start identity before claiming exact recovery evidence, and add process names with spaces and embedded right-parenthesis cases to the cleanup tests.

## Verified round-7 behavior

- The retained native ELF executable FD, not the mutable configured pathname, is the fresh probe's argv element zero and is present with the unlinked media FD in `pass_fds`.
- Tool and media descriptors close after both success and failure; scripts and unsupported formats do not fall back to pathname execution.
- Route digest selection is now an explicit caller input to acceptance, verification, accepted-receipt loading, export, and the export CLI, and it is signed into acceptance and publication metadata.
- Coherent route substitution cannot satisfy an independently retained original route digest.
- Parsed route speed, exact buffer limit, prior capture/cadence gates, and stable-copy export behavior remain correct under the focused suite.

## Round 7 validation

```text
python3 tools/kpharness_creative_test.py
30 tests passed

python3 tools/kpharness_gamescope_boot_repair_test.py
41 tests passed

python3 tools/kpharness_gamescope_backend_test.py
87 tests passed

targeted retained-tool FD, route commitment, speed, durable-write, argv/pass_fds, and export-digest tests
6 tests passed

ad hoc unresolved-cleanup retry/export and spaced-comm PID-start probes
PASS as probes; R7-1 and R7-2 reproduced
```

Total focused tests: 158 passed.

## Diagnostic authorization

**NOT AUTHORIZED.** Close R7-1 and R7-2, add the unresolved-cleanup retry/export regression and robust PID-start parsing coverage, then rerun the host-only acceptance/export review before one bounded animated-pattern diagnostic. K1 remains later than a passing diagnostic and separate authorization.

---

# Round 8 re-review

Date: 2026-09-27

Implementation report reviewed: `.superpowers/sdd/lua-boundary-validation-plan/ta[REDACTED].md`

This review reran all 166 focused host-only tests and replayed the earlier capture, cadence, acceptance, route, tool, and cleanup contradictions. It directly exercised the external FFprobe digest through acceptance/verification/export, kill-versus-exit races, robust process-name parsing, multiple immutable failure records, unresolved/malformed/symlink/orphan gate behavior, identity-matched/mismatched/already-exited recovery, and cross-bound existing resolutions. No external FFmpeg, FFprobe, Gamescope, X11/Xvfb server, Wine process, or K1 process was launched. The worktree was not edited.

## Round 8 verdict

**Specification verdict: FAIL.** R7-1 and the ordinary spaced-name parser defect in R7-2 are closed for the tested happy and mismatch paths. The append-only ledger now blocks acceptance, verification, and export while a recognized failure is unresolved, retains multiple failures, and supports bounded identity-checked recovery. The configured FFprobe digest is independently supplied and signed through export. Three recovery contradictions remain: the production PID reader treats every `/proc` read failure as process absence, partial/non-exact cleanup schemas can clear the gate, and repeated recovery returns a cross-bound existing resolution as success before comparing it with the selected failure.

**Code verdict: CHANGES REQUIRED.** One bounded animated-pattern diagnostic is **not authorized**. A live but unreadable retained child must remain unresolved, the documented exact cleanup schemas must be enforced, and recovery must validate an existing resolution against its failure before returning it.

## Prior-finding disposition

- R7-1, unresolved cleanup ignored by later acceptance/export: **closed for recognized ledger records**. Failure records have unique IDs and exclusive creation, resolutions are separate, multiple children are retained, and all acceptance/export gates call `cleanup_state_clear()`.
- R7-2, whitespace-sensitive `/proc/<pid>/stat` parsing: **closed for readable stat data**. `ProbeCleanupError` reuses `session.pid_start()`, whose final-right-parenthesis parsing handles spaces and embedded right parentheses.
- The external FFprobe commitment is present at every requested boundary. A coherent local tool/cadence/artifact substitution cannot satisfy the operator-supplied digest; wrong digests fail acceptance verification and export; the derivative sidecar records the selected digest.
- Poll-to-exit `ProcessLookupError` still performs a bounded wait, other signal failures produce typed cleanup evidence, and no cleanup path calls an unbounded wait.
- Prior route commitment, parsed speed, retained tool/media descriptors, exact PTS buffer cap, schema-2 cadence recomputation, capture gates, legacy/Xvfb, and stable-copy export behavior remain green.

## Remaining findings

### Critical

#### R8-1. An unreadable live PID is recorded as `already_exited` and clears every cleanup gate

The production recovery reader is `session.pid_start()`. That helper returns the empty string for every `OSError`, including `PermissionError`, transient I/O errors, and actual process absence. `recover_cleanup()` interprets any empty value as an exited PID, appends an `already_exited` resolution without signaling, and `cleanup_state_clear()` then treats the failure as resolved (`creative_accept.py:285-323`; `session.py:97-108`).

A pure mocked `/proc` permission failure reproduced the false resolution for an otherwise live recorded identity:

```text
pid_start_on_permission_error=""
unreadable_outcome=already_exited
unreadable_signal_count=0
unreadable_gate_clear=True
```

This is the unsafe side of the required fail-closed recovery boundary. The process was not proven absent, yet acceptance, verification, and export can proceed because the ledger now says it exited.

Use a strict tri-state identity reader for recovery: return a start value only after a valid stat parse, return a distinct absent result only for `FileNotFoundError`/`ProcessLookupError`, and propagate permission, I/O, truncation, and parse errors as unresolved recovery failures. Apply the same distinction during post-signal polling. Add tests in which open/read/parse fails before and after signaling and prove no resolution is written and every gate remains blocked.

### Important

#### R8-2. Partial and non-exact cleanup schemas can clear the authoritative ledger

`_cleanup_record()` checks only selected members and never compares the record's key set with an exact schema (`creative_accept.py:102-125`). Failure records can omit the command, tool identity, bounded waits, signal errors, and recovery requirement. Resolution records accept extra members and accept any string as `resolved_utc`, including an empty or invalid timestamp. This contradicts the round report's exact-schema claim and weakens the evidence on which all later gates depend.

A minimal failure record plus a resolution containing `resolved_utc="not-a-timestamp"` and an unexpected object passed the authoritative check:

```text
malformed_resolution_gate_clear=True
```

Require exact key sets and validate every field: strict PID/start types, exact wait list, command vector, tool identity shape and SHA, signal-error list, fixed recovery text or version, UTC-aware parseable timestamps, allowed outcomes, and failure/resolution ID equality. Add omission, extra-member, invalid-time, invalid-tool, and invalid-wait mutations through acceptance, verification, and export.

#### R8-3. Repeated recovery returns a cross-bound existing resolution before validating it against the selected failure

`recover_cleanup()` loads the requested failure, but if the corresponding resolution pathname exists it immediately returns `_cleanup_record(resolution_path, resolution=True)` (`creative_accept.py:293-298`). It does not compare the resolution PID/start pair with the failure. `cleanup_state_clear()` performs that comparison later, so the global gates remain closed, but the recovery command itself reports a mismatched resolution as successful.

A failure for PID/start `4242/expected` with an existing same-ID resolution for `9999/other` produced:

```text
cross_bound_recovery_returned=[9999, "other"]
cross_bound_gate_clear=False
```

Validate the existing resolution's ID, PID, and start identity against the already loaded failure before returning it. A mismatch must raise the same corruption error used by the ledger gate. Add repeated-recovery tests for PID mismatch, start mismatch, outcome corruption, symlink, and malformed timestamp.

## Verified round-8 behavior

- The external FFprobe SHA is explicit at acceptance, verification, accepted-receipt loading, export, and both CLIs, is signed into `visual_review`, and is copied into the export sidecar.
- Cleanup failure filenames use random 32-hex IDs and exclusive creation, so a later producer failure cannot overwrite an earlier record.
- Recognized unresolved, symlinked, misnamed, malformed-required-field, and orphan-resolution states block the tested gates.
- A matching readable identity receives one SIGKILL and bounded disappearance polling; a readable mismatched identity is not signaled; a genuinely absent identity can be recorded as already exited once absence is distinguished correctly.
- The robust readable-stat parser correctly handles spaces and embedded right parentheses in `comm`.

## Round 8 validation

```text
python3 tools/kpharness_creative_test.py
30 tests passed

python3 tools/kpharness_gamescope_boot_repair_test.py
41 tests passed

python3 tools/kpharness_gamescope_backend_test.py
95 tests passed

ad hoc unreadable-PID, non-exact-schema, and cross-bound-resolution probes
PASS as probes; R8-1 through R8-3 reproduced
```

Total focused tests: 166 passed.

## Diagnostic authorization

**NOT AUTHORIZED.** Close R8-1 through R8-3, add strict absence/error recovery and exact-schema regressions through all gates, then rerun the host-only acceptance/export review before one bounded animated-pattern diagnostic. K1 remains later than a passing diagnostic and separate authorization.

---

# Round 9 re-review

Date: 2026-09-27

Implementation report reviewed: `.superpowers/sdd/lua-boundary-validation-plan/ta[REDACTED].md`

This review reran the three focused suites on the host (173 tests), reran the backend suite inside the agent container, replayed the receipt-level counterexamples from rounds 0 to 8, and exercised the new hash-chained cleanup ledger, external head, tri-state identity reader, pidfd recovery, signal-error-then-reap path, and repeated recovery. Probe scripts live outside the worktree in `/home/brunner56/kp-live-20260922/review-probes-r9-correctness/`, in `probe_r9.py` and `replay_r0_r7.py`. No FFmpeg, FFprobe child, Gamescope, X11/Xvfb server, Wine process, or K1 process was launched. The live-game lock was not touched. The worktree was not edited.

## Round 9 verdict

**Specification verdict: FAIL.** The ledger schema, chain validation, failure-to-resolution binding, tri-state identity, pidfd-only signaling, post-`Popen` start capture, and signal-error-then-reap resolution all hold as written. The external head is checked at every consumer. But the implementation never gives the operator an independent head. The run creator discards the initial head. The failure append discards the new head. The acceptance error omits both the failure ID and the head. The documentation tells the operator to hash the ledger file at review time. Every run's empty ledger also has the same bytes. So a same-user rewrite of the ledger back to the empty state after a cleanup failure passes acceptance, verification, and export admission while the retained child is unresolved. This is the round-8 completeness-anchor finding, still open in practice.

**Code verdict: CHANGES REQUIRED.** The bounded animated-pattern diagnostic is **not authorized**.

## Prior-finding disposition

Two numbering schemes exist for round 8. This file's R8-1..3 are listed first. The orchestrator's labels are in brackets.

- R8-1 [orchestrator R8-2], unreadable live PID treated as exited: **closed**. `_process_identity()` (`creative_accept.py:375-396`) returns `absent` only for `FileNotFoundError`/`ProcessLookupError`. `PermissionError`, other `OSError`, decode errors, truncation, and a nondecimal start are all `unreadable`. `recover_cleanup()` raises without writing on `unreadable` (`:425-426`) and on malformed reader output (`:423-424`). While the pidfd is held, it re-reads identity and refuses `unreadable`, `absent`, or a start mismatch (`:455-459`). Probe results: `unreadable_resolved=False`, `held_unreadable_resolved=False`, `gate_after_unreadable=False`, `r8_1_permission -> unreadable`, `r8_1_truncated -> unreadable`.
- [orchestrator R8-2], numeric-PID race: **closed**. Signaling happens only through `pidfd_send_signal` on a held pidfd, after the start identity is revalidated under the pidfd (`:436-461`). There is no numeric-PID fallback; missing pidfd support raises (`:439-440`). The wait is bounded by `pidfd_wait(descriptor, 2.0)`, and a survivor stays unresolved (`:466-469`). The descriptor closes in `finally` (`:476-478`). Probe results: `no_pidfd_resolved=False`, `survivor_resolved=False`, `reuse_resolved=False`.
- R8-2, non-exact cleanup schemas: **closed**. Record and payload key sets are exact, and every field is typed (`:131-173`). `_utc()` requires an aware timestamp with zero offset (`:107-112`). Each of these mutations, re-chained with fresh digests, was rejected even against its own self-computed head: invalid timestamp, naive timestamp, extra resolution member, missing failure `command`, bad tool SHA, bad wait list, cross PID, cross start, bad outcome, and a `True` PID. A non-dict resolution payload raises `AttributeError` instead of returning `False`; see R9-2 below.
- R8-3 [orchestrator R8-3], cross-bound or unrecoverable resolution: **closed**. Repeated recovery returns only a resolution the loader has already bound to the failure's exact `record_digest`, PID, and start (`:157-169`, `:417-420`). Probe: `repeat_returns_same=True`, and cross-PID and cross-start resolutions fail the loader. A signal error followed by a successful bounded reap now appends a failure plus a bound `signal_error_reaped` resolution (`recording.py:212-218`, `creative_accept.py:546-553`). Probe: `sigerr_failures_resolutions=(1, 1)`. The start identity is captured right after `Popen` (`recording.py:250-253`). Publishing a record with an empty identity is refused (`creative_accept.py:363-366`).
- [orchestrator R8-1], mutable cleanup files with no completeness anchor: **not closed**. See R9-1.
- R7-1 two-attempt acceptance: **closed for an honest ledger**. `test_unreaped_probe_persists_typed_cleanup_receipt` (`kpharness_gamescope_backend_test.py:1120`, assert at `:1137`) passes. It fails under rollback; see R9-1.
- R7-2 spaced `comm`: **closed**. Both `session.pid_start` and `_process_identity` return `424242` for the name `(a b) c) d)`.
- R6-1 tool swap: **closed** (`:1058`). R6-2 speed: **closed**; the replay gives `r6_speed_8_8 ready=False`.
- R5-1 private copy: **closed** (`:977`). R5-2 route binding: **closed** (`:1007`). R5-3 buffer cap: **closed** (`:1295`). R4-1 public swap: **closed** (`:961`).
- R3-1 whole-capture PTS: **closed** (`:1511`). R3-2 terminal frame below decoded count: **closed**, replay `ready=False`. R3-3 extra marker with no interval: **closed**, replay `ready=False`. R3-4: **closed**, covered by `:1402`/`:1511`.
- R2-1 end sample above terminal: **closed**, replay `ready=False`. R2-2 shared descriptor: **closed**, replay `ready=False`. R2-3 setup I/O mislabeled: **closed** (`:1786`).
- R1-1 failed capture gate: **closed**, replay `ready=False`. R1-2: **closed** (`:1383`, `:1402`). R1-3 xdotool timeout: **closed** (`:1796`, `:1811`). R1-4 input-option order: **closed**, replay `ready=False`.
- Round 0: absent markers, reversed markers, 2-frame/10-second interval, `-r 1`, `-vf setpts`, and a 250 ms poll claim all give `ready=False`. Findings 3 and 4 remain closed (`:1763`). The mutation "terminal `drop_frames` 999" now gives `ready=True` **by design**. This is not a regression. Drops are gated on the acceptance-interval delta (`display_backends.py:560`, `:582`, policy scope at `:610`), and the terminal total need only be at least the interval delta (`:606`). That is the resolution adopted for round-0 finding 5.

## Remaining findings

### Critical

#### R9-1. The cleanup-ledger head has no independent source, so a rollback to the empty ledger passes acceptance and export with an unresolved child

The external head is compared at every consumer: acceptance (`creative_accept.py:495`), the signed review field (`:567`), verification (`:332`, `:340`), export (`creative_export.py:33-36`, `:91`), and both CLIs. The check itself is sound. When the true head is supplied, a dropped-failure forgery is rejected (`mut_drop_failure_gate_clear_realhead=False`).

The defect is that nothing ever gives the operator the true head through a channel other than the mutable file:

- `creative.py:202` calls `initialize_cleanup_ledger(run_dir)` and discards the returned head. The execution receipt does not record it.
- `_persist_probe_cleanup_failure()` discards the head that `_append_cleanup_record()` returns (`creative_accept.py:371`).
- The acceptance error `canonical PTS re-probe cleanup failed: <detail>` (`:553`) carries neither the failure ID nor the new head. `main()` does not catch it and prints nothing on stdout.
- `docs/creative-runner.md:78` tells the operator to pass `SHA256_OF_FFPROBE_CLEANUP_LEDGER_AT_REVIEW`, which is a hash of the file under attack.
- The empty ledger's bytes are fixed (`:197-198`). Every run has the same initial head, `b80aca12...2f2e`. A carefully retained initial head therefore matches any rewritten empty ledger.
- The test helper derives the head from the file (`tools/kpharness_gamescope_backend_test.py:41`, `A.cleanup_ledger_sha256(Path(run_dir))`). The suite cannot detect this class.

Host probe (`probe_r9.py`, P2 and P3). An injected surviving FFprobe child made `accept()` append a failure. A same-user rewrite then restored the empty-ledger bytes. The operator followed the docs and hashed the file at review. The next acceptance used a successful probe:

```text
failure_error_message='canonical PTS re-probe cleanup failed: survived'
message_contains_failure_id=False
message_contains_new_head=False
retry_with_initial_head_blocked=True
rollback_head_equals_initial=True
rollback_accepted=True
rollback_verifies=True
rollback_export_admission=True
cli_failure_exception=ValueError
cli_failure_stdout=''
```

The end state is a signed accepted receipt, eligible for export, while the retained child is unresolved and has no durable record. This is the outcome R7-1 was Critical for. It uses the same same-user rewrite model as R4-1, R5-1, and R6-1.

Required repair:

1. Emit the head, together with any new failure ID, on every ledger transition, through a channel the operator retains outside the run directory. This covers run creation, the acceptance-failure path (stdout JSON and the exception), and recovery, which already prints its head.
2. Make the empty ledger unique per run, for example with a run nonce, so a replayed empty ledger cannot match.
3. Change `docs/creative-runner.md:78` to require the last head that the tool emitted, not a hash of the file.
4. Add a regression in which the head comes only from tool output. It should fail after a rollback to the empty ledger and after a dropped-and-rechained failure.

### Important

None.

### Minor

#### R9-2. A non-dict resolution payload escapes the gates as `AttributeError`

`_validate_cleanup_record()` calls `payload.get()` before it checks the payload type (`creative_accept.py:159`). `cleanup_state_clear()` catches only `OSError`, `ValueError`, `TypeError`, and `JSONDecodeError` (`:214`). `verify_acceptance()` catches `KeyError`, `TypeError`, `ValueError`, and `OSError` (`:342`). The export CLI catches `ValueError`, `OSError`, and `SubprocessError`. A resolution record whose payload is `5` produced `EXC AttributeError: 'int' object has no attribute 'get'` from `cleanup_state_clear` with both heads. The failure is closed (nothing passes), but a gate predicate crashes instead of returning `False`. Check `isinstance(payload, dict)` first.

#### R9-3. Concurrent ledger appends lose records

`_append_cleanup_record()` loads, appends, and atomically replaces the ledger with no lock (`:218-232`). Two interleaved failure appends left one failure (`concurrent_failures_retained=1`, no error). Round 8's exclusive-create files did not lose writes this way. The trigger requires concurrent acceptance or recovery commands on the same run. After R9-1 is fixed, the emitted head would expose the loss. Use a lock such as `flock` on the run directory or ledger for the whole load-append-replace.

#### R9-4. A surviving child with an empty start identity leaves no durable record

If `pid_start` returns `""` for a child that has not been reaped, `_persist_probe_cleanup_failure()` raises (`:363-366`) and no failure is written. The gate then stays clear. Probe: `empty_start_ledger_records=0`, `empty_start_gate_clear_initial_head=True`. For the process's own child this needs a `/proc` read failure, so it is unlikely. Still, it fails open for durable blocking. Record the failure with an explicit `identity_unavailable` state that permanently blocks, rather than recording nothing.

#### R9-5. Recovery does not bind the PID namespace

Failure records hold PID and start time but not a PID-namespace or boot identity. If recovery runs in a different PID namespace, `/proc/<pid>` is `absent` and the result is `already_exited` even though the child is alive. This is **not reproducible here**: the agent container and the host share PID namespace `pid:[4026531836]`. Consider recording `/proc/self/ns/pid` and `boot_id` and refusing on a mismatch.

#### R9-6. Two backend tests depend on the host `ffprobe`

`test_marker_bounded_cadence_recomputes_terminal_duplication` (`tools/kpharness_gamescope_backend_test.py:1660`) and `test_same_poll_markers_keep_byte_order_without_claiming_reverse_time` (`:1682`) inject `pts_probe`. But `_finalize_cadence()` still calls `probe_tool_identity(self.ffprobe)` (`recording.py:613`). That function uses `shutil.which` and hashes the real binary (`:227-236`). Inside the container, which has no `ffprobe`, both tests fail with `configured ffprobe executable was not found`. On the host, which has `/home/linuxbrew/.linuxbrew/bin/ffprobe`, they pass. Production behavior is correct and fails closed. The defect is test hermeticity only. Inject the tool identity in these tests.

## Verified round-9 behavior

- Ledger: one canonical file, created exclusively at run creation (`creative.py:201-202`, `creative_accept.py:93-104`, `:196-200`). It must be a unique regular non-symlink file with one link, is read no-follow and bounded, and is checked for a stable identity across the read (`:176-188`). Sequence, `prev_digest` chain, recomputed `record_digest`, unique IDs, and exact schemas are all validated (`:131-193`).
- Resolution binding: failure ID equals resolution ID, `failure_digest` equals the failure's `record_digest`, and PID and start are equal. Outcome, pidfd, signal, and wait values come from fixed enumerations (`:157-169`).
- Tri-state identity and pidfd recovery: as described in the disposition above (`:375-478`).
- Start identity: captured right after `Popen`, before any cleanup can reap (`recording.py:250-253`). A reaped signal-error case produces a resolved pair, not a malformed unresolved record.
- The external head is required at every requested boundary: acceptance and its CLI (`creative_accept.py:481-483`, `:591-610`), verification (`:318-341`), `accepted_receipt`, every export recheck, the export CLI, and the sidecar field `selected_cleanup_ledger_sha256` (`creative_export.py:20-38`, `:91`, `:117-122`).

## Round 9 validation

Host (the agent shell has no `ffprobe`, so the suites ran through `host-cmd`):

```text
/home/brunner56/.local/bin/host-cmd sh -c 'cd <worktree> && PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_backend_test.py 2>&1 | tail -4'
Ran 102 tests in 6.858s
OK

/home/brunner56/.local/bin/host-cmd sh -c 'cd <worktree> && PYTHONPATH=scripts/harness python3 tools/kpharness_creative_test.py 2>&1 | tail -4'
Ran 30 tests in 0.587s
OK

/home/brunner56/.local/bin/host-cmd sh -c 'cd <worktree> && PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_boot_repair_test.py 2>&1 | tail -4'
Ran 41 tests in 1.225s
OK
```

Host total: 173 passed.

Container:

```text
PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_backend_test.py
FAIL: test_marker_bounded_cadence_recomputes_terminal_duplication
FAIL: test_same_poll_markers_keep_byte_order_without_claiming_reverse_time
  ... 'capture_cadence_failed: ValueError: configured ffprobe executable was not found'
Ran 102 tests in 22.096s
FAILED (failures=2)
```

Probes run on the host:

```text
python3 /home/brunner56/kp-live-20260922/review-probes-r9-correctness/probe_r9.py
python3 /home/brunner56/kp-live-20260922/review-probes-r9-correctness/replay_r0_r7.py
PASS as probes; R9-1 through R9-4 reproduced; all prior receipt-level counterexamples rejected except the by-design terminal-drop case
```

## Diagnostic authorization

**NOT AUTHORIZED.** Close R9-1 so that every ledger transition emits a head the operator retains, the empty ledger is unique per run, the docs require the tool-emitted head, and a regression proves rollback fails. Then rerun the host-only acceptance and export review before one bounded animated-pattern diagnostic. K1 stays behind a passing diagnostic and needs separate authorization.

## Cross-check (read after verdict formed)

The companion adversarial review contains no round-9 section yet. Its R8-1 (`task7-capture-cadence-adversarial-review.md:743-757`) required a head "durably committed outside the mutable run directory" that "cannot be restored from pre-failure run evidence". R9-1 shows that part is still unmet: the chain exists, but the head is never emitted, and the empty-ledger state can be replayed. Verdict unchanged.

Round 9 correctness verdict: FAIL

---

# Round 10 re-review

Date: 2026-09-27

Implementation report reviewed: `.superpowers/sdd/lua-boundary-validation-plan/ta[REDACTED].md`. Brief: `task7-capture-cadence-round-10-brief.md` (Parts A, B, C).

Probes live in `/home/brunner56/kp-live-20260922/review-probes-r10-correctness/`: `probe_r10.py` (ledger, head, recovery, schema), `content_noise.sh` + `content_ratio.py` + `dif_hist.py` (content gate on synthetic lavfi encodes), `suites-container.txt`, `suites-host.txt`. The encodes are `/usr/bin/ffmpeg -f lavfi` synthetic sources with the recorder's exact encoder settings (`libx264 -preset ultrafast -crf 28 -pix_fmt yuv420p`). No x11grab, no capture, no Gamescope, Xvfb, Wine, mpv, or game. The live-game lock was not touched. The worktree was not edited. A foreign `wineserver` (pid 2547167, GE-Proton) is running on the host. It was only observed. The diagnostic preflight would refuse on it.

## Round 10 verdict

**Specification verdict: FAIL.** Part A holds. The head is now external, unique per run, and emitted on every transition, and every R9 counterexample is refused when the head comes only from tool output. Part B geometry holds against `Xext/shm.c:639-654`. Part C's driver meets its structural requirements. But the content gate's distinct-frame measurement counts x264 re-encoding noise as a change. A capture in which every second frame is a stale duplicate passes the animated-diagnostic 99% criterion at 99.58%. The criterion the brief added to separate fresh 60 FPS frames from repeated ones cannot make that separation.

**Code verdict: CHANGES REQUIRED.** The animated-pattern diagnostic is **not authorized**. Its content criterion could return PASS on the exact failure it exists to detect.

## Critical

#### R10-1. Distinct-frame counting treats lossy-encoder noise as a pattern change, so a half-stale capture passes the 99% diagnostic gate

`evaluate_content()` counts a frame as changed when any of `ydif`, `udif`, or `vdif` is `> 0` (`display_backends.py:211-212`). The master is lossy (`recording.py:1114`: `libx264 -preset ultrafast -crf 28`). x264 codes a repeated source frame as a P-frame against the previous reconstruction, which has quantization error. The decoded duplicate therefore differs slightly from its predecessor. `signalstats` reports YDIF of roughly 0.07 to 0.14 for it, not 0.

Production `probe_frame_content` + `probe_frame_pts` (brew ffprobe 9.0.1, `/proc/self/fd`), then production `evaluate_content` over a 1 s to 9 s interval (`content_ratio.py`, `dif_hist.py`):

```text
clip                         true fresh share   distinct_ratio  animated-diagnostic-v1  game-capture-v1
static_flat (color)          0%                 0.0             failed (black+static)   failed
static_pattern (testsrc2 f0) 0%                 0.0021          failed                  failed
static_pattern + noise       0%                 0.023           failed                  failed
half_dup (testsrc2 r=30->60) 50%                0.9958          PASSED                  passed
tenth_fresh (r=6->60)        10%                0.7996          failed                  passed
anim60 (testsrc2 r=60)       100%               1.0             passed                  passed

half_dup YDIF quantiles, duplicate frames: [0.0, 0.0695, 0.0964, 0.1129, 0.1354]
half_dup YDIF quantiles, fresh frames:     [1.9667, 2.119, 2.6176, 3.217, 4.0915]
anim60   YDIF quantiles, all frames:       min 1.2684, max 2.4878
```

On the orchestrator's question: encoder noise does **not** let a truly static source pass. Static sources reach at most 2.3%, below the 5% game minimum. The flat source also fails the black/variance check. The failure is in the other direction. Noise turns *duplicated* frames into "distinct" frames. Suppose Gamescope or Xwayland updates the mpv window at 30 Hz while x11grab samples at 60 Hz. PTS cadence is then perfect, FFmpeg reports `dup_frames=0`, and the content gate reports 99.58%. All 18 diagnostic criteria can pass. The brief's MD5 example has the same defect on this master, because a duplicate with YDIF > 0 has different decoded bytes.

Required repair (pick one and prove it red-first with these clips):
- Record the diagnostic losslessly (for example a separate reviewed `-qp 0` or FFV1 diagnostic command form). A duplicate is then bit-identical and gives DIF 0. `_window_capture_matches` must admit that form only for the diagnostic.
- Or count a change only above a noise floor that is a policy field. The measured separation for testsrc2 at crf 28 is 0.14 or less for duplicates and 1.27 or more for fresh frames. Add regressions that use `half_dup`- and `tenth_fresh`-shaped rows and fail at 99%.
- Or read a frame counter embedded in the pattern.

For `game-capture-v1`, the same inflation makes the 5% ratio an upper bound on real change. Record that as a limit in the evidence.

## Important

None.

## Minor

#### R10-2. A commitment log that stops validating mid-acceptance suppresses the survivor record

`accept()` validates the log at entry (`creative_accept.py:691`). `_append_cleanup_record()` validates it again *before* taking the lock and writing (`:390`). If the log is removed, replaced, or gains a hard link (for example a `cp -l` backup) while the probe runs, a `ProbeCleanupError` leads to a `ValueError` and no ledger record. Nothing goes to stderr. The CLI prints only `commitment log is missing`. The gate stays clear under the launch head, and the next acceptance succeeds. The child remains alive and unrecorded, which is the R7-1 outcome. Probe (`probe_r10.py` P8/P8b):

```text
P8_exit_stdout=(1, '{"ok": false, "error": "cleanup commitment log is missing; create it outside the run directory"}')
P8_stderr_heads=0
P8_ledger_records=0
P8_gate_clear_with_launch_head=True
P8_next_accept_with_launch_head_exit=0
P8b_hardlinked_log_records=0
P8b_gate_clear_with_launch_head=True
```

This is Minor because it needs the log to break within the acceptance window. A same-user actor could suppress the record just as easily by killing the acceptor. Fix: append the failure under the lock first, emit the head on stderr, then fail on the log write. The ledger then blocks, and the operator holds the stderr head.

#### R10-3. The diagnostic's FFprobe children do not inherit the lock descriptor

`with_inherited_descriptor` wraps the recorder's `popen` (`capture_diagnostic.py:288`, `:307`). But the recorder's cadence and content probes call `probe_frame_pts` and `probe_frame_content` with the default `subprocess.Popen` (`recording.py:609-611`), so they do not get the lock fd. A surviving probe is still caught by the post-run name scan (`capture_diagnostic.py:549`), so the verdict fails closed. The brief's rule that the lock passes to every child does not hold for these two children.

#### R10-4. Preflight skips processes whose `/proc` entries it cannot read

`process_inventory()` silently `continue`s on `OSError`, `ValueError`, or `IndexError` (`capture_diagnostic.py:120-121`). A forbidden process with an unreadable `cmdline` or `stat` is omitted instead of refusing. `comm` and `stat` are normally world-readable, so the exposure is small. Fail closed: record the entry as unreadable and refuse.

#### R10-5. The commitment log is same-user writable

This is an operational boundary, not a code defect. After a rollback to the launch bytes, a forged head line appended to the log becomes "the last line for this run's nonce" (`docs/creative-runner.md:89-90`). The captured stdout/stderr head still refuses. Probe P2b: `P2b_log_last_head_is_forged=True`, `P2b_stdout_head_still_refuses=True`. The docs should rank the captured CLI output above the log, or tell operators to keep the log append-only (for example `chattr +a`) or off-host.

## Closed findings and additional probes

Every head below comes only from captured CLI stdout/stderr or the commitment log, never from the ledger file (`probe_r10.py`).

- **R9-1 (rollback): closed.** Positive control: an honest run accepts with the logged launch head (`P0_honest_accept_exit=0`, `P0_honest_verifies=True`). Failure path: `P2_fail_exit=1`, and stdout carries the failure ID and head. The stdout, stderr, and log heads are equal (`creative_accept.py:772-777`, `:850-854`). Each attack below then gives `exit=1 ok=False receipt=pending` and `gate_clear=False` under the tool head:
  - reset to the exact launch bytes;
  - a fresh ledger with a new nonce;
  - deletion;
  - a forged, rechained failure-plus-resolution pair;
  - dropping records under a new nonce.
  Only the stale launch head admits a reset-to-launch ledger (`P2_reset_to_launch_accept_with_STALE_launch_head=exit=0`). That is by design; the docs require the last head.
- A1 nonce: `_launch_bytes` (`:262`), `initialize_cleanup_ledger` (`:359-368`). `P1_launch_heads_differ=True`.
- A2 emission: `_emit_head` (`:313-338`) is called from init and from the single mutation path (`:413`). Launch validates the log before `mkdir` and initializes before any child (`creative.py:176-181`, `:205-212`). `P1_launch_logged=True`.
- A3: `CleanupLedgerChanged` (`:40-46`) carries both values. The CLI catches it and exits 1.
- A5 regressions: `tools/kpharness_gamescope_backend_test.py:1798-1840` take the head from `self.logged()` or CLI stdout (`:1734-1762`). The file-hashing helper (`:65-76`) is not their head source. Holds.
- R9-2 non-dict payloads and schema minors: closed. Each of these, rechained under its own self-computed head, gives `gate_clear=False` with no exception escaping:
  - bool `sequence`, float `schema`, bool ledger `schema`, a float wait, bool PID in the failure or resolution;
  - an int or list payload, an unhashable `failure_id`, a non-string `boot_id`, a resolved `unavailable` identity;
  - `Z`, no-microsecond, and `+01:00` timestamps, and a resolution earlier than its failure;
  - a duplicate key, non-canonical spacing, a missing final newline, and `NaN`.
- R9-3 concurrency: closed. With a barrier, two appenders on the same head give `['ok', 'refused cleanup ledger head changed; ...']`, and one failure is retained (`_ledger_lock` `:341-356`, recheck `:395-396`).
- R9-4 empty start identity: closed. The ruling "permanently blocked" is within the brief. With `reaped` either False or True, the ledger holds `[('failure', 'unavailable')]`, the gate is blocked, and recovery refuses (`:554-565`, `:619-620`, `:248`).
- R9-5 boot and namespace binding: closed. Another boot or namespace refuses before the identity reader, which is a mock that raises if called (`:621-626`).
- PID reuse ruling: holds. A start mismatch before the pidfd opens resolves as `original_exited_pid_reused` / `not_needed` / `not_sent` / `start_mismatch`. The pidfd mocks raise if called. A mismatch after the pidfd opens refuses (`P3_held_start_changes=refused`). Both readers parse field 20 after the final `)` (`session.py:97-106`, `creative_accept.py:570-591`). `P3_same_start_parser=True`.
- Tri-state and pidfd: `unreadable` and survivor both refuse, and the gate stays blocked.
- Signal error then reap: stderr shows the events `['acceptance_failure', 'signal_error_reaped']`. The stdout head is the final one, and the gate clears only under it.
- R9-6 hermetic tests: closed. The container, which has no `ffprobe`, passes 121/121.
- Rounds 0 to 8 receipt replays (`review-probes-r9-correctness/replay_r0_r7.py`, rerun on the host): all give `ready=False`, except `r0_terminal_drop_999 ready=True`, which is by design as recorded in round 9. R7-2: `424242`. R8-1: `unreadable`.

Writer rulings:
1. The log must already exist; missing logs, symlinks, and hard links are refused: **holds**. It is within the brief.
2. The head goes on stderr, and stdout keeps its JSON: **holds**.
3. Schema 1 is refused: **holds**.
4. Zero border is required: **holds**, and it is also necessary. xwininfo's "Absolute upper-left" translates `(-bw,-bw)` to the outer corner, while ShmGetImage uses `pDraw->x/y`, the inside origin. With `bw=0` they coincide.
5. Root refusal on every Gamescope lease: **holds**. No other caller of the removed root matcher exists (grep).
6. signalstats `> 0` distinct counting: **does not hold**. See R10-1.
7. Game minimum 5%: holds for truly static content. It is inflated by R10-1.
8. Empty-start survivor stays blocked: **holds**.
9. PID-reuse resolution only before the pidfd opens: **holds**.
10. Explicit authorization flag: **holds**. It exits 2 before any file is created.

Part B geometry against `Xext/shm.c:639-654` (`/tmp/t7src/Xext_shm.c`):
- `!realized`: `IsViewable` is reported iff `mapped && realized` (`/tmp/t7src/dix_window.c:1617-1622`). The `viewable` condition therefore proves `realized`.
- On screen: the check uses `pDraw->pScreen->width/height`. `update_screen_size` sets the screen and root drawable sizes to the same values (`hw_xwayland_xwayland-output.c:235-246`). `xwininfo -root` therefore gives the checked screen size, and `equals_lease` pins root = lease = window at origin 0,0.
- Inside border: the check uses `stuff->x/y = 0` and width equal to the window's width. FFmpeg's `x11grab` uses `c->x`, `c->y` = 0 because the URL `:N.0` has no offset, and `-video_size` equals the lease size equals the window size (`xcbgrab.c:284-285`, `:599-610`, `:829-857`).
- Re-read: `_geometry` runs again right before `_popen`, with only dict assignments in between (`recording.py:1143-1161`). A mismatch refuses, and the result is frozen for watch/stop (`:850-862`). Verification recomputes from the recorded fields (`display_backends.py:166-180`, `:809-810`).
- The residual race after exec is covered by the unchanged SHM fallback watch.

Part C (`capture_diagnostic.py`), checked against the brief's criteria:
- Lock: taken and kept (`:476`), passed to the child (`:519`) and to lease, client, and recorder spawns (`:288`). The child's `canonical_lock_guard` finds the inherited flock through `KP_GAMESCOPE_REPO_ROOT` (`gamescope_socket.py:43-73`). `shared_lock_path` resolves the git common directory, so this is the canonical checkout's lock.
- Preflight `/proc` evidence: `:139-147`.
- Snapshot: `create_snapshot` then `verify_snapshot` (`:481-482`), and the child runs `-I -S -B` from it (`:510-513`).
- Commitments (route SHA, FFprobe ELF SHA, launch head) are printed and logged before the single spawn (`:489-505`).
- `mpv` testsrc2 at 60 FPS (`:86-92`). Real constructor signatures match the factory calls (introspected).
- Markers 3/30/1 s: `:309-313`. Cleanup order recorder → client → display, with every step attempted: `:318-321`, `:228-244`. Protected displays compared before and after.
- 18 criteria evaluated independently (`:357-421`), no retry, nonzero exit, and the media SHA printed (`:570-572`).

## Verification

```text
# container
PYTHONPATH=scripts/harness python3 tools/kpharness_{creative,gamescope_boot_repair,gamescope_backend,capture_diagnostic}_test.py
Ran 32 OK | Ran 41 OK | Ran 121 tests in 21.899s OK | Ran 14 tests in 3.004s OK

# host
/home/brunner56/.local/bin/host-cmd sh -c 'cd <worktree> && PYTHONPATH=scripts/harness python3 tools/kpharness_<suite>_test.py'
Ran 32 OK | Ran 41 OK | Ran 121 tests in 6.829s OK | Ran 14 tests in 1.835s OK
```

Total: 208 OK in both, which matches the orchestrator's count. (The boot-repair suite prints only `OK` through `tail -3`. Its count of 41 is from the writer report and round 9.)

```text
python3 review-probes-r10-correctness/probe_r10.py        # P0..P8 as quoted above
host-cmd: content_noise.sh && content_ratio.py <6 clips>  # R10-1 table
host-cmd: dif_hist.py half_dup.mp4 anim60.mp4             # R10-1 quantiles
host-cmd: review-probes-r9-correctness/replay_r0_r7.py    # rounds 0-8 replays
```

The suites pass, but they cannot detect R10-1. Their content fixtures use `ydif` 3.5 for every changed frame (`tools/kpharness_gamescope_backend_test.py:96-100`), so they never model duplicate-with-noise rows.

## Diagnostic authorization

**NOT AUTHORIZED.** Close R10-1 so that the distinct-frame count measures source changes, not re-encoding noise. Prove it red-first with half-duplicate and tenth-fresh rows or clips that fail at 99%. Then re-review before the single animated-pattern run. K1 stays behind a passing diagnostic and needs separate authorization.

## Cross-check (read after verdict formed)

The companion adversarial review has no round-10 section yet (`task7-capture-cadence-adversarial-review.md` ends with the round 9 cross-check at line 923). Verdict unchanged.

Round 10 correctness verdict: FAIL

## Round 11 verdict

I resumed the existing review artifacts rather than creating a second Round 11
section.  Before forming this verdict I inspected the writer report, the dirty
worktree status, the existing correctness scratch directory, and the report's
claimed source locations.  `git status --short --untracked-files=no` confirmed
the worktree remains intentionally dirty with many unrelated writers; this
review did not modify any source file.  A whole-worktree diff statistic timed
out after 12 seconds on the loaded MyBook volume, so it is not claimed as a
cleanliness check.

The evidence below is independent through the end of the first three findings.
Only then did I read `task7-capture-cadence-adversarial-review.md`; its two
post-verdict Important findings are retained in the cross-check because their
source and real-process-probe referents match the present tree.

### Critical

#### R11-C1. The selected 1.2 noise floor rejects a fully fresh, explicitly included slower testsrc2 pattern

claim: "1.2 is a valid per-policy distinct noise floor after including I-frame duplicates and slower patterns."

referent: `display_backends.py:43-46` fixes the animated policy at 1.2; the independent calibration probe explicitly includes `slow_half` and `slow_quarter` at `review-probes-r11-correctness/calib_r11.py:25-26`, labels source-frame hashes independently at `:28-32,51-55`, and calls the production `probe_frame_content` plus `evaluate_content` at `:42-57`.

checked: `cal_summary.out:10-11` reports `slow_half fresh min=1.2937 ... diag=passed ratio=1.0`, but `slow_quarter fresh min=0.8421 ... dup n=0 ... diag=failed ratio=0.1186`.  Thus every labelled frame is fresh in the latter input, yet only about 11.86% exceed the current 1.2 threshold.  The same evidence reports I-frame duplicate maxima through the normal duplicate families, including `r30_k1` at `cal_summary.out:7` (0.668).  I re-ran the complete earlier mutation set: `rerun_probe_r11.out` covers ledger rollback, log deletion and hard-linking, cleanup/recovery, schema and concurrency cases P0--P8; `rerun_replay_r0_r7.out` covers rounds 0--8 receipt mutations.  They retain their expected fail-closed results.  The legacy `probe_r9.py` cannot execute unchanged because it omits the now-required `commitment_log` keyword; its behavioral cases are superseded by P0--P8 in the rerun rather than counted as a pass.

verdict: does not hold

confidence: high.  The error is in the required calibration envelope itself, not an inference from a mock: source hashes say there are no duplicates, while the production probe and production gate fail.  Restricting the supported signal strictly to native-speed `testsrc2@60`, and rejecting any transformed/slow presentation before recording, would change the applicability of this finding; otherwise calibration needs a threshold/pattern whose fresh and duplicate distributions have a real separating margin.

This is Critical because the diagnostic's purpose is to decide whether the
capture path actually carries an all-changing full-frame test.  A fully fresh
input from the requested slower-pattern calibration set is classified as
static, so a negative diagnostic result cannot distinguish broken capture from
an invalid threshold.  The writer report's claim that the floor is 1.58x below
the smallest fresh frame only aggregates the native-rate set; it is contradicted
by its own slower-pattern measurement.

### Important

#### R11-C2. Signal delivery between fork and `Popen` return can leave an unregistered diagnostic child

claim: "SIGINT, SIGHUP, and SIGTERM during the diagnostic always allow ordered cleanup within the bounded budget."

referent: `capture_diagnostic.py:881-884` starts the child and only assigns `signals.child` after `deps.spawn_child` returns.  Before that assignment, `_SupervisorSignals.handler` raises `DiagnosticInterrupted` when `self.child is None` (`:744-748`).  The companion's independently run real-process probe is `review-probes-r11-adversarial/p11b_supervisor_spawn_window.py`, recorded in the companion Round 11 section at `task7-capture-cadence-adversarial-review.md:1061-1079`.

checked: source review after my independent verdict; companion probe injects the signal after fork but before the wrapper returns the Popen object and observes an already launched child with no supervisor identity/ordered cleanup path.

verdict: does not hold

confidence: high.  Blocking the interrupt set around spawn/registration and processing pending signals afterward, or using a pre-registered launcher/reaper, would settle it.

#### R11-C3. Child token plus lock check does not establish a non-forgeable parent authority boundary

claim: "`--child` refuses forgery/replay unless the parent holds the canonical live-game lock."

referent: the writer describes the construction at `capture_diagnostic.py:409-420`; the companion's source/probe analysis is recorded in its Round 11 R11-2 section immediately after the spawn-window finding in `task7-capture-cadence-adversarial-review.md`.

checked: source review after my independent verdict; a same-UID process can create its own pipe/token/config/commitments and hold the same lock before asking for `--child`.  The token proves possession of pipe bytes, not that the sanctioned supervisor minted them.  The check prevents accidental invocation but not the claimed launch authority forgery.

verdict: does not hold

confidence: high.  A parent-authenticated channel rooted in an already trusted, non-forgeable supervisor identity would change this conclusion.

### Findings that hold in this round

claim: "A surviving FFprobe child is retained as blocking evidence even if the commitment log disappears or becomes hard-linked during the probe."

referent: `creative_accept.py:441-490,644-710`; `rerun_probe_r11.out` P8 and P8b.

checked: rerun P8 reports one ledger record, one stderr head, blocked launch head and a refused next acceptance after log disappearance; P8b reports one record and blocked gate after hard-linking.

verdict: holds

confidence: high; an actual unwritable run directory that prevents both ledger and exclusive sidecar write remains the documented residual boundary.

claim: "The diagnostic run limit includes the full 1,442-second cleanup budget, and FFprobe deadlines scale by frame count."

referent: `capture_diagnostic.py:72-93,767-784`; `recording.py:36-47`; writer regression locations `tools/kpharness_capture_diagnostic_test.py:631-663` and `tools/kpharness_gamescope_backend_test.py:2471-2539`.

checked: arithmetic is exact: recorder `2 + 4*5 + 15 + 5 + 2*(30 + .2*3240)` = 1,398, plus source 4, display 25, margin 15 = 1,442; pre-cleanup 134 + cleanup 1,442 = 1,576.  `probe_deadline_seconds(2100)` is 450 seconds and is capped at 3,600.  This is code/test evidence, not a live cleanup-duration proof.

verdict: holds

confidence: high for the arithmetic and bound; a real overloaded host may still consume the full budget, as the report candidly notes.

### Cross-check after independent verdict

The companion adversarial review is now present and ends Round 11 with FAIL.
Its R11-1 and R11-2 correspond to R11-C2 and R11-C3 above.  Those findings do
not alter the calibration finding, but independently leave two additional
Important defects.  The companion's successful content and FD-inheritance
probes do not contradict R11-C1: they exercise native/selected patterns and
descriptor propagation, whereas C1 is the slower fresh pattern explicitly
included by the calibration source.

## Verification and limits

- Existing reviewer evidence was preserved in `/home/brunner56/kp-live-20260922/review-probes-r11-correctness/`; the reruns added `rerun_probe_r11.out`, `rerun_probe_r10.out`, and `rerun_replay_r0_r7.out` there.
- `rerun_probe_r11.out`: P0 honest acceptance/verifies; P2 rollback families stay blocked under the emitted tool head; P3 identity/recovery refusals and PID reuse behavior hold; P4 malformed ledger forms fail closed; P5 bounded signal-error/reap resolution has the final emitted head; P6 empty identity remains permanently blocked; P7 serializes same-head appends; P8/P8b retain a survivor record despite log loss/hard-linking.
- `rerun_replay_r0_r7.out`: all prior receipt counterexamples are `ready=False` except the already documented `r0_terminal_drop_999 ready=True`; robust stat parsing and unreadable/truncated `/proc` handling retain their expected evidence states.
- I did not start Wine, a game, Gamescope, Xvfb/Xwayland, mpv, or x11grab; I did not touch the live-game lock or signal any process.  The late host recalibration command did not return a fresh printable receipt on this heavily loaded MyBook mount, so C1 relies on the already completed calibration's independently labelled raw-source/production-probe receipt rather than claiming a second successful live rerun.

**Diagnostic authorization: NOT AUTHORIZED.**  Repair C1, C2, and C3 and
repeat the content calibration and real post-fork signal probe before the
single authorized diagnostic is considered.

Round 11 correctness verdict: FAIL

## Round 12 verdict

Independent correctness review. I resumed a previous reviewer's partial run that a rate limit had cut off. Its 47-encode calibration had finished. I reused those outputs and reran only what was missing: the summary, which had crashed on a sort tie, plus three new probes. I formed this verdict from the source and my own probes. After that I read the writer's Grill me section. I read the adversarial Round 12 section last. No source file was modified and no git write was made. I ran no Wine, game, Gamescope, Xvfb, Xwayland, mpv, or x11grab. The canonical lock was only `stat`ed. Every lock I used was private, and every process I signalled was started by a probe. Probes are in `/home/brunner56/kp-live-20260922/review-probes-r12-correctness/`.

The round-11 Critical (R11-C1) and both Importants are closed. Every finding below is Minor. One Minor corrects the writer's calibration number. The duplicate maximum is 1.2414, not 1.0167. The ≥3x margin still holds, but the headroom to the 1.3 band edge is 4.7%.

### Critical

None.

### Important

None.

### Minor

#### R12C-m1. The pinned duplicate maximum is understated. The real I-frame maximum is 1.2414, 4.7% under the band edge.

My calibration forces a duplicate onto every x264 I-frame (250, 500, 750) for all 7 levels. It covers 14 phase offsets at native speed, 7 at 4x, and 3 each at quarter speed and fully static. The recorder's codec arguments are used exactly. Labels come from the index map and are cross-checked with the md5 of each raw frame. Results (`summarize_r12c.py`, `cal/*.json`):

```text
ALL duplicates n=4230 max=1.2414 at isodup_fast4_k6 {'i': 750, 'lvl': 1, 'key': 'I'}
I-frame duplicates n=93 max=1.2414
fresh (calibration families) n=26781 min=14.8870 at isodup_static_k0
margins: floor/dupmax=3.142 freshmin/floor=3.817  band-edge 1.3/dupmax=1.047  freshmin/11.7=1.272
dups > 1.3: []   calibration fresh < 11.7: []
I-dup max by level: {-3: 1.1425, -2: 1.0539, -1: 1.2091, 0: 1.1996, 1: 1.2414, 2: 1.1649, 3: 1.2245}
```

claim: "Duplicates: 7,825 frames, max 1.0167" and floor 3.9 "is 3.84x above the largest duplicate" (writer report, Calibration)
referent: `cal/isodup_fast4_k6.json`, and 11 of my 31 isodup families exceed 1.0167
checked: host encodes at 1024x768, with production `probe_frame_content` and `probe_frame_pts` over `/proc/self/fd/N`
verdict: does not hold as a number. The ruling it serves still holds: floor/dup-max is 3.14x, which is ≥3x.
confidence: high. More I-frame phases could only raise the maximum further.

The failure mode is fail-closed. A duplicate above 1.3 lands in the band and gives `calibration_ambiguous`, never PASS. The cost is liveness. At 4.7% headroom, the one authorized run could come back ambiguous from encoder noise alone. `tools/kpharness_gamescope_backend_test.py:2398` pins `CALIBRATED_DUPLICATE_MAX = 1.0167`. Update it to 1.2414 and restate the margin (3.14x). The test at `:2437` still passes with the true value.

#### R12C-m2. Stale-buffer loops pass the content gate: a two-frame loop and a three-frame loop

Same finding as adversarial R12-2, reached independently:

```text
pingpong_native  (out[i] = src[i % 2])  759/52.927 fresh   passed 1.0000 separated
cycle3_native    (out[i] = src[i % 3])  759/51.963 fresh   passed 1.0000 separated
```

The gate measures only the size of each difference (`display_backends.py:256-257`). It does not check that the next pattern level followed. The pattern already carries that information: `pattern_yavg.out` shows yavg stepping through 38.7, 125.7, 209.7, 97.7, 179.7, 69.7, 151.7 and repeating. A level-sequence check (+3 mod 7 per fresh frame, +0 per counted duplicate) would reject loops, 7-skips, and partial frames. I know of no real capture mechanism that loops over 2 or 3 stale buffers, so this is Minor.

#### R12C-m3. "Never blames capture" when the step does not render is true by a one-frame margin at slow motion

This asks what happens if mpv shows the graph without the per-frame step, either because the step is dropped or because `eval` is ignored (`nostep_probe.py`, `nostep_probe.out`):

```text
step_dropped_contrast04 failed ['calibration_ambiguous'] b/i/a=0/479/0   min/med/max=2.002/2.557/3.685
step_eval_init          failed ['calibration_ambiguous'] b/i/a=0/479/0
step_dropped_slowq      failed ['calibration_ambiguous'] b/i/a=478/1/0   min/med/max=0.947/1.179/1.466
```

At native speed, the missing step is ambiguous with a wide margin. At quarter-speed underlying motion, it is ambiguous because of one frame out of 479 (max 1.466). With slightly less motion, every value would fall below 1.3. That would give a "separated" `capture_content_static`: a render fault blamed on capture. The graph pins testsrc2 at rate=60, so this needs two faults at once. Minor. The R12C-m2 level check would also close it, because it positively verifies that the step rendered.

#### R12C-m4. A loader-exec'd tool is not detected, and the residual list does not name it

Independently confirmed (adversarial R12-1). `ldso_probe.py`, `ldso_probe.out`:

```text
ldso_renamed_enc  detected= False match= None comm= ld-linux-x86-64 exe= /usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2
ldso_named_ffmpeg detected= False match= None comm= ld-linux-x86-64
```

Even a file literally named `ffmpeg` is missed. The loader is not in `WRAPPER_NAMES` (`capture_diagnostic.py:80-81`), so `argv[1]` is never examined. `_match_exe` hashes the loader (`:185-209`). `docs/creative-runner.md:672-675` lists the residuals as a different build, another user, a non-dumpable process, and a process started after the scan. Loader exec is not among them. Fix: add `ld-linux*`/`ld.so` to the launchers, or match tool `(dev, ino)` against `/proc/PID/map_files`. Alternatively, name the case in the residual list.

#### R12C-m5. `calibration_ambiguous` outranks safety failures, and the thread check counts only `threading` threads

These agree with adversarial R12-3 and R12-4. `evaluate()` sets the ambiguous verdict whatever the other criteria say (`capture_diagnostic.py:786-790`). The verdict is fail-closed: exit 1 at `:1132`, and every criterion is recorded. But a survivor or a protected-display change would carry a calibration label. Given R12C-m1, an ambiguous first run is plausible, so this deserves the fix: use FAIL when any non-content criterion fails.

`threading.active_count()` (`:1015-1016`) misses a raw `_thread` thread. `thread_count_probe.out`: `active_count 1 proc threads 2`. The supervisor starts no such thread today. `len(os.listdir('/proc/self/task')) == 1` would be exact.

### Closed findings and additional probes

- **R11-C1 (slow-quarter false pass): closed.** Against the new pattern, `clean_slowq` has fresh-min 51.84 and passes at 1.0. `isodup_slowq_k0-2` have fresh-min 15.19 or more and duplicates at most 1.19, and pass separated. `r30_slowq_k*` fail at 0.50 with `capture_content_static`, correctly blamed. The step makes fresh-frame change independent of testsrc2 speed. `clean_static` (testsrc2 frozen, step only) has fresh-min 51.74.
- **7-frame skips fail closed.** Every skip7 family is `calibration_ambiguous`: `skip7_every_*`, `skip7_once_*` (a single 7-frame jump, 1 inside the band), and `skip7_sparse_native`. Level-aliased fresh values fall between 1.73 and 6.86, all inside the band. The writer's claim that only an exact 7-frame skip repeats a level holds, and it never passes.
- **`calibration_ambiguous` implementation: holds.**
  - Band rule `display_backends.py:277-296`: open interval (floor/3, floor·3) = (1.3, 11.7), taken from the policy (`:57-59`) and not from the data.
  - The verdict recomputes separation from the hashed artifact (`capture_diagnostic.py:786-790`, `content_separation_status`).
  - `rows_probe_v2.out`, cases driven through `evaluate_content`:
    - one duplicate at 1.31 and one fresh frame at 11.69 each give ambiguous;
    - exactly 1.3 counts as below and exactly 11.7 as above;
    - band values outside the acceptance window are ignored;
    - 0.9% duplicates pass and 1.1% fail as static.
- **mpv `eq ... eval=frame`: unverified by execution (mpv not run).** Static evidence: host ffmpeg evaluates the exact `PATTERN_GRAPH`, and yavg cycles through the 7 levels per frame (`pattern_yavg.out`). `ldd` shows `/usr/bin/mpv` (mpv-0.41.0-5.fc44) and `/usr/bin/ffmpeg` (ffmpeg-8.1.2-3.fc44) resolving the same `/lib64/libavfilter.so.11`, `libavformat.so.62`, and `libavdevice.so.62`. The graph contains no comma (`capture_diagnostic.py:70-71`), and it is passed as a file argument, not an option (`:147`). If the step does not render, see R12C-m3.
- **Spawn signal mask: closed.**
  - The set is blocked before `spawn_child` (`capture_diagnostic.py:1029`).
  - `signals.child` and the identity are recorded inside the block (`:1034-1040`). The mask is restored in `finally` (`:1041-1042`).
  - The child installs its handlers and then unblocks, first thing in the cleanup `try` (`:636-642`, `unblock` at `:598-600`).
  - Reruns:
    - `rerun/p11b_supervisor_spawn_window.out`: `child_alive_after_supervisor_exit=False owned_started_after_supervisor_exit=[]`.
    - `rerun/spawn_race.out`: `owned_alive_3s_after_supervisor_exit []`.
    - `rerun/p11c_signals_per_phase.out`: ordered cleanup in every phase.
  - Known residual, unchanged: a SIGKILLed supervisor leaves the child alive (`child_alive_after_supervisor_death=True`).
- **`--child` canonical-lock fd check: closed.**
  - `held_lock_descriptor` (`gamescope_socket.py:81-107`) requires the passed fd and the trusted path to have the same `(st_dev, st_ino)`. It also requires that fd's own fdinfo to show `FLOCK ... WRITE <maj:min:ino> 0 EOF`, and it re-stats the path.
  - `lock_fs_probe.{container,host}.out`: the fdinfo key format `08:11:<ino>` matches the code's format. A second open of the same file without the flock is refused.
  - `trusted_repository_root` (`gamescope_socket.py:60-78`) ignores the environment. `verify_child_authority` uses it (`capture_diagnostic.py:499-503, 541-553`), and `_child_main` pins the variable afterwards (`:702-703`).
  - `rerun/p12_child_token.out`: `forged_pipe_commitments_env_redirected_lock: refused: ... lock descriptor is not the canonical lock file`.
  - `snapshot_child_root.out`: a real snapshot's trusted lock path equals the supervisor's `canonical_lock_path`.
- **Renamed binaries: closed as narrowed.**
  - `_match_exe` checks inode first, then SHA-256 for same-size files only (`capture_diagnostic.py:185-209`).
  - `exe_sha_probe.out`: `renamed_copy detected=True by=sha256`, `hard_link detected=True by=inode`, and `same_size_diff detected=False` (correct).
  - The unchanged R11 `p10_preflight.out` still shows `renamed_copy_exe_argv_comm: ADMITTED`, because that probe passes no tool identities. The supervisor passes them (`:971-972`).
  - The gap is R12C-m4.
- **Rounds 0-11 replays** (container, `rerun/`):
  - `replay_r0_r7.out`: all `ready=False` except `r0_terminal_drop_999 ready=True`, which is by design since round 9.
  - `probe_r10.out` and `probe_r11.out`: identical to round 11, with P4-P8b fail-closed.
  - `p13_lock_inheritance` and `p14_content_attacks` failed in the container on environment faults: no `/usr/bin/ffmpeg`, and the probe references the removed `animated-diagnostic-v1`. Their host runs are rc 0.
    - `p13_lock_inheritance.host.out`: the lock fd reaches the probes as designed.
    - `p14_content_attacks.host.out`:
      - plain testsrc2, upscaled, long, and fade-in are all ambiguous;
      - the three still-moving-box cases fail `capture_content_static`, separated;
      - `testsrc_v1_60` fails `capture_content_static`, separated;
      - the old-pattern `alternating_two_frames` is ambiguous.
- **Writer Grill, weakest first.**
  - #1 (forged snapshot manifest): that holds, as a documented trust-boundary statement. The adversarial review showed a byte-identical copied tree gets there without forgery. The supervisor's own lock choice has the same boundary.
  - #3 (dup-max vs band edge): the reasoning holds, but the number does not. See R12C-m1: 1.2414, not 1.0167.
  - #4 (mask leak): that holds (source lines above; the adversarial p15 sigblk values are all 0). Caveat: R12C-m5.
  - #2: not checkable here.
  - #5: fail-closed by code (`verify_snapshot` rehash).
  - My own grill question the writer missed: "Does the gate prove the pattern rendered at all?" No. See R12C-m2 and m3.

### Verification

- Calibration: `JOBS=3 python3 calib_r12c.py`, run on the host by the previous reviewer. `cal_run.log` and `cal_run2.log` show all 47 families done, and `cal/` has 47 JSON files. I read them with `python3 summarize_r12c.py`, after fixing a tuple-sort crash in the summary script. The output is quoted in R12C-m1 and in the closed items.
- `host-cmd python3 nostep_probe.py`: 3 encodes, output in R12C-m3.
- `python3 ldso_probe.py`: two `/bin/sleep` copies under the loader, both terminated by the probe. Output in R12C-m4.
- `python3 -c '<_thread probe>'`: `active_count 1 proc threads 2`.
- `host-cmd ldd /usr/bin/mpv`, `ldd /usr/bin/ffmpeg`, and `rpm -q`: output as quoted above.
- Suites (`suites/`, previous reviewer):
  - container: creative 33 OK, gamescope_boot_repair OK, gamescope_backend 142 OK (1 skipped), capture_diagnostic 50 OK;
  - host: the same;
  - all rc 0. This matches the orchestrator's 266 per environment.
- Not done: any real mpv, Gamescope, or x11grab path.

Open question I could not settle: will the real mpv to x11grab path keep every duplicate at or below 1.3, given only 4.7% synthetic headroom? One check settles it: `content_separation.inside_band == 0` and `duplicate_max` in the authorized run's `diagnostic-result.json`, plus a yavg +3-mod-7 step across the acceptance frames.

Round 12 correctness verdict: PASS

## Round 13 verdict

Independent correctness re-review. I formed my own view from the source and my own probes before reading the writer's round-13 report in full; I read the writer's Grill me section last. No source file was modified and no git write was made (`git log --oneline -1` still `ca329e5`, `git status --short` unchanged by me). I ran no Wine, game, Gamescope, Xvfb, Xwayland, mpv, or x11grab, and I never opened the live-game lock. Scratch is in `/home/brunner56/kp-live-20260922/review-probes-r13-correctness/`.

Method: diffed the owned files against the writer's `r13-baseline/` copies (`db.diff`, `cd.diff` in my scratch dir) to read the actual change, not the report's description of it; reran the writer's own probe scripts (`ldso_probe_r13.py`, `thread_probe_r13.py`, `evaluate_r13.py`) myself against production code; reran all four suites in both environments myself; and built one new probe (`btrfs_dev_probe.py`) the brief specifically asked for that no prior round had run.

### Critical

None.

### Important

None.

### Minor

#### R13C-m1. The btrfs lock-fd mismatch is confirmed by direct measurement, and its mechanism is narrower than the report's own hypothesis

The resume brief asked me to confirm or refute the btrfs note with a tiny probe. I wrote `btrfs_dev_probe.py`: open a file, take an exclusive flock, then compare `fstat(fd).st_dev` against the device the kernel prints in that same fd's `/proc/self/fdinfo` `FLOCK` line.

```text
# /home (btrfs, host-cmd):
fstat(fd).st_dev  = 45   (00:2d)
stat(path).st_dev = 45   (00:2d)      <- fstat and stat agree with each other
fdinfo FLOCK line: ... WRITE 1583320 00:23:178126739 0 EOF   <- but fdinfo reports 00:23, not 00:2d
computed key 00:2d:<ino> in fdinfo: False

# /run/media/.../MyBook (ext4, host-cmd), same probe:
fstat(fd).st_dev  = 2065 (08:11)
fdinfo FLOCK line: ... WRITE 1583378 08:11:39738466 0 EOF
computed key 08:11:<ino> in fdinfo: True
```

This narrows the writer's own hypothesis ("per-subvolume anon dev... differs from the lock-record dev"). The mismatch is not between two different callers' `stat()`s of the same path — `fstat(fd)` and `stat(path)` agree with each other (both 00:2d). It is between what `fstat`/`stat` report and what the kernel independently encodes into the *fdinfo FLOCK line itself* for the same fd, on btrfs only. `held_lock_descriptor` (`gamescope_socket.py:93,100`) and `canonical_lock_guard` (`:120,123`) both build their search key from `fstat(fd).st_dev`, so on btrfs that key can never appear in the fdinfo line, and a real, correctly-held lock is refused as "does not hold the exclusive lock". This is exactly the `RuntimeError` class the writer's own report logs under the btrfs-TMPDIR run.

Severity: the real live-game lock lives on the ext4-mounted repository (confirmed: `df -T /run/media/brunner56/MyBook` reports ext4; `df -T /home` reports btrfs), so this does not affect the one authorized diagnostic. It does mean any future host where the repository root or a redirected `TMPDIR` sits on btrfs will spuriously fail `canonical_lock_guard` regardless of round 13's changes. `gamescope_socket.py` is outside round 13's owned-file set, so I record this as Minor and out of scope for a fix here, but it is now a measured fact, not a hypothesis: **confirmed**, mechanism is fstat-vs-fdinfo device disagreement on btrfs, not a per-subvolume path issue.

### Verified as claimed

- **Level-sequence rule (item 1, R12-2/R12C-m2/m3).** Read `content_level_sequence`/`decode_levels` in `db.diff`. The delta classification is exhaustive and correctly labeled: `delta==step` with a small difference falls through to `duplicate_difference_with_step`, `delta==0` with a large difference falls through to `fresh_difference_without_step`, anything else is `step`. Reran `evaluate_r13.py` myself against the writer's cached encodes plus the R12-adversarial p18 cache, straight through production `evaluate_content`:
  - clean families (native, slowq, fast4, static, 34 s long): `passed`, resolution 3.93-1054, histogram 257-258 counts per level on the long clip — matches the table.
  - `cycle3_native` and `pingpong_native`/`abab_two_frames`: `failed`, `capture_content_sequence`, 357-359 violations, all `kind=step` — matches.
  - `nostep_contrast04`, `nostep_eval_init`, `nostep_slowq`: `failed`, sequence plus (ambiguous or static) — matches.
  - `torn_half_every100`/`torn_quarter_every100`: `failed`, sequence, 8 violations — matches.
  - `drift_dup_skip_native` and all four `isodup_*` families: now `failed` via sequence, 3 violations each, `kind=step` — this is the real behavior change the writer's grill answer #1 claims (a dup-then-skip pattern that passed the old size-only gate now fails). Confirmed independently, not just quoted from the writer.
  - `half_frozen_bottom`/`quarter_fresh_top`: still `passed` — the documented whole-clip-freeze residual reproduces exactly as claimed.
  - `tenth_fresh_top`: `failed` with only `calibration_ambiguous` (`seq=passed`) — matches.
- **Guard band and calibration constants (item 2).** `grep` on `tools/kpharness_gamescope_backend_test.py` confirms `CALIBRATED_DUPLICATE_MAX = 1.2414`, `CALIBRATED_FRESH_MIN = 14.887`, `CALIBRATED_LEVEL_RESOLUTION_MIN = 3.93`, and `policy['level_resolution_factor'] <= CALIBRATED_LEVEL_RESOLUTION_MIN / 2` is asserted. `docs/creative-runner.md` recomputes 3.14x, 3.82x, band (1.95, 7.8), 1.57x, 1.91x; I recomputed all five ratios by hand from the pinned constants and they check out (3.9/1.2414=3.142, 14.887/3.9=3.817, 1.95/1.2414=1.571, 14.887/7.8=1.908).
- **Label precedence (item 3).** Read the `evaluate()` diff: `only_ambiguous` requires separation ambiguous, all content failures prefixed `calibration_ambiguous`, and no non-content criterion failing; `_cadence_recomputed_apart_from_content` correctly re-adds `cadence_evidence_recomputed` to `non_content` only when the content-blind recomputation *also* fails, so a genuine cadence fault can't hide behind a folded-in content failure. The three named tests exist at the claimed lines and run clean inside the 57/57 `capture_diagnostic` count I reran myself.
- **Dynamic loader (item 4).** Reran `ldso_probe_r13.py` myself (not from the writer's saved output): all three loader launches (`ldso_renamed_enc`, `ldso_named_ffmpeg`, and the options-then-relative-path case) show `detected= True` with `loader_match= ffmpeg sha256`, and the correct `loader_program` resolved for each, including the relative-path-plus-loader-options case (`./enc` under `--library-path ... --argv0 x`).
- **Thread count (item 5).** Reran `thread_probe_r13.py` myself: `supervisor_thread_count()` reads 1 before and 2 after starting a raw `_thread`, while `threading.active_count()` stays 1 throughout — confirms the fix and the residual it closes.
- **Publication leaks (item 6).** `grep -n "/home/\|linuxbrew\|Homebrew" docs/creative-runner.md` finds nothing. `--ffprobe` is `required=True` with no default (confirmed by invoking `run --help` and a run missing `--ffprobe`, both live, not from source reading alone). `native_elf_identity` (unchanged, pre-existing) is applied to `options.ffprobe` and records `ffprobe_resolved_path`/`ffprobe_sha256`; it refuses non-regular files, non-executable files, and anything without ELF magic — a shell wrapper is refused.
- **Suites, both environments, rerun myself (not pasted from the writer's log):** container `creative 39 OK | gamescope_boot_repair 41 OK | gamescope_backend 155 OK (skipped=1) | capture_diagnostic 57 OK`; host (via `host-cmd`) identical counts. Matches the report's table exactly.
- **Hygiene.** `py_compile` on all four changed Python files: OK. No trailing whitespace. `git diff --check -- docs/creative-runner.md`: clean. `git log --oneline -1`: `ca329e5`, unchanged — no commits by the writer or by me.
- **`recording.py` unchanged, as claimed.** `diff -q` against `r13-baseline/recording.py`: identical.

### Not independently rerun

- The opt-in `RealEncodeContentTests` (`KP_R11_REAL_ENCODES=1`) — I relied on the writer's `real-encode-test.host.out` plus my own `evaluate_r13.py` rerun over the cached row files, which covers the same shapes (two-frame loop, three-frame loop, step-dropped) through the identical production `evaluate_content` path.
- Real mpv/Gamescope/x11grab. Out of scope per the brief; the writer's own report and both prior rounds already flag this as the one thing nothing here settles.

### Writer Grill, checked

- #1 (exact +3 vs a real late-frame dup+skip): holds as stated, and I reproduced the specific claim (`drift_dup_skip_native`/`isodup_*` now fail via sequence) myself rather than trusting the quoted table.
- #2 (factor 1.9 safety on the real path): not checkable here, same as the writer says.
- #3 (keeping policy id v2): holds — `content_recomputed` compares the full dict, so this isn't a version-skew hazard.
- #4 (cadence fault hiding under ambiguous): holds, confirmed by reading `_cadence_recomputed_apart_from_content`'s two-sided check.
- #5 (narrower band cost): holds; `tblend_average`'s move from ambiguous to separated-but-sequence-failed reproduced in my own `evaluate_r13.py` rerun (`res=3.21`, `fails=['capture_content_sequence']`).

My own grill question, closed by the new probe rather than left open: does the btrfs lock-fd gap look like a per-subvolume `st_dev` disagreement between callers, or something else? Neither — `fstat(fd)` and `stat(path)` agree with each other on btrfs; it's the fdinfo FLOCK line's own device encoding that disagrees with both. See R13C-m1.

Open question I could not settle, same as round 12: the real mpv-to-x11grab path's actual dup/skip rate and whether the +3-mod-7 exact rule ever fires on a healthy real run. The single check that settles it is unchanged: `content_level_sequence.violation_count` and its violation kinds, next to `content_separation`, in the authorized run's own `diagnostic-result.json`.

Round 13 correctness verdict: PASS
