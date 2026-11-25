# Capture cadence history

Historical reports combined verbatim in their original order. Statements and
verification results below belong to their recorded dates, not to this cleanup.
See `evidence-index.json` for original paths, hashes and byte offsets.



<a id="initial"></a>

---

Original file: `task-7-capture-cadence-fix-report.md`

# Task 7 Gamescope capture-cadence fix report

Date: 2026-09-27

## Scope

This slice changes only the Gamescope recorder's source drawable and its
capture/cadence evidence. It does not launch Wine, K1, Gamescope, X11 capture,
or real FFmpeg, and it does not add PipeWire, GStreamer, CFR interpolation, an
FPS filter, a second encoder, or timestamp rewriting.

The reviewed post-accept export implementation in `recording.py`,
`creative_export.py`, and the existing host tests was preserved.

## Implemented behavior

- The immutable `OwnedWindow`, PID/start identity, lease, private display,
  one-visible-window discovery, dimensions, and 250 ms continuous verifier stay
  as authorization evidence.
- The Linux recorder additionally proves the authorized window is at `0,0` and
  exactly covers both the lease dimensions and the private display root.
- Gamescope capture now reads normalized screen zero (`:N.0`) with
  `-draw_mouse 0`; the command has no `-window_id`.
- The encoder remains libx264, ultrafast, CRF 28, yuv420p, two threads, the
  requested acquisition FPS, and an MP4 master.
- Startup consumes machine-readable FFmpeg progress, requires a complete block
  with `frame >= 1` within five monotonic seconds, and validates the run-local
  regular non-symlink output.
- `ffmpeg.log` is scanned incrementally with overlap for both forbidden SHM
  fallback strings through orderly stop. Successful evidence is accurately
  named `no_fallback_observed`.
- Startup failures retain typed evidence and clean up only the owned FFmpeg
  process with SIGINT, a two-second wait, then kill and another two-second wait.
- Portable named markers, marker byte offsets, shared-process monotonic times,
  polling uncertainty, configurable cadence endpoints, FFmpeg terminal
  counters, ffprobe PTS evidence, interval metrics, and fail-closed cadence
  thresholds are serialized.
- Schema-2 recomputation rejects the old child-window command, duplicate source
  flags, mismatched display/lease/window identity, inexact coverage, caller
  display reuse, SHM fallback, incomplete diagnostics, and cadence status that
  contradicts the primitive metrics.
- Route status remains independent. Capture or cadence failure prevents overall
  acceptance and representative-success rendering while retaining partial media.

## Failure classes

The slice emits the stable capture failure strings requested by the brief:

- `capture_start_timeout`
- `capture_shm_fallback`
- `capture_progress_malformed`
- `capture_process_exited`
- `capture_output_invalid`
- `capture_log_read_failed`
- `capture_lease_lost`
- `capture_binding_changed`
- `capture_finalize_timeout`
- `capture_cadence_failed`
- `capture_markers_incomplete`

Marker/cadence failures are also retained in the portable cadence failure list
so capture authorization and cadence acceptance remain distinct.

## Host-only verification

The final verification commands are:

```sh
python3 tools/kpharness_gamescope_backend_test.py
python3 tools/kpharness_creative_test.py
python3 tools/kpharness_gamescope_boot_repair_test.py
python3 -m py_compile \
  scripts/harness/kpharness/recording.py \
  scripts/harness/kpharness/display_backends.py \
  scripts/harness/kpharness/creative_wine.py \
  scripts/harness/kpharness/creative.py \
  tools/kpharness_creative_test.py \
  tools/kpharness_gamescope_backend_test.py
```

All recorder launches in these tests use fake processes and mocked host queries.
No live acceptance content or animated diagnostic was run.

## Next gate

Stop after static review. The next action requires separate parent authorization:
run one serialized bounded animated-pattern diagnostic on the same owned private
Gamescope display. Do not launch K1 first. If it reports
`capture_shm_fallback`, retain the result and open a separate PipeWire adapter
slice rather than loosening cadence or timestamp gates.


<a id="round-1"></a>

---

Original file: `task-7-capture-cadence-fix-round-1-report.md`

# Task 7 capture-cadence fix round 1 report

Date: 2026-09-27

Inputs:

- `/home/brunner56/kp-live-20260922/task7-capture-cadence-fix-review.md`
- `/home/brunner56/kp-live-20260922/task7-capture-cadence-adversarial-review.md`

No real FFmpeg, ffprobe, Gamescope, X11 server, Wine process, or K1 process was
launched. No file was staged, reset, or committed.

## Deterministic findings closed

### Authoritative schema-2 recomputation

The central execution gate now rejects:

- absent, duplicate, reversed, or non-monotonic serialized markers;
- acceptance endpoints not bound to the captured marker list;
- false marker polling/uncertainty values;
- cached cadence status that contradicts frame count, inter-frame count, PTS
  span, effective FPS, requested slots, missing slots, interval FFmpeg deltas,
  missing/drop ratio, thresholds, or terminal progress;
- terminal progress that differs between capture and cadence evidence;
- child-window capture, duplicate source flags, and appended timestamp-policy
  changes including `-r`, `-vsync`, `-fps_mode`, `fps=`, and `setpts`.

The schema mutation regressions invoke `execution_evidence_ready()` directly,
which is the gate used by visual acceptance and export.

### Marker clocks and final drain

Named markers are polled every 100 ms. Window/lease identity remains on its own
250 ms schedule. Marker receipts use the actual 100 ms uncertainty and include a
strict observation sequence. Multiple markers found in one poll retain strict
native-log byte order and sequence with nondecreasing monotonic timing. Capture
serializes an explicit ordered marker status instead of inferring strict time
separation.

Recorder stop synchronously drains complete native-log lines before signaling
FFmpeg. It revalidates the frozen window, lease, root geometry, and exact
coverage immediately before signaling and again after finalization.

### Cadence arithmetic and interval drop evidence

Expected slots are computed from the first and last included PTS. Partial cells
between marker boundaries and frame timestamps no longer become false missing
frames. Perfect 60 Hz input passes offset one-second intervals.

Progress blocks retain their shared-process capture observation time. When
samples bound the marker interval, duplicate and drop evidence is computed as an
interval delta. Missing/drop acceptance uses the maximum of the PTS-derived
missing slots and that interval drop delta. Terminal counters remain separately
bound and recomputed.

### Route and capture separation

The route result, report artifact, predicates, and persisted steps are recorded
immediately after the route runner returns. A later capture check writes a
separate `capture_gate` failure and cannot relabel successful route predicates.

### Typed process failures and owned cleanup

FFmpeg spawn failure writes `capture-failure.json` with the stable
`capture_process_exited` class. Startup cleanup records the actual SIGINT, grace,
kill, wait, and outcome evidence.

If FFmpeg survives the post-kill wait, recorder stop raises, retains the exact
process handle and staging descriptors for retry, and records failed cleanup.
Session teardown therefore cannot mark the still-live recorder operation passed.

### Capture output and diagnostic files

FFmpeg writes to `continuous.mp4` through an inherited descriptor for a random
mode-0700 staging directory. The public master is published only after process
death by an exclusive hard link of the verified regular staging inode. An
existing public file or symlink is never followed or overwritten.

FFmpeg stderr and progress files are created exclusively with `O_NOFOLLOW`.
Incremental reads retain device/inode identity, reject truncation/replacement,
cap each read at 1 MiB, and cap an unterminated progress suffix at 64 KiB.

### Acceptance and export publication

Visual acceptance now binds reviewer, aware UTC acceptance time, review scope,
media digest, and execution digest into `acceptance_receipt_sha256`. Independent
tampering of reviewer, time, or scope invalidates acceptance.

The accepted receipt is published from an unpredictable exclusive
same-directory temporary file with file fsync, atomic replacement, directory
fsync, and a regular non-symlink byte-for-byte reopen check. Receipt symlinks are
rejected on acceptance and export.

Export opens the accepted master with `O_NOFOLLOW`, copies it into the private
export staging directory, verifies the copy against the accepted digest, and
encodes only that stable copy. A public-master swap and restore during rendering
cannot alter encoder input.

## Fresh verification

```text
python3 tools/kpharness_gamescope_backend_test.py
63 tests passed

python3 tools/kpharness_creative_test.py
30 tests passed

python3 tools/kpharness_gamescope_boot_repair_test.py
41 tests passed

python3 -m py_compile [eight scoped Python files]
PASS

git diff --check [tracked and untracked scoped files]
PASS
```

The creative suite intentionally prints the injected cleanup and late-capture
exceptions used by its negative-path tests; the suite exits zero.

## Remaining proof boundary

These mocked checks do not prove a live private-root acquisition, actual active
MIT-SHM use, real FFmpeg progress timing, GPU capture cadence, distinct game
renders, visual framing, or K1 behavior. The next step remains the separately
authorized, serialized animated-pattern diagnostic. K1 must not be the first
live validation. A `capture_shm_fallback` result remains a hard stop and input to
a separately scoped PipeWire adapter rather than permission to weaken this gate.


<a id="round-2"></a>

---

Original file: `task-7-capture-cadence-fix-round-2-report.md`

# Task 7 capture cadence fix: round 2 implementation report

Date: 2026-09-27

Worktree: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`

This round addresses every remaining Critical and Important finding in the two appended round-1 re-reviews. All validation remained host-only. No real FFmpeg, FFprobe, Gamescope, X11 server, Wine process, or game process was launched. No files were staged or committed.

## Completed repairs

- Schema-2 readiness now requires `capture_gate.status == passed`, `route.predicates_passed is true`, a nonempty completed route step list whose every step has `status == ok`, and the existing report artifact and completion timestamps. `schema2_receipt()` includes the capture gate and uses the same route primitives when computing `ok`.
- Visual acceptance verification and accepted export both rerun authoritative completed execution readiness. A refreshed digest cannot make an explicit capture failure acceptable.
- Root-capture argv validation now requires the producer's complete ordered FFmpeg command grammar, including the contiguous x11grab input-option segment before `-i`, one inherited descriptor progress target, and exactly one inherited staging-directory `continuous.mp4` output. Missing, changed, appended, or arbitrary destinations fail closed.
- Cadence readiness validates finite and legal numeric domains, reconstructs interval gaps, histograms, percentiles, maximum gap, threshold counts, frame/span/rate/slot arithmetic, and missing/drop ratios from serialized interval PTS. Total terminal duplicates must be zero.
- Marker receipts are bound to the capture startup monotonic origin within their declared 100 ms uncertainty. Acceptance interval bounds must lie within endpoint uncertainty.
- The producer serializes the included interval PTS and both cumulative FFmpeg progress samples bounding the interval. Readiness requires those samples to surround the selected interval and recomputes duplicate/drop deltas from their cumulative counters.
- Same-poll start/end markers retain byte/sequence ordering and use adjacent poll-uncertainty bounds for a conservative nonzero cadence interval.
- FFmpeg progress uses an inherited descriptor (`/proc/self/fd/<n>`) created with exclusive, no-follow semantics. A raced caller-visible progress symlink cannot redirect FFmpeg writes.
- All diagnostic/staging acquisition after preflight is inside the guarded start lifecycle. Setup collisions create typed `capture_setup_failed` evidence and close the log, progress descriptor, staging descriptor, run-directory descriptor, and owned staging directory. `stop()` is safe before start and after partial setup.
- Background and synchronous final binding checks catch `subprocess.SubprocessError`, including `TimeoutExpired`, and record terminal `capture_binding_changed` evidence.
- Documentation now describes inherited progress transport, same-poll interval bounds, serialized PTS/progress recomputation, and the route/capture gates.

## TDD evidence

The authoritative-gate regression was run before production changes and reproduced 11 independent false-ready categories: failed capture gate; failed predicates; failed or absent steps; missing or appended output; source option drift; nonzero terminal duplicates; negative/NaN or contradictory gap evidence; marker clock drift; progress bounds that do not surround the interval; reversed progress bounds; and cumulative counter/delta contradictions.

Lifecycle regressions cover same-poll finalization, setup collision cleanup, never-started stop, watcher timeout, final binding timeout, and progress-path symlink replacement while FFmpeg writes through the inherited descriptor.

## Final validation

```text
PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_backend_test.py
69 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_creative_test.py
30 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_boot_repair_test.py
41 tests passed

python3 -m py_compile [eight scoped Python files]
PASS

git diff --check [scoped implementation, test, and documentation files]
PASS
```

Total focused tests: 140 passed.

## Files changed in this task unit

- `scripts/harness/kpharness/recording.py`
- `scripts/harness/kpharness/display_backends.py`
- `scripts/harness/kpharness/creative.py`
- `scripts/harness/kpharness/creative_accept.py`
- `scripts/harness/kpharness/creative_export.py` (preserved prior round behavior; validated through the strengthened shared gate)
- `tools/kpharness_gamescope_backend_test.py`
- `tools/kpharness_creative_test.py` (prior round tests retained)
- `docs/creative-runner.md`

## Remaining proof boundary

These mocked/static checks establish deterministic lifecycle and receipt contracts only. They do not establish real FFmpeg inherited-progress compatibility, live private-root SHM capture, source cadence on the GPU path, visual framing, distinct rendered frames, or K1 behavior. The separately serialized bounded animated-pattern diagnostic remains the next live proof step after independent review authorizes it.


<a id="round-3"></a>

---

Original file: `task-7-capture-cadence-fix-round-3-report.md`

# Task 7 capture cadence fix: round 3 implementation report

Date: 2026-09-27

Worktree: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`

This round closes all Critical and Important findings in the appended round-2 reviews. Work remained host-only and mock-driven. No real FFmpeg, FFprobe, Gamescope, X11/Xvfb server, Wine process, or game process was launched. No files were staged or committed.

## Repairs

- Added the hard-coded, versioned `gamescope-cadence-v1` policy. Gamescope capture is fixed at 60 FPS with a 99% minimum rate, 0.5% maximum missing/drop ratio, and 50 ms maximum gap. The producer rejects another requested rate, serializes the policy, and the authoritative verifier requires exact policy and threshold equality.
- Added reusable authoritative PTS-summary validation. Every named interval must have strictly increasing finite PTS entirely inside its serialized bounds, exact counts/span/rate/slots/histogram/percentiles/maximum/gap counts, canonical thresholds, and a status derived from the trusted policy.
- Bound every named interval to its actual start/end markers within each marker's declared uncertainty. Duplicate marker-pair interval representations are rejected. The producer no longer emits the configured acceptance pair twice when it is also an adjacent named-marker interval.
- The whole-capture PTS summary is independently recomputed, including its missing ratio. Fabricated or partial whole-capture evidence is rejected.
- Terminal diagnostics must contain the exact canonical cumulative counters. Terminal `frame`, `out_time_us`, `dup_frames`, and `drop_frames` must be nonnegative integers, must not regress below the interval's right cumulative sample, and terminal encoded time must cover the measured whole-capture PTS clock. Terminal duplicates remain exactly zero, which also rejects equal nonzero left/right interval duplicate totals.
- Added structured capture transport metadata for the inherited progress regular-file descriptor and private output-directory descriptor. The verifier parses descriptor numbers from argv, requires both to be nonstandard and distinct, and requires exact metadata/argv role agreement.
- Start now tracks whether spawn was attempted. Every generic setup exception before `_popen()` is `capture_setup_failed`; `_popen()` failure remains `capture_process_exited`.
- Acceptance verification and export regressions confirm that terminal/right-sample contradictions remain rejected even after an attacker refreshes the execution and acceptance digests.
- Operator documentation now records the fixed policy, full PTS/terminal rules, and descriptor-role contract.

## Red-first evidence

Before production changes, the new authoritative mutation test reproduced ten false-ready receipt states:

1. Fully recomputed degraded cadence admitted by loosened thresholds.
2. Lowered requested capture rate.
3. PTS displaced outside the marker interval.
4. Duplicate contradictory acceptance intervals.
5. Fabricated whole-capture summary.
6. Zero terminal encoded clock.
7. Terminal frame regression below the right cumulative sample.
8. Equal nonzero left/right cumulative duplicate totals hidden behind a zero delta.
9. Aliased progress/output descriptor roles.
10. Standard or metadata-mismatched descriptor roles.

A separate lifecycle regression reproduced generic pre-spawn `OSError` being mislabeled as `capture_process_exited`. All eleven cases are now green.

## Final validation

```text
PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_backend_test.py
72 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_creative_test.py
30 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_boot_repair_test.py
41 tests passed

python3 -m py_compile [eight scoped Python files]
PASS

git diff --check [scoped implementation, tests, and documentation]
PASS
```

Total focused tests: 143 passed.

## Round-3 files edited

- `scripts/harness/kpharness/recording.py`
- `scripts/harness/kpharness/display_backends.py`
- `tools/kpharness_gamescope_backend_test.py`
- `docs/creative-runner.md`

Earlier task-unit changes in `creative.py`, `creative_accept.py`, `creative_export.py`, and `tools/kpharness_creative_test.py` were preserved and revalidated.

## Remaining proof boundary

These checks establish deterministic producer, lifecycle, schema, acceptance, and export contracts under mocks. They do not establish real FFmpeg inherited-file behavior, live Gamescope private-root capture, active MIT-SHM use, GPU cadence, distinct rendered frames, visual framing, or K1 behavior. The separately serialized bounded animated-pattern diagnostic remains the next live proof step only after both independent re-reviews authorize it.


<a id="round-4"></a>

---

Original file: `task-7-capture-cadence-fix-round-4-report.md`

# Task 7 capture cadence fix: round 4 implementation report

Date: 2026-09-27

Worktree: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`

This round closes all Critical, Important, and authoritative-field Minor findings from the appended round-3 reviews. Work remained host-only and mock-driven. No real FFmpeg, FFprobe, Gamescope, X11/Xvfb server, Wine process, or game process was launched. No files were staged or committed.

## Canonical media-to-PTS evidence

- The producer writes exactly one canonical `ffprobe-cadence.json` after the final master is published.
- The artifact is bounded to 250,000 frames and 16 MiB. It records schema version, exact master path and SHA-256, probe executable/method, frame count, and one finite strictly increasing ordered PTS list.
- Cadence execution evidence records the artifact's exact path, SHA-256, master SHA-256, and frame count.
- Readiness opens the artifact with `O_NOFOLLOW`, requires a regular bounded file, verifies its SHA-256, hashes the actual regular non-symlink master, compares both master identities, and validates the canonical list.
- Visual acceptance freshly reruns the bounded probe against the digest-verified master and requires exact ordered equality with the canonical artifact before signing. The accepted review record binds the artifact SHA-256.
- Acceptance verification and export rerun execution readiness, reopen and verify the artifact/master identities, and require the review-bound artifact digest. A coherent alternative cadence-perfect PTS history for the same master can no longer be accepted, even if its artifact and execution receipt hashes are refreshed before review.

## Authoritative projections and topology

- `whole_capture` must use the entire canonical PTS list, with bounds exactly equal to its first and last PTS.
- Every named, acceptance, and route interval must contain the exact inclusive ordered projection selected from that canonical list. Disjoint, shifted-lattice, widened-bound, omitted-subsequence, and fabricated-summary evidence fails closed.
- Terminal frame count must cover the canonical whole-capture frame count. Terminal encoded time must cover the canonical whole PTS clock.
- The receipt serializes configured required marker order, patterns, optional `effect_start`, and acceptance pair. Capture markers may contain only those names; required markers must appear exactly in configured order with matching patterns.
- The interval set must equal the union of all configured consecutive required-marker pairs and exactly one acceptance pair. Invented, missing, extra, and duplicate markers or interval pairs fail.
- The producer avoids emitting a duplicate acceptance pair and derives conservative uncertainty bounds for any same-poll consecutive pair.
- Route capture-clock bounds are stored in the route receipt. If present, `route_interval` is required, fully recomputed, and must be the exact canonical PTS projection for those bounds. If trustworthy route bounds are absent, route cadence evidence must be absent.

## Progress and policy scope

- Acceptance progress samples are related to canonical PTS prefixes. The left cumulative frame/time cannot advance beyond the interval boundary; the right frame count and encoded clock must cover the canonical prefix and final included PTS. Zero or insufficient right progress cannot enclose a populated interval.
- `gamescope-cadence-v1` now states its scope explicitly: rate, gap, missing-slot, and FFmpeg drop-delta gates apply to the acceptance interval; FFmpeg duplicate count applies to the whole capture.
- Terminal drops outside the accepted interval are permitted under that exact scope. Terminal duplicate count remains globally zero.

## Red-first evidence

Before production changes, seven new false-ready states were reproduced: disjoint/replaced whole history, invented marker evidence, unchecked route interval, zero progress frame/time around a populated interval, terminal frame count below the whole decoded count, bad canonical-artifact digest, and altered policy scope. Widened whole bounds were already rejected by the round-3 arithmetic validator.

Additional acceptance tests install a coherent alternative artifact and recomputed whole/interval summaries for the unchanged master, confirm readiness can validate the artifact as internally coherent, then prove that the mandatory fresh acceptance probe rejects it. Acceptance/export verification also rejects artifact/review digest drift.

## Final validation

```text
PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_backend_test.py
74 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_creative_test.py
30 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_boot_repair_test.py
41 tests passed

python3 -m py_compile [eight scoped Python files]
PASS

git diff --check [scoped implementation, tests, and documentation]
PASS
```

Total focused tests: 145 passed.

## Round-4 files edited

- `scripts/harness/kpharness/recording.py`
- `scripts/harness/kpharness/display_backends.py`
- `scripts/harness/kpharness/creative.py`
- `scripts/harness/kpharness/creative_accept.py`
- `tools/kpharness_gamescope_backend_test.py`
- `docs/creative-runner.md`

Earlier task-unit changes in `creative_export.py`, `creative_wine.py`, and `tools/kpharness_creative_test.py` were preserved and revalidated.

## Remaining proof boundary

These checks establish deterministic artifact, producer, lifecycle, schema, acceptance, and export contracts under mocks. They do not establish real FFmpeg/FFprobe inherited-file behavior, live Gamescope private-root capture, active MIT-SHM use, GPU cadence, distinct rendered frames, visual framing, or K1 behavior. The separately serialized bounded animated-pattern diagnostic remains the next live proof step only after independent re-review authorizes it.


<a id="round-5"></a>

---

Original file: `task-7-capture-cadence-fix-round-5-report.md`

# Task 7 capture cadence fix: round 5

Date: 2026-09-27

## Scope

This round closes R4-1 through R4-3 from both round-4 reviews. It remains a
host-only implementation: no Wine, game, Gamescope, X11 server, FFmpeg, or
FFprobe process was launched. All process behavior in the regressions is mocked.

## Changes

- Visual acceptance now opens the public master with `O_NOFOLLOW`, retains and
  checks its regular-file identity, copies and hashes that descriptor into an
  unpredictable private acceptance directory with exclusive creation, and
  probes only the stable copy. It verifies both stable-copy and public-master
  identity/digest after the probe. Public mutation during the probe is a typed
  acceptance failure.
- Export reuses the same stable-copy primitive, retaining the existing accepted
  receipt checks before and after rendering.
- Completed route evidence now opens the stated run-local `report.json` with
  `O_NOFOLLOW`, enforces a bounded regular file and exact SHA-256, validates the
  canonical `ScenarioRunner` report and successful step-result schema, and
  requires the duplicated receipt step list to equal the report list exactly.
  Missing reports, fake digests, arbitrary fields, malformed steps, and failed
  reports therefore fail readiness, acceptance, verification, and export.
- Canonical frame-PTS probing no longer uses `check_output`. FFprobe stdout is
  incrementally drained through a nonblocking pipe while the child runs. The
  child is killed and reaped on the 16 MiB limit or timeout; nonzero exit,
  malformed JSON, nonfinite timestamps, and more than 250,000 frames fail
  closed. Python reads at most 16 MiB plus one byte.
- Documentation describes the stable acceptance probe, canonical route report,
  and bounded ffprobe process behavior.

## Regression coverage

- A probe callback mutates and restores the public master while inspecting the
  private stable input. Acceptance rejects the changed public identity and the
  callback never receives the public master path.
- Route readiness rejects a missing report, a false report digest, and an
  otherwise passed step carrying an unsupported arbitrary field.
- The oversized-output test exposes a sparse mocked stream past 16 MiB without
  constructing that byte payload in Python, then proves the child was killed
  and reaped.

## Validation

Final serial run:

- `python3 tools/kpharness_creative_test.py`: 30/30 passed.
- `python3 tools/kpharness_gamescope_boot_repair_test.py`: 41/41 passed.
- `python3 tools/kpharness_gamescope_backend_test.py`: 77/77 passed.
- Total focused tests: 148/148 passed.
- `python3 -m py_compile` passed for the six owned harness modules and both
  focused test modules.
- `git diff --check` passed.

The expected mocked cleanup/capture diagnostics printed by the creative and boot
repair suites remain test fixture output, not live process failures.

## Files changed in round 5

- `scripts/harness/kpharness/recording.py`
- `scripts/harness/kpharness/display_backends.py`
- `scripts/harness/kpharness/creative_accept.py`
- `scripts/harness/kpharness/creative_export.py`
- `tools/kpharness_gamescope_backend_test.py`
- `docs/creative-runner.md`

No files were staged, reset, or committed.


<a id="round-6"></a>

---

Original file: `task-7-capture-cadence-fix-round-6-report.md`

# Task 7 capture cadence fix: round 6

Date: 2026-09-27

## Scope

This host-only round closes R5-1 through R5-3 from both round-5 reviews. No
Wine, game, Gamescope, X11 server, FFmpeg, or FFprobe process was launched.
All process behavior was exercised with mocks or pure filesystem operations.

## Descriptor-only acceptance probe

- Acceptance copies the retained `O_NOFOLLOW` public-master descriptor into an
  exclusive private file, verifies the copy with exactly one link, reopens it
  read-only, unlinks it, and requires the retained descriptor to have zero
  links before probing.
- FFprobe receives only `/proc/self/fd/<n>` and `pass_fds=(n,)`. There is no
  stable-copy pathname left to rename, replace, or restore.
- Stable and public identities now include device, inode, size, mtime, ctime,
  and link count in addition to SHA-256. The exact zero-link stable descriptor
  is fstat'ed and rehashed after the callback. A private write-and-restore can
  restore bytes and mtime but cannot restore ctime, so it fails acceptance.
- The canonical producer records the configured FFprobe command, its resolved
  regular-file path, and executable SHA-256. Readiness verifies that executable
  identity, the PTS artifact must contain the same identity, and acceptance
  invokes the verified resolved path rather than artifact-controlled text.

## Route-source and report binding

- The producer records the copied route's device, inode, size, mtime, ctime,
  link count, path, and SHA-256 and includes an execution identity binding the
  route scenario, K1 target, build/profile string, route digest, and runtime
  artifact hashes.
- Readiness opens `executed-route.toml` and `report.json` with `O_NOFOLLOW`,
  bounds and hashes both, verifies the route's recorded one-link identity, and
  parses the exact route bytes.
- Report target/scenario/build, step count, consecutive indices, and step
  descriptions must match the parsed K1 route and receipt build. The runtime
  artifact names must equal the K1 runtime set, and their current SHA-256 values
  must match both receipt artifacts and the route execution identity.
- Report execution metadata accepts only requested/effective and optional
  restored-or-retained game-speed fields. Values must be finite, non-boolean,
  in `(0,16]`, and obey requested/effective/retained consistency.
- The producer independently marks the route failed when the returned report
  scenario, target, build, step count, indices, or descriptions disagree with
  the selected route.

## Bounded probe cleanup and byte ceiling

- FFprobe cleanup performs two bounded two-second kill/reap attempts. It never
  calls an unbounded `wait()`, including the missing-stdout path.
- A child that survives both attempts raises `ProbeCleanupError`, which retains
  the exact process object for later owner-controlled cleanup. Acceptance fails.
- Each nonblocking read is limited to the remaining byte budget. Oversized
  output is rejected after retaining exactly 16 MiB plus one byte, even when
  the producer has a full 64 KiB chunk ready.

## Regression coverage

- The acceptance callback receives an inherited zero-link descriptor path.
- Private descriptor bytes changed and restored during the callback are rejected
  through ctime/descriptor identity even when their digest is restored.
- An artifact-selected probe executable fails readiness.
- Coherently rehashed wrong K2/scenario/build reports, fully substituted matching
  report/receipt steps, arbitrary execution keys, boolean/nonfinite speeds, and
  contradictory speeds fail readiness.
- A sparse full-chunk oversized stream proves exact 16 MiB-plus-one retention,
  kill, and reap behavior.
- An unkillable missing-stdout child records waits `[2, 2]`, raises the typed
  cleanup error, and exposes the exact child object through that error.

## Validation

Final serial run:

- `python3 tools/kpharness_creative_test.py`: 30/30 passed.
- `python3 tools/kpharness_gamescope_boot_repair_test.py`: 41/41 passed.
- `python3 tools/kpharness_gamescope_backend_test.py`: 81/81 passed.
- Total focused tests: 152/152 passed.
- `python3 -m py_compile` passed for the six owned harness modules and both
  focused test modules.
- `git diff --check` passed.

The creative and boot-repair diagnostic lines are expected mocked failure-path
output. They are not live-process failures.

## Files changed in round 6

- `scripts/harness/kpharness/recording.py`
- `scripts/harness/kpharness/display_backends.py`
- `scripts/harness/kpharness/creative.py`
- `scripts/harness/kpharness/creative_accept.py`
- `tools/kpharness_creative_test.py`
- `tools/kpharness_gamescope_backend_test.py`
- `docs/creative-runner.md`

No files were staged, reset, or committed.


<a id="round-7"></a>

---

Original file: `task-7-capture-cadence-fix-round-7-report.md`

# Task 7 capture cadence fix: round 7

Date: 2026-09-27

## Scope

This host-only round closes R6-1 and R6-2 from both round-6 reviews and closes
the durable-cleanup residual. No Wine, game, Gamescope, X11 server, FFmpeg, or
FFprobe process was launched. Process behavior was exercised with mocks and
native executable descriptors were inspected without executing them.

## Verified executable descriptor

- Acceptance opens the configured resolved FFprobe path with `O_NOFOLLOW`,
  requires a regular executable native ELF file, and hashes/fstats that retained
  descriptor against the producer-recorded tool identity.
- The fresh probe command uses `/proc/self/fd/<tool_fd>` and inherits that tool
  descriptor alongside the zero-link media descriptor. The configured pathname
  is never reopened for child execution.
- Acceptance rehashes and re-fstats the same tool descriptor after probing and
  rechecks the configured public path. Rename/install/restore changes ctime and
  fails; regardless, the probe callback observes only the original retained
  executable bytes.
- Script and unsupported executable formats fail closed rather than falling
  back to pathname execution.

## Independent route commitment

- `creative_accept` now requires `--route-sha256`, supplied independently by
  the reviewer/operator in the same manner as the reviewed media digest.
- The expected digest must equal the launch-selected `route_source` digest and
  is signed into `visual_review`, including the acceptance digest.
- `verify_acceptance`, `accepted_receipt`, and export all require the expected
  digest as an explicit caller input. The export CLI also requires
  `--route-sha256`, and the derivative sidecar records it.
- A coherent replacement of `executed-route.toml`, its stat identity/digest,
  report, duplicated steps, and execution identity remains internally ready but
  cannot be accepted using the independently retained launch digest.

## Route speed semantics

- Report `game_speed_requested` and `game_speed_effective` must equal the parsed
  executed route's `scenario.settings.game_speed` within the established exact
  tolerance. Internal requested/effective agreement at another speed fails.
- Optional retained speed must still equal effective speed; restored speed
  remains the prior valid speed reported by attached-run semantics.

## Durable unreaped-child evidence

- `ProbeCleanupError` retains the exact process, command, PID, and Linux process
  start identity after both bounded two-second waits fail.
- Before the acceptance CLI can exit, acceptance atomically writes
  `ffprobe-cleanup-failure.json` with failed status, failure type, exact PID/start,
  command, verified tool identity, wait bounds, and the identity-checked recovery
  requirement.
- The execution remains unaccepted and no cleanup-passed claim is emitted.

## Regression coverage

- Replace-for-invocation/restore proves the callback receives original ELF bytes
  through the tool FD and acceptance detects identity change.
- Both inherited descriptors are present during probing and are closed after the
  operation, covering descriptor lifetime and reuse boundaries.
- A direct mocked `probe_frame_pts` call proves argv element zero is the inherited
  `/proc/self/fd/<tool_fd>` path and both descriptors are in `pass_fds`.
- Coherent all-local route substitution passes internal readiness but fails the
  independent expected-route check.
- Consistent report speed `8.0/8.0` fails against a parsed 16x route.
- Wrong expected route SHA fails acceptance verification and export admission.
- An unreaped mocked child produces the durable typed cleanup receipt with exact
  PID/start identity and `[2, 2]` bounded waits.

## Validation

Final serial run:

- `python3 tools/kpharness_creative_test.py`: 30/30 passed.
- `python3 tools/kpharness_gamescope_boot_repair_test.py`: 41/41 passed.
- `python3 tools/kpharness_gamescope_backend_test.py`: 87/87 passed.
- Total focused tests: 158/158 passed.
- `python3 -m py_compile` passed for the six owned harness modules and both
  focused test modules.
- `git diff --check` passed.

Expected creative and boot-repair diagnostic lines are mocked failure-path output,
not live-process failures.

## Files changed in round 7

- `scripts/harness/kpharness/recording.py`
- `scripts/harness/kpharness/display_backends.py`
- `scripts/harness/kpharness/creative_accept.py`
- `scripts/harness/kpharness/creative_export.py`
- `tools/kpharness_gamescope_backend_test.py`
- `docs/creative-runner.md`

No files were staged, reset, or committed.


<a id="round-8"></a>

---

Original file: `task-7-capture-cadence-fix-round-8-report.md`

# Task 7 capture cadence fix: round 8

Date: 2026-09-27

## Scope

This host-only round closes R7-1 and R7-2, adds the independent configured-tool
commitment requested by the parent review, and completes the bounded probe-child
recovery contract. No Wine, game, Gamescope, X11 server, FFmpeg, or FFprobe
process was launched. All process behavior used mocks or pure filesystem logic.

## Independent configured-tool commitment

- Acceptance now requires `--ffprobe-sha256` as an operator/reviewer input
  established outside mutable run evidence.
- The expected digest must equal both the producer-recorded tool digest and the
  retained native ELF descriptor digest before execution.
- The digest is signed into `visual_review` and its acceptance digest.
- Acceptance verification, accepted-receipt loading, export, and the export CLI
  all require the same explicit digest. Export sidecars record it.
- A coherent replacement of the configured tool, cadence tool identity, and PTS
  artifact remains internally self-consistent but fails the external digest.

## Authoritative append-only cleanup ledger

- Every unreaped/signaling failure is written with a random 32-hex identity to
  `ffprobe-cleanup-failure-ID.json` using exclusive creation and directory fsync.
  A later failure cannot overwrite an earlier child identity.
- Each failure records failed status, exact PID/start identity, command, verified
  tool identity, bounded waits, signal errors, and recovery requirements.
- Acceptance, `verify_acceptance`, accepted-receipt loading, and export fail while
  any failure lacks a valid resolution. Malformed, symlinked, misnamed, or orphaned
  cleanup records also fail closed.
- Resolution records are separately and exclusively appended as
  `ffprobe-cleanup-resolution-ID.json`; original failures are never removed or
  relabeled.

## Safe recovery entry point

- `creative_accept RUN_DIR --recover-cleanup FAILURE_ID` reads the selected
  failure with `O_NOFOLLOW`, a 64 KiB bound, exact schema, and filename/id binding.
- Recovery reads the live PID start identity before any signal. A different start
  value is treated as PID reuse and no signal is sent.
- A matching identity receives only SIGKILL and bounded two-second disappearance
  polling. A surviving matching identity remains unresolved.
- An already-exited PID resolves without signaling. A ProcessLookupError race
  also proceeds safely to bounded identity polling.
- Successful recovery appends a resolution with the exact original PID/start and
  outcome. Repeated recovery reads the existing resolution without mutation.

## Robust process identity and cleanup races

- `ProbeCleanupError` now reuses `session.pid_start()`, whose final-right-parenthesis
  parser handles Linux process names containing spaces and embedded right parentheses.
- Exact nonempty PID/start identity is required by the cleanup failure schema.
- Each cleanup attempt catches `ProcessLookupError` from kill and still calls
  `wait(timeout=2)`. Other signaling errors also proceed to bounded wait and then
  become `ProbeCleanupError`; no signaling path skips reap and no wait is unbounded.

## Regression coverage

- Coherent run-local FFprobe/tool/artifact substitution fails the external tool SHA.
- Wrong external tool SHA fails verification and export admission.
- A successful second PTS callback cannot bypass an unresolved first child.
- Unresolved cleanup blocks accepted verification and export.
- Two cleanup failures produce two immutable failure records.
- Malformed, symlinked, and orphaned records block readiness.
- Matching recovery signals once and appends resolution; PID reuse sends no signal;
  already-exited recovery appends a no-signal resolution.
- Kill ProcessLookupError still performs bounded wait; permission/signaling failure
  becomes typed cleanup failure after bounded wait.
- A mocked `/proc/<pid>/stat` comm containing spaces and an embedded right parenthesis
  yields the exact field-22 start identity.

## Validation

Final serial run:

- `python3 tools/kpharness_creative_test.py`: 30/30 passed.
- `python3 tools/kpharness_gamescope_boot_repair_test.py`: 41/41 passed.
- `python3 tools/kpharness_gamescope_backend_test.py`: 95/95 passed.
- Total focused tests: 166/166 passed.
- `python3 -m py_compile` passed for the six owned harness modules and both focused
  test modules.
- `git diff --check` passed.

Expected creative and boot-repair diagnostic lines are mocked failure-path output,
not live-process failures.

## Files changed in round 8

- `scripts/harness/kpharness/recording.py`
- `scripts/harness/kpharness/creative_accept.py`
- `scripts/harness/kpharness/creative_export.py`
- `tools/kpharness_gamescope_backend_test.py`
- `docs/creative-runner.md`

No files were staged, reset, or committed.


<a id="round-9"></a>

---

Original file: `task-7-capture-cadence-fix-round-9-report.md`

# Task 7 capture cadence fix — round 9 implementation report

Date: 2026-09-27

## Scope

This round closes the three cleanup-lifecycle findings in the round-8 correctness and adversarial reviews. It remains host-only: no Wine, game, Gamescope, X11/Xvfb server, FFmpeg, or FFprobe process was launched.

## Implemented

- Replaced directory glob discovery of independently mutable cleanup files with one canonical `ffprobe-cleanup-ledger.json` per Gamescope run.
- The ledger has an exact top-level schema and exact failure/resolution record schemas. Every record includes schema, type, sequence, 32-hex ID, previous-record digest, UTC timestamp, payload, and recomputed record digest. The loader checks sequence, chain order, record digest, unique failure/resolution relationships, unique regular-file identity, exact field sets/types, and exact failure-to-resolution binding.
- Failure payloads bind PID/start, full command, producer tool identity, the two bounded waits, signal diagnostics, and fixed recovery requirements. Resolution payloads bind the exact failure record digest, PID/start, outcome, pidfd use, signal result, and bounded-wait result.
- Gamescope run creation exclusively creates the empty canonical ledger before execution. Missing, symlinked, hard-linked, malformed, truncated, reordered, forged, extra-field, orphan-resolution, and unresolved ledgers fail closed.
- Acceptance now requires an independently supplied `cleanup_ledger_sha256`, checks it against the exact current ledger bytes, signs it into `visual_review`, and includes it in the acceptance digest. Verification, accepted-receipt loading, every export recheck, the export CLI, and `export.json` require the same external head.
- Cleanup recovery requires the independently retained current ledger digest. Repeated recovery returns an existing resolution only after complete chain validation proves that it binds the selected failure's exact digest, PID, and start identity.
- Recovery process identity is tri-state. Only `FileNotFoundError` or `ProcessLookupError` proves absence. Permission, I/O, decoding, truncation, and stat parsing failures remain explicitly unreadable and unresolved.
- Automated signaling now requires Linux `pidfd_open` and `pidfd_send_signal`. Recovery validates start identity, opens a pidfd, revalidates start while holding the pidfd, signals only through the pidfd, and waits on pidfd readiness with a two-second bound. There is no numeric-PID signal fallback. Missing pidfd support refuses recovery.
- PID disappearance while opening a pidfd is accepted only after a second tri-state read confirms absence. PID reuse before or after pidfd acquisition refuses signaling. A signal/exit race is recorded as a resolved diagnostic only after pidfd readiness proves reap.
- FFprobe start identity is captured immediately after `Popen`, before any cleanup can signal or reap the process. Surviving-child publication requires a positive PID and nonempty captured start identity. A signaling error followed by a successful bounded reap appends a failure and an immediately bound resolution rather than creating an unrecoverable malformed record.
- Documentation now describes the cleanup-head input, pidfd-only recovery command, fail-closed states, and export commitment.

## Regression coverage

Added mocked host tests for:

- deletion, truncation, replacement, wrong external digest, and symlink substitution;
- reordered multi-record chains, altered payloads/record digests, and extra members;
- multiple append-only failures and exact failure/resolution chain preservation;
- permission-denied, malformed, absent, present, and reused process identities;
- pidfd unavailability, reuse detected while a pidfd is held, pidfd-only signal delivery, signal/exit races, bounded pidfd waits, and descriptor closure;
- repeated recovery returning only the exact validated resolution;
- signal failure followed by bounded reap producing a resolved ledger chain;
- acceptance, verification, accepted-receipt loading, export admission, and sidecar propagation of the independent cleanup-ledger digest.

## Validation

```text
PYTHONPATH=scripts/harness python3 tools/kpharness_creative_test.py
30 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_boot_repair_test.py
41 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_backend_test.py
102 tests passed

Focused total: 173 tests passed

python3 -m py_compile \
  scripts/harness/kpharness/recording.py \
  scripts/harness/kpharness/display_backends.py \
  scripts/harness/kpharness/creative_wine.py \
  scripts/harness/kpharness/creative.py \
  scripts/harness/kpharness/creative_accept.py \
  scripts/harness/kpharness/creative_export.py \
  tools/kpharness_creative_test.py \
  tools/kpharness_gamescope_backend_test.py
passed

git diff --check
passed
```

## Files changed in round 9

- `scripts/harness/kpharness/recording.py`
- `scripts/harness/kpharness/creative.py`
- `scripts/harness/kpharness/creative_accept.py`
- `scripts/harness/kpharness/creative_export.py`
- `tools/kpharness_gamescope_backend_test.py`
- `docs/creative-runner.md`
- `.superpowers/sdd/lua-boundary-validation-plan/task-7-capture-cadence-fix-round-9-report.md`

## Residual proof boundary

The tests prove deterministic schema, digest, acceptance/export, process-identity, and pidfd control behavior with mocked child and operating-system boundaries. They do not prove real FFprobe cleanup, live Gamescope capture, MIT-SHM use, GPU cadence, rendered-frame distinctness, visual framing, or K1 behavior. The requested live diagnostic remains outside this implementation round and was not started.


<a id="round-10"></a>

---

Original file: `task-7-capture-cadence-fix-round-10-report.md`

# Task 7 capture cadence fix, round 10: writer report

Date: 2026-09-27. Sole writer. Brief: `/home/brunner56/kp-live-20260922/task7-capture-cadence-round-10-brief.md`.
Worktree: `.worktrees/lua-boundary-validation` (branch `codex/lua-boundary-validation`).

Safety: every edit is inside this worktree. There was no reset, stash,
staging, commit, or push. No Gamescope, Xwayland, X server, Wine, game, mpv,
FFmpeg, or FFprobe process was started. The only host commands were
`command -v` / `rpm -qf` tool-presence checks and the test suites. The
canonical `tmp/harness-locks/live-game.lock` was never opened. Test lock paths
are temporary files, and one test asserts that the real path is never opened.
The diagnostic driver is checked in and was never run. Unrelated dirty changes
are preserved. A byte comparison against a session-start copy shows changes only
in the files listed under "Files changed".

## Results

| Suite | Container | Host (`host-cmd`, Python 3.14.7) |
|---|---|---|
| `tools/kpharness_creative_test.py` | 32 OK | 32 OK |
| `tools/kpharness_gamescope_boot_repair_test.py` | 41 OK | 41 OK |
| `tools/kpharness_gamescope_backend_test.py` | 121 OK | 121 OK |
| `tools/kpharness_capture_diagnostic_test.py` (new) | 14 OK | 14 OK |
| **Total** | **208 OK** | **208 OK** |

Round 9 baseline: 173 on the host, and 171 of 173 in the container (R9-6, two
FFprobe-dependent tests). The backend suite now passes in a container with no
`ffprobe`.

## Part A: external ledger head (R9-1) and minors

Line references are to `scripts/harness/kpharness/creative_accept.py` unless
another file is named. The regressions are in
`tools/kpharness_gamescope_backend_test.py` (class `CleanupLedgerHeadTests`,
lines 1764-1985) unless another file is named.

| # | Requirement | Code | Regression |
|---|---|---|---|
| A1 | Empty ledger has a random per-run nonce. The ledger is `{"schema":2,"nonce":<32 hex>,"records":[]}`, and the chain starts at the nonce-bound launch head. | `_launch_bytes` :262, `initialize_cleanup_ledger` :359, genesis link in `_load_cleanup_ledger` :283-287 | `test_launch_heads_are_unique_per_run_and_emitted_before_use` :1764 |
| A2 | Every ledger change emits one JSON head line (`kind: kpharness.cleanup-ledger-head.v1`, event, run_dir, nonce, sequence, head, failure_id). It goes to stderr and is appended to an operator log that must already exist outside the run directory. The log may not be a symlink or hard link, and may not be inside the run directory. Events: `run_initialized`, `acceptance_failure`, `signal_error_reaped`, `recovery_resolution`. | `validate_commitment_log` :295, `_emit_head` :313, called from `initialize_cleanup_ledger` :359 and `_append_cleanup_record` :386 (the only mutation path) | `test_commitment_log_must_exist_outside_run_and_never_link` :1776; `test_recovery_cli_emits_resolution_head_and_catches_refusal` :1842 |
| A2 | Launch prints the initial head before any child runs. The log is validated before the run directory is created. | `creative.py:176-181` (validate before mkdir), `:205-212` (initialize right after mkdir, before session boot), `:261-262` (`cleanup_ledger_launch` in receipt), `--cleanup-commitment-log` at `:412` | `tools/kpharness_creative_test.py`: `test_gamescope_launch_emits_unique_initial_head_before_any_child` :440 (boot observes the logged head equal to the ledger bytes), `test_gamescope_launch_refuses_missing_or_inside_commitment_log_before_run_directory` :462 |
| A3 | A failure raises `CleanupLedgerChanged(ValueError)` carrying `failure_id`, `cleanup_ledger_sha256`, and the head line. The message includes both. The accept and recover CLIs catch it, print `{"ok":false,...,"failure_id","cleanup_ledger_sha256","cleanup_ledger_head"}`, and exit 1. | class :40, raise :774, `main` :812 (catch :850) | `test_failed_acceptance_cli_prints_failure_id_and_head_and_exits_nonzero` :1788 (drives `A.main([...])` end to end; probes resolved at call time) |
| A4 | Docs: pass the last head the tool printed or logged; never hash the file at review time. The stale per-failure-file and `--recover-cleanup` text is replaced. | `docs/creative-runner.md`: acceptance command and warning; ledger section ("The head must come from outside the run directory..."); recovery command with `--cleanup-commitment-log`; the old `ffprobe-cleanup-failure-ID.json` paragraph now describes the single chain | n/a (docs) |
| A5 | Rollback, reset, forged pair, and deletion regressions. Each takes the head only from captured CLI stderr and stdout, or from the commitment log, and never from the ledger file. | n/a | `test_rollback_to_fresh_empty_ledger_is_refused_with_logged_head` :1798 (fresh empty ledger, new nonce); `test_reset_to_exact_launch_bytes_is_refused_with_logged_head` :1809 (byte-exact launch bytes; shows only the stale launch head would pass); `test_forged_failure_resolution_pair_is_refused_with_logged_head` :1819 (rechained forged resolution passes under its own head, refused under the logged head); `test_deleted_ledger_is_refused_with_logged_head` :1837. Each runs the acceptance CLI with the logged head and asserts nonzero exit, `ok:false`, `cleanup_state_clear(logged head) is False`, and a receipt still pending. |

Minors:

| Requirement | Code | Regression |
|---|---|---|
| Exact integers (`type is int`) for ledger `schema`, record `schema` and `sequence`, both waits, failure `pid`, and resolution `pid`. A non-dict payload or unhashable `failure_id` gives a typed `ValueError`, never an `AttributeError`. Duplicate JSON keys are rejected (`object_pairs_hook`). Bytes must equal the canonical re-serialization. The only timestamp form is `YYYY-MM-DDTHH:MM:SS.ffffff+00:00`; `Z` and forms without microseconds are refused. A resolution may not predate its failure. Loader `TypeError`, `KeyError`, `AttributeError`, and similar become `ValueError`. | `_UTC` :36, `_utc_now` :124, `_exact_int` :142, `_unique_object` :156, `_validate_failure_payload` :201, `_validate_cleanup_record` :226 (time order :254), `_load_cleanup_ledger` :266 (canonical :277, exception conversion) | `test_exact_schema_rejects_standins_nondicts_duplicates_noncanonical_and_time_order` :1874. 18 mutations, each against a fully resolved ledger and each with its own self-computed head. All give `cleanup_state_clear(...) is False` and a `ValueError` from the loader. |
| Appends take an exclusive `flock` on the run-directory descriptor (bounded 10 s) and recheck the caller-supplied head under the lock. A mismatch fails closed. | `_ledger_lock` :341, `_append_cleanup_record` :386 (recheck just before append) | `test_append_is_serialized_by_lock_and_refuses_stale_supplied_head` :1917 (held lock refuses; a second caller holding the same launch head is refused; one record is kept and the log head matches the file) |
| A surviving child with an empty start identity is recorded as `identity: "unavailable"` with the recovery text `UNRECOVERABLE_REQUIREMENT`. It can never be resolved, recovery refuses, and the gate stays blocked. | `_persist_probe_cleanup_failure` :550; resolution refused in `_validate_cleanup_record`; recovery refusal in `recover_cleanup` | `test_surviving_child_without_start_identity_blocks_permanently` :1945 |
| A different start at the recorded PID resolves as `original_exited_pid_reused` with `pidfd: not_needed`, `signal: not_sent`, and `wait: start_mismatch`. No pidfd is opened and nothing is signaled. | `recover_cleanup` :599 (resolution at :650); `_RESOLUTION_SHAPES` :194 | `test_cleanup_recovery_resolves_pid_reuse_without_signal_and_already_exited` :1282 (pidfd open and send mocks assert they are not called) |
| `boot_id` and `/proc/self/ns/pid` are stored in each failure. Recovery on another or unknown boot or namespace refuses before reading `/proc/<pid>`. | `_host_identity` :169; checks in `recover_cleanup` :624-626 | `test_recovery_refuses_other_boot_or_pid_namespace_before_concluding_absence` :1969 (identity reader never called; ledger unchanged) |
| Hermetic tests: `ffprobe=sys.executable` plus an injected content probe. | test file :2360, :2384 | Both pass in the container, which has no `ffprobe`. Before: the container baseline (session start) failed both with `configured ffprobe executable was not found`. |

## Part B: capture target correction

| # | Requirement | Code | Regression |
|---|---|---|---|
| B1 | Root capture is refused. `capture_target='root'` fails as `capture_target_rootless_root` when the lease's Xwayland argv has `-rootless`, or when it cannot be read (`xwayland_rootless` returns None). Any other Gamescope lease fails as `capture_target_unsupported`. Both happen before any geometry query or process. The Xvfb `X11Recorder` root path is unchanged. | `recording.py:386` (`xwayland_rootless`), `:1053-1066` | `test_root_capture_is_refused_on_rootless_or_unknown_xwayland` :2024 |
| B2 | Capture uses exact `-window_id` on the verified window. `xwininfo -id` and `-root` supply map state, absolute origin, size, border width, and root size. The `Xext/shm.c:639-654` conditions (viewable, inside screen, inside border) plus equality with the lease give `capture.geometry_precondition`. The geometry is re-read immediately before exec; a refusal gives `capture_geometry_precondition` and a change gives `capture_geometry_changed`, with no FFmpeg. Watch and stop checks compare against the frozen pre-exec read. `xwininfo` is added to `GAMESCOPE_TOOLS`. | `display_backends.py:132` (`geometry_precondition`), `:166` (`_geometry_evidence_matches` recomputes from recorded fields), `:26`; `recording.py:368` (parser), `:850` (`_geometry`), `:863` (`_binding`), `:1069-1083` (initial), `:1112` (`-window_id`), `:1143-1158` (pre-exec reread) | `test_geometry_precondition_refuses_each_shm_condition_before_exec` :2045 (unviewable, unmapped, four off-screen directions, size, border, root, foreign window, malformed, nonzero exit); `test_geometry_is_reread_immediately_before_exec_and_change_refuses` :2077 (the last two queries before `popen` are the xwininfo pair; drift refuses); `test_gamescope_recorder_captures_verified_window_after_geometry_precondition` :2411; `test_gamescope_recorder_refuses_offscreen_window_before_process_creation` :2437 |
| B3 | The MIT-SHM fallback gate and first-frame admission are kept unchanged. | `recording.py` `_admit_startup` and watch loop (untouched) | Existing `test_startup_fallback_is_typed_and_cleans_only_owned_recorder` and siblings still pass |
| B4 | Content gate before any cadence verdict. The configured FFprobe runs `-f lavfi -i movie=/proc/self/fd/N,signalstats` over an inherited master descriptor; only fd paths are accepted. `ffprobe-content.json` is hashed and bound to the master. `capture_content_black` fires when first-frame YMAX is at or below `black_luma_max` or when YMAX <= YMIN (zero variance). `capture_content_static` fires on zero changes or a changed ratio below the minimum; a frame is changed when Y, U, or V DIF > 0 inside the acceptance projection. A frame-count mismatch with canonical PTS gives `capture_content_failed`. Policies come from a fixed table: `animated-diagnostic-v1` (0.99) and `game-capture-v1` (0.05). The verifier compares the serialized policy to that table and recomputes from the artifact. | `display_backends.py:32` (table), `:191` (`evaluate_content`), `:223` (`_content_evidence_passed`), `:757` (required inside `_cadence_evidence_passed`); `recording.py:243` (shared bounded reader), `:319` (`probe_frame_content`), `:774-803`, `:815` (`_measure_content`) | `test_content_gate_rejects_black_and_static_before_cadence_can_pass` :2108; `test_content_probe_uses_fd_signalstats_and_bounded_reader` :2136 |
| B5 | Acceptance re-probes content over the same retained media and tool descriptors, inside the `ProbeCleanupError` block, and requires the exact rows. The visual review signs `content_artifact_sha256` and `geometry_precondition_sha256`, and `verify_acceptance` checks both. The export sidecar records `accepted_content_artifact_sha256` and `accepted_geometry_precondition_sha256`. Execution readiness now requires `_window_capture_matches`; `_root_capture_matches` is removed. | `creative_accept.py:747` (re-probe), `:783`, `:794-795`, `:524-527`; `creative_export.py:92-93`; `display_backends.py:763` | `test_execution_gate_requires_exact_window_geometry_and_bound_content` :2165 (14 mutations, including coherent re-hashed black, static, and short artifacts, forged origin, loosened or unknown policy, root form); `test_acceptance_reprobes_content_and_records_surviving_content_probe` :2211 (coherent substitution refused; field tamper with a recomputed acceptance digest refused; a surviving content-probe child is written to the ledger); export assertions in `test_reviewed_interval_includes_restoration_and_preserves_accepted_evidence` :448 |
| B6 | No CFR duplication and no silent non-SHM fallback. SHM BadMatch with verified geometry points to the PipeWire adapter. | Docs only | n/a |

## Part C: diagnostic driver (never run)

`scripts/harness/kpharness/capture_diagnostic.py`, tests in
`tools/kpharness_capture_diagnostic_test.py`. The CLI refuses without
`--authorized-single-run` (exit 2, no files created).

| Brief item | Code | Regression |
|---|---|---|
| Takes the canonical lock with the descriptor kept, and passes it to every child (`with_inherited_descriptor`, and `pass_fds` on the child spawn) | `acquire_lock`, `with_inherited_descriptor`, `supervise` | `test_supervisor_refuses_a_held_lock_before_preflight_snapshot_or_launch` :123; `test_supervisor_snapshots_then_prints_commitments_before_the_single_launch` :161 (one `pass_fds` entry); `test_child_orders_launch_markers_and_cleanup_and_passes_the_lock` :242 (mpv launched with fd 77) |
| Refuses on any `wineserver`, `swkotor`, `gamescope*`, `ffmpeg`, or `ffprobe` process not owned by this run, and writes `/proc` evidence (with `-auth` redacted) to `preflight.json` | `process_inventory`, `forbidden_processes`, `preflight` | `test_preflight_refuses_unowned_game_display_and_capture_processes_with_proc_evidence` :81; `test_supervisor_refuses_before_snapshot_or_launch_and_never_touches_canonical_lock` :104 |
| Fresh `create_snapshot` plus `verify_snapshot` with `DEFAULT_ENTRIES + ('kpharness.capture_diagnostic',)`; the child runs `-I -S -B` from the snapshot runtime | `SNAPSHOT_ENTRIES`, `supervise` | `test_real_snapshot_closure_contains_the_diagnostic_driver_and_verifies_source_equal` :152 (real copy into a temp directory); :161 (create, then verify, with those entries) |
| Pre-launch commitments: route SHA of `diagnostic-route.json`, FFprobe ELF SHA, launch ledger head. They are printed and appended to the commitment log before the single spawn. FFmpeg and FFprobe must each resolve to one native ELF; wrapper scripts are refused. | `route_document`, `native_elf_identity`, `supervise` | :161 (spawn sees the commitments line already printed); `test_wrapper_script_or_missing_capture_tool_is_refused_before_launch` :198 |
| Private lease; `mpv` `testsrc2` at 60 FPS with a fixed `--title`; single owned-window discovery (10 s); Part B recorder with `/usr/bin/ffmpeg`, brew ffprobe, and `animated-diagnostic-v1`; `pattern_start`, then 30 s, then `pattern_end` | `client_command`, `run_child` | :242 (sleeps `[3.0, 30.0, 1.0]`, exact marker lines, recorder kwargs) |
| Cleanup order recorder, client, display, with every step attempted; bounded client stop (SIGINT, 2 s, SIGKILL, 2 s); X0/X94/X100 socket and lock identities checked before and after | `ordered_cleanup`, `stop_client`, `protected_displays` | `test_ordered_cleanup_attempts_every_component_in_recorder_client_display_order` :213; `test_client_stop_interrupts_then_kills_only_the_owned_process_with_bounded_waits` :230; `test_child_failure_still_cleans_up_in_order_and_retains_error` :288 |
| Every criterion is evaluated and written to `diagnostic-result.json`. There are 18 criteria, including the brief's list plus `cadence_evidence_recomputed`, `acceptance_interval_matches_route`, `no_owned_survivors`, `snapshot_unchanged`, and `no_driver_error`. The ledger criterion uses the head the driver emitted, never `None`. The media SHA is printed. No retry; nonzero exit on any failure. | `evaluate`, `CRITERIA`, `supervise` | `test_complete_observation_passes_every_criterion` :336; `test_each_criterion_fails_independently` :341 (one mutation per criterion; each flips its own criterion and the verdict) |

## Rulings (fail-closed choices the brief did not settle)

1. The commitment log must already exist. "Missing" is refused rather than
   created, as is a symlink, a hard link (`st_nlink != 1`), or a path inside the
   run directory. Operators create the empty file first.
2. Head lines go to stderr, so each CLI's single-line stdout JSON contract is
   kept. The accept and recover CLIs also put the head on their stdout failure
   JSON. Commitment-log writes are one `O_APPEND` write per line, with no `flock`.
   Locking the log could deadlock on a leaked descriptor, which a round-10 test
   run showed.
3. The ledger schema moved to 2. Schema-1 ledgers from older runs are refused.
4. `xwininfo` "Absolute upper-left" is treated as the outer corner, including
   the border. That reading was not verified from source here. To stay
   fail-closed, `border_width == 0` is required, so the corner and the content
   origin coincide.
5. Root capture is refused on every Gamescope lease: rootless and unknown give
   `capture_target_rootless_root`, anything else gives
   `capture_target_unsupported`. `_root_capture_matches` was removed because
   no other backend used it; the Xvfb `X11Recorder` root path is untouched.
6. Distinct-frame measurement uses signalstats Y/U/VDIF > 0 against the
   previous decoded frame. The brief offered MD5 only as an example. This
   keeps the single configured FFprobe and the descriptor transport, and
   avoids adding FFmpeg as a second probe tool. A tiny difference that prints
   as 0.000000 counts as unchanged, which fails closed.
7. The game policy minimum is 5%. Zero changes always fail, whatever the
   policy.
8. A surviving child with no start identity stays permanently unresolved,
   even when it was reaped.
9. A start change while the pidfd is held still refuses
   (`test_pidfd_recovery_rechecks_identity_after_open_before_signal`). The
   reuse resolution applies only to the pre-pidfd read.
10. The diagnostic requires `--authorized-single-run`.
    `acceptance_interval_matches_route` also requires the acceptance pair to
    be `pattern_start`/`pattern_end` and its span to be at least 90% of 30 s.

## Red-first evidence

- Part A: after the fixture and regression edits, before implementation:
  `Ran 114 tests ... FAILED (failures=2, errors=58)` (`/tmp/r10-red-A-backend.txt`).
  The new tests failed because the API did not exist (`commitment_log`
  keyword, `CleanupLedgerChanged`, `_host_identity`). The pre-fix code had no
  head source at all, which is the R9-1 defect. The behavioural red for
  rollback is the round-9 reviewers' probe (`rollback_accepted=True`), not
  reproduced here. Creative: `Ran 32 tests ... FAILED (errors=5)`
  (`TypeError: initialize_cleanup_ledger() missing 1 required keyword-only
  argument: 'commitment_log'`).
- Part B: `Ran 121 tests ... FAILED (failures=27, errors=50)`
  (`/tmp/r10-red-B-backend.txt`).
- Part C: `ImportError: cannot import name 'capture_diagnostic'`
  (`/tmp/r10-red-C.txt`).

## Commands and outputs

```text
$ cd <worktree>; for s in creative gamescope_boot_repair gamescope_backend capture_diagnostic; do
    PYTHONPATH=scripts/harness python3 tools/kpharness_${s}_test.py; done        # container
Ran 32 tests in 1.983s   OK
Ran 41 tests in 0.453s   OK
Ran 121 tests in 17.022s OK
Ran 14 tests in 3.345s   OK

$ /home/brunner56/.local/bin/host-cmd sh -c 'cd <worktree> && for s in ...; do
    PYTHONPATH=scripts/harness python3 tools/kpharness_${s}_test.py; done'         # host, Python 3.14.7
Ran 32 tests in 0.471s   OK
Ran 41 tests in 0.557s   OK
Ran 121 tests in 4.854s  OK
Ran 14 tests in 1.644s   OK

$ python3 -m py_compile scripts/harness/kpharness/{creative_accept,creative_export,creative,recording,display_backends,capture_diagnostic}.py \
    tools/kpharness_{gamescope_backend,capture_diagnostic,creative}_test.py
py_compile-ok

$ git diff --check -- scripts/harness/kpharness/creative.py scripts/harness/kpharness/recording.py \
    docs/creative-runner.md tools/kpharness_creative_test.py
(no output) exit=0

# untracked touched files: trailing whitespace / leading tabs / final newline
creative_accept.py trailing=0 leading_tabs=0 final_newline=yes
creative_export.py trailing=0 leading_tabs=0 final_newline=yes
display_backends.py trailing=0 leading_tabs=0 final_newline=yes
capture_diagnostic.py trailing=0 leading_tabs=0 final_newline=yes
tools/kpharness_gamescope_backend_test.py trailing=0 leading_tabs=0 final_newline=yes
tools/kpharness_capture_diagnostic_test.py trailing=0 leading_tabs=0 final_newline=yes

$ host-cmd sh -c 'command -v xwininfo xdotool mpv gamescope /usr/bin/ffmpeg /home/linuxbrew/.linuxbrew/bin/ffprobe /usr/bin/python3.14; rpm -qf /usr/bin/xwininfo'
all present; xwininfo-1.1.6-4.fc44.x86_64
```

## Files changed

Tracked (modified): `scripts/harness/kpharness/creative.py`,
`scripts/harness/kpharness/recording.py`, `docs/creative-runner.md`,
`tools/kpharness_creative_test.py`.

Untracked (modified): `scripts/harness/kpharness/creative_accept.py`,
`scripts/harness/kpharness/creative_export.py`,
`scripts/harness/kpharness/display_backends.py`,
`tools/kpharness_gamescope_backend_test.py`.

New: `scripts/harness/kpharness/capture_diagnostic.py`,
`tools/kpharness_capture_diagnostic_test.py`, this report.

## Residual proof boundary (`unverified`)

- No live run. Nothing proves that Gamescope child-window ShmGetImage keeps
  MIT-SHM, gives non-black frames, or reaches 60 FPS cadence under verified
  0,0 / in-screen geometry. The diagnostic exists to settle that.
- `xwininfo` output format and the outer-corner reading of "Absolute
  upper-left" come from the fixture shape. The border-0 ruling covers either
  reading.
- Not run: brew FFprobe `lavfi` / `movie` / `signalstats` availability, the tag
  names and print precision of the `*DIF` tags, and `/proc/self/fd/N` fd-exec
  of that FFprobe. The same applies to `movie=` decoding exactly the same
  frame count as `ffprobe -show_entries frame=best_effort_timestamp_time`. A
  mismatch fails closed as `capture_content_failed`.
- Not run: `-window_id` hex parsing by FFmpeg 8.1.2, `mpv` `_NET_WM_PID`, a
  single window, and 0,0 geometry under headless Gamescope.
- Recovery host identity (`boot_id`, pid-ns) was checked only with injected
  readers, and in one shared namespace (container and host share
  `pid:[4026531836]` per round 9).
- The first-frame black check will also fail a game capture whose first
  recorded frame is really black. That is by the brief's rule, and its effect
  on K1 is untested.
- The commitment log only anchors the head if the operator keeps it out of
  reach of the same-user attacker. That is an operational boundary.
- Rounds 0-9 findings are covered only by the regressions that still pass;
  they were not re-probed.


<a id="round-11"></a>

---

Original file: `task-7-capture-cadence-fix-round-11-report.md`

# Task 7 capture cadence fix, round 11 report

Date: 2026-09-27. Sole writer. Brief: `/home/brunner56/kp-live-20260922/task7-capture-cadence-round-11-brief.md`.

Nothing live was started: no Wine, game, Gamescope, Xvfb, Xwayland, mpv, or x11grab. Only synthetic lavfi encodes ran, through host `/usr/bin/ffmpeg`. The live-game lock was not opened. Nothing was reset, stashed, staged, committed, or pushed. Pre-round copies of every owned file are in `/tmp/r11-backup/`.

Host load was 115 to 260 on 12 CPUs for the whole round. All probe timings below were measured under that load.

## Files changed

The changes stay inside the owned set.

- `scripts/harness/kpharness/display_backends.py`: per-policy noise floor, and the black check at the acceptance start.
- `scripts/harness/kpharness/recording.py`: frame-scaled FFprobe deadlines, and `inherited_fds` for FFmpeg, FFprobe, and xwininfo.
- `scripts/harness/kpharness/creative_accept.py`: survivor always recorded, log bind-mount alias check, `append_commitment_line`, unrecorded-survivor sidecar, scaled re-probe deadlines.
- `scripts/harness/kpharness/capture_diagnostic.py`: preflight, child token and lock check, signal forwarding, cleanup budget, owned-process kill, run bound.
- `scripts/harness/kpharness/creative.py`: `live_lock` yields its stream, and the Gamescope recorder inherits that descriptor.
- `docs/creative-runner.md`.
- Tests: `tools/kpharness_gamescope_backend_test.py`, `tools/kpharness_capture_diagnostic_test.py`, `tools/kpharness_creative_test.py`.

`creative_export.py` did not change. It gates through `verify_acceptance` → `cleanup_state_clear` (`creative_export.py:34`), so the new sidecar check reaches export. `ExportTests.test_unrecorded_survivor_sidecar_blocks_verify_and_export` proves this.

## Red-first evidence

The round-11 tests were run against a tree that holds the pre-round owned modules (`/tmp/r11-red`, modules copied from `/tmp/r11-backup`) and the new tests. Result: `Ran 32 tests ... FAILED (failures=16, errors=26)`. The full output is in `/tmp/r11-red-run.txt` and `/tmp/r11-red-summary.txt`. These are the failures that show behavior, not a missing API:

- `half_duplicate_30_to_60` under `animated-diagnostic-v1`: `'passed' != 'failed'`, and `1.0 != 0.5` for the ratio.
- Black startup before the marker: `'failed' != 'passed'`.
- Bind-mount alias of the run directory, a subdirectory, or a file: `ValueError not raised` (3 cases).
- `--child` without a token: `DiagnosticRefused not raised`.
- Wrapped, `exe`, and `env` targets: `[] != [301, 302, 303, 304]` and `[] != [401]`.
- Commitments append after a hard link was added: `Expected 'mock' to not have been called`, meaning the child was spawned.
- Creative recorder lock inheritance: `not enough values to unpack (expected 1, got 0)`.
- Export with a sidecar: `True is not false`.

The survivor tests fail on the missing `survivor` field. The substantive red for those is the reviewers' own baseline output: p2 and p7 gave `ledger_records_after=0 gate_clear_with_same_head=True reaccept ... exit=0`. The interrupt tests fail on baseline because the supervisor has no Popen path. The mechanism red is the reviewers' p5 (`child_cleanup_steps_completed=[]`).

Two defects were found during this round, and each got a regression:

- **Run deadline.** An honest diagnostic would have been cut off at 74 s, before its own normal cleanup finished. With the pre-fix formula, `test_an_uninterrupted_run_is_never_cut_short_by_the_run_deadline` fails with `AssertionError: 74.0 not greater than or equal to 1576.0`.
- **Unreadable `exe` refusal.** A host classification (below) showed that refusing on an unreadable `exe` would block the run permanently. It is now evidence only (`test_unreadable_exe_alone_is_evidence_not_a_refusal`).

## Requirement 1: R10-1 content noise floor (Critical)

- **Policy table.** `display_backends.py:32-46`. `animated-diagnostic-v1` sets `distinct_noise_floor` to 1.2. `game-capture-v1` sets it to 0.0, which keeps the game policy as it was, per the ruling.
- **Counting.** `evaluate_content` (`display_backends.py:204`) counts a frame as distinct only when `max(ydif, udif, vdif) > floor`, and records the floor in `acceptance`. `_content_evidence_passed` still requires the receipt policy to equal the table, so a changed floor is refused.
- **Mocked-row regressions.** `ContentNoiseFloorTests` covers these cases. The rows are shaped on the calibration values below.

| Clip | animated-diagnostic-v1 | game-capture-v1 |
| --- | --- | --- |
| Half duplicate | fails, ratio 0.5 | passes |
| One in ten fresh | fails, ratio 0.1 | passes |
| Static still | fails | fails |
| Textured static | fails | fails |
| 8x8 blink | fails | passes |
| Full animated | passes | passes |

  The class also covers floor-in-gap margins, receipt tampering (`test_receipt_cannot_loosen_the_noise_floor`, and `content_noise_floor_loosened` in the execution-gate mutations), and table immutability.
- **Real encodes through the production probe.** `RealEncodeContentTests` is host-only. It is skipped in the default suites; set `KP_R11_REAL_ENCODES=1` to run it. Host run (`/home/brunner56/kp-live-20260922/r11-calibration/real-encode-test.txt`):

```text
half_duplicate_30_to_60 {'animated-diagnostic-v1': ('failed', 0.5), 'game-capture-v1': ('passed', 1.0)}
one_in_ten_fresh {'animated-diagnostic-v1': ('failed', 0.0979), 'game-capture-v1': ('passed', 0.8608)}
static_still {'animated-diagnostic-v1': ('failed', 0.0), 'game-capture-v1': ('failed', 0.0)}
textured_static {'animated-diagnostic-v1': ('failed', 0.0), 'game-capture-v1': ('failed', 0.0)}
blink_8x8 {'animated-diagnostic-v1': ('failed', 0.0), 'game-capture-v1': ('passed', 0.0515)}
full_animated_60 {'animated-diagnostic-v1': ('passed', 1.0), 'game-capture-v1': ('passed', 1.0)}
Ran 1 test in 168.995s  OK
```

  The real `blink_8x8` game ratio (0.0515) is only just above 0.05 on this 4 s clip. The deterministic mocked case is the regression that carries this behavior. The real case is corroboration only.

### Calibration evidence

The scripts are in `/home/brunner56/kp-live-20260922/r11-calibration/`:

- `calibrate_noise_floor.py`: lavfi → bgr0 rawvideo, which is x11grab's input format, → `libx264 -preset ultrafast -crf 28 -pix_fmt yuv420p -threads 2`, the exact recorder settings. It then runs the production `probe_frame_content` and `probe_frame_pts` over `/proc/self/fd/N` with brew FFprobe 9.0.1. The clips are 12 s at 1024x768.
- `analyze_rows.py`: labels each frame fresh or duplicate by FFmpeg `fps` round=near slot semantics.
- `split_by_pict_type.py`: splits the values by I and P frame.

The outputs are `calibration-run3.txt`, `analysis-floor-1.2.txt`, and `split-by-pict-type.txt`. Each value below is the largest of Y, U, and V DIF.

| testsrc2 source | fresh min | duplicate max |
| --- | --- | --- |
| 60 FPS | 1.8907 | none |
| 30→60 | 3.0935 | 0.1797 |
| 20→60 | 3.8659 | 0.5374 |
| 6→60 | 4.1965 | 0.3311 |
| 59→60 | 1.8911 | 0.3048 |
| 15→60 | 3.9283 | 0.4800 |
| 45→60 | 2.2950 | 0.7596 |

Across all testsrc2 sources, 2,813 fresh frames had a minimum of 1.8907, and 2,220 duplicate frames had a maximum of 0.7596. The geometric midpoint is 1.198.

**Chosen floor: 1.2.** It is 1.58x above the largest duplicate and 1.58x below the smallest fresh frame. No duplicate is above the floor, and no fresh frame is at or below it.

By picture type, the duplicate maximum is 0.3311 for P frames (n=2,216) and 0.7596 for I frames (n=4, all at the keyframe index 250). Against P duplicates the margin is 3.6x. The I-frame outliers occur only at keyframes (keyint 250, so one per about 4.2 s). All of them together could add at most about 7 frames to a 30 s interval of about 1,800. That cannot lift a half-stale capture (about 50%) anywhere near 99%.

The floor is pattern-specific. Plain `testsrc` fresh frames measured as low as 0.1347. The docs state that the floor holds only for the diagnostic's full-frame testsrc2 pattern.

The reviewers' clips were re-probed through the adapted `content_ratio.py`. Output: `review-probes-r11-rerun/content_ratio.out`.

```text
static_flat     game failed 0.0     diag failed 0.0 (black + static)
static_pattern  game failed 0.0021  diag failed 0.0
static+noise    game failed 0.023   diag failed 0.0
half_dup        game passed 0.9958  diag failed 0.499   (above_floor_frames 299/599)
tenth_fresh     game passed 0.7996  diag failed 0.0981
anim60          game passed 1.0     diag passed 1.0
```

### R10-6: first-frame black check

`evaluate_content` (`display_backends.py:220-236`) applies the black check to the first frame at or after `interval_start`. Black frames before that are recorded only, in `content.startup` (the count before acceptance, the black count, and the capture's first frame). If no frame falls in the interval, the check fails. Regression: `test_black_check_uses_the_first_frame_at_the_acceptance_start`.

### R10-7: game policy limit

The game policy is unchanged. `docs/creative-runner.md` ("Content gate", with the table) states that the game ratio is an upper bound, that the 8x8 blink passes it, and that partial censoring is not ruled out.

## Requirement 2: a surviving FFprobe child is always recorded (Important)

- `_append_cleanup_record(..., survivor=True)` (`creative_accept.py:441-490`) skips the up-front log validation. It writes under the ledger lock. If the head moved during the probe, it appends to the current valid chain and sets `head_changed`. Only then does it call `_emit_head`, which prints to stderr before it validates the log.
- A log failure after the write raises `CommitmentLogFailed` (`:56`), which carries the new head.
- `_record_surviving_probe` (`:644`) always prints one `kpharness.ffprobe-survivor.v1` line to stderr. The line holds the PID, start, command, `recorded_in_ledger`, `failure_id`, head, and any log or ledger error. It then returns `CleanupLedgerChanged` with `survivor`.
- If the ledger cannot take the record (lock timeout, or a malformed or missing ledger), the function writes an exclusive `ffprobe-cleanup-unrecorded-*.json` sidecar (`:688`). `cleanup_state_clear` refuses while any sidecar exists (`:424-431`).
- The CLI prints `survivor` in its failure JSON (`:989`) and exits 1. A failed recovery log append also reports its head (`:966`).
- Regressions in `CleanupLedgerHeadTests`:
  - `test_log_deleted_during_probe_still_records_survivor_and_blocks`
  - `test_log_rotated_during_probe_still_records_survivor_and_blocks`, covering both a missing log and a fresh file at the old path
  - `test_log_hard_linked_during_probe_still_records_survivor_and_blocks`
  - `test_head_changed_during_probe_still_records_survivor_on_the_current_chain`
  - `test_ledger_lock_unavailable_during_probe_leaves_a_blocking_survivor_record`
  - Export: `ExportTests.test_unrecorded_survivor_sidecar_blocks_verify_and_export`

  Each asserts the stderr survivor line, a ledger failure, the gate blocked under both the launch head and the new head, and a refused re-accept.

## Requirement 3: signals during the diagnostic (Important)

- **Supervisor.**
  - `Dependencies.host().spawn_child` is `subprocess.Popen`.
  - The child starts with `start_new_session=True` and `pass_fds=(lock_fd, token_fd)` (`capture_diagnostic.py:879-884`).
  - `_SupervisorSignals` (`:736`) handles SIGINT, SIGHUP, and SIGTERM. Before launch it aborts to the `finally` block. After launch it forwards exactly one SIGINT.
  - `_wait_for_child` (`:767`) waits up to `CLEANUP_BUDGET_SECONDS` after a forward.
  - Only after the budget, or when the child ended without a passed ordered cleanup while owned processes are alive, does `_kill_owned_after_budget` (`:787`) act. It runs `killpg` on the child's own session group, then calls `kill_owned_identity` (pidfd, start re-checked, `:283`) for each identity in `diagnostic-owned.json`.
  - `diagnostic-result.json` records `interrupts`, `cleanup_budget` (seconds, components, exhausted, kill evidence), `owned_alive_after_child`, and `owned_survivors`, each with role, PID, and start.
- **Child.**
  - `run_child` (`:519`) installs `_ChildSignals` (`:482`): the first signal raises `DiagnosticInterrupted`, and later ones are recorded only (`cleaning`, `:565`).
  - `record_owned` (`:458`) writes each owned identity as soon as it exists: lease identities, client, and recorder FFmpeg.
- **Budget.** `CLEANUP_BUDGET_COMPONENTS` (`:72`) totals 1,442 s: recorder 1,398 (thread join 2, four xwininfo x 5, FFmpeg 15+5, two probes at `probe_deadline_seconds(3240)` = 678 s each), client 4, display 25, margin 15.
- **Run bound.** `CHILD_RUN_SECONDS` = pre-cleanup 134 s (`CHILD_PRE_CLEANUP_COMPONENTS`, `:82`) + 1,442 s = 1,576 s (`:93`). An uninterrupted run is never cut off by its own cleanup.
- **Regressions.** `InterruptTests` runs a real supervisor process, a real child running the real `run_child`, and real `sleep` grandchildren. There is no display.
  - SIGINT, SIGHUP, and repeated SIGINT each give ordered cleanup `recorder, source_process, display`, exactly one forwarded SIGINT, no survivors, and all owned processes dead.
  - Budget exhausted: only owned processes are killed, and a bystander `sleep` survives.
  - Survivor listed exactly.
  - Crashed child: its owned processes are killed.
  - Quiet run: no interrupt.
  - Run-deadline bound, and budget = sum of components.

## Minors

- **`--child` token and lock.**
  - `create_child_token` (`:409`) writes a 64-hex nonce into a pipe and closes the write end. Only the read fd is inherited, and its SHA-256 goes into the printed and logged commitments.
  - `verify_child_authority` (`:420`) requires a FIFO fd, a token whose digest equals both the config and `commitments.json`, and `canonical_lock_guard()` returning the configured `lock_fd`.
  - `main` returns 2 with a JSON refusal.
  - Tests: `ChildAuthorityTests`. `test_production_lock_guard_admits_only_the_configured_held_descriptor` uses the real guard on a temporary `KP_GAMESCOPE_REPO_ROOT` and never touches the canonical lock.
- **Preflight** (`:146-260`).
  - It refuses if `comm`, `stat`, or `cmdline` of any own-uid row is unreadable.
  - It detects targets by `comm`, the `/proc/PID/exe` basename, `argv[0]`, and the first script argument after a launcher (`WRAPPER_NAMES`, `:61`, skipping `VAR=value`).
  - It excludes this process and its ancestors (`_launch_chain`).
  - It never signals.
  - An unreadable `exe` is kept as evidence only (`:185`).
  - Tests: `PreflightRound11Tests`, which patches `os.kill` and `os.killpg` to raise.
- **Lock inheritance.**
  - `X11WindowRecorder(inherited_fds=...)` (`recording.py:611`) passes the descriptor to FFmpeg (`:1209`), both default probes (`:665-671`), and every xwininfo query (`_query`, `:673`).
  - The diagnostic child passes `inherited_fds=(lock_fd,)` and a lock-wrapped `run` to discovery, the verifier, and the recorder (`capture_diagnostic.py:525`, `:550`).
  - Creative Gamescope runs pass the held live-lock stream's fd (`creative.py:103`, `:242`).
  - Tests: `LockInheritanceTests` (two) and `test_gamescope_recorder_children_inherit_the_held_live_lock`.
- **FFprobe deadlines.**
  - `probe_deadline_seconds(frames)` = min(3,600, 30 + 0.2 x frames) (`recording.py:37-47`).
  - Recorder: the PTS probe is sized from terminal FFmpeg frames (`:761`) and the content probe from `len(pts)` (`:871`).
  - Acceptance sizes it from the PTS artifact `frame_count` (`creative_accept.py:871`).
  - Tests: `ProbeDeadlineTests`. A 10-minute clip finishes at 45 fake seconds under the scaled bound, times out under the old fixed 30 s, and the cap still holds.
  - Basis: a 12 s, 720-frame clip took 61 to 194 s for both probes combined at load 125 to 260 (`calibration-run3.txt` `probe_seconds`). The first calibration attempt died at the old fixed 30 s bound (`calibration-run1.txt`). So 0.2 s per frame is about 1.5x the worst measured per-frame cost.
- **Docs and log placement.**
  - `validate_commitment_log` (`creative_accept.py:313-360`) now compares the log and its parent chain by `(st_dev, st_ino)` with every inode in the run tree.
  - Tests: `CommitmentLogPlacementTests` (mocked stat). The real bind mount was rerun with p8 on the host: `bind_mount_alias_of_run_log: refused ... (it aliases the run tree by device and inode, for example a bind mount)`.
  - The supervisor's commitments append goes through `append_commitment_line`, which re-validates the log (`capture_diagnostic.py:864`; test `test_commitments_append_revalidates_the_log_before_the_single_launch`).
  - Docs: the trust root is the captured output, and the log is an anchor only when out of the writer's reach (`chattr +a`, another account, or off the host). Copy head lines out of band. The export example now uses `LAST_HEAD_THE_TOOL_PRINTED_FOR_THIS_RUN`, with a warning not to read it from `creative-run.json`. Bind-mount refusal and its limits are documented.

## Host preflight classification (read-only)

This reads `/proc` only. It took no lock, sent no signal, and did not call `preflight()`. Output: `review-probes-r11-rerun/host-preflight-classification.out`.

```text
rows 1215 own_uid_rows 785
forbidden [(2547167, 'wineserver', ...), (3970958, 'ffprobe', ...)]
unreadable [sd-pam, passless, kwin_wayland, polkit-kde-auth, ssh-agent, ksystemstats, ksgrd_network_h: all "exe: PermissionError"]
```

The `ffprobe` was this round's own `content_ratio` probe. The `wineserver` is the known foreign process, so preflight will refuse until it exits.

All the unreadable rows were exe-only kernel protections. That is why unreadable `exe` became evidence only. Under the final code, the unreadable list for these rows is empty, because only `comm`, `stat`, and `cmdline` failures refuse.

## Validation

```text
# container (no ffprobe on PATH)
PYTHONPATH=scripts/harness:tools python3 tools/kpharness_<suite>_test.py
creative 33 OK | gamescope_boot_repair 41 OK | gamescope_backend 137 OK (skipped=1: RealEncodeContentTests) | capture_diagnostic 35 OK
# host: host-cmd sh -c 'cd <worktree> && PYTHONPATH=scripts/harness python3 tools/kpharness_<suite>_test.py'  (Python 3.14.7)
creative 33 OK | gamescope_boot_repair 41 OK | gamescope_backend 137 OK (skipped=1) | capture_diagnostic 35 OK
```

Total: 246 in each environment (245 run, 1 skipped). The round-10 total was 208.

`py_compile` was run on the five changed modules and three test files: OK. A scoped `git diff --check` was run on the touched tracked files (`recording.py`, `creative.py`, `tools/kpharness_creative_test.py`, and `docs/creative-runner.md`): clean. A trailing-whitespace scan of the untracked touched files (`display_backends.py`, `creative_accept.py`, `capture_diagnostic.py`, the two untracked tests, and this report) found 0 lines.

### Reviewer probe reruns (adapted copies in `/home/brunner56/kp-live-20260922/review-probes-r11-rerun/`)

p2 (`p2.out`, container):
```text
inside_direct=refused
relative_inside=refused
dotdot_into_run=refused
via_dir_symlink_into_run=refused
lexical_dotdot_through_symlink=refused
outside_through_link_in_run=accepted
run_dir_itself=refused
outside_plain=accepted
run_given_via_symlink_log_inside=refused
log_vanished_during_probe: exit=1 stdout_error='canonical PTS re-probe cleanup failed: survived; surviving ffprobe pid=4242 start=12345; failure_id=c3b3cf497dc34f859cc601e26350e992; cleanup_ledger_sha256=16ae7846823ee80a4f967e85fae51fd201b12fbf8c009617f341bef61a695949; do not accept or export this run; retain this line, the ledger head, and the survivor PID/start out of band'
  survivor_mentioned_in_output=True
  r11_stderr_heads=1 stderr_survivor=[(4242, '12345', True, 'cleanup commitment log is missing; create it outside the run directory')]
  ledger_records_after=1 gate_clear_with_same_head=False
  reaccept_after_unrecorded_survivor: exit=1 ok=False
  r11_gate_clear_with_new_stderr_head=False
concurrent_same_head_appends=['ok', 'refused', 'refused', 'refused'] records=1 logged_failures=1 log_head_matches_file=True
```

p7 (`p7.out`, container):
```text
hardlink_during_probe: exit=1 error='canonical PTS re-probe cleanup failed: survived; surviving ffprobe pid=4242 start=12345; failure_id=3b58d1ff67324ff99144172d1ba1654b; cleanup_ledger_sha256=15b8688296e3c5fa8e9136b7a1386b369855f7c1f58d2889911c66d4473922a7; do not accept or export this run; retain this line, the ledger head, and the survivor PID/start out of band' records=1 clear=False pid_in_output=True
  r11_stderr_survivor_pid=True stderr_head_event=['acceptance_failure']
title_injection: status=verified size=[1024, 768] map=IsViewable border=0 origin=[0, 0]
reuse_while_pidfd_held='cleanup PID identity changed while pidfd held' signals=0 ledger_unchanged=True
```

p5 adapted to the real supervisor and a real child (`p5_sigint_cleanup_r11.py`, `p5.out`):
```text
cooperative ['SIGINT']: parent_exit=1 parent_finally_ran=True child_cleanup_steps_completed=['recorder', 'source_process', 'display'] interrupts=['SIGINT'] budget_exhausted=False owned_alive_after=[] result_owned_survivors=[]
cooperative ['SIGHUP']: parent_exit=1 parent_finally_ran=True child_cleanup_steps_completed=['recorder', 'source_process', 'display'] interrupts=['SIGHUP'] budget_exhausted=False owned_alive_after=[] result_owned_survivors=[]
cooperative ['SIGTERM']: parent_exit=1 parent_finally_ran=True child_cleanup_steps_completed=['recorder', 'source_process', 'display'] interrupts=['SIGTERM'] budget_exhausted=False owned_alive_after=[] result_owned_survivors=[]
cooperative ['SIGINT', 'SIGINT', 'SIGINT']: parent_exit=1 parent_finally_ran=True child_cleanup_steps_completed=['recorder', 'source_process', 'display'] interrupts=['SIGINT', 'SIGINT', 'SIGINT'] budget_exhausted=False owned_alive_after=[] result_owned_survivors=[]
stubborn ['SIGINT']: parent_exit=1 parent_finally_ran=True child_cleanup_steps_completed=[] interrupts=['SIGINT'] budget_exhausted=True owned_alive_after=[] result_owned_survivors=[]
survivor ['SIGINT']: parent_exit=1 parent_finally_ran=True child_cleanup_steps_completed=[] interrupts=['SIGINT'] budget_exhausted=True owned_alive_after=['client'] result_owned_survivors=[('client', 3919327)]
production_budget_seconds=1442.0 components={'recorder': 1398.0, 'source_process': 4, 'display': 25, 'evidence_margin': 15}
```

p9 (`p9.out`, host, scaled deadline):
```text
half_dup_30_to_60 animated-diagnostic-v1: failed ratio=0.5000 floor=1.2
half_dup_30_to_60 game-capture-v1: passed ratio=0.9958 floor=0.0
tenth_fresh_6_to_60 animated-diagnostic-v1: failed ratio=0.1000 floor=1.2
tenth_fresh_6_to_60 game-capture-v1: passed ratio=0.8000 floor=0.0
content_probe_35s_1024x768: 117.7s frames=2100 (scaled bound 450 s)
nproc=12 loadavg=(259.03759765625, 263.47314453125, 242.64013671875)
exit=0
```

content_ratio over the reviewers' clips: see the table under Requirement 1 (`content_ratio.out`).

p8, the real user-namespace bind mount on the host: `bind_mount_alias_of_run_log: refused ... (it aliases the run tree by device and inode, for example a bind mount)`.


## Residual proof boundary

- **The floor is calibrated on synthetic encodes, not on a Gamescope/mpv capture.** The mpv-to-x11grab path of the diagnostic has not been measured. The first real diagnostic's per-frame DIF values should be compared against the 1.2 floor before its verdict is trusted.
- **The game policy (floor 0, 5%) proves only that something moved.** This is documented.
- **The sidecar fallback depends on the run directory being writable.** If the sidecar write also fails, only the stderr survivor line remains. The CLI still exits 1.
- **A same-user writer can still delete the sidecar or the ledger.** The captured stderr head is the anchor, as documented.
- **Bind-mount detection is point-in-time.** It misses an alias created after the check, or a mount the process cannot stat.
- **`canonical_lock_guard` is trusted for the lock check.** The `--child` token stops accidental and replayed starts. A same-user process that builds its own pipe and commitments and holds the lock could still start a child, but it would already hold the lock.
- **The cleanup budget is long.** A Ctrl-C can wait up to 1,442 s, dominated by probe deadlines sized for this load.
- **`RealEncodeContentTests` is opt-in** and is not part of the default suite counts.
- **The one authorized diagnostic has still not run.** Nothing here authorizes it.


<a id="round-12"></a>

---

Original file: `task-7-capture-cadence-fix-round-12-report.md`

# Task 7 capture cadence fix, round 12 report

Date: 2026-09-27. Sole writer. Brief: `/home/brunner56/kp-live-20260922/task7-capture-cadence-round-12-brief.md`.

Nothing live ran. No Wine, game, Gamescope, Xwayland, mpv, or x11grab was started. Only synthetic lavfi encodes ran, through host `/usr/bin/ffmpeg`, plus dummy `sleep` and Python process trees. The live-game lock was never opened. The p12 rerun and the production code path only `stat` its pathname. Nothing was reset, stashed, staged, committed, or pushed. Pre-round copies of the owned files are in `/tmp/r12-backup/` (container `/tmp`). Host load was 229 to 270 on 12 CPUs for the whole round.

## Files changed

All changes are inside the owned set.

- `scripts/harness/kpharness/display_backends.py`:
  - policy `animated-diagnostic-v2` (floor 3.9, `separation_factor` 3.0) replaces v1;
  - `content_separation` and `CONTENT_HISTOGRAM_EDGES`;
  - `content_recomputed`, which `_content_evidence_passed` now uses.
  - `game-capture-v1` is byte-identical.
- `scripts/harness/kpharness/capture_diagnostic.py`:
  - `PATTERN_STEP` / `PATTERN_GRAPH`, and the client and route now use them;
  - the `calibration_ambiguous` verdict;
  - the signal mask around the spawn, with the child unblocking;
  - the trusted lock check for `--child`;
  - exe-identity preflight, which also feeds the post-run scan.
- `scripts/harness/kpharness/gamescope_socket.py`: `common_repository_root`, `canonical_lock_path_for`, `trusted_repository_root`, and `held_lock_descriptor`. `canonical_lock_guard` behaves as before. Only its `.git` resolution moved into a helper.
- `docs/creative-runner.md`.
- `tools/kpharness_gamescope_backend_test.py` and `tools/kpharness_capture_diagnostic_test.py`.

Four tests were added after a review pass and were not run red first:

- `test_recorder_keeps_calibration_ambiguous_content_recomputable`
- `test_snapshot_child_lock_path_equals_the_supervisor_lock_path`
- `test_a_multithreaded_supervisor_refuses_before_the_spawn`
- the `content_separation` and `supervisor_threads_at_spawn` assertions in the supervisor commitments test

The first two verify existing behavior. The other two are new behavior, but their red was not captured.

`recording.py`, `creative.py`, `creative_accept.py`, `creative_export.py`, and `tools/kpharness_creative_test.py` did not change.

## Red-first evidence

The tests were written first and run against the unchanged modules. Output is in `/home/brunner56/kp-live-20260922/r12-red/`.

- `red-unit.txt`: 25 tests, `FAILED (failures=2, errors=35)`.
  - Most errors are the missing v2 policy, `PATTERN_*`, `repository_root=`, and `tools=`.
  - Two failures show behavior:
    - `test_admitted_child_pins_the_trusted_root_for_every_later_lock_check`: the environment stayed `/elsewhere`.
    - `test_supervisor_refuses_a_renamed_tool_copy_before_any_launch`: the child was spawned.
- `red-interrupt.txt` (spawn window, real processes): three subtest failures.
  - SIGINT: `'interrupted before launch: SIGINT' unexpectedly found`.
  - SIGHUP and SIGTERM: `launches 0 != 1`. The orphan from the SIGINT subtest still held the fake lock, so the next supervisor refused. That orphan is the defect itself. It was my own test's dummy child, and it finished its own run and exited. I sent it no signal.
  - `test_the_spawn_mask_never_reaches_the_child_or_its_owned_processes` passed on the baseline, by construction. It guards the new blocking and is not a red test.
- Only ruling 2 has a behavioral red of my own. For rulings 1, 3, and 4, the red is missing-API errors plus the two unit failures above. Their behavioral red is the reviewers' baseline output:
  - `review-probes-r11-adversarial/p12.out`: `forged_pipe_commitments_env_redirected_lock: ADMITTED`.
  - `p10.out`: `real renamed_enc_binary: detected=False`.

## Ruling 1 (R11-C1, Critical): pattern, calibration, separation

### Pattern and why

`PATTERN_STEP = eq=contrast=0.4:brightness=(3*n-7*floor(3*n/7)-3)*0.11:eval=frame`, and `PATTERN_GRAPH = testsrc2=size=1024x768:rate=60,` + step (`capture_diagnostic.py`, near `CLIENT_TITLE`). The client plays `av://lavfi:` + `PATTERN_GRAPH`.

- Every output frame gets a full-frame brightness level `(3n mod 7) - 3`. There are seven levels, 0.11 apart (about 18 luma).
- Any two frames 1 to 6 source frames apart differ by at least one level over the whole frame. Adjacent frames differ by at least three.
- This does not depend on how fast `testsrc2` moves. `testsrc2` is only texture at 40% contrast.
- Blind spot: a skip of exactly 7 frames (117 ms) repeats the level. The cadence gate's 50 ms maximum gap is 3 frame intervals, so a capture that skips 7 frames already fails cadence.
- `PatternTests` asserts both properties from the expression itself.

I chose a brightness step over checker inversion. Inversion has period 2, so a one-frame skip returns to the same polarity and leaves only `testsrc2` motion. That is the R11-C1 failure again.

The expression has no comma, so it needs no filtergraph escaping in mpv's URL. On the host, `ldd` shows `/usr/bin/mpv` (mpv-0.41.0-5.fc44) and `/usr/bin/ffmpeg` (ffmpeg-8.1.2-3.fc44) link the same `/lib64/libavfilter.so.11`, `libavformat.so.62`, and `libavdevice.so.62`. I did not run mpv.

### Calibration

Script: `/home/brunner56/kp-live-20260922/r12-calibration/calib_r12.py`. It is the correctness reviewer's `calib_r11.py` with `SOURCES` rewritten onto the new pattern, plus six families.

- Each clip is 18 s at 1024x768. It is rendered to `bgr0` and encoded with the recorder's exact args (`-c:v libx264 -preset ultrafast -crf 28 -pix_fmt yuv420p -threads 2`).
- The production `probe_frame_content` and `probe_frame_pts` read each clip over `/proc/self/fd/N` with brew FFprobe.
- Labels come from the framemd5 of every source frame.
- The step is applied at the pattern output. Capture duplication (`fps=R,fps=60`) and I-frame alignment trims come after it.
- I-frames are at 250, 500, 750, and 1000 in every clip, checked by `pict_type`.
- Output: `summary.out`.

| Family | Fresh n / min | Duplicate n / max | I-frame duplicates n / max | v2 verdict |
| --- | --- | --- | --- | --- |
| fresh60 | 1079 / 51.83 | 0 | 0 | passed, separated |
| slow_half | 1079 / 51.78 | 0 | 0 | passed, separated |
| slow_quarter (R11-C1 case) | 1079 / 51.84 | 0 | 0 | passed, separated, ratio 1.0 |
| frozen (testsrc2 at 1 FPS) | 1079 / 51.73 | 0 | 0 | passed, separated |
| r30_k0 / r30_k1 | 539 / 15.35, 540 / 15.35 | 540 / 0.398, 539 / 0.944 | 0; 4 / 0.944 | failed 0.50, separated |
| r30_k1_slowq | 540 / 15.28 | 539 / 0.913 | 4 / 0.913 | failed 0.50, separated |
| r20_k0 / k1 / k2 | 359-360 / 33.24 | 719-720 / 0.985 max | 2-3 / 0.985 max | failed 0.33, separated |
| r12_d5 / r12_d5_k1 (distance 5, one level) | 215-216 / 15.57 | 863-864 / 0.975 | 4 / 0.975 | failed 0.20, separated |
| r15, r45, r50, r58, r3 | min 15.37 | max 1.0167 (r45 I-frame) | r45 2 / 1.0167 | all failed, separated |

- Duplicates: 7,825 frames, max **1.0167** (an I-frame duplicate, r45).
- Fresh: 10,518 frames, min **15.2818** (r30_k1_slowq, one level).
- The ratio is 15.03 and the geometric midpoint is 3.942.
- **Floor 3.9.** That is 3.84x above the largest duplicate and 3.92x below the smallest fresh frame, so there is at least 3x on both sides.
- `test_policy_floor_sits_inside_the_calibrated_gap_with_threefold_margin_on_both_sides` pins this, using `CALIBRATED_DUPLICATE_MAX = 1.0167` and `CALIBRATED_FRESH_MIN = 15.2818`.

The opt-in real-encode test ran on the host with the new pattern (`r12-calibration/real-encode-test.txt`, `OK`):

- `slow_quarter_stepped` passed at 1.0.
- `half_duplicate_30_to_60` failed at 0.5.
- `one_in_ten_fresh` failed at 0.0979.
- `static_still`, `textured_static`, and `blink_8x8` failed.
- `full_animated_60` passed.

Encode cost (`encode_cost.out`): bitrate is +13% (7,467 vs 6,595 kbit/s at identical size and duration). The speed numbers are unusable at load 233-270: old 0.555x and 0.359x, new 0.296x and 1.28x. The cost is unverified beyond bitrate.

### Separation rule (mandatory check)

`display_backends.content_separation` runs when a policy defines `separation_factor`, which only the diagnostic policy does.

- The guard band is the open interval `(floor/3, floor*3)` = (1.3, 11.7), taken from the policy table and never from the data.
- `separation` records:
  - the guard band and the counts below, inside, and above it;
  - `duplicate_max` and `fresh_min`;
  - a histogram over fixed bins `CONTENT_HISTOGRAM_EDGES`, so recomputation is exact.
- If any acceptance frame is inside the band, the status is `ambiguous`. The only failure is then `calibration_ambiguous: ...`, and `capture_content_static` is suppressed.
- `capture_diagnostic.evaluate` recomputes separation from the hashed artifact under the v2 policy (`content_separation_status`), never from the receipt.
- `ambiguous` makes the verdict `calibration_ambiguous`. That outranks PASS and FAIL, every criterion is still recorded, and the exit is nonzero.
- `supervise` writes the recomputed separation dict (guard band, counts, `duplicate_max`, `fresh_min`, and histogram) to `diagnostic-result.json` as `content_separation`. It is `null` when nothing could be recomputed.

Tests:

- `ContentSeparationTests` covers:
  - fixed histogram;
  - band values give ambiguous and never pass or blame capture: one frame at the floor, fresh values inside the band, duplicates inside the band, and plain slow-testsrc2 values;
  - stuck and half-duplicate captures separate and blame capture;
  - the game result shape is unchanged.
- `CaptureTargetAndContentTests.test_recorder_keeps_calibration_ambiguous_content_recomputable` runs the recorder's own `_finalize_cadence` on rows at the floor. It checks:
  - the recorder receipt has `separation.status == 'ambiguous'`;
  - the first content failure is `calibration_ambiguous`, with no `capture_content_static`;
  - `D.content_recomputed` equals the recorder's content block;
  - `CD.content_separation_status` returns the ambiguous separation.
- `SnapshotAndCommitmentTests` asserts that `content_separation` is present in the result JSON. It is `None` in that test, because no content is recomputed.
- `CriteriaTests` covers:
  - ambiguous outranks another failed criterion;
  - separated stale content gives FAIL;
  - the receipt cannot claim a separation the artifact does not show, in either direction;
  - a loosened `separation_factor` fails the content gate.

Worked example (`r12-calibration/old_pattern_under_v2.out`): the reviewer's round-11 old-pattern encodes, judged by v2.

```text
OLD-pattern slow_quarter  v2: status=failed ratio=0.0000 sep=ambiguous below=1000 inside=79 above=0 failures=['calibration_ambiguous']
OLD-pattern fresh60       v2: status=failed ratio=0.0000 sep=ambiguous below=0 inside=1079 above=0 failures=['calibration_ambiguous']
```

So if the step did not reach the screen, the verdict would be `calibration_ambiguous`, not a capture failure.

The game policy is unchanged (`GAME_POLICY_R11` equality test). The docs and the `display_backends.py` comment say its zero floor is not calibrated.

## Ruling 2: spawn-window signals

The supervisor side (`capture_diagnostic.py`, `supervise`, the `driver.log` block) works in this order:

1. `signal.pthread_sigmask(SIG_BLOCK, INTERRUPT_SIGNALS)` runs before `spawn_child`.
2. The supervisor assigns `signals.child`, reads the child's PID and start, and records `result['child']`.
3. The previous mask is restored in `finally`, which also covers a Popen exception. A held signal is then delivered, and the handler forwards one SIGINT.
4. The single-threaded assumption is enforced. `result['supervisor_threads_at_spawn']` records `threading.active_count()`. With more than one thread, the supervisor refuses before `launches = 1` and before any spawn (`test_a_multithreaded_supervisor_refuses_before_the_spawn`).

The child side: `run_child` installs its handlers, then calls `_ChildSignals.unblock()` as the first statement inside the ordered-cleanup `try`. It does this before it starts the lease, the client, or FFmpeg.

Regressions (`InterruptTests`, real supervisor, child, and `sleep` grandchildren):

- `test_a_signal_between_fork_and_popen_return_still_supervises_the_child` covers SIGINT, SIGHUP, and SIGTERM. The signal is sent from inside `spawn` after the child exists. The test checks:
  - `interrupts == [sig]` and exactly one forwarded SIGINT;
  - the child identity is recorded, and the child has exited and is not alive;
  - no survivors.
- `test_the_spawn_mask_never_reaches_the_child_or_its_owned_processes` reads `SigBlk` from `/proc/PID/status` of the child, the Gamescope stand-in, and the client stand-in. The INT, HUP, and TERM bits are 0.

The whole `InterruptTests` class passed: 11 tests, `r12-red/green-interrupt.txt`.

p11b rerun, unchanged probe (`/home/brunner56/kp-live-20260922/review-probes-r12-rerun/p11b.out`):

```text
supervisor_exit=1 errors=['interrupted: SIGINT'] launches=1 child_returncode=1 owned_survivors=[]
child_alive_after_supervisor_exit=False owned_started_after_supervisor_exit=[]
unsupervised_child_completed_run=True its_cleanup_steps=[] result_file_rewritten=False
```

The probe's labels come from round 11. Here `unsupervised_child_completed_run=True` only means the child wrote `diagnostic-run.json` before it exited. The supervisor waited for it (`child_returncode=1`, child not alive). Nothing had started, so the cleanup steps list is empty.

## Ruling 3: `--child` authority

- `gamescope_socket.trusted_repository_root(module_file)` derives the root from the code's own location and never from the environment.
  - Code under `<snapshot>/runtime/kpharness/` runs `verify_snapshot(snapshot)`, which checks the manifest canonical form, its `.sha256` sidecar, and every copied module. It then takes the manifest's `repository_root`.
  - Checkout code takes `parents[3]`.
- `held_lock_descriptor(fd, path)` requires all of these:
  - `fstat(fd)` and `stat(path)` are regular files with the same `(st_dev, st_ino)`;
  - that exact descriptor's `/proc/self/fdinfo/<fd>` shows the `FLOCK ... WRITE` entry for that dev:ino;
  - the path still names the same inode after the check.
- `verify_child_authority` uses `held_lock_descriptor(config['lock_fd'], trusted_lock_path())`. `_child_main` then pins `KP_GAMESCOPE_REPO_ROOT` to the trusted root, so later socket-cleanup guard calls cannot be redirected.
- The global `canonical_lock_guard` still honours the environment, because the boot_repair suite, which I do not own, relies on it.

Regressions (`ChildAuthorityTests`, temporary roots only):

- the passed descriptor itself must hold the lock: another fd of the same file is refused, an unlocked fd is refused, and a closed fd is refused;
- `test_environment_redirected_private_lock_is_refused` is the p12 regression. It also asserts that `trusted_repository_root()` returns the checkout with the environment redirected;
- a real snapshot gives its manifest root even with the environment redirected, and a tampered or missing manifest raises;
- the admitted child pins the trusted root;
- `test_snapshot_child_lock_path_equals_the_supervisor_lock_path` compares pure paths, with no lock opened. The lock path derived from a real snapshot manifest (manual `.git`/`commondir` parse) equals `CD.canonical_lock_path()` (`git rev-parse`). `CD.trusted_lock_path()` equals it too.

p12 rerun, unchanged probe (`review-probes-r12-rerun/p12.out`):

```text
forged_pipe_and_commitments_no_lock: refused: child does not hold the canonical lock: canonical lock descriptor or path is unavailable: [Errno 9] Bad file descriptor
forged_pipe_commitments_env_redirected_lock: refused: child does not hold the canonical lock: lock descriptor is not the canonical lock file
```

The other four p12 cases stay refused. p12 and `held_lock_descriptor` only `stat` the canonical lock pathname. Neither opens it.

Documented trust boundary (`docs/creative-runner.md`, capture diagnostic section):

- A same-UID process that really holds the canonical lock is inside the boundary.
- So is a same-UID author who writes their own snapshot whose manifest names a private root, because that is running code they control.

## Ruling 4 (Minor): renamed binaries

- `process_inventory(..., tools=...)` covers readable own-UID rows with an openable `/proc/PID/exe`.
  - It first compares the configured FFmpeg and FFprobe ELF by device and inode, which catches a hard link.
  - Next, only for files of the same size, it compares SHA-256. Each `(dev, ino, size, mtime)` is hashed once.
  - A match sets `exe_tool_match`, and `forbidden_processes` refuses it.
- `supervise` now computes `native_elf_identity` for both tools before preflight. It passes them to preflight and to the post-run survivor scan.
- `preflight.json` records `tool_identities`.
- Tests (`PreflightExeIdentityTests`):
  - a renamed copy and a hard link are detected;
  - a same-size different file and an unreadable exe are not;
  - hashing happens once for three rows sharing an inode, and a small file is never hashed;
  - the supervisor refuses a renamed copy before launch, and `spawn_child` is not called.
- The docs narrow the guarantee: name, exe basename, and argv detection, plus exe content for readable own-UID processes. Not covered: another build, another UID, non-dumpable processes, and processes that start after the scan.

p10 reruns (`review-probes-r12-rerun/`):

- The unchanged `p10-original.out` still gives `renamed_enc_binary: detected=False`. It calls `process_inventory` without configured identities, as round 11 did.
- The adapted `p10_r12_preflight.py` / `p10-r12.out` passes a `/bin/sleep` copy as the configured-FFmpeg stand-in:

```text
renamed_copy_exe_argv_comm_with_configured_identity: refused: preflight found existing Wine, game, Gamescope, or FFmpeg processes
real renamed_enc_binary: exe_tool_match=ffmpeg by=sha256 detected=True comm=enc exe=/tmp/kp-r11-p10-l55pyqgp/enc
```

In that adapted run, every host `sleep` also matches. That is expected, because the stand-in identity is `sleep`, and it shows the matching is by content. The probe's `forbidden_all` line lists them. It sent no signal: `os.kill` is patched to raise, and only its own three dummies were terminated.

## Validation

Final run, after the follow-up changes. Output is in `/home/brunner56/kp-live-20260922/r12-suites/final/`.

```text
# container (Python 3.12.3): PYTHONPATH=scripts/harness:tools python3 tools/kpharness_<suite>_test.py
creative 33 OK | gamescope_boot_repair 41 OK | gamescope_backend 142 OK (skipped=1: RealEncodeContentTests) | capture_diagnostic 50 OK
# host (Python 3.14.7): host-cmd sh -c 'cd <worktree> && PYTHONPATH=scripts/harness:tools python3 tools/kpharness_<suite>_test.py'
creative 33 OK | gamescope_boot_repair 41 OK | gamescope_backend 142 OK (skipped=1) | capture_diagnostic 50 OK
```

- Total: 266 in each environment, with 265 run and 1 skipped. Round 11 had 246.
- An earlier full run, before the follow-ups, had 263 per environment, all OK (`r12-suites/`).
- The skipped opt-in `RealEncodeContentTests` was run separately on the host with `KP_R11_REAL_ENCODES=1`: 1 test, OK (`r12-calibration/real-encode-test.txt`).

- `py_compile` of the three changed modules and two changed test files: OK.
- Trailing-whitespace scan of the six touched files: 0 lines.
- `git diff --check -- docs/creative-runner.md`: clean. The other touched files are untracked.
- No whole-worktree diff was run.

## Residual proof boundary

- **Synthetic calibration only.** The mpv, Gamescope, and x11grab path is not measured. If its noise differs, the separation rule turns that into `calibration_ambiguous`, not a pass or a capture blame.
- **The duplicate maximum crept up as families were added** (0.944, then 0.985, then 1.0167). The band edge is 1.3. A real I-frame duplicate above 1.3 gives `calibration_ambiguous`, which fails safe.
- **mpv's use of `eq ... eval=frame` is inferred** from the shared libavfilter, not run.
- **The spawn-mask fix needs a single-threaded supervisor.** This is enforced by refusal, not proven for threads started between the check and the block. None are started there.
- **Forgery residual:** a same-UID author of a snapshot manifest naming a private root is inside the trust boundary, as documented.
- **The one authorized diagnostic has still not run.** Nothing here authorizes it.

## Grill me

1. **Can a forger still redirect `--child` to a private lock?** (weakest)
   Yes, by writing a whole fake snapshot whose manifest (and its `.sha256`) names a private root, then running the copied code from it. The env-var path is closed. p12 case 6 is refused in `review-probes-r12-rerun/p12.out`, and `test_environment_redirected_private_lock_is_refused` covers it. The manifest path is the same redirect moved into a data file the forger writes. I documented it as inside the trust boundary, because the forger then runs code they control. Closing it needs an anchor outside the same UID's reach, and nothing in this tree provides one. Status: unresolved by design, documented in `docs/creative-runner.md`.
2. **Does the calibration represent the real mpv to x11grab path?**
   Unverified. The only referents are synthetic: `r12-calibration/summary.out` and `real-encode-test.txt`. What makes a mismatch safe is the separation rule. `old_pattern_under_v2.out` shows plain testsrc2 at native and quarter speed judged `calibration_ambiguous`, not PASS and not a capture failure. The first real run's `content.separation.histogram` is the check.
3. **Why is there only 1.28x between the duplicate maximum (1.0167) and the band edge (1.3)?**
   The brief's 3x is floor-to-population, and that is 3.84x and 3.92x (`summary.out`, last two lines). The band edge sits at floor/3 by construction, so a duplicate above 1.3 lands in the band and the verdict is ambiguous. That is a failure, not a false pass. The maximum rose with each family added: 0.944 for r30_k1, 0.985 for r20_k1, 1.0167 for r45. More I-frame alignments could push it past 1.3. That would give a false `calibration_ambiguous`, never a false PASS.
4. **Could the blocked mask leak into Gamescope, mpv, or FFmpeg, or be lost?**
   `test_the_spawn_mask_never_reaches_the_child_or_its_owned_processes` reads `SigBlk`: the INT, HUP, and TERM bits are 0 in the child, the lease stand-in, and the client stand-in. Unblocking happens in the first statement of the `run_child` cleanup scope. A second supervisor thread would defeat the block. The supervisor now refuses in that case (`test_a_multithreaded_supervisor_refuses_before_the_spawn`) and records `supervisor_threads_at_spawn`.
5. **Does the child refuse if a repository input changes between snapshot and child start?**
   Yes. `verify_snapshot` in `trusted_repository_root` rehashes the manifest's `repository_inputs` (`gamescope_snapshot.py`, `verify_snapshot`). In this dirty, multi-writer worktree, an edit to `data/addresses/*.json` in those seconds would refuse `--child` (exit 2, no lease). That fails closed and has not been observed (unverified).

Handoff, the one question not settled: does the real mpv render of `PATTERN_GRAPH` keep every duplicate at or below 1.3 and every fresh frame at or above 11.7? The single check that settles it is `content_separation` (with its histogram) in `diagnostic-result.json` from the one authorized diagnostic run.


<a id="round-13"></a>

---

Original file: `task-7-capture-cadence-fix-round-13-report.md`

# Task 7 capture cadence fix, round 13 report

Date: 2026-09-27. Sole writer. Brief: `/home/brunner56/kp-live-20260922/task7-capture-cadence-round-13-brief.md`.

Nothing live ran. I started no Wine, game, Gamescope, Xwayland, mpv, or x11grab. What ran:

- synthetic lavfi encodes through host `/usr/bin/ffmpeg`;
- `/bin/sleep` and `/usr/bin/ffmpeg` (lavfi to null) under the dynamic loader;
- the reviewers' dummy process trees.

I never opened the live-game lock. I made no git writes. Pre-round copies of the owned files are in `/home/brunner56/kp-live-20260922/r13-baseline/`.

Environment note: partway through the round, `/tmp` (tmpfs) returned `Disk quota exceeded` for this user. Other sessions' trees (`/tmp/modsync-*` and others, not mine) were filling it. I deleted only my own partial encodes. I moved my encode cache to `/home/brunner56/kp-live-20260922/r13-work/content/`.

The first full container suite run used `TMPDIR` on btrfs. Four lock tests failed there: fdinfo reports the btrfs superblock device, not `st_dev`. That output is kept in `r13-suites/container/btrfs-tmpdir-run/`. Once `/tmp` was writable again, every suite reported below ran with the default `/tmp`.

## Files changed

All changes are inside the owned set. `recording.py` did not change: `cmp` against the baseline is identical.

- `scripts/harness/kpharness/display_backends.py`:
  - the policy keeps the id `animated-diagnostic-v2`, so the reviewer probes rerun unchanged. Its content changed: `separation_factor` 3.0 to 2.0, plus `level_period` 7, `level_step` 3, and `level_resolution_factor` 1.9. `content_recomputed` compares the whole policy dict, so a stale factor-3 receipt fails closed;
  - `decode_levels`, `content_level_sequence`, and `MAX_RECORDED_LEVEL_VIOLATIONS`;
  - `evaluate_content` appends `capture_content_sequence` independently of the separation result;
  - `_cadence_evidence_passed(..., content_aside=False)`. The default behaviour is byte-for-byte the old one.
- `scripts/harness/kpharness/capture_diagnostic.py`:
  - loader detection (`LOADER_NAME`, `LOADER_OPTIONS_WITH_VALUE`, `loader_program`), with `_match_exe` generalized to take a path and a key prefix;
  - `evaluate` precedence, with `failing_criteria` and `_cadence_recomputed_apart_from_content`;
  - `content_recomputation`;
  - `supervisor_thread_count()` reads `/proc/self/task`;
  - `DEFAULT_FFPROBE` is removed and `--ffprobe` is required;
  - `threading` is no longer imported.
- `tools/kpharness_gamescope_backend_test.py` and `tools/kpharness_capture_diagnostic_test.py`.
- `docs/creative-runner.md`.

## Red-first evidence

I wrote every test below first. I ran them against the unchanged modules and saved the output to `/home/brunner56/kp-live-20260922/r13-red/`.

- `red-backend-content.txt`: 29 tests, `FAILED (failures=10, errors=8)`. The behavioural failures:
  - the loops, missing-step, skip, torn, 7-skip and short-interval tests find no `capture_content_sequence`;
  - the guard-band test sees factor 3.0.
- `red-diagnostic.txt`: 23 tests, `FAILED (failures=19, errors=24)`. Behavioural:
  - 16 subtests of `test_any_failed_non_content_criterion_makes_ambiguous_content_a_fail` get `calibration_ambiguous`, not FAIL;
  - `test_a_raw_native_thread_is_counted_and_the_supervisor_refuses` gets `spawn_child` called;
  - `test_ffprobe_has_no_default...` finds `DEFAULT_FFPROBE`;
  - the loader tests hit `KeyError 'loader_program'` / `'loader_tool_match'`. The real-loader test ran and was not detected.

Not run red:

- The three new cases in the opt-in `RealEncodeContentTests` (two-frame loop, three-frame loop, step dropped). The unit tests already covered those shapes red.
- `evaluate_r13.py` and the probe reruns are measurements, not tests.

## Item 1: brightness level sequence (R12-2, R12C-m2, R12C-m3)

The rule is in `display_backends.content_level_sequence`, which `evaluate_content` runs for any policy with `level_period`.

- **Decode.** The acceptance frames' `yavg` values are sorted and split at their 6 largest gaps (ties go to the lower index). The groups are levels -3 to +3 in brightness order.
  - Only the order is used, never the luma scale.
  - The advisor flagged the scale as path-dependent: `pattern_yavg.out` has levels about 28 apart, while the bgr0 encodes have them about 17.6 apart.
  - `test_decoding_is_scale_free` covers compressed, expanded and uneven ladders.
- **Resolved.** The smallest split gap must be at least 1.9 times the largest gap left inside a level. Otherwise the result is `capture_content_sequence` ("do not decode to 7 separated brightness levels").
- **Step.** Take delta = (level − previous level) mod 7.
  - delta 3 is a fresh step. delta 0 is a duplicate.
  - Any other delta is a violation.
  - Delta 0 with a difference ≥ floor×2 (clearly fresh) is a violation.
  - Delta 3 with a difference ≤ floor/2 (clearly a duplicate) is a violation.
  - Differences inside the band get no cross-check. They are left to the separation rule.
- **Recorded** as `content.level_sequence`:
  - the ladder (thresholds, centers, gaps, resolution, resolved);
  - `level_histogram` (count per level -3 to 3);
  - `steps`, `repeats`, and `violation_count`;
  - up to 64 violations, each with index, PTS, previous level, level, step, difference and kind;
  - `reason`.
- `supervise` writes the recomputed block to `diagnostic-result.json` as `content_level_sequence`, next to `content_separation`.

Resolution factor calibration: `r13-work/evaluate_r13.out` runs production `evaluate_content` over 18 fresh writer encodes (`r13-work/encode_r13.py`, with the recorder's codec and the production probes) plus the adversarial p18 cache.

- The clean families gave a resolution of at least 3.93 over 8 s clips (fresh native and isodup native), 4.02 at 4x speed, and 20.02 over a 34 s clip with a 30 s acceptance interval.
- The factor 1.9 is half of 3.93, rounded down.
- This is pinned as `CALIBRATED_LEVEL_RESOLUTION_MIN = 3.93` in `test_policy_carries_the_pattern_period_step_and_a_calibrated_resolution_factor`.

Results (production code, `evaluate_r13.out`, `r13-probes/p18.host.out`, `r13-probes/nostep_probe.host.out`):

| Shape | Verdict | Failures |
| --- | --- | --- |
| clean native, slowq, fast4, static, 34 s long | passed | none; histogram 257/258/257/257/258/257/257 on the long clip |
| two-frame loop (p18 `abab`, writer `pingpong`) | failed | `capture_content_sequence` (res undefined, 359 violations), separated |
| three-frame loop (`cycle3`) | failed | `capture_content_sequence`, separated |
| step dropped, native (`nostep_probe`) | failed | `calibration_ambiguous` + `capture_content_sequence` |
| step `eval=init` | failed | same |
| step dropped, quarter speed (R12C-m3) | failed | `capture_content_static` + `capture_content_sequence` (res 1.0) |
| torn half every 100 | failed | `capture_content_sequence` (res 1.2, 8 violations) |
| torn quarter every 100 | failed | `capture_content_sequence` (res 1.96, resolved, 8 violations) |
| `tblend_average` | failed | `capture_content_sequence`. It is now *separated* (min 8.34 > 7.8), so the narrower band no longer flags it; only the sequence does. |
| one skipped source frame | failed | `capture_content_sequence`, 1 violation (step 6) |
| **duplicate then skip (drift), isodup_* families** | **failed** | **`capture_content_sequence`, 3 violations each (step 6)** |
| `half_frozen_bottom`, `quarter_fresh_top` | **passed** | documented residual (below) |
| `tenth_fresh_top` | failed | `calibration_ambiguous` only |

- The opt-in real-encode test on the host (`r13-probes/real-encode-test.host.out`) gave `OK`. `two_frame_loop` and `three_frame_loop` fail with only `capture_content_sequence`, and `step_dropped` fails with ambiguity plus sequence. `full_animated_60` and `slow_quarter_stepped` pass.
- **Partial frames:** caught when intermittent (torn), through the resolution rule or violations. A region frozen for the **whole clip** only compresses the ladder and is not caught by the level sequence. `test_whole_clip_partial_freeze_is_a_documented_residual` pins this, and the docs name it.
- I did not add an absolute luma-spacing floor. It would close `quarter_fresh_top` (spacing 3.82 vs 15.3), but it could false-fail the real run on an unmeasured path scale. The brief's "if detectable through the level sequence" covers leaving it out.

## Item 2: guard band

- `separation_factor` 2.0 gives the band (1.95, 7.8).
- The constants are now `CALIBRATED_DUPLICATE_MAX = 1.2414` (R12C-m1). I also set `CALIBRATED_FRESH_MIN = 14.887`, the same review's measured minimum, which is below the writer's old 15.2818.
- Margins recomputed in `display_backends.py` and the docs:
  - floor/dup max = 3.14;
  - fresh min/floor = 3.82;
  - lower edge/dup max = 1.57;
  - fresh min/upper edge = 1.91.
- `test_guard_band_is_half_to_twice_the_floor_and_clears_both_calibrated_populations` checks these.

## Item 3: label precedence (R12-3, R12C-m5a)

`evaluate` returns `failing_criteria` (in `CRITERIA` order). `supervise` writes it and also prints it on the result line. The verdict is:

- PASS if nothing fails;
- `calibration_ambiguous` only if all of these hold:
  - the recomputed separation is ambiguous;
  - every recomputed content failure starts with `calibration_ambiguous`, so the sequence passed and the frame is not black;
  - every non-content criterion passed;
- otherwise FAIL.

`cadence_evidence_recomputed` always fails with content, because the recorder folds content failures into `cadence.status`. So for the precedence decision it is judged "apart from content":

- no non-content entry may appear in `cadence.failures`;
- `_cadence_evidence_passed(content_aside=True)` must pass on a copy with status `passed`;
- the window must match.

The result records this as `cadence_recomputed_apart_from_content`.

Tests:

- `test_any_failed_non_content_criterion_makes_ambiguous_content_a_fail`: 17 non-content criteria × ambiguous content, each giving FAIL with the criterion listed. This includes the tampered p95 gap for `cadence_evidence_recomputed`.
- `test_a_content_sequence_failure_is_a_fail_even_when_separation_is_ambiguous`.
- `test_guard_band_content_is_calibration_ambiguous_whatever_else_passes` now asserts `failing_criteria == ['content_gate', 'cadence_evidence_recomputed']` with `cadence_recomputed_apart_from_content` True.

"Lock" has no criterion in `CRITERIA`. A refused lock raises before launch. `launches == 0` forces FAIL (`result['verdict'] = ... if result['launches'] else 'FAIL'`), and `no_driver_error` fails. A child that refuses its lock check leaves no run evidence, so `no_driver_error` and cleanup fail too.

## Item 4: dynamic loader (R12-1, R12C-m4)

- A row is a loader launch when `comm`, the `exe` basename, or `argv[0]` fully matches `ld-linux[\w.-]*|ld\.so(\.[0-9]+)*|ld-[0-9.]+\.so`. That covers the 15-character comm `ld-linux-x86-64` and Homebrew's `ld.so`.
- The program is the first argument after `argv[0]` that is not a loader option. `--library-path`, `--inhibit-rpath`, `--audit`, `--preload`, `--argv0` and `--glibc-hwcaps-*` consume a value.
- It is recorded as `loader_program`. Its basename joins the name check.
- For rows of this user, the program file (relative paths resolve against `/proc/PID/cwd`) is matched by inode, then by size and SHA-256, like `exe`. The result goes in `loader_tool_match`, `loader_match_by`, or `loader_program_unreadable`.
- `forbidden_processes` refuses on `loader_tool_match`.

Reruns:

- `review-probes-r12-correctness/ldso_probe.py`, unchanged, on the host and in the container: `ldso_renamed_enc detected= True`, `ldso_named_ffmpeg detected= True`. It prints `match= None` because it reads `exe_tool_match`.
- Adapted `r13-probes/ldso_probe_r13.py`: `loader_match= ffmpeg sha256` for both. `--library-path /nonexistent/ffmpeg --argv0 x ./enc` gives `loader_program= ./enc`, detected by sha256.
- `review-probes-r12-adversarial/p19_renamed_binaries.py`, unchanged, on the host with a real `/usr/bin/ffmpeg` under the loader:
  - `loader_invocation_of_real_ffmpeg detected=True` and `loader_invocation_of_renamed_copy detected=True` (round 12: both False);
  - execute-only copy `detected=False`, which is the documented non-dumpable residual.

Remaining gap, documented: a program loaded another way, such as `dlopen`.

## Item 5: thread count (R12-4, R12C-m5b)

- `supervisor_thread_count()` is `len(os.listdir('/proc/self/task'))`. It is recorded as `supervisor_threads_at_spawn`.
- `test_a_raw_native_thread_is_counted_and_the_supervisor_refuses` starts a `_thread` thread and asserts `threading.active_count() == 1`. It then checks that the supervisor refuses, `spawn_child` is never called, and `launches == 0`.
- Probes:
  - `thread_probe_r13.py` (host and container): `with _thread: active_count 1 supervisor_thread_count 2`.
  - p16 rerun unchanged: `a) threading.active_count()=1 os_threads=2`, `b) handler_ran=2000/2000 mask_left_blocked_after_raise=0`.

## Item 6: publication leaks

- `docs/creative-runner.md`: the `/home/<user>/kp-live-20260922/r12-calibration/` path is gone. `grep -n "/home/\|/run/media\|linuxbrew\|Homebrew" docs/creative-runner.md` finds nothing.
- `capture_diagnostic.py`:
  - `DEFAULT_FFPROBE` is removed and `--ffprobe` is `required=True`;
  - the value must pass `native_elf_identity`: absolute, a regular file, executable, with ELF magic. Wrappers are refused, as the existing test shows;
  - commitments carry `ffprobe_resolved_path` and `ffprobe_sha256`, and `preflight.json` carries `tool_identities`. The commitments test asserts both;
  - `test_ffprobe_has_no_default_and_must_be_given_explicitly`: argparse exits 2 naming `--ffprobe`, no run directory is created, and the module text has no `linuxbrew`.
- Other `linuxbrew` mentions exist outside my owned files, in `docs/harness-design.md` and `docs/harness-research/*`. I left them alone.

## Validation

Output is in `/home/brunner56/kp-live-20260922/r13-suites/`. All suites ran one at a time.

```text
# container (Python 3.12.3): PYTHONPATH=scripts/harness:tools python3 tools/kpharness_<suite>_test.py
creative 39 OK | gamescope_boot_repair 41 OK | gamescope_backend 155 OK (skipped=1) | capture_diagnostic 57 OK
# host (Python 3.14.7): host-cmd sh -c 'cd <worktree> && PYTHONPATH=scripts/harness:tools python3 tools/kpharness_<suite>_test.py'
creative 39 OK | gamescope_boot_repair 41 OK | gamescope_backend 155 OK (skipped=1) | capture_diagnostic 57 OK
```

- That is 292 per environment. Round 12 had 266.
- Creative went from 33 to 39 through other writers' changes; I did not touch it.
- The opt-in `RealEncodeContentTests` ran separately on the host with `KP_R11_REAL_ENCODES=1`: 1 test, OK.
- `py_compile` of the 4 changed Python files: OK. There is no trailing whitespace in the 5 touched files. `git diff --check -- docs/creative-runner.md` is clean.

Reviewer probe reruns, all under `/home/brunner56/kp-live-20260922/r13-probes/`:

- `ldso_probe` (container and host), plus p19 (host);
- `nostep_probe` (host, 3 new encodes);
- p16 and the `_thread` probe (container and host);
- the stale-loop encodes. p18 on the host reused the adversarial reviewer's cached rows in `/tmp/kp-r12-adv-content`. These are the real encodes' probe output, so only the evaluation is new. The writer's fresh `pingpong_native` and `cycle3_native` encodes are new encodes (`r13-work/content/`).

## Verification (continuation, same round)

Picked up after a model switch. Nothing above was rewritten; this reruns what the report already cites, then checks the diffs and artifacts against the report's own claims.

- **Container, rerun this session:** `creative 39 OK | gamescope_boot_repair 41 OK | gamescope_backend 155 OK (skipped=1) | capture_diagnostic 57 OK` — matches the table above exactly.
- **Host, default `/tmp`, rerun this session:** same four counts, all OK. Host `/tmp` is now 46% used (`df -h /tmp`), so the quota exhaustion this report opens with has cleared.
- **Host, `TMPDIR=/home/brunner56/kp-live-20260922/tmp-r13` (btrfs, per the resume brief):** reproduces the same failure class the report already names under "btrfs-tmpdir-run" — `gamescope_boot_repair` 1 error (`test_canonical_lock_capability_required_and_contention_preserves_node`) and `capture_diagnostic` 1 error (`test_production_check_admits_only_the_passed_descriptor_holding_the_trusted_lock`), both `RuntimeError` out of `gamescope_socket.held_lock_descriptor`/`canonical_lock_guard` — a file outside the owned set. Reran the single failing `capture_diagnostic` test 3x under that TMPDIR: fails every time, same trace. This is filesystem-dependent lock-fd identity, not a round 13 regression: none of round 13's owned files (`display_backends.py`, `capture_diagnostic.py`'s content/loader/thread/label code, `recording.py` unchanged) touch lock-fd comparison. The counts pasted above are the default-`/tmp` run, matching what the report's own table already reports.
- **Diffs vs `r13-baseline/`:** `recording.py` is `cmp`-identical (exit 0). `display_backends.py` and `capture_diagnostic.py` diffs match the report's per-item descriptions (separation_factor 2.0, level_period/step/resolution_factor, CALIBRATED_DUPLICATE_MAX=1.2414/CALIBRATED_FRESH_MIN=14.887 in the test file, `--ffprobe` required with no `DEFAULT_FFPROBE`, no `linuxbrew`/`/home/` leaks in `docs/creative-runner.md`).
- **Probe files under `r13-probes/`:** contents match what's quoted in the body (`ldso_probe_r13.host.out` all `detected= True`; `thread_probes.host.out` shows `supervisor_thread_count 2` with one raw `_thread`; `nostep_probe.host.out` and `p18.host.out` show the claimed verdicts and violation reasons; `p19.host.out` shows both loader-launch rows `detected=True`; `real-encode-test.host.out` shows `two_frame_loop`/`three_frame_loop`/`step_dropped` failing only under `animated-diagnostic-v2`).
- **Hygiene:** `py_compile` on all four changed Python files: OK. No trailing whitespace in the touched files. `git diff --check -- docs/creative-runner.md`: clean. `git log --oneline -1` still at `ca329e5`: no commits made.

## Incomplete or not done

- No real mpv, Gamescope, or x11grab path was run. The one authorized diagnostic has still not run.
- The new real-encode cases were not run red.
- Whole-clip partial freeze is a documented residual.
- The resume brief's `TMPDIR=tmp-r13` (btrfs) instruction surfaces the same lock-fd-identity artifact the report already flagged under a different tmpdir; not chased further since the affected code (`gamescope_socket.py`) is outside the owned file set and the report's validation already used default `/tmp` once it was writable.

## Grill me

1. **Won't exact +3 fail a healthy real run that has one late frame?** (weakest)
   Yes, if the late frame shows up as a duplicate followed by a skip.
   - `drift_dup_skip_native` and every `isodup_*` family fail with 3 step-6 violations each (`evaluate_r13.out`). Their DIF duplicate ratio (0.8%) would pass the old gate.
   - A pure duplicate followed by +3 passes (`test_counted_duplicates_repeat_the_level_and_still_pass`).
   - The brief says "exactly", so I kept zero tolerance. The real mpv to x11grab dup/skip rate is unverified.
   - What settles it: `content_level_sequence.violation_count` and the violation kinds in the authorized run's `diagnostic-result.json`.
2. **Is a factor of 1.9 safe for the real run?**
   - The synthetic minimum is 3.93 at 8 s and 20.02 at a 30 s interval (`evaluate_r13.out`).
   - The real-path yavg noise from dithering and compositing is unverified.
   - A path that adds scattered yavg outliers inside a level would lower the ratio and fail as `capture_content_sequence`, not as a pass.
3. **Why keep the policy id v2 when its content changed?**
   - `content_recomputed` compares the full policy dict, so an old factor-3 receipt is refused. A v2 content gate on an old receipt fails, as `test_a_receipt_cannot_claim_separation_the_artifact_does_not_show` (the loosened-factor part) shows.
   - Keeping the id let `nostep_probe.py` and `p18_content_attacks.py` rerun byte-unchanged.
   - Cost: two different v2 dicts have existed over time, and nothing live ever ran under the old one.
4. **Can a cadence fault hide under `calibration_ambiguous` through the content-aside recomputation?**
   - No. It requires zero non-content `cadence.failures` and a passing `_cadence_evidence_passed(content_aside=True)`. The only thing skipped is `_content_evidence_passed`.
   - The subtest with a tampered p95 gap gives FAIL.
5. **Does the narrower band weaken anything?**
   - `tblend_average` moved from ambiguous to separated (fresh min 8.34 > 7.8). Only the level sequence now catches it (`p18.host.out`).
   - `tenth_fresh_top` stays ambiguous (351 inside the band), and quarter/half frozen still pass (the residual).

Handoff, the one question not settled: how often does the real mpv to x11grab path produce a duplicate followed by a skip? The single check is the authorized run's `content_level_sequence`: its `violation_count` and violation kinds, alongside `content_separation`.


<a id="round-14"></a>

---

Original file: `task-7-capture-cadence-fix-round-14-report.md`

# Task 7 capture cadence fix, round 14 report

Date: 2026-09-28. Sole writer. Brief: `/home/brunner56/kp-live-20260922/task7-capture-cadence-round-14-brief.md`.

## Scope and ownership

Host-only work in the assigned worktree. The changed implementation files are `scripts/harness/kpharness/display_backends.py`, `scripts/harness/kpharness/capture_diagnostic.py`, `scripts/harness/kpharness/recording.py`, and `scripts/harness/kpharness/gamescope_socket.py`; the assigned test files are `tools/kpharness_gamescope_backend_test.py` and `tools/kpharness_capture_diagnostic_test.py`; the documentation file is `docs/creative-runner.md`. No live-game lock, Wine, Gamescope, mpv, x11grab, or game process was started.

## Round-14 fixes

The diagnostic graph now appends two independent 14-bit binary index copies plus parity, in top and bottom 32-pixel bands. `evaluate_content` decodes both regions, requires parity and region agreement, rejects non-monotonic/repeated-loop indices, and cross-checks fresh index jumps against PTS elapsed frames. The diagnostic receipt records the `index_sequence` summary and bounded violations alongside the existing +3 mod-7 level signal.

The lock descriptor check now matches the fdinfo FLOCK record by inode, ignoring the btrfs device field that disagrees with `fstat`/`stat`, and confirms exclusivity by attempting a nonblocking lock on a fresh probe descriptor. The probe releases the descriptor immediately on the unexpected-success path.

## Host validation

The default host suites passed:

```text
creative              39 OK
gamescope_boot_repair 41 OK
gamescope_backend     155 OK (skipped=1)
capture_diagnostic    57 OK
```

The backend fixtures were updated to emit barcode fields only at the diagnostic policy boundary. A counted duplicate case explicitly carries a repeated source index, while game-capture fixtures retain the original row schema.

The lock probe ran against a temporary file on `/home/brunner56` (btrfs):

```text
held True
fake_refused RuntimeError canonical lock descriptor does not hold the exclusive lock
```

The unmodified round-13 loop probe was also run. It rejected its rows as malformed because it does not pass the new `index_policy`; that result was not treated as proof. An adapted production probe was then run through `host-cmd` with `index_policy={bits:14,cell:32,inset:6}` and `height=768` on 8-second 1024x768 libx264 ultrafast CRF-28 clips.

## Adapted synthetic evidence

The exact adapted probe is retained at `/home/brunner56/kp-live-20260922/pl5-scratch/r14_adapted_index_probe.py`. It used `/usr/bin/ffmpeg`, the host ffprobe, `PATTERN_GRAPH`, and production `R.probe_frame_content`/`D.evaluate_content`. Acceptance interval was 1–7 seconds. Its encoded media remain at `/tmp/kp-r14-8s-2291a5l9/{healthy,loop7,loop14}.mp4`.

```text
healthy  status=passed index_status=passed index_violations=0 separation=separated bit_margin=221.1
loop7    status=failed index_status=failed index_violations=52 index_kinds=[non_monotonic] bit_margin=219.0
loop14   status=failed index_status=failed index_violations=26 index_kinds=[non_monotonic] bit_margin=220.0
half_freeze status=failed index_status=failed index_violations=361 index_kinds=[region_mismatch]
```

The half-freeze case freezes the bottom decoded region to the first frame after the healthy production decode; it is a typed region-mismatch proof for the two-region gate. The clean control passes the same decoder and policy. The observed bit-on/off separation was 219.0–221.1 luma units across the encoded clips, above the documented 106-unit minimum.

## Btrfs suite run

The required second suite run used `TMPDIR=/home/brunner56/kp-live-20260922/tmp-r14-btrfs`, confirmed btrfs (`stat -f -c '%T'` → `btrfs`). Through `/home/brunner56/.local/bin/host-cmd`, all four suites passed: `creative 39 OK`, `gamescope_boot_repair 41 OK`, `gamescope_backend 155 OK (skipped=1)`, and `capture_diagnostic 57 OK`. Raw retained output is `/tmp/r14-btrfs-{creative,gamescope_boot_repair,gamescope_backend,capture_diagnostic}.out`. The direct lock probe above exercises the btrfs fdinfo mismatch path.

## Claims and evidence

claim: The barcode closes period-7 and period-14 loops.
referent: Adapted 8-second production probes: `loop7` had 52 `non_monotonic` index violations; `loop14` had 26 `non_monotonic` violations; both were `status=failed`.
checked: `/usr/bin/ffmpeg` production graph/codec; `probe_frame_content(... index_policy=..., height=768)`; `evaluate_content(..., 1.0, 7.0, animated-diagnostic-v2)`.
verdict: holds
confidence: high; a longer real diagnostic would change only the measured drop profile, not the typed loop result.

claim: A healthy encoded diagnostic passes the new gate.
referent: Adapted 8-second control: `healthy status=passed index_status=passed index_violations=0 separation=separated`.
checked: Same graph, codec, decoder, policy, and acceptance interval as the loop probes.
verdict: holds
confidence: high; real mpv-to-x11grab behavior remains unverified.

claim: A partial bottom freeze is rejected independently of the level signal.
referent: Adapted half-freeze: `index_status=failed`, `index_kinds=[region_mismatch]`, 361 violations.
checked: Bottom index arrays replaced with the first decoded bottom region after production decode; evaluated by `content_index_sequence`.
verdict: holds
confidence: high; a live partial-frame shape remains unverified.

claim: The barcode decode margin is adequate under the recorder codec.
referent: Healthy/loop encoded clips measured bit luma ranges with minimum observed on/off separation 219.0, compared with documented 106-unit minimum.
checked: 8-second 1024x768 libx264 ultrafast CRF-28 encodes and production signalstats crop probe.
verdict: holds
confidence: high for this host/codec; another encoder or compositor could require a fresh measurement.

claim: The btrfs lock-fd fix refuses an unlocked same-inode descriptor.
referent: Temporary btrfs file probe printed `held True` and `fake_refused RuntimeError canonical lock descriptor does not hold the exclusive lock`.
checked: `held_lock_descriptor` with one flock-held fd and one independently opened same-inode fd.
verdict: holds
confidence: high; canonical production lock remains on ext4 and was intentionally not opened.

## Grill me

1. Why is the half-freeze evidence not a full media proof? It mutates decoded bottom arrays after a healthy production decode, so it proves the typed evaluator rejects region disagreement; a separate compositor-generated partial-frame encode would settle the media-shape question.
2. Why are the loop counts below the clip frame count? The acceptance interval is 360 frames and the decoder records at most 64 index violations; the typed count is the full violation count, while the list is bounded for receipt size.
3. Does the btrfs test prove production lock behavior? It proves the exact fdinfo inode/exclusivity logic on a btrfs temporary file. The live-game lock was not opened, as required.
4. What remains unresolved? Real mpv-to-x11grab duplicate/drop rates. The required round-13 drift/duplicate/skip family sweep was not rerun in round 14; the adapted control/loop/half-freeze probes above are the bounded round-14 evidence. No live diagnostic was authorized in this unit.

Open question I could not settle: whether the real mpv-to-x11grab path produces a duplicate followed by a skip often enough to exceed the exact index/PTS policy. The single settling check is the authorized diagnostic's `diagnostic-result.json` `content_level_sequence` and `index_sequence` blocks.


<a id="round-15"></a>

---

Original file: `task-7-capture-cadence-fix-round-15-report.md`

# Task 7 capture cadence correction, round 15

## Verdict

**PASS for the R15 host correction; integration gate remains conditional on the
existing live Gamescope/media acceptance.** The host content gate now accepts a
single validated source advance within the shared cadence budget, while it
rejects accumulated source loss, an overlarge source gap, and same-brightness
index advances. No live game, Wine, display, encoder, or media launch was used.

## Claim and checked referent

The checked referent is the current worktree
`/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`.
The one-drop failure recorded in `/tmp/kp-root-r14-one-drop.json` showed an
index gate pass with a legacy level gate failure. R15 binds level expectations
to the decoded source advance: a fresh index delta `d` expects `3*d mod 7`,
while an index repeat remains an optical duplicate. The index gate also
accumulates decoded dropped source frames and records the maximum source gap.
Both aggregate checks use the shared `gamescope-cadence-v1` thresholds (0.5%
drop ratio and 50 ms gap), with a small `1e-12` comparison guard for binary
floating point at an exact threshold. Aggregate failures are retained before
the bounded per-frame violation details.

## Evidence

The bounded command below was run from the stated worktree, with no product
build or live process:

```text
python3 -m py_compile scripts/harness/kpharness/display_backends.py \
  tools/kpharness_capture_diagnostic_test.py \
  tools/kpharness_gamescope_backend_test.py
python3 -m unittest tools.kpharness_capture_diagnostic_test -v
```

Result: **61 tests passed in 21.455 s**. The focused R15 cases also passed,
including a direct regression probe for loop7, loop14, stale replay, and
adjacent reorder inputs: each returned a structured failed result without an
exception.

* one source drop within policy: index and level gates pass;
* sustained `delta=2`: accumulated `source_drop_ratio` fails;
* one `delta=7` same-brightness jump: `source_gap` fails even while total
  ratio stays below 0.5%;
* pure duplicates and duplicate followed by one within-policy skip pass;
* all prior stale/loop/ambiguous and lifecycle criteria remain green in the
  full host suite.

The complete stdout/stderr receipt is
`/home/brunner56/kp-live-20260922/r15-focused-suite.log`, SHA-256
`955b23b9d8a08ffaa223c8fd22f31bd027f38b1845bff06d17e9eeba20f37b72`.

Source hashes at command start were:

```text
bca12b48d48b9d9545b6dead2f5f8314b06ac3ff96958328183dd35da4e32575  scripts/harness/kpharness/display_backends.py
7bdc2df4ae3750a58660465340eaf352eb3d6f36b38a2fea1bcdf231100cda2d  tools/kpharness_capture_diagnostic_test.py
ccb220b6058db9c818b2978b14e0c9644560578b882e4949160e1f4af07ce48c  tools/kpharness_gamescope_backend_test.py
347e2942fc5a3153fb88b410aaab372ee077f1122252ed6c5f9e802deca04d7b  docs/creative-runner.md
```

## Integration gate

This is a host correctness PASS only. Before K1 acceptance, the independent
Gamescope run must still provide the required retained master, canonical PTS
binding, full prior clean/drift/duplicate/skip family evidence, 34-second
production deadline and byte budget, and the existing cleanup/renderer/window
proof. This report supplies no live-media evidence and does not waive those
gates.

## Unsettled question

The production diagnostic must serialize the new index aggregate fields into
its retained receipt and the acceptance verifier must recompute them from the
hashed artifact. A future receipt that only reports the legacy level sequence
is insufficient even if the host suite remains green.
