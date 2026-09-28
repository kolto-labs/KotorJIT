# Gamescope Root Capture and Cadence Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the failing per-window X11 capture source with the exact root of the already-owned private Gamescope Xwayland display, fail closed on MIT-SHM fallback or unmeasurable cadence, and emit marker-bounded cadence evidence without weakening display/window ownership.

**Architecture:** Keep the existing portable backend/session/recorder boundary. The Linux Gamescope recorder remains the only layer that knows X11 root semantics; it still accepts and continuously verifies the immutable `OwnedWindow` as the authorization target. Common recording code owns marker clocks, FFmpeg progress parsing, PTS analysis, receipt shape, and acceptance states so future Windows Graphics Capture and macOS ScreenCaptureKit backends can supply frames without inheriting X11 flags or error strings.

**Tech Stack:** Python standard library, FFmpeg/ffprobe, private Gamescope Xwayland lease, existing `kpharness` immutable receipts and host-only fake-process tests.

---

## Scope and decision

This is one causal repair slice. Change only the Linux Gamescope capture drawable from the verified child window to the root of the same private display, then add the diagnostics needed to prove or reject that repair. Keep libx264, `ultrafast`, CRF 28, yuv420p, two encoder threads, requested FPS, MP4 master, and the existing marker polling interval unchanged. Do not add CFR interpolation, an FPS filter, or a second encoder.

PipeWire/GStreamer is **not in this first slice**. If the private-root diagnostic still logs an MIT-SHM failure, this slice must stop before route execution and retain a typed failure. A subsequent brief may admit Gamescope's PipeWire node as a distinct Linux capture adapter. Automatically falling back here would change two source transports in one experiment, add node identity and GStreamer lifecycle semantics, and make the result unable to prove whether root X11 capture repaired the defect.

No acceptance content run is allowed directly after code completion. First run a bounded animated-pattern integration diagnostic on the owned display. Only after that passes may the parent authorize a serialized K1 acceptance run.

Do not edit the sealed run snapshot under `/home/brunner56/kp-live-20260922/next-k1-preparations/20260927-task7-scale-102038-74cb804b/harness-snapshot`. Implement in the canonical harness source that generates a fresh snapshot.

## File ownership

| Owner | Files | Exact responsibility |
|---|---|---|
| Capture core owner | `scripts/harness/kpharness/recording.py` | Common marker timeline, progress parser, ffprobe PTS analyzer, fail-closed lifecycle, receipt structures, and the Linux Gamescope root-capture implementation. No session launch or Gamescope process creation. |
| Display contract owner | `scripts/harness/kpharness/display_backends.py` | Capability identifier change, schema-2 identity validation, source/window binding validation, cadence acceptance recomputation, and immutable receipt checks. No FFmpeg process control. |
| Linux session owner | `scripts/harness/kpharness/creative_wine.py` | Keep `DeferredGamescopeRecorder` and `LinuxWineGamescopeCreativeSession` interfaces stable; attach the Linux recorder to the existing lease/verifier; do not move X11 root logic into portable session selection. |
| Orchestration owner | `scripts/harness/kpharness/creative.py` | Parse portable named markers and cadence thresholds, stop before route execution when recorder startup admission fails, merge final recorder/cadence receipt, and suppress representative-success rendering on cadence failure. |
| Tests owner | `tools/kpharness_creative_test.py` | Host-only unit and fake-process coverage for argv, ownership, startup parser, timeout/cleanup, marker intervals, PTS metrics, receipts, and legacy Xvfb behavior. |
| Operator documentation owner | `docs/creative-runner.md` | Document the source change, marker syntax, failure states, thresholds, and the diagnostic-before-live gate. |

The frozen snapshot shows these modules even if the current checkout does not. If a selected implementation checkout lacks them, resolve the canonical source branch/worktree that produced the verified snapshot before coding. Do not copy a sealed run snapshot back into an unrelated checkout and call that provenance.

No C++, Lua, route behavior, physical console protocol, Gamescope lease process topology, socket cleanup, Wine teardown, or game artifact belongs to this slice.

## Invariants that must survive

Root capture changes the drawable, not the authorization model. The recorder must still require all of the following before it starts:

1. `OwnedWindow` has one canonical non-root X11 ID, exact PID/start identity, positive even geometry, private display, lease ID, and admitted capture capability.
2. `OwnedWindowVerifier(target)` returns the same frozen object immediately before process creation.
3. The target lease ID and display equal the attached live Gamescope lease.
4. The lease is private, newly created, alive, and advertises `linux-wine-k1-gamescope`; caller display reuse remains refused.
5. `xdotool getdisplaygeometry` under the lease environment exactly equals both the lease dimensions and frozen game-window dimensions.
6. `xdotool getwindowgeometry --shell <id>` reports `X=0`, `Y=0`, and width/height equal to the display root. Root capture is refused if the verified game window does not cover the complete private display.
7. Exactly one visible PID-owned game window remains present. The watcher continues revalidating it at no less than 250 ms, even though FFmpeg reads the root.

The X/Y/full-root check is Linux-specific evidence owned by the Linux recorder. Do not add `x11_root_id`, X/Y shell parsing, `DISPLAY`, or `-window_id` concepts to a future-neutral capture protocol. The common receipt may use neutral names such as `authorized_surface`, `source_extent`, and `coverage`, with an adapter-specific `details` object.

During the run, any lease death, recorder exit, window disappearance/replacement, PID/start change, geometry change, loss of full-root coverage, or query timeout is terminal. The recorder never silently switches back to a child drawable, a caller desktop, a new window, PipeWire, or a new size.

## Exact command change

The Gamescope command must change from:

```text
-f x11grab -framerate 60 -video_size 1024x768 \
-window_id 0xc00004 -i :1
```

to:

```text
-f x11grab -draw_mouse 0 -framerate 60 -video_size 1024x768 \
-i :1.0
```

The complete first-slice argv is:

```python
command = [
    ffmpeg,
    "-nostdin", "-y", "-threads", "2",
    "-nostats", "-stats_period", "0.25",
    "-progress", str(run_dir / "ffmpeg-progress.log"),
    "-f", "x11grab",
    "-draw_mouse", "0",
    "-framerate", str(fps),
    "-video_size", f"{lease.width}x{lease.height}",
    "-i", normalized_display_screen_zero,
    "-an",
    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
    "-pix_fmt", "yuv420p", "-threads", "2",
    str(run_dir / "continuous.mp4"),
]
```

`normalized_display_screen_zero` must be derived from the admitted lease display: `:1` becomes `:1.0`; `:1.0` stays `:1.0`; malformed or nonzero screens are refused. There is no `-window_id` anywhere in the command. `-draw_mouse 0` avoids root-cursor work and makes the intended evidence explicit.

Keep FFmpeg's existing output timestamp policy in this first slice. Do not add `-fps_mode`, `-vsync`, `fps=`, `-r`, or `setpts`. That isolates acquisition repair from timestamp-policy changes. The final cadence gate will expose any remaining packet collapse. A future evidence-container change can be evaluated from the new progress and PTS receipts.

The portable backend selection tuple returned by `creative.backend()` remains unchanged: session type, recorder type, claim helper, disjointness helper, and source receipt helper. `DeferredGamescopeRecorder.attach(lease, verifier)` and `recorder.start(owned_window, native_log)` also remain stable. Only the attached Linux implementation changes its source drawable after proving the full-root binding.

## Startup MIT-SHM admission

Use two separate files:

- `ffmpeg.log`: FFmpeg stderr, opened in binary append-safe mode and flushed by FFmpeg.
- `ffmpeg-progress.log`: machine-readable `key=value` progress output selected by `-progress`.

Do not parse the carriage-return human status stream. The startup state machine is:

```python
FORBIDDEN_X11_STARTUP = (
    b"Cannot get the image data",
    b"Continuing without shared memory",
)

startup = {
    "status": "pending",
    "timeout_seconds": 5.0,
    "started_monotonic": started,
    "first_frame_monotonic": None,
    "first_frame": None,
    "shm": {
        "status": "pending",
        "method": "absence-of-fallback-through-first-frame-and-continuous-log-watch",
        "forbidden_matches": [],
    },
}
```

Poll every 50 ms for at most 5.0 monotonic seconds. On every poll:

1. Revalidate lease liveness and process liveness.
2. Read only newly appended bytes from both files, retaining an overlap at least as long as the longest forbidden token so a token split across reads is detected.
3. Parse complete progress blocks. A block is complete at `progress=continue` or `progress=end`; integers must be canonical nonnegative decimal strings.
4. Fail immediately if either forbidden token appears, FFmpeg exits, the lease dies, progress is malformed, or an I/O read fails.
5. Admit startup only after a complete progress block reports `frame >= 1`, the output file is a regular non-symlink file inside `run_dir`, and no forbidden marker has appeared.

Absence of a warning before a timer expires is not success. Conversely, FFmpeg has no affirmative “MIT-SHM active” log line, so the receipt must accurately call this `no_fallback_observed`, not `shm_proven`. Continue scanning `ffmpeg.log` for both forbidden tokens until orderly recorder stop; a later fallback transitions the run to `failed`.

Failure classes are stable strings:

```text
capture_start_timeout
capture_shm_fallback
capture_progress_malformed
capture_process_exited
capture_output_invalid
capture_log_read_failed
capture_lease_lost
capture_binding_changed
capture_finalize_timeout
capture_cadence_failed
capture_markers_incomplete
```

On startup failure, set the typed failure exactly once, prevent route execution, signal only the owned FFmpeg process with SIGINT, wait two seconds, then kill and wait two seconds if still live. Always retain logs, progress, `capture-failure.json`, and any partial media. Display/game teardown continues through the existing ordered `recorder -> game_wine -> display` path. Cleanup success does not erase capture failure.

## Progress parser and final diagnostics

Implement a common pure function independent of Linux:

```python
@dataclass(frozen=True)
class FFmpegProgress:
    frame: int
    out_time_us: int
    dup_frames: int
    drop_frames: int
    speed: str
    terminal: bool

def parse_progress_blocks(raw: bytes) -> tuple[list[FFmpegProgress], bytes]: ...
```

It returns complete immutable blocks plus an incomplete suffix. Reject duplicate keys within a block, negative/nondecimal counters, missing `frame`, `dup_frames`, `drop_frames`, or `progress`, an unknown progress value, counter regression, or a terminal block followed by more data. `out_time_us` may be absent before the first frame and is then zero. `speed` is retained as text and never used as acceptance evidence.

At orderly stop, require one `progress=end` block and record its frame/dup/drop counters. If SIGINT exit 255 is accepted under the existing finalization rule but no terminal progress block was emitted, diagnostics are unavailable and cadence fails closed. Do not infer zero drops from a missing field.

Finalization retains the current 15-second orderly media timeout. If it expires, kill only the owned recorder, write `capture_finalize_timeout`, and mark partial media. The shorter two-second escalation is only for failed startup, before route execution.

## Marker and phase-specific evidence

Replace the single semantic marker with a portable named-marker map while preserving `--marker` as the backward-compatible `effect_start` alias. Add repeatable CLI arguments:

```text
--capture-marker NAME=REGEX
```

Names must match `[a-z][a-z0-9_]{0,31}`, be unique, and have regexes that compile before any run directory or mutable resource is claimed. A run may record extra markers, but cadence acceptance requires the names configured as start/end. Add portable arguments:

```text
--cadence-start-marker phase_1
--cadence-end-marker complete
```

For Task 7, the diagnostic/acceptance configuration is:

```text
--capture-marker 'phase_1=\[model-scene:task7scale\] phase=1 actor=1'
--capture-marker 'phase_2=\[model-scene:task7scale\] phase=2 actor=1'
--capture-marker 'phase_3=\[model-scene:task7scale\] phase=3 actor=1'
--capture-marker 'restored=\[model-scene:task7scale\] restored actors=1'
--capture-marker 'complete=\[model-scene:task7scale\] complete phases=3 restored=1'
--cadence-start-marker phase_1
--cadence-end-marker complete
```

Each named marker records its first matching complete native-log line:

```json
{
  "name": "phase_1",
  "pattern": "...",
  "line": "...",
  "native_log_byte_end": 10123,
  "detected_monotonic": 599361.424446232,
  "capture_seconds": 207.117260618,
  "poll_interval_ms": 100,
  "uncertainty_ms": 100
}
```

Reject duplicate occurrence of a marker declared `unique`, missing start/end markers, end at or before start, or Task 7 phase order other than `phase_1 < phase_2 < phase_3 <= restored <= complete`. The common recorder enforces only configured presence/order pairs; Task 7-specific names and order remain launch/test data, never hardcoded platform behavior.

`capture_seconds` is based on the recorder's monotonic start and has the 100 ms log-poll uncertainty stated in the receipt. In the same process, save the monotonic time when FFmpeg startup first frame is observed. Record `clock_alignment = "shared-process-monotonic; capture origin is Popen start; first-frame latency retained"`. Do not claim frame-exact marker alignment.

After media finalization, use ffprobe frame PTS and compute these windows from the source master:

- whole capture;
- route start to route finish, when both monotonic times are available;
- configured cadence start marker to end marker;
- every consecutive named phase pair;
- selected representative interval.

For every interval record start/end capture seconds, uncertainty, first/last included PTS, frame count, inter-frame count, span, effective FPS, requested-slot count, missing slots, interval histogram in 1/60-second ticks, p95/p99/max gap, counts above 25/50/100 ms, FFmpeg dup/drop deltas when progress samples bound the interval, and whether the interval crosses either boundary uncertainty.

## Cadence analysis and acceptance

Implement a pure common analyzer:

```python
@dataclass(frozen=True)
class CadenceThresholds:
    minimum_rate_ratio: float = 0.99
    maximum_drop_ratio: float = 0.005
    maximum_gap_seconds: float = 0.050

def analyze_pts(
    pts_seconds: list[float],
    *, requested_fps: int,
    interval_start: float,
    interval_end: float,
    thresholds: CadenceThresholds,
) -> dict: ...
```

The implementation must reject NaN/infinite/negative/non-increasing PTS, fewer than two frames, invalid interval bounds, and thresholds outside `(0,1]`, `[0,1]`, and `(0,1]` respectively. Use rational/integer tick arithmetic derived from ffprobe timestamps where possible; do not compare rounded display strings.

The evidence master passes only when the configured marker interval satisfies all of:

```text
effective_fps >= requested_fps * 0.99
missing_or_dropped_slots / expected_slots <= 0.005
max_inter_frame_gap <= 0.050 seconds
FFmpeg dup_frames == 0
startup.shm.status == no_fallback_observed
terminal progress diagnostics present
all required markers present and ordered
```

For 60 FPS, the initial minimum is 59.4 FPS. The 50 ms maximum permits two missed 60 Hz periods but not the 83.3 ms gaps in the failed Task 7 selection. Keep thresholds portable and serialized; do not bake KDE, GNOME, X11, Windows, macOS, or Task 7 names into the analyzer.

Distinct decoded-frame hashes remain a reported observation, not a cadence pass condition. Static scene holds can legitimately produce identical images. The first slice may leave distinct-frame status `unvalidated` if no bounded hashing helper exists in canonical source; it must not relabel encoded cadence as game-render cadence.

## Receipt contract

The Gamescope receipt must replace the old `x11-window` source claim with:

```json
{
  "capture": {
    "status": "passed",
    "adapter": "linux-gamescope-x11-private-root-v1",
    "source": {
      "kind": "x11-private-root",
      "input": ":1.0",
      "source_extent": [1024, 768],
      "drawable": "root",
      "details": {"screen": 0, "draw_mouse": false}
    },
    "authorization": {
      "lease_id": "gamescope-...",
      "private_display": true,
      "caller_display_reused": false,
      "authorized_surface": {
        "id": "0xc00004",
        "pid": 1257609,
        "pid_start": "59913887",
        "extent": [1024, 768]
      },
      "coverage": {
        "status": "exact",
        "surface_origin": [0, 0],
        "surface_extent": [1024, 768],
        "source_extent": [1024, 768]
      }
    },
    "startup": {
      "status": "passed",
      "timeout_seconds": 5.0,
      "first_frame": 1,
      "first_frame_monotonic": 0.0,
      "shm": {
        "status": "no_fallback_observed",
        "method": "absence-of-fallback-through-first-frame-and-continuous-log-watch",
        "forbidden_matches": []
      }
    },
    "command": ["ffmpeg", "..."],
    "diagnostics": {
      "status": "complete",
      "progress_path": "ffmpeg-progress.log",
      "terminal": {"frame": 0, "dup_frames": 0, "drop_frames": 0}
    },
    "markers": [],
    "watch": {"interval_ms": 250, "checks": 0}
  },
  "cadence": {
    "status": "passed",
    "requested_fps": 60,
    "thresholds": {
      "minimum_rate_ratio": 0.99,
      "maximum_drop_ratio": 0.005,
      "maximum_gap_seconds": 0.05
    },
    "acceptance_interval": {"start_marker": "phase_1", "end_marker": "complete"},
    "whole_capture": {},
    "intervals": [],
    "failures": []
  }
}
```

Portable schema fields are `adapter`, `source.kind`, `source_extent`, `authorization`, `startup`, `diagnostics`, `markers`, and `cadence`. X11 details remain nested in the Linux adapter's `source.details`. Future Windows/macOS adapters populate the same portable fields with their own adapter IDs and details.

`capture.status = passed` requires source authorization, successful startup, continuous identity watch, orderly finalization, and complete progress diagnostics. `cadence.status = passed` is separate and requires the configured marker interval thresholds. Overall schema-2 execution and `acceptance_ready` require both. Valid route predicates with failed capture are retained as `route.status = passed`, `capture.status = failed` or `cadence.status = failed`, `media.status = retained_failure_recording`, and overall `ok = false`.

Update `schema2_receipt()` and `execution_evidence_ready()` so they no longer require `-window_id`. They must instead require:

- command has exactly one each of `-f`, `-video_size`, `-framerate`, and `-i` before/around the expected input position;
- command contains no `-window_id`;
- `-f x11grab`, `-draw_mouse 0`, normalized private display screen 0, lease dimensions, and requested FPS match the receipt;
- exact root coverage binds the same immutable window and lease already recorded in top-level `window` and `display`;
- startup, diagnostics, capture, and cadence all passed.

Do not accept serialized booleans or statuses without recomputing these relationships.

## Task 1: Lock the portable contracts with failing tests

**Files:**
- Modify: `tools/kpharness_creative_test.py`
- Read only: `scripts/harness/kpharness/display_backends.py`

- [ ] Add tests constructing a valid existing `DisplayLease`/`OwnedWindow` and assert the portable backend factory and `DeferredGamescopeRecorder.attach/start` signatures do not change.
- [ ] Add a test proving Linux X11 fields appear only beneath adapter-specific receipt details and are absent from the common cadence analyzer input.
- [ ] Add schema tests that reject old `-window_id`, missing exact coverage, foreign lease/window identity, caller display reuse, and a cadence boolean that contradicts recomputed metrics.
- [ ] Run `python3 tools/kpharness_creative_test.py`; expect the new tests to fail against the current child-window schema while all pre-existing tests retain their prior outcomes.
- [ ] Commit only the test change.

## Task 2: Implement and test exact private-root binding

**Files:**
- Modify: `scripts/harness/kpharness/recording.py`
- Modify: `scripts/harness/kpharness/display_backends.py`
- Test: `tools/kpharness_creative_test.py`

- [ ] Add fake-runner tests for display `:7`, root 1024x768, window at 0,0 size 1024x768; assert command input `:7.0`, no `-window_id`, `-draw_mouse 0`, and unchanged encoder flags.
- [ ] Add refusal tests for window at nonzero origin, smaller/larger window, root/lease dimension disagreement, odd dimensions, changed verifier identity, dead lease, second visible window, and malformed/nonzero display screen.
- [ ] Implement the Linux-only root binding and command construction while leaving `X11Recorder` software/Xvfb behavior and portable attach/start signatures intact.
- [ ] Update capability ID from `ffmpeg-x11grab-window-id` to `ffmpeg-x11grab-private-root-v1`; retain the existing single-window enumeration and `x11-xdotool` input capability.
- [ ] Run the host-only creative tests; expect every new binding/argv test and every legacy Xvfb test to pass.
- [ ] Commit this slice.

## Task 3: Implement fail-closed startup diagnostics

**Files:**
- Modify: `scripts/harness/kpharness/recording.py`
- Test: `tools/kpharness_creative_test.py`

- [ ] Add table tests for complete/split forbidden log tokens, one-frame progress admission, malformed/partial progress blocks, counter regression, process exit before first frame, lease loss, output symlink/outside-run path, and five-second timeout under a fake monotonic clock.
- [ ] Add cleanup tests proving startup failure sends SIGINT only to the owned FFmpeg process, waits two seconds, escalates once, retains typed evidence, and permits existing game/display teardown without turning capture green.
- [ ] Implement the pure progress parser, incremental overlapping log scanner, startup state machine, and continuous forbidden-token watch.
- [ ] Ensure `LinuxWineGamescopeCreativeSession.boot()` does not return its channel until recorder startup admission passes; route step 1 must never execute on startup failure.
- [ ] Run the focused test file and verify all startup cases pass without invoking FFmpeg, X11, Wine, or Gamescope.
- [ ] Commit this slice.

## Task 4: Add named markers and interval analysis

**Files:**
- Modify: `scripts/harness/kpharness/recording.py`
- Modify: `scripts/harness/kpharness/creative.py`
- Test: `tools/kpharness_creative_test.py`

- [ ] Add parser tests for valid repeated `NAME=REGEX` markers, invalid names, duplicate names, invalid regexes, missing cadence endpoints, and preservation of existing `--marker` as `effect_start`.
- [ ] Add marker watcher tests with lines split across reads, log truncation, duplicates, out-of-order phases, byte offsets, first-match retention, 100 ms uncertainty, and monotonic capture seconds.
- [ ] Add analyzer tests for perfect 60 Hz, this run's 528-frame selected interval histogram, the 616.667 ms failure, NaN/duplicate/decreasing PTS, boundary uncertainty, too few frames, and threshold edges at exactly 59.4 FPS, 0.5% drops, and 50 ms.
- [ ] Implement named markers and the pure PTS analyzer. Invoke ffprobe only after recorder finalization; parse JSON with a bounded timeout and retain raw `ffprobe-cadence.json` input/output evidence.
- [ ] Make representative selection require configured start/end markers and include the complete marker interval plus explicit lead/tail; do not cut a success clip from only the first marker.
- [ ] Run focused tests and verify platform-neutral analyzer/marker tests pass.
- [ ] Commit this slice.

## Task 5: Make receipts and orchestration fail closed

**Files:**
- Modify: `scripts/harness/kpharness/display_backends.py`
- Modify: `scripts/harness/kpharness/creative.py`
- Modify: `scripts/harness/kpharness/recording.py`
- Test: `tools/kpharness_creative_test.py`

- [ ] Add complete receipt fixtures for pass, SHM fallback, startup timeout, route-pass/cadence-fail, missing terminal diagnostics, missing complete marker, foreign window binding, and cleanup retry after capture failure.
- [ ] Update `receipt()`, `schema2_receipt()`, and `execution_evidence_ready()` to recompute authorization and acceptance from primitive evidence.
- [ ] Preserve route outcome independently; bypass representative-success rendering whenever capture or cadence fails; hash readable partial media under `retained_failure_recording`.
- [ ] Assert stale or manually edited `status=passed` cannot override contradictory command, counters, PTS metrics, marker order, or failure evidence.
- [ ] Run all host-only harness tests, then the repository's existing offline test command. No live tools are permitted in this task.
- [ ] Commit this slice.

## Task 6: Document and perform the non-live review gate

**Files:**
- Modify: `docs/creative-runner.md`
- Review: all files above

- [ ] Document the exact command change, private-root authorization, absence-based SHM evidence wording, named-marker syntax, thresholds, typed failures, retained-failure media, and explicit PipeWire exclusion.
- [ ] Run `python3 -m py_compile` on changed Python modules and the focused host-only test file.
- [ ] Run `rg -n 'window_id|Continuing without shared memory|fps_mode|vsync|pipewire|gstreamer'` over the diff and verify every occurrence matches this brief: no child-window argv, no silent fallback, no timestamp rewrite, and no first-slice PipeWire implementation.
- [ ] Inspect the full diff for unrelated source, artifact, route, or live-process changes.
- [ ] Prepare a fresh immutable harness snapshot and static manifest only after tests pass. Snapshot preparation is not a live/display/media launch.
- [ ] Stop and request the parent's separate authorization for the bounded animated-pattern diagnostic. Do not launch K1 as the first validation.

## Bounded diagnostic acceptance after implementation

The later diagnostic, outside this no-launch task, must use the same private Gamescope lease and root recorder with an animated test source whose frame changes are known. It passes only if:

- startup observes a first frame within five seconds;
- neither forbidden SHM fallback string occurs at any point;
- exact root/window coverage remains stable;
- terminal progress diagnostics exist;
- the configured marker interval reaches at least 99% of requested cadence;
- drop/missing ratio is no more than 0.5%;
- maximum marker-interval gap is no more than 50 ms;
- FFmpeg reports zero duplicates;
- cleanup passes in `recorder -> source/process -> display` order; and
- a second independent static receipt recomputation returns acceptance-ready.

If it fails with `capture_shm_fallback`, do not loosen the gate, add CFR, lower the requested FPS, or rerun K1. Preserve that result and start a separate PipeWire/GStreamer adapter slice with explicit node identity, format negotiation, progress, marker clocks, cleanup, and the same portable cadence receipt.

## Self-review checklist

- [ ] Root drawable change is the only capture-transport change.
- [ ] Existing lease, exact window identity, real input, geometry, and cleanup gates remain stronger than before.
- [ ] Startup success requires a real first frame and continuous absence of the exact fallback diagnostics.
- [ ] Timeouts use monotonic clocks and terminate only owned processes.
- [ ] Route success cannot make capture or cadence pass.
- [ ] Phase acceptance uses named start/end timestamps, not whole-run average FPS.
- [ ] Linux details stay inside the Linux adapter receipt; common marker/cadence code is reusable by Windows and macOS.
- [ ] PipeWire is an explicit follow-up, not a silent fallback.
- [ ] No test or validation step in this brief launches Wine, KOTOR, Gamescope, X11 capture, or modifies existing media.
