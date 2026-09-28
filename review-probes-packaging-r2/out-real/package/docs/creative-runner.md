# Creative route runner and media

## Capture backends

`--backend linux-wine-k1` is the existing owned-Xvfb software path. It retains
root-display capture and does not constitute GPU or exact-window proof.

`--backend linux-wine-k1-gamescope` is the Linux K1/Wine GPU candidate. It
creates a private headless Gamescope process group and nested Xwayland server,
proves a direct accelerated non-software renderer, freezes one PID/start-owned
game window, proves that it covers the private display at `0,0`, and records
that exact window with `-window_id`. Recording starts after the first mapped window
and first-frame admission; teardown is recorder, game/Wine, then
the recorded Gamescope group. The backend refuses caller display reuse,
Crostini, missing dependencies or render devices, malformed/foreign nested
authority, ambiguous windows, resize/replacement, and recorder/display death.

## Gamescope driver provenance

Before any live attempt, materialize the exact Python harness closure into a
new empty directory. This copies only checked harness `.py` modules; it does
not copy the K1 install, saves, Wine prefix, built runtime/proxy, media, or
other retail assets.

```sh
PYTHONPATH=scripts/harness /usr/bin/python3 -m kpharness.gamescope_snapshot create \
  --source-root scripts/harness --snapshot /safe/task7-gamescope-harness
PYTHONPATH=scripts/harness /usr/bin/python3 -m kpharness.gamescope_snapshot verify \
  --snapshot /safe/task7-gamescope-harness --source-root scripts/harness
```

Creation records a canonical, sorted module list and SHA-256 for the full
static import closure of `kpharness.creative` and its Gamescope support. It
hashes the source before and after copying and refuses a source change. The
second command also rejects an added, removed, or changed source module. Keep
the resulting `gamescope-harness-manifest.json` beside the live receipt.

Run the driver through the materialized snapshot, rather than through a dirty
checkout:

```sh
PYTHONPATH=scripts/harness /usr/bin/python3 -m kpharness.gamescope_snapshot driver \
  --snapshot /safe/task7-gamescope-harness -- --backend linux-wine-k1-gamescope \
  --cleanup-commitment-log /operator/owned/commitments.log ...
```

The Gamescope backend refuses to create a run directory without an existing
commitment log outside it. The first line it prints for the run is the launch
head (`"event":"run_initialized"`), written before any child starts.

The driver validates the copied manifest and every copied module before it
starts a subprocess whose only harness `PYTHONPATH` is the snapshot's
`runtime/`. It deliberately does not re-read the original worktree at launch;
use `verify --source-root` when source-to-snapshot equality itself is required.
The run directory retains `gamescope-lease.json` from before the first
Gamescope child is spawned. It atomically records the run ID, sanitized argv,
leader PID/start/PGID/session, then readiness-child PID/start/display once
known, and it remains after every boot or cleanup failure. Each atomic rewrite
retains the prior numbered monotonic/UTC phase events, so a forensic reader can
audit the prepared, spawn, readiness, failure, and cleanup sequence. No
Xauthority path, cookie, or environment dump is recorded.

GNOME and KDE and the host's X11 or Wayland session are detection facts. They
do not mean the game is controlled through native Wayland. This adapter is
admitted only through its separately owned Gamescope/Xwayland authority.
Native/shared Wayland, Windows, macOS, ChromeOS, K2, and native Linux remain
refused or unimplemented until each has its own process, window, real-input,
capture, renderer, cleanup, and installed-game acceptance.

Gamescope runs write schema 2. The receipt cross-checks adapter, lease,
PID/start, window, display, actual geometry, FFmpeg argv, physical-console
correlation, media, preservation, and cleanup. Requested/encoded FPS,
duplicate/drop diagnostics, the content gate, and visual review remain
separate. Every run ends with visual review pending and `ok=false`; a valid MP4
or route alone is insufficient. After reviewing the completed unaltered master,
bind the decision to its recorded digest with the separate command:

```sh
PYTHONPATH=scripts/harness python3 -m kpharness.creative_accept RUN_DIR \
  --reviewer "REVIEWER" --media-sha256 "SHA256_FROM_THE_REVIEWED_FILE" \
  --route-sha256 "SHA256_RECORDED_FOR_THE_SELECTED_ROUTE_BEFORE_LAUNCH" \
  --ffprobe-sha256 "SHA256_RECORDED_FOR_THE_CONFIGURED_FFPROBE_BEFORE_LAUNCH" \
  --cleanup-ledger-sha256 "LAST_HEAD_THE_TOOL_PRINTED_FOR_THIS_RUN" \
  --cleanup-commitment-log /operator/owned/commitments.log
```

Never hash `ffprobe-cleanup-ledger.json` at review time to get the
`--cleanup-ledger-sha256` value. That file is the thing under attack. Use the
last head the tool printed for this run. Copy each printed head line out of
band as it appears, for example into a note on another account or host.

The trust root is that captured output, not the log. The tools never read the
commitment log back. The log anchors the head only if whoever can write the run
directory cannot rewrite the log: keep it under another account, make it
append-only (`chattr +a`), or ship it off the host. A same-user log is a
convenience copy. A same-user writer who forges the ledger can also append a
forged head line to it. When the captured head and the log disagree, trust the
captured head.

The acceptance command ignores the serialized `acceptance_ready` convenience
field and recomputes readiness from the completed schema-2 evidence: start and
finish timestamps, platform admission, Gamescope PID/start/group/renderer,
window PID/start/lease/geometry, effective FFmpeg arguments, route report and
physical-console correlation, continuous media, preservation, and ordered
component cleanup. It then checks the artifact location and both recorded and
reviewer-supplied media digests. The acceptance record stores reviewer, time,
scope, media digest, and a canonical digest of the completed execution receipt.
That digest excludes only review-derived fields (`visual_review`, `ok`, and the
cached readiness value), avoiding a self-reference while allowing later
execution-evidence changes to be detected with `verify_acceptance()`.

Each Gamescope run starts with `ffprobe-cleanup-ledger.json`. The empty ledger
holds a random per-run nonce, so no two runs share a launch head. Its
exact-schema records form a digest chain that starts at that launch head. A
retained FFprobe child appends a failure record. Acceptance and export stay
blocked until that exact failure is resolved.

The head must come from outside the run directory. Before launch, create an
empty commitment log outside the run directory and pass it with
`--cleanup-commitment-log`. The tools refuse a missing log, a symlink, a
hard-linked file, or a path inside the run directory. They also compare the
device and inode of the log and of each parent directory with every inode in
the run tree. That refuses a bind mount of the run directory, of one of its
subdirectories, or of a file inside it. The tools re-validate the log before
every append. Limits: an alias created after the check, a mount the process
cannot stat, and a log on storage the run-directory writer controls in another
way are not detected. Every ledger change prints one JSON line to stderr and
appends the same line to the log:

```json
{"cleanup_ledger_sha256":"...","event":"acceptance_failure","failure_id":"...","kind":"kpharness.cleanup-ledger-head.v1","nonce":"...","run_dir":"...","sequence":1,"utc":"..."}
```

The events are `run_initialized` (printed before any child starts),
`acceptance_failure`, `signal_error_reaped`, and `recovery_resolution`.
A failed acceptance also prints `{"ok": false, "failure_id": ..., "cleanup_ledger_sha256": ...}`
on stdout and exits nonzero. Always pass the last head for this run's nonce.
Never recompute it from the ledger file at review time. With that head, a
rollback to an empty ledger, a restore of the launch bytes, a forged failure and
resolution pair, or a deleted ledger all fail closed.

Appends hold an exclusive lock on the run directory and recheck the supplied
head under that lock. Two concurrent commands on one run cannot both extend the
same head. The ledger must also be canonical JSON: exact integer types, no
duplicate keys, and one timestamp form (`YYYY-MM-DDTHH:MM:SS.ffffff+00:00`).
A resolution may not predate its failure.

Recovery is Linux-only. It signals through a held pidfd after checking the
recorded PID start identity. It never signals a bare numeric PID. Run it with
the last emitted head and the failure ID:

```sh
PYTHONPATH=scripts/harness python3 -m kpharness.creative_accept RUN_DIR \
  --recover-cleanup FAILURE_ID \
  --cleanup-ledger-sha256 "LAST_HEAD_THE_TOOL_PRINTED_FOR_THIS_RUN" \
  --cleanup-commitment-log /operator/owned/commitments.log
```

Successful recovery prints and logs the new head. Use that head for acceptance.
Each failure records the boot ID and PID-namespace identity. Recovery from
another boot or PID namespace refuses rather than treating a missing `/proc`
entry as an exit. A different start time at the recorded PID proves the
original child exited, so recovery records `original_exited_pid_reused` and
sends no signal. Missing pidfd support, unreadable process identity, a changed
identity while the pidfd is held, or an unbounded survivor leaves the failure
unresolved. A surviving child whose start identity could not be read is
recorded as `identity: unavailable`. That failure can never be resolved, so the
run stays blocked.

Gamescope capture creates no representative MP4 or GIF before this acceptance.
After acceptance, export a reviewed interval from the unchanged master:

```sh
PYTHONPATH=scripts/harness python3 -m kpharness.creative_export RUN_DIR \
  --route-sha256 "SHA256_RECORDED_FOR_THE_SELECTED_ROUTE_BEFORE_LAUNCH" \
  --ffprobe-sha256 "SHA256_RECORDED_FOR_THE_CONFIGURED_FFPROBE_BEFORE_LAUNCH" \
  --cleanup-ledger-sha256 "LAST_HEAD_THE_TOOL_PRINTED_FOR_THIS_RUN" \
  --start-seconds 12.5 --end-seconds 32.5 --gif-fps 25
```

Pass the same captured head you used for acceptance (or the newer one a later
recovery printed). Do not copy it from `creative-run.json`: the run directory is
the thing under attack.

The times above are examples. Choose actual frame-reviewed boundaries that
include a calm normal lead-in, every defining phase and transition, restoration,
and a calm restored lead-out. For a size-change sequence, retain at least two
seconds before the first change and two seconds after normal size returns.
Do not infer the end from the first log marker or shorten the effect to fit a
fixed clip length. Start/end must be finite and satisfy
`0 <= start < end <= master duration`; out-of-range requests fail without an
encoder call rather than silently truncating. GIF FPS is an integer from 1 to
60 (default 25); actual smoothness and readability still require review.

The exporter reloads the current schema-2 acceptance and verifies the actual
master digest before encoding. Pending, rejected, or changed evidence cannot
export. MP4 and GIF use identical source bounds. Outputs are staged privately,
probed for complete duration, and published only after the accepted receipt
and master verify again. Each export creates a new `accepted-media-<id>`
directory with `representative.mp4`, `representative.gif`, and `export.json`.
The sidecar binds the master SHA-256, accepted execution digest, accepted receipt
digest, interval, settings, and output hashes. Export never changes the master
or accepted execution receipt; failure publishes no accepted derivative sidecar.
The MP4 is scaled to 640 pixels wide and preserves source timestamps; the GIF
is 480 pixels wide at the selected rate. Review these smaller outputs for
readability. Exporting cannot repair failed source cadence or framing.
`--ffmpeg` and `--ffprobe` override the export tools without launching a game.
If exporting from a frozen harness snapshot, include `kpharness.creative_export`
as a snapshot entry; a capture-only dependency snapshot may omit this separate command.

The host-only lifecycle gate is:

```sh
python3 tools/kpharness_gamescope_backend_test.py
ctest --test-dir /path/to/build -R kpharness_gamescope_backend_test --output-on-failure
```

It starts no game, Wine, Xvfb, Gamescope, or FFmpeg process and is not live GPU
or visual proof.

`kpharness.creative` packages one creative route, its exact Lua inputs, an owned
session, and continuous capture. Legacy Xvfb runs also generate representative
MP4/GIF previews automatically; Gamescope exports follow visual acceptance. It reuses
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
geometry (default1024×768). `--ffmpeg`, `--ffprobe`, `--boot-timeout`, `--marker`,
`--capture-marker`, `--cadence-start-marker`, and `--cadence-end-marker` are
explicit overrides. A missing runtime or media tool fails before launch.

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
not a timed proof of silence. `advance_ticks` waits for measured server ticks by default. Set `clock = "client"`
to require client tick progress instead; `"server"` is the only other accepted
value. It fails on tick reset or watchdog verdict. Helper
waits retain the existing watchdog and are bounded to600seconds.

Before each action the creative runner takes **one** `status.events_seq`
watermark. It does not drain until the event ring becomes empty. A probe can
produce continuously; repeated draining previously delayed a six-second effect
check by about12seconds. Events after the snapshot remain available to the
inherited event waits. Unsupported/malformed watermark responses fail explicitly.

## Video selection and result interpretation

Continuous `continuous.mp4` recording begins on the owned display before game
launch and lasts through the route. Capture uses the session's configured
screen,60fps by default and at most two ffmpeg encoding threads. A watcher records the first
fresh creative native-log marker and its monotonic time relative to recorder
startup. Arming and "beat drops" announcements are excluded by default. The
marker receipt records exact text and timing uncertainty:100ms log polling plus
uncalibrated recorder startup latency. It is a selection hint, not frame-exact
proof of effect onset.

For a successful legacy Xvfb route, the runner extracts up to10seconds around that marker,
including one second of lead-in where available, into `representative.mp4` and
`representative.gif`. If no marker arrives, it explicitly labels a final-interval
fallback for visual review. A reviewer must inspect the clip; it is not silently
certified as showing a defining effect. Both outputs are probed for usable video
geometry/duration and hashed. The continuous source video's identity, clip
start/length, marker and review requirement are saved in `media.json`.
Gamescope retains the master for acceptance and uses the explicit post-accept
export interval described above instead of this automatic ten-second selection.

`creative-run.json` separately records route, media and cleanup status, source
preservation and input identities. For legacy Xvfb, exit0 requires every route step to pass
without skips, valid media, clean teardown and unchanged source/input bytes.
Exit1 means execution/artifact acceptance failed; exit2 is preflight refusal.
Gamescope capture exits with `ok=false` while visual review is pending; its
separate acceptance and export commands report their own results.
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

Capture defaults to `--capture-fps 60`; choose an integer from 1 through 120 to
match host capacity. This sets X11 acquisition frequency, with no interpolation
or synthetic motion smoothing. Capture and encoding remain limited to two
ffmpeg threads. The representative MP4 preserves source cadence. The legacy
automatic GIF is an 8 FPS lightweight preview, not the smooth showcase deliverable;
the Gamescope post-accept exporter defaults to 25 FPS and accepts `--gif-fps`.

Requested capture FPS and encoded stream FPS are different from actual game
render cadence. `capture.json` records sampling settings; media probes record
encoded average/nominal frame rate and frame count. These can contain duplicate
game frames. The Gamescope adapter fails closed on encoded-source cadence inside
the configured named-marker interval. A content gate also rejects a black first
acceptance frame and static acceptance intervals. Visual review is still required. A clip is not automatically a good
advertisement because its route passed: review framing, immediate visible effect,
phase readbacks and restoration before selecting footage for a short-form video.
The complete recording remains the evidence source.

### Gamescope window capture, geometry, content, and cadence gates

Gamescope starts Xwayland rootless. A rootless root window has a 0x0 screen
pixmap and an empty visible region. Root `ShmGetImage` therefore returns
all-black frames at full cadence without an error. The recorder refuses root
capture with the typed failure `capture_target_rootless_root` whenever the
lease's Xwayland argv has `-rootless` or cannot be read. It refuses root capture
on any other Gamescope lease as `capture_target_unsupported`. Receipts that
claim root capture never pass verification. Legacy Xvfb capture keeps its
existing root behavior.

The recorder captures the same immutable, PID/start-bound game window used for
input, with `-window_id`. Before FFmpeg starts it runs `xwininfo -id WINDOW`
and `xwininfo -root`. It records map state, absolute origin, size, border
width, and root size. It then applies the exact `ShmGetImage` window checks
from `Xext/shm.c`. The window must be viewable. The grab rectangle must lie
inside the screen and inside the window border. The window and root must also
equal the lease geometry at origin `0,0`. `xwininfo` reports the outer corner,
so the border width must be zero for that corner to be the content origin. The
recorder reads the geometry again immediately before exec. A refused read fails
as `capture_geometry_precondition` and a changed read fails as
`capture_geometry_changed`, with no FFmpeg process. Both reads are stored as
`capture.geometry_precondition`, and verification recomputes the conditions
from the recorded values. The 250 ms watch and both stop-time checks compare
later reads with the frozen pre-exec geometry. The input uses `-draw_mouse 0`.
The command has no FPS filter, CFR interpolation, `-r`, `-vsync`, `-fps_mode`,
or `setpts` rewrite.

The content gate runs before any cadence verdict can pass. After the master is
final, the configured FFprobe decodes every frame through
`-f lavfi -i movie=/proc/self/fd/N,signalstats`, reading the master only through
an inherited descriptor. The rows go to `ffprobe-content.json`, which is hashed
and bound to the master like the PTS artifact. The black check applies to the
first frame at or after the acceptance-start marker. That frame fails as
`capture_content_black` unless its luma maximum is above the policy's black
threshold and above its luma minimum (nonzero variance). Black startup frames
before the marker are recorded in `content.startup` as evidence only. Inside
the acceptance interval, a frame counts as distinct only when the largest of
its Y, U, and V differences from the previous frame is above the policy's
`distinct_noise_floor`. Zero distinct frames, or a distinct ratio below the
policy minimum, fails as `capture_content_static`. Content rows must match the
canonical PTS frame count. Thresholds come from a fixed table in
`display_backends.CONTENT_POLICIES`, never from the receipt:

| Policy | Black luma max | Noise floor | Minimum distinct ratio |
| --- | --- | --- | --- |
| `animated-diagnostic-v1` | 24 | 1.2 | 99% |
| `game-capture-v1` | 24 | 0 | 5% |

The master is lossy (`libx264 -preset ultrafast -crf 28`). A repeated source
frame is coded against the previous reconstruction, so it decodes with small
nonzero differences. The diagnostic floor was calibrated in round 11 with the
production probes on synthetic `testsrc2` encodes that use the recorder's exact
codec settings. Across 2,220 duplicate frames (sources at 6, 15, 20, 30, 45,
and 59 FPS repeated to 60) the largest difference was 0.76. Across 2,813 fresh
frames it was never below 1.89. The floor 1.2 leaves a factor of 1.58 on both
sides. It holds for the diagnostic's full-frame `testsrc2` pattern only: plain
`testsrc` fresh frames measured as low as 0.13.

The game policy keeps a zero floor, so its ratio is an upper bound on real
change. Encoder refinement after one real change counts too. A still frame with
an 8x8 box blinking twice a second scores about 5 to 7% and passes the game
policy, while it fails the diagnostic. A passing game ratio therefore shows that
something moved. It does not prove full-frame capture, and it does not rule out
partly censored frames. The diagnostic, which requires 99% distinct frames over
a full-frame pattern, is the check for that. Acceptance probes content again over the same retained media and
tool descriptors and requires the exact rows. The visual review signs
`content_artifact_sha256` and `geometry_precondition_sha256`. Verification and
export check both, and the export sidecar records them.

Startup uses FFmpeg's machine-readable `-progress` output through an inherited
descriptor; FFmpeg never reopens a caller-visible progress pathname. Within five seconds it
must receive a complete progress block with at least one frame and find the
regular, non-symlink MP4 inside the run directory. `ffmpeg.log` is scanned from
startup through orderly stop for both `Cannot get the image data` and
`Continuing without shared memory`. Because FFmpeg provides no affirmative SHM
confirmation, successful evidence is named `no_fallback_observed`. Either string,
malformed progress, an exited recorder, a lost lease, invalid output, or timeout
prevents route execution. Startup cleanup signals only the recorder's owned
FFmpeg process with SIGINT, waits two seconds, then kills and waits two seconds
if needed. The partial MP4, log, progress log, and `capture-failure.json` remain.
Diagnostic reads are capped, retain incomplete-progress limits, and fail if a
log is truncated or its device/inode identity changes. FFmpeg writes the master
through an inherited descriptor for a random mode-0700 staging directory. After
the owned process is proven stopped, the recorder publishes that exact regular
inode with an exclusive hard link; it never follows or overwrites an existing
`continuous.mp4` symlink or pathname.
The schema records versioned descriptor roles for the progress regular file and
private output directory. Both descriptors must be nonstandard, distinct, and
match the descriptor numbers in the exact FFmpeg command.

`--capture-marker NAME=REGEX` is repeatable. Names must match
`[a-z][a-z0-9_]{0,31}`, names are unique, and every regex is compiled during
preflight before a run directory or game resource is claimed. `--marker` remains
the `effect_start` alias. Configure the measured window with
`--cadence-start-marker NAME --cadence-end-marker NAME`. Each first complete
matching log line records its byte end, shared-process monotonic capture time,
100 ms polling interval, and 100 ms uncertainty. Missing, duplicate, or reversed
required markers fail cadence. Marker reads run at 100 ms independently of the
250 ms window/lease identity verification cadence. Stop performs a synchronous
final log drain and window geometry check before SIGINT, followed by another
binding check after FFmpeg finalization. Markers observed in one poll retain
strict byte/sequence order with nondecreasing timing instead of inventing
different timestamps.
When ordered start and end lines arrive in one poll, the interval uses their
byte order and adjacent 100 ms uncertainty bounds, so it remains measurable
without claiming a false zero-length interval.

After orderly MP4 finalization, the adapter retains `ffprobe-cadence.json` and
measures source PTS for the whole capture, route interval when available, the
configured acceptance interval, and consecutive named-marker intervals. The
probe artifact is bounded to 250,000 frames and 16 MiB, names the exact master
path and SHA-256, and has its own SHA-256 in execution evidence. Readiness and
export reopen and verify that artifact and master. Visual acceptance also runs
a fresh bounded probe against a private copy made from one retained `O_NOFOLLOW`
master descriptor. The copy is reopened read-only, verified while it has exactly
one link, unlinked, and passed to FFprobe only as `/proc/self/fd/N` with that FD
explicitly inherited. Its identity includes device, inode, size, mtime, ctime,
and link count. Acceptance hashes and checks that same zero-link descriptor after
the probe, brackets the operation with public-master identity/digest checks, and
requires the exact ordered PTS list
before signing the artifact digest into the review record. FFprobe output is
read incrementally through a nonblocking pipe and the child is terminated and
reaped with bounded waits if output crosses 16 MiB, times out, fails, or yields
invalid timestamps. Each FFprobe deadline scales with the frames it decodes:
30 s plus 0.2 s per frame, capped at 3,600 s. The recorder sizes it from the
terminal FFmpeg frame count, and acceptance from the recorded PTS frame count.
An unreaped child is retained in a typed cleanup failure. Before the acceptance
CLI exits, that path appends one failure record to the single
`ffprobe-cleanup-ledger.json` chain. The record is written first, under the
ledger lock, before and independently of any commitment-log check. If another
transition moved the head during the probe, the record still goes onto the
current valid chain. The record holds the exact PID/start identity, boot and
PID-namespace identity, command, tool identity, bounded waits, and recovery
requirement. The CLI prints the head line and one
`kpharness.ffprobe-survivor.v1` line with the survivor's PID, start identity,
and command to stderr. It then tries to append the head to the log, prints the
failure ID and head on stdout, and exits nonzero. If the log was deleted,
rotated, or hard-linked during the probe, the ledger still holds the failure and
the gate stays blocked. Only the log copy is missing, and the survivor line
names the log error. If the ledger itself cannot take the record (lock timeout
or a malformed ledger), the CLI writes an exclusive
`ffprobe-cleanup-unrecorded-*.json` file in the run directory instead. Any such
file blocks acceptance and export permanently. Every unresolved or malformed
ledger entry blocks acceptance, verification, and export. Recovery is explicit and uses the
`--recover-cleanup` command shown earlier, with the last emitted head and the
commitment log. It appends a resolution and never removes the original failure.
The producer records the configured FFprobe command, resolved regular-file path,
and executable SHA-256. Acceptance opens and hashes that native ELF executable,
retains the verified inode, and invokes `/proc/self/fd/N` with the executable FD
in `pass_fds`; scripts and unsupported executable formats fail closed. The same
tool descriptor and public tool identity are rechecked after the probe.
Acceptance compares the retained descriptor to the independently supplied
configured FFprobe SHA-256, signs it into visual review, and requires the same
explicit digest during verification and export. Coherent replacement of all
run-local tool and PTS evidence cannot replace this external commitment.
The whole-capture summary is the exact canonical list, and every named or route
interval is the exact inclusive projection of that list.

The configured marker order and regexes are serialized. A complete receipt has
exactly the configured consecutive marker-pair intervals plus one acceptance
pair; invented, omitted, extra, or duplicate markers and pairs fail closed.
When route capture-clock bounds exist, route cadence must match those bounds and
the same canonical PTS projection; otherwise route cadence is omitted.

The acceptance interval requires at least 99% of requested cadence, no more than
0.5% missing or dropped slots, a maximum inter-frame gap of 50 ms, zero FFmpeg
duplicates, terminal progress diagnostics, and continuous
`no_fallback_observed` evidence. Capture and cadence remain separate receipt
statuses; route success cannot turn either green. Failed runs retain the master
as `retained_failure_recording`, and representative success media is suppressed.
The acceptance gate recomputes interval metrics from serialized PTS, verifies
the cumulative FFmpeg samples surrounding the markers and their counter deltas,
and requires a passed capture gate plus a complete route with passed predicates
and steps. Acceptance verification and export repeat that recomputation. The
route result is bound to the actual run-local `report.json`: readiness opens a
bounded regular non-symlink file, checks its exact SHA-256 and canonical
ScenarioRunner schema, and requires the duplicated ordered steps to match it.
It also opens and verifies the recorded device/inode/size/mtime/ctime/link identity
and digest of `executed-route.toml`, parses that exact byte sequence, and binds the
report to its K1 target, scenario name, ordered step descriptions, build/profile
identifier, and current K1 runtime artifact hashes. Route execution metadata has
only the finite, non-boolean requested/effective/restored-or-retained speed fields,
with their required consistency relationships.
Requested and effective speed must also equal the parsed route's configured
`game_speed`; internal agreement at a different speed is insufficient. Acceptance
and every later verification/export require the independently supplied selected
route SHA-256. That value is signed into the visual review and cannot be derived
from mutable run-local evidence by these commands.
The `gamescope-cadence-v1` policy fixes capture at 60 FPS with a 99% minimum
rate, 0.5% maximum missing/drop ratio, and 50 ms maximum gap. Receipts cannot
lower the requested rate or loosen these thresholds. Every named interval must
be unique, its PTS must fall inside its marker bounds, the whole-capture summary
is independently recomputed, and terminal FFmpeg counters and encoded time must
be at least the final bounding sample and measured PTS clock.
Progress samples also bracket the canonical PTS prefix: the right cumulative
frame count and encoded clock must cover the selected interval, while the left
sample cannot claim progress beyond its interval boundary. The policy explicitly
scopes rate, gaps, missing slots, and FFmpeg drop deltas to the acceptance
interval. Terminal drops outside that interval are allowed; FFmpeg duplicates
must remain zero for the whole capture.

PipeWire and GStreamer are outside this slice. An SHM fallback is a typed
failure, not permission to switch transport. There is no CFR duplication and no
silent non-SHM fallback. Before any K1 acceptance run, run the separately
authorized animated-pattern diagnostic (`kpharness.capture_diagnostic`, below)
on one owned private Gamescope display. It must pass the same startup,
geometry, content, cadence, identity, and cleanup gates. If
`capture_shm_fallback` still happens with verified geometry, stop. The next step
is a separately reviewed PipeWire node adapter.

### Animated-pattern capture diagnostic

`kpharness.capture_diagnostic` is the checked-in driver for the one bounded
diagnostic. Tests never run it. It refuses to start without
`--authorized-single-run`, and it never retries:

```sh
cd scripts/harness && /usr/bin/python3.14 -S -B -m kpharness.capture_diagnostic run \
  --run-root /operator/diagnostic-runs --snapshot /operator/diagnostic-snapshot \
  --cleanup-commitment-log /operator/owned/commitments.log --authorized-single-run
```

Run it on the host, not in a container. The supervisor imports from the
worktree, and the child it starts runs isolated (`-I -S -B`) from the verified
snapshot only. The defaults are `/usr/bin/ffmpeg` (not the
`~/.local/bin` wrapper) and the Homebrew FFprobe. Each tool must resolve to one
native ELF file. The driver takes the canonical live-game lock and passes that
descriptor to every child, including the recorder's FFprobe probes and every
`xwininfo` query. It refuses if any `wineserver`, `swkotor`, `gamescope`,
`ffmpeg`, or `ffprobe` process exists. It matches the name in `comm`, in the
`/proc/PID/exe` target, in `argv[0]`, and in the first script argument after a
launcher such as `bash`, `env`, or `python3` (a wrapped `bash ~/.local/bin/ffmpeg`
is caught). It also refuses if the `comm`, `stat`, or `cmdline` of any `/proc`
entry of this user cannot be read. An unreadable `/proc/PID/exe` alone is kept
as evidence: the kernel hides it for non-dumpable processes such as
`kwin_wayland` and `ssh-agent`, and `comm` and `argv` still classify them. Its
own process and ancestors are excluded, and it never signals any process
during preflight. The `/proc` evidence stays in `preflight.json`. It snapshots
the harness closure plus the driver, verifies the snapshot is source-equal, and
runs the child from that snapshot. Before the child starts it prints one
commitments line and appends it to the re-validated commitment log. That line
has the SHA-256 of `diagnostic-route.json`, the FFprobe ELF SHA-256, the launch
cleanup-ledger head, the cleanup budget, and the SHA-256 of a one-time child
token. The child plays lavfi `testsrc2` at 60 FPS in `mpv` with a fixed title
and captures the verified window. It writes `[kp-diag] pattern_start` after
3 s and `[kp-diag] pattern_end` 30 s later. It then cleans up in the order
recorder, client, display.

The `--child` entry is for the supervisor only. It refuses unless it can read
the token from an inherited pipe that only the supervisor wrote, and the token
matches both its config and `commitments.json`. It also refuses unless
`canonical_lock_guard()` finds the held canonical lock on the configured
descriptor.

The child runs in its own session. A terminal Ctrl-C or hangup reaches only the
supervisor, which forwards one SIGINT to the child. SIGINT, SIGHUP, and SIGTERM
all take this path, and repeated signals are recorded but never cut the ordered
cleanup short. The supervisor then waits for the cleanup budget (1,442 s, about
24 minutes, dominated by the two frame-scaled FFprobe deadlines; the components are
in `CLEANUP_BUDGET_COMPONENTS`). Only after that budget does it kill the child's
session group and each process the run recorded in `diagnostic-owned.json`,
through a pidfd and only when the PID start still matches. It never signals a
process it did not record. `diagnostic-result.json` lists the signals received,
whether the budget ran out, and each surviving owned process by role, PID, and
start.

Without an interrupt, the supervisor lets the child run for 1,576 s: every
pre-cleanup phase in `CHILD_PRE_CLEANUP_COMPONENTS` plus the full cleanup
budget, because a normal stop runs the same two FFprobe probes. Only past that
bound does it forward SIGINT (recorded as `run_deadline`, a failed run) and
start the cleanup budget.

`diagnostic-result.json` lists each criterion. The verdict is PASS only when all
of them pass: no SHM fallback string, first-frame admission, exact window
geometry, the `animated-diagnostic-v1` content gate, canonical PTS binding, at
least 99% of 60 FPS, at most 0.5% missing or dropped slots, no gap over 50 ms,
zero FFmpeg duplicates, recomputed cadence evidence, and an acceptance interval
bounded by the route markers. The run also needs complete cleanup, no surviving
owned or forbidden process, a clear ledger at the launch head, unchanged
X0/X94/X100 sockets and lock files, an unchanged snapshot, a recorded media
SHA-256, and no driver error. Any failure exits nonzero and keeps all evidence.

Visual acceptance binds reviewer identity, UTC acceptance time, review scope,
execution digest, and master digest into a separate acceptance digest. The
accepted receipt is written through an unpredictable same-directory exclusive
temporary file, fsynced, atomically replaced, directory-fsynced, and reopened as
a regular non-symlink file before success is returned. Export rejects receipt
symlinks and copies the accepted master from a no-follow descriptor into its
private staging directory, verifies that copy against the accepted digest, and
encodes only the stable copy. A swap-and-restore of the public master during
encoding therefore cannot change encoder input.

### Gamescope DISPLAY-only admission and boot-failure evidence

A readiness file containing only `DISPLAY` is a candidate, not authority to use
that display. The Gamescope adapter rejects the caller's display (including
screen suffix aliases), verifies the readiness child's PID/start/PGID/session
and its complete ancestry back to the owned Popen leader, and rereads that
chain to detect replacement. Ordinary transitive ancestry may cross a changed
process group/session; cleanup signals individual verified identities.
Before launch, the single-purpose Linux harness records its own PID/start and
sets and verifies `PR_SET_CHILD_SUBREAPER`. It refuses an already established
subreaper, existing child workloads, or multiple threads. A double-forked
Xwayland may be adopted by this recorded controller only with stable ancestry
and the Gamescope owner's exact PGID/SID. A shared external adopter is refused.
A process must be fresh for each Gamescope lease; subreaping remains enabled
for the controller's lifetime.

For a child with no explicit `XAUTHORITY`, admission additionally requires one
owned Xwayland executable for that display. Both the pathname and abstract
AF_UNIX X11 listeners must have inodes held by that process. Its actual TCP
listener set must be empty. Bounded connections to both the pathname and abstract
sockets must report same-user peers in the owned ancestry and accept X11
setup requests with no credentials. One absolute two-second deadline covers
both handshakes. Process identities and listener inodes are checked again
after each handshake. An explicit `-ac` flag is refused. The recorded access model is
`owned-endpoint-host-local-no-cookie`; it does not claim isolation from other
local users or private Xauthority. The client environment
then sets `XAUTHORITY=/dev/null` to prevent Xlib from borrowing the user's
implicit `~/.Xauthority`. Receipts report `xauthority_present=false` and
`xauthority_mode=no-cookie-sentinel`. A `-displayfd` launch is admitted through
the same socket/ancestry binding without requiring a literal display argument.
Failure at any ownership or access check prevents
geometry/renderer probing and game launch. Children that publish an explicit `XAUTHORITY` are currently refused. An
existing path is insufficient: a future authority-file mode must also bind the
owned server endpoint, applicable display/address authorization record and
authenticated access. This refusal includes host-file aliases and files with
only unrelated-display records. No credential contents enter evidence.

Cleanup polls the direct Popen child and reaps recorded adopted children with
PID-specific `waitpid(WNOHANG)`, without stealing the leader's Popen status.
Each signal uses a pidfd pinned to an independently verified PID/start.
Matching group/session observations never gain authority from another member;
unknown members remain in separate evidence and prevent a cleanup pass.
Unreaped zombies, live descendants, reused PIDs, and unreadable recorded
identities prevent an absence claim. Retries retain the original boot error.

Endpoint admission retains candidate PID/start/parent/group/session, executable,
redacted command, socket FD attribution, and failed chain observations before
cleanup. A safely parsed candidate display is retained immediately from
readiness, before authority, environment or ancestry rejection. A launched
process with unknown display records socket cleanup as unknown and cannot pass.
Known but unadmitted endpoints can only be inspected for absence or retained;
they never grant unlink authority.
Successful admission also captures the pathname socket's exact device/inode,
type, uid/gid, mode/timestamps, basename and parent directory identity while the
owned Xwayland still holds the matching listener. This is deletion authority
only for that admitted node; old runs and rejected candidates grant none.

Pathname cleanup requires the canonical live-game lock through an open FD in
the controller, exact parent/node checks, all verified owned processes absent,
no pathname or abstract socket-table row in any state within the recorded
controller/Xwayland network namespace. Admission retains both namespace kernel
identities and verifies equality, along with the owned Xwayland FD-to-listener
attribution. Cleanup rechecks that namespace identity before and after complete
socket-table reads; a mismatch or unreadable/incomplete table fails closed.
This proves absence of live named endpoints in the admitted namespace, not
absence in unrelated namespaces or absence of harmless filesystem `O_PATH`
references. It repeats these checks and uses only the recorded basename relative to
an opened parent directory. Protected sibling display nodes and listeners are
compared before/after. A missing node is `already_absent` only after the same
listener/process checks. Any ambiguity retains the node and fails cleanup.
Cleanup does not enumerate unrelated processes' descriptor tables. An
unreadable `/proc/1/fd` therefore does not block the scoped endpoint absence
proof; named listening and accepted/connected sockets still block removal.

A supervisor holding the canonical lock must pass its FD to the isolated
controller with `pass_fds=(lock.fileno(),)`; a supervisor's assertion alone
is insufficient. `KP_GAMESCOPE_REPO_ROOT` identifies the repository for a
snapshot runtime so the exact canonical lock inode can be verified. Ordinary
creative runs hold that descriptor in the same controller already.
Linux has no atomic unlink-by-inode operation. The canonical lock and repeated
checks bound cooperating harness races; an uncooperative replacement after the
last stat remains a documented limit. Detected pre-unlink replacement is
refused, and postconditions cannot be promoted to success on ambiguity.

`gamescope-lease.json` retains the boot error separately from each cleanup
attempt. `gamescope-session-cleanup.json` preserves the session boot error,
component failures and per-attempt order. Retries execute only unfinished
components; the canonical order remains `recorder`, `game_wine`, `display`.
A cleanup exception cannot replace the original exception reported by boot.
An earlier failed session-cleanup attempt remains a failed run even if a retry
subsequently releases the resources. These are host lifecycle guarantees;
passing the regressions does not establish a live renderer or game result.

Focused host-only repair regressions (no display or game launch):

```sh
python tools/kpharness_gamescope_boot_repair_test.py
python tools/kpharness_gamescope_backend_test.py
```
