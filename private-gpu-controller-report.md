# Owned GPU display with SSD-backed private /tmp

Standalone acceptance passed 2026-09-22, run `/home/brunner56/kp-live-20260922/private-gpu-runs/20260922-141634`. No Wine or game process was launched. No product source, existing private driver, quota, unrelated file or external display was modified.

## Commands

Display-only proof (safe standalone test):

```sh
/usr/bin/python3 /home/brunner56/kp-live-20260922/private_gpu_controller.py smoke
```

Controller-owned next live run, after its own gate/authorization:

```sh
/usr/bin/python3 /home/brunner56/kp-live-20260922/private_gpu_controller.py run <arguments normally passed to live_example_gpu.py>
```

The wrapper passes all arguments unchanged to the existing private live driver. It retains that driver's canonical live lock, source receipt comparisons, staged tree, scenario checks and teardown. Before entering its PID namespace, run mode refuses an existing host `swkotor.exe` process. The actual live command was not exercised by this display-only task.

## Mechanism

The new private wrapper launches the entire controller inside bwrap, with a new PID and network namespace, an SSD directory bound over `/tmp`, private XDG runtime/cache directories, standard private device nodes and explicit `/dev/dri` device binding. It clears desktop DISPLAY/WAYLAND/XAUTHORITY and display-reuse settings. Isolated network sockets prevent the owned `:0` display from borrowing or colliding with the unrelated desktop's `:0` socket. Parent and child namespace identities are retained in the run receipts.

The existing product preflight checks `quota -s` for any full tmpfs row, which can misidentify a shadowed host tmpfs as the effective `/tmp`. The private wrapper overrides that function only in its own process after proving `/tmp` and the owned backing have exactly matching device/inode identity and ownership. It then checks at least64MiB free and writes/fsyncs a1MiB probe on that exact mounted filesystem. It neither changes quotas nor treats a successful tiny write as enough. `findmnt` can show both a shadowed tmpfs and the final btrfs bind; the inode/device verification determines the effective path.

GPU access requires `--dev /dev` and `--dev-bind /dev/dri /dev/dri`. Without the render-device bind the first attempt selected llvmpipe and failed allocation; adding only the render bind allowed Vulkan but left `/dev/null` inaccessible for Xwayland. The final combination succeeded. Failed attempt receipts are preserved at141446 and141513; no foreign process was killed.

## Proof

- `smoke.json`: mount and loopback verified, `accelerated:true`, nested Wine display/loopback verified, display parent reaped, `game_launched:false`.
- `renderer.txt` and `nested-renderer.txt`: direct rendering Yes; AMD Radeon RX460 Graphics; Accelerated yes; OpenGL4.6 compatibility.
- The nested check uses the existing `session.wine_command` unchanged to execute `glxinfo`, proving its private Wine `/tmp` retains the owned X11 socket mount and render-node access. A second nested Python client connected to a controller localhost socket and sent an independently checked payload. No Wine executable was run.
- `mount.json`, parent/child namespace JSON and `command.json`: exact bwrap/mount provenance.
- `teardown.json`: `remaining_owned_pids:[]`, `originals_unchanged:true`.
- `backups/`, `originals-before.json`, `originals-after.json`: preserved copies and matching SHA256 receipts for gpu_display.py, gpu_display_child.py, live_example_gpu.py and live_preflight.py.

Gamescope logs include unavailable PipeWire capture and an X I/O message during intentional teardown. Acceleration and nested X clients succeeded; the existing live controller captures through X11/ffmpeg, not PipeWire. This proof does not claim actual game launch, runtime DLL behavior, recording, or scenario acceptance.

All wrapper output/cache/temporary directories are under the private controller run on SSD. The wrapper reaps its own gamescope process group, waits for it, and exits its PID namespace, then checks host `/proc` for remaining processes bearing the exact run marker. It never deletes or relocates another owner's `/tmp` contents. The namespace and display are fully torn down before handoff.

## Optional frozen harness snapshot

`KP_PRIVATE_HARNESS_SNAPSHOT=/absolute/frozen/scripts-harness-directory` adds a read-only bind over the exact product `ROOT/scripts/harness` location inside the namespace. This preserves the harness's physical path assumptions while insulating a live run from concurrent product edits. The wrapper requires a real directory containing `kpharness/__init__.py`, rejects symlinks, records a complete file SHA256 manifest, and checks it again after the controller exits. Existing private drivers remain unchanged. Set the variable for both `smoke` and the subsequent controller-owned `run` command. Syntax validation passed; the snapshot-specific smoke is awaiting the controller's frozen directory handoff.
