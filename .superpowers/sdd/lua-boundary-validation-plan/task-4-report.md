# Task4 portable creative run and media

Implemented focused shared orchestration and explicit current-host adapter.
Files: kpharness/creative.py, creative_steps.py, creative_wine.py, recording.py;
tools/kpharness_creative_test.py; CMake offline test registration;
docs/creative-runner.md. No game launch, runtime build, live-stage edit, or
shipped Lua-source change was performed by this worker.

Platform steering preserved: --backend linux-wine-k1 selects the implemented
LinuxWineCreativeSession/X11Recorder. macos-k1 and macos-k2 return structured
unsupported before file creation or staging. Shared CLI, route/receipt identity,
independent readback artifact retention, selection and rendering have no invented
Mac memory/launch backend. No plugin framework or new engine API was introduced.

CLI accepts repeat --script, --route, --build-dir, --source, --staged,
--wineprefix, --checkpoint-root, --output, target consistency, capture geometry,
marker regex and tool/timeout overrides. Existing discovery fills omitted paths.
ScenarioRunner and Checkpoints remain authorities; explicit game_speed1 required.
Copies and hashes exact script/route inputs; validates deployed build runtime;
records checkpoint identities, source before/after and final input identity.

Owned Linux behavior: canonical Git-common-root shared live-game flock; refuse
existing K1; stage/prefix must be new/empty or carry matching runner ownership
sidecars (no broad force/adopt bypass). Source/build/stage/prefix/run overlap
refused. Writable trees and Override materialized privately before runtime
writes, including nested symlinks. Game PID filtering requires both exact
WINEPREFIX and staged cwd. Recorder stopped before GameSession teardown/Xvfb,
including boot-exception path. CLI SIGTERM reaches owned cleanup. Reused owned
logs are truncated before launch with prior identities retained, never source
logs; native marker watcher also retains its initial byte offset.

Measured live harness defects addressed in creative adapter: sync_cursor takes
one status.events_seq watermark, not64 drains until an impossible empty event
ring. Continuous-producer regression verifies one status query and no events
calls; post-watermark events remain eligible for inherited waits. Current-run
log regression excludes prior lines, records new lines and rejects truncation
after mark_log. Optional mark_log/await_log/advance_ticks helpers reuse do TOML
syntax and watchdogs; no Lua dialect added.

Recording starts on configured owned Xvfb display/screen before game launch;
12fps continuousMP4; ffmpeg decoder/encoder max2threads, GIF filter1thread.
First fresh non-arming creative native marker is timestamped relative to
monotonic recorder startup. Up-to10s MP4/GIF uses1s lead-in where possible.
Missing marker fallback is explicitly marked for visual review. Capture timing
records100ms polling and uncalibrated startup latency; not frame-exact proof.
Outputs probed for dimensions/duration and hashed. Media failure is separate
from route failure; failed route continuousvideo/log/report are preserved.
No139-predicate or all-example live status is promoted by media generation.

Tests:19 offline unittests PASS. Cover source alias/nonempty ownership refusal,
private source-preserving symlink materialization, exact PID scope, recorder
cleanup before parent teardown even on exception, current-run log reset,
actual800x600 display command, owned SIGINT and forced-stop escalation,
fresh marker timing/arming exclusion/fallback, invalid zero-duration rejection,
failed-route media refusal, thread-bounded render/identities, one-watermark
continuous event producer, marked log epoch, unsupported mac pre-mutation,
script basename/input validation, driver success/provenance, route-failure raw
video retention, media/route failure separation, and source-change invalidation.

Validation commands:
- /usr/bin/python3 tools/kpharness_creative_test.py:19/19 PASS.
- PYTHONPATH=scripts/harness /usr/bin/python3 -m kpharness.creative --backend
  macos-k1 --script showcase/30_battle_meditation.lua --route unused:
  expected exit2 unsupported JSON, without examining route or creating files.
- cmake -S . -B /home/brunner56/kp-validation-20260922-build:configure only.
- ctest --test-dir /home/brunner56/kp-validation-20260922-build -R
  '^(kpharness_creative_test|example_validation)$' --output-on-failure.
- git diff --check; git diff --exit-code89c9999 -- scripts/examples.

Limitations/independent-review focus: no packaged live run yet; controller owns
that proof after review. Current executable adapter is K1/Wine only; macOS is
explicitly unsupported. Source preservation scope excludes immutable bulk game
assets. Native-log marker timing is selection guidance and clips still require
visual review. Unmarked prior prototype stage/prefix reuse is refused; use fresh
private paths. Existing route failures are not automatically example defects.

Task4 commit: da1fce3 (Package creative routes with scoped capture and media receipts).
Integrated CTest result: creative19-case gate PASS0.45s; existing example gate
PASS1.05s,2/2 total1.50s. Other controller-owned plan/research edits preserved.

## Review fix round 1 (base ebcbc19)

Addressed both findings in /tmp/kp-task4-review.md.

P1: Resolve effective checkpoint root before lock acquisition, ownership claims,
run directory creation or session boot. Reject overlap with source, stage, prefix,
build or run directories, and validate all declared save/load checkpoint names.
New creative_checkpoints.py subclasses existing Checkpoints: actual inherited
store/restore copy/delete operations are retained, with bounded destination and
root-identity checks, name traversal refusal, and symlink refusal. Restore metadata
cannot redirect writes outside the owned saves root. Existing general checkpoint
API is unchanged. Tests cover all four requested protected roots before boot,
preflight symlink escape, actual successful store/restore, symlink destination
refusal and malicious restore metadata while retaining a protected source asset.

P2: Track recorder/session cleanup completion independently. Preserve cleanup
errors across retries; retry unfinished operations only and continue attempting
session teardown after recorder failure. Driver-level boot failure regression
uses the real creative teardown against a mocked parent teardown that fails once
then succeeds; persisted creative-run.json still reports cleanup failed and does
not render/promote success. Recorder teardown ordering remains covered.

Validation (no games or builds):
- /usr/bin/python3 tools/kpharness_creative_test.py: 23 tests passed.
- ctest --test-dir /home/brunner56/kp-validation-20260922-build -R '^kpharness_creative_test$' --output-on-failure: 1/1 passed.
- git diff --check: clean.

Files: creative.py, creative_wine.py, new creative_checkpoints.py,
kpharness_creative_test.py and docs/creative-runner.md. No Task5 implementation,
example-byte changes, controller research docs, live files or runtime build changes.

Self-review: checks are preflight plus operation-time path resolution, not an
OS-level defense against a concurrent hostile filesystem writer swapping paths
between check and copy. Shared serialized harness lock prevents cooperating
creative sessions racing each other; source directories remain outside writable
checkpoint roots. Cleanup receipt intentionally stays failed after a successful
retry to retain the original fault history. Live proof remains controller-owned.

## User capture-cadence steering

After the review-fix commit, added --capture-fps (integer 1..120), default60,
propagated to actual X11 capture -framerate without interpolation. Recorder also
validates direct API input. Existing two-thread limit remains. Media probe records
encoded nominal/average frame rate and count, explicitly marks actual game render
cadence unvalidated; docs explain duplicate frames and the independent cadence /
visual review needed. MP4 keeps source cadence; GIF remains explicitly8FPS preview.
Full video is retained; no good-advertisement claim follows from route success.

Validation: 24 offline tests passed; kpharness_creative_test CTest1/1 passed;
git diff --check clean. Mock command test covers default60 and selected30FPS,
invalid bounds/type rejection and CLI-to-driver recorder propagation. No actual
60FPS capture or game render cadence proof was performed by this worker.
