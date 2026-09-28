# KotorPhasor serialized live-run runbook (2026-09-27)

Written by a read-only planner. I edited no worktree file. I ran no Wine, game,
Gamescope, Xwayland, mpv or FFmpeg. I did not open the live-game lock. I read its
path, its `stat`, and `/proc/locks` (container and host), and nothing else.

- Worktree (`WT`): `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`, HEAD `ca329e5`, dirty tree.
- Main checkout (`MAIN`): `/run/media/brunner56/MyBook/Workspaces/KotorPhasor`.
- Live dir (`LIVE`): `/home/brunner56/kp-live-20260922`.
- Canonical lock (`LOCK`): `MAIN/tmp/harness-locks/live-game.lock`.
  - At 14:3x it was 0 bytes, inode 40769209 on dev 8,17, mtime 2026-09-26 23:49:27.
  - No `/proc/locks` row for that inode on host or in the container, so it was **not held** at planning time.
- Ledger: `WT/.superpowers/sdd/lua-boundary-validation-plan/progress.md`, lines 138-254 (the 2026-09-27 entries).

`unverified` means I have no referent for it. Nothing marked that way may be treated as a precondition that is met.

---

## 1. Global gates (apply to every item)

### G-RETRY: the harness relaunches the game by itself. Blocks items 1-9.

- `WT/scripts/harness/kpharness/session.py:74` sets `BOOT_ATTEMPTS = 5`, and `:75` sets `BOOT_RETRY_SETTLE = 3.0`.
- `_launch_and_connect` (`session.py:1394-1416`) calls `launch()` + `connect()` up to 5 times when the failure reason is `crash` or `boot timeout`. Between attempts it kills the game and runs a prefix-scoped `wineserver -k` (`:1419-1447`).
- The Gamescope creative session uses the same method: `creative_wine.py:226`, `channel = self._launch_and_connect()`. The plain `run` / `boot` path uses it through `session.py:1491`.
- `cli.py:418-430` has no attempts flag, and there is no environment knob.
- So a single authorized invocation can produce up to five game launches. That breaks "one launch per authorized attempt, no automatic retries."
- The 10:27 scale run showed exactly one `launching:` line (`next-k1-preparations/20260927-task7-scale-102038-74cb804b/launcher.log`). That shows the retry was not needed that time. It does not show the retry is off.
- **Unblock (one action, cheapest):** a writer adds an attempts override that forces 1. It also adds a host test that a first `crash` raises without a second `launch()`. An independent review must pass. Until then, the only alternative is an explicit written waiver from the user.
- **Update 2026-09-27 (single-launch writer, follow-ups).** The override exists in the worktree. It is **awaiting an independent review**, so G-RETRY is not closed yet. What it does:
  - `session.py` reads the variable **`KP_MAX_BOOT_ATTEMPTS`** (1..5). No other name works. Any other spelling, such as one missing `MAX_`, is silently ignored and gives 5 launches. A set but invalid value is refused before anything launches.
  - The creative runner (`kpharness.creative`, which the Gamescope `driver` runs) always passes `max_boot_attempts=1`. It refuses a bad `KP_MAX_BOOT_ATTEMPTS` before the lock, run dir, ledger head or stage claim. Only `--dev-max-boot-attempts N` raises the limit, and such a run is never acceptance-eligible.
  - `kpharness.sh boot` / `run` take `--max-boot-attempts N`. A bad flag or env value prints one line, exits 3, and launches nothing.
  - Every run writes `boot-attempts.json` into its run dir. The creative runner copies it into `creative-run.json` under `boot_attempts`. It refuses acceptance (`ok: false`; on Gamescope, `visual_review.status: refused_boot_budget`) unless the run shows exactly one launch under a limit of 1.
- **Preconditions for every Wine item (1-9), in the host shell that runs the item:**
  1. `export KP_MAX_BOOT_ATTEMPTS=1`, then `echo "$KP_MAX_BOOT_ATTEMPTS"` must print `1`. Copy the name exactly.
  2. Gamescope items (1, 7, 8, and 6a if it runs on Gamescope): build a **new** snapshot for this item from the worktree. Do not reuse an existing one. Every snapshot made before this fix has 0 hits and would allow 5 launches. That includes `next-k1-preparations/20260927-task7-scale-102038-74cb804b/harness-snapshot` and the three under `harness-snapshots/`.
     ```sh
     SNAP="$PREP/harness-snapshot"   # new, must not exist yet
     /usr/bin/python3.14 -I -S -B -c "import sys,runpy;sys.path.insert(0,'$WT/scripts/harness');runpy.run_module('kpharness.gamescope_snapshot',run_name='__main__')" \
       create --snapshot "$SNAP"
     test "$(grep -c KP_MAX_BOOT_ATTEMPTS "$SNAP/runtime/kpharness/session.py")" -ge 1 || echo 'STOP: snapshot lacks single-launch'
     test "$(grep -c dev-max-boot-attempts "$SNAP/runtime/kpharness/creative.py")" -ge 1 || echo 'STOP: snapshot creative runner lacks single-launch'
     ```
     If either line prints `STOP`, do not launch.
  3. Plain `kpharness.sh run` / `boot` items (2, 3): pass `--max-boot-attempts 1` as well as the variable.
- **Post-run check, required in every Wine item:** read `boot-attempts.json` in the run dir. For creative and Gamescope runs it is `$PREP/runs/<run>/boot-attempts.json`, and `creative-run.json` has the same values under `boot_attempts`. For `kpharness.sh run` / `boot` it is `<staged>/runs/<ts>/boot-attempts.json`.
  ```sh
  python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d["max_boot_attempts"], d["launch_count"]); sys.exit(0 if (d["max_boot_attempts"], d["launch_count"]) == (1, 1) else 1)' "$RUN/boot-attempts.json"
  ```
  It must print `1 1`. A missing file, or any other pair, means **FAIL: rule breach**. Do not check `max_boot_attempts_source`: creative runs record `kwarg`, not `env`, and that is expected.
- **Detection, required in every item even after the fix:** `grep -c 'launching:' session.log` (or `launcher.log`) must be `1`, and `grep -c 'boot attempt' session.log` must be `0`. Any other count means the run is **FAIL: rule breach**. Keep the evidence. Do not relaunch.
- **Banned for acceptance runs.** These entry points start `wine swkotor.exe` themselves, outside the launch limit. No item may use them, directly or through another script:
  1. `scripts/harness/live_session.sh` (`:88`)
  2. `scripts/harness/spike_headless_k1.sh` (`:101`)
  3. `scripts/harness/drive_k1_console.sh` (`:118`)
  4. `scripts/harness/measure_boot.sh` (`:79`)
  5. `scripts/harness/demo_play.sh` (calls `drive_k1_console.sh`, `:176`)
  6. `scripts/harness/gameplay_tests/lib.sh` (calls `live_session.sh`, `:92`)

  The D-route command for items 4, 5 and 9 is not written yet. When it is, grep it for all six names before launch.
- Item 0 is **exempt**. `capture_diagnostic.py` plays `/usr/bin/mpv` (`:56`) on a private Gamescope lease. It never starts Wine, and it has no retry path (`:22`, "no automatic retry").

### G-FOREIGN: foreign processes that the preflights refuse. Blocks item 0; may block Gamescope K1 items.

`ps` at planning time (14:3x) showed three kinds:

1. **The user's PotPlayer Wine.** `wineserver` pid 1099968 (started 13:42:11, prefix `~/.wine`), several `PotPlayerMini64.exe`, and `AutoHotkey64.exe`. **Only the user may close these. No agent may signal them.**
2. **The round-12 reviewer's calibration encodes.** `/usr/bin/ffmpeg ... testsrc2 ... libx264`, pids 2061206-2061226, started 14:32:44. They end when that review finishes.
3. **Jellyfin** (pid 1574, user `nobody`). It can spawn a transcoding `ffmpeg` at any time.

What each preflight refuses:
- `capture_diagnostic` refuses any process whose name matches `('wineserver','swkotor','gamescope','ffmpeg','ffprobe')` (`capture_diagnostic.py:77, :304, :331`). All three kinds above trigger it.
- The prep-dir pattern used for the 10:27 K1 run collects processes by `comm` name, including `wineserver`, `ffmpeg`, `xvfb` and `wine` (`control.py:21-33`). It then marks every match as conflicting except `xwayland` and `xvfb`, for any user (`control.py:56`, `conflicting_processes=[p ... if p['name'].lower() not in {'xwayland','xvfb'}]`).
  - At 10:27, `preflight-launch.json` had `conflicting_processes: []`.
  - So the PotPlayer `wineserver`, a reviewer `ffmpeg`, or a Jellyfin `ffmpeg` **will refuse** any prep reused from that pattern. That covers items 1, 6a, 7 and 8 if they reuse it.
- That same `control.py:44-49` pins `ROOT/data/addresses/k1_gog_103.json` to `44a5984b…`. The worktree copy is now `65e7c2dd5c4c83cf02296a69f3c5d082b9e75d1c2bee5a1eeb497474c3f7fd66`, after the camera regen (ledger :245). So a copied `control.py` would refuse `inputs_exact`. Every new prep must re-pin, and it must record that the staged K1 GOG table changed. The worktree root's `data/addresses` is what `session.stage` copies.
- The plain `kpharness run` / `boot` path does not scan for foreign Wine. Its `wineserver -w` / `-k` calls go through `_wine_command` with this session's `WINEPREFIX` (`session.py:1245-1260, 1438, 1544, 1603-1617`). So it should not touch `~/.wine`. That is `unverified` live. Record the PotPlayer wineserver PID and start time before and after every Wine item, as evidence.

### G-HOST: run every command in a host shell

- This planner ran inside the `ubuntu-dev` podman container (`/run/.containerenv`). That container lacks `gamescope`, `Xwayland`, `xdotool`, `glxinfo`, `wine`, `/usr/bin/ffmpeg`, the Homebrew `ffprobe`, and `/usr/bin/python3.14`.
- On the host (checked with `~/.local/bin/host-cmd`) all of these are present:
  - `/usr/bin/{gamescope,Xwayland,xdotool,xwininfo,glxinfo,wine,wineserver,bwrap,mpv,python3.14,ffmpeg}`
  - `/home/linuxbrew/.linuxbrew/bin/ffprobe`, which links to `../Cellar/ffmpeg/9.0.1_1/bin/ffprobe`
- Tool hashes at planning time:
  - `/usr/bin/ffmpeg`: `abecc2e819e1754850556d6978d726ea4ece8fa4fb65536780137d6537809f27`
  - Brew `ffprobe`: `bb675d2732189c58ad566b4502b4e0638867467d9ef90081e1b67ffc083c0ac6`
- Recompute both hashes at launch time. Do not use `~/.local/bin/mpv` or `~/.local/bin/ffmpeg`, which are wrappers.

### G-LOCK: who takes the canonical lock

| Entry point | Takes `LOCK` itself? | What the operator does |
| --- | --- | --- |
| `kpharness.capture_diagnostic run` | Yes. It holds the lock and passes the descriptor to every child (`creative-runner.md:659-667`). | **Do not wrap it.** Probe with `flock -n LOCK true` first; the probe releases on exit. |
| `kpharness.gamescope_snapshot driver -- --backend linux-wine-k1-gamescope` (the creative runner) | Yes, in the same process that becomes the subreaper (`creative.py:86-100`, `live_lock`). | **Do not wrap it.** Wrapping makes its own `LOCK_NB` acquisition fail. |
| `kpharness.sh run` / `boot` / `pioneer ...` (plain Xvfb session) | **No.** `session.py:890` uses only `ROOT/tmp/harness-locks/display-N.lock`. | Wrap the **whole** sequence in one holder, e.g. `flock -n -E 75 "$LOCK" bash -c '...'`. `boot` returns while the game keeps running, so a holder that wraps only `boot` releases the lock too early. |

### G-SERIAL: rules for every item

- Run one item at a time.
- Exactly one invocation per authorized attempt. Never re-run a failed item inside the same authorization.
- Before starting, give every item a new, empty private directory. Never delete a failed run directory. On failure, write `FAILED-<reason>.txt` beside it with `sha256sum` of every file.
- Before each item, record protected X0, X94 and X100 socket/lock identities, and the PotPlayer wineserver identity. Record them again after.
- No agent kills a process it did not start.

---

## 2. Execution order (minimizes restarts and waits)

| Phase | Item | Launches | Why here |
| --- | --- | --- | --- |
| A | (2) Steam K1 footlocker rerun | 1 (Xvfb, Steam stage) | No capture dependency. Needs only G-RETRY and G-LOCK. **Orchestrator decision:** ledger line 30 (progress.md:~225) queued it after the diagnostic ("serialize live work"). Running it first removes a wait and changes nothing the diagnostic depends on. It must still not overlap item 0. |
| A | (3) Pioneer attached play/status/stop/SIGKILL+reclaim | 1 (Xvfb, GOG) | No capture dependency. Waits for the Pioneer round-3 review PASS. |
| B | (0) Animated capture diagnostic | 0 game (1 mpv) | Gate for every media item. Needs both round-12 reviews PASS and G-FOREIGN clear. |
| C | (1) Blaster Stage 0 `restore_report` | 1 (Gamescope, GOG, `danm14aa` AUTOSAVE) | Same DLL and save as the 10:27 scale run. Ledger gates it on the diagnostic PASS. |
| C | (6a) Item airstrike `GetIsEnemy`-in-hook | 1 (GOG, `endar_room3`) | Independent of the chain-reaction fix. |
| C | (6c) ID-recycle readback (new private read-only route) | 1, or 0 if a reviewer approves merging it into 6a | Settles example-fixes review R3-2/R3-3 (`LIVE/example-fixes-r3-review.md:166`). |
| C | (6b) Chain-reaction live checks | 1 (GOG, `endar_room3`) | Only after example-fixes round 4 passes review. |
| C | (8) Doppelganger fresh gameplay/video | 1 (Gamescope, GOG, `endar_room3`) | Needs a trustworthy capture (item 0 PASS). |
| D | (4)+(5)+(9) camera L1, motion M1, `kp.vec`/timer F12 | 1 shared launch (GOG, `danm14aa`, integrated DLL) | All three need the same not-yet-built integrated DLL and the same save. One new private route, authored after integration. |
| D | (7) K1 creative scale clip, attempt 2 | 1 (Gamescope, GOG) | Last. Needs item 0 PASS, item 4 camera evidence, and the scale-review conditions. |

Do **not** merge reviewed routes into composite routes to save launches. A merged route is a new, unreviewed input. The only merges proposed here are new private routes (6c, and the D-phase combined route). Each needs its own review before launch.

---

## 3. Items

### Item 0: animated capture diagnostic (`kpharness.capture_diagnostic`)

**Status: BLOCKED.**

Preconditions and gates:
1. Both round-12 reviews PASS.
   - At planning time, `LIVE/task7-capture-cadence-fix-review.md` ends with the "Round 11 verdict" section (`:1286-1393`, FAIL).
   - `LIVE/task7-capture-cadence-adversarial-review.md` ends with round 11 (`:1053-1143`, FAIL).
   - The round-12 reviewers are still running (their ffmpeg pids were seen at 14:32).
   - Round-12 PASS is `unverified`.
2. The orchestrator suite rerun on round 12 is green. `LIVE/r12-suites/final/` exists; its verdict is `unverified` here.
3. G-FOREIGN is clear. PotPlayer is closed by the user, the reviewer encodes have finished, and Jellyfin is not transcoding.
4. Lock probe: `flock -n "$LOCK" true` succeeds.
5. Supervisor is single-threaded (the driver records `supervisor_threads_at_spawn` and refuses otherwise).
6. Open orchestrator decision: the packaging plan (`LIVE/fanout-creative-packaging-plan.md`, ledger :209) wants the diagnostic run "from extracted candidate". Whether that applies to this first diagnostic is `unverified`. Default: the worktree snapshot, as the doc's command shows.

Inputs to stage:
- New empty `RUN_ROOT=LIVE/diagnostic-runs/<utc>-<uuid8>/` and new `SNAP=LIVE/diagnostic-snapshots/<same-id>/`.
- An empty commitment log **outside** `RUN_ROOT`, for example `LIVE/owned-commitments/<same-id>.log`.
  - Better: owned by another account, or `chattr +a` (`creative-runner.md:94-102`).
  - It must not be a symlink or hard link, and not inside the run tree.
- Tool identities (G-HOST). The route/pattern is built in (`PATTERN_GRAPH`); nothing else is staged.

Command (host shell; the doc form is at `WT/docs/creative-runner.md:654-657`):
```sh
cd "$WT/scripts/harness" && /usr/bin/python3.14 -S -B -m kpharness.capture_diagnostic run \
  --run-root "$RUN_ROOT" --snapshot "$SNAP" \
  --cleanup-commitment-log "$COMMIT_LOG" --authorized-single-run
```
Copy every printed JSON head/commitments line out of band as it appears (the trust root, `creative-runner.md:88-93`).

Expected evidence: `preflight.json`, `commitments.json`, the printed commitments line, `diagnostic-route.json`, `diagnostic-owned.json`, `diagnostic-result.json` (with `child`, signals, `content_separation`), the media master and its SHA-256, `ffprobe-cleanup-ledger.json`, and the snapshot manifest.

Pass criteria (every one, `creative-runner.md:731-747`):
- Verdict `PASS`.
- No SHM-fallback string.
- First-frame admission.
- Exact window geometry.
- `animated-diagnostic-v2` content gate.
- Canonical PTS binding.
- At least 99% of 60 FPS.
- At most 0.5% missing or dropped slots.
- No gap over 50 ms.
- 0 FFmpeg duplicates.
- Acceptance interval bounded by `pattern_start` / `pattern_end`.
- Complete cleanup and no surviving owned process.
- Ledger clear at the launch head.
- X0/X94/X100 unchanged, snapshot unchanged, and no driver error.

Stop rules (no retry in any case):
- `calibration_ambiguous` → stop. Send `content_separation` to the capture writer.
- `capture_shm_fallback` with verified geometry → stop. The next step is the PipeWire adapter (`creative-runner.md:640-645`).

Capture: the whole `RUN_ROOT`, the out-of-band head lines, `ps` before and after, and `/proc/locks` before and after.

Rollback and cleanup:
- The supervisor owns cleanup: recorder, then client, then display. The budget is 1,442 s, and the run bound is 1,576 s.
- Never kill its children by hand before the budget expires. Afterwards, compare `diagnostic-owned.json` survivors with `ps`, and report them. Do not signal them.

### Item 1: blaster Stage 0 `restore_report` run

**Status: BLOCKED.** Blocked by G-RETRY, item 0 PASS (ledger :204 ruling), the missing second-report route, and the fixture injection method.

Preconditions and gates:
1. G-RETRY closed.
2. Item 0 PASS (ledger :204, "Live run gated on capture diagnostic PASS").
3. **The private route with a settled second report exists and has passed review.**
   - The ledger ruling (:204) wants a second `restore_report` after a bounded settle wait, placed **before** the step-23 assert.
   - The current `LIVE/projectile-research/blaster-fixture-baseline.toml` is `ff476d4e…` (24 steps, one report at step 21). It does **not** have the second report.
   - The new TOML and its hash are `unverified`, because it has not been written yet.
4. **Fixture injection method** into a fresh private stage. This is `unverified`.
   - The route `dofile`s `kotorphasor/console-examples/blaster_fixture.lua`.
   - The creative runner builds a new stage by copying the source `kotorphasor/` directory (launcher.log, "copied writable dir kotorphasor").
   - The source `/home/brunner56/krayt/tmp/k1_harness/kotorphasor/` has only `addresses/` and `scripts/`, with no `console-examples/`.
   - `--script` deploys into `scripts/`, which is a different path.
   - The prep writer must choose and test one of two options: (a) a supported pre-stage hook, or (b) a route variant that `dofile`s from the `--script`-deployed path. Option (b) needs proof that auto-loading the fixture as a mod script is inert.
5. DLL choice. Record this as a deviation:
   - The plan says "on 143031's runtime". That runtime is only known by its manifest prefix `27077224b72a`.
   - `LIVE/stage-k1` now holds `kphasor.dll` `4e14d0fe…` with manifest `7ae257f9…`, so 143031's exact DLL cannot be recovered (`unverified`).
   - Default: the reviewed 10:27 build `/home/brunner56/kp-console-protocol-20260927/build`, with `kphasor.dll` `fd8e069a…` and `binkw32.dll` `1b25f371…` (`build-artifacts.json`).
   - `kp.model.matches` on `fd8e069a` is `unverified`. The route and fixture use it; `kp.model.snapshot` is live-proven on `fd8e069a` by the 10:27 run.

Inputs (hashes):

| Input | SHA-256 |
| --- | --- |
| `LIVE/projectile-research/blaster_fixture.lua` (Stage 0) | `6acfba47d21578b57834044e718faa4a830ed344aba9adba8283a9f11642f43c` |
| `LIVE/projectile-research/blaster-fixture-baseline.toml` (one report; to be superseded) | `ff476d4edf211abfb3ae058464a387981c95989b22bc9a3b287466a1972d7c21` |
| `LIVE/projectile-research/borrowed-fixture-test.lua` | `d825af90a3cede23493b250c766829a397f2da3df8bca5f38253f3ae08599e53` |
| Stale staged copy `LIVE/stage-k1/kotorphasor/console-examples/blaster_fixture.lua` (**must not be used**) | `a9a0b3394aea170178e54fa0e2d3f6dba4bdeb35e4cc7243e7b4b438a1b1e153` |
| Second-report TOML | `unverified` (not written) |
| Source exe `/home/brunner56/krayt/tmp/k1_harness/swkotor.exe` | `9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435` |
| Save `000001 - AUTOSAVE` files | Five hashes in `next-k1-preparations/20260927-task7-scale-102038-74cb804b/brief.md` (GLOBALVARS `fcdab529…`, PARTYTABLE `f380d021…`, SAVEGAME `d879c65a…`, pifo `a181c82c…`, savenfo `d4d04f59…`) |

Command: mirror the 10:27 invocation (`…-74cb804b/launch-once.json`) with a new prep dir. Create a new snapshot first and pass the G-RETRY preconditions (`KP_MAX_BOOT_ATTEMPTS=1`, both snapshot greps), then:
```sh
PREP=LIVE/next-k1-preparations/20260927-blaster-stage0-<uuid8>   # new, empty
/usr/bin/python3.14 -I -S -B -c "import sys,runpy;sys.path.insert(0,'$WT/scripts/harness');runpy.run_module('kpharness.gamescope_snapshot',run_name='__main__')" \
  driver --snapshot "$PREP/harness-snapshot" -- --backend linux-wine-k1-gamescope --target k1 \
  --route "$PREP/blaster-stage0.toml" --build-dir /home/brunner56/kp-console-protocol-20260927/build \
  --source /home/brunner56/krayt/tmp/k1_harness --staged "$PREP/stage-k1" --wineprefix "$PREP/wineprefix-k1" \
  --checkpoint-root "$PREP/checkpoints-k1" --output "$PREP/runs" --width 1024 --height 768 --capture-fps 60 \
  --boot-timeout 120 --cleanup-commitment-log "$COMMIT_LOG"
```
- Whether this backend requires `--cleanup-commitment-log` here: the doc says it refuses a run directory without one (`creative-runner.md:46-48`). The 10:27 argv did not pass one, so the requirement may postdate it (`unverified`).
- Add `--script …` only if option (b) of precondition 4 is chosen.

Expected evidence: `report.json`, `console-command-21.json` (first report), the second-report receipt (its step index is `unverified` until the route exists), `kotorphasor.log`, `session.log`, `executed-route.toml`, `deployed-scripts.json`, and the master MP4 (diagnostic only; it is not an acceptance clip).

Pass criteria:
- Both `restore_report:` strings are captured.
- The **settled** report names each of the five conditions with raw values.
- The run PASSes as a diagnostic if the report names the failing condition(s) (`fanout-blaster-plan.md:24`, "pass = report names the failing condition"), even if step 23 fails.
- Also: exactly one `launching:` line, `boot-attempts.json` reads `1 1` (G-RETRY post-run check), and no source/save change.

Rollback and cleanup: the runner tears down recorder → game/Wine → display. Keep `PREP` entirely. Nothing is written back to `LIVE/stage-k1` or the source.

### Item 2: Steam K1 footlocker rerun (VM-layout fix)

**Status: BLOCKED only by G-RETRY.** It becomes **READY** once G-RETRY closes, after the operator's checkpoint step below. Ordering relative to item 0 is an orchestrator decision; see §2.

Preconditions and gates:
1. G-RETRY closed. G-LOCK held by an external `flock` wrapper, because the plain run takes no canonical lock.
2. Layout fix independently CONFIRMED: `LIVE/steam-k1-vm-layout-fix-review.md`. Worktree tables:
   - `WT/data/addresses/k1_steam_103.json` = `c52447bd10a2811a2a40530ecf3696803adad0ddcebcb62ebf7a415ce7f62048`
   - `WT/data/addresses/k1_steam_103_unpacked.json` = `5cc67517140e3559b939b39aecb4d741c7f2fffb83075e3445726f897c2bc155`
   - Rehashed at planning time.
3. The stale staged tables are still in place:
   - `MAIN/tmp/k1_harness/kotorphasor/addresses/k1_steam_103.json` = `57b1368a…`
   - `…/k1_steam_103_unpacked.json` = `541c5c3e…`
   - `MAIN/data/addresses` holds the same two old hashes.
4. Multiplayer off (no `start_multiplayer`). The review showed the catch-up rows are multiplayer-gated (`steam-k1-vm-layout-fix-review.md:68-78`).

Restage mechanism (derived, and the reason for the command shape):
- `session._install_runtime` (`WT/scripts/harness/kpharness/session.py:756-816`) copies `repo_root()/data/addresses` wholesale into the stage. It does this whenever its size+mtime manifest differs from `kotorphasor/.installed` (current `.installed` = `1f3efb51…`).
- `repo_root()` is the checkout that holds the harness code (`discover.py:25-28`).
- So running the driver **from the worktree** restages the new tables automatically.
- Running from `MAIN` would reinstall `MAIN`'s old tables whenever the manifest changes. A hand-copied restage there could be silently overwritten.

Pin every other root-derived path explicitly:
- **Route:** exists only in `MAIN`, untracked: `MAIN/scripts/harness/scenarios/cursed/110_footlocker_blaster.toml`, `b022dccefbfa5346a7a81099d6d8e94042ad4a15bf9c5b0af94df0aa2ef589a7`. Pass its absolute path.
- **Script:** already deployed in the Steam stage: `MAIN/tmp/k1_harness/kotorphasor/scripts/110_footlocker_blaster.lua` = `c5721bb8…`, equal to `MAIN/scripts/examples/cursed/110_footlocker_blaster.lua`. The worktree has no copy. `_install_runtime` does not wipe `scripts/`.
- **DLL:** `--build-dir MAIN/build`, `kphasor.dll` `bdf420d1b283dcd69f5c292d6b85f5ce0a9fc1afe27f5199414b379c0500d26f`. This is the exact DLL whose runs failed with the gate (RCA :73-75), so the table swap is the only variable.
- **Stage:** `--staged MAIN/tmp/k1_harness`. This keeps the unpacked exe `2719ed2c…`. A fresh stage could copy the SteamStub-packed exe and change the build id.
- **Prefix:** `--wineprefix MAIN/tmp/wineprefix-k1`.
- **Data:** `KOTOR1_DIR=/run/media/brunner56/MyBook/SteamLibrary/steamapps/common/swkotor` (the source the failed runs used, per their `session.log` line 1).
- **Checkpoint:** `checkpoints.py:38` uses `repo_root()/tmp/checkpoints/k1`, and `WT/tmp/checkpoints/k1/` is **empty**. Operator step, before the run: copy `MAIN/tmp/checkpoints/k1/endar_room3/` (meta stored 2026-09-15, slot 3) to `WT/tmp/checkpoints/k1/endar_room3/`. This is gitignored `tmp/`. Hash every file in both copies before the run.
- **Display locks** move to `WT/tmp/harness-locks/display-N.lock`. That is harmless under the canonical lock.

Command (host shell):
```sh
cd "$WT"
export KOTOR1_DIR=/run/media/brunner56/MyBook/SteamLibrary/steamapps/common/swkotor
export KP_MAX_BOOT_ATTEMPTS=1
flock -n -E 75 "$LOCK" scripts/harness/kpharness.sh run \
  "$MAIN/scripts/harness/scenarios/cursed/110_footlocker_blaster.toml" --target k1 \
  --build-dir "$MAIN/build" --staged "$MAIN/tmp/k1_harness" --wineprefix "$MAIN/tmp/wineprefix-k1" \
  --max-boot-attempts 1
```
- Exit 75 means the lock was busy: nothing ran.
- Whether `run` accepts `--build-dir/--staged/--wineprefix` after the route: `cli.py:418-430` defines them on the boot/run parsers, but argument order is `unverified`. Check with `--help` first; that launches nothing.

Expected evidence (new `MAIN/tmp/k1_harness/runs/<ts>/`): `report.json`, `session.log`, `kotorphasor.log`, `wine.log`, `xvfb.log`, `shots/`. Also record `sha256sum` of the staged `addresses/k1_steam_103*.json` and `.installed` before and after.

Pass criteria for **the fix**:
- (a) The channel line and `report.json` both say build `k1_steam_103_unpacked`.
- (b) The staged tables are `c52447bd…` / `5cc67517…` after the run, and `session.log` says `runtime installed from …/build` (the manifest changed because the root changed).
- (c) `kotorphasor.log` contains `vm: routine bridge refreshed` (or `bound`; RCA :62 greps `routine bridge bound|refreshed`).
- (d) The step `state` has non-null `pc`.
- (e) Step 3 ("counter plumbing: warm the harness Lua VM") or step 5 ("ensure PC has a ranged weapon") passes.
- The full route (at least 3 knockback impacts) is a bonus, not the gate.

Result classes:
- **FAIL of the fix:** gameplay reached and (c)-(e) absent.
- **Inconclusive:** the phase wait times out before gameplay (earlier Steam runs needed 323-632 s of a 600 s budget), or a (b) mismatch.
- **Rule breach:** any `boot attempt` line, or `boot-attempts.json` not reading `1 1`.

Capture: the whole run dir, the table hashes, and the PotPlayer wineserver pid/start before and after.

Rollback and cleanup:
- The session tears down itself.
- The stage keeps the new tables. That is intended, and it is the reviewer's requested restage.
- To roll back: copy `MAIN/data/addresses/k1_steam_103*.json` (old) back into the stage and delete `.installed`. Do this only if the orchestrator asks.
- Leave the copied checkpoint in `WT/tmp` and record it.

### Item 3: Pioneer attached play/status/stop/SIGKILL+reclaim (K1)

**Status: BLOCKED.**

Preconditions and gates:
1. G-RETRY closed.
2. **The Pioneer round-3 review PASS.** It was dispatched (ledger :251, probes in `LIVE/review-probes-pioneer-r3/`), but no review markdown exists yet (`unverified`). Round 2 was FAIL on I6 (`LIVE/pioneer-round2-review.md`).
3. The DLL provides `kp.game_speed` read/write. Attached calls require it (`WT/docs/pioneer-authoring.md:14-20`). For `fd8e069a` this is `unverified`.
4. A private route `R.toml` exists and is hashed. It needs at least 3 committed steps and a leading `load_save` for `--restart`.
   - Proposal: `load_save "000001 - AUTOSAVE"`, `wait phase gameplay`, `clear_auto_pause`, `assert_lua` read-only, `advance_ticks 120`.
   - Its hash is `unverified` (not written).
5. `$XDG_STATE_HOME/kpharness/playback-locks` (or `~/.local/state/…`) is mode 0700 and holds no stale lock. The policy test leaves an empty lock file there (ledger :207).

Command (one holder process spans the whole sequence, per G-LOCK):
```sh
cd "$WT"; KP=scripts/harness/kpharness.sh; R="$PREP/pioneer-route.toml"
export KP_MAX_BOOT_ATTEMPTS=1
flock -n -E 75 "$LOCK" bash -euo pipefail -c '
  '"$KP"' boot --target k1 --build-dir /home/brunner56/kp-console-protocol-20260927/build \
     --staged '"$PREP"'/stage-k1 --wineprefix '"$PREP"'/wineprefix-k1 --max-boot-attempts 1
  '"$KP"' pioneer attach --out '"$R"'
  '"$KP"' pioneer play   --out '"$R"' --restart --until 3
  '"$KP"' pioneer status --out '"$R"'
  '"$KP"' pioneer stop   --out '"$R"'
  '"$KP"' state                                  # must work again once the owner is gone
  '"$KP"' pioneer fastforward --out '"$R"' --speed 8 --no-wait
  # SIGKILL only the owner: read owner_pid from R.toml.playback.json, then confirm that PID cmdline is the kpharness owner
  kill -KILL "$OWNER_PID"
  '"$KP"' pioneer status  --out '"$R"'             # expect: owner not reachable
  '"$KP"' pioneer reclaim --out '"$R"'
  '"$KP"' exec "return kp.game_speed()"
  '"$KP"' down'
```
- `--source` for `boot` defaults through discovery. Set `KOTOR1_DIR=/home/brunner56/krayt/tmp/k1_harness`, so it is the same GOG data as the 10:27 run (`unverified` that `boot` honors it identically).
- The `$OWNER_PID` extraction is manual. Never signal the game PID.
- If any command fails, stop, run `pioneer stop` / `reclaim` / `down` as applicable, and do not repeat the job (`pioneer-authoring.md:130-135`, "Jobs are never retried").

Pass criteria (`pioneer-authoring.md:201-203` and the stage 0-5 report :127-128):
- `play --until 3` completes, and the boundary is 3.
- `status` shows the owner live.
- After `stop`: state is `execution_stopped`, `world_paused=false`, `speed_after_job == speed_before_job` by readback, and the game PID is still alive.
- After SIGKILL: `status` reports not reachable.
- `reclaim` removes the descriptor, restores `speed_before_job` with readback, and marks the world uncertain.
- The final `kp.game_speed()` equals the pre-job value.

Capture: `R.toml*`, `R.toml.playback.json`, `R.toml.playback-state.json`, every CLI stdout/exit code, the session dir, `ps` of owner and game before and after the kill.

Rollback and cleanup: run `down`. Remove nothing from the playback-locks dir by hand; `reclaim` owns it.

### Item 4: camera Stage 1 live snapshot readback (incl. +0x84/+0x88/+0x8c after a restore-path mode change)

**Status: BLOCKED.** The runtime wiring is not integrated.

The dependency chain, all `unverified` as future events:
1. Lifecycle L1+L2 re-fix and PASS. It is FAIL on I1 (`LIVE/lua-lifecycle-l1l2-review.md:214`, 14:29).
2. W1 round 3 (`Runtime::log`) PASS.
3. The integration writer lands camera + lifecycle + utilities + motion + the Steam log line (ledger :200, :217, :254).
4. Integration review PASS.
5. The motion engine-thread guard (motion-m1 review, narrow FAIL, ledger :238).
6. Regenerate `k1_gog_103.json` with the motion rows. The worktree copy is `65e7c2dd…` after the camera regen (ledger :245 says the regen adds 7 motion rows).
7. A frozen DLL with a recorded hash and the build provenance manifest.

Host-only closure exists: camera Stage 1 CLOSED host-only (ledger :250), with `kp_cameratest` passing 1,818 checks.

Inputs:
- The integrated frozen DLL (hash `unverified`).
- Exe `9c10e045…`.
- The `danm14aa` AUTOSAVE hashes above.
- The new private route (see the D-phase combined route under item 9).

Steps and pass criteria (from `LIVE/kp-camera-api-plan.md:228-248`, L1):
1. `kp.camera.capabilities().available == true`, `profile == "windows-k1-gog"`, and no `camera:` refusal in the log.
2. `SetCameraMode(p,2)` through `nwscript.call`, then advance 600 ticks. Take two snapshots 180 ticks apart, each with a screenshot. Record `behavior`, `dolly` (+0x84), `style_pending`, and the raw +0x88 and +0x8c.
3. Steady pair: at most 4 px of background displacement means raw fields are equal within 1e-4. Panning pair: more than 4 px means a nonzero change.
4. Yaw sweep: at least 8 samples. r = |(pos − pc_pos).xy| within 2%, Δz invariant, and `position` vs `position2` recorded.
5. **Restore-path mode change.** The copy-ctor 0x63ad60 leaves +0x84 uninitialized on the restore-from-saved-record path (mode switch 0x641dc0 → 0x642221). See `LIVE/kp-camera-offsets-rederivation.md:188`.
   - **No in-game trigger for that path is known: `unverified`.**
   - The route may cycle `SetCameraMode` away from 2 and back, and record +0x84/+0x88/+0x8c after each transition.
   - It must **not** claim the restore path was reached unless a separate referent shows it (a hook or log that does not exist yet).
   - If +0x84 is non-zero in chase mode, record it as the E7 answer. Stage 2 then stays blocked.

Admission: `report.json` plus PPMs, and an R2 reviewer who did not run L1 signs off. Stage 1 writes nothing, so there is nothing to restore.

### Item 5: motion M1 capture readback checklist

**Status: BLOCKED.** Same integration chain as item 4, plus the motion engine-thread guard (ledger :238).

Inputs:
- The integrated DLL (`unverified`).
- A disposable footlocker template resref for `CreateObject(64, …)`. `footlker001` is the ammo-default resref in the footlocker route (`110_footlocker_blaster.toml:63`, "#footlker001 == 11"). Whether it is a valid placeable template in `danm14aa` is `unverified`.
- A GIT placeable with a non-zero `Bearing` in `danm14aa`: `unverified` (none identified).

Steps and pass criteria (from `WT/.superpowers/sdd/lua-boundary-validation-plan/motion-m1-report.md:283-299`, verbatim intent):
1. Spawn one footlocker and record its id.
2. `capabilities().available` is true, and the profile is `windows-k1-gog`.
3. The crate captures. The PC id and a creature id return `identity:`.
4. `position` equals `GetPosition` within 1e-3.
5. `facing` equals `GetFacing` within 0.01°. Record the range convention.
6. `area_id` equals the id of `GetArea(crate)`.
7. At rest: record `push_gate_raw` (expected ≠ 0), and both dirty flags are false (record, do not interpret).
8. Record `collision_registered`.
9. Settle the quaternion order from the Bearing placeable, or mark it `unverified` if none is found.
10. Two captures with nothing in between are identical, with no `[model]`/setter log lines.

Cleanup: destroy the spawned crate through `nwscript.call('DestroyObject', id)` and confirm it is invalid after settle.

### Item 6: chain-reaction live checks and item-airstrike `GetIsEnemy`-in-hook

**Status: 6a BLOCKED only by G-RETRY (+ item 0 PASS if run on Gamescope). 6b BLOCKED on the example-fixes round-4 PASS. 6c BLOCKED on authoring and review.**

Common inputs:
- `endar_room3` checkpoint, from either `LIVE/checkpoints/endar_room3/` (with `source-manifest.json`) or `MAIN/tmp/checkpoints/k1/endar_room3/`. Which source is GOG-valid for the krayt source is `unverified`. Hash all files at prep.
- DLL `fd8e069a…`.

**6a: airstrike `GetIsEnemy` inside `OnModuleAcquireItem`.**
- Route `WT/scripts/harness/scenarios/cursed/100_item_airstrike.toml` = `3c6398720f48dffa7fae96510b06b3e4fd6cc6ead8712ec83770c9a0c25735ab` (13 steps).
- Script `WT/scripts/examples/cursed/100_item_airstrike.lua` = `ce2e1504f9b45cfe5edb85a694df6330613f2d3ec7a3033e4f1c72e0256e0e11`.
- The filter is at `:67`, `yes(q("GetIsEnemy", o, pc))`. On 2026-09-16, `GetIsEnemy` returned 0 inside the hook (`:19-20`).
- Command: the creative runner as in item 1, with `--script cursed/100_item_airstrike.lua --route …/100_item_airstrike.toml --checkpoint-root "$PREP/checkpoints-k1"` (seeded from the chosen checkpoint). Pass the G-RETRY preconditions first. On Gamescope that means a new snapshot with both greps. On either backend, set `KP_MAX_BOOT_ATTEMPTS=1` and run the post-run `boot-attempts.json` check.
- Pass:
  - Step "the strike fired and hit at least three of the ring (targets of the last strike in local number 6)" passes.
  - `kotorphasor.log` has `[cursed:strike] <label> -> N targets` with N ≥ 3.
- A `-> 0 targets` line with hostiles in range = **GetIsEnemy-in-hook FAIL** (the known risk). Keep it; do not retry.

**6b: chain reaction.**
- Route `…/cursed/40_chain_reaction.toml` = `d7d4cbb9…`. Script `…/cursed/40_chain_reaction.lua` = `047e37906bbdc1b223700569893b7428a09fac76ba1147c163d84aad74f617e5`.
- **Blocked:** `LIVE/example-fixes-r3-review.md:168`, "Example fixes round 3 verdict: FAIL" (R3-2/R3-3, the session-wide raw-ID `owned` set). A live run on this script tests a rejected revision.
- After round 4 passes, two live checks are owed (ledger :210, :225):
  - (i) A module transition within 3 s of a blast; afterwards min-one-HP is restored on the PC and party.
  - (ii) A leader swap: identity readback shows the original object restored and the replacement untouched.
- Both need a new private route. Whether the transition is triggered by `StartNewModule` from `nwscript.call` is `unverified`. No such route exists.

**6c: ID-recycle readback (read-only, settles R3-2/R3-3 reachability).**
- `LIVE/example-fixes-r3-review.md:166`: read every party member's numeric ID and `GetTag`, and `GetFirstPC`, before and after one module load.
- Proposal: a private route of `load_checkpoint endar_room3` → read → `load_checkpoint endar_room3` again (a module load) → read. It is new and needs review. Hash `unverified`.
- Pass: the IDs are recorded both times. The result (recycled or not) is the answer; either value passes as evidence.

Cleanup: the runner tears down. The checkpoint copies in `PREP` stay.

### Item 7: K1 creative scale clip, attempt 2

**Status: BLOCKED.**

Preconditions and gates:
1. Item 0 PASS.
2. G-RETRY closed.
3. **The prep dir `LIVE/next-k1-preparations/20260927-task7-scale-attempt2/` does not exist.** `ls` of `next-k1-preparations/` shows only `20260927-task7-scale-102038-74cb804b`. The preparing agent's route, snapshot and hashes are all `unverified`.
4. The scale-run review conditions are closed (`LIVE/task7-k1-scale-run-review.md`, ledger :179): framing, interval and cadence.
   - Framing: normal height about 25-30% of 768, giant only if the same-run baseline is ≤ 211 px (`LIVE/task7-k1-framing-plan.md`, ledger :193).
   - Interval: the representative window must include the restoration at about 218.03 s.
   - Cadence: item 0 PASS.
5. If V1 (the camera stability gate) uses `kp.camera`, item 4 must PASS first, with the integrated DLL. That makes the base DLL differ from `fd8e069a`. Which DLL attempt 2 uses is `unverified`.

Command shape: identical to `…-74cb804b/launch-once.json`, pointed at the attempt-2 prep paths and route, plus `--cleanup-commitment-log`. Use a new snapshot, not the `…-74cb804b` one, and pass the G-RETRY preconditions first. Never pass `--dev-max-boot-attempts`.

Pass criteria:
- Behavior: all route steps pass, three physical F12 requests return exact Boolean true, and the native `1.0 → 0.35 → 2.4 → 1.0` gates pass.
- Presentation: no clipping of the 2.4× body, the representative interval includes restoration, and the item 0 cadence thresholds hold on the master.
- Then `creative_accept` with the printed heads (`creative-runner.md:79-84`), then `creative_export` with explicit bounds.

Rollback: none needed in game. The failure evidence stays quarantined, as in the 10:27 run.

### Item 8: Doppelganger fresh live gameplay and video

**Status: BLOCKED** on G-RETRY and item 0 PASS.

- Route `WT/scripts/harness/scenarios/cursed/70_doppelganger.toml` = `1ba9678f365d01aa9b1abfc2a52b30bacb303b895b57dbe3fdf3e02b1c3af2be` (13 steps, `endar_room3`).
- Script `WT/scripts/examples/cursed/70_doppelganger.lua` = `5d9864b22241ff135d3bb0c1ecb3f2671af218b58cdf2f44eb7bc62c95f62c42`. It is frozen; it matches the receipt, `LIVE/example-host-receipt-20260927d.json` ("Doppelganger unchanged").
- Final scoped review PASS: `LIVE/task13-doppel-rereview-round3.md`.
- Command: the creative runner, as in 6a, with `--script cursed/70_doppelganger.lua --route …/70_doppelganger.toml`. Pass the G-RETRY preconditions first: a new snapshot with both greps, and `KP_MAX_BOOT_ATTEMPTS=1`.
- Pass criterion: exactly three living marked hostiles, each following the disguise-token count **1 baseline → 2 active → 1 owned cleanup → 0 explicit baseline cleanup** (ledger :173), with every route step passing.
- The fixture seeds baseline appearance P before the script adds its own P. So the pass is the per-actor token count sequence. **It is not a visible appearance change** (`…-74cb804b/brief.md`, "Do not select … 70_doppelganger").
- Video is gameplay evidence only; visual review is separate.
- Known risk: the disguise-in-combat engine fault at 0x6502ff (commit `b4b022e`). Its interaction with this route is `unverified`. A crash is a FAIL with evidence, and there is no retry.

### Item 9: `kp.vec` and function-timer F12 checks

**Status: BLOCKED.** Same integration chain as item 4. The `register_vector` snippet lands only with the integration writer (ledger :214, :224).

Host proof exists:
- `kp_vectortest` 15/0 and `kp_supporttest` 49/0 after the follow-up round (ledger :231).
- Review PASS (`LIVE/lua-utilities-u1u2-review.md`, `LIVE/lua-utilities-followup-review.md`).

F12 steps (physical `console_command`, from `lua-utilities-u1-u2-report.md:148-149` and `fanout-lua-lifecycle-plan.md:144,150`):
1. `return kp.vec(3,4,0):length()` → `expect_values=[{type="Number", value=5}]`.
   - The exact result type name in `kp.console.v1` (`Number` vs `number:5`) is `unverified`. The report text shows `number:5`.
2. A `GetPosition` round trip on real engine floats: `nwscript.call('GetPosition', pc)` into `kp.vec`, and back through a routine that takes a Vector. Pass: components within 1e-4.
3. A closure timer increments an upvalue exactly 3 times, then returns false. `pending` returns to its baseline. Pass: an independent `assert_lua` reads 3.

**D-phase combined route (items 4, 5 and 9):** one new private TOML on `danm14aa` AUTOSAVE, with sections in this order:
1. Camera L1 (read-only).
2. Motion M1 (spawn one crate, read, destroy).
3. F12 `vec`/timer.

Hash `unverified` (not written). It needs its own review, and one launch.

---

## 4. One-page summary

| # | Item | Launch path | Hard gates still open | Inputs known (sha) | Status |
| --- | --- | --- | --- | --- | --- |
| 0 | Capture diagnostic | `capture_diagnostic run` (takes lock) | R12 correctness + adversarial PASS; G-FOREIGN (PotPlayer wineserver 1099968, reviewer ffmpeg, Jellyfin) | ffmpeg `abecc2e8…`, ffprobe `bb675d27…` | BLOCKED |
| 1 | Blaster Stage 0 | Gamescope creative (takes lock) | G-RETRY; item 0 PASS; second-report TOML unwritten; fixture injection method | fixture `6acfba47…`, toml `ff476d4e…` (to supersede), DLL `fd8e069a…` | BLOCKED |
| 2 | Steam footlocker | `kpharness.sh run` from WT under `flock` | G-RETRY (+ copy `endar_room3` into `WT/tmp/checkpoints/k1`) | tables `c52447bd…`/`5cc67517…`, DLL `bdf420d1…`, route `b022dcce…`, script `c5721bb8…` | BLOCKED (READY after G-RETRY) |
| 3 | Pioneer | `boot` + `pioneer …` + `down` in one `flock` holder | G-RETRY; Pioneer r3 review PASS; route unwritten; `kp.game_speed` on DLL | DLL `fd8e069a…` | BLOCKED |
| 4 | Camera L1 | combined D-route | lifecycle fix → integration → review → regen → DLL; restore-path trigger unknown | exe `9c10e045…` | BLOCKED |
| 5 | Motion M1 | combined D-route | same as 4 + engine-thread guard; crate resref and Bearing placeable unknown | — | BLOCKED |
| 6a | Airstrike `GetIsEnemy` | creative runner | G-RETRY (+ item 0 if Gamescope) | route `3c639872…`, script `ce2e1504…` | BLOCKED |
| 6b | Chain reaction | creative runner, new route | example-fixes round 4 PASS; transition route unwritten | route `d7d4cbb9…`, script `047e3790…` (rejected rev) | BLOCKED |
| 6c | ID-recycle readback | new private route | authoring + review | — | BLOCKED |
| 7 | K1 scale clip #2 | Gamescope creative | item 0 PASS; prep dir absent; framing/interval/cadence; camera evidence | — | BLOCKED |
| 8 | Doppelganger video | Gamescope creative | G-RETRY; item 0 PASS | route `1ba9678f…`, script `5d9864b2…` | BLOCKED |
| 9 | `kp.vec`/timer F12 | combined D-route | integration chain | — | BLOCKED |

**Counts:** ready now **0**, blocked **12** (items 0-9 with 6 split into 6a/6b/6c). Grouped as the ten requested items: ready **0**, blocked **10**.

- **The single action that unblocks the most:** the G-RETRY writer plus review (a single-launch override with a host test). It unblocks item 2 immediately. It is also a precondition for 1, 3, 6a, 7 and 8.
- **The next largest unblocker:** round-12 PASS plus the user closing PotPlayer, which opens item 0. After that, 1, 6a and 8 need only their own inputs.

---

## 5. Grill me

1. **Is the in-harness relaunch really a "retry" under the user's rule, or is it one launch attempt?** (weakest answer)
   - My answer is yes, it is a retry. `session.py:1406-1416` calls `self.launch()` again after `_kill_game()`, which is a second `wine swkotor.exe` process. The rule says "one launch per authorized attempt."
   - It is still an interpretation of "launch". If the orchestrator reads "attempt" as "one CLI invocation", G-RETRY drops and item 2 is READY now.
   - Referent: `session.py:74`, `:1394-1416`; `creative_wine.py:226`.
   - Settle it with one line from the user.
2. **Why run the Steam rerun from the worktree instead of hand-restaging `MAIN`'s stage as the reviewer wrote?**
   - `_install_runtime` (`session.py:766-812`) re-copies `repo_root()/data/addresses` whenever the size+mtime manifest differs. From `MAIN` that is the old `57b1368a…`/`541c5c3e…`.
   - The worktree root makes the new tables the code-driven copy, with no silent-overwrite window.
   - The costs are an empty `WT/tmp/checkpoints/k1` (copy needed) and a route and script that exist only in `MAIN` (absolute route path; the script is already in the stage).
   - Whether `run` accepts an absolute route path outside `repo_root()` is `unverified`. `harness-driver.md:83` says "resolves the route", and "an explicit route path" is listed at `:13`.
3. **Why DLL `bdf420d1…` for Steam and not the newer `fd8e069a…`?**
   - It is the DLL whose runs failed with the gate (RCA :73). Keeping it makes the table swap the only variable.
   - Whether `fd8e069a` also contains the gate is `unverified`. A `git merge-base --is-ancestor 5cffd0f ca329e5` check timed out under host I/O load (rc 124 both directions).
4. **Why is item 6a not blocked by the chain-reaction FAIL?**
   - R3-2/R3-3 are in `40_chain_reaction.lua` only (`example-fixes-r3-review.md:154`). The airstrike script `ce2e1504…` passed the round-2/3 receipts (41 sources / 96 cases, `example-host-receipt-20260927d.json`).
   - I did not read the airstrike review section in full, so "no open airstrike finding" is `unverified` beyond the Minor "strikes nothing if GetIsEnemy returns 0" (ledger :225). That Minor is the thing 6a measures.
5. **Can the diagnostic run while the user's PotPlayer is open, if a `wineserver` exemption is added?**
   - Not without a reviewed code change. `FORBIDDEN_NAMES` matching is name-based by design (`capture_diagnostic.py:77, :304`). An exemption would reopen the renamed-binary and foreign-process questions that rounds 11-12 closed.
   - Cheaper to reverse: ask the user to close PotPlayer for the diagnostic window.

6. **Does the PotPlayer wineserver block the Gamescope K1 items too, or only the diagnostic?**
   - It blocks them too, if their prep reuses the 10:27 pattern. `control.py:56` exempts only `xwayland` and `xvfb`, for any user, and `preflight-launch.json` at 10:27 shows `conflicting_processes: []`.
   - The creative runner's own checks may differ (`unverified`).

**Hand-off: the one question I could not settle.** Does `fd8e069a…` (the 10:27 build, base `ca329e5` plus overlays) expose `kp.game_speed` read/write and `kp.model.matches`? Items 1 and 3 depend on these.
- I ran a partial check: a byte search of that DLL found `game_speed` 10 times, `matches` 19, `registertimer` 5, and `snapshot` 11. That suggests the names are present. It does not prove they are bound as `kp.game_speed` / `kp.model.matches`.
- The proof is one read-only live `exec`: `return type(kp.game_speed), type(kp.model.matches)`. Run it as the first step of item 3.
