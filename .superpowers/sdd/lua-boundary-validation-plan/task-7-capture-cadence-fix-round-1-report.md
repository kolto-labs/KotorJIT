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
