# Plan: package the creative harness and the accepted video/GIF flow

Date: 2026-09-27. Read-only planner. No repository edit, no Wine, game, Gamescope or FFmpeg capture, and the live-game lock was not touched. The only host commands were read-only existence and package checks (`head -c4`, `readlink -f`, `rpm -q`, `python3 --version`).

Worktree read: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation` (HEAD `ca329e5`, dirty). Paths below are relative to it unless absolute.

## Verdict

**Not packageable today.** Stages P0–P4 below can start now, using new files only. Nothing may ship until gates G1–G7 pass. The live gates run from the extracted package candidate, not the worktree, so the bytes that ship are the bytes that passed live. That is the same rule the console preview followed: 44/44 on the exact DLL pair.

- No run has passed the current capture gate. C7 is `known-failing` [K4] on the only in-tree Gamescope run (`20260927-102706-0523fa70`). The cause was an MIT-SHM fallback: 54.49 FPS, 1,293 drops, and a worst gap of 616.7 ms (`docs/capability-cells.md`, "Where capture stands").
- The animated diagnostic has never been launched. Round 10 failed both reviews. The round-11 brief exists (`task7-capture-cadence-round-11-brief.md`). There is no round-11 report yet: `.superpowers/sdd/lua-boundary-validation-plan/` holds reports only up to `round-10`.
- `creative_accept` and `creative_export` have never run against a real passing run. They are host-test-only.
- No standalone sidecar verifier exists.
- The capture modules are untracked (`git status`: `?? creative_accept.py`, `creative_export.py`, `capture_diagnostic.py`, `display_backends.py`, `gamescope_*.py`, `owned_x11.py`, `physical_console.py`), so the package cannot be bound to a commit yet.

## 1. What a user needs to run it on their own install

### Supported scope (honest cells)

Only one cell combination has live evidence for the creative path: **K1 GOG 1.03 (`k1_gog_103`, image `9c10e045…`) under Wine, inside the in-tree `linux-wine-k1-gamescope` backend, on a KDE Plasma Wayland host.**

| Cell | Status | Referent |
|---|---|---|
| C1–C6, C8 (boot, F12, Lua/`kp.*`, bridge, save load, gameplay subset, physical input) | live-accepted | [E6] run `20260927-102706-0523fa70`, `kphasor.dll fd8e069a…` |
| C7 capture | **known-failing** | [K4] same run: SHM fallback, cadence failure, head clipped at 2.4× |
| K1 Steam post-migration runtime | known-failing | [K5] VM never binds (`GetFirstPC` unavailable) |
| K2 (any) on the Gamescope backend | not admitted | the backend is K1-only. [N2] K2 has screenshots only. |
| GNOME Wayland, GNOME/KDE Xorg | not attempted | capability-cells matrix. [T2] is host-test-only. |
| Crostini | refused | [N6] refusal, not capability evidence |
| Native Windows and macOS | not attempted | `macos-k1`/`macos-k2` return unsupported before creating files |
| Legacy Xvfb (`linux-wine-k1`) | C7 not attempted | [N1] no cadence ever measured |

The earlier accepted excerpts (`media/native-size-swap`, `media/f12-native-size-swap`, `media/f12-giant-bow`) are trimmed excerpts from the private prototype. They do not meet C7 and must not be cited as proof of this flow ([K2]).

**DLL binding gap.** [E6] used `kphasor.dll fd8e069a…`. The shipped console preview is `4e14d0fe…` (`/home/brunner56/kp-release-20260927/build-artifacts.json`). No creative evidence exists for the shipped pair. Gate G4 must run on the exact pair the package tells users to install.

### Host requirements

"Verified here" means present on the evidence workstation (Fedora 44, kernel 7.1.9). The checks were `rpm -q` and an ELF-magic read on the host via `host-cmd`. The minimum versions are `unverified`.

| Need | Why | Verified here | Referent |
|---|---|---|---|
| Linux with pidfd and `PR_SET_CHILD_SUBREAPER` | cleanup signals only through pidfds; the controller must be a subreaper | kernel 7.1.9 | `docs/creative-runner.md` "Recovery is Linux-only", "DISPLAY-only admission" |
| Python 3.12+ | harness runtime | 3.14.7 (host), 3.12.3 (container, suites pass per ledger line 196). CMake floor 3.11 is `unverified` for these modules. | `CMakeLists.txt:32`, ledger |
| `gamescope`, `Xwayland` | private headless display | gamescope-3.16.25, Xwayland-24.1.13 | `display_backends.py:26` |
| `glxinfo`, `xdotool`, `xwininfo` | renderer proof, window checks | xwininfo-1.1.6. `glxinfo` and `xdotool` presence `unverified` (not checked, to avoid opening a display). | `display_backends.py:26` `GAMESCOPE_TOOLS` |
| `/dev/dri` render node, direct accelerated non-software renderer | the backend refuses llvmpipe | AMD RX 460 radeonsi per [E4]/[E6] | `display_backends.py:421,911` |
| `ffmpeg` as a native ELF, not a wrapper | recording | `/usr/bin/ffmpeg` is ELF (ffmpeg-8.1.2). **PATH `ffmpeg` here is the `~/.local/bin` bash wrapper.** | host check; `head -3 ~/.local/bin/ffmpeg` |
| `ffprobe` as a native ELF | acceptance opens, hashes and runs the ELF through `/proc/self/fd/N`. Scripts fail closed. | `/usr/bin/ffprobe` ELF; brew `9.0.1_1` ELF | `creative-runner.md:495-503`, `recording.py:231-239` |
| `mpv` | animated diagnostic client only | mpv-0.41.0 | `capture_diagnostic.py:49` |
| Wine with 32-bit support | runs K1 | wine-11.0 x86_64 + i686 | host `rpm -q` |
| `bwrap` (bubblewrap) | private Wine `/tmp`. Hard refusal if missing. | presence `unverified` | `session.py:241-242` |
| K1 GOG 1.03 install, read-only | game | user-supplied | — |
| A save or checkpoint the user owns | route input | user-supplied | — |
| `kphasor.dll` + `binkw32.dll` in a directory passed as `--build-dir` | runtime | from the release ZIP | `targets.py:97`; `creative.py:168-171` checks only these two files |
| An operator-owned commitment log outside the run directory | trust root for the cleanup-ledger head | — | `creative-runner.md:110-126` |

**Encoder caveat.** The round-11 content gate uses a noise floor calibrated on synthetic encodes from this host's `/usr/bin/ffmpeg` (brief R10-1). Other FFmpeg or x264 builds are `unverified` and may need recalibration.

**Tree shape.** The harness reads `data/addresses/` from its repository root (`session.py:768,812`). It also loads `tools/kpdiscover.py` dynamically (`discover.py:31-39`), which the static snapshot closure does not see. Its lock path falls back to `<root>/tmp/harness-locks/live-game.lock` when `git` is absent (`creative.py:86-91`). The package must therefore unpack as a repository-shaped tree. Whether an extracted tree without `.git` boots end to end is `unverified`; stage P1's dry-run test checks the fallback.

## 2. Package contents

### Include (allowlist, repository-shaped)

- `scripts/harness/kpharness/*.py`. This is the static closure from `gamescope_snapshot.runtime_module_paths(source_root, entries=("kpharness.creative", "kpharness.gamescope_snapshot", "kpharness.creative_accept", "kpharness.creative_export", "kpharness.capture_diagnostic"))`. Compute it; do not hand-list it.
- `tools/kpdiscover.py` (a dynamic import).
- `scripts/harness/scenarios/cursed/*.toml` routes that match the public examples. These are route text only; they name saves and include no save bytes. Showcase routes have no `scenarios/showcase` directory (`find scenarios -maxdepth 1 -type d` lists only `animation-memory`, `cursed`, `model-memory`), so where they live is `unverified`. Settle it in the P1 dry run.
- `scripts/examples/{cursed,showcase,probe}/*.lua` as curated by `ab387d6`. Retired examples are excluded.
- `data/addresses/k1_gog_103.json`, sanitized with the release `clean_bytes` rule (removes `reference_image` and private `source_path`/`corpus_path`/`signature_source`).
- User docs: a new `docs/user/creative-harness.md` (P2) and a frozen copy of `docs/creative-runner.md` taken after round 11.
- `LICENSE`, `ATTRIBUTION.md`.
- `manifest.json`, `packaging-receipt.json`, `source-provenance.json`.
- Optional: a pointer to the console preview ZIP by SHA-256 (`0388d080…`), not a copy of it. If the DLLs are bundled, they must be byte-equal to the pair G4 ran on.

### Exclude (deny even if an allowlist path matches)

- **Retail assets.** The release denylist (`.bif .key .mdl .mdx .rim .erf .sav .ncs .nss .bik .tlk .2da .utp .utc .uti .dlg .wav .mp3 .mp4`) needs `.gif .png .jpg .jpeg .webm .mkv .tga .dds .tpc .txi .gff .res .pth .lip` added. The current `/home/brunner56/kp-release-20260927/package.py` has `.mp4` but no image or GIF suffixes.
- **Game footage.** Any accepted MP4 or GIF shows retail game visuals. **No media enters the package, and this plan publishes none.** Media stays in the user's own run directory.
- **Run-directory evidence.** Exclude by name as well as suffix: `creative-run.json`, `continuous.mp4`, `accepted-media-*`, `sources/`, `executed-route.toml`, `ffprobe-*.json`, `gamescope-lease.json`, `gamescope-*-manifest.json`, `commitments.log`, `driver.log`, `ffmpeg.log`, `report.json`, `capture*.json`, `diagnostic-*.json`, `preflight.json`.
- **Private evidence.** Everything under `/home/brunner56/kp-live-20260922/`, plus `data/adjudication/`, `data/research/`, `.superpowers/`, `tmp/`, and the private Gamescope prototype scripts.
- **Saves and checkpoints.** `Saves/`, `saves/`, checkpoint roots, and `*.sav`.
- `__pycache__`, `.pyc`, `.git`, symlinks (refuse, as the release builder does).
- Unfinished work: `playback.py`, `pioneer.py` (unless the closure pulls them in; if it does, stop and review), projectile fixtures.

### Manifest and hash scheme (reuse the release builder)

Mirror `/home/brunner56/kp-release-20260927/package.py`:

1. Refuse symlinks in the source tree before staging.
2. Verify `source-provenance.json`: base commit plus `overlay_sha256` per file. This is the same scheme as the release, and it handles the untracked capture modules if G2 chooses an overlay over a commit.
3. Stage into a new directory (`mkdir(exist_ok=False)`).
4. Apply the sanitization rule and record each change in `packaging-receipt.json` `sanitizations`, with every excluded path in `exclusions`.
5. Write `manifest.json` as `{"scope": ..., "files": {relpath: sha256}}`.
6. Write the ZIP with mode `'x'` and a fixed top folder (`kotorphasor-creative-harness/`).
7. Check with `testzip()`, then re-read every manifest entry from the ZIP and compare its SHA-256.
8. Write `zip-sha256.txt` and `verification.json`.

Additions for this package:

- `snapshot_manifest_sha256`: the `gamescope-harness-manifest.json` hash from `gamescope_snapshot create` over the same closure. The user's run then carries a snapshot manifest the package can be compared against.
- `absolute_path_scan`: every packaged text file is scanned for `/home/`, `/run/media/` and `/Users/`. Today this finds `capture_diagnostic.py:52` (`DEFAULT_FFPROBE = '/home/linuxbrew/.linuxbrew/bin/ffprobe'`). **Ruling: this is a fix for the capture writer after round 11, not an allowlisted exception.** The fix is to require `--ffprobe` or default to `/usr/bin/ffprobe`. The brew default is a portability bug on hosts without Homebrew.
- `scope` string: "K1 GOG 1.03, Linux, Wine inside a private Gamescope display, KDE Plasma Wayland evidence host only. Other hosts not attempted."

## 3. Accepted-media flow (user-facing steps)

Draft text for `docs/user/creative-harness.md`. It follows plain copy rules: verb-first headings, no buzzwords. Commands marked *(round-11 pending)* may change and must be re-checked against the frozen `creative-runner.md`.

> ### Check your tools
> Run `readlink -f "$(command -v ffmpeg)"` and the same for `ffprobe`. Each must point to a program file, not a script. Pass those paths with `--ffmpeg` and `--ffprobe` on every command.
>
> ### Create a commitment log
> Make an empty file outside the folder where runs go, for example `~/kp-commitments.log`. The tools append one line to it each time the cleanup ledger changes. Keep a copy somewhere else as well.
>
> ### Record your inputs before you launch
> Make a second file next to your log, for example `~/kp-inputs.log`. Hash the route and the FFprobe program into it:
> `sha256sum ROUTE.toml "$(readlink -f FFPROBE)" >> ~/kp-inputs.log`
> The tool does not do this for creative runs. You need these values later, and they must come from before the run.
>
> ### Freeze the harness
> `gamescope_snapshot create`, then `verify` (commands in `creative-runner.md:25-30`).
>
> ### Run the route
> `gamescope_snapshot driver --snapshot … -- --backend linux-wine-k1-gamescope --cleanup-commitment-log ~/kp-commitments.log --ffmpeg … --ffprobe … --build-dir DIR_WITH_THE_TWO_DLLS …`
> The first line printed is the launch head. It is also written to your log. The run always ends with `ok=false` and visual review pending.
>
> ### Watch the full recording
> Open `continuous.mp4` from the run folder and watch all of it. Check framing, the effect, and the return to normal. Then hash the file you watched: `sha256sum continuous.mp4`.
>
> ### Accept the run
> `python3 -m kpharness.creative_accept RUN_DIR --reviewer NAME --media-sha256 … --route-sha256 … --ffprobe-sha256 … --cleanup-ledger-sha256 LAST_HEAD_FROM_YOUR_LOG --cleanup-commitment-log ~/kp-commitments.log` (flags from `creative_accept.py:813-823`).
> Take the head from your log. Never hash the ledger file in the run folder to get it.
> If acceptance prints a `failure_id`, recover first with `--recover-cleanup FAILURE_ID`, then accept using the new head.
>
> ### Export a short clip *(round-11 pending)*
> `python3 -m kpharness.creative_export RUN_DIR --route-sha256 … --ffprobe-sha256 … --cleanup-ledger-sha256 … --start-seconds S --end-seconds E --gif-fps 25 --ffmpeg /usr/bin/ffmpeg --ffprobe …`
> Choose start and end after watching. Include a calm lead-in, every phase, and the return to normal.
>
> ### Check the clip
> `python3 -m kpharness.export_verify RUN_DIR/accepted-media-ID` (added in stage P3).
>
> ### Share only what you own
> The clip shows the game. Check the game's terms before you post it. Do not post the run folder. It holds your local paths.

### Proof status of each step

| Step | Status | Referent |
|---|---|---|
| Snapshot create/verify/driver | live-used | [E6] run dir contains `gamescope-run-manifest.json` (`next-k1-preparations/20260927-task7-scale-102038-74cb804b/runs/20260927-102706-0523fa70/`) |
| Route run (behavior) | **live-accepted** | [E6] 23/23 steps, 3 physical F12 requests |
| Route run (capture gate) | **known-failing** | [K4] |
| Pre-launch route/FFprobe commitment | **not implemented for creative runs**. It is a manual user step. | `creative.py:209` prints only the ledger head. Only the diagnostic prints route and FFprobe SHA-256 (`capture_diagnostic.py:495-496`). |
| Human review | done once, result reject | `task7-k1-scale-run-review.md` |
| `creative_accept` | host-test-only; never run on a real passing run | backend suite (121 cases in round 10, ledger line 196) |
| `--recover-cleanup` | host-test-only | same suite |
| `creative_export` | host-test-only | `task7-post-accept-export-review.md` (host) |
| Sidecar verification | **not implemented** (no CLI) | the only check is inside `tools/kpharness_gamescope_backend_test.py:479` |
| Animated diagnostic | never launched | ledger lines 188, 206; round-11 brief |

### Sidecar defects to fix before publishing (capture writer, after round 11)

These are in `creative_export.py:86-103`, a file owned by the round-11 writer:

1. `run_dir` and every `artifacts[*].path` are absolute. They leak local paths if the sidecar is shared. Store paths relative to the export folder, and keep the absolute path only in a non-shared run receipt.
2. `settings.ffmpeg` and `settings.ffprobe` record the command string, not a resolved path and SHA-256. Use `recording.probe_tool_identity` (`recording.py:231`) for both.
3. The `--ffmpeg`/`--ffprobe` defaults are `'ffmpeg'`/`'ffprobe'` resolved through PATH (`creative_export.py:117-118`). On this host that picks the bash wrapper. Require explicit ELF paths, or refuse non-ELF, as acceptance already does for FFprobe.
4. The `--cleanup-ledger-sha256` semantics for export are being corrected in round 11 (brief minor: "fix the export example that reads the head from the run dir"). Freeze the user text only after that.

**Why a separate inputs log.** Today `creative_accept.py:295-325` validates the commitment log by `lstat` only: regular file, one link, outside the run dir. It appends one JSON line and never parses existing lines, so extra lines would not break acceptance. Round 11 adds "diagnostic re-validates the log before appending". A separate file keeps user-written lines out of the tool-owned chain whatever round 11 does. P4 writes to the inputs log too.

## 4. Packaging gates (in order; each blocks the next)

| Gate | Pass condition | Current state |
|---|---|---|
| **G1** Round-11 capture review | round-11 report exists; correctness and adversarial reviews both PASS; host and container suites green (creative, boot_repair, gamescope_backend, capture_diagnostic) | report absent; round 10 FAIL ×2 |
| **G2** Source binding | capture modules committed, **or** frozen as base `ca329e5` plus a per-file `overlay_sha256` map like `source-provenance.json` | 14 harness files untracked |
| **G3a** Package candidate | P1 builds a real candidate ZIP in a new staging directory from the G2-bound source. It passes every dry-run check. The candidate is extracted to a private directory. | builder not written |
| **G3** Animated diagnostic | one authorized `capture_diagnostic run` **from the extracted candidate**, verdict PASS on every criterion (`creative-runner.md:587-595`). **Stop branch:** if `capture_shm_fallback` occurs with verified geometry, packaging is blocked on a separately reviewed PipeWire adapter. | never launched |
| **G4** One accepted K1 clip | one K1 GOG run **from the extracted candidate**, on the **exact DLL pair to be shipped**. The run's `gamescope-run-manifest.json` `manifest_sha256` must equal the candidate's `snapshot_manifest_sha256`. This exercises the sanitized address table, the computed closure and the no-`.git` lock path. using `task7-k1-framing-plan.md`. It must pass capture, cadence (`gamescope-cadence-v1`), `game-capture-v1` content and framing, and reach human review → `creative_accept` PASS. | none. [E6] used a different DLL. |
| **G5** Export and verify | `creative_export` from the G4 run, then `export_verify` PASS on the sidecar and both outputs. The sidecar defects in section 3 must be fixed. | exporter host-only; verifier absent |
| **G6** Candidate unchanged | re-hash the candidate ZIP and every extracted file against `manifest.json`. They must equal the G3a bytes. Any change sends it back to G3a. | — |
| **G7** Release | copy the unchanged candidate into the release directory with `verification.json`. Do not rebuild. | — |

Only after G6 does the release step run. Its output is a new `/home/brunner56/kp-release-YYYYMMDD-creative/` directory, following the layout of the two existing ones. Publishing the ZIP (not any media) is a separate user decision.

## 5. Staged plan

File ownership during round 11: the capture writer owns `scripts/harness/kpharness/{recording,display_backends,creative,creative_accept,creative_export,capture_diagnostic}.py`, `tools/kpharness_{creative,gamescope_backend,capture_diagnostic}_test.py`, and `docs/creative-runner.md`. Other writers hold `src/**`, `scripts/examples/**`, `playback.py`, `cli.py`, `pioneer.py` and `session.py`. `CMakeLists.txt` has unrelated Mach-O and projectile hunks.

### Can start now (new files only; no overlap with the capture writer)

**P0. Dependency preflight (new file `tools/creative_host_check.py`).**
- Reads only. It runs `command -v`, `os.path.realpath`, and an ELF magic check (`\x7fELF`) for ffmpeg, ffprobe, gamescope, Xwayland, xdotool, xwininfo, glxinfo, bwrap, wine and mpv. It also checks that `/dev/dri/renderD*` exists and reports the Python version.
- It never launches a tool that opens a display.
- Output: one JSON line with one `ok`/`missing`/`wrapper` value per tool.
- Test: `tools/creative_host_check_test.py` with fake PATH directories holding an ELF stub, a shell-script wrapper and a missing entry. Expect `wrapper` for the script.

**P1. Package builder plus dry-run test.**
- `tools/package_creative_harness.py`. This ports the release `package.py` steps 1–8 above as functions: `select_files(source_root)`, `stage(dest)`, `write_manifest`, `write_zip`, `verify_zip`. The allowlist comes from `gamescope_snapshot.runtime_module_paths` (import only) plus the fixed extras in section 2. It takes `--source-root`, `--provenance`, and `--out` (must not exist).
- `tools/package_creative_harness_test.py`. It builds a fake repository-shaped tree in `tempfile.TemporaryDirectory()` and seeds it with a planted `.sav`, a `.gif`, a `continuous.mp4`, an `accepted-media-x/export.json`, a `data/adjudication/x.json`, a symlink, a `__pycache__`, and a `.py` containing `/home/someone/`. It then asserts:
  1. The ZIP contains none of the planted denylist items.
  2. The symlink makes the build refuse.
  3. The absolute-path scan fails the build, naming the file.
  4. Every `manifest.json` entry re-hashes equal from the ZIP, and `testzip()` is `None`.
  5. A second build into an existing `--out` refuses.
  6. The module set equals `runtime_module_paths(...)` for the fake tree.
  7. A `creative.shared_lock_path(root)` equivalent resolves to `<root>/tmp/harness-locks/live-game.lock` with no `.git`. This is a pure function call; it creates no lock.
  8. Sanitization removes `reference_image` from a seeded address JSON and records it.
- A third, read-only mode runs the builder against the real worktree into a temp dir with `--dry-run` (no ZIP write). It lists what would be included and the current path-scan hits. Expected today: `capture_diagnostic.py:52`. That is the referent for the section 3 ruling.

**P2. User guide draft (new file `docs/user/creative-harness.md`).**
- Section 3's draft text, section 1's tables, and the cell scope.
- Mark every command that depends on round 11 as pending.
- Plain copy: verb-first headings, one idea per sentence. Run the `plain-ui-copy` slop audit before finishing.

**P3. Sidecar verifier (new file `scripts/harness/kpharness/export_verify.py` plus `tools/kpharness_export_verify_test.py`).**
- Pinned to sidecar `schema: 1`.
- Checks:
  - each `artifacts[*]` SHA-256 and duration, re-probed with an explicit ELF FFprobe;
  - `source_video.sha256` equals the current master;
  - `accepted_receipt_sha256` equals the current `creative-run.json` bytes;
  - `accepted_execution_sha256` equals `visual_review.execution_receipt_sha256`;
  - the interval matches the MP4/GIF durations within the exporter's tolerance (`creative_export.py:73-76`).
- It imports `creative_accept.verify_acceptance` read-only and does not modify capture-writer files.
- Test: build a synthetic accepted run dir with fake probe rows (the pattern from `kpharness_gamescope_backend_test.py:479`, reimplemented without editing that file). Tamper each field once and expect refusal.
- It imports `creative_accept` and `display_backends`, which the capture writer is editing now. Rerun this test after G1, and bump the pin if round 11 changes the sidecar schema.

**P4. Commit helper (new file `scripts/harness/kpharness/commit_inputs.py`).**
- Given `--route` and `--ffprobe`, it hashes both and appends one JSON line (`kind: kpharness.input-commitment.v1`) to the commitment log. It uses the same log validation rules as `creative_accept.validate_commitment_log`, imported read-only.
- It closes the "manual pre-launch commitment" gap without touching `creative.py`.
- Test: `tools/kpharness_commit_inputs_test.py` covers a missing log, a symlink, a hard link, a log inside the run dir, and a normal append.

### After G1 (capture writer, or a new writer once round 11 is released)

**P5. Capture-module fixes.**
- The section 3 sidecar defects 1–3 in `creative_export.py`.
- The `capture_diagnostic.py:52` default.
- Optional: `creative.py` calls `commit_inputs` itself before `initialize_cleanup_ledger`.
- Each fix needs red-first regressions in the owned test files.

**P6. CTest registration (`CMakeLists.txt:33` foreach).**
- Add `kpharness_capture_diagnostic_test`, `kpharness_gamescope_boot_repair_test` (both missing today), `kpharness_export_verify_test`, `kpharness_commit_inputs_test`, `creative_host_check_test` and `package_creative_harness_test`.
- This must be a hunk-only edit, because the file carries Mach-O and projectile hunks from other writers. Coordinate through the orchestrator's index owner.

**P7. Freeze docs.** Copy the round-11 `docs/creative-runner.md` into the package staging list and finalize the P2 guide's pending commands.

### After G2–G5 (live, serial, under the canonical lock, orchestrator-authorized)

- **P8a.** Build the G3a candidate with P1 (non-dry mode, private staging) and extract it to a private directory.
- **P8.** From the extracted candidate, run G3 (diagnostic), then G4 (one K1 run on the shipped DLL pair), human review, accept, export, and `export_verify`. Record the referents in the ledger and in `docs/capability-cells.md`. Move the K1 · KDE Wayland · C7 cell only if every gate passes.
- **P9.** Run G6, then G7: copy the unchanged candidate into a new `/home/brunner56/kp-release-YYYYMMDD-creative/` directory with `manifest.json`, `verification.json` and `zip-sha256.txt`. Do not rebuild after the live gates.

### Tests summary

| Test file | Stage | Starts now |
|---|---|---|
| `tools/creative_host_check_test.py` | P0 | yes |
| `tools/package_creative_harness_test.py` (dry-run ZIP in temp dir, manifest re-hash, exclusions, path scan, no-`.git` lock fallback) | P1 | yes |
| `tools/kpharness_export_verify_test.py` | P3 | yes, pinned to schema 1 |
| `tools/kpharness_commit_inputs_test.py` | P4 | yes |
| owned capture tests for P5 fixes | P5 | after G1 |
| CTest registration | P6 | after G1, hunk-only |

## Unverified items

- Minimum Python below 3.12 for these modules.
- Presence of `glxinfo`, `xdotool` and `bwrap` on the host (not checked, to avoid display access; `rpm -q` for them was not run).
- Whether an extracted tree without `.git` boots end to end. The lock-path fallback is readable in `creative.py:86-91`, but no run has used it. G3 and G4 settle this by running from the candidate.
- The noise-floor calibration on other FFmpeg or x264 builds.
- Whether any GNOME, Xorg, Windows, macOS or K2 creative cell works. All are not attempted or not admitted.
- Whether `runtime_module_paths` over the five entries pulls in `playback.py` or `pioneer.py`. Check this in the P1 dry run; if either appears, stop and review.
