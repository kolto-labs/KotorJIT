# Task 7 Gamescope live preflight review

Date: 2026-09-27  
Reviewer: Codex (read-only preflight)  
Checkout reviewed: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`  
Backend: `linux-wine-k1-gamescope`

## Verdict

**FAIL — do not start the proposed live run from this checkout yet.**

The host has the basic visible prerequisites (`gamescope`, `glxinfo`, `xdotool`,
Wine, FFmpeg, FFprobe, and `/dev/dri`), and the checked-in adapter has the
intended ownership and capture shape. That is only a conditional host preflight.
The run is not currently package-ready: the worktree is heavily dirty, the
Task 7 package audit says the current source is not an immutable minimal
manifest, no current installed runtime/proxy is bound to this adapter snapshot,
and no fresh stage, Wine prefix, checkpoint root, route, or output directory
has been selected and proven disjoint. Existing private GPU/prototype media is
not a substitute for a receipt from this source and run.

This review performed no process launch, renderer probe, display creation, game
launch, recording, or file mutation other than writing this review.

## Read-only observations

The checked-in implementation does the required sequencing in principle:

* `display_backends.py` admits only Linux K1, refuses Crostini, refuses display
  reuse, requires the four tools and `/dev/dri`, and separates host facts from
  backend admission.
* `gamescope_xwayland.py` creates a run-owned Gamescope process group, obtains
  private Xwayland authority, removes the three forced software-renderer
  variables, and requires `glxinfo -B` to report direct, accelerated,
  non-software rendering.
* The Gamescope session discovers exactly one visible PID-owned window before
  attaching `X11WindowRecorder`; the recorder freezes the window identity and
  uses its actual geometry with FFmpeg `-window_id`.
* The watcher treats recorder exit, lease loss, window replacement, resize, or
  identity-query failure as capture failure. Teardown records and enforces
  recorder, game/Wine, then display order.
* Schema 2 keeps requested capture FPS, encoded FPS, distinct-frame cadence,
  and human visual acceptance separate. A valid MP4 or passing route leaves
  `ok=false` until the review command binds a visual decision to the media
  digest.

The reviewed worktree is on `codex/lua-boundary-validation` with many modified
and untracked files, including the runner, session, recorder, CMake, native
runtime, route, and example files. The private package audit at
`/home/brunner56/kp-live-20260922/task7-package-proof-audit.md` explicitly says
the current tree is not packageable and that the current whole-file state pulls
unrelated Mach-O, projectile, and cancellation changes into a supposed Task 7
snapshot. A live run must therefore use a clean, hunk-materialized source
snapshot and a manifest, or its result cannot claim byte-bound Task 7 proof.

Current host facts observed without launching anything:

* Linux `7.1.9-200.fc44.x86_64`, x86_64; `XDG_SESSION_TYPE=wayland`,
  `XDG_CURRENT_DESKTOP=KDE`, host `DISPLAY=:0`, host `WAYLAND_DISPLAY=wayland-0`.
* `/usr/bin/gamescope`, `/usr/bin/glxinfo`, `/usr/bin/xdotool`,
  `/usr/bin/wine`, `/usr/bin/wineserver`, `/home/brunner56/.local/bin/ffmpeg`,
  `/home/linuxbrew/.linuxbrew/bin/ffprobe`, and `/usr/bin/python3` exist.
* `/dev/dri` exists with `card0`, `card1`, `renderD128`, and `renderD129`.
  This is device availability only; it does not prove that a fresh Gamescope
  lease or game is accelerated.
* The running desktop owns Xwayland `:0`; unrelated Xvfb servers exist on
  `:1008869546` and `:94`. No `swkotor.exe`, Wine server, Gamescope, or FFmpeg
  process was observed in the process listing at review time. The checkout's
  `tmp/harness-locks` directory had no existing `live-game.lock` file, but that
  is a point-in-time observation and the live runner must acquire the canonical
  lock immediately before launch.
* Existing paths under `/home/brunner56/kp-live-20260922` include
  `gpu-capture-probe/capture.mp4`, old frozen console artifacts, and prior
  receipts. They are historical/prototype artifacts, not fresh disjoint run
  ownership. No existing path was adopted.
* Candidate K1 files found under `/home/brunner56` include
  `/home/brunner56/modsync-hot/K1_auto/swkotor.exe` and
  `/home/brunner56/agentdecompile-nvme/k1gog-target/swkotor.exe` (both 4,395,008
  bytes), plus a zero-byte `K1_manual/swkotor.exe`. The candidate install must
  be selected explicitly and verified by the harness; this review does not
  declare either candidate a valid installed source.

## Exact safe command contract

After producing a clean, Task 7-only source/artifact manifest and selecting
fresh paths, the one permitted acceptance command is this template. Replace
every angle-bracket value with an explicit path from that manifest; do not use
the historical probe or frozen artifact directories as stage, prefix,
checkpoint, or output:

```sh
cd /run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation
PYTHONPATH=scripts/harness /usr/bin/python3 -m kpharness.creative \
  --backend linux-wine-k1-gamescope --capture-fps 60 --width 1024 --height 768 \
  --script <frozen-lua> --route <frozen-console-route> \
  --build-dir <fresh-build> --source <installed-k1> \
  --staged <new-owned-stage> --wineprefix <new-owned-prefix> \
  --checkpoint-root <disjoint-checkpoints> --output <new-owned-output>
```

The command is safe to attempt only after these preconditions are true:

1. The source archive, every allowlisted runner file, route, Lua input,
   address profile, built runtime/proxy, and installed K1 source each have
   manifest SHA-256 identities. Hunk-only dirty files have been materialized
   onto a declared base; the whole dirty checkout is not used as a package.
2. `<fresh-build>`, `<new-owned-stage>`, `<new-owned-prefix>`,
   `<disjoint-checkpoints>`, and `<new-owned-output>` are newly created or
   carry only this runner's matching ownership sidecars. They are pairwise
   disjoint from source, build, and one another, and no symlink escapes them.
3. The selected route is K1, explicitly sets `game_speed=1.0`, names the
   frozen physical-console route, and all deployed Lua basenames are unique.
   The selected install passes the harness's content and source identity
   checks; no source or save tree is borrowed from another run.
4. The canonical `tmp/harness-locks/live-game.lock` is acquired, no K1/Wine
   process belongs to the selected stage/prefix, and no caller `DISPLAY` or
   `WAYLAND_DISPLAY` is reused. The backend must create a new owned
   Gamescope/Xwayland authority.
5. The backend preflight admits Linux K1, all four required executables, and
   `/dev/dri`; the lease then independently proves readiness and direct,
   accelerated, non-software `glxinfo -B` output.

## Acceptance predicates

The run is accepted as Task 7 live proof only if one schema-2 receipt proves
all of the following. A build, host-only test, route pass, screenshot, encoded
60 FPS stream, or old MP4 is insufficient by itself.

* The receipt binds the manifest/source/archive, runtime/proxy, address profile,
  route, Lua, stage, prefix, and output identities before and after; source
  and input bytes are unchanged.
* Platform admission is Linux K1 through a newly owned Gamescope/Xwayland
  lease. Gamescope parent/child PID and start identities, process group,
  private display, authority presence, dimensions, readiness, and renderer
  output are retained. The renderer is direct, accelerated, and not a
  software renderer.
* Exactly one visible game window is found by PID-scoped X11 discovery. Its
  X11 ID, owner PID/start identity, positive actual geometry, exact private
  display, and lease ID remain stable through capture.
* Recording starts only after that window is mapped. The retained FFmpeg argv
  contains `-f x11grab`, actual target `-video_size`, exactly one
  `-window_id <same-id>`, and the private display input. It never uses a root
  capture as GPU/window evidence. Continuous media is retained and hashed;
  FFprobe metadata is retained; recorder liveness has no unhandled exit,
  resize, replacement, lease-loss, or identity-query failure.
* The physical-console route records the exact pre-input and post-input
  `kp.console.v1` identity, one F12/Enter sequence, the exact next request and
  successful outcome, and undropped session-filtered input/result lines.
  Route predicates pass with no skipped step.
* Cleanup is `recorder` then `game_wine` then `display`, with each component
  passed and no foreign PID terminated. This must hold on success and on
  boot/route/recorder failure paths.
* The unaltered landscape master receives explicit human visual review for
  native behavior, framing, readability, and motion. Only then may
  `kpharness.creative_accept` be run with the reviewed file's SHA-256; its
  receipt digest must verify and `ok` may become true. Requested 60 FPS and
  encoded FPS remain distinct from distinct game-frame cadence.

## Hazards and blockers

* **Source hazard:** current checkout is dirty and not a byte-stable package;
  full-file copying can include unrelated product changes. Resolve with a
  clean materialized manifest before any live command.
* **Artifact hazard:** existing `gpu-capture-probe` media, frozen DLLs, and
  prior acceptance JSON are historical evidence and must not be relabeled as
  this run's output or runtime proof.
* **Stage/save hazard:** no fresh stage/prefix/checkpoint/output contract was
  established in this review. Reusing a nonempty prototype risks saves,
  Override, logs, or runtime bytes crossing runs. Use new owned paths and the
  runner's ownership checks.
* **Process/display hazard:** KDE's `:0` and `wayland-0`, plus unrelated Xvfb
  instances, are user/other-process state. They are not valid capture or input
  authorities. A concurrent live run can appear after this read-only check;
  lock and exact PID/start checks are mandatory immediately before launch.
* **Renderer hazard:** `/dev/dri` and installed tools do not establish an
  accelerated Gamescope child. The lease's own `glxinfo -B` receipt is the
  admission predicate, and must be retained.
* **Platform boundary:** this review makes no claim for native Wayland,
  Windows, macOS, ChromeOS/Crostini, or any other platform. KDE/Wayland is
  only the host condition for the private Linux Gamescope/Xwayland adapter.

## Readiness decision

Host/tool availability is **conditionally favorable**. The proposed run's
overall readiness is **FAIL** until the source snapshot is materialized and
manifested, a fresh installed runtime/build and K1 source are selected, and
fresh disjoint owned paths are proven. Once those gates are satisfied, the
command and predicates above are the safe contract; a successful live run must
still earn its own renderer, window, capture, console, cleanup, preservation,
and visual evidence.
