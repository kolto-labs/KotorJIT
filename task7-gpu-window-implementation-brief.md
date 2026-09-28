# Task 7 implementation brief: owned GPU window capture

## Decision and boundary

Implement a reusable *display / owned-window / input / exact-window-recording*
boundary.  The first executable adapter is Linux K1/Wine inside an **owned,
headless Gamescope Xwayland display**.  It is selected explicitly as
`linux-wine-k1-gamescope`; the existing `linux-wine-k1` adapter remains the
software/Xvfb path and retains its root-window recorder.

This is a Linux-only implementation slice.  The shared interface describes
what a native Wayland, Windows, macOS, or ChromeOS adapter must prove before it
can be admitted.  It does not make those platforms supported merely because
they implement the same Python protocol.

The proof referent for the slice is one installed K1 route run, controlled by
the frozen source/artifact manifest described in
`/home/brunner56/kp-live-20260922/task7-package-proof-audit.md`.  In that run,
the same immutable receipt must bind the selected adapter, its owned display,
the accelerated renderer probe, the actual game-window identity, the ffmpeg
`-window_id` command, the continuous media bytes, physical console route
results, cleanup, and a human visual decision.  A build, a valid MP4, an
encoded 60 FPS stream, or a passing route alone is insufficient.

## Owned files

The implementation owns only the following repository files.  Do not copy the
private prototype files or their local controller imports, absolute paths,
environment mutation, regex-based largest-window selection, or class-level
per-run attributes.

| File | Change and responsibility |
| --- | --- |
| `scripts/harness/kpharness/display_backends.py` **new** | Immutable capability, detected-host, display-lease, owned-window, and input/capture protocol records; platform/compositor detection and explicit admission/refusal reasons.  No game launch code. |
| `scripts/harness/kpharness/gamescope_xwayland.py` **new** | Linux Gamescope/Xwayland display lease.  It starts and stops only its own process group, obtains the child-published Xwayland environment, tests the renderer, and produces the immutable display identity receipt. |
| `scripts/harness/kpharness/creative_wine.py` | Keep the existing Xvfb session intact.  Add a separate Gamescope session class that owns one `GamescopeXwaylandLease`, clears only its own inherited software-renderer overrides, waits for and records the first verified game window, and stops the recorder before the lease. |
| `scripts/harness/kpharness/session.py` | Extract the existing PID-owned X11 window discovery into a display-lease-aware helper, preserving its single-visible-window, PID, positive-geometry, and replacement checks.  The default Xvfb lease must retain current behaviour. |
| `scripts/harness/kpharness/owned_x11.py` | Consume the generic immutable owned-window target while retaining X11-only focus/key injection and exact-DISPLAY validation.  It must refuse a lease that did not advertise `x11_input`. |
| `scripts/harness/kpharness/recording.py` | Preserve `X11Recorder` root capture for the Xvfb backend.  Add a window-target recorder that accepts only an `OwnedWindow`, starts ffmpeg with `-window_id`, polls target identity/geometry and recorder liveness, and records cadence and failure evidence. |
| `scripts/harness/kpharness/creative.py` | Select a backend explicitly, construct the matching session/recorder, start GPU recording only after the mapped owned window exists, surface asynchronous capture failure to the route, and emit schema-2 receipts. |
| `tools/kpharness_creative_test.py` | Add host-only fake-process/probe tests for capability admission, Gamescope environment isolation, exact window capture, errors, and teardown order.  Existing Xvfb tests remain. |
| `docs/creative-runner.md` | Document backend names, supported/refused matrix, dependency/preflight requirements, receipts, cadence language, and the one live acceptance command/criteria. |

`CMakeLists.txt` requires no change: its existing `kpharness_creative_test`
entry executes the expanded host-only test file.  No console driver, route TOML,
private test controller, build artifact, or project-wide display rewrite is in
this implementation slice.

## Reusable contract and platform admission

`display_backends.py` is the boundary between platform/compositor detection and
the game adapter.  Detection only reports facts from the process environment,
available binaries, kernel/OS identifiers, and explicit probes.  It must not
start a game, borrow a desktop, or infer support from `DISPLAY`,
`WAYLAND_DISPLAY`, or an interface class existing in source.

The module exposes immutable records rather than mutable class settings:

* `HostFacts`: OS family/version, container or Crostini marker, desktop session,
  compositor/session type, machine architecture, required executable presence,
  and probe results.
* `BackendCapabilities`: stable adapter id; supported target ids; whether it can
  create an owned display; window enumeration method; exact-window capture
  method; real input method; acceleration proof method; and explicit refusal
  reason when an item is unavailable.
* `DisplayLease`: adapter id, generated run id, owned process PID plus process
  start identity, exact X11/Wayland authority environment, requested dimensions,
  readiness deadline, and `is_alive()`/`close()` methods.  The environment is a
  newly constructed allowlist for the child, never the user's desktop session.
* `OwnedWindow`: X11/OS window id, owning game PID plus start identity, original
  positive width/height, lease id, discovery time, and the capture/input
  capabilities actually admitted for this window.  It is the only object an
  input port or window recorder accepts.

The game adapter can request capabilities from this layer; it cannot fabricate
a window id, pass a root window, reuse `DISPLAY`, or treat host detection as a
successful acceleration/capture proof.  A backend must return `refused` before
stage ownership or game launch when its required capability is absent.

| Detected host / adapter | First-slice status | Ownership and real input | Exact-window capture and acceleration admission | Cleanup and live acceptance needed before a support claim |
| --- | --- | --- | --- | --- |
| Linux X11, `linux-wine-k1` | Existing supported software path | Fresh Xvfb; X11 `xdotool` only against a PID-owned window when physical input is requested | Existing root capture only; it must continue to say software/Xvfb root capture, not GPU/window capture | Existing creative acceptance; it does not satisfy GPU acceptance |
| Linux X11 or Wayland GNOME/KDE host, `linux-wine-k1-gamescope` | **Implement now** | Fresh headless Gamescope process creates its own Xwayland; X11 input is scoped to its verified game window | ffmpeg `x11grab -window_id` of the verified Xwayland window; `glxinfo -B` inside the lease must show direct/accelerated non-software rendering | Stop recorder, game, Wine server, Gamescope child/group in order; one installed game route, exact receipt, and visual review |
| Native Linux Wayland GNOME/KDE without the owned Gamescope/Xwayland lease | Refused for this runner | Do not use portals, `wtype`, `ydotool`, or the user's compositor session as a substitute | No native Wayland surface identity/capture proof is implemented | A future adapter needs compositor-specific owned surface, focused input, surface capture, renderer and cleanup live proof |
| Native Windows | Declared interface only; refused | Future adapter must own a process/job object and use its verified HWND with real window-directed input | Future adapter must bind the HWND/PID/geometry to Windows Graphics Capture or equivalent and retain a hardware-renderer proof | Must prove no desktop/window reuse, resize/loss, recorder failure, job cleanup, and a native installed-game acceptance |
| Native macOS | Declared interface only; refused | Future adapter must own the launched app process and verified CGWindowID; send input only after explicit focus/ownership checks | Future adapter must bind CGWindowID/PID/geometry to a supported window capture path and record Metal/renderer evidence | Must prove Screen Recording/Input Monitoring permissions, window loss/resize, capture exit, process cleanup, and a native acceptance |
| ChromeOS Crostini | Detected and refused by default | Detect Crostini (`/dev/.cros_milestone`, container and ChromeOS host markers) before adapter choice; never reuse the ChromeOS display or browser input | X11 forwarding, Wayland forwarding, and Steam/Proton availability are each facts, not support.  No capture/acceleration claim from forwarded display alone | Only a separately admitted owned Gamescope/Xwayland-in-Crostini path with working `/dev/dri`, capture, input and installed-game proof may be named supported |
| ChromeOS Steam environment outside Crostini | Declared interface only; refused | Detect it distinctly from Crostini; no assumption that Steam’s compositor grants an owned game surface | No native capture/input/render proof is implemented | Requires its own platform adapter and end-to-end live acceptance |

This keeps GNOME/KDE detection separate from Gamescope: a GNOME or KDE Wayland
desktop is only a host condition; the first slice is supported because it
creates a private Xwayland display below its own Gamescope process.

## Linux Gamescope/Xwayland lifecycle

1. `creative.py` validates `--backend` before claiming stage/prefix/output
   directories.  Valid names are `linux-wine-k1` and
   `linux-wine-k1-gamescope`; unsupported native platform names return the
   current structured preflight failure.  `--width`, `--height`, and
   `--capture-fps` remain explicit and bounded.
2. The Gamescope backend rejects non-Linux hosts, display reuse requests,
   missing `gamescope`, `glxinfo`, `xdotool`, `ffmpeg`, or a suitable renderer
   probe before game launch.  It also performs the current private stage,
   prefix, `/tmp`, source/build/run disjointness, lock, and no-existing-K1
   preflights.
3. `GamescopeXwaylandLease.start()` makes a run-owned readiness path under
   `run_dir`, opens `gamescope.log`, and launches a new process group with
   `gamescope --backend headless -w W -h H -W W -H H -r 60 --` followed by the
   current Python executable in a small module child mode.  The child writes a
   temporary JSON then atomically renames it after it has collected only
   `DISPLAY`, `XAUTHORITY`, and `WAYLAND_DISPLAY`.  It stays alive until the
   parent terminates its owned group.  The helper has no hardcoded filesystem
   location and no global or class-mutable run state.
4. The parent requires a bounded ready file, a live Gamescope parent/child, a
   syntactically valid private X11 display endpoint, and a successful X11
   readiness probe.  It records parent/child PIDs and process start identities,
   requested dimensions, command argv, readiness timing, and sanitized display
   identity.  Do not record authentication cookie contents.
5. The GPU lease constructs game environment from the normal isolated session
   environment, removes only `LIBGL_ALWAYS_SOFTWARE`, `GALLIUM_DRIVER`, and
   `LP_NUM_THREADS`, then overlays its ready-file X11/Wayland values.  It does
   not copy `DBUS_SESSION_BUS_ADDRESS`, desktop `WAYLAND_DISPLAY`, host
   `DISPLAY`, portal variables, or any user Xauthority into the game.
6. Run `glxinfo -B` with that exact lease environment, save raw output and a
   parsed renderer receipt.  Admission requires successful command execution,
   direct rendering/`Accelerated: yes`, and an OpenGL renderer string that is
   neither llvmpipe, softpipe, nor another software renderer.  This establishes
   an accelerated Xwayland renderer for the lease; it is evidence for the game
   launch environment, not a claim that distinct game frames are 60 FPS.
7. Launch Wine only after that proof.  After launch, wait with a fixed bounded
   deadline for one visible PID-owned X11 game window.  The shared discovery
   checks every candidate using `xdotool search --onlyvisible --pid`, then
   verifies X11 id, owner PID/start identity, positive geometry, exact lease
   display and a live owned Gamescope lease.  Zero, multiple, foreign, changed,
   or missing candidates fail.  The first valid mapped game window is frozen in
   `OwnedWindow`; a later replacement never silently becomes the capture target.
8. Only after this discovery starts the window recorder.  This is intentionally
   different from the software backend’s pre-launch display/root capture.  The
   GPU recording receipt says `capture_start = after_first_mapped_owned_window`.
   It never calls an X11-root command and cannot use the configured screen size
   as a substitute for the actual game size.  This handles K1’s resolution
   fallback: capture the verified actual geometry, including 800x600 when an
   unsupported requested size was reset, while 1024x768 remains the tested
   starting configuration.

## Exact-window recorder and failures

`X11WindowRecorder.start(target, native_log)` requires an `OwnedWindow`; it
does not accept a display integer or generic screen tuple.  Its command uses
the target’s discovery-time `width` and `height`, exact X11 display, and
`-window_id <target.window_id>`.  It refuses a root id, a missing id, an odd or
non-positive geometry, a target from another lease, or a recorder restart.

The command captures the game window rather than the Gamescope root because
root grabbing has produced black files.  Use the configured capture sampling
rate, no interpolation, the existing bounded ffmpeg thread count, and the
continuous MP4 output.  Store argv as an argument array in the receipt; do not
shell-concatenate it.

A watcher samples no more frequently than every 250 ms and reports a terminal
capture failure if any of these occurs before orderly recorder shutdown:

* Gamescope parent or readiness child dies;
* ffmpeg exits, including an early successful-looking exit;
* the window is missing, its X11 ID/PID/start identity changes, or it is no
  longer visible/positive-size;
* width or height differs from the frozen capture geometry; or
* querying X11 fails or times out.

The watcher writes `capture-failure.json` with the initial identity, last
verified identity, elapsed time, ffmpeg status, and error class.  It sets a
thread-safe instance failure state consumed before and after every route step.
`creative.py` treats it as route/media failure, retains the partial MP4 and
logs, bypasses representative rendering, and records no success.  A resize is
not recaptured at a new size in this slice: fail the run, then investigate.

On normal completion, stop and join the marker/window watcher, signal only the
owned ffmpeg process, wait boundedly, and write `capture.json`.  SIGINT exit
255 remains acceptable only at this finalization point and only if the process
was still live at recorder stop; all other non-zero exits remain failures.

## Receipt schema (schema 2)

`creative-run.json` advances from schema 1 to schema 2.  Keep the existing
source/input/runtime/route/checkpoint/cleanup identities and add the following
shape.  Exact absolute paths are retained only for the user-selected run,
stage, prefix and artifact locations; no secret environment values are emitted.

```json
{
  "schema": 2,
  "backend": "linux-wine-k1-gamescope",
  "platform": {
    "detected": {"os": "linux", "session": "wayland", "desktop": "KDE"},
    "admission": {"status": "admitted", "reason": "owned Gamescope Xwayland lease"}
  },
  "display": {
    "kind": "gamescope-xwayland", "lease_id": "run-scoped-id",
    "owner": {"gamescope": {"pid": 1, "start": "..."}, "ready_child": {"pid": 2, "start": "..."}},
    "requested_geometry": [1024, 768], "x11": {"display": ":N", "xauthority_present": true},
    "readiness": {"status": "passed", "elapsed_seconds": 0.0},
    "renderer": {"status": "accelerated", "probe": "renderer.txt", "renderer": "...", "direct": true}
  },
  "window": {
    "status": "verified", "id": "0x...", "pid": 3, "pid_start": "...",
    "geometry": [1024, 768], "discovered_monotonic": 0.0, "lease_id": "run-scoped-id"
  },
  "capture": {
    "kind": "x11-window", "root_capture": false, "window_id": "0x...",
    "input": ":N", "command": ["ffmpeg", "...", "-window_id", "0x...", "..."],
    "capture_sampling_fps_requested": 60, "interpolation": false,
    "start": "after_first_mapped_owned_window", "status": "passed",
    "geometry_at_start": [1024, 768], "watch": {"interval_ms": 250, "checks": 0}
  },
  "cadence": {
    "capture_sampling_fps_requested": 60,
    "encoded": {"average_frame_rate": "...", "nominal_frame_rate": "...", "frame_count": "..."},
    "ffmpeg": {"duplicates": null, "drops": null, "diagnostics_status": "recorded-or-unavailable"},
    "distinct_game_frames": {"status": "unvalidated", "method": null},
    "visual_review": {"status": "pending", "scope": "native behavior, framing, readability, and cadence"}
  },
  "route": {"status": "passed"},
  "media": {"status": "retained_for_visual_review", "continuous": {"path": "...", "sha256": "..."}},
  "cleanup": {"recorder": "passed", "game": "passed", "display": "passed", "status": "passed"},
  "ok": false
}
```

`ok` remains false until all execution identities, the physical-console route
predicate, capture, cleanup, source preservation and input preservation have
passed **and** the separate visual review has been explicitly accepted.  On a
capture failure, retain the same identity fields with `capture.status =
"failed"`, a typed failure record, partial media hash when readable, and
`media.status = "retained_failure_recording"`.

Cadence terms are intentionally separate:

| Term | What it measures | What it cannot establish |
| --- | --- | --- |
| Requested capture FPS | ffmpeg/X11 sampling request, e.g. 60 Hz | Encoder output, game renderer speed, or perceptual smoothness |
| Encoded FPS | ffprobe nominal/average stream rate and frame count | Whether adjacent frames contain a new game frame |
| ffmpeg duplicates/drops | Encoder/capture diagnostics when available | Complete game-render cadence without a valid analysis method |
| Distinct-frame cadence | Measured change/timing between actual captured game images | Native behavior quality or a readable presentation by itself |
| Visual acceptance | Human review of unaltered landscape master and selected clip: defining effect, actors/framing, no misleading transition, and understandable motion | Route correctness, artifact identity, or hidden state proof |

Do not interpolate, upsample, or label an encoded 60 FPS MP4 as 60 distinct
game FPS.  Preserve the continuous landscape MP4 at capture cadence.  A GIF is
a lower-rate preview, never the cadence evidence.  Any optional vertical short
must retain the uncropped clean master, parameterize its title/caption, keep
hashes, and receive its own visual decision.

## Cleanup order and ownership limits

The session’s `finally` path must run identically for successful routes, route
failure, boot failure after display creation, SIGTERM, and recorder failure:

1. Mark the recorder as stopping so its watcher does not classify deliberate
   finalization as failure; stop/join the window recorder and retain its log and
   MP4 status.
2. Close the channel and stop only the game PIDs that match both this exact
   Wine prefix and staged working directory; then request only this Wine
   namespace’s `wineserver -k`.
3. Close the `GamescopeXwaylandLease`: terminate the readiness child and
   Gamescope process group recorded at startup, wait boundedly, escalate only
   those recorded PIDs/group members if necessary, close its log, and delete
   only its ready file.
4. Release only the session’s stage/display locks, copy available owned runtime
   logs, calculate source-after/input-after receipts, and write final cleanup
   states even when an earlier step failed.

The Xvfb backend continues its present recorder-before-game-before-Xvfb order.
No backend may kill by display number alone, scan a user desktop, reuse a
caller `DISPLAY`/`WAYLAND_DISPLAY`, terminate an arbitrary Gamescope, or pass
a user desktop window to `xdotool` or ffmpeg.

## Host-only gates and one live acceptance

Expand `tools/kpharness_creative_test.py` with injection seams for process
launch, time, readiness files, environment, renderer probe, `xdotool`, and
ffmpeg.  The host gate must cover all of the following without launching Wine,
Gamescope, Xvfb, a game, or a real recorder:

* explicit backend choice and capability/refusal table: existing software
  backend remains constructible; unsupported platform/backend combinations
  fail before claims or launch;
* environment construction strips host desktop/session authority and only the
  GPU backend removes the three forced software rendering variables;
* Gamescope readiness timeout/death, invalid child environment, unaccelerated
  or software renderer, and missing dependency refuse the run;
* exact one PID-owned first mapped window becomes an immutable target; zero,
  multiple, foreign, replaced, lost, or resized windows fail;
* GPU recording command contains `-window_id` and actual target geometry, never
  an X11 root `-i :N.0` capture without `-window_id`; software recorder remains
  root/display capture;
* early recorder exit, non-finalization error, lease death, watch failure, and
  partial MP4 all keep failure evidence and block representative success;
* requested sampling, encoded stream fields, distinct-frame status, and visual
  status are distinct receipt fields; and
* recorder stop precedes game/Wine and Gamescope teardown on normal, boot-error
  and double-teardown paths, with no foreign PID killed.

Run the existing CTest label gate after the focused script.  These are design
and lifecycle regressions; they are not GPU, game, installed-artifact, or
visual proof.

The single live acceptance is deliberately narrow.  Materialize the Task 7
source allowlist onto a clean base, build its runtime/proxy, and run one chosen
private physical-console TOML with:

```sh
PYTHONPATH=scripts/harness /usr/bin/python3 -m kpharness.creative \\
  --backend linux-wine-k1-gamescope --capture-fps 60 --width 1024 --height 768 \\
  --script <frozen-lua> --route <frozen-console-route> \\
  --build-dir <fresh-build> --source <installed-k1> \\
  --staged <new-owned-stage> --wineprefix <new-owned-prefix> \\
  --checkpoint-root <disjoint-checkpoints> --output <new-owned-output>
```

The command is an acceptance template, not a claim that arbitrary local paths
or a live user display are usable.  It passes only when one schema-2 receipt
shows: source/archive/runtime/proxy/route/Lua hashes before and after; selected
Gamescope/Xwayland identity; an accelerated lease renderer; one verified game
window whose captured actual geometry matches the `-window_id` command; a
continuous MP4 and ffprobe data; recorder survival without resize/loss; exact
physical F12/Enter console correlation and route predicates; recorder-first
cleanup; and a reviewer’s explicit acceptance of the native visual behavior.

The historical 60-FPS rave media and any black root capture are excluded from
presentation acceptance.  They are prototype observations only.
