# Creative route runner and media

`kpharness.creative` packages one creative route, its exact Lua inputs, an owned
session, continuous capture, and a representative MP4/GIF. It reuses
`GameSession`, `ScenarioRunner` and `Checkpoints`; it does not add an engine API
or a second route format. The ten cursed and six showcase examples remain the
current creative inventory. Their Lua bytes are unchanged by this runner.

Platform selection is explicit. `linux-wine-k1` is the implemented host adapter.
`macos-k1` and `macos-k2` currently return a structured unsupported result before
creating files, staging, or launching anything. Native macOS launch, memory
bindings and capture need their own validated adapter. Route execution, input
identity, independent readback artifacts, clip selection and receipt structure
are reusable across those backends; macOS is not treated as Wine.

Run one existing route with its matching example:

```sh
PYTHONPATH=scripts/harness /usr/bin/python3 -m kpharness.creative \
  --backend linux-wine-k1 \
  --script cursed/10_rancor_roulette.lua \
  --script probe/00_probe.lua \
  --route scripts/harness/scenarios/cursed/10_rancor_roulette.toml \
  --build-dir /path/to/build \
  --source /path/to/kotor-install \
  --staged /path/to/creative-stage \
  --wineprefix /path/to/creative-prefix \
  --checkpoint-root /path/to/checkpoints/k1 \
  --output /path/to/creative-runs
```

`--script` is repeatable and accepts example-relative names or explicit `.lua`
paths, including a reviewed readback observer. Deployed basenames must be unique.
`--route` accepts any existing ScenarioRunner TOML file or scenario name. It must
explicitly set `game_speed=1.0`; creative recording does not silently alter a
route's speed. `--target` optionally checks consistency with its target.

Build and source discovery use the existing harness rules when their flags are
omitted. Output defaults to `tmp/creative-runs`; stage and Wine prefix default
to owned sibling directories there. Checkpoint discovery retains the existing
target-specific default. `--width`/`--height` set both the Xvfb session and capture
geometry (default1024×768). `--ffmpeg`, `--ffprobe`, `--boot-timeout` and `--marker`
are explicit overrides. A missing runtime or media tool fails before launch.

## Ownership and preservation

The Linux adapter holds the canonical repository's existing
`tmp/harness-locks/live-game.lock`, including when invoked from a worktree. A
second live runner fails promptly. Existing K1 processes cause refusal; they
are not stopped. Each run allocates its own Xvfb rather than borrowing a user's
display. Game process teardown requires both the exact Wine prefix and exact
staged working directory; Wine-server shutdown uses that private prefix.

Stage and prefix must be empty/new, or carry this runner's matching ownership
sidecar from an earlier run. A nonempty unmarked prototype directory is refused;
there is no force/adopt bypass. The controller can use fresh private paths for
packaged verification. Source, build, stage, prefix and run output are checked
for unsafe aliases/overlap before staging. Writable directories and Override
are materialized privately, including nested symlinks, before runtime writes.
Only the runner-owned script directory is replaced.

Source preservation receipts hash the executable, INIs, runtime/proxy files,
logs, saves, Override and source Lua scripts before/after. Immutable bulk game
assets are not rescanned. Route, input scripts, build runtime and referenced
checkpoint files have their own identities. Scripts and route are frozen in
`run/sources/` and `executed-route.toml`; deployment and selected runtime bytes
are checked. Unexpected source or input changes prevent overall success.

Only the owned recorder process receives a stop signal. Recording is finalized
before game/Xvfb teardown, including boot exceptions, route failures and service
SIGTERM. Failed runs retain their continuous video and native/driver logs for
diagnosis. Stage log files are truncated only inside the owned tree before
launch; their prior sizes/hashes are recorded. Source logs are preserved.

## Existing TOML plus three observation helpers

Ordinary ScenarioRunner steps retain their behavior. The creative runner adds
three bounded helpers using the same `do` syntax:

```toml
[[step]]
do = "mark_log"

[[step]]
do = "await_log"
pattern = '\[meditation\] round 1: steadied 3'
minimum = 1
maximum = 1
 timeout = 20

[[step]]
do = "advance_ticks"
ticks = 200
timeout = 120
```

`mark_log` records the current native-log byte offset. `await_log` reads only
subsequent lines, rejects truncation after the mark, and stores the matching
lines. Minimum/maximum bounds apply to the observed snapshot; a zero minimum is
not a timed proof of silence. `advance_ticks` waits for measured server ticks,
not a wall-clock sleep, and fails on tick reset or watchdog verdict. Helper
waits retain the existing watchdog and are bounded to600seconds.

Before each action the creative runner takes **one** `status.events_seq`
watermark. It does not drain until the event ring becomes empty. A probe can
produce continuously; repeated draining previously delayed a six-second effect
check by about12seconds. Events after the snapshot remain available to the
inherited event waits. Unsupported/malformed watermark responses fail explicitly.

## Video selection and result interpretation

Continuous `continuous.mp4` recording begins on the owned display before game
launch and lasts through the route. Capture uses the session's configured
screen,12fps and at most two ffmpeg encoding threads. A watcher records the first
fresh creative native-log marker and its monotonic time relative to recorder
startup. Arming and "beat drops" announcements are excluded by default. The
marker receipt records exact text and timing uncertainty:100ms log polling plus
uncalibrated recorder startup latency. It is a selection hint, not frame-exact
proof of effect onset.

For a successful route, the runner extracts up to10seconds around that marker,
including one second of lead-in where available, into `representative.mp4` and
`representative.gif`. If no marker arrives, it explicitly labels a final-interval
fallback for visual review. A reviewer must inspect the clip; it is not silently
certified as showing a defining effect. Both outputs are probed for usable video
geometry/duration and hashed. The continuous source video's identity, clip
start/length, marker and review requirement are saved in `media.json`.

`creative-run.json` separately records route, media and cleanup status, source
preservation and input identities. Exit0 requires every route step to pass
without skips, valid media, clean teardown and unchanged source/input bytes.
Exit1 means execution/artifact acceptance failed; exit2 is preflight refusal.
A failed media encoder does not relabel a passed route. A failed route remains a
route/control observation, not an automatic Lua-script defect. Its raw
`report.json`, copied TOML, current native logs, driver log and continuous video
remain available.

This receipt does **not** mark all139 example live obligations passed. Importing
full example acceptance remains a separate reviewed operation described in
[example validation](example-validation.md). Independent engine readbacks and
visible evidence are still required for each concrete claim.

Host-only regression gate:

```sh
/usr/bin/python3 tools/kpharness_creative_test.py
ctest --test-dir /path/to/build -R kpharness_creative_test --output-on-failure
```

The writable checkpoint root is resolved during preflight and must be disjoint
from source, stage, Wine prefix, build and run directories. Declared checkpoint
destinations are checked before ownership claims or boot. The creative checkpoint
adapter rechecks destinations during store/restore, rejects escaping symlinks and
save-folder traversal, and delegates valid copies to the existing checkpoint code.
Use a separate checkpoint directory even for routes that currently only load saves.

Cleanup tracks recorder and session completion separately. A boot-time cleanup
failure remains a failed cleanup receipt even if a later retry releases the
remaining owned resources; completed operations are not repeated. Retained raw
video and the cleanup error remain available for diagnosis.
