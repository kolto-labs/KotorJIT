# Task 7 animated-pattern diagnostic: readiness scout

Date: 2026-09-27. Read-only. No display, Gamescope, Wine, FFmpeg capture, or
lock-file operation was launched. The only host commands run were `command -v`,
`rpm -q`, `file`, `readelf`, `sha256sum`, `grep -c` on binaries, `ps`, `ss`,
`/proc/locks` reads, option listings, and one `mpv --vo=null --ao=null
--frames=3` decode of `av://lavfi:testsrc2` (null output, no display).

Worktree: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`
(paths below are relative to `scripts/harness/kpharness/` unless absolute).

## 1. Existing entry point? No.

There is no entry point that launches a non-game client in the private
Gamescope root and records it through the new capture path with the four
external commitments. `rg -i 'animated|testsrc|glxgears|vkcube|xeyes|non-game'`
over `scripts/harness`, `tools/kpharness_creative_test.py`, and
`docs/creative-runner.md` finds only the prose requirement at
`docs/creative-runner.md:480`.

Why the existing pieces cannot be used as-is:

| Piece | Why it does not cover the diagnostic | Referent |
|---|---|---|
| `kpharness.creative` CLI | `--script` and `--route` are required, and the only Gamescope session is K1 under Wine. | `creative.py:386-387`, `creative_wine.py:204-244` |
| `display_gate.py` (the display-only gate driver) | This one-off driver lives in the run dir. It starts and closes a lease. It never starts a client, a recorder, markers, or a ledger. | `display-only-runs/20260927-100845-8cd691c3/display_gate.py:117-175`, invoked as `/usr/bin/python3.14 -I -S -B display_gate.py --child` (`invocation.json`) |
| `creative_accept` (media, route, FFprobe, and ledger SHAs) | It requires `backend == linux-wine-k1-gamescope`, schema 2, and `route_source`. It also needs `execution_evidence_ready()`. That function requires a route report, `physical_console_correlated`, and cleanup order `recorder, game_wine, display`. A non-game run cannot satisfy these. | `creative_accept.py:481-512`, `display_backends.py:749-800` |
| `X11WindowRecorder` (the capture path) | Reusable as-is. It takes a lease, a verifier, and an `OwnedWindow`, plus named markers read from any text log. | `recording.py:482-531`, `recording.py:893-975`, `recording.py:400-436` |
| Window discovery | Reusable. It needs exactly one visible window found by `xdotool search --onlyvisible --pid <pid>`, so the client must set `_NET_WM_PID`. The title must stay stable because the verifier compares it every 250 ms. | `display_backends.py:326-390` |
| Coverage | The window must sit at X=0, Y=0 at exactly the lease size (1024x768). | `recording.py:703-724` |
| Static recomputation | `_root_capture_matches(...)` and `_cadence_evidence_passed(cadence, capture, continuous, route={})` can be called without a game. With `route={}` and no `set_route_interval`, the route summary must be absent, and it is. | `display_backends.py:405, 569-580, 616-681` |
| Ledger | `initialize_cleanup_ledger(run_dir)`. The empty-ledger head is `b80aca1257084bb4969555b6b98b2635e551fecd5d400f55af1e877bb0982f2e` (computed with `printf '{"records":[],"schema":1}\n' \| sha256sum`). | `creative_accept.py:196-201` (file lines) |

### What is missing (smallest diff)

**A. One new run-dir driver `animated_gate.py`, copied from `display_gate.py`.**
No source change is needed for the capture itself.

Supervisor (reuse `display_gate.py:177-266` almost verbatim):

- Take the canonical lock (`LOCK_EX|LOCK_NB`).
- Run the process preflight. Add `mpv` to the watched command names.
- Record protected-socket identity for X0, X94, and X100.
- Run `create_snapshot(SOURCE, SNAP)`, then `verify_snapshot(SNAP, source_root=SOURCE)`, then chmod the snapshot read-only.
- Write `diagnostic-route.json` and compute its SHA before launch. Its contents: client argv, marker regexes, durations, and geometry.
- Compute the FFprobe ELF SHA before launch.
- Print both digests before the child launches so the parent can commit them externally.
- Run the child with `pass_fds=(lock.fileno(),)`.
- After the child: verify the snapshot is unchanged and source-equal, check protected sockets, confirm owned PIDs are gone, remove the private socket, and confirm the lock is free.

Child steps (all imports from `SNAP/runtime`):

1. Start `GamescopeXwaylandLease(RUN, 1024, 768, xwayland_verifier=verify_candidate)`, as in `display_gate.py:135`.
2. Run `initialize_cleanup_ledger(RUN)`. Record the head SHA.
3. Popen the client with `env=lease.game_environment({})` and `start_new_session=True`. Record the PID and start time.
4. Poll `discover_owned_x11_window(lease, [pid], run=subprocess.run, monotonic=time.monotonic)` for up to 10 s. Then create `OwnedWindowVerifier(lease, run=subprocess.run)`.
5. Create `X11WindowRecorder(RUN, verifier=v, lease=lease, ffmpeg='/usr/bin/ffmpeg', ffprobe='/home/linuxbrew/.linuxbrew/bin/ffprobe', named_markers={'pattern_start': r'\[kp-diag\] start', 'pattern_end': r'\[kp-diag\] end'}, cadence_start_marker='pattern_start', cadence_end_marker='pattern_end')`. Then call `.start(window, RUN/'diag-native.log')`.
6. Wait 3 s, then append `[kp-diag] start\n` to the log. Wait 30 s, then append `[kp-diag] end\n`. 30 s at 60 Hz is 1800 slots, so the 0.5% limit allows 9 missing slots. Wait 1 s more.
7. Stop in the ordered cleanup: `recorder.stop()`, then SIGINT the owned client (SIGKILL after 2 s), then `lease.close()`. Record `cleanup.order = ['recorder','source_process','display']`.
8. Write `diagnostic-run.json` with `recorder.receipt()`, the window receipt, the lease receipt, and the cleanup record.

**B. A diagnostic acceptance verifier. About 60 lines in `creative_accept.py`, or in the driver.**
It reuses the existing private helpers so there is no second probe path:

- `cleanup_state_clear(run, ledger_sha)`.
- `_root_capture_matches(capture, lease_id=..., xdisplay=..., width=1024, height=768, window=window_receipt)`.
- `_cadence_evidence_passed(cadence, capture, media['continuous'], {})`.
- `media['continuous']['sha256'] == cadence['pts_artifact']['master_sha256'] == supplied media SHA`.
- `sha256(diagnostic-route.json) == supplied route SHA`.
- `cadence['probe_tool']['sha256'] == supplied FFprobe SHA`.
- A fresh probe through `_stable_unlinked_fd` and `_verified_tool_fd`, then `probe_frame_pts(Path('/proc/self/fd/M'), Path('/proc/self/fd/T'), pass_fds=(M, T))`. This is the same descriptor transport as `creative_accept.py:520-547`. The result must equal `ffprobe-cadence.json`.

The shape would be
`verify_diagnostic(run_dir, *, media_sha256, route_sha256, ffprobe_sha256, cleanup_ledger_sha256)`,
with a sibling `--diagnostic` CLI mode that takes the same four flags.

**C. A content check, observation only.** See the risk in section 4.
Decode the acceptance interval and record distinct-frame ratio and luma
statistics.

Do not change `recording.py`, `display_backends.py`, or `creative.py`. With no
source diff, the fresh snapshot stays equal to the reviewed round-9 source.
Putting B in the driver avoids touching reviewed source. Putting it in
`creative_accept.py` needs a test plus a rerun of the host-only tests before the
snapshot is taken.

Exact command: none exists yet. After A and B, it would be (host, not container):

```sh
/home/brunner56/.local/bin/host-cmd /usr/bin/python3.14 -I -S -B \
  /home/brunner56/kp-live-20260922/animated-runs/<RUNID>/animated_gate.py
```

The parent then runs the verifier with
`--media-sha256 <continuous.mp4> --route-sha256 <diagnostic-route.json, committed pre-launch> --ffprobe-sha256 bb675d2732189c58ad566b4502b4e0638867467d9ef90081e1b67ffc083c0ac6 --cleanup-ledger-sha256 <head at review>`.
The FFprobe SHA is for `/home/linuxbrew/.linuxbrew/Cellar/ffmpeg/9.0.1_1/bin/ffprobe` (host `sha256sum`).

## 2. Host animated client

Host `command -v` results:

- Present: `glxgears`, `vkcube`, `mpv` (0.41.0 rpm), `ffplay` (brew 9.0.1), `xterm`, `es2gears_x11`, `eglgears_x11`, `glmark2`.
- Missing: `xeyes`, `xclock` (xorg-x11-apps not installed).

Hard constraint from `display_backends.py:340`: the client must set `_NET_WM_PID`.
Check used: `grep -c _NET_WM_PID` on each binary or its window library.

| Client | `_NET_WM_PID` string | Usable |
|---|---|---|
| glxgears, vkcube, es2gears_x11, eglgears_x11 | 0 | No. Discovery finds 0 windows. |
| mpv | 1 | Yes |
| ffplay | 0 in binary; 1 in `/home/linuxbrew/.linuxbrew/opt/sdl3/lib/libSDL3.so.0.4.16` (via sdl2-compat) | Probably |
| xterm | 1 | Yes, but it does not animate at 60 Hz |

**Recommendation: mpv playing lavfi `testsrc2` at 60 fps.**

```sh
/usr/bin/mpv --no-config --really-quiet --terminal=no --vo=gpu --ao=null --osc=no --osd-level=0 \
  --input-default-bindings=no --border=no --geometry=1024x768+0+0 --keepaspect-window=no \
  --title=kp-diag-testsrc2 --force-window=immediate --loop-file=inf \
  "av://lavfi:testsrc2=size=1024x768:rate=60"
```

Why this client:

- It is a system package in `/usr/bin`, so no wrapper sits in front of it.
- It sets `_NET_WM_PID`.
- `--title` keeps the title fixed, which the verifier needs.
- `testsrc2` has a moving pattern and a frame counter, so every one of the 60 source frames per second is different. The frame changes are known.
- Verified: `mpv --vo=null --ao=null --frames=3 av://lavfi:testsrc2=size=1024x768:rate=60` exits 0 on the host.
- `--vo=x11` is the fallback if GL misbehaves.

Not verified in a display:

- mpv presents one new frame per 16.7 ms under headless Gamescope at `-r 60` (`gamescope_xwayland.py:210`).
- Only one visible window appears.
- The window reports geometry exactly 0,0 at 1024x768.

Note that capture cadence does not depend on the client redrawing. x11grab samples the root on its own clock. Per-vsync redraw matters for the content check and for realistic compositor load.

ffplay is second choice. Its brew binary is outside the rpm set, and `_NET_WM_PID` comes indirectly through SDL3 (unverified at runtime).

## 3. Snapshot and the four SHAs

**Snapshot.** Use `kpharness.gamescope_snapshot.create_snapshot(source_root, snapshot)` (`gamescope_snapshot.py:146-183`):

- It copies the static import closure of `kpharness.creative` and `kpharness.gamescope_snapshot`.
- It refuses the snapshot if the source changes during the copy.
- It writes a canonical manifest plus its `.sha256`.

Check it with `verify_snapshot(snapshot, source_root=SOURCE)` (`:211-243`). The CLI form is `python3 -m kpharness.gamescope_snapshot create --source-root scripts/harness --snapshot DIR`, then `verify`. The display gate calls these in-process (`display_gate.py:193-201`), and so does K1 `control.py:86-87`.

A fresh snapshot is required. The current closure differs from `task7-display-only-topology-20260927-100845-8cd691c3` in `creative.py`, `creative_accept.py` (newly in the closure), `display_backends.py`, and `recording.py` (computed with `_file_entries` against that manifest).

**The four SHAs** (existing CLI: `creative_accept.py:586-612`; docs: `docs/creative-runner.md:73-78, 92-98, 425-431`):

- **Media SHA** (`--media-sha256`): sha256 of `continuous.mp4`. It must equal `media.continuous.sha256` and `pts_artifact.master_sha256`. It is taken from the file after the run.
- **Route SHA** (`--route-sha256`): must equal `route_source.sha256`, which is the run-local route copy (`creative.py:240`). It is chosen before launch. The diagnostic has no route, so the pre-launch `diagnostic-route.json` is the analogue. This needs the new verifier in 1B.
- **FFprobe SHA** (`--ffprobe-sha256`): must equal `cadence.probe_tool.sha256`. `probe_tool_identity()` resolves `shutil.which(ffprobe)` to its real path (`recording.py:227-236`), so the value is the Cellar ELF digest above. Acceptance execs it only as `/proc/self/fd/N` (`creative_accept.py:345-360`). The ELF uses an absolute RPATH and interpreter `/home/linuxbrew/.linuxbrew/lib/ld.so` (`readelf`), so fd-exec works. fd-exec itself is unverified here.
- **Cleanup-ledger SHA** (`--cleanup-ledger-sha256`): the SHA of the current `ffprobe-cleanup-ledger.json`. It is initialized at run start (`creative.py:201-202`) and must have no unresolved failure (`cleanup_state_clear`). The empty-ledger head is `b80aca12...2f2e`. If the fresh probe appends a failure, `--recover-cleanup` prints the new head.

## 4. Blockers and risks on this host

These are current host observations, from `ps` via host-cmd.

1. **Unrelated Wine workload is running (blocker).** umu/GE-Proton PotPlayer is up, with `wineserver` PIDs 2547167 and 2700516 plus several `winedevice.exe`. The copied preflight refuses on the `wineserver` command name (`display_gate.py:26,40-41,186-188`), and the gate check `no_game_wine_ffmpeg` fails. The user must close PotPlayer, or the parent must explicitly allow unowned Wine. I recommend closing it.
2. **A concurrent harness test run is active.** PID 2682563 runs a host loop over `kpharness_*_test.py` in this worktree. It owns Xvfb `:93`, PID 2703384, with `/tmp/.X93-lock`. The diagnostic must wait for it to finish. The source must not change between snapshot and run, which `create_snapshot` enforces.
3. **Jellyfin (PID 1574) runs its own ffmpeg when transcoding.** An `ffmpeg` process name would trip the preflight. It is idle now; recheck at launch.
4. **FFmpeg resolution.** On the host, `PATH` puts `~/.local/bin/ffmpeg` (a bash wrapper symlink to `_host_wrap_template`) ahead of `/usr/bin/ffmpeg`. The wrapper `exec`s host-cmd, which `exec`s `/usr/bin/ffmpeg`. PID and inherited FDs survive that chain in principle (unverified). The prior K1 run recorded argv[0]=`ffmpeg` with the tool `~/.local/bin/ffmpeg` (`preflight-launch.json`). Pass `ffmpeg='/usr/bin/ffmpeg'` explicitly. It is an ELF, rpm 8.1.2, sha256 `abecc2e8...f27`, and lists the `x11grab` and `lavfi` devices. The receipt check accepts any argv[0] (`display_backends.py:641`).
5. **Container versus host.** This agent shell is a podman container without gamescope, ffprobe, mpv, or xdotool. host-spawn would break `/proc/self/fd/N` transports. The driver must run on the host with `/usr/bin/python3.14 -I -S -B`, like the display gate.
6. **Root capture content (high risk, unverified).** Gamescope's Xwayland runs `-rootless` (`display-only-runs/.../lease-before-close.json` owned_topology: `Xwayland :1 -rootless -core ...`). Root GetImage and ShmGetImage on rootless Xwayland may return black or stale pixels, because Gamescope composites redirected windows itself. If so, every cadence gate can still pass while the video is blank. Add the content check from 1C: distinct-frame ratio near 100% in the acceptance interval for `testsrc2`, and nonzero luma variance. A black capture must stop K1 authorization even if cadence passes. The same rootless path is where MIT-SHM root capture might still fail. That case is `capture_shm_fallback`, and the brief says to stop there.
7. **Disk.** `/home` has 25 GB free (95% used). That is more than the 1 GiB gate, and about 30 s of 1024x768 CRF 28 video is small.
8. **Lock and sockets.**
   - The canonical lock inode 40769209 has no entry in `/proc/locks`, so it is free now.
   - X0, X94, and X100 are present.
   - The historical X1 socket and lock are still quarantined as `.task7-quarantine-20260927-100845-8cd691c3-*`.
   - `/tmp/.X1-lock` is absent.
   - The K1 preflight asserts the quarantine is unchanged (`control.py:64-65`). Keep that assertion.
9. **Clock alignment.** Marker `capture_seconds` is measured from Popen start. The PTS origin is FFmpeg's first frame. Startup latency is retained but not subtracted (`recording.py:431`, `clock_alignment`). Surround the 30 s window with at least 3 s of lead and 1 s of tail so the acceptance interval is not trimmed.
10. **Version mismatch.** Capture uses FFmpeg 8.1.2 and probing uses FFprobe 9.0.1. The receipt binds whichever FFprobe is configured, so this is not a blocker.

## Claim blocks

claim: No existing entry point runs a non-game animated client through the new capture path with the four commitments.
referent: `creative.py:386-387`, `creative_accept.py:490-491`, `display_backends.py:756,780-791`, `display_gate.py:117-175`, rg result.
checked: file reads plus rg.
verdict: holds.
confidence: high. A driver elsewhere in the repo or run dirs that rg missed would change this.

claim: mpv is the only system client present that animates at 60 Hz and sets `_NET_WM_PID`.
referent: host `grep -c _NET_WM_PID` table; mpv null-output decode rc=0.
checked: host-cmd.
verdict: holds statically. The in-display window count, geometry, and cadence are unverified.
confidence: medium. The live window geometry under Gamescope could change it.

claim: Unrelated Wine processes block the copied preflight.
referent: `ps` output (wineserver 2547167, 2700516); `display_gate.py:26,186-188`.
checked: host ps.
verdict: holds at scout time.
confidence: high for now. PotPlayer exiting removes it.

claim: Root capture on rootless Xwayland may record black frames.
referent: `-rootless` argv in the display-only lease evidence.
checked: argv only. No capture was run.
verdict: unresolved (`unverified`).
confidence: low. The diagnostic's content check decides it.
