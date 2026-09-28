# Record a creative run on your own install (draft)

> **Status: not ready.** No run has passed the capture check yet.
> The capture check is known to fail on the one tested host.
> Acceptance cannot succeed until it passes.
> This guide shows the steps so you can check your setup.
> Steps marked *(pending)* may change before release.
> The DLLs in the release ZIP have not been used in a creative run yet.

The creative harness runs a K1 route with a Lua example.
It records the game window to a video.
You watch the video and accept it.
Then you can cut a short MP4 and GIF from the accepted video.

## Check what is supported

Only one setup has live evidence:

- Game: KotOR 1, GOG version 1.03.
- Runtime: Wine, inside a private Gamescope display.
- Desktop: KDE Plasma on Wayland.
- Host: Linux with a GPU render node. The harness refuses software rendering.

| Part | Status |
|---|---|
| Boot | Worked in one live run |
| F12 console | Worked in one live run |
| Lua scripts | Worked in one live run |
| Save load | Worked in one live run |
| Route steps | Worked in one live run |
| Video capture | Known to fail. Frames were dropped. The rate fell to 54 FPS. |
| Acceptance and export | Tested offline only. Never run on a real passing video. |
| K1 Steam | Known to fail. The game VM never binds. |
| K2 | Not supported on this backend. |
| GNOME | Not attempted. |
| Xorg | Not attempted. |
| Windows | Not attempted. |
| macOS | Not attempted. |
| Crostini | Refused. |

The package holds no game files, saves, videos or images.
You need your own K1 install and your own save.

## Check your host

From the unpacked package folder, run:

```sh
python3 tools/creative_host_check.py
```

It prints one line of JSON. It opens no display.
It runs `ffmpeg -version` and `ffprobe -version` to check each tool. It starts nothing else.
Look for `"ok": true`.

- `missing` means the program is not on your `PATH`.
- `wrapper` means the first match is a script, not a program file.
- `not_the_tool` means the program file did not answer `-version` as that tool.
- For `ffmpeg` and `ffprobe`, a wrapper or `not_the_tool` blocks the run.
- `elf_elsewhere` names a program file found later on your `PATH`. Treat it as a hint. Check it with the next section.
- `render_nodes` must list at least one `/dev/dri/renderD*` device.

You also need Python 3.12 or newer and Wine with 32-bit support.

## Find your FFmpeg and FFprobe

Use the FFmpeg package from your Linux distribution.
It installs `/usr/bin/ffmpeg` and `/usr/bin/ffprobe` on most systems.
The capture limits were measured with that build.
Do not use a wrapper script. Do not use a second FFmpeg build from another folder.

Check both files:

```sh
file -L /usr/bin/ffmpeg /usr/bin/ffprobe
/usr/bin/ffmpeg -version | head -n 1
/usr/bin/ffprobe -version | head -n 1
```

`file` must report an ELF program for each.
Each `-version` line must start with the tool name.
Pass these exact paths with `--ffmpeg` and `--ffprobe` on every command below.
The examples use `/usr/bin/ffmpeg` and `/usr/bin/ffprobe`.

## Create your logs and runs folder

```sh
mkdir -p ~/kp-runs
touch ~/kp-commitments.log ~/kp-inputs.log
```

Keep both logs outside `~/kp-runs`. The tools refuse a log inside it.

- `~/kp-commitments.log` gets one line each time the cleanup ledger changes. The tools write it.
- `~/kp-inputs.log` gets the hashes you record before a run. You write it with the next step.

Keep a copy of both logs somewhere else as well.

## Record your inputs before you launch

```sh
PYTHONPATH=scripts/harness python3 -m kpharness.commit_inputs \
  --route scripts/harness/scenarios/cursed/10_rancor_roulette.toml \
  --ffprobe /usr/bin/ffprobe \
  --log ~/kp-inputs.log --runs-dir ~/kp-runs
```

It adds one line to `~/kp-inputs.log` and prints it.
The line holds the route hash and the FFprobe hash.
You need both hashes later.
They must come from before the run, not from the run folder.

## Freeze the harness

```sh
PYTHONPATH=scripts/harness python3 -m kpharness.gamescope_snapshot create \
  --source-root scripts/harness --snapshot ~/kp-snapshot-1
PYTHONPATH=scripts/harness python3 -m kpharness.gamescope_snapshot verify \
  --snapshot ~/kp-snapshot-1 --source-root scripts/harness
```

The snapshot copies only the harness Python files.
Use a new snapshot folder each time.

## Run the route *(pending)*

Put `kphasor.dll` and `binkw32.dll` from the release ZIP in one folder.
Pass that folder with `--build-dir`.
These DLLs have not been used in a creative run yet. The one live run used a different build.

```sh
PYTHONPATH=scripts/harness python3 -m kpharness.gamescope_snapshot driver \
  --snapshot ~/kp-snapshot-1 -- \
  --backend linux-wine-k1-gamescope \
  --script cursed/10_rancor_roulette.lua --script probe/00_probe.lua \
  --route scripts/harness/scenarios/cursed/10_rancor_roulette.toml \
  --build-dir ~/kp-dlls --source ~/games/kotor \
  --checkpoint-root ~/kp-checkpoints/k1 --output ~/kp-runs \
  --ffmpeg /usr/bin/ffmpeg --ffprobe /usr/bin/ffprobe \
  --cleanup-commitment-log ~/kp-commitments.log
```

The first line it prints is the launch head.
The same line goes to `~/kp-commitments.log`.
A run always ends with `ok=false` and visual review pending.
That is expected. You review the video next.

See `docs/creative-runner.md` for every run option.

## Watch the full recording

Open `continuous.mp4` in the new run folder.
Watch all of it. Check three things:

- The game fills the frame.
- The effect plays in full.
- The scene returns to normal.

Then hash the file you watched:

```sh
sha256sum ~/kp-runs/RUN_ID/continuous.mp4
```

## Accept the run

```sh
PYTHONPATH=scripts/harness python3 -m kpharness.creative_accept ~/kp-runs/RUN_ID \
  --reviewer YOUR_NAME \
  --media-sha256 HASH_OF_THE_VIDEO_YOU_WATCHED \
  --route-sha256 ROUTE_HASH_FROM_INPUTS_LOG \
  --ffprobe-sha256 FFPROBE_HASH_FROM_INPUTS_LOG \
  --cleanup-ledger-sha256 LAST_HEAD_FROM_COMMITMENTS_LOG \
  --cleanup-commitment-log ~/kp-commitments.log
```

Find the ledger head in `~/kp-commitments.log`:

```sh
grep -F '"run_dir":"'"$HOME"'/kp-runs/RUN_ID"' ~/kp-commitments.log | tail -n 1
```

Use the `cleanup_ledger_sha256` value from that line.
The log stores the real path. If that `grep` finds nothing, run `readlink -f ~/kp-runs/RUN_ID` and search for that path.
The log holds lines for every run, so always pick this run's last line.
Do not hash the ledger file in the run folder to get it.
Every `LAST_HEAD_FROM_COMMITMENTS_LOG` in this guide means this value.

If it prints a `failure_id`, recover first:

```sh
PYTHONPATH=scripts/harness python3 -m kpharness.creative_accept ~/kp-runs/RUN_ID \
  --recover-cleanup FAILURE_ID \
  --cleanup-ledger-sha256 LAST_HEAD_FROM_COMMITMENTS_LOG \
  --cleanup-commitment-log ~/kp-commitments.log
```

Recovery adds a new line for this run. Accept again with the head from that line.

## Export a short clip *(pending)*

```sh
PYTHONPATH=scripts/harness python3 -m kpharness.creative_export ~/kp-runs/RUN_ID \
  --route-sha256 ROUTE_HASH_FROM_INPUTS_LOG \
  --ffprobe-sha256 FFPROBE_HASH_FROM_INPUTS_LOG \
  --cleanup-ledger-sha256 LAST_HEAD_FROM_COMMITMENTS_LOG \
  --start-seconds START --end-seconds END --gif-fps 25 \
  --ffmpeg /usr/bin/ffmpeg --ffprobe /usr/bin/ffprobe
```

Choose the start and end after you watch the video.
Start a little before the effect.
End after the scene returns to normal.
The clip lands in a new `accepted-media-*` folder inside the run folder.

## Check the clip

```sh
PYTHONPATH=scripts/harness python3 -m kpharness.export_verify \
  ~/kp-runs/RUN_ID/accepted-media-ID \
  --route-sha256 ROUTE_HASH_FROM_INPUTS_LOG \
  --ffprobe-sha256 FFPROBE_HASH_FROM_INPUTS_LOG \
  --cleanup-ledger-sha256 LAST_HEAD_FROM_COMMITMENTS_LOG \
  --ffprobe /usr/bin/ffprobe
```

It re-hashes the clips and re-probes them. It changes nothing.
It prints `"ok": true` only when every check passes.
One check is that `--ffprobe` is the same program you recorded before the run.
If `"shareable": false`, the `export.json` file holds local paths. Do not post that file.

## Share only what you own

The clip shows the game.
Check the game's terms before you post it.
Do not post the run folder or your logs. They hold your local paths.
