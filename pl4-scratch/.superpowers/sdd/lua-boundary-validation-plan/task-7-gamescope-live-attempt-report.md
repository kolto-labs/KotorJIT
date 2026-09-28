# Task 7 Gamescope creative live attempt — failed before route

## Result and proof boundary

One serialized private invocation of the checked-out `kpharness.creative`
Gamescope backend was made.  It is **not** a valid Task 7 acceptance attempt:
the harness source used by the command was the dirty
`lua-boundary-validation` worktree, not an immutable snapshot that includes
the Gamescope backend.  The run also failed before it reached an owned game
window, FFmpeg exact-window capture, F12 input, or any `kp.console.v1`
physical-console result.  No visual review or `creative_accept` action was
performed.

The retained runner receipt is schema 2, but it contains no populated
`platform`, `display`, `window`, `capture`, or `cadence` section because boot
did not finish.  It records `ok: false`, `route.status: failed`, and
`media.status: retained_failure_recording`; no media file exists.

## Exact private run and command

- Run directory:
  `/home/brunner56/kp-live-20260922/private-gpu-runs/20260927-081255-56942ef0`
- UTC interval: `2026-09-27T08:14:33.146865+00:00` through
  `2026-09-27T08:17:13.970827+00:00`.
- Source: `/home/brunner56/krayt/tmp/k1_harness`.
- Candidate build: `/home/brunner56/kp-console-protocol-20260927/build`.
- Existing route: `/home/brunner56/kp-live-20260922/console-smoke.toml`.
- Existing deployed input: `scripts/examples/probe/00_probe.lua`.
- Fresh private stage, Wine prefix, and checkpoint root:
  `/home/brunner56/kp-live-20260922/private-gpu-runs/20260927-gamescope-creative-console-{stage,wineprefix,checkpoints}`.

The command was:

```sh
env -u DISPLAY -u WAYLAND_DISPLAY -u XAUTHORITY -u DBUS_SESSION_BUS_ADDRESS \
  -u KP_HARNESS_REUSE_DISPLAY PYTHONPATH=scripts/harness /usr/bin/python3 \
  -m kpharness.creative --backend linux-wine-k1-gamescope --capture-fps 60 \
  --width 1024 --height 768 --boot-timeout 120 --script probe/00_probe.lua \
  --route /home/brunner56/kp-live-20260922/console-smoke.toml \
  --build-dir /home/brunner56/kp-console-protocol-20260927/build \
  --source /home/brunner56/krayt/tmp/k1_harness \
  --staged /home/brunner56/kp-live-20260922/private-gpu-runs/20260927-gamescope-creative-console-stage \
  --wineprefix /home/brunner56/kp-live-20260922/private-gpu-runs/20260927-gamescope-creative-console-wineprefix \
  --checkpoint-root /home/brunner56/kp-live-20260922/private-gpu-runs/20260927-gamescope-creative-console-checkpoints \
  --output /home/brunner56/kp-live-20260922/private-gpu-runs
```

It exited `1` and printed:

```json
{"ok": false, "run_dir": "/home/brunner56/kp-live-20260922/private-gpu-runs/20260927-081255-56942ef0", "route": "failed", "media": "retained_failure_recording"}
```

## Preflight observations

- `/usr/bin/gamescope`, `/usr/bin/glxinfo`, FFmpeg, FFprobe, XDoTool, Wine,
  and WineServer were present.
- `/dev/dri/renderD128` and `/dev/dri/renderD129` were present and
  world-readable/writable character devices.  The backend's own admission
  reported Linux/KDE/Wayland, non-Crostini, required executables present,
  `dri_present: true`, and `status: admitted` for an owned Gamescope Xwayland
  lease.
- The preflight had no `swkotor.exe`, `swkotor2.exe`, or `gamescope` process,
  and no process carried `KP_PRIVATE_CONTROLLER_RUN`.  Two unrelated Xvfb
  instances were observed and left untouched.
- The private-run filesystem had 27,572,895,744 bytes available; the workspace
  volume had 193,654,272,000 bytes available.  Available RAM was
  8,447,737,856 bytes and swap remained available.
- Candidate bytes matched its frozen build manifest before staging:
  `kphasor.dll` =
  `fd8e069a1ff5a7b489f32a6492222f396f85e7b74539deb56228395b297dfac2`,
  `binkw32.dll` =
  `1b25f37125237aefb67271533f88c48dcf07ddd37bf180743a3b0dfa2ff729d9`.

## Failure predicate and retained evidence

The runner performed private staging, copied writable data only to the new
stage, installed the two candidate runtime files, and then started Gamescope.
Its log selected `AMD Radeon RX 460 Graphics (RADV POLARIS11)` and brought
Xwayland up on its private `:1`.  Boot/teardown then failed on the exact
predicate:

```text
RuntimeError: cleanup failed: display: RuntimeError: owned Gamescope process group survived SIGKILL
```

The receipt repeats that error in `route.error` and records cleanup order
`["recorder", "game_wine", "display", "display"]`, with `recorder: passed`,
`game_wine: passed`, and `display: failed`.  The duplicated display entry is
the session's error cleanup followed by the outer `finally` cleanup attempt.
This is a cleanup refusal, not evidence of a Lua, console, or game defect.

The only owned PID persisted before failure was the ready child from
`gamescope-b12ab845ccbc4a5e9efe224f4d6cc26b.ready.json`:

| Role | PID | Start token | PGID | Final liveness |
| --- | ---: | --- | --- | --- |
| Gamescope ready child (private `DISPLAY=:1`) | 486796 | `59098686` | Not persisted because boot failed before schema-2 lease receipt | `/proc/486796` absent |
| Gamescope leader/process group | Not persisted | Not persisted | Not persisted | `pgrep -x gamescope` returned no process |
| K1 game | No PID was created/persisted | — | — | `pgrep -x swkotor.exe` and `swkotor2.exe` returned no process |
| Private Xwayland | No PID was persisted | — | — | only unrelated host `Xwayland :0` remained; no private `:1` process remained |

No signal or kill was issued after the runner's own teardown.  The canonical
live-game lock had no holder after exit.

Retained evidence under the run directory includes `creative-run.json`,
`driver.log`, `gamescope.log`, the ready record, `session.log`, frozen
`executed-route.toml`, deployed-script receipt, and source before/after
receipts.  There is no continuous MP4, GIF, PNG, route `report.json`, or
console-command receipt because no owned window/capture/route began.

## Preservation and artifact equality

- `source-before.json` and `source-after.json` have the same SHA-256:
  `bfa95f2de32efa858256b58640ef3379c14c5c8b3c6dacb3d87bfb133caf40e3`.
  Their 5,945 source-preservation entries compare equal; the receipt therefore
  has `source_unchanged: true`.
- The frozen input script and its staged copy both hash to
  `cafcf88daf0683c076f24cc6e6f8b8dbf497d48bfda74e5105c20efeda5658b7`;
  the receipt records `inputs_unchanged: true`.
- The staged `kphasor.dll` and `binkw32.dll` match the candidate build hashes
  stated above.  The stage/prefix/checkpoint directories are private run
  artifacts and were retained; no original save, source asset, source INI,
  source DLL, source log, or user display process was changed.

## Immutable-source follow-up

The candidate directory
`/home/brunner56/kp-live-20260922/harness-snapshots/task7-supported-console-20260927`
does contain a `kpharness` package, but it does **not** contain
`display_backends.py` or `gamescope_xwayland.py`.  It is therefore not a safe
immutable source snapshot for this Gamescope backend.  The current worktree
has the required backend as untracked/modified files, including
`display_backends.py`, `gamescope_xwayland.py`, `console_protocol.py`,
`console_steps.py`, `owned_x11.py`, and `physical_console.py`; `creative.py`
itself has a `37 insertions / 7 deletions` worktree diff.  No immutable
snapshot candidate with the required Gamescope implementation and an identity
manifest was found during this bounded follow-up, and no additional launch was
attempted.


## 2026-09-27 host-only provenance repair follow-up

No additional live launch was performed. The snapshot driver now uses an
absolute interpreter with `-I -S`, preserves its standard library path, disables
bytecode writes, and prepends the verified snapshot runtime. A real subprocess
CWD/PYTHONPATH shadow-package test verifies the imported package/module origins.
A second real snapshot subprocess loads repository discovery and curation
metadata, and the actual creative entrypoint completes `--help`.

Repository discovery now uses the explicitly bound repository root carried by
the snapshot driver. The snapshot verifies external `tools/kpdiscover.py`,
curation metadata, app signatures and address JSON identities before use.
Creative binds its existing route/Lua/built-runtime input hashes and bounded
source-preservation receipt into an atomic run manifest before directory claims;
it rechecks the binding after boot and teardown. Existing deployed-runtime
comparison remains authoritative. This is deliberately the existing bounded
creative contract, not a complete build-input or retail-asset closure.

Lease publications fsync the containing directory. Invalid readiness retains a
sanitized candidate PID/start/display, observed identity and available process
relationship, without assigning ownership. Successful validation clears that
rejected candidate. Cleanup exceptions publish terminal failure, retain the
first cleanup error across retries, and retain verified-group cleanup rules.
Runtime verification rejects unlisted data, symlinks and special files.

Validation: Gamescope host suite 33/33; creative suite 28/28 (rerun after the
metadata compatibility adjustment). No game, display or recorder was launched.

Remaining acceptance limits: no complete build-source/toolchain manifest, no
run-wide source-change lock, and no comprehensive secret scrub gate covering
arbitrary external logs. Python module identities are checked when binding the
run, but no adversarial concurrent filesystem mutation guarantee is claimed.
Actual no-XAUTHORITY readiness and zombie leader cleanup findings are tracked
separately in `/home/brunner56/kp-live-20260922/task7-actual-boot-cause.md`.

### Readiness-child provenance review repair

The production readiness helper now starts the absolute interpreter with
`-I -S -B` and an explicit runtime import bootstrap. This prevents the separate
child interpreter from creating unlisted bytecode in the closed snapshot and
removes caller CWD/PYTHONPATH package shadowing. A real host subprocess executes
the exact helper bootstrap without its readiness arguments (imports then exits
2, without display launch or waiting), from an injected shadow-package CWD;
subsequent snapshot verification and absence of `.pyc` files both pass.

Candidate observed start identity and available process relationship are now
captured before X11 authority validation. The DISPLAY-only rejected-candidate
test retains these diagnostics while `owner.ready_child` remains null.

Validation after this narrow review repair: Gamescope host suite **35/35**.
No Gamescope, Wine, display, recorder or game process was launched. Authority
policy and zombie-leader boot cleanup remain separate work.
