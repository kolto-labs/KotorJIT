# Task 7 capture-cadence adversarial review

Reviewed the uncommitted capture-cadence implementation in `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation` without modifying the worktree and without launching FFmpeg, ffprobe, Gamescope, Wine, Xvfb, or the game. Validation used the existing mock-only Python suites and focused ad hoc Python probes.

## Verdict

No Critical findings. Seven Important findings remain. The implementation fails closed in several ordinary error cases, and the existing mocked Xvfb and post-accept export paths pass, but an acceptance-bearing animated diagnostic is **not safe yet**. Cadence can reject perfect input, marker order can be lost, final window identity can go unchecked, an unkillable recorder can be forgotten, and acceptance provenance can be changed or redirected through symlinks. A disposable preview in a trusted, single-user run directory may still be useful for debugging, but it must not be represented as accepted capture evidence.

## Critical

None found.

## Important

### 1. Ordered markers observed in one poll are assigned the same time and rejected as out of order

`X11Recorder.observe()` assigns the caller's single `now` value to every complete line in a read (`recording.py:276-308`). `X11WindowRecorder._finalize_cadence()` then requires the end marker's `capture_seconds` to be strictly greater than the start marker's and sorts the configured sequence by that same value (`recording.py:415-429`). The Gamescope watcher polls every 250 ms or slower (`recording.py:361-362, 693-710`). Two correctly ordered log markers emitted within one poll therefore receive identical times and fail with `capture_markers_incomplete: marker order is not increasing`.

The ad hoc probe wrote `phase start\nphase end\n` before one observation. The stored byte ends proved order (`12`, then `22`), but both marker times were `0.25`, and cadence failed. This is a normal fast-transition case, not malformed input.

Use byte order to establish marker ordering and retain a bounded timing interval for each poll, or timestamp lines at emission through a monotonic source. Do not turn one poll timestamp into an assertion that distinct ordered lines were simultaneous.

### 2. Perfect PTS cadence fails for intervals whose endpoints fall between frames

`analyze_pts()` counts expected slots as `round((interval_end - interval_start) * fps)` but compares that to the number of gaps between frames whose PTS values lie inside the closed marker interval (`recording.py:133-141`). For a perfect 60 fps stream from 0 through 2 seconds, the interval `[0.005, 1.005]` selects 60 frames and 59 gaps. The function expects 60 slots, reports one missing slot and a 1.6667% drop ratio, then fails the 0.5% threshold even though effective cadence is exactly 60 fps and every gap is 1/60 second.

The same probe passed `[0, 1]` and failed both `[0.005, 1.005]` and `[0.016, 1.016]`. Marker detection times are not frame aligned, so this is expected in real captures, especially for short diagnostic intervals.

Compute expected samples from the first and last included PTS, account for the two partial boundary cells, or compare observed gaps against an endpoint-aware expected range. Add offset intervals at multiple durations to the regression suite.

### 3. Stop removes the watcher before the last binding check and can mark a changed window as passed

The continuous watcher verifies the window identity and full-root geometry (`recording.py:693-710`), but `stop()` sets the stop event and joins the watcher before finalizing FFmpeg (`recording.py:725-744`). It never calls the verifier or `_binding()` again. A resize, window replacement, or geometry change after the last 250 ms check and before/during SIGINT finalization is therefore absent from the receipt. A mock recorder whose verifier always raised `window resized` completed `stop()` with `capture.status == "passed"`, `failure is None`, and zero verifier calls.

Run a synchronous final identity and geometry verification immediately before signaling FFmpeg, and preferably again after finalization when the lease/window is still owned. Persist the last successful check time and require it to bracket the terminal frame within a defined uncertainty.

This same shutdown ordering also loses a cadence-end marker that is already in the native log but has not yet been consumed by the watcher. `stop()` does not retain the native-log path and performs no final `observe()` drain. Final marker ingestion should happen synchronously before cadence finalization.

### 4. A recorder that survives SIGKILL is forgotten and session cleanup can call the recorder step passed

After the 15-second graceful wait, `stop()` kills FFmpeg and waits five seconds. If that second wait also times out, it ignores the timeout, records `capture_finalize_timeout`, and later clears `self.process` (`recording.py:738-768`). `LinuxWineGamescopeCreativeSession.teardown()` marks a cleanup operation passed whenever it returns without raising (`creative_wine.py:263-289`). The process may therefore still be alive while the recorder cleanup component says `passed`, and the handle needed for a retry has been discarded.

The mock probe made both waits raise `TimeoutExpired`; `stop()` returned, `self.process` became `None`, the failure cleanup remained `{"owned_process": true, "status": "pending"}`, and the owned process mock had merely received one `kill()` call.

Keep the process identity and handle until death is proven, set cleanup to failed, and raise from `stop()` when the post-kill wait expires. Teardown can then preserve the failed cleanup receipt and retry/reap the exact owned PID safely.

### 5. FFmpeg can overwrite a symlink target before output validation rejects the capture

The recorder passes `-y <run_dir>/continuous.mp4` directly to FFmpeg (`recording.py:636-641`). It checks `is_symlink()` only after progress reports the first frame (`recording.py:541-547, 600-603`). A symlink created between fresh run-directory creation and FFmpeg opening the output is followed and overwritten before the recorder fails closed. The ad hoc Popen stub reproduced this: startup raised `capture_output_invalid`, but the external target had already changed from `ORIGINAL` to `OVERWRITTEN`. `ffmpeg.log` is also opened with ordinary append semantics and follows a raced symlink (`recording.py:632-634`).

Create recorder-owned files with exclusive, no-follow semantics and pass FFmpeg an already-open descriptor where supported, or encode to an exclusively created private staging directory whose ownership and inode identity are checked before and after the process. At minimum, reject every existing output/log path before launch and retain inode/device identities, while recognizing that a pathname-only check still has a race.

The random fresh run directory reduces accidental exposure, but it does not enforce the claimed safety boundary against a concurrent same-UID process.

### 6. Acceptance's fixed temporary filename follows symlinks and can publish the receipt as a symlink

`accept()` writes to the predictable `creative-run.json.tmp` with `Path.write_text()` and then replaces the real receipt (`creative_accept.py:74-76`). A pre-existing symlink at that temporary path is followed during the write. The subsequent replace moves the symlink itself onto `creative-run.json`. The function verifies only the in-memory receipt before this write and returns success without reopening the published file.

The ad hoc probe linked `creative-run.json.tmp` to `victim.txt`. `accept()` returned `ok=true`, overwrote `victim.txt` with the accepted receipt, installed `creative-run.json` as a symlink, and `verify_acceptance()` still returned true when reading it. This permits arbitrary same-permission file overwrite and breaks the expectation that the accepted receipt is an immutable run-local file.

Use the repository's existing `_atomic_write()` pattern (`gamescope_snapshot.py:45-55`): an unpredictable same-directory name, exclusive creation, fsync, `os.replace`, directory fsync, and a post-publication regular-file/no-symlink check. Keep the final file descriptor or inode identity when verification must cover the exact bytes that were published.

### 7. Reviewer identity, acceptance time, and review scope are not protected by acceptance verification

The execution digest intentionally removes the entire `visual_review` object (`creative_accept.py:15-21`). `verify_acceptance()` checks the review status, execution digest, and media hash, but does not authenticate `reviewer`, `accepted_utc`, or `scope` (`creative_accept.py:24-35`). After a valid acceptance, changing each of those fields independently still returned `True` in the ad hoc probe.

This allows a schema-2 receipt to falsely attribute acceptance to another reviewer or time without invalidating acceptance or blocking export. Bind a canonical review record to the execution digest and media digest with a separate `acceptance_receipt_sha256`, or include all review metadata except that digest in its preimage and verify it before export.

## Minor

None retained as standalone findings.

## Residual risks and coverage limits

- FFmpeg progress and diagnostic files are read to EOF without a byte cap (`recording.py:506-539`). Well-formed FFmpeg output is incremental and bounded per poll, but a concurrent same-UID writer can force large allocations or retain an indefinitely growing unterminated progress suffix. Bound file growth and pending-line size if the run directory is meant to resist malicious mutation.
- Log readers do not detect inode replacement, and the FFmpeg log reader does not reset its offset on truncation. A replacement/truncation can hide later fallback diagnostics. This is primarily relevant under concurrent mutation; ordinary FFmpeg does not rotate these files.
- Post-accept export rechecks receipt bytes and the master's digest before and after rendering, which is a good fail-closed baseline, but it cannot prove the encoder read one stable inode if a same-UID actor swaps the master and restores it during encoding. Descriptor-based input would close that time-of-check/time-of-use gap.
- No real FFmpeg/ffprobe/Gamescope/Wine/game run was permitted or performed. The review establishes mock-level logic failures and cannot validate actual FFmpeg progress vocabulary, filesystem behavior under the production mount, GPU capture cadence, or visual animation quality.

## Passing checks

- `PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_backend_test.py`: 52 tests passed. These are host-only mocks and launch none of the prohibited programs.
- `PYTHONPATH=scripts/harness python3 tools/kpharness_creative_test.py`: 29 tests passed. This covers the legacy Xvfb orchestration through mocks and confirms Gamescope still defers derivatives until acceptance.
- The focused export tests passed, including invalid bounds/FPS, encoder failure, master replacement, provenance drift before/during render, duration truncation, and successful reviewed-interval publication.
- Split FFmpeg progress tokens across reads parse correctly. Progress is written to a file rather than a pipe, stderr is a regular log file, and stdout is `DEVNULL`, so the reviewed launch does not expose a pipe-capacity startup deadlock.
- Split forbidden FFmpeg diagnostic strings are preserved through an overlap tail, although truncation/replacement remains a residual gap described above.
- `git diff --check` passed for the reviewed capture, receipt, acceptance, export, and test files.

## Safe-use decision

Do not use the current path to produce or label an animated diagnostic as accepted evidence. Fix findings 1 through 7 and rerun the mock suites plus a bounded real capture/ffprobe validation before claiming safety. The existing post-accept exporter itself retained its mocked behavior, so after provenance, cadence, final-binding, and cleanup fixes it remains the right place to generate the MP4/GIF derivative.

---

# Fix round 1 adversarial re-review

Reviewed `.superpowers/sdd/lua-boundary-validation-plan/ta[REDACTED].md` and the current worktree implementation. No worktree files were edited, and no real FFmpeg, ffprobe, Gamescope, Xvfb, Wine, or game process was launched. All execution below used mocks or pure Python.

## Round 1 verdict

Round 1 closes six of the seven original findings under deterministic probes. The same-poll marker defect remains at cadence finalization, and four additional Important gaps were found in progress publication, setup cleanup, schema command binding, and route/capture schema enforcement. No Critical findings and no standalone Minor findings were retained.

**One animated diagnostic is not safe yet as acceptance-bearing evidence.** The new master staging and post-accept export paths are materially safer, but the current implementation can still reject valid fast markers, allow FFmpeg's progress pathname to overwrite a raced symlink target, lose resources and durable evidence during diagnostic-file setup failure, and accept schema-2 evidence whose command output or route predicates were altered. A disposable non-authoritative run on a trusted host would still exercise these unresolved correctness paths and should wait for the next fix round.

## Critical

None found.

## Important

### R1-1. Same-poll markers are ordered in the receipt but still form an invalid zero-length cadence interval

The new byte-end and sequence fields correctly preserve order when two markers arrive in one poll (`recording.py:290-338`). However, both markers still receive the same `capture_seconds`. `_finalize_cadence()` passes those equal values directly to `analyze_pts()` (`recording.py:454-479`), which requires `interval_end > interval_start` (`recording.py:126-130`).

The deterministic replay produced:

```text
marker_order=ordered
times=[0.25, 0.25]
cadence=failed
capture_cadence_failed: ValueError: cadence interval end must follow start
```

The added same-poll regression stops after asserting `_marker_order_status() == "ordered"`; it never finalizes cadence (`tools/kpharness_gamescope_backend_test.py:896-908`). Derive a conservative nonzero interval from the adjacent polling uncertainty bounds, or explicitly declare the interval too short for cadence analysis without claiming this finding closed. Add a regression that calls `_finalize_cadence()` for two ordered markers from one observation.

### R1-2. FFmpeg still opens the progress destination by pathname and can overwrite a raced symlink target

The public master is now staged through an inherited directory descriptor, and stderr is an inherited file descriptor. The progress file differs: the parent exclusively creates it and closes the descriptor, then passes its pathname through `-progress <run_dir>/ffmpeg-progress.log` (`recording.py:753-767`). FFmpeg must reopen that pathname. A concurrent same-UID process can unlink the safe inode and install a symlink before FFmpeg opens it.

The mock Popen callback performed that exact replacement, wrote progress through the command pathname, and changed an external victim from `ORIGINAL` to FFmpeg progress bytes. Startup then failed with `capture_log_read_failed`, but the overwrite had already occurred. The inode checks correctly detected the replacement only after the side effect.

Pass progress through an inherited writable descriptor, such as FFmpeg's `pipe:<fd>` progress target with a dedicated `pass_fds` entry, and read from the retained descriptor or a safely duplicated read endpoint. Path validation after child launch cannot prevent the overwrite.

### R1-3. Diagnostic setup failures occur outside the cleanup guard and make teardown fail with a secondary TypeError

Run-directory and staging descriptors are opened before the `try` that begins at process creation (`recording.py:748-799`). If `ffmpeg.log` or `ffmpeg-progress.log` already exists, exclusive creation raises `FileExistsError` before `started`, `capture`, and diagnostic identities are initialized. Calling `stop()` then reaches diagnostic failure handling, where `_fail()` subtracts `self.started == None` (`recording.py:818-832`). Cleanup aborts before closing descriptors or the partially opened log.

Deterministic results for both collisions were:

```text
start: FileExistsError
stop: TypeError: unsupported operand type(s) for -: 'float' and 'NoneType'
failure receipt: None
run/stage descriptors: still open
```

When the collision was on `ffmpeg-progress.log`, `ffmpeg.log` also remained open. In the real session wrapper, boot does call teardown, but this secondary exception is exactly what prevents teardown from releasing these resources and producing the intended typed capture failure.

Initialize failure-safe state before acquiring resources and wrap all run-directory descriptor, staging-directory, log, and progress acquisition in one exception-safe block. On any failure, close every acquired descriptor, remove the exact owned empty staging directory, write a stable typed failure, and keep `stop()` idempotent for a never-started recorder.

### R1-4. Schema-2 recomputation does not bind the capture output destination or complete command shape

`_root_capture_matches()` validates selected input flags and bans a few timestamp-transforming flags, but it does not validate the output argument or the complete command grammar (`display_backends.py:343-382`). The baseline test fixture contains no output argument at all and passes `execution_evidence_ready()`. Appending `/tmp/evil.mp4`, or changing the last argument and appending an arbitrary output, also passed the authoritative execution gate.

This means a pre-acceptance receipt can claim the safe inherited-FD staging design while serializing a command that wrote elsewhere. Require exactly the expected ordered command, including one output matching a strict `/proc/self/fd/<decimal>/continuous.mp4` form, and reject unknown or extra positional outputs/options. Prefer storing a structured launch contract alongside argv and recomputing argv from it.

### R1-5. Schema-2 recomputation ignores failed route predicates, failed persisted steps, and a failed capture gate

The runner now persists `route.predicates_passed`, `route.steps`, and a separate `capture_gate`, which correctly preserves a successful route result when later capture checking fails (`creative.py:273-296`). The acceptance gate only checks `route.status == "passed"`, report hash presence, and physical-console correlation (`display_backends.py:443-489`). It does not require `predicates_passed is True`, require a nonempty well-formed step list whose statuses passed, or reject `capture_gate.status == "failed"`.

Starting from a receipt accepted by `execution_evidence_ready(require_completion=True)`, all of these independently still returned `True`:

```text
route.predicates_passed=false plus route.steps=[{"status":"failed"}]
capture_gate={"status":"failed","error":"capture_binding_changed"}
```

The current test fixture omits the new route fields entirely and is still treated as complete (`tools/kpharness_gamescope_backend_test.py:63-124`). Bind the persisted report, predicates, and step statuses into authoritative recomputation. Require `capture_gate.status == "passed"` for completed executions while continuing to preserve route status separately for diagnosis.

## Original findings verified closed in round 1

- **Offset PTS arithmetic:** perfect 60 Hz intervals starting at `0.005` and `0.016` both passed. Expected slots now derive from included-frame span.
- **Final marker drain and binding:** the recorder synchronously drains the native log and performs pre- and post-finalization verifier/geometry checks. The focused regression passed.
- **Unkillable recorder retention:** two wait timeouts cause `stop()` to raise, retain the process and staging handles, and record failed cleanup; a later retry can prove death and release resources.
- **Public master symlink protection:** an existing publication symlink is refused before process creation. A symlink inserted after start also remained untouched; hard-link publication failed closed with `capture_output_invalid`.
- **FD staging and hard-link publication:** the success probe published the exact staging inode, left link count one after removing the staging name, and closed/removed the staging resources.
- **Acceptance atomic write:** the former predictable `creative-run.json.tmp` symlink no longer affected the victim. The published receipt was a regular non-symlink file and verified after reopening.
- **Acceptance metadata digest:** independent reviewer, accepted-time, and scope mutations each made `verify_acceptance()` return false.
- **Bounded diagnostic reads:** focused tests rejected truncation, inode replacement, and growth beyond 1 MiB. Unterminated progress remains capped at 64 KiB.
- **Export swap/restore:** the encoder read only the private digest-verified stable copy even while the public master was changed and restored during both mocked encoder calls.
- **Route/capture presentation separation:** an injected late capture failure preserved `route.status == "passed"`, recorded `capture_gate.status == "failed"`, kept overall `ok == false`, and did not invoke derivative rendering. R1-5 concerns authoritative schema enforcement of those separated fields, not this presentation behavior.

## Verification

```text
python3 tools/kpharness_gamescope_backend_test.py
63 tests passed

python3 tools/kpharness_creative_test.py
30 tests passed

7 focused regressions covering bounded diagnostics, final binding, kill survival,
public-master symlinks, export swap/restore, schema arithmetic, and route/capture
separation
7 tests passed

git diff --check [scoped capture/receipt/export/test files]
PASS
```

The suites are mock-only. They do not establish real FFmpeg progress-descriptor compatibility, filesystem crash durability, live Gamescope private-root capture, active MIT-SHM use, GPU cadence, distinct rendered frames, visual framing, or game behavior.

## Round 1 safe-use decision

Do not run or label one animated diagnostic as accepted evidence yet. Fix R1-1 through R1-5, repeat the deterministic probes, and only then perform the separately authorized serialized non-game animated-pattern diagnostic. The first live diagnostic must still treat any `capture_shm_fallback`, progress-channel incompatibility, cadence failure, binding change, cleanup failure, or evidence mismatch as a hard stop.

---

# Fix round 2 adversarial re-review

Reviewed `.superpowers/sdd/lua-boundary-validation-plan/ta[REDACTED].md` and the current isolated-worktree implementation. No worktree file was edited, and no real FFmpeg, ffprobe, Gamescope, Xvfb, Wine, or game process was launched. The execution below was limited to mocks and ad hoc Python.

## Round 2 verdict

Round 2 closes the five round-1 findings in the producer and its ordinary receipt-validation cases. The inherited progress descriptor, guarded partial setup, exact ordered argv shape, route/capture gates, cadence recomputation, timeout handling, hard-link publication, acceptance publication, and stable export copy all survived their deterministic regressions. Three Important schema gaps remain: the validator accepts attacker-selected cadence policy, accepts PTS displaced entirely outside the claimed interval, and accepts one descriptor as both the progress regular file and output directory. These are pre-acceptance receipt mutations that `execution_evidence_ready()` treats as authoritative, so the execution/acceptance digest cannot repair them after acceptance.

**Authorization decision for exactly one animated diagnostic: REFUSED.** Do not launch or label an animated diagnostic through this path until R2-1 through R2-3 are fixed and the deterministic probes pass. The refusal is about the authoritative evidence gate; the producer lifecycle and post-accept exporter otherwise passed the requested mock review.

## Critical

None found.

## Important

### R2-1. The receipt chooses its own cadence policy, allowing severely degraded cadence to pass

`_cadence_evidence_passed()` reads all three thresholds from the untrusted receipt and only checks broad numeric domains (`display_backends.py:273,307-310,372-381`). It never requires the producer's `CadenceThresholds()` policy. A pre-acceptance mutation can therefore weaken the evidence contract and make internally consistent bad cadence authoritative.

The deterministic probe replaced the acceptance interval with 11 frames over one second at a requested 60 FPS, an effective rate of 10 FPS, 83.33% missing slots, and a 100 ms maximum gap. After changing the serialized policy to minimum rate `0.1`, maximum drop `1.0`, and maximum gap `1.0`, `execution_evidence_ready()` returned `True`:

```text
effective_fps=10.0
missing_ratio=0.8333333333333334
maximum_gap_seconds=0.10000000000000009
gate_accepts=True
```

Bind the schema/version to exact policy constants, or derive the thresholds from trusted code and reject any serialized mismatch. Add a regression that rebuilds every derived field around a degraded PTS sequence and confirms that altered thresholds cannot make it ready.

### R2-2. Recomputed PTS are not required to fall inside the claimed marker interval or bind to the media probe

The gate recomputes frame count, span, effective FPS, histogram, percentiles, gaps, and drop arithmetic from `included_pts_seconds` (`display_backends.py:310-370`), but it never requires those PTS to lie within `start_capture_seconds` and `end_capture_seconds`. It also does not bind them to the media digest or a hashed `ffprobe-cadence.json`. Only the interval bounds are compared to marker clocks (`display_backends.py:375-376`).

Starting with a ready fixture for interval `[1.0, 2.0]`, the probe added 100 seconds to every included PTS and to `first_included_pts`/`last_included_pts`. All recomputed spacing metrics remained unchanged, and `execution_evidence_ready()` still returned `True`, even though every asserted frame timestamp was around 101-102 seconds and none belonged to the claimed interval.

The same selector takes the first matching interval and ignores contradictory duplicates (`display_backends.py:303-304`); appending a second failed interval for the same marker pair also passed. Replacing `whole_capture` with fabricated content and zeroing the terminal encoded clock in both copies passed as well. Require exactly one acceptance interval, require each included PTS to be within its serialized interval according to the producer's endpoint rule, and bind the PTS source to the accepted master, such as by hashing a bounded probe artifact into completed execution evidence or rerunning the bounded probe before acceptance.

### R2-3. Command grammar accepts one FD as both the progress file and output directory

The complete argv equality and destination regexes are a substantial improvement, but `_root_capture_matches()` independently validates `/proc/self/fd/<n>` and `/proc/self/fd/<n>/continuous.mp4` without requiring different descriptor numbers (`display_backends.py:407-421`). The probe rewrote the output to `<progress-target>/continuous.mp4`; `execution_evidence_ready()` returned `True`.

One inherited FD cannot simultaneously be the regular progress file created at `recording.py:777-779` and the staging directory opened at `recording.py:770-773`. This receipt therefore describes a launch topology the producer could not have executed. Parse both decimal FD numbers and require them to differ. A stronger structured launch receipt could also record and validate descriptor roles without treating argv strings as the whole descriptor contract.

## Minor

None retained as a standalone finding.

## Closed findings and passing probes

- Same-poll markers at the normal 250 ms observation point finalized with a nonzero conservative interval and passed cadence. An artificial observation exactly at capture origin (`capture_seconds == 0` for both lines) still fails closed because subtracting uncertainty clamps the start to zero; it does not create false-ready evidence.
- Split log/progress input, diagnostic truncation/replacement/oversize input, malformed/regressing progress, and terminal ordering remained fail closed. Progress is a regular inherited descriptor, not a pipe, so no pipe-capacity deadlock was introduced. The raced public progress pathname cannot redirect the child write.
- Existing public output, log, and progress collisions stay inside guarded setup. The progress-collision regression produced `capture_setup_failed`, closed run/stage/progress descriptors, and allowed idempotent `stop()`.
- Pre- and post-finalization binding checks catch geometry/window changes and `subprocess.TimeoutExpired`. A recorder surviving both graceful and post-kill waits raises, retains its process/staging handles, records failed cleanup, and can be retried after death is proven.
- Exact route predicates, nonempty passed steps, and `capture_gate == {"status":"passed"}` are now required by both schema creation and completed execution readiness. Failed route/capture mutations and appended/missing output mutations were rejected.
- Hard-link publication rejects symlink/existing public output replacement and checks the published inode. Acceptance rejects receipt/media symlinks, writes an unpredictable regular temporary file atomically, fsyncs, reopens, and verifies it. Export copies through an `O_NOFOLLOW` source descriptor, verifies the stable-copy digest, and rechecks exact acceptance bytes before and after encoding; the master swap/restore probe only exposed accepted bytes to mocked encoders.
- The legacy creative/Xvfb mock route remains separated from Gamescope capture and continues to defer derivatives after capture failure.

## Verification

```text
PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_backend_test.py
69 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_creative_test.py
30 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_boot_repair_test.py
41 tests passed

Ad hoc authoritative-gate mutations:
baseline=true
pts_displaced_100s_outside_interval=true
policy_thresholds_relaxed=true
same_fd_file_and_directory=true
whole_capture_fabricated=true
duplicate_contradictory_acceptance_interval=true
terminal_encoded_clock_zero=true
```

`git diff --check` passed. The suites are host-only and mocked; they do not establish real inherited-FD behavior in FFmpeg, live Gamescope private-root capture, active MIT-SHM use, GPU cadence, distinct rendered frames, visual quality, or K1 behavior.

---

# Fix round 3 adversarial re-review

Reviewed `.superpowers/sdd/lua-boundary-validation-plan/ta[REDACTED].md` and the current isolated-worktree implementation. No worktree file was edited, and no real FFmpeg, ffprobe, Gamescope, Xvfb, Wine, or game process was launched. All execution was mock-only or pure Python.

## Round 3 verdict

Round 3 closes R2-1 and R2-3 and the simple displaced/duplicate forms of R2-2. Canonical policy constants, exact per-summary arithmetic, PTS-in-interval bounds, duplicate-pair rejection, whole-summary validation, terminal counter types and lower bounds, and distinct structured descriptor roles all fail closed under the previous mutations. Setup, timeout, acceptance, stable-copy export, and legacy-route regressions also pass.

Two Important provenance gaps remain. A different internally perfect PTS history can be substituted for the same unchanged master, accepted, atomically published, and verified. The interval's cumulative FFmpeg boundary samples can also claim zero frames and zero encoded time while the same interval claims 60 encoded frames. An invented marker and extra internally valid interval also pass authoritative readiness; that additional evidence is not used for the acceptance decision, but it confirms that the gate does not reconstruct the producer's expected marker/interval set.

**Authorization decision for exactly one bounded animated diagnostic: REFUSED.** Do not launch the diagnostic through this acceptance path until R3-1 and R3-2 are fixed and their deterministic probes fail closed. The live diagnostic would otherwise be the first observation capable of establishing the very media-to-PTS and progress-to-PTS relationships that the accepted receipt currently does not preserve.

## Critical

None found.

## Important

### R3-1. Canonical PTS arithmetic is still not bound to the unchanged master

`_pts_summary_matches()` recomputes an internally consistent summary (`display_backends.py:33-75`), and `_cadence_evidence_passed()` applies it to whole-capture and named intervals (`display_backends.py:322-387`). Neither function authenticates those PTS against `continuous.mp4`, its digest, or a bounded ffprobe artifact. Acceptance hashes the master bytes, but never reruns or verifies the probe that produced the timestamps.

The deterministic probe kept one unchanged master and replaced both the whole-capture and acceptance histories with a different perfect 60 Hz lattice:

```text
whole PTS:    0.005000 .. 9.988333
interval PTS: 1.005000 .. 1.988333
execution_evidence_ready=True
```

A second probe changed only the acceptance interval to the alternative lattice, wrote that receipt as pending, called `accept()`, and obtained `verify_acceptance=True`. The execution and acceptance digests therefore make the substituted history durable; they do not establish that it came from the accepted master.

Persist a canonical, bounded ffprobe receipt with the master identity and hash it into completed execution evidence, then validate all whole/interval summaries as projections of that one canonical PTS list. Stronger still, acceptance can rerun the bounded frame-PTS probe against the already digest-verified master and compare its canonical output before signing. Add a test showing that two different valid PTS lists cannot both verify for the same media digest.

### R3-2. FFmpeg progress samples can report zero output across an interval that claims 60 frames

The gate requires the left/right samples to surround the interval in capture-wall-clock time and requires nondecreasing counters (`display_backends.py:417-451`). It does not relate either sample's `frame` or `out_time_us` to the included PTS, frame count, or interval encoded-time endpoints. Terminal counters need only exceed the right sample (`display_backends.py:466-475`).

The probe changed both interval samples to `frame=0` and `out_time_us=0`, leaving their capture times at 0.9 and 2.1 seconds and leaving the interval's 61 included PTS/60 inter-frame gaps unchanged. `execution_evidence_ready()` returned `True`. This receipt says FFmpeg had produced no frames or encoded time at the end sample while simultaneously attributing 60 frames to the enclosed interval.

Require progress counters to be compatible with the canonical PTS projection. At minimum, the right sample's frame count must cover the number of whole-capture PTS at or before the interval end and its encoded clock must cover the last included interval PTS within the declared one-frame tolerance; apply corresponding lower/upper constraints to the left sample. A canonical ffprobe receipt from R3-1 provides the shared timeline needed for this check.

## Minor

None retained as a standalone finding.

## Additional adversarial results

- All prior round-2 exploits now fail: relaxed top-level/policy thresholds, a 30 FPS request, PTS shifted outside interval bounds, duplicate marker-pair intervals, partial/fabricated whole summary, zero terminal clock, terminal frame regression, hidden equal nonzero duplicate counters, aliased descriptor roles, standard descriptor roles, and metadata/argv mismatch.
- Adding a fabricated third marker plus a unique, internally valid `complete_to_post` interval still returns ready. This does not change which interval controls acceptance, but the signed receipt can claim extra cadence evidence not reconstructed from a known producer configuration. Serialize the expected marker names and exact expected interval-pair set if every signed interval is intended to be authoritative.
- Setting terminal cumulative `drop_frames` to 999 in both terminal copies still returns ready when the acceptance interval drop delta remains zero. This is consistent with a policy scoped only to the acceptance interval, but the receipt should state that scope plainly; if whole-capture drop-free behavior is intended, enforce the terminal cumulative counter too.
- Same-poll normal finalization, split diagnostics, progress replacement/truncation/growth limits, generic pre-spawn setup failure classification and cleanup, post-kill process retention, final binding timeouts, hard-link publication, atomic acceptance, master swap/restore, and failed route/capture separation remain green.

## Verification

```text
PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_backend_test.py
72 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_creative_test.py
30 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_boot_repair_test.py
41 tests passed

Ad hoc mutation results:
baseline=true
relaxed_top_threshold=false
displaced_pts=false
duplicate_interval=false
aliased_fd_roles=false
alternative_pts_same_master=true
alternative_pts_accepted_and_verified=true
zero_progress_frames_and_clock=true
invented_marker_and_extra_interval=true
999_terminal_drops_outside_interval=true
```

`git diff --check` passed. These results remain host-only and do not prove live inherited-FD operation, Gamescope capture, MIT-SHM use, GPU cadence, distinct frames, visual framing, or K1 behavior.

---

# Fix round 4 adversarial re-review

Reviewed `.superpowers/sdd/lua-boundary-validation-plan/ta[REDACTED].md` and the current isolated-worktree implementation. No worktree file was edited, and no real FFmpeg, ffprobe, Gamescope, Xvfb, Wine, or game process was launched. All execution used mocks or pure Python.

## Round 4 verdict

Round 4 closes the static form of R3-1 and closes R3-2. The canonical artifact is bounded, hashed, opened with `O_NOFOLLOW`, tied to the master digest, projected exactly into whole/named/route intervals, and freshly reprobed before acceptance. Marker configuration, exact interval-pair topology, progress-prefix lower bounds, terminal whole-frame coverage, and explicit policy scope reject the earlier mutations. Direct master/artifact symlinks, alternative PTS without a matching reprobe, extra/missing markers and intervals, route-interval nonsense, counter-prefix insufficiency, terminal drift, and acceptance/export digest drift fail closed in the focused suites.

Three Important reliability/provenance gaps remain. Acceptance hashes and reprobes the master through separate pathname opens, allowing a swap-and-restore to make the fresh probe observe another video. Completed route evidence still accepts a nonexistent report and arbitrary step payload as long as status strings say `ok`. The 16 MiB ffprobe bound is checked only after `subprocess.check_output()` has accumulated all child output in memory.

**Authorization decision for exactly one bounded animated diagnostic: REFUSED.** Do not launch the diagnostic through this acceptance path until R4-1 through R4-3 are fixed and their deterministic regressions pass. The requested diagnostic is specifically intended to establish real media/probe behavior, so accepting a probe of a raced pathname would invalidate its main provenance claim.

## Critical

None found.

## Important

### R4-1. Master swap-and-restore during the mandatory fresh probe can bind another video's PTS to the accepted master

`accept()` first runs execution readiness, separately hashes `media`, and later passes the same pathname to `pts_probe()` (`creative_accept.py:115-142`). It does not retain the exact hashed master descriptor or make a private stable copy for the probe. `verify_acceptance()` hashes the pathname again afterward. A same-UID actor can therefore replace the regular master after the accepted hash, let ffprobe read a different regular video, and restore the original before final verification.

The deterministic callback modeled this ordering. The receipt and canonical artifact contained a coherent alternative 60 Hz PTS history while retaining the original master's SHA-256. During `pts_probe`, the callback replaced `continuous.mp4` with attacker bytes, returned the alternative video's PTS, and restored the original bytes before returning. Results:

```text
alternative_artifact_ready_pre_acceptance=true
master_swap_restore_during_reprobe_accepted=true
master_restored=true
verify_acceptance=true
```

Direct artifact and master symlinks were correctly rejected; this exploit uses regular-file pathname replacement between independent opens. Open the master once with `O_RDONLY|O_NOFOLLOW`, validate and hash that descriptor, copy from that descriptor into a private same-run staging file, and run the fresh probe against the stable copy. Verify the copied digest before signing, as the exporter already does. Retain or revalidate the public master separately if acceptance also promises that its pathname remained unchanged.

### R4-2. Completed execution and acceptance sign nonexistent route reports and arbitrary `ok` step payloads

`execution_evidence_ready()` requires only that `route.report` is a mapping with a truthy `sha256`, and that the route has a nonempty list whose elements are mappings with `status == "ok"` (`display_backends.py:757-768`). It neither opens and hashes the stated report nor validates the step schema or binds the report bytes to the serialized predicates/steps.

The probe replaced the route with:

```json
{
  "steps": [{"status": "ok", "nonsense": {"accepted": true}}],
  "report": {"path": "/definitely/nonexistent/report.json", "sha256": "x"}
}
```

Both `execution_evidence_ready()` and the full `accept()` plus `verify_acceptance()` path returned true. This allows a cadence-correct capture to become an accepted overall execution receipt with fabricated route evidence.

Apply the same bounded regular-file identity pattern to the route report: require a run-local regular non-symlink path, a canonical schema, exact digest, and agreement between report predicates/steps and the serialized route. If the individual step schema varies, at least require the exact canonical report bytes and derive readiness from that parsed report rather than accepting free-form duplicated fields.

### R4-3. The ffprobe output limit is enforced after unbounded subprocess capture

`probe_frame_pts()` calls `subprocess.check_output()` and only then checks `len(raw) > MAX_CANONICAL_PTS_BYTES` (`recording.py:187-198`). `check_output()` accumulates the child's entire stdout before returning. A malformed ffprobe, unexpectedly huge input, or hostile executable can therefore consume arbitrarily large memory despite the advertised 16 MiB evidence limit; the 30-second timeout limits duration but not bytes or memory.

Capture through a pipe that is drained incrementally with a strict byte counter, terminate the exact child when the limit is exceeded, and apply the existing timeout while waiting/reaping. Alternatively direct stdout into an exclusively created bounded staging file while monitoring size, then parse it through the bounded regular-file reader. Add a mock child/output-stream regression that crosses the limit without first constructing the entire oversized value in the parent.

## Minor

None retained as a standalone finding.

## Closed findings and additional probes

- Direct `ffprobe-cadence.json` symlink replacement and direct `continuous.mp4` symlink replacement both made readiness false. Artifact size, schema, digest, frame count, ordered finite numeric PTS, exact path/name, and master digest checks remained fail closed.
- Alternative PTS with a restored original master is rejected in the non-raced acceptance path because the mandatory re-probe disagrees. Artifact/review digest drift is also rejected by acceptance verification and export.
- Missing, extra, duplicated, reordered, or pattern-mismatched configured markers and interval pairs are rejected. Whole, named, acceptance, and route interval PTS must be exact canonical projections.
- Zero/insufficient right progress counters, terminal frame count below canonical whole-frame count, terminal encoded-time regression, nonzero duplicate counters, altered policy scope, and prior descriptor/threshold mutations are rejected.
- Terminal drops outside the acceptance interval remain explicitly permitted by the versioned policy; the prior `999` mutation is no longer an ambiguous unscoped field.
- Hard-link master publication, partial setup cleanup, final geometry checks, unkillable-recorder retention, atomic acceptance publication, stable-copy export, post-accept receipt/master drift checks, and the legacy Xvfb route remain green under mocks.
- Same-digest replacement was not treated as a content-integrity failure because SHA-256 content identity is the stated contract. The inode-sensitive operations still reject symlinks and the exporter verifies the copied bytes before encoding.

## Verification

```text
PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_backend_test.py
74 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_creative_test.py
30 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_boot_repair_test.py
41 tests passed

Ad hoc results:
alternative_artifact_ready_pre_acceptance=true
master_swap_restore_during_reprobe_accepted=true
master_restored=true
route_nonsense_ready=true
route_nonsense_accepted=true
artifact_symlink_ready=false
master_symlink_ready=false
```

`git diff --check` passed. These checks remain host-only and do not prove real FFmpeg/ffprobe descriptor behavior, live Gamescope capture, MIT-SHM use, GPU cadence, distinct frames, visual framing, or K1 behavior.

---

# Fix round 5 adversarial re-review

Reviewed `.superpowers/sdd/lua-boundary-validation-plan/ta[REDACTED].md` and the current isolated-worktree implementation. No worktree file was edited, and no real FFmpeg, ffprobe, Gamescope, Xvfb, Wine, or game process was launched. All probes used mocks or pure Python.

## Round 5 verdict

Round 5 closes the public-path form of R4-1, the missing/fake route-report forms of R4-2, and the unbounded-output allocation in R4-3. The acceptance probe receives a private digest-verified copy, public mutation is bracketed, route report bytes and duplicated steps are hashed and compared, and frame-PTS output is drained incrementally to 16 MiB plus one byte. All 148 focused mocked tests pass, as do every earlier threshold, artifact, marker, interval, counter, descriptor, setup, acceptance, and export mutation.

Three Important gaps remain. The private stable-copy bracket omits `ctime`, so a same-UID probe-side writer can alter and restore the stable file's bytes and `mtime` without detection. The route report validator accepts arbitrary `execution` payloads despite claiming a canonical ScenarioRunner report. The streaming probe falls back to an unbounded `wait()` if the child survives its first bounded post-kill wait.

**Authorization decision for exactly one bounded animated diagnostic: REFUSED.** Fix R5-1 through R5-3 and rerun their deterministic regressions before starting the diagnostic. R5-1 directly affects whether the fresh live probe observes the stable accepted master, and R5-3 can hang the harness during the diagnostic's required bounded probe.

## Critical

None found.

## Important

### R5-1. The private acceptance copy can be modified and restored without changing the checked identity tuple

`_stable_regular_copy()` and `_regular_identity_and_sha()` define identity as `(st_dev, st_ino, st_size, st_mtime_ns)` (`creative_accept.py:82-130`). After the fresh probe, acceptance compares that identity and the restored SHA-256 (`creative_accept.py:191-199`). It omits `st_ctime_ns` and link count. The stable copy is a normal same-UID-owned regular file in a discoverable temporary path passed to the probe.

The deterministic probe installed a coherent alternative PTS artifact, then used the probe callback to modify the private `accepted-master.mp4`, restore its original bytes, and reset `mtime` to the saved nanosecond value before returning the alternative PTS. The source inode, size, `mtime`, and digest all matched after restoration, so `accept()` succeeded and `verify_acceptance()` returned true:

```text
alternative_pts_execution_ready=true
stable_mutate_restore_accepted=true
```

Include `st_ctime_ns` and `st_nlink` in both source and stable identities and require the stable copy to retain one link. `ctime` cannot be reset by an unprivileged file owner after a write or metadata change. Also bind the probe executable to a trusted configured identity rather than accepting any nonempty executable string from the artifact; otherwise a substituted executable can simply emit the artifact's chosen PTS. A sealed memfd or an unlinked read-only inherited descriptor would further reduce same-UID pathname exposure.

### R5-2. The route report's `execution` object remains an unrestricted authoritative field

`_route_report_matches()` enforces exact top-level keys and a detailed step schema, but checks `execution` only with `isinstance(report['execution'], dict)` (`display_backends.py:807-838`). A probe replaced it with `{"nonsense":{"accepted":true}}`, rewrote the canonical report, and refreshed the report digest in the receipt. `execution_evidence_ready()` still returned true.

The actual ScenarioRunner populates a small known execution vocabulary, including game-speed request/effective/restoration fields. Validate the allowed keys and their types/ranges, or define this field as explicitly non-authoritative and remove it from the accepted route proof. Add regressions for unknown keys, booleans as numeric values, nonfinite values, and contradictory speed fields.

### R5-3. FFprobe cleanup uses an unbounded second wait after the bounded reap attempt times out

On a probe error or timeout, `probe_frame_pts()` kills the child and calls `wait(timeout=2)`. If that times out, it kills again and calls `process.wait()` with no timeout (`recording.py:224-230`). The missing-stdout branch also calls an unbounded `wait()` after kill (`recording.py:195-198`). A child stuck in uninterruptible kernel I/O can therefore hang acceptance indefinitely despite the advertised 30-second probe and two-second cleanup bounds.

The mock timeout probe recorded:

```text
kill calls: 2
wait arguments: [2, None]
```

Keep every reap attempt bounded. If the second bounded wait also expires, retain the exact process handle/identity, raise a typed cleanup failure, and prevent acceptance while allowing a later owner-controlled reap attempt. Apply the same bounded logic to the missing-stdout branch.

## Minor

None retained as a standalone finding.

## Closed findings and additional probes

- The prior public-master swap-and-restore callback now receives a private path and acceptance rejects the changed public identity. Export uses the same stable-copy helper and continues to encode only the verified copy.
- Missing route report, wrong digest, report symlink, oversized or malformed report, unsupported step fields, failed report, and disagreement between report steps and duplicated receipt steps fail readiness.
- FFprobe stdout is incrementally read with nonblocking 64 KiB reads, caps the parent buffer at 16 MiB plus one byte, and kills/reaps the ordinary oversized mocked child.
- Direct master/artifact symlinks, alternative PTS without a matching fresh probe, marker/interval changes, route-interval changes, counter-prefix contradictions, terminal drift, threshold/policy changes, and descriptor aliasing remain rejected.
- Acceptance publication and export provenance checks remain atomic/fail closed under their existing mocked swaps. Same-digest replacement remains acceptable under the stated content-identity contract.

## Verification

```text
PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_backend_test.py
77 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_creative_test.py
30 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_boot_repair_test.py
41 tests passed

Ad hoc results:
alternative_pts_execution_ready=true
stable_mutate_restore_accepted=true
route_execution_nonsense_ready=true
probe_timeout_exception=TimeoutExpired
probe_cleanup_kills=2
probe_cleanup_wait_arguments=[2, null]
```

`git diff --check` passed. These checks remain host-only and do not prove real FFmpeg/ffprobe behavior, live Gamescope capture, MIT-SHM use, GPU cadence, distinct rendered frames, visual framing, or K1 behavior.

---

# Fix round 6 adversarial re-review

Reviewed `.superpowers/sdd/lua-boundary-validation-plan/ta[REDACTED].md` and the current isolated-worktree implementation. No worktree file was edited, and no real FFmpeg, ffprobe, Gamescope, Xvfb, Wine, or game process was launched. All execution was mocked or pure Python.

## Round 6 verdict

Round 6 closes the direct private-copy mutation in R5-1, validates the route execution vocabulary from R5-2, and bounds both cleanup waits from R5-3. Acceptance now probes an unlinked zero-link master descriptor inherited through `pass_fds`; stable/public identities include `ctime` and link count; the configured probe tool is resolved, hashed, and bound into the canonical artifact; route source, report, K1 runtime, scenario/build/steps, and speed metadata are internally cross-checked; and an unkillable probe raises a typed error after two bounded waits.

Two Important provenance gaps remain. The verified probe executable is hashed and then later executed by pathname, so a replace-for-exec/restore race can run another program while all pre/post digest checks see the trusted bytes. The route binding has no acceptance-time anchor outside the mutable run evidence: replacing the route copy, report, duplicated steps, and their identities coherently with another valid K1 route still produces an accepted verified receipt.

**Authorization decision for exactly one bounded animated diagnostic: REFUSED.** Fix R6-1 and R6-2 and rerun their deterministic probes before starting the diagnostic. R6-1 can make the required live PTS re-probe execute unverified code and certify chosen timestamps; R6-2 can make the final accepted receipt describe a different route from the route selected at launch.

## Critical

None found.

## Important

### R6-1. The hashed FFprobe tool is still executed through a replaceable pathname

`_probe_tool_matches()` opens and hashes `resolved_path`, then closes the descriptor (`display_backends.py:47-68`). Acceptance later calls `pts_probe(..., tool['resolved_path'], ...)`, and `probe_frame_pts()` passes that pathname to `Popen` (`creative_accept.py:225-230`; `recording.py:218-228`). No retained executable descriptor or pre/post path identity brackets the actual exec.

The deterministic probe used a run-local executable identity and a coherent alternative PTS artifact. Readiness verified the original tool bytes. Inside the probe callback, the tool pathname was replaced with malicious bytes for the simulated invocation, restored before returning, and the alternative PTS were returned. Final readiness saw the restored trusted digest. Results:

```text
tool_race_alternative_ready=true
tool_race_observed_malicious_bytes=true
tool_replace_restore_accepted=true
verify_acceptance=true
```

Open and hash the executable once, retain its descriptor, and execute the retained identity rather than reopening the pathname. On Linux, use a supported descriptor-exec mechanism or a carefully validated `/proc/self/fd/<n>` execution path with the descriptor inherited and kept open through exec; test ELF and script behavior explicitly. If descriptor execution is unavailable, bracket the invocation with full device/inode/size/mtime/ctime/link/digest checks and recognize that rename-away/restore of the original inode can still evade a pathname-only bracket.

### R6-2. A coherent route-source plus report substitution is accepted because no out-of-run launch anchor is checked

`_route_report_matches()` rigorously checks that the current `executed-route.toml`, `report.json`, receipt steps, execution identity, runtime hashes, and scenario-derived descriptions agree (`display_backends.py:805-950`). All of those authorities live in the mutable run evidence and can be replaced together before acceptance. The validator does not compare the copied route against an independently supplied launch-time route digest or a protected manifest outside that mutable set.

The probe replaced the copied route with a different valid K1 scenario named `substituted`, changed its step to `do unrelated`, rewrote the report to the same scenario/step, and refreshed route-source identity/digest, report digest, duplicated steps, and execution identity. Runtime/build/media were left unchanged. Results:

```text
coherent_route_substitution_ready=true
coherent_route_substitution_accepted=true
verify_acceptance=true
```

Bind acceptance to an independent expected route digest supplied by the reviewer/operator, analogous to `--media-sha256`, or to a launch manifest whose identity is established outside the mutable run directory before execution. Require the selected source route digest, copied route digest, execution identity, and report to match that anchor. Add a regression that substitutes a fully valid route and updates every run-local dependent field coherently.

## Minor

None retained as a standalone finding.

## Closed findings and additional probes

- The inherited master descriptor is read-only, has zero links during probing, is passed explicitly through `pass_fds`, and is rehashed/re-fstat'ed afterward. Private bytes changed and restored through the descriptor change `ctime` and are rejected.
- Artifact-only tool replacement, wrong resolved path, wrong tool digest, symlink tool, and nonregular tool fail readiness. R6-1 is the time gap between successful validation and pathname exec.
- Wrong K2 target, wrong scenario/build, report-only step replacement, unknown speed fields, booleans/nonfinite speeds, inconsistent effective/retained speeds, wrong runtime sets/hashes, source/report symlinks, identity drift, and report mismatch fail readiness.
- FFprobe output retains at most 16 MiB plus one byte. Both kill/reap attempts use two-second timeouts; a surviving child raises `ProbeCleanupError` and exposes the exact child object through the error.
- All earlier artifact, PTS projection, marker/interval topology, route interval, counter-prefix, terminal, policy, descriptor-role, setup/cleanup, acceptance publication, and export stable-copy mutations remain rejected.
- Acceptance currently wraps `ProbeCleanupError` as a `ValueError` with the original error as `__cause__`. Library callers can recover the process through the cause; the CLI does not persist a durable cleanup receipt or retry handle if it exits. This remains an operational limitation for an actually unkillable probe.

## Verification

```text
PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_backend_test.py
81 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_creative_test.py
30 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_boot_repair_test.py
41 tests passed

Ad hoc results:
tool_race_alternative_ready=true
tool_race_observed_malicious_bytes=true
tool_replace_restore_accepted=true
coherent_route_substitution_ready=true
coherent_route_substitution_accepted=true
```

`git diff --check` passed. These checks remain host-only and do not prove real FFmpeg/ffprobe descriptor execution, live Gamescope capture, MIT-SHM use, GPU cadence, distinct rendered frames, visual framing, or K1 behavior.

---

# Fix round 7 adversarial re-review

Reviewed `.superpowers/sdd/lua-boundary-validation-plan/ta[REDACTED].md` and the current isolated-worktree implementation. No worktree file was edited, and no real FFmpeg, ffprobe, Gamescope, Xvfb, Wine, or game process was launched. All execution was mocked or pure Python.

## Round 7 verdict

Round 7 closes the pathname-execution race in R6-1, adds an independent caller-supplied route commitment that closes R6-2, binds reported speed to the parsed route, and persists a typed receipt for the already modeled unkillable-child case. The acceptance probe now executes the retained native ELF descriptor, keeps the media and tool descriptors distinct and inherited, verifies both afterward, and closes them on every ordinary return or exception. The external route digest is required again by verification and export. All 158 focused tests pass, and the prior cadence, route, media, acceptance, and export mutation suites remain green.

Two Important gaps remain. First, the identity of the supposedly trusted probe executable is still selected wholly by mutable run evidence. A coherent replacement of the tool identity, canonical PTS artifact, and derived cadence summaries is internally ready and accepted when a different native ELF emits the substituted PTS. Retaining the descriptor proves which recorded bytes ran, but nothing outside the run proves those bytes are FFprobe. Second, `_bounded_probe_cleanup()` calls `kill()` outside its bounded-wait handling. If the child exits between `poll()` and `kill()`, `ProcessLookupError` escapes before `wait()`, so the child is not explicitly reaped and acceptance emits no durable cleanup-failure receipt.

**Authorization decision for exactly one bounded animated diagnostic: REFUSED.** Fix R7-1 and R7-2 and rerun their deterministic regressions before starting the diagnostic. R7-1 permits a coherently substituted executable to certify chosen frame timestamps, and R7-2 leaves a concrete exit race outside the claimed bounded cleanup and durable failure-evidence path.

## Critical

None found.

## Important

### R7-1. The retained executable descriptor has no independent trusted-tool commitment

`execution_evidence_ready()` validates `cadence.probe_tool` only against the executable path and the probe object embedded in the mutable canonical PTS artifact (`display_backends.py:47-98`). Acceptance then opens and hashes the `resolved_path` and compares it to that receipt-controlled digest (`creative_accept.py:189-203,253-265`). The new descriptor execution prevents a pathname swap after validation, but it does not establish that the selected ELF is the operator-configured FFprobe or any independently approved binary.

The deterministic probe copied another native ELF into the run directory, replaced both `cadence.probe_tool` and the artifact's probe identity with that ELF and its digest, installed an alternative valid PTS history, and recomputed the whole and acceptance-interval cadence projections. Its injected callback read the retained tool FD and returned the alternative PTS. Results:

```text
coherent_tool_substitution_ready=true
coherent_tool_substitution_accepted=true
substituted_tool_seen=true
```

Require an expected FFprobe digest or protected launch commitment as an explicit acceptance input, parallel to `--route-sha256` and `--media-sha256`. Compare it to the retained tool descriptor digest before execution, sign it into `visual_review`, and require it again for `verify_acceptance()` and export admission. A fixed policy may instead commit an approved absolute path plus digest outside the run, but the receipt and its PTS sidecar cannot be the sole authority. Add a regression that coherently changes the native tool, PTS artifact, and every cadence projection while preserving the original external tool digest.

### R7-2. A child exit between `poll()` and `kill()` bypasses bounded wait, reaping, and cleanup evidence

`probe_frame_pts()` calls `_bounded_probe_cleanup()` after observing a live process (`recording.py:237-240,267-270`). `_bounded_probe_cleanup()` immediately calls `process.kill()` before entering either bounded `wait()` (`recording.py:203-211`). Process exit is asynchronous: if the child exits after the caller's `poll()` but before `kill()`, real `Popen.kill()` can raise `ProcessLookupError`. That error propagates without calling `wait()`. Acceptance catches it only as a generic `OSError` (`creative_accept.py:274-278`), so `_persist_probe_cleanup_failure()` is not called either.

The deterministic exit-race mock returned live from `poll()`, raised `ProcessLookupError` from `kill()`, and would have returned successfully from `wait(timeout=2)`. Results:

```text
cleanup_exit_race_exception=ProcessLookupError
cleanup_exit_race_waits=[]
```

Treat `ProcessLookupError` from `kill()` as a signal to continue directly to a bounded `wait()`. Structure cleanup so every observed or suspected exit gets a bounded reap attempt. If signaling or both waits fail, raise `ProbeCleanupError` with the retained process identity so acceptance persists the durable failure receipt. Add races for the initial kill and the repeat kill after the first wait timeout.

## Minor

None retained as a standalone finding.

## Closed findings and additional probes

- Replace-for-exec/restore now exposes the original retained ELF bytes to the probe callback. Media and tool descriptors are distinct, passed together through `pass_fds`, revalidated after the probe, closed afterward, and a public executable path identity change fails acceptance.
- A fully coherent run-local route/report/step/execution substitution remains internally consistent but fails acceptance when the caller supplies the retained original route digest. Wrong route digests also fail later acceptance verification and export admission.
- Requested/effective speed must match the parsed route setting; booleans, nonfinite values, unknown keys, contradictory values, and out-of-range values fail closed.
- Direct stable-descriptor mutation, public master or tool path replacement, artifact/master/report/route symlinks, alternative PTS without a matching fresh probe, marker/interval topology changes, counter-prefix contradictions, terminal drift, policy/threshold mutations, and route/capture separation mutations remain rejected by the focused suite.
- The modeled child that survives two successful `kill()` calls and two bounded waits produces `ffprobe-cleanup-failure.json` with PID/start identity. R7-2 is the earlier signaling race that does not enter that typed path.
- Accepted-receipt and master changes remain bracketed during export, and the independently supplied route digest is recorded in the derivative sidecar.

## Verification

```text
PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_backend_test.py
87 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_creative_test.py
30 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_boot_repair_test.py
41 tests passed

Ad hoc results:
coherent_tool_substitution_ready=true
coherent_tool_substitution_accepted=true
substituted_tool_seen=true
cleanup_exit_race_exception=ProcessLookupError
cleanup_exit_race_waits=[]
```

`git diff --check` passed. These checks remain host-only and do not prove real FFprobe descriptor execution through `/proc/self/fd`, real process-exit timing, live Gamescope capture, MIT-SHM use, GPU cadence, distinct rendered frames, visual framing, or K1 behavior.

---

# Fix round 8 adversarial re-review

Reviewed `.superpowers/sdd/lua-boundary-validation-plan/ta[REDACTED].md` and the current isolated-worktree implementation. No worktree file was edited, and no real FFmpeg, ffprobe, Gamescope, Xvfb, Wine, game, or recovery process was launched. All process and filesystem behavior used mocks or pure Python.

## Round 8 verdict

Round 8 closes R7-1 by requiring an independently supplied FFprobe digest throughout acceptance, verification, accepted-receipt loading, export, and the derivative sidecar. It also closes the direct R7-2 `ProcessLookupError` path: every modeled signal outcome now reaches a bounded wait, and an unreaped child produces a distinct failure record rather than overwriting an earlier record. All 166 focused tests pass, along with the prior cadence, media, route, tool-descriptor, acceptance, and export mutations.

Three Important cleanup-lifecycle gaps remain. The cleanup files are exclusive only at creation; they are not durably append-only or anchored elsewhere, so deleting a failure or coherently replacing it with a forged failure/resolution pair makes the gate clear. Recovery checks `/proc/<pid>/stat` and then signals the numeric PID, leaving a PID-reuse window in which SIGKILL can target an unrelated process; it also treats every unreadable or malformed `/proc` read as proof that the process exited. Finally, a signaling error followed by a successful bounded reap raises `ProbeCleanupError` only after the process is gone, so start identity can be empty and the code writes a failure record that its own parser rejects and cannot recover.

**Authorization decision for exactly one bounded animated diagnostic: REFUSED.** Fix R8-1 through R8-3 and rerun their deterministic regressions before starting the diagnostic. R8-1 permits retry acceptance and export after unresolved cleanup evidence is removed or rewritten, R8-2 can signal an unrelated reused PID, and R8-3 can leave the diagnostic permanently blocked by a schema-invalid record emitted by the harness itself.

## Critical

None found.

## Important

### R8-1. Cleanup failure and resolution files are mutable and have no durable completeness anchor

`_exclusive_regular_write()` uses `O_EXCL`, but after close the owner can truncate, replace, rename, or delete the file (`creative_accept.py:88-99`). `cleanup_state_clear()` discovers current records only by globbing the run directory (`creative_accept.py:128-145`). It has no independently committed set of failure IDs or immutable ledger head, and `_cleanup_record()` accepts additional/missing nonidentity evidence without a record digest (`creative_accept.py:102-125`). Therefore absence is interpreted as a clear ledger, and a matching forged failure/resolution pair is interpreted as resolved.

The deterministic probes created a valid unresolved failure, then separately deleted it and replaced it with a syntactically valid pair for a different identity:

```text
legitimate_failure_clear=false
deleted_failure_clear=true
replaced_failure_pair_clear=true
```

Because `accept()`, `verify_acceptance()`, and export rely on `cleanup_state_clear()`, either mutation permits retry acceptance or export without resolving the original retained child.

Commit each failure ID and the exact failure-record digest into an authority that cannot be restored from pre-failure run evidence. A small append-only ledger needs a hash chain whose current head is durably committed outside the mutable run directory, or an owner-held state database/file descriptor with replacement protection. Bind each resolution to the exact failure digest, validate exact record keys and values, and treat a missing previously committed record as corruption. Add delete, rename, truncate, same-name replacement, forged pair, and multiple-record regressions across acceptance and export.

### R8-2. Recovery has a numeric-PID check-to-signal race and conflates unreadable identity with exit

`recover_cleanup()` reads the PID start identity, compares it once, and then calls `os.kill(pid, SIGKILL)` on the numeric PID (`creative_accept.py:298-310`). If the original process exits and the PID is reused after the check but before the signal, SIGKILL can target the new unrelated process. The later identity poll cannot undo that signal. Separately, `session.pid_start()` returns the same empty string for `FileNotFoundError`, permission errors, malformed/truncated stat data, and decode/index errors (`session.py:97-107`). Recovery treats that empty value as `already_exited` before signaling and as successful disappearance after signaling (`creative_accept.py:299-318`).

The PID-reuse mock returned the expected identity for the check, changed to a reused identity at the next observation, and recorded that a signal was still sent. A separate unreadable-identity mock returned the same empty sentinel used for a missing PID:

```text
pid_reuse_race_signal_count=1
pid_reuse_race_resolution=identity_gone_after_signal
unreadable_pid_resolved=already_exited
unreadable_pid_signal_count=0
```

Open a Linux pidfd for the target before authorizing recovery, verify the start identity while holding that process reference, signal through the pidfd, and poll/wait the pidfd with the existing bound. If pidfds are unavailable, refuse automated signaling rather than claiming race-free identity. Change the identity reader to return distinct `present`, `gone`, and `unreadable/malformed` states; only `ENOENT`/confirmed absence may resolve as exited. Permission, I/O, parse, and short-read failures must remain unresolved. Test exit/reuse immediately before signaling and transient read failure both before and after signaling.

### R8-3. A signaling error followed by successful reap can emit an unrecoverable malformed failure record

When any `kill()` raises a non-`ProcessLookupError`, `_bounded_probe_cleanup()` records the signal error, performs a bounded `wait()`, and raises `ProbeCleanupError` even when that wait successfully reaps the child (`recording.py:202-222`). `ProbeCleanupError` obtains `pid_start` only when it is constructed, after the reap (`recording.py:188-199`). A real `Popen` has no stored `pid_start`, and `/proc/<pid>/stat` is then gone, so `pid_start` can be empty. `_persist_probe_cleanup_failure()` writes the empty identity without validating it (`creative_accept.py:274-282`), while `_cleanup_record()` requires a nonempty identity (`creative_accept.py:121-124`). The harness therefore creates a record that blocks `cleanup_state_clear()` but cannot be read by `recover_cleanup()`.

The deterministic signaling-error/reap probe produced:

```text
reaped_signal_error_pid_start=''
malformed_emitted_record_count=1
malformed_emitted_ledger_clear=false
malformed_emitted_recovery=ValueError:malformed FFprobe cleanup failure
```

Capture and retain the child start identity immediately after `Popen`, before cleanup can signal or reap it. Validate the complete failure payload before exclusive publication. If bounded `wait()` successfully reaps the child, treat ownership cleanup as complete and propagate the original probe failure without creating an unresolved-child record; signal diagnostics may be recorded separately as already resolved. Add a real-`Popen`-shaped mock with no synthetic `pid_start`, a signal error, and successful bounded wait, then assert that retry acceptance is not permanently blocked.

## Minor

None retained as a standalone finding.

## Closed findings and additional probes

- The independently supplied FFprobe digest must match both the producer tool identity and the retained ELF descriptor. Wrong digests fail acceptance verification and export admission, and the digest is included in `visual_review` and the export sidecar.
- Tool pathname replacement after descriptor retention, media descriptor mutation, public master replacement, route substitution under the retained route digest, route speed contradictions, and all prior PTS/cadence/marker/interval/counter/policy mutations remain rejected.
- `ProcessLookupError` from the initial cleanup signal now proceeds to `wait(timeout=2)`. Two timed-out waits remain bounded, and ordinary surviving-child failures generate distinct randomly named records.
- Symlinked, malformed, truncated, misnamed, and orphaned records fail closed while present. Multiple legitimate unresolved records also block. R8-1 is the missing immutable completeness/identity anchor across deletion and coherent replacement.
- Existing accepted receipts and export calls fail while a currently visible unresolved record is present. R8-1 permits the record itself to be removed or replaced before those gates run.
- The `rindex(')')` stat parser handles process names containing spaces and embedded right parentheses. R8-2 concerns the state ambiguity and the unavoidable gap between pathname identity read and numeric-PID signal.

## Verification

```text
PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_backend_test.py
95 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_creative_test.py
30 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_boot_repair_test.py
41 tests passed

Ad hoc results:
legitimate_failure_clear=false
deleted_failure_clear=true
replaced_failure_pair_clear=true
pid_reuse_race_signal_count=1
pid_reuse_race_resolution=identity_gone_after_signal
unreadable_pid_resolved=already_exited
unreadable_pid_signal_count=0
reaped_signal_error_pid_start=''
malformed_emitted_record_count=1
malformed_emitted_ledger_clear=false
malformed_emitted_recovery=ValueError:malformed FFprobe cleanup failure
```

`git diff --check` passed. These checks remain host-only and do not prove pidfd recovery, real FFprobe descriptor execution, live Gamescope capture, MIT-SHM use, GPU cadence, distinct rendered frames, visual framing, or K1 behavior.

---

# Fix round 9 adversarial re-review

Reviewed `.superpowers/sdd/lua-boundary-validation-plan/ta[REDACTED].md` and the current isolated-worktree implementation. No worktree file was edited, and no real FFmpeg, ffprobe, Gamescope, Xvfb, Wine, game, or recovery process was launched. Probes live in `/home/brunner56/kp-live-20260922/review-probes-r9-adversarial/` and use mocks or pure Python only.

## Round 9 verdict

Round 9 closes the code-level parts of R8-2 and R8-3 and most of R8-1. The ledger is one canonical hash-chained file with exact record key sets, sequence and previous-digest checks, and failure/resolution binding by digest, PID and start. Recovery reads identity in three states, holds a pidfd, rechecks start while holding it, signals only through the pidfd, and polls with a two-second bound. Start identity is captured right after `Popen`. A signal error followed by a successful reap now writes a failure plus a bound resolution.

One Important gap remains. The "external" head has no source outside the run. When acceptance appends a failure, the new head and the failure ID are never shown or stored anywhere else. The CLI ends with a `ValueError` whose text has neither value. The docs tell the reviewer to pass the "SHA256 of the cleanup ledger at review", which is read from the same mutable file. The launch head is the same constant for every run. So the R8-1 deletion and forged-pair attacks still work end to end under the documented procedure.

**Authorization decision for exactly one bounded animated diagnostic: REFUSED.** Fix R9-1 and rerun its probe first.

## Critical

None found.

## Important

### R9-1. The post-failure ledger head and failure ID never leave the run directory, so the reviewer can only re-derive the head from the mutable file

`accept()` handles `ProbeCleanupError` by calling `_persist_probe_cleanup_failure()` and, when reaped, `_append_cleanup_record()`. It then raises `ValueError(f'canonical PTS re-probe cleanup failed: {error}')` (`creative_accept.py:549-556`). The new head returned by `_append_cleanup_record()` (`creative_accept.py:218-232`) is discarded. The failure record ID is not in the message either. `main()` does not catch the error (`creative_accept.py:608-610`), so nothing prints the head. The only head the harness hands out before a failure is the empty-ledger digest from `initialize_cleanup_ledger()` (`creative_accept.py:196-200`). `creative.py:201-202` drops that value, and it equals `sha256(b'{"records":[],"schema":1}\n')` for every run. The docs tell the reviewer to pass `SHA256_OF_FFPROBE_CLEANUP_LEDGER_AT_REVIEW` (`docs/creative-runner.md:78`). To find `FAILURE_ID` and the current head, the reviewer has to read the ledger (`docs/creative-runner.md:100-105`). Every regression test also derives the head with `A.cleanup_ledger_sha256(run)` from the run directory (`tools/kpharness_gamescope_backend_test.py:41,1055,1081,1108,1130,...`).

The hash chain is only as strong as the anchor, and the anchor here is the file itself. In `p1_head_external.py`, a retained child is recorded through the real CLI path. Two attacks follow. The first resets the ledger to the launch bytes. The second writes a new, internally valid failure-plus-resolution pair for a different PID. Each time the reviewer computes the head "at review" as documented:

```text
launch_head_is_universal_constant=True
failure_exception='ValueError: canonical PTS re-probe cleanup failed: ffprobe child survived two bounded kill/reap attempts'
post_failure_head_emitted_out_of_band=False
failure_id_emitted_out_of_band=False
reset_to_empty_accepted=True
reset_verify=True export_head=True
forged_pair_accepted=True verify=True
```

At the code level, the chain rejects deletion when the reviewer already holds the real post-failure head (`r8_deleted_clear_with_retained_head=False` in `p2_ledger_pidfd.py`). But no supported workflow gives the reviewer that head.

Fix: whenever the ledger changes (launch, failure append, reaped-failure resolution, recovery), give the new head and the failure ID to the operator outside the run directory. Printing both to stderr/stdout before the non-zero exit is the minimum. Better: append them to an operator-owned file outside the run directory. Change the docs so the acceptance, recovery and export head is always the last head the harness printed, and is never recomputed from the file. Add a regression that parses the CLI output of a failed acceptance, then resets or forges the ledger, then shows that acceptance with the printed head fails.

## Minor

### R9-2. The "exact schema" still accepts bool and float stand-ins

`_validate_cleanup_record()` and `_load_cleanup_ledger()` use `==`/`!=` for `schema`, `sequence`, and `bounded_wait_seconds` (`creative_accept.py:135-138,151,186-187`). They accept `true` or `1.0` for schema, `true` for sequence 1, and `[2.0, 2.0]` for the waits. They also accept duplicate JSON keys, non-canonical whitespace, and `Z` timestamps. Timestamps are not checked for order, so a resolution may carry a time before its failure. Probe results: `schema_bool=loads schema_float=loads seq_bool=loads rec_schema_float=loads waits_float=loads dup_keys=loads noncanonical_ws=loads resolution_timestamp_before_failure=loads`. With a truly external head these add no forgery power, because the head binds the raw bytes. Use `type(x) is int` checks, and require `raw == canonical encoding` if exactness is claimed.

### R9-3. Different start at the recorded PID refuses forever, although it proves the original is gone

A PID cannot be reused while its original holder exists, even as a zombie. `present` with a different start therefore confirms absence of the recorded child. `recover_cleanup()` raises `cleanup PID identity changed; refusing reused process` (`creative_accept.py:426-427`) and never resolves. The run stays blocked until the unrelated reusing process exits (`reused_pid_long_lived=ValueError`). This fails closed and only affects liveness. Refusing to signal is right, but it could record a resolution as `already_exited` with `wait: 'start_mismatch'`.

### R9-4. Stale recovery docs contradict the new CLI

`docs/creative-runner.md:407-420` still describes a separate `ffprobe-cleanup-failure-ID.json` file. It also shows `--recover-cleanup FAILURE_ID` without `--cleanup-ledger-sha256`, which `main()` now rejects (`creative_accept.py:598-599`).

### R9-5. Two backend tests depend on a real `ffprobe` on PATH

`probe_tool_identity()` calls the real `shutil.which()` (`recording.py:232-241`). `test_marker_bounded_cadence_recomputes_terminal_duplication` and `test_same_poll_markers_keep_byte_order_without_claiming_reverse_time` fail in a container without ffprobe (`configured ffprobe executable was not found`) and pass on the host, where `/home/linuxbrew/.linuxbrew/bin/ffprobe` exists. They fail rather than pass falsely, so no false green is possible. This only affects hermeticity: patch `probe_tool_identity` or `shutil.which` in those two tests.

### R9-6. Ledger append is an unlocked read-modify-replace

`_append_cleanup_record()` loads, appends, and `os.replace`s without a lock or compare-and-swap on the prior head (`creative_accept.py:218-232`). If two acceptances or recoveries on one run write at the same time, one record is silently lost. The failure path in `accept()` also appends without checking that the ledger still matches the head supplied at entry, so a change made during the probe gets extended. This is low likelihood and part of the anchor problem in R9-1.

## Closed findings and additional probes

- R8-1 (code level): with a retained true head, deletion, truncation, reorder, altered payload/digest, extra members, hard link (`hardlink=ValueError`), sequence gap, resolution before failure, and two resolutions for one failure all fail closed. A second append after acceptance makes every later verify/export fail closed, because the signed head no longer matches. It never passes. The remaining problem is the anchor's provenance (R9-1).
- R8-2: reuse detected before or while holding the pidfd refuses with zero signals (`reuse_before_pidfd` sent 0 signals). `unreadable` never resolves. `pidfd_open` raising ENOSYS/EPERM propagates as `OSError`/`PermissionError` with the ledger unchanged. Missing `os.pidfd_open`/`signal.pidfd_send_signal` refuses. The pidfd is closed on wait-raise, signal-error-then-survive, and reader-raise paths. The poll bound is `int(2.0*1000)` ms. For a zombie, the pidfd reads as readable, so a dead-but-unreaped target resolves as `pidfd_reaped`. The label is loose, but "exited" holds.
- `/proc/<pid>/stat` parsing with `)` and spaces in comm picks field 22 (`stat_paren_comm start='22'`) and matches `session.pid_start()` for self. A non-ASCII comm is `unreadable` and fails closed.
- R8-3: a real-`Popen`-shaped child with a signal error and a successful bounded wait keeps a nonempty captured start (`(True, True, [2])`). Acceptance writes a failure plus a bound resolution, so it is not permanently blocked.
- R7-2: `ProcessLookupError` from `kill()` still proceeds to `wait(timeout=2)` (`r7_2_exit_race=('OSError', [2])`).
- R7-1, R6-1, R6-2 and earlier rounds: covered by passing host regressions: `test_external_ffprobe_digest_rejects_coherent_run_local_tool_substitution`, `test_acceptance_executes_retained_native_tool_fd_during_path_swap_restore`, `test_external_route_digest_rejects_coherent_run_local_route_substitution`, `test_verify_and_export_require_independent_configured_ffprobe_digest`, and the pre-existing PTS/marker/interval/counter/policy/export mutation tests (all green). Rounds 0–5 were not re-scripted separately this round. Their regressions are in the same passing suite.
- Repeated recovery: with a stale head it raises. With the new head it returns the exact bound resolution.
- Symlink swap between check and read (reasoned, not probed): a symlink put in place hits `O_NOFOLLOW` in `_read_regular()` (`creative_accept.py:57`), which raises and fails closed. The suite already covers symlink substitution. A regular-file swap-and-restore between the first `lstat` and the `open` is not detected, because `_read_regular()` never compares its `fstat` result to the earlier `lstat` (`creative_accept.py:178-184`). The raw-byte head still has to match, so this adds no power while the head is truly external. It falls under R9-1.
- Rounds 0–5 were checked only through suite regressions and were not re-scripted this round. Confidence is medium.

## Verification

```text
host: PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_backend_test.py
Ran 102 tests  OK
host: PYTHONPATH=scripts/harness python3 tools/kpharness_creative_test.py
Ran 30 tests  OK
host: PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_boot_repair_test.py
Ran 41 tests  OK
container (no ffprobe): kpharness_gamescope_backend_test.py  Ran 102, FAILED (failures=2), both 'configured ffprobe executable was not found'

python3 review-probes-r9-adversarial/p1_head_external.py   (output quoted under R9-1)
python3 review-probes-r9-adversarial/p2_ledger_pidfd.py    (output quoted above)
```

`git diff --check` did not finish within 5 minutes on the MyBook worktree and was stopped. `creative_accept.py` and `creative_export.py` are untracked, so `diff --check` would not cover them anyway. These checks do not prove real pidfd recovery, real FFprobe cleanup, live Gamescope capture, MIT-SHM use, GPU cadence, rendered-frame distinctness, visual framing, or K1 behavior.

Round 9 adversarial verdict: FAIL

## Cross-check with companion correctness review (read after the verdict above was written)

- The companion's R9-1 is the same defect as my R9-1, with the same referents (`creative.py:202`, `creative_accept.py:371,553`, `docs/creative-runner.md:78`, test helper `:41`) and a matching rollback probe. The companion rates it Critical. I keep Important so the rating matches R6-1, R6-2, R7-1 and R8-1 in this file, which were the same kind of provenance gap. The verdict is FAIL either way. Their repair adds a per-run nonce in the empty ledger, so a retained launch head cannot match a replayed empty ledger. I agree and add it to the R9-1 fix.
- The companion's R9-2 (a non-dict resolution payload raises `AttributeError`, which escapes `cleanup_state_clear()`'s `except (OSError, ValueError, TypeError, JSONDecodeError)`) is fair. It fails closed by raising, so it is Minor. It belongs with my R9-2 exact-schema note.
- No disagreement on closure of R8-2/R8-3 or of earlier rounds.

Verdict unchanged by the cross-check.

Round 9 adversarial verdict: FAIL

## Round 10 verdict

Round 10 closes R9-1 as it was stated. Each run now has a nonce-bound launch head. Every ledger change prints one head line to stderr and appends it to a commitment log outside the run directory. The accept and recover CLIs print the failure ID and head and exit nonzero. With the head taken only from tool output, reset, fresh-empty, forged-pair, deletion, v1 downgrade and cross-run transplant all fail closed (p1). All R9 minors are closed (p3).

Part B's geometry precondition matches `Xext/shm.c:639-654`, and the content gate does not pass a static source through encoder noise (p4). I found two Important gaps. First, a new precondition can silently drop a surviving FFprobe child from the ledger. Second, the diagnostic driver's supervisor kills its child before the ordered cleanup can run on Ctrl-C.

**Authorization decision for exactly one bounded animated diagnostic: REFUSED.** Fix R10-1 and R10-2 and rerun p2/p7 and p5 first.

## Critical

None found.

## Important

### R10-1. A surviving FFprobe child gets no ledger record when the commitment log becomes unusable during the probe, and the error hides the survivor

`_append_cleanup_record()` calls `validate_commitment_log()` before it takes the lock and before it writes anything (`creative_accept.py:390`). `accept()` checks the log once at entry (`:691`). It then runs the probes, which can last up to 2 x 30 s, and records a failure in the `except ProbeCleanupError` block (`:762-763`). The log may stop being admissible inside that window. The operator may have deleted or rotated it, or hard-linked it for a backup (so `st_nlink` becomes 2). In that case the append raises before the ledger changes. `main()` prints only the log error. The ProbeCleanupError, with its PID and start, survives only as `__context__`. The ledger stays at the launch head, so the gate is clear, and a re-run of acceptance with the same head succeeds. The docs promise the opposite: "Before the acceptance CLI exits, that path appends one failure record" (`docs/creative-runner.md:487`). This is exactly the outcome the brief forbids for the empty-identity case: "silently produce no record and a clear gate".

```text
p2  log_vanished_during_probe: exit=1 stdout_error='cleanup commitment log is missing; create it outside the run directory'
      survivor_mentioned_in_output=False
      ledger_records_after=0 gate_clear_with_same_head=True
      reaccept_after_unrecorded_survivor: exit=0 ok=True
p7  hardlink_during_probe: exit=1 error='cleanup commitment log must be a unique regular non-symlink file' records=0 clear=True pid_in_output=False
```

The same record is lost in two other cases, found by reasoning from the code. One is a supplied-head mismatch under the lock, when another transition happened during the probe. The other is the 10 s lock timeout (`:341-356`). Before round 10 only a real disk-write failure could drop the record. The log precondition makes this avoidable loss new.

Fix: write the ledger record first. Validate the log only inside `_emit_head`, which already prints to stderr before it touches the log. On any failure to persist or to emit, put the survivor's PID, start, command and "do not accept this run" in the CLI's failure JSON, and exit nonzero. Add a regression that deletes or hard-links the log inside the probe and asserts the failure is recorded and the gate is blocked.

### R10-2. Ctrl-C during the diagnostic kills the child before its ordered cleanup, and leaves the owned Gamescope, mpv and FFmpeg running

`supervise()` starts the child with `deps.spawn_child = subprocess.run` (`capture_diagnostic.py:519`), in the supervisor's own process group. A terminal Ctrl-C sends SIGINT to both processes. The child's `run_child` catches `BaseException` and starts `ordered_cleanup` (`:285-331`). But in the supervisor, `subprocess.run` handles the KeyboardInterrupt by waiting `_sigint_wait_secs = 0.25` s and then running a bare `except: process.kill()`, which SIGKILLs the child. Host Python 3.14.7 source: `self._sigint_wait_secs = 0.25`. `subprocess.run`: `except:  # Including KeyboardInterrupt ... process.kill()`. `recorder.stop` alone (FFmpeg `q` plus a bounded wait) takes longer than 0.25 s. So the recorder → client → display order does not run.

mpv was started with `start_new_session=True`, so it gets no SIGINT and survives uncleaned. Whether Gamescope and FFmpeg die or survive depends on their process groups. Either way nothing cleans them up in order. The survivors keep the inherited canonical lock descriptor. That is safe for other harnesses, but a private display stays live. Because the child is killed, `diagnostic-run.json` is never written, so `_owned_identities` is empty (`:445-458`). The name scan in the finally block covers neither mpv nor Xwayland (`FORBIDDEN_NAMES`, `:57`), so the result under-reports survivors. SIGHUP (terminal closed) is worse: by default both processes die with no cleanup at all. `except (DiagnosticRefused, OSError, ValueError, RuntimeError, SubprocessError)` (`:522`) does not catch KeyboardInterrupt. The finally block still writes a FAIL result, but only after the child is gone.

```text
p5 (harmless stand-in: child mimics run_child with three 0.5 s cleanup steps; parent uses subprocess.run; SIGINT to the group)
parent_exit=-2
parent_finally_ran=True
child_cleanup_steps_completed=[]
```

Fix: start the child with `start_new_session=True`. In the supervisor, replace `subprocess.run` with a Popen and wait loop. On SIGINT, SIGTERM or SIGHUP, forward one SIGINT to the child and wait for it, bounded by the cleanup budget (recorder + 2 + 2 + lease close). Escalate only after that budget. Record the interruption in the result. Add a mocked regression in which the supervisor's wait raises KeyboardInterrupt and the child is not killed before the budget.

## Minor

### R10-3. The docs present the commitment log as the anchor but do not say it must be out of reach of whoever can write the run directory

The tool never reads the log back. `validate_commitment_log` only calls `lstat` and `resolve`, and `_emit_head` opens it `O_WRONLY|O_APPEND` (`creative_accept.py:295-338`). The head is whatever the operator passes. The docs tell the operator to use "the last line for this run's nonce in your commitment log" (`docs/creative-runner.md:89`). A same-user writer who forges the ledger can also append one forged head line. Following the doc, acceptance then passes: `log_appended_forgery_following_doc_last_line_for_nonce: exit=0 ok=True` (p1). An unprivileged user-namespace bind mount also makes a log inside the run directory pass placement validation (`bind_mount_alias_of_run_log: accepted`, p8). The writer's report does state this "operational boundary", but the docs do not.

Also:
- The export example says `SHA256_SIGNED_IN_THE_ACCEPTANCE` (`:163`), and that value is read from the run directory's receipt.
- The diagnostic supervisor appends its commitments line through an unvalidated `Path.open('a')` (`capture_diagnostic.py:504`).

Doc fix: the captured stderr/stdout head is the strongest anchor. The log is an anchor only if the run-directory writer cannot modify it (another account, `chattr +a`, or off-host). For export, pass the same head used for acceptance.

### R10-4. The `--child` entry skips authorization, preflight, the snapshot and the lock check

`main()` routes `['--child', CONFIG]` straight to `_child_main` (`capture_diagnostic.py:577`). This skips `--authorized-single-run`, preflight, the snapshot, the commitments line, and any check that `config['lock_fd']` is the flocked canonical lock. Accidental use is unlikely. The fix is cheap: the child should verify the inherited descriptor with `gamescope_socket.canonical_lock_guard()`, and refuse unless it was started by the supervisor, for example by checking a nonce in the config that also appears in `commitments.json`.

### R10-5. Preflight fails open on unreadable `/proc` rows and checks only `comm` and `argv[0]`

`process_inventory` silently skips any row whose `comm`, `stat` or `cmdline` read raises (`capture_diagnostic.py:120`). A `wineserver` with an unreadable cmdline is not inventoried (`unreadable_cmdline: detected=False inventoried=False`, p6). Wrappers such as `bash ~/.local/bin/ffmpeg`, or a renamed comm with the real binary in a later argv, are missed. What is detected: the user's own `wineserver` (PotPlayer), `swkotor.exe` / `swkotor2.exe`, and `gamescope-wl`. Detection always ends in refusal. The only signals the driver sends are `send_signal(SIGINT)` and `kill()` on its own mpv Popen (`:247-258`). Nothing unowned is ever killed.

### R10-6. `mpv --force-window=immediate` together with the first-frame black gate can false-FAIL the single diagnostic (`unverified`)

`--force-window=immediate` (`capture_diagnostic.py:91`) maps a black window before the first testsrc2 frame is shown. Window discovery then starts the recorder right away. If FFmpeg's first grab lands before mpv's first video frame, `capture_content_black` fires (`display_backends.py` `evaluate_content`: first frame `ymax <= 24` or `ymax == ymin`). I did not observe mpv. Consider `--force-window=no`, or waiting for a non-black probe before starting the recorder.

### R10-7. The content gate accepts partly censored frames and low-activity scenes

The black test only needs the first frame's `ymax > 24` and `ymax > ymin`. A frame that is mostly censored (zeroed by `XaceCensorImage`) with any visible region passes. In the acceptance interval, "distinct" means any Y, U or V DIF > 0. Encoder refinement after each real change roughly doubles the count. An 8x8 box that blinks twice a second on a still frame scores 0.0694 and passes `game-capture-v1` (0.05), though it fails `animated-diagnostic-v1` (p4). This matches the brief ("record the distinct ratio as evidence"). It is listed so nobody reads a passing game ratio as proof of full-frame capture.

## Closed findings and additional probes

- **R9-1 closed.** Nonce-bound launch heads are unique (`launch_heads_unique=True`). The failed CLI exits 1 with `ok:false`. The stderr head line carries the failure ID, and stdout matches it. With only the captured head, `reset_to_launch`, `fresh_empty`, `forged_pair`, `deleted`, `v1_downgrade` and `transplant_other_run` all exit 1 and leave the receipt `pending` (p1). The writer's tests take the head from `head_lines(stderr)` or the log, never the file (`tools/kpharness_gamescope_backend_test.py:1718-1770`).
- **Commitment-log placement.** Refused: inside the run directory, a relative path inside it, `..` into it, a directory symlink into it, lexical `..` through a symlink, the run directory itself, and a log inside it when the run is named through a symlink. Accepted: plain outside paths, and a symlink in the run directory that points outside (the file really is outside) (p2). The one gap is the bind mount (R10-3).
- **Lock and head recheck.** Four threads appending with the same supplied head give `['ok','refused','refused','refused']`, one record, and a log head equal to the file (p2). A same-user writer that ignores `flock` is not stopped. That is reasoned, not probed. An unlocked overwrite during an append is itself overwritten, and the emitted head then disagrees with any tampered file.
- **R9-2 closed.** Refused: bool and float stand-ins for `schema`, `sequence`, waits and `pid`; list and string payloads (failure and resolution); duplicate keys; non-canonical whitespace; `Z` timestamps and timestamps without microseconds; a resolution earlier than its failure; a v1 ledger; and a top-level list. All give `ValueError`, not `AttributeError` (p3).
- **R9-3 closed.** A different start resolves as `original_exited_pid_reused` with 0 signals and no pidfd opened. Reuse seen while the pidfd is held still refuses with 0 signals and an unchanged ledger (p7, real fd).
- **Boot and namespace binding.** Another boot, another namespace, or a non-dict host reader all refuse with 0 signals (p3).
- **Unavailable identity.** Recorded as `identity: unavailable`, the gate is blocked, and recovery refuses (p3).
- **R9-4 closed.** The stale per-failure-file text is gone.
- **R9-5 closed.** The backend suite passes in the container, which has no `ffprobe`.
- **R9-6 closed** for cooperating writers.
- **R8-3 / R7-2 regressions still hold.** `r8_3=(True, True, [2])`.
- **Part B geometry.** `xwininfo` "Absolute upper-left" is the outer corner. With `border_width == 0` required, it equals `pDraw->x`. The root size from `xwininfo -root` equals `pScreen->width/height`, because `update_screen_size` sets both `screen->width` and `root->drawable.width` (`/tmp/t7src/hw_xwayland_xwayland-output.c:224-245`, `dix_window.c:3672-3673`). I found no geometry that passes and still hits BadMatch at start. A move or resize after the pre-exec read makes xcbgrab log `Cannot get the image data` and `Continuing without shared memory.` (both present in `/lib64/libavdevice.so.62` for FFmpeg 8.1.2). The log scan runs in startup admission, the watch loop and stop. The watch's `_binding` also compares against the frozen pre-exec geometry. A size above the window fails at FFmpeg start ("outside the screen size"). A title injected into the header line cannot override the real fields (`title_injection: status=verified size=[1024, 768] map=IsViewable border=0`, p7). A title containing `(the root window)` is refused. `xwininfo` labels are not localized.
- **Content gate vs encoder noise.** The master's exact codec (`libx264 ultrafast crf 28 yuv420p threads 2`, `recording.py:1114-1115`) was run on synthetic stills through host `/usr/bin/ffmpeg`, then probed with the production `probe_frame_content` and `probe_frame_pts` over `/proc/self/fd/N` with brew FFprobe 9.0.1. Results for a static source: static testsrc2 frame ratio 0.0117, textured noise 0.0006, black and flat-dark both `capture_content_black` + `capture_content_static`. All fail both policies. Animated testsrc2 passes with 1.0. Frame counts matched PTS (2100/2100) in every case. The static-noise margin under the game policy is about 4x (0.0117 vs 0.05).
- **Part C.** The driver refuses without `--authorized-single-run` and never retries. The lock descriptor is inherited by every child (`pass_fds`), and the lease's `canonical_lock_guard` looks for exactly that inherited flock. The real signatures of the lease, discovery, verifier and recorder match what `_child_main` passes. The snapshot is created, then verified, and verified again after the run. The commitments line is printed and logged before the single spawn.

## Residual risks (brief-level, not writer defects)

- The diagnostic samples a 60 FPS mpv source at 60 FPS. Phase jitter near a flip boundary causes duplicate and skip pairs, which press on both the ≥99% distinct and the cadence criteria. The one run may fail for this reason alone.
- K1's game window probably starts black. The mandatory first-frame black gate would then fail every `game-capture-v1` run, as the writer also notes. The orchestrator should decide this before K1 capture.

## Verification

```text
container (no ffprobe on PATH):
  kpharness_creative_test.py              Ran 32 tests   OK
  kpharness_gamescope_boot_repair_test.py Ran 41 tests   OK
  kpharness_gamescope_backend_test.py     Ran 121 tests  OK
  kpharness_capture_diagnostic_test.py    Ran 14 tests   OK
host (host-cmd, Python 3.14.7): same four suites  32 / 41 / 121 / 14  OK   (208/208 both)

review-probes-r10-adversarial/
  p1_head_external.py            R9-1 re-run, head only from CLI output / log (output above)
  p2_log_placement_and_persist.py placement, R10-1 deletion trigger, concurrent appends
  p3_ledger_schema_pidfd.py      exact schema, recovery paths
  p4_static_encoder_noise.py     host only: synthetic lavfi -> /usr/bin/ffmpeg exact codec -> production probes
  p5_sigint_cleanup.py           R10-2 mechanism with a harmless stand-in child
  p6_preflight.py                synthetic /proc tree
  p7_extra.py                    R10-1 hard-link trigger, title injection, pidfd-held reuse (real fd)
  p8_bind_mount.sh               user-namespace bind mount alias
```

No Wine, Gamescope, Xvfb, Xwayland, mpv, game or x11grab was started. The live-game lock was not opened by the probes. The p4 FFmpeg runs used only lavfi sources to rawvideo to libx264 files in `/tmp`. `git diff --check` was not rerun.

Round 10 adversarial verdict: FAIL

## Round 11 verdict

I performed this review independently of the companion correctness review. I resumed the stopped review rather than starting a second section: the existing R11 adversarial probes p10 through p14 and their source were present in `review-probes-r11-adversarial/`, while this verdict section was absent. I also inspected the producer's Round 11 report and the dirty worktree status; no source files were modified by this review.

The revised content-floor evidence is useful but does not repair the two launch-authority/cleanup failures below. `p14_content_attacks.py` reports that alternating full frames and `testsrc2` at 640x480/upscaled, 60 fps, and a 39 s interval pass the diagnostic policy; half-duplicate streams including temporal encoder noise and a live 128px box fail it at 0.5000; and the start-marker fade test distinguishes black at 0.00/0.05 s from non-black at 0.10 s onward. The static/low-motion results remain an intentional game-policy limitation, not a false diagnostic pass. `p13_lock_inheritance.py` also shows the held lock FD in the real FFprobe-shaped child and xwininfo-shaped child. Those claims hold, but neither is an end-to-end live capture proof.

### Important

#### R11-1. A signal in the `Popen` return window can orphan an already-launched child; the supervisor records no child identity and exits before the child's ordered cleanup

`supervise()` assigns `process = deps.spawn_child(...)` and only afterwards assigns `signals.child = process` (`capture_diagnostic.py:880-884`). `_SupervisorSignals.handler()` raises `DiagnosticInterrupted` whenever `self.child is None` (`:625-629`). Thus a terminal SIGINT, SIGHUP, or SIGTERM delivered after the underlying child has forked but before `Popen` returns is interpreted as “before launch.” The `finally` only forwards/waits if `process is not None` (`:896-908`), so it has no handle to supervise, forward to, or kill the already-created session.

The existing synthetic process-tree attack wraps the real `subprocess.Popen`: it starts the real dummy child, writes its PID, sends SIGINT to the supervisor itself before returning, then returns the child. It uses the real `supervise()` and the real child `run_child()`, with no display. Its saved result is:

```text
supervisor_exit=1 errors=['interrupted before launch: SIGINT'] launches=1 child_returncode=None owned_survivors=[]
child_alive_after_supervisor_exit=True owned_started_after_supervisor_exit=['display:gamescope', 'client']
unsupervised_child_completed_run=True its_cleanup_steps=['recorder', 'source_process', 'display'] result_file_rewritten=False
```

The process is not killed by the probe; it continues independently and later happens to perform its own cleanup. A production child that hangs, is stopped, or fails before its own cleanup has no ordered-cleanup budget enforcement and no survivor accounting. This contradicts the requirement that signals during *each cleanup phase* cause owned cleanup within the budget, and the stated parent-side guarantee for signals during diagnostic launch.

claim: “SIGINT/SIGHUP/SIGTERM during the diagnostic always runs the ordered cleanup within the bounded budget.”
referent: `capture_diagnostic.py:880-908`; `review-probes-r11-adversarial/p11b_supervisor_spawn_window.py`; `p11b.out`
checked: real `supervise()` with a post-fork/pre-return Popen wrapper and a real dummy child tree
verdict: does not hold
confidence: high; only an atomic spawn/registration mechanism or an external reaper tied to the run identity would change it

Fix: block the interrupt set around child creation and registration, then restore it and explicitly process pending signals; or spawn through a small registered launcher/reaper whose PID is known before it forks the child. The regression must inject each of SIGINT, SIGHUP, and SIGTERM in that exact post-fork/pre-return window and assert no child or owned process remains after the 1,442 s budget (or its test-scale equivalent).

#### R11-2. `--child` authority accepts a forged private “canonical” lock when `KP_GAMESCOPE_REPO_ROOT` is supplied by the caller

The child verification path imports `canonical_lock_guard()` (`capture_diagnostic.py:447-451`). That guard derives its root directly from `os.environ['KP_GAMESCOPE_REPO_ROOT']` when it exists (`gamescope_socket.py:43-46`), then accepts any held FD matching `root/tmp/harness-locks/live-game.lock` (`:54-73`). The supervisor sets that environment variable correctly for its own child (`capture_diagnostic.py:875`), but `--child` itself does not authenticate the value or require that it resolves to this worktree/common Git directory.

`p12_child_token.py` rejects no-token, no-commitments, replayed-token, regular-file-token, and an unlocked forgery. It then creates a private fake Git-looking root, takes an exclusive flock on its private `live-game.lock`, supplies a matching pipe token and a matching `commitments.json`, sets `KP_GAMESCOPE_REPO_ROOT` to the fake root, and receives:

```text
forged_pipe_commitments_env_redirected_lock: ADMITTED
canonical_lock_path_would_be= /run/media/brunner56/MyBook/Workspaces/KotorPhasor/tmp/harness-locks/live-game.lock exists= True
```

The test intentionally stops immediately after authority verification, so it neither touches the canonical lock nor launches Wine/Gamescope. An arbitrary same-user caller can therefore construct a complete child configuration and cause `--child` to accept without holding the actual live-game lock. The token only authenticates a supervisor that the caller can also forge because the commitment file and its plaintext pipe endpoint are both caller-controlled in this direct-entry path.

claim: “`--child` refuses forgery/replay unless the parent holds the canonical live-game lock.”
referent: `capture_diagnostic.py:420-451,875`; `gamescope_socket.py:43-73`; `review-probes-r11-adversarial/p12_child_token.py`; `p12.out`
checked: private-root, private-lock, matching pipe-token and commitments forgery; no canonical lock opened
verdict: does not hold
confidence: high; pinning the guard's repository/lock identity independently of inherited environment would change it

Fix: do not derive the canonical lock root from a mutable environment variable in the `--child` verification path. Pass and verify a pre-opened lock FD against a lock pathname/identity computed from installed trusted code or a supervisor-signed immutable descriptor; require that exact identity before reading the token/commitments. Add the private-root forgery as a permanent regression.

### Minor

#### R11-3. Preflight does not detect an executable renamed away from every protected basename

The preflight matcher is deliberately limited to `comm`, the `/proc/PID/exe` basename, argv[0], and certain launcher positions. `p10_preflight.py` copies `/bin/sleep` to a file called `enc` as a safe stand-in for an executable renamed from its protected name. The live `/proc` inventory reports `comm=enc`, `exe=.../enc`, argv0=`.../enc`, and `forbidden_processes()` returns `detected=False`. Its synthetic counterpart is likewise admitted:

```text
renamed_copy_exe_argv_comm: ADMITTED
real renamed_enc_binary: detected=False comm=enc exe=/tmp/.../enc argv0=/tmp/.../enc
```

This is an unavoidable limitation of name-based `/proc` classification unless preflight also permits a trusted binary identity comparison. It matters because the task specifically includes renamed/wrapped FFmpeg evasions. The wrapper cases that retain `ffmpeg` in exe/argv are caught; a genuinely renamed executable is not. Preflight correctly sends no signal in this probe and correctly excludes other UIDs, which is safe but leaves the refusal claim incomplete.

claim: “Preflight catches renamed/wrapped FFmpeg without killing foreign processes.”
referent: `review-probes-r11-adversarial/p10_preflight.py`; `p10.out`; matcher described in the Round 11 report
checked: live renamed safe executable plus synthetic `/proc` rows, with `os.kill` and `os.killpg` made fatal
verdict: does not hold for renamed executables; holds for the tested named wrappers and non-mutation property
confidence: high; a trusted executable identity/hash comparison, or explicitly narrowing the guarantee to names, would change it

## Verification and scope

- Reused completed R11 adversarial probes: p10 preflight, p11a CPython signal window, p11b supervisor spawn window, p11c phase signals, p12 child token, p13 FD inheritance, and p14 content/black-marker attacks. p11b and p12 directly establish the two Important findings above.
- I re-invoked p11b, p12, and p10 after resumption. The mounted/high-load environment left the p11b rerun process still in its deliberate real-child wait at the time this verdict was written; its pre-existing completed `p11b.out` is the referent and the source/probe are unchanged. No process outside this review's own synthetic probe tree was signalled.
- The Round 11 implementation report claims 246 tests in each environment (245 run and one opt-in skip) and documents a 1,576 s run cap / 1,442 s cleanup budget. I did not treat those suite claims as proof against the direct adversarial counterexamples.
- Not tested here: live Gamescope/Xwayland/mpv/Wine/K1 behavior, real GPU cadence, or the full 1,442 s timeout path. Per the task constraints, none was launched.

Round 11 adversarial verdict: FAIL

## Cross-check with companion correctness review (read after the verdict above was written)

- **Companion R10-1 (Critical): x264 noise turns duplicated frames into "distinct" frames. You're right.** I tested only fully static sources (p4) and missed the duplicate direction. I re-ran it with my own pipeline: `p9_dup_and_probe_time.py` encodes testsrc2 `rate=30,fps=60` with the master's exact codec, then runs the production probes, then `evaluate_content` over 1-9 s. Result: `half_dup_30_to_60 animated-diagnostic-v1: passed ratio=0.9958`. A capture in which half the frames are stale therefore passes the 99% criterion. That is a false PASS on the exact failure the diagnostic exists to detect. I adopt the companion's rating: Critical, because it gives a false PASS and does not fail closed. My R10-7 is the weaker form of the same defect.
- **Companion R10-2 (Minor) is my R10-1 (Important).** The referents match (`creative_accept.py:390`, gate clear, re-accept exit 0). The deciding criterion is whether a documented guarantee breaks under a non-adversarial trigger. `docs/creative-runner.md:487` promises the record. A hard-link backup of the log (p7) breaks that promise, with no attacker involved. So the argument "a same-user actor could just kill the acceptor" does not settle it. I keep Important. The verdict is FAIL either way, so this does not need escalation.
- **Companion R10-3 (Minor): the diagnostic's FFprobe children do not inherit the lock. That holds.** The recorder's default probes call `probe_frame_pts` and `probe_frame_content` with plain `subprocess.Popen` (`recording.py:609-611`). The same is true of `xwininfo` through `run=`. The post-run name scan still catches a surviving `ffprobe`. I add this as Minor.
- **Companion R10-4 is my R10-5. Companion R10-5 is my R10-3.** They agree.
- **The companion did not report my R10-2** (Ctrl-C and SIGHUP kill the child before ordered cleanup). It stands on p5 and the host `subprocess.run` source.
- **Found during the cross-check (Minor, reliability).** `_bounded_probe_output` has a fixed 30 s deadline (`recording.py:260-283`) that does not scale with media length. The content probe decodes every frame through `signalstats`. On this host, under load average 132 on 12 CPUs, that took 8-22 s for 10-35 s clips at 1024x768. Two p9 runs hit the 30 s bound, giving `TimeoutExpired`. On a quiet host, a multi-minute game capture's content probe could still pass 30 s, which gives `capture_content_failed` or a failed acceptance. The timing on a quiet host is `unverified`. The bound should scale with frame count or duration.

Updated severity summary: Critical 1 (the companion's R10-1, confirmed by p9). Important 2 (my R10-1 and R10-2). Minor: R10-3 through R10-7, the lock-inheritance gap, and the fixed probe deadline.

Round 10 adversarial verdict: FAIL

## Round 12 verdict

I formed this view from the source and my own probes before I read the writer's Grill me section. I read the companion correctness review only after writing this section. No source file was modified. Every lock I used was private; the canonical lock was only `stat`ed. Every signalled process was started by a probe. Probes are in `review-probes-r12-adversarial/` (p15-p20, plus reruns of my R11 p11b and p12 against the R12 code).

The two R11 Important findings are closed. The new pattern holds up against the stale-capture shapes that matter for cadence. It fails closed on skips, blends and heavily partial frames. It does not verify which part of the frame changed, or the order of the levels. So two synthetic stale shapes still pass (R12-2). All four findings below are Minor.

### Critical

None.

### Important

None.

### Minor

#### R12-1. A loader-invoked FFmpeg is not detected, and the documented residual list does not name it

`/lib64/ld-linux-x86-64.so.2 /usr/bin/ffmpeg ...` runs the real configured FFmpeg. `comm` is `ld-linux-x86-64`, `/proc/PID/exe` is the loader, and `argv[0]` is the loader. The loader is not in `WRAPPER_NAMES` (`capture_diagnostic.py:80-81`), so `argv[1]` is never examined. `_match_exe` hashes the loader, not FFmpeg (`:185-209`).

```text
loader_invocation_of_real_ffmpeg: running=True detected=False argv0..1=['/lib64/ld-linux-x86-64.so.2', '/usr/bin/ffmpeg'] {'comm': 'ld-linux-x86-64', 'exe': '/usr/lib64/ld-linux-x86-64.so.2', 'exe_tool_match': None, ...}
loader_invocation_of_renamed_copy: running=True detected=False
```

claim: "renamed copies are found by content" (docs/creative-runner.md:669-676, "The guarantee is limited to that")
referent: `review-probes-r12-adversarial/p19_renamed_binaries.py`, `p19.out`
checked: real host `/usr/bin/ffmpeg` (lavfi 64x48 to null) under the loader, and the real `process_inventory`/`forbidden_processes` with the configured tool identities
verdict: holds for renamed copies, hard links, memfd exec and LD_PRELOAD. It does not hold for a loader-invoked binary, and the residual list ("different build, another user, non-dumpable, started after the scan") omits this case.
confidence: high. Two fixes would close it: add `ld-linux*`/`ld.so` to the launcher names, or match tool `(dev, ino)` against `/proc/PID/map_files`.

Execute-only renamed copy (`chmod 0111`): `exe_identity_unreadable: PermissionError`, not detected. That case is the documented "non-dumpable process whose exe is hidden" residual, so it holds as documented.

#### R12-2. The content gate checks only the size of each difference. A two-frame loop and a 75% frozen frame both pass.

`evaluate_content` counts a frame as distinct when `max(YDIF, UDIF, VDIF)` is at least the floor (`display_backends.py:252-253`). That is a whole-frame mean. It does not show that the whole frame changed, or that the frame is the next one in the pattern. Real 1024x768 encodes through the recorder's exact codec and the production probes gave:

```text
abab_two_frames:   status=passed ratio=1.0000 sep=separated maxdif[min,p50,max]=[52.93,53.01,53.04] yavg[:8]=[124.8, 71.8, 124.8, 71.8, ...]
half_frozen_bottom: status=passed ratio=0.9944 sep=separated maxdif=[0.00,27.92,36.61]
quarter_fresh_top: status=passed ratio=0.9944 sep=separated maxdif=[0.01,14.04,18.49]   (bottom 75% frozen for the whole clip)
tenth_fresh_top:   status=failed sep=ambiguous inside=358
skip7_every_frame: status=failed ratio=0.6250 sep=ambiguous inside=8  (maxdif 2.64-9.76)
tblend_average:    status=failed sep=ambiguous inside=304
every_other_dup_noise3: status=failed ratio=0.5000 sep=separated -> capture_content_static
fresh:             status=passed ratio=1.0000 maxdif min 51.85
```

I have no real capture mechanism for either passing shape. The window and lease geometry are checked exactly, and a hung mpv presents one buffer, not two. So this is Minor. It keeps R11's alternating-frames result (which also passed). The fix is cheap and already in the artifact. `yavg` decodes the seven levels (fresh: 87.6, 143.6, 71.7, 124.8, 176.9, 105.0, 161.5, about 17.6 apart). The gate could require each acceptance frame's level to be the previous level plus 3 (mod 7), or equal to it for a counted duplicate. That rejects the two-frame loop (124.8 to 71.8 and back is -3 then +3, and -3 is +4 mod 7, not +3). It also rejects exact 7-skips (+0) and partial frames, whose `yavg` falls between levels.

The writer's claim on skips holds: "Only a skip of exactly 7 frames repeats a level ... the cadence gate rejects it". The content stream of an every-frame 7-skip is itself `calibration_ambiguous`, which is a failure, so no false PASS comes from that aliasing.

#### R12-3. `calibration_ambiguous` outranks every other failed criterion, including survivors, protected displays and cleanup

`evaluate()` sets the verdict to `calibration_ambiguous` whenever the recomputed separation is ambiguous, "whatever the other criteria say" (`capture_diagnostic.py:786-792`; docs/creative-runner.md:745-747). With the separation stubbed as ambiguous and a real observation that has an owned survivor, a changed protected display, a failed cleanup and a driver error:

```text
verdict= calibration_ambiguous | failed criteria= [... 'cleanup_complete', ..., 'no_owned_survivors', ..., 'protected_displays_unchanged', 'rate_at_least_99_percent', ...]
same observation, separated -> FAIL
```

This is fail-closed: the exit is nonzero, every criterion is recorded, and stdout still lists the errors and survivors. It follows the letter of the ruling ("the verdict is `calibration_ambiguous` ... never pass or blame capture"). But that ruling covers the content result. Here the label also covers cadence gaps, SHM fallback, survivors and X0/X94/X100 changes, none of which depend on calibration. The writer's own Grill #2 and #3 say the first real run may well be ambiguous (real-path noise, duplicate maximum near the band edge). If it is, a capture or safety fault in that run will be headlined as a calibration problem. A partial-update fault (`tenth_fresh_top`, `tblend_average` above) is also reported as ambiguous rather than as a capture fault. The ruling permits that, but it does hide the fault.
Fix: report `calibration_ambiguous` only when every non-content criterion passes; otherwise FAIL, with `content_separation` still recorded.

claim: an ambiguous run "never passes, and it never blames capture"
referent: `p20_ambiguous_outranks.py`, `p20.out`; `capture_diagnostic.py:786-792`
verdict: holds (never passes). Applying the label to non-content failures is the defect.
confidence: high on the behaviour. The severity would rise if any automation keyed on the verdict string.

#### R12-4. The single-thread refusal counts only `threading` threads

`threading.active_count()` (`capture_diagnostic.py:1015-1017`) misses a `_thread`/native thread: `p16.out` shows `threading.active_count()=1 os_threads=2`. The supervisor starts no such thread today, so nothing triggers this. `len(os.listdir('/proc/self/task')) == 1` would be exact.
A second idea, a signal pending at `pthread_sigmask(SIG_BLOCK)` that raises out of it and leaves the set blocked, is `unverified`. p16(b) could not reproduce it (0 of 2,000 attempts). Even if it happened, it would affect only an exiting supervisor.

### Closed findings and additional probes

- **R11-1 (spawn window): closed.** The interrupt set is blocked from before the fork until `signals.child` is set (`:1029-1042`). The child unblocks it only after installing its handlers (`:636-642`).
  - `p15.out`: SIGINT and SIGTERM together in the post-fork/pre-return window gave one forward, `child_interrupts=['SIGINT']`, `child_alive_after=False`, `owned_alive_after=[]`, and no budget exhausted. SIGHUP in the window gave the same.
  - An external SIGTERM after child-ready ran the ordered cleanup `['recorder','source_process','display']`, with `sigblk={'child': 0, 'display:gamescope': 0, 'client': 0}`. No blocked mask leaks to the lease or the client.
  - My R11 p11b rerun (`p11b-r12.out`) gave `child_alive_after_supervisor_exit=False owned_started_after_supervisor_exit=[]` (R11: True, with display and client started unsupervised).
- **R11-2 (`--child` env redirect): closed.** `p12-r12.out` case 6 was refused ("lock descriptor is not the canonical lock file"). In `p17.out`, checkout code with `KP_GAMESCOPE_REPO_ROOT` pointing at a private locked root was also refused. A second open file description of the lock without the flock was refused: fdinfo lists only locks on that `struct file`. A lock renamed away and replaced was refused, and so was one renamed away with nothing replacing it.
- **Writer Grill #1 (weakest: forged snapshot manifest): that holds, as a trust-boundary statement.** I went further than the writer. No manifest forgery is needed. The real `create_snapshot` on a byte-identical copied tree records the copy as `repository_root`, and the child admits a private lock (`p17.out`: `every module byte-identical to checkout = True`, `snapshot_copy_forged_lock: ADMITTED`). A bind mount in a private user+mount namespace redirects `stat(path)` the same way (`bind_mount_redirect: ADMITTED`, private stand-in path). I judge both inside the boundary for one reason. An honest supervisor run from a copied tree takes that copy's lock too (`canonical_lock_path()` derives from `__file__`). The lock is a per-repository cooperative mutex, and a child check cannot be stronger than the supervisor's own lock choice. The residual is correctly documented. The R11 attack, where real checkout code was redirected by an inherited variable, is gone.
- **R11-3 (renamed binary): closed as narrowed.** `renamed_copy_enc` was detected by SHA-256, `memfd_exec_copy` by SHA-256 (comm `3`, exe `/memfd:enc`), and `LD_PRELOAD` on the real binary by inode (`p19.out`). The one gap is R12-1.
- **Writer Grill #3 (duplicate maximum 1.0167 vs band edge 1.3): that holds.** A duplicate above 1.3 becomes ambiguous, not a pass.
- **Writer Grill #4 (mask leak): that holds** (`p15` sigblk all 0). R12-4 is the caveat on the thread check.
- **Writer Grill #2 and #5:** not checkable here. #5 is fail-closed by code (`gamescope_snapshot.verify_snapshot` rehashes `repository_inputs`).
- **Is the histogram tamper-evident?** Partly. `_content_evidence_passed` requires the receipt's content block, including `separation`, to equal the version recomputed from the hashed `ffprobe-content.json` (`display_backends.py:299-306`). A receipt-side edit therefore fails the content criterion. `diagnostic-result.json` itself is neither signed nor committed; only `media_sha256` leaves the run on stdout. The histogram can be recomputed from that master, but the file is not tamper-evident on its own. No claim in the report says otherwise. Also, the bin edges (1, 2, 8, 16) do not coincide with the band edges (1.3, 11.7). The histogram alone cannot show the band, so read `inside_band`.

### Verification

- `python3 p15_spawn_window.py` (container, real `supervise()` plus dummy tree): output quoted above.
- `python3 p16_threads_and_mask.py`: `a) threading.active_count()=1 os_threads=2`; `b) handler_ran=2000/2000 mask_left_blocked_after_raise=0`.
- `python3 p17_child_authority.py`: 8 cases. Env redirect, second OFD, rename+replace and rename-only were refused. Holder OFD (control), snapshot copy and bind mount were admitted.
- `host-cmd python3 p18_content_attacks.py`: 8 real encodes, output quoted in R12-2. Encoded clips are in `/tmp/kp-r12-adv-content/` on the host.
- `host-cmd python3 p19_renamed_binaries.py`: 6 live synthetic FFmpeg runs, 25 s each, lavfi to null. None was signalled.
- `python3 p20_ambiguous_outranks.py`: output quoted in R12-3.
- `p12-r12.out`, `p11b-r12.out`: my R11 probes rerun unchanged against R12 code.
- `PYTHONPATH=scripts/harness:tools python3 tools/kpharness_capture_diagnostic_test.py` (container): `Ran 50 tests in 264.791s OK` (`suite_capture_diagnostic_container.out`). I did not rerun the other suites or the host suites.
- Not done: any real mpv, Gamescope or x11grab path. Whether a real render separates at 1.3/11.7 remains the writer's open handoff question, and only the one authorized run can settle it.

Open question I could not settle: does the real mpv to x11grab path give the level-sequence and full-frame freshness that the synthetic encodes show? One check would settle it: in the authorized run's `ffprobe-content.json`, `yavg` of consecutive acceptance frames should step by exactly +3 levels (mod 7) with `inside_band == 0`.

Round 12 adversarial verdict: PASS

---

## Round 13

Independent adversarial re-review. Read-only on the worktree
`/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`.
Scratch under `review-probes-r13-adversarial/`. Formed an independent view from the
diffs against `r13-baseline/` before reading the writer's Grill me section.

### R13-1. Critical: an exact-loop capture whose loop length is a multiple of the pattern's own period (7) passes clean

The whole point of item 1 (brief) is to catch a capture that never advances —
duplicated, looped, or stalled — using the brightness level sequence. The brief
explicitly asked to try "loops of length 7k (period aligned with the +3 mod 7
cycle — e.g. a 7-frame loop repeating)". It is a real gap, not a near-miss.

`PATTERN_STEP`'s own comment (`capture_diagnostic.py:56-63`) says the level
formula is `level(n) = (3n mod 7) - 3`, so the diagnostic's own brightness
signal is exactly periodic with period 7 forever — that repetition is by design
and expected in a healthy run. `content_level_sequence` only checks that
consecutive levels step by `+3 mod 7`; it never checks that the *same seven
source frames* are not being replayed over and over. `evaluate_content`'s
distinct-ratio check (`capture_content_static`) doesn't catch this either,
because `distinct_ratio` is computed from adjacent-frame `ydif/udif/vdif`
(genuinely large between the 7 distinct frames in one loop cycle), never from
global uniqueness across the whole clip.

I built a real lavfi encode of exactly `CD.PATTERN_GRAPH` truncated to its
first 7 frames and looped indefinitely with `ffmpeg`'s `loop` filter (the same
graph, same recorder codec, same production probes the writer used), 34 s, and
ran the production `D.evaluate_content` on it, unmodified:

```
status: passed
failures: []
distinct_ratio: 1.0
separation: separated 0
level_sequence status: passed violation_count: 0
histogram: [{'level': -3, 'count': 257}, ..., {'level': 3, 'count': 257}]
ladder resolved: True resolution: 87.71
```

A capture that is frozen at its first 116 ms of content — genuinely
"not playing back live," the exact failure mode the diagnostic exists to
detect — is reported PASS, `content_gate` true, no violations, no ambiguity.
I reran with a 14-frame loop (2×7) and got the identical result
(`probe_14loop.py`: `status passed []`). Both probe scripts and their
output are in `review-probes-r13-adversarial/probe_7loop.py`,
`probe_14loop.py`, run via `/home/brunner56/.local/bin/host-cmd python3 ...`
(host `/usr/bin/ffmpeg`, `/home/linuxbrew/.linuxbrew/bin/ffprobe`), encodes
kept at `/tmp/kp-r13-7loop-*/continuous.mp4` and `/tmp/kp-r13-14loop-*/continuous.mp4`
on the host.

This is not a receipt-forgery or trust-boundary question: `content_gate` in
`capture_diagnostic.evaluate` is satisfied honestly, because the underlying
`evaluate_content` genuinely returns `passed` on this input — the recomputed
receipt and a from-scratch recomputation agree. So the masking-precedence
logic (item 3) is not at fault here; the content check itself has the hole.

The writer's report tested only 2-frame and 3-frame loops (`test_two_and_three_frame_stale_loops_fail_as_content_sequence`,
`tools/kpharness_gamescope_backend_test.py:2677-2679`, and the real-encode
`two_frame_loop`/`three_frame_loop` cases), never a period-7-aligned one. The
brief named this exact case; it was not tried.

claim: "A capture that is actually fine must still pass" (brief item 1) and,
symmetrically, a capture that never advances must fail.
referent: `review-probes-r13-adversarial/probe_7loop.py` and `probe_14loop.py`, run against unmodified `D.evaluate_content` / `CONTENT_POLICIES['animated-diagnostic-v2']`.
checked: `host-cmd python3 review-probes-r13-adversarial/probe_7loop.py` → `status: passed`, `violation_count: 0`.
verdict: does not hold.
confidence: high — reproduced twice (7-frame and 14-frame loops), against the real recorder codec and real ffprobe, with the exact policy dict the production code ships.

Fix directions (not adjudicated here, out of scope for a reviewer): a
whole-clip content-uniqueness check (e.g. distinct `(level, phase-within-level)`
signatures, or a raw-frame hash/near-hash cross-check across the full
acceptance window) independent of the level-sequence and DIF-based checks,
since both of those are inherently blind to a period-aligned exact repeat.

### R13-2. Minor (confirmed hold): whole-clip partial freeze remains a documented residual, correctly labeled

The writer's report names `half_frozen_bottom`/`quarter_fresh_top` passing as
a residual and does not try to hide it: `test_whole_clip_partial_freeze_is_a_documented_residual`
pins it, and it's the same class of blind spot as R13-1 (a check that only
sees full-frame aggregate signals, not per-region liveness). I did not
rerun this encode myself — no new referent beyond what the writer already
supplied. Grill answer 5 ("does the narrower band weaken anything") is
consistent with the code (`separation_factor` 2.0 vs the old 3.0 only
*narrows* the ambiguous band, doesn't loosen the sequence check).
verdict: holds (as a documented, not hidden, residual).
confidence: medium (took the writer's referent rather than an independent encode; the R13-1 finding above is the same shape but is independently reproduced).

### R13-3. Null move: label precedence, loader detection, thread count, and the two publication leaks hold

- **Label precedence (item 3).** Read `capture_diagnostic.evaluate`
  (`:830-865` post-diff): `only_ambiguous` requires every content failure to
  start with `calibration_ambiguous` (so a `capture_content_sequence` failure
  next to an ambiguous separation forces FAIL, not masking — matches R12-3's
  concern about the sequence check itself, distinct from R13-1's blind spot in
  the sequence check's own coverage), and requires `non_content` empty, where
  `cadence_evidence_recomputed` is added back into `non_content` unless
  `_cadence_recomputed_apart_from_content` is true. I traced this by hand
  against the diff rather than re-running the 17-way non-content test; the
  logic is sound on read. That holds.
- **Dynamic loader (item 4).** `LOADER_NAME` regex matches `comm`/`exe`
  basename/`argv[0]`; a copy of the loader itself renamed to something the
  regex doesn't match is an admitted, documented gap
  (`docs/creative-runner.md:735`, "for example through `dlopen` from another
  process" — actually the doc line covers dlopen; renamed-loader-binary isn't
  spelled out verbatim but the surrounding "known gap" framing covers it in
  spirit). Did not independently reproduce the renamed-loader-binary case;
  took the writer's `ldso_probe_r13.py`/`p19` referents as sufficient given
  the code reads correctly. Unresolved to medium confidence, not chased
  further (round cap).
- **Thread count (item 5).** `supervisor_thread_count()` is
  `len(os.listdir('/proc/self/task'))`, called before spawn; matches the
  brief exactly. Did not rerun `thread_probe_r13.py` myself, no reason from
  the code to doubt it.
- **Publication leaks (item 6).** `grep -n "/home/\|linuxbrew\|Homebrew" docs/creative-runner.md`
  and `grep -n "linuxbrew\|DEFAULT_FFPROBE" capture_diagnostic.py` from this
  session: both empty/absent. `--ffprobe` is `required=True`
  (`capture_diagnostic.py` diff). Confirmed directly, holds.

### Grill me attack (weakest-first)

1. **"Won't exact +3 fail a healthy real run that has one late frame?"** The
   writer's own answer already concedes zero tolerance is a real risk and
   names the unresolved question (real mpv/x11grab dup-then-skip rate). I
   have nothing to add; that holds as an open, correctly-flagged risk — but it
   is a *false-failure* risk on good captures. R13-1 is the opposite and more
   serious defect: a *false-pass* on a bad capture, which the grill section
   does not mention at all.
2. **"Is a factor of 1.9 safe for the real run?"** Not re-derived independently
   (would need a real mpv/x11grab capture, out of scope: no Wine/Gamescope/
   Xwayland/mpv/x11grab this round). Taking the writer's synthetic numbers
   (3.93 min resolution measured) at face value; unresolved on the real path,
   same as the writer's own framing.
3. **"Can a cadence fault hide under `calibration_ambiguous`?"** Read the code
   per R13-3 above; holds.
4. New grill question the writer's list missed: **"Does the level sequence
   check assume the loop length can't be a multiple of the period it's
   checking?"** No — see R13-1. The check has no way to see a repeat with
   period 7 (or 14, 21, ...) as anything but healthy progression, because it
   only ever looks at consecutive-level deltas.

### Verification

- `diff -u r13-baseline/{display_backends,capture_diagnostic,recording}.py <worktree equivalents>`: `recording.py` cmp-identical (matches the report); the other two diffs read in full (`review-probes-r13-adversarial/diff_display_backends.txt`, `diff_capture_diagnostic.txt`).
- `review-probes-r13-adversarial/probe_7loop.py`, `probe_14loop.py`: real lavfi encodes through `/usr/bin/ffmpeg` via `host-cmd`, `/home/linuxbrew/.linuxbrew/bin/ffprobe`, production `D.evaluate_content` unmodified. Output quoted above.
- `grep` checks for the two publication leaks: clean.
- Not done: any real mpv/Gamescope/x11grab path (out of scope this round); independent rerun of `ldso_probe_r13.py`, `nostep_probe.py`, `_thread` probe, or the writer's stale-loop encodes (took the writer's referents on read of the code, per round cap — the one new probe that mattered for this round's verdict, the period-7 loop, was run fresh).

Open question I could not settle: whether a period-7-aligned exact repeat is
physically plausible on the real mpv→Xwayland→x11grab-equivalent capture path
this harness uses, or whether it can only happen in a synthetic lavfi loop.
One check would settle it: whether any known capture-stall failure mode on
this stack (encoder ring-buffer replay, compositor frame-pacing stall that
re-presents an old buffer) can produce an exact byte-for-byte repeat at a
period that is a multiple of 7 frames specifically. Absent that, the finding
still stands on its own terms: the check that was added specifically to
detect "content isn't advancing" cannot detect the one class of non-advancing
content whose period matches the pattern's own period, and the brief asked
for exactly this case to be tried.

Round 13 adversarial verdict: FAIL
