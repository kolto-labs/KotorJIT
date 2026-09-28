# Task 7 K1 scale, attempt 2: preparation report

Prepared 2026-09-27; revision r2 the same day answers review FAIL `k1-scale-attempt2-prep-review.md` (F1, F2, F3, M1) under the orchestrator's rulings. Revision r3, the same day, answers the r2 re-review `k1-scale-attempt2-prep-r2-review.md` (PASS with one Important, non-blocking gap: Finding I1, F3's "BLOCKING" status was prose-only, not enforced by anything executable). r3 gives `postrun-gate.py` a `--require-l1 <L1 run-dir>` mode that is now mandatory for any route other than the checked-in `l1-camera-diagnostic.toml` itself (identified by content hash, not by name or a trusted flag), so a V1 acceptance check with no L1 path refuses instead of silently passing. Every file changed in r3 has its previous copy beside it as `<name>.pre-r3` (r2's `<name>.pre-r2` copies are untouched). This is preparation only. I did not launch Wine, the game, Gamescope or FFmpeg. I did not touch `tmp/harness-locks/live-game.lock` and did not edit the worktree. Every file I wrote is in this directory. The harness was imported read-only with `-I -S -B`. No new `.pyc` appeared under `scripts/harness` (`find … -name '*.pyc' -newer framing-fit.py | wc -l` printed `0`). In r2, three `.pyc` files under `kpharness/__pycache__` (creative, display_backends, capture_diagnostic; 18:54) are newer than my first r2 file. They are not mine: re-running my exact import (`python3 -I -S -B`, `sys.dont_write_bytecode=True`) left `creative.cpython-314.pyc`'s mtime unchanged, and other writers are active in WT (§0 item 3). r3 touched only `postrun-gate.py`, `validate.py`, `validation-output.txt` and this report; it launched nothing and imported the WT harness read-only exactly as r2 did. §7's r2 rows are re-verified again in r3 (all unchanged since r2's last check), and r3 adds one new row (`recording.py`, a dependency `--require-l1` newly reads for `artifact()`/`sha256()`).

Paths:

- DIR = this directory
- WT = `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`
- FAILED = `/home/brunner56/kp-live-20260922/next-k1-preparations/20260927-task7-scale-102038-74cb804b`
- FP = `/home/brunner56/kp-live-20260922/task7-k1-framing-plan.md`
- CP = `/home/brunner56/kp-live-20260922/kp-camera-api-plan.md`

## 0. Blocking prerequisites (before any launch)

Summary. V1 counts as the acceptance attempt only when all of these hold, in this order:

| # | Precondition | How it is checked |
|---|---|---|
| P1 | New reviewed build with kp.camera (item 1) | `grep -a -c kp.camera.capture kphasor.dll` ≥ 1, and the build hash is recorded |
| P2 | Fresh harness snapshot `$SNAP` taken after WT settles (item 3), containing the one-launch budget | `grep -c KP_MAX_BOOT_ATTEMPTS $SNAP/runtime/kpharness/session.py` ≥ 1, then `validate.py` re-run against it. **(r3)** Also grep `$SNAP/runtime/kpharness/creative.py` for `route_source` and `'runtime'`, and `$SNAP/runtime/kpharness/scenario.py` for `"started"` / `"finished"`: `--require-l1` depends on these field names (§7, Grill me #8), and `validate.py`'s own check 9 fixtures hardcode them, so re-running `validate.py` against `$SNAP` does not by itself prove the real harness still writes them |
| P3 | `KP_MAX_BOOT_ATTEMPTS=1` in the driver environment, for L1 and for V1. Never pass `--dev-max-boot-attempts` (item 6) | Before: the launch record shows the env entry. After: `postrun-gate.py` (§4e) |
| P4 | Capture diagnostic passed (item 4) | its own receipt |
| P5 | **L1 camera diagnostic ran once and passed its admission rule (§5b). This is BLOCKING, not optional (item 2)** | L1 `report.json`, `postrun-gate.py` on L1, and the §5b measurements. **(r3) Mechanically enforced**: `postrun-gate.py --route task7s2-v1-readonly-camera.toml --run-dir <V1 run> --require-l1 <L1 run>` refuses (nonzero, one line) unless L1's own gate passed *for the L1 route* (receipt's `route_sha256` checked too, not only its verdict), L1's *runner-recorded* route hash (`creative-run.json` `route_source.sha256`) matches the checked-in `l1-camera-diagnostic.toml`, L1's `boot-attempts.json` shows `launch_count=1` (read directly, not just from the cached receipt), the §5b admission rule A1-A5 is recorded in `admission.json` and holds under re-derivation (missing/non-finite fields are problems, not defaulted; signed displacements use `abs()`), A6 holds via both run-dirs' `creative-run.json` runtime-file hashes (not `report.json`'s `build` string), and L1 finished before V1 started (run-record timestamps, not mtimes) |
| P6 | L1 and V1 use the same build hash and the same `$SNAP`. The stage, save and 1024×768 Gamescope are the same too | hashes in both launch records. **(r3)** The build-hash half is now also re-checked by `--require-l1`'s A6, from both run-dirs' `creative-run.json` `runtime` file hashes (`check_build_match()`), not `report.json`'s `build` field (a status string, `session.py:1423`, not necessarily a content hash). The `$SNAP` half is **not** machine-checked: no run record read here identifies which harness snapshot produced a run |
| P7 | After V1: `postrun-gate.py` on V1 prints PASS. A missing, empty or wrong-size still A, B or C makes the run a failure (§4e) | exit code 0. **(r3)** The documented driver command always passes `--require-l1 <L1 run-dir>` (§4e); omitting it now refuses rather than silently running V1's F1/F2 checks alone |

1. **The run needs a new build.**
   - The failed run's `kphasor.dll` (`fd8e069a…dfac2`) does not contain the string `kp.camera.capture` (`grep -a -c` printed `0`; `kp.model.capture` printed `1`).
   - The kp.camera sources are untracked in WT (`git status`: `?? src/api/camera_backend.cpp`, `camera_lua.cpp`, `camera_profiles.cpp`).
   - The run needs a new reviewed build that includes kp.camera. Its hash is not known yet.
   - The route fails closed on a wrong build: step 5 raises `kp.camera missing: wrong build` before any F12 (proven in the stub simulation, §6).
2. **kp.camera has never been read in a running game. The L1 diagnostic must run first. It is BLOCKING.** See WT/docs/lua-api.md, section "Native camera", and CP §2h.
   - The orchestrator ruled this (F3). The failed-run review (condition 3) and FP §0.6(b) say the same thing: a route-only candidate must first pass a separate, bounded framing diagnostic.
   - L1 is `l1-camera-diagnostic.toml` (§5b). It is **non-acceptance**, uses one launch and has no F12. Its media is never acceptance media.
   - V1 is authorized as the acceptance attempt only if L1 meets the §5b admission rule. Otherwise V1 does not run. The orchestrator then chooses between Stage 2 (V2) and a different spot.
   - **(r3) This is now a machine gate, not just a rule an orchestrator must remember.** The r2 re-review (`k1-scale-attempt2-prep-r2-review.md`, Finding I1) constructed a synthetic V1 run directory with zero reference to L1 anywhere and got `postrun-gate.py` PASS. `postrun-gate.py --require-l1` closes that: see P5 and §4e.
3. **Take a fresh harness snapshot.** The failed prep's frozen `creative.py` has no `--capture-marker` / `--cadence-*` flags (grep of `FAILED/harness-snapshot/runtime/kpharness/creative.py` found none). The current WT `creative.py` (`0e302254…`) has them (lines 410-413).
   - WT has other active writers right now (new files under `scripts/harness/scenarios/object-blaster`, `src/harness`, `tools`). Snapshot only after those settle, and re-run `validate.py` against the snapshot.
4. **The capture diagnostic must pass first** (FP header; WT/docs/creative-runner.md "Animated-pattern capture diagnostic"). The failed master measured about 54.5 FPS encoded, 109 gaps over 50 ms, and `drop=1293` (review).
5. **Stage the scene script.** Deploy it with a second `--script`, next to the frozen helper. Both are autoloaded as host scripts; both are inert at load (§3).
6. **One launch only: set `KP_MAX_BOOT_ATTEMPTS=1` in the driver environment (F1).**
   - Why: `WT/scripts/harness/kpharness/session.py:74` sets `BOOT_ATTEMPTS = 5`. At `:76-79`, `KP_MAX_BOOT_ATTEMPTS` "down to 1 = exactly one game launch with no relaunch".
   - The failed prep's frozen snapshot cannot honour it: `grep -c KP_MAX_BOOT_ATTEMPTS FAILED/harness-snapshot/runtime/kpharness/session.py` printed `0`. The current WT `session.py` (`29a454b2…1b14`) printed `4`. So P2 requires a fresh `$SNAP` with a count of at least 1.
   - The variable reaches the runner. `gamescope_snapshot.py:330` copies `os.environ` into the child environment, and WT `creative.py:164` records `env` in the receipt.
   - Since the prep, WT `creative.py` has changed (`0e302254…` to `08d9a4a5…`). It now passes `max_boot_attempts=1` to the session itself (`boot_budget`, `:150-164`). It also refuses a bad env value before the run starts (`resolve_max_boot_attempts()` at `:158`). So the env variable is belt and braces on this build. It is still mandatory: it is the ruling, and it protects against an older `$SNAP`.
   - **r2 re-verification (read-only, this pass):** `WT creative.py` has moved a third time, to `f160f81f0acdab15b8815aa12395fd47db5c0879ce86fb428dcf69e9c4e29ee6` (`sha256sum` just now). `session.py` is unchanged at `29a454b2fbe15a4e68c267b2e9b59db1dafff7082902f27a3d6c0e0d05e41b14`, and `grep -c KP_MAX_BOOT_ATTEMPTS session.py` still prints `4`. WT is still moving on `creative.py` specifically: none of the three hashes recorded here (prep-time, mid-prep, this check) should be treated as `$SNAP`'s eventual hash. P2 stands: take `$SNAP` fresh, right before the launch, and re-run `validate.py` against whatever `creative.py`/`session.py` land in it, not against any hash in this report.
   - Post-run check (`postrun-gate.py`, §4e): `boot-attempts.json` shows `max_boot_attempts == 1`, `launch_count == 1`, one entry in `attempts`, and `outcome == "channel"`. `creative-run.json` must also show `boot_attempts.env == "1"` and `acceptance_eligible == true`. `max_boot_attempts_source` is recorded. It is not gated, because on this build it reads `kwarg` and not `env` (`session.py:101-125`).
   - The same applies to L1.
   - **File-level check (this pass):** `grep -n KP_MAX_BOOT_ATTEMPTS l1-launcher-args.json launcher-args.json`. `l1-launcher-args.json` carries it directly (`"KP_MAX_BOOT_ATTEMPTS": "1"`, key `env`). V1's `launcher-args.json` was left byte-identical in r2 (§1) and does **not** carry the variable at all — the grep returns nothing for it. This is not a defect in the file (r1 predates the ruling and nothing here rewrites V1's launcher flags), but it means the env var is not self-contained in the artifact: the driver must set `KP_MAX_BOOT_ATTEMPTS=1` in its own environment before invoking V1, per P3, or the run is not acceptance-eligible even though the route TOML itself is fine. `postrun-gate.py`'s `KP_MAX_BOOT_ATTEMPTS unset=FAIL` fixture is what catches a driver that forgets this.

## 1. Files

| File | SHA-256 | Role |
|---|---|---|
| `task7s2-v1-readonly-camera.toml` | `0fbca9b9…803b49` | **V1** route (runnable candidate). 46 steps; 3 physical F12 submissions; `shot_interval=0`. |
| `task7s2-v2-stage2-PLACEHOLDER.toml` | `421e3eae…b4d1a3` | **V2** placeholder. **Not runnable.** The loader rejects it (§6). |
| `task7s2_scale.lua` | `9fc558d4…0928e4` | Scene script (product layer): `construct`, `arm`, `cleanup`; markers; construct-time camera line; log-only camera watch. |
| `generate-route.py` | `3ae63e04…e2a5df5` | Generator. One `GIANT` constant feeds the typed command, the phase-2 gate and the phase-2 marker. It asserts they agree, and asserts that the Lua tolerances equal the route's. |
| `launcher-args.json` | `59892fb5…0c06` | Proposed marker flags for `kpharness.creative`. |
| `framing-fit.py`, `framing-fit-output.json` | `83907263…b7f`, `b5e79125…8558` | Re-derivation of FP §2b/§2c. Used to choose the giant scale. |
| `validate.py`, `validation-output.txt` | `35e87886…ad643d` (r3), `d2a84839…a0467d` (r3, scratch-run copy) | Offline validation and its output (r2: adds the L1 and post-run-gate checks; r3: adds check 9, `postrun-gate.py --require-l1`, red-first against `postrun-gate.py.pre-r3`, five negative-admission/build-mismatch cases and a same-directory green-first REFUSE, all added after self-review; check 9's own scratch dir (`.reql1-scratch`, inside whatever copy of this directory `validate.py` is run from) is a fixed name, not a random `mkdtemp` suffix, so re-running `validate.py` twice *from the same copy* gives a byte-identical `validation-output.txt` -- confirmed two consecutive in-place runs, `diff` silent. Two of check 9's REFUSE messages embed that copy's own absolute path (the `no --require-l1` route path and the missing-`admission.json` OSError), so the hash above, `d2a84839…a0467d`, only reproduces from the exact scratch path this pass used, `$TMPDIR/k1r3-final-scratch/copy`; a run from PREP itself or a different-named scratch copy gives the same *content* with different embedded paths and therefore a different hash, same as r2's own scratch-path caveat in §6. Check 9 also requires `postrun-gate.py.pre-r3` to exist next to `validate.py`, since its red-first case runs that file directly). |
| `l1-camera-diagnostic.toml` | `07ba1555…c635d` | **L1**, NON-ACCEPTANCE camera diagnostic (§5b). 47 steps, no F12, 4 stills, `shot_interval=0`. |
| `l1_camera_probe.lua` | `c2168be8…795b` | L1's only `--script`. Inert host script: one load line `[l1cam] loaded camera=present/absent`, no timers, no routines. |
| `generate-l1.py` | `4aeaba8d…73ce` | L1 generator. It imports `generate-route.py` and asserts that the reused V1 chunks are byte-identical. It does not rewrite V1, V2 or `launcher-args.json`. |
| `l1-launcher-args.json` | `0e451634…3f1a` | Proposed L1 flags and env (`KP_MAX_BOOT_ATTEMPTS=1`). No capture markers and no cadence window. |
| `postrun-gate.py` | `b3dbf34b…ac99ff` (r3, was `0c44c379…6175` in r2) | Mandatory post-run gate for V1 and L1: one launch (F1), and all stills present, non-empty and 1024×768 (F2). **(r3)** adds `--require-l1 <L1 run-dir>`, mandatory for any route other than the checked-in L1 route itself (§4e, §5b, Finding I1). |
| `sim-native-log-tps10.txt`, `sim-native-log-tps60.txt` | `ffd43d73…cb75`, `9ce91a12…1ea1d` | Simulated native logs fed through the WT recorder's marker observer. Host simulation only. |

Full hashes are in `validation-output.txt` (first lines) and in the `sha256sum` output of the final report message. r2 left V1, V2, `task7s2_scale.lua`, `generate-route.py`, `launcher-args.json`, the fit files and both sim logs byte-identical. That is checked by `sha256sum` before and after: those hashes are unchanged from the table above. r3 additionally left `l1-camera-diagnostic.toml`, `l1_camera_probe.lua`, `generate-l1.py` and `l1-launcher-args.json` byte-identical to r2 (same hashes as the row above); only `postrun-gate.py`, `validate.py`, `validation-output.txt` and this report changed. `validate.py` regenerates `sim-native-log-tps10.txt` and `sim-native-log-tps60.txt` on every run (their mtimes move each time `validate.py` runs); their content did not: `sha256sum` this pass gives `ffd43d73…cb75` and `9ce91a12…1ea1d`, unchanged from the table above, same as r2 found.

**(r3) Two new run-directory artifacts**, not files in this directory but records the operator/orchestrator produces alongside a run, that `--require-l1` reads:

- `postrun-gate-result.json`, written by `postrun-gate.py` itself into `run_dir` every time a full F1/F2 gate completes (PASS or FAIL): `{"verdict", "route", "route_sha256", "run_dir", "checked_at"}`. This is the audit trail proving the gate actually ran against that run directory (P5/R1); it is not itself trusted for the route hash or the boot-attempt count, both of which `--require-l1` re-reads directly from `creative-run.json` / `boot-attempts.json` in case the receipt is stale (validate.py check 9, the launch_count=2-with-a-stale-PASS-receipt case).
- `admission.json`, written by the orchestrator after doing the §5b measurements on the finished L1 run (silhouette heights, `doorbox.py` feature displacement, the R1a/R3a/R3a-`ps`/dolly/delta receipts already in L1's `report.json`): `{"beh_r1a", "ps_r1a", "beh_r3a", "ps_r3a", "dolly": [R1..R4], "height_still3", "height_still4", "feature_disp_3_4": {"dx","dy","row_span_delta"}, "r4_vs_r3": {"idsame","dcfg","dq","dp38","dp50"}, "feature_disp_1_2": {...}, "r2_vs_r1": {...}}`. `postrun-gate.py` re-derives A1-A5 from these numbers against the exact §5b thresholds (192-230 px, `abs(dx)`/`abs(dy)` ≤4 px, `abs(row_span_delta)` ≤2 px, ≤1e-4, `idsame=1`) rather than trusting a boolean, and rejects a missing or non-finite (`NaN`/`inf`) field as a problem instead of defaulting it to 0 or "no motion" — see `check_admission()` in `postrun-gate.py` and the Grill me answer below on what this does and does not prove. A6 (build match) is checked separately by `check_build_match()` from both run-dirs' `creative-run.json` `runtime` map (the sha256 of each deployed runtime file, `creative.py:326`), not from `report.json`'s `build` field: `session.build` is a status string the game reports at connect (`session.py:1423`), not necessarily a content hash, so a same-directory rebuild could share it. The `$SNAP` half of P6/A6 is **not** mechanically checked: no run record read here identifies which harness snapshot produced a run.

## 2. Sequence and phase markers

Order in the native log (`kotorphasor.log`). Each line appears once.

| # | Line (regex name in `launcher-args.json`) | Emitted by | Meaning |
|---|---|---|---|
| 1 | `[task7s2] camera_construct dist=… pitch=… height=… fov=… q=… p=…` | F12 #1 (scene) | Scene-side camera reading before the marker. Proven path to the native log. |
| 2 | `[task7s2] armed tiny=0.350 giant=1.900` | F12 #2 | Timer registered and trigger set. Asserted by step 22. |
| 3 | `[task7s2] calm_start` (`calm_start`) | scene | **Cadence window opens.** Comes at least 180 callbacks and at least 3 s after arm. Step 21 fails the run if it fired before the console closed. |
| 4 | `[model-scene:task7s2] phase=1 actor=1 base=0.350 …` (`tiny`; also `--marker`/`effect_start`) | helper | Tiny. At least 120 callbacks and at least 2 s of calm normal after `calm_start`. |
| 5 | `… phase=2 actor=1 base=1.900 …` (`giant`) | helper | Giant, with a 60-callback hold |
| 6 | `… phase=3 actor=1 base=1.000 …` (`normal`) | helper | Normal size again |
| 7 | `… restored actors=1 holding-original-scale` (`restored`) | helper | kp.model.restore verified, with a 60-callback hold |
| 8 | `… complete phases=3 restored=1` (`complete`) | helper | Completion published after readback |
| 9 | `[task7s2] camera_watch samples=N max_q=… max_p=… cfg_changed=0 failures=0 stable=1` | scene | Per-callback camera watch from `calm_start` to here. Log-only. Asserted by step 35. |
| 10 | `[task7s2] calm_end` (`calm_end`) | scene | **Cadence window closes.** At least 120 callbacks and at least 2 s of restored normal after `complete`. |

Lines 3-8 and 10 are each asserted exactly once (steps 27-33). The scene failure and timer error lines are asserted absent (step 36).

- **The harness-side camera receipts are in `report.json`, not the native log.** Harness-state `kp.print` never reaches `kotorphasor.log`: the CAL log has 0 `camera-calibration` lines even though CAL step 5 printed one.
  - The baseline and after-window receipts therefore come from `lua` steps 10 and 38. They return strings of about 140 characters, and `report.json` keeps about 200 characters of the detail (`scenario.py` `lua ->` `[:200]`).
- **Marker order.**
  - The WT recorder checks the configured order of named markers and excludes `effect_start` (`recording.py` `_marker_order_status`). The configured order equals the log order, one name per line.
  - Running the recorder's own `observe()` on the simulated log gives `order=ordered duplicates=[]`.
  - `effect_start` and `tiny` match the same line. That is allowed: each name is recorded once, and `effect_start` is excluded from the order check.

**Choosing reviewed clip bounds later:**

- Use the capture-clock times that `capture.json` records for `calm_start`, `tiny`, `giant`, `normal`, `restored`, `complete` and `calm_end` (100 ms polling, uncalibrated start latency).
- Start at or after `calm_start`, at least 2 s before the first frame showing the tiny body. End at or before `calm_end`, at least 2 s after the first frame showing restored normal size.
- Confirm both edges on decoded frames, following the export section of WT/docs/creative-runner.md ("Choose actual frame-reviewed boundaries…"). Do not reuse the failed run's 204-224 s.

**Physical submissions (typed text, exact):**

1. `task7s2=dofile('kotorphasor/scripts/task7s2_scale.lua');return task7s2.construct{tiny=0.35,giant=1.9}`
2. `return task7s2.arm()`
3. `return task7s2.cleanup()`

Each expects `contains=["boolean: true"]`, `expect_values=[{type="Boolean", value=true}]` and `return_count=1`. These are the same as in the failed route.

## 3. Layers

- **The harness TOML is the test driver.** It loads the save, sets the chase mode once, settles and gates the camera, opens and closes F12, types the three commands, reads native scale independently at each phase, and checks log bounds. Its Lua reads `kp.model`, `kp.camera` and `nwscript.call` directly. It does not reuse the scene script's code.
- **The scene script is the product layer.** It is `task7s2_scale.lua` plus the frozen `model_scene.lua`. It uses only `kp.*` and `nwscript.call(<routine>, …)`.
  - The NWScript-name scan checked all 76 chunks (1 scene script + 18 V1 `code=` steps + 20 V2 `code=` steps [V2 is rejected by the loader, but its `code=` entries are still read and scanned raw, per `validate.py:120-121`] + 36 L1 `code=` steps + 1 probe script = 76; r1's 39 was 1+18+20), the script and the helper against the 772 K1 routine names. It found no bare routine names (§6).
  - The routines actually executed in the simulation are listed in §6.
  - I read "no NWScript names in Lua" as "no routine exposed or called other than through `nwscript.call`", following WT/docs/scenario-toml.md ("Lua chunks use `nwscript.call` for engine routines and `kp.*` for native host facilities") and FP §1.
- **Helper choice: frozen `model_scene.lua` `07c533c2…a0e`.** This helper passed the failed run's native gates live. The WT copy (`2af947fe…c287`) adds `identify`/`matches` ownership, but only on `spawn=true` paths. For `spawn=false` the two behave the same: I read the diff, `self.ownership[pc]` is nil and the call becomes `snapshot(id, nil)`. The WT `kp.model.snapshot` accepts one or two arguments (`model_lua.cpp` `take_snapshot`, `lua_isnoneornil(L,2)`).

## 4. V1: read-only camera

### 4a. Spot and angle

- The spot is unchanged: same save `000001 - AUTOSAVE`, `danm14aa`, PC at (105.7, 96.5, 1.0).
- **No angle knob is proven**, so V1 does not rotate anything:
  - `SetCameraFacing` is expected to be inert under the chase behaviour (CP §0.3).
  - CAL shots 0007, 0008 and 0009 (angles 90, 180, 270) look nearly the same (FP §1b).
  - PC `SetFacing` through `with_caller` has never run live.
  - The route calls only `SetCameraMode(p,2)`, once (step 6). It drops the failed route's `SetCameraFacing(GetFacing(p))`.
- **Settle hypothesis (unverified).** The failed run gave the camera only 120 ticks before the scene, and the view was still panning about 10 px/s at 202-220 s. In CAL, the same spot drifted from the 272 px view (shot 0006, 180 ticks after mode 2) to about 220 px (shot 0007, about 380 ticks after), and stayed nearly still through 0008 and 0009.
  - V1 therefore waits 600 ticks (step 7).
  - It then requires the raw camera fields to stay within tolerance of one fixed anchor for at least 15 samples **and** at least 20 wall seconds (step 8, timeout 300 s).
  - It then checks again after 180 more ticks (step 14).
  - If the settled view is again about 272 px, V1 fails G1 at any giant scale (FP §0.6). The route cannot see pixels, so that failure shows up only in the offline gate.

### 4b. Giant scale: 1.9

`framing-fit.py` reproduces FP §2b/§2c exactly for all five clip-consistent fits. For example, fit 670/+0/−5 gives top@2.0 = 36.9 at the RUN camera and k = 1.161/1.286/1.435. FP gives 37 and 1.16/1.29/1.44. The results are FOV-invariant: 40°, 55° and 70° give identical rows.

The largest giant scale that keeps at least 60 px of top headroom, by model normal height:

| Model normal px | 205 | 211 | 217 | 220 | 225 | 230 | 235 | 240 |
|---|---|---|---|---|---|---|---|---|
| worst fit (670/+5/−5) | 2.069 | 2.033 | 2.000 | 1.984 | 1.958 | **1.933** | 1.909 | 1.887 |
| min of the other four | 2.082 | 2.082 | 2.047 | 2.031 | 2.005 | 1.980 | 1.955 | 1.932 |

- **Two pixel definitions.**
  - The *model* height runs from the hem ground (row 670) to the head top. At the RUN camera it is 251-261 px.
  - The *measured* G1 height runs from the head top to the boot bottom. At the RUN camera it was 272 px, so measured ≈ model + 11-16 px.
  - FP's "2.0 only if G1 ≤ 211 px" treats measured as model, which is conservative.
- **Why 1.9.** V1 cannot choose its distance, so the giant scale must be safe across the whole G1 band (192-230 px measured).
  - Even treating measured as model, the worst fit keeps at least 60 px up to 230 px at 1.933 ≥ 1.9. With the boot offset it holds to about 245-250 px measured.
  - 1.95 fails the worst fit at 230 px (1.933 < 1.95).
  - 2.0 holds only up to 217 px model.
  - 1.9 is 5.43 × tiny, so the phases stay clearly distinct.
- **Limits.**
  - These fits are calibrated on the RUN view under a dolly-along-view-ray model. For a different settled view they are only indicative.
  - If the settled view is still about 272 px measured, 1.9 is marginal: the 16 px-margin maximum at the RUN camera is 1.876-2.046 across fits. That is `run_max_scale_16px` in `framing-fit-output.json`, printed by `python3 -c "import json;d=json.load(open('framing-fit-output.json'));v=[f['run_max_scale_16px'] for f in d['fits'].values()];print(min(v),max(v))"`, which gives `1.876 2.046`. (r1 quoted 1.868-2.089 without a referent; M1.)
  - G1 fails either way in that case.

### 4c. Camera stability gate (fails the run if the camera moves)

A distance/pitch/height-only gate **would have passed the failed run**: the door box rows and height stayed fixed while the view panned in yaw (FP §2a). So the gate compares all of these:

- **Identity and state, exact:** `behavior=="chase"`, `pending_style==-1`, `mode`, `module`, `camera`, `behavior_ptr`, `style_row`, and `dolly` unchanged. Unchanged, not `==0`: the stage-1 report says +0x84 can be uninitialised.
- **Configured fields within 1e-4:** `distance`, `speed`, `pitch`, `height`, `base_distance`, `base_view_angle`.
- **Motion:** `raw_28_unverified` (4 floats) within 1e-3 per component. `raw_38_unverified` and `raw_50_unverified` within 0.01 per component.
- **PC pose:** `GetFacing` within 0.1° and `GetPosition` within 0.01.

**Tolerance arithmetic, against G5's 4 px limit.** Focal length is f = 384/tan(27.5°) = 737.6 px, at an assumed 55° vertical FOV. The baseline receipt logs `base_view_angle` so this can be checked.

- For a unit quaternion, a rotation δ moves each component by at most about δ/2. A 1e-3 component tolerance therefore triggers at δ ≈ 2e-3 rad = 0.115°, which is 0.002 × 737.6 ≈ **1.5 px**.
- A 0.01-unit lateral shift at the 6.25-unit default distance is 0.01/6.25 × 737.6 ≈ **1.2 px**.
- Both are under 4 px.
- For scale: the CAL drift of about 17 px per 207 ticks crosses 1e-3 in roughly 18 ticks.

**Where the gate runs:**

- **Before the start marker:**
  - step 8 (settle)
  - step 9 (baseline equals the settle anchor; receipt in step 10)
  - step 14 (unchanged after 180 ticks and two stills)
  - step 20 (console closed)
- **At every phase gate and at completion:** steps 23-26. Each poll re-checks the camera and raises `camera moved at …`.
- **After `calm_end`:** step 37, with its receipt in step 38.
- **Scene side:** a per-callback watch from `calm_start` to `calm_end`, asserted by step 35. It is log-only and never changes scale behaviour.
- **After cleanup:** step 45 records the camera comparison only; it is not a gate.

**Detection latency.** The route gates sample only while polling. In the simulation, a raw_28 move that began during the giant hold was caught at the phase-3 poll, one gate late. The run still fails.

A camera that moves and returns within one hold is caught only by the scene-side watch (step 35). The offline G5 check covers both cases.

**Limit.** The raw fields' meaning is unverified (lua-api.md; CP §1c). The in-route gate can **detect** motion. It cannot **prove** stillness. The offline G5 pixel check stays authoritative.

### 4d. Framing measurement gate (offline, on stills outside the cadence window)

The stills come from `screenshot=true` at step 11 (baseline A), step 13 (baseline B, 180 ticks later) and step 39 (restored, after `calm_end`). Periodic shots are off (`shot_interval=0`).

- The default is a periodic shot every 120 s. CAL screenshot steps took 0.17-0.35 s, so one landing in the window would break the 50 ms gap rule. All three are outside [`calm_start`, `calm_end`], so an in-window screenshot stall cannot hurt the cadence gate (FP §3b risk note). Phase stills for G3/G4 come from the decoded master after the run.

- Head and foot rows come from a connected-component silhouette, seeded at the torso centre and grown by colour distance (FP §3d). Do not use a global colour threshold.
- Measure HUD boxes on baseline A.

| Gate | Rule (measured px, head top to boot bottom) |
|---|---|
| G1 | A and B: 192-230 px. At 1.9 no tighter ceiling is needed (§4b). |
| G2 | C against A: height and foot row each within ±6 px |
| G3 | Every master frame in the giant hold: silhouette rows 16-752, at least 16 px from each measured HUD box and from companions |
| G4 | Tiny hold: height at least 48 px, not hidden |
| G5 | A fixed background feature sampled at ≥ 2 Hz from `calm_start` to `calm_end`: at most 4 px in x and y; feature height within ±2 px. Also A against B and A against C. |
| G6 | Before acceptance: refit §2b on A plus the tiny frames. Predicted top@1.9 ≥ 60 px. |

### 4e. Stills are mandatory: post-run gate (F2); L1 is mandatory: `--require-l1` (r3, F3/Finding I1)

A missing framing still is a **run failure**. The documented driver command for a V1 acceptance check is now:

```
python3 -I -S -B postrun-gate.py --route task7s2-v1-readonly-camera.toml --run-dir <V1 runs/STAMP> --require-l1 <L1 runs/STAMP>
```

(exit 0) before G1-G6 are judged and before acceptance. `--require-l1` is not optional for V1: `postrun-gate.py` treats any route whose content hash is not the checked-in `l1-camera-diagnostic.toml`'s as an acceptance route, and **refuses** (nonzero exit, one line, e.g. `REFUSE: missing-l1: acceptance route ... requires --require-l1 <L1 run-dir>`) if `--require-l1` is absent — it does not silently run the F1/F2 checks alone the way r2's gate did. This closes the r2 re-review's Finding I1, which built a synthetic V1 run directory with no L1 trace anywhere and got `PASS` from r2's gate (reproduced here again, red-first, against `postrun-gate.py.pre-r3`, before r3's fix existed: `validate.py` check 9, `validation-output.txt` line `RED-FIRST pre-r3 (V1, no L1 anywhere)=PASS exit 0`).

When `--require-l1 <L1 run-dir>` is given, `postrun-gate.py` refuses (same one-line form, `REFUSE: l1-precondition: ...`) unless all of P5's conditions hold, checked in this order (first failure wins):

1. `<L1 run-dir>/postrun-gate-result.json` exists, its recorded verdict is `PASS`, and its recorded `route_sha256` matches the checked-in L1 route (someone ran this same gate *on the L1 route* against this run-dir, and it passed — not a stray receipt from checking some other route against this directory).
2. `<L1 run-dir>/creative-run.json`'s `route_source.sha256` — the hash the WT runner itself took of the route file at launch time, not an operator-typed path — equals the sha256 of the `l1-camera-diagnostic.toml` checked into this directory right now.
3. `<L1 run-dir>/boot-attempts.json` (read directly, independent of #1's cached receipt) shows `launch_count == 1`.
4. `<L1 run-dir>/admission.json` exists and the §5b admission rule A1-A5 holds under mechanical re-derivation from its recorded measurements (see §1's note on the artifact, and `check_admission()`).
5. A6: both run-dirs' `creative-run.json` `runtime` hashes agree file-for-file (see §1's note, and `check_build_match()`). The `$SNAP` half of P6 is not covered by this.
6. `<L1 run-dir>/report.json`'s `finished` timestamp is earlier than this run's own `boot-attempts.json` `attempts[0].started` timestamp (run records, not filesystem mtimes).

The gate fails (distinct from a REFUSE: this is the ordinary F1/F2 PASS/FAIL JSON verdict) if any of these holds:

- the report has no entry for a still step (steps 11, 13 and 39), or the entry's label differs
- the detail is `no screenshot taken`
- the file is missing or has zero bytes
- the PNG or PPM header is not 1024×768

PPM is accepted because the FAILED run kept `0001_periodic.ppm` when conversion failed. There is **no master-frame fallback** for A, B or C. The same gate also checks F1 (§0 item 6).

Why this is offline, not a route step:

- `scenario.py:1968-1985` returns status `"ok"` even when `Shooter.take` returns None.
- `shots.py:83-122` (unlink at `:118`) deletes the in-game PPM after conversion (`src.unlink()`). The only copy is host-side under `run_dir/shots`.
- No scenario step kind reads host files (`scenario.py` header: do / wait / expect_events / screenshot).

`validate.py` (8) runs the gate on synthetic run directories for both routes. One PASS case uses PNG and one keeps a PPM. It gives FAIL for a still not taken, an empty still, an 800×600 still, a boot budget of 5, two launches, and an unset env.

`validate.py` (9, r3) exercises `--require-l1` end to end as a subprocess (not just the internal `gate()` function, so the CLI's actual stdout/exit-code contract is what's tested): red-first reproduction of Finding I1 against `postrun-gate.py.pre-r3` (PASS, exit 0, no L1 anywhere — the bug); then, against the r3 gate, a well-formed L1/V1 pair (PASS); missing `--require-l1` entirely (REFUSE); an L1 that failed its own gate (REFUSE); a wrong L1 route hash (REFUSE); an L1 `boot-attempts.json` showing `launch_count=2` while its own `postrun-gate-result.json` receipt still reads `PASS` from before the tamper (REFUSE, proving the launch-count check re-reads the file rather than trusting the cached receipt); and an L1 that finished after V1 started (REFUSE).

**Added after a self-review pass** (an advisor read of this same session's transcript, before this was called done, caught that `check_admission()`/`check_build_match()` had zero negative-path coverage even though they now contain real arithmetic): an out-of-band still-3 height, 272px, the exact "272 again" scenario Grill me #2 names as most likely (REFUSE via A3); a feature displacement of `dx=-10` (negative; an unsigned check would have let `-10 < 4` through — this exercises that `abs()` is actually applied, REFUSE via A4); a `NaN` in an R4-vs-R3 delta (`NaN` compares `False` against every `<=` and `>` ordering, so a naive numeric check would silently pass it — REFUSE via A4); `admission.json` missing entirely, distinct from a failed admission rule (REFUSE, "unreadable"); and mismatched `creative-run.json` `runtime` hashes between L1 and V1, i.e. two different builds (REFUSE via A6). Also added: the r3 gate run again on the exact same `v1_only` directory the red-first case used, with no `--require-l1` -- REFUSE, directly beside the pre-r3 PASS on that same directory, not just a separately-built lookalike. All thirteen lines (red-first, that same-directory green check, and eleven `--require-l1` cases) are in `validation-output.txt` under `require-l1:`.

Behaviour gates are unchanged from the failed route:

- three physical F12 receipts correlated by runtime, session and request
- native base readback 1.0 → 0.35 → 1.9 → 1.0 with identity and effective ratio
- locals 5-9 restored
- cleanup

## 5. V2: Stage 2 placeholder (not runnable)

`task7s2-v2-stage2-PLACEHOLDER.toml` is V1 plus two marked steps:

- after the camera-mode step: `kp.camera.set_distance(t7_cam_orig, t7_cam_orig.distance*T7_K)`
- after cleanup: `kp.camera.restore(t7_cam_orig)` with a bit-exact readback

The names follow CP §3 (`set_distance(capture, d)`, `restore(capture)`). **Neither function exists.** `T7_K` is undefined; CP suggests about 1.28 for the 27.5% row.

The file carries the top-level key `NOT_RUNNABLE_STAGE2_CAMERA_API_MISSING = true`. The WT loader rejects it with `ScenarioError: unknown scenario fields: NOT_RUNNABLE_STAGE2_CAMERA_API_MISSING`.

When Stage 2 exists, V2 needs:

- E4-E9 and L2 from CP §3f/§3g
- the giant scale re-chosen for the 27.5% target: 2.0 is then safe, with a worst fit of 74 px headroom
- the settle and stability gates re-checked against Stage 2's speed interpolation

## 5b. L1: camera diagnostic (NON-ACCEPTANCE, blocking for V1)

`l1-camera-diagnostic.toml` follows CP §2h, cut to what V1 needs. Its setup matches V1: same build, `$SNAP`, stage, save `000001 - AUTOSAVE`, `danm14aa`, PC at (105.7, 96.5, 1.0), Gamescope at 1024×768 and `KP_MAX_BOOT_ATTEMPTS=1`. Launch it with `l1-launcher-args.json`:

- `--script l1_camera_probe.lua` only
- `--marker '\[l1cam\] loaded camera='`
- no `--capture-marker` and no `--cadence-*` flags

There is no cadence window, so every still is outside one. The creative runner needs a `--script` and a marker. The probe line gives the clip logic its anchor. The runner's media verdict is ignored for L1.

**Steps** (validate: 47 steps, 0 `console_command`, stills at 10, 13, 30 and 33):

| L1 steps | What | Source |
|---|---|---|
| 1-4 | load save, gameplay, clear pause, dialog | as V1 |
| 5 | Precondition. **Fails early if kp.camera is absent** (`kp.camera missing: wrong build`), unavailable, or not `windows-k1-gog` (§2h step 1) | **V1 step 5 code, byte-identical** |
| 6 | Harness helper library: stores readings, formats receipts. No game effect | L1 only |
| 7-8 | `SetCameraMode(p,2)`, then 600 ticks | V1 steps 6-7, byte-identical |
| 9-10 | Reading **R1** (`kp.camera.snapshot()` plus PC pose, full precision, in harness state), then **still 1** | §2h step 2 |
| 11-13 | 180 ticks, reading **R2**, **still 2** | §2h step 2 |
| 14-26 | Receipts R1a-f and R2a-f, then the delta R2 vs R1 | raw-field log |
| 27-28 | Settle and baseline **rehearsal** | **V1 steps 8-9 code, byte-identical** |
| 29-33 | R3, **still 3** (V1 still-A timing), 180 ticks, R4, **still 4** (V1 still-B timing) | |
| 34-46 | Receipts R3a-f and R4a-f, then the delta R4 vs R3 | |
| 47 | +180 stability rehearsal | **V1 step 14 code, byte-identical** |

- Each reading takes the snapshot and PC pose in one `lua` step, and the still comes in the very next step. The receipts are formatted afterwards from the stored values, so formatting time does not separate a reading from its still.
- The §2h pair (R1 and R2) is on record before any step that can fail on camera state. A settle timeout at step 27 is itself a result: V1 would die at its step 8.
- **Raw fields logged.** Receipts use `%.9g`, which round-trips a float. Each receipt is ≤ 150 characters, so it survives report.json's 200-character detail cut: the longest seen is 136 with adversarial values (validate). Receipts are pcall-wrapped and nil-safe, so they never fail the route.
  - `a`: `behavior`, `mode`, `pending_style`, `dolly`, `style_row`, `behavior_vtable`, `behavior_ptr`, `camera`, `module`
  - `b`: `distance`, `speed`, `pitch`, `height`, `base_distance`, `base_view_angle`
  - `c`: `raw_28_unverified` (4 values)
  - `d`: `raw_38_unverified` and `raw_50_unverified`
  - `e`: PC x, y, z, facing and `os.time`
  - `f`: for both raw_38 and raw_50, r = |(v − pc).xy| and Δz (§2h step 4 geometry)
  - Delta receipts give identity-same, then the max |Δ| of the configured fields, raw_28, raw_38, raw_50, the PC position and facing (`%.4g`), then dt in seconds.
  - A failed snapshot is recorded as `snapshot failed: <code> <msg>`.
- Lua uses only `kp.*`, `nwscript.call` (through `q`) and standard Lua. The name scan is clean across the L1 chunks and the probe.

**Offline checks after L1** (the orchestrator runs these; nothing here runs live):

1. `postrun-gate.py --route l1-camera-diagnostic.toml --run-dir <L1 run>` gives PASS: one launch, and stills 1-4 present, non-empty and 1024×768. Steps 27-47 must be `ok` in report.json. **(r3)** This writes `<L1 run>/postrun-gate-result.json` (§1), which V1's later `--require-l1 <L1 run>` reads back as P5's precondition #1.
2. `kotorphasor.log` has no `camera:` refusal line (§2h step 1). The probe line reads `camera=present`.
3. **Player on-screen height**, measured on stills 3 and 4, which are V1's A and B timing. Also report stills 1 and 2.
   - Decode the PNG (or PPM).
   - Find the torso centre by eye on still 3, and record the pixel.
   - Grow a connected-component silhouette from that seed, using colour distance against the torso median (FP §3d). Do not use a global threshold: FP saw false hits on background at rows 9 and 22.
   - Height = boot-bottom row − head-top row + 1, in 1024×768 pixels.
   - Record the seed, the threshold, the rows and a crop with the rows marked, so a reviewer can re-derive the number.
   - Measure the HUD boxes on still 3 as well (for G3 later).
4. **Background feature displacement.** Run `python3 /home/brunner56/kp-live-20260922/review-probes-k1-scale2/doorbox.py <still1.png> <still2.png> <still3.png> <still4.png>` (`a8ec2c9d…fc6c`, PNG only; convert a kept PPM first). Record the median x and the row span of the orange door panel per still. If the panel is not in view, pick another fixed feature and document it.
5. **(r3) Write `admission.json`** in the L1 run directory from checks 3-4 above plus the R1a/R3a/dolly/delta values already in L1's `report.json` (§1 documents the exact fields). This is what `postrun-gate.py --require-l1` reads to re-derive A1-A6 below mechanically instead of trusting a human's "yes it passed."

**Admission rule. V1 may run as the acceptance attempt only if all hold. (r3: A1-A5 below are now re-derived by `postrun-gate.py --require-l1` from `admission.json` against these exact thresholds, not just checked by eye; A6, build match, is re-derived separately from both run-dirs' `creative-run.json` runtime hashes, not from `admission.json` — see §4e.)**

- A1. Check 1 passes, and L1 completed step 47 (settle, baseline and +180 rehearsal all `ok`).
- A2. R1a and R3a read `beh=chase ps=-1`, and `dolly` is the same in R1-R4.
- A3. Framing: stills 3 **and** 4 each measure 192-230 px (G1). At 1.9 no tighter ceiling is needed (§4b).
- A4. Stillness correlation (§2h step 3) on the V1-timing pair:
  - the still 3 → 4 feature moves ≤ 4 px in x and y, with the row span within ±2 px
  - **and** R4-vs-R3 gives `idsame=1`, `dcfg` ≤ 1e-4, and `dq`, `dp38`, `dp50` each ≤ 1e-4 (the §2h equality rule)
- A5. Check the pair 1 → 2 (R2 vs R1) too:
  - If it moved > 4 px, at least one of `dq`, `dp38`, `dp50` must be non-zero. This shows the raw fields see motion.
  - If it moved ≤ 4 px, the same 1e-4 equality as A4 must hold.
  - If neither pair moved, the "fields see motion" half stays unproven. V1 may still run, and G5 stays the authoritative motion check.
- A6. L1 and V1 share the build hash and `$SNAP` (P6).

If A1-A5 fail, V1 does not run as acceptance. The failure tells us why:

- a settle timeout: V1's step 8 would fail
- the height is out of band: G1 would fail at any giant scale that V1 can use
- the correlation fails: the in-route gates cannot be trusted

Not covered by L1: CP §2h step 4, the ≥ 8-point yaw-sweep collision test. It is only needed to justify Stage 2. The `f` receipts give r and Δz at four points, which helps but does not replace it.

## 6. Validation output (offline)

Command: `python3 -I -S -B validate.py`. It exited 0. The output is in `validation-output.txt`; summary:

- **Loader:** WT `Scenario.load` accepts V1: 46 steps, 3 `console_command` steps, target k1, game_speed 1.0. It rejects V2, as quoted in §5.
- **Route policy:** as `FAILED/control.py`. Three physical commands, each with `expect_values=[Boolean true]` and `return_count=1`. The allowed verbs are **widened on purpose** by `screenshot` and `lua` (steps 10, 38 and 45, record only).
- **Launcher flags:** the WT `creative.parser()` plus `marker_configuration` accept the proposed flags. Markers: `calm_end, calm_start, complete, effect_start, giant, normal, restored, tiny`; cadence runs `calm_start..calm_end`.
- **LuaJIT 2.1 (Lua 5.1 syntax)** compiles all 76 chunks: 1 scene script + 18 V1 `code=` steps + 20 V2 `code=` steps + 36 L1 `code=` steps + 1 probe script (`validate.py:117-128`). r1's count was 39 (scene + V1 + V2 only); r2 adds L1's 36 code-bearing steps (of its 47 total steps) plus the 1-line probe, for +37. These are every `code=` in V1, V2 and L1, including the three typed commands.
- **NWScript-name scan:** no bare routine names. Routines reached through `nwscript.call` in all code, helper included: ChangeToStandardFaction, CreateObject, DestroyObject, GetArea, GetFacing, GetFirstPC, GetIsDead, GetIsInCombat, GetIsInConversation, GetIsObjectValid, GetLocalNumber, GetModuleFileName, GetPosition, GetStandardFaction, Location, SetCameraMode, SetCommandable, SetLocalNumber. The spawn-only ones are not executed with `spawn=false`.
- **Stub simulation (host only, not live evidence).** LuaJIT ran fake `kp.model`, `kp.camera`, `kp.print`, `kp.registertimer` and `nwscript.call`, with separate harness and console environments and a fake clock. It executed V1's own chunks, the scene script and the frozen helper:
  - **Nominal at 10 and 60 ticks per second:** all 46 steps pass. The WT recorder's `observe()` and `_marker_order_status()` on the simulated log give `ordered` with no duplicates. The marker order is as in §2, and every `await_log` bound holds under the harness regexes. Routines executed: GetArea, GetFacing, GetFirstPC, GetIsDead, GetIsInCombat, GetIsInConversation, GetIsObjectValid, GetLocalNumber, GetModuleFileName, GetPosition, SetCameraMode, SetLocalNumber.
  - **raw_28 moves by 0.01 during giant:** the route fails at step 25 with `camera moved at phase 3 poll: raw_28 moved 0.01`. That is one gate late (§4c).
  - **Build without kp.camera:** the route fails at step 5 with `kp.camera missing: wrong build`, before any F12.
  - **raw_28 drifts 2e-5 per tick until tick 1000:** the anchor resets 7 times, then the route passes. Baseline receipt: `…q=0.0000,0.0000,0.3800,0.9400 … r=7`.
  - **The drift never stops:** the route fails at step 8 (settle).
- **L1 (r2)**, all through the WT loader and the same stub sim:
  - **Loader:** WT `Scenario.load` accepts L1 with 47 steps and 0 `console_command`. The stills are at 10, 13, 30 and 33. The name carries NON-ACCEPTANCE, and `shot_interval=0`.
  - **Reused chunks:** the V1 → L1 step map is 5→5, 6→7, 8→27, 9→28 and 14→47, each byte-identical.
  - **Launcher:** `creative.parser()` accepts `l1-launcher-args.json`. Named markers = `{effect_start: probe line}`; cadence is None..None; the size is 1024×768.
  - **Nominal:** all 47 steps pass, with 30 receipts. The longest is 77 characters.
  - **Huge values** (−1.23456789e+30 in every float, 0xffffffff pointers, `pending_style` −2^31): all 15 R1/R2 receipts are recorded, the longest 136 characters. Then the settle rehearsal fails at step 27, as it must.
  - **No kp.camera:** fails at step 5, before any reading.
  - **Non-chase behaviour:** R1 and R2 are recorded (`beh=other`), then it fails at step 27.
  - **Pan between R1 and R2:** passes, with delta `dq=0.0109`.
- **postrun-gate (r2):** runs on synthetic runs for V1 and L1. The PNG and kept-PPM cases PASS. Still not taken, empty, 800×600, budget 5, two launches and env unset all FAIL (see `validation-output.txt`).
- `validate.py` writes into its own directory. So it ran on a scratch copy (`/tmp/kp-r2-scratch/copy`), exit 0, and `validation-output.txt` was copied back. Its hash lines therefore show the scratch paths. The regenerated sim logs were byte-identical to the prep's (`cmp`).
- **(r3)** Re-run the same way: `validate.py` copied to `$TMPDIR/k1r3-final-scratch/copy` and run there (`python3 -I -S -B validate.py`), exit 0, `validation-output.txt` copied back — hash lines and the `require-l1:` `no --require-l1`/`missing admission.json` lines therefore show that scratch path (`$TMPDIR/k1r3-final-scratch/copy/...`), same convention as r2. This copy must also carry `postrun-gate.py.pre-r3` alongside `validate.py`: check 9's red-first case runs it directly by path, and a re-run against a fresh `$SNAP` that forgets to bring this backup file along would raise, not silently skip, the red-first case. All thirteen `require-l1:` lines from that run:

```
require-l1: RED-FIRST pre-r3 (V1, no L1 anywhere)=PASS exit 0 <- the bug Finding I1 found
require-l1: GREEN, same dir, r3 (V1, no L1 anywhere)=REFUSE: missing-l1: acceptance route <scratch>/task7s2-v1-readonly-camera.toml requires --require-l1 <L1 run-dir> (round-2 Finding I1: a V1 check with no L1 path must refuse, not silently pass) (exit 1)
require-l1: well-formed pair=PASS exit 0
require-l1: no --require-l1=REFUSE: missing-l1: acceptance route <scratch>/task7s2-v1-readonly-camera.toml requires --require-l1 <L1 run-dir> (round-2 Finding I1: a V1 check with no L1 path must refuse, not silently pass) (exit 1)
require-l1: L1 failed its own gate=REFUSE: l1-precondition: L1 gate did not pass: verdict='FAIL' (exit 1)
require-l1: wrong L1 route hash=REFUSE: l1-precondition: L1 route hash 'deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef' != checked-in l1-camera-diagnostic.toml '07ba1555e4ce8d260c685ba2ed15fafa38561ea16fa04f6931f37848769c635d' (exit 1)
require-l1: L1 launch_count=2 (stale PASS receipt)=REFUSE: l1-precondition: L1 boot-attempts.json launch_count=2 (need 1) (exit 1)
require-l1: L1 after V1 started=REFUSE: l1-precondition: L1 finished (5010.0) did not happen before this run started (95.0) (exit 1)
require-l1: admission A3 (height 272px, out of 192-230 band)=REFUSE: l1-precondition: admission rule failed: A3: still 3 height=272 not in 192-230 (exit 1)
require-l1: admission A4 (dx=-10px, sign must not hide it)=REFUSE: l1-precondition: admission rule failed: A4: feature dx=-10.0 exceeds 4px (exit 1)
require-l1: admission A4 (dq=NaN, must not pass "<=1e-4")=REFUSE: l1-precondition: admission rule failed: A4: equality rule failed: field 'dq' is not a finite number: nan (exit 1)
require-l1: missing admission.json=REFUSE: l1-precondition: L1 admission.json unreadable: [Errno 2] No such file or directory: '<scratch>/.reql1-scratch/l1-noadm/admission.json' (exit 1)
require-l1: admission A6 (runtime hash mismatch = different build)=REFUSE: l1-precondition: A6: build mismatch on runtime file 'kphasor.dll': L1 sha256='aaaa' V1 sha256='bbbb' (exit 1)
```

## 7. Input hashes

| Input | SHA-256 (as of the r2 write) | r2 re-verify (this pass, read-only) |
|---|---|---|
| FAILED/physical-native-scale.toml | `2e8e403a4ce0873aeeabd810624955502f65c9acc719737bab9dfdb473ee9e0e` | not re-checked (static FAILED tree) |
| FAILED/generate-route.py | `9d430c2294e25641951f37cd9f6301a6e860607866a156ef34811911b114703a` | not re-checked (static FAILED tree) |
| FAILED/control.py | `eb9ff93be492636e4f23b6122968b9b92868485d4344c2baa58d4993ebe65110` | not re-checked (static FAILED tree) |
| FAILED/launch-once.json | `05dfbaf4be5460cb4c37d37611d82a0f81505ff52b74c9b60bc448e58db9c019` | not re-checked (static FAILED tree) |
| task7-k1-framing-plan.md | `ff6634c4aecbeb3477cd06c31a8e993bcfcdeb2b4fcaf79f5a397342d290b999` | not re-checked (static) |
| task7-scale-framing-fix-brief.md | `5ee37e449c84974796a7838df3a33ef3681ce127cc2e0cd3370e841163802c49` | not re-checked (static) |
| task7-k1-scale-run-review.md | `b9757949e11eef19812ea95ab1d2467b634cdd2516be000bfcc6ab56e51133e9` | not re-checked (static) |
| kp-camera-api-plan.md | `69c2da3d8feee529962e3559c344b949d51cc83ddab8fddc84c80a28977116f1` | not re-checked (static) |
| WT/.superpowers/sdd/lua-boundary-validation-plan/camera-stage1-report.md | `aad97452bcd16c7c7a5f40733f5a0f63b0d4ee57c73ed703a822ac888577cdf9` | not re-checked |
| WT/docs/creative-runner.md | `90cd385a1af61845d8f04738674f8069669e21cc982458e6fa17440940502bfc` | not re-checked |
| WT/docs/lua-api.md | `f2c41e6a4a40d126fadbf7ffcb99c853de389852ca0d8db42ab28e5d37b4f64f` | not re-checked |
| WT/docs/scenario-toml.md | `9a6a9cae0a1e18c072bd727471485fc65e5b7b21e93d3fbc9f5690c0b397cc0b` | not re-checked |
| WT/src/api/camera_lua.cpp (field names) | `772d4e2125c1eff5da8866118e88d007cf36da293bb851523fedc35ede1bd106` | not re-checked |
| WT/scripts/harness/kpharness/scenario.py | `98f1b3678bdd5f363184a621cd5ad8ee12b2f7976c7e1262a8df9931c1bfdf47` | **unchanged, re-verified again in r3**: `98f1b3678bdd5f363184a621cd5ad8ee12b2f7976c7e1262a8df9931c1bfdf47` (sha256sum, r3 pass, identical). `--require-l1`'s R5/R6 read `Report.started`/`.finished` (`scenario.py:376-395`, written at `:481` and `:2061`) -- unchanged lines, same hash |
| WT/scripts/harness/kpharness/creative.py | `0e302254335d0acc3e95be786365a1544642b169377c4a08c67504f373de3ee6` | **unchanged since r2's last re-verify**: `f160f81f0acdab15b8815aa12395fd47db5c0879ce86fb428dcf69e9c4e29ee6` (sha256sum, r3 pass, identical to the "moved again" value r2 already recorded -- WT did not move this file again between r2 and r3). `--require-l1`'s R2/R6 read `route_source` (`creative.py:284-311,452`) and `runtime` (`:326`) -- same hash, so these lines are as r2 last saw them. **Still not `$SNAP`**: P2 must re-grep these field names (`route_source`, `'runtime'`, `boot_attempts`) in whatever creative.py lands in the fresh snapshot, the same way it already re-greps `KP_MAX_BOOT_ATTEMPTS` |
| WT/scripts/harness/kpharness/creative_steps.py | `bc1849a0c63a603766d8b63fec33077f893bfcfef256a56a301506763522c89c` | not re-checked |
| WT/scripts/harness/kpharness/recording.py (r3, new dependency: `artifact()`, `sha256()`) | `939160e924db2bf74321917ce27af6099f73d7bbbace31e3fc06c3eac735deb9` | read this pass: `artifact()` at `:426` is what makes `route_source.sha256` and `runtime[name].sha256` a real content hash, not a path |
| WT/scripts/harness/kpharness/session.py:1467 (`attempts[].started`, read by R5) | (row above, `session.py`) | same hash as row above; `grep -c KP_MAX_BOOT_ATTEMPTS` still 4, unchanged |
| WT/data/routines/k1.json | `80b2a9b59096a2edfd4dee6a921f9fd0efc3ce2c142b0215f1a30d146587e957` | not re-checked |
| frozen model_scene.lua (used) | `07c533c28bb588507b473918b90abdb1a440d6099083155e7a86cfff32584a0e` | not re-checked (frozen copy, outside WT) |
| WT model_scene.lua (not used) | `2af947fe2f4384b64b3aa2a7a04d24f5706bce2739cc7f3096c9ba5d459dc287` | not re-checked |
| failed build kphasor.dll (lacks kp.camera) | `fd8e069a1ff5a7b489f32a6492222f396f85e7b74539deb56228395b297dfac2` | not re-checked (static FAILED tree) |
| CAL report.json (stage-k1/runs/20260922-113712) | `40206b20d7898462f3a0d5a244d8092a27c38e9208fae992f0e26ad6a39bf95c` | not re-checked (static) |

## 8. What remains unproven

- **kp.camera live behaviour.** No live read has happened. The mode-2 behaviour may not be `chase`; if it is not, step 8 times out before the marker. The meaning of raw_28/38/50 is unverified. `dolly` may be uninitialised. There is an NaN refusal risk at +0x88/+0x8c (stage-1 M6).
- **The settle hypothesis.** It is not known whether 600 ticks plus a 20 s anchor settle reaches a still view, or whether that view is about 220 px (CAL 0007) or about 272 px (RUN). G1 is judged only offline.
- **Whether the chase camera moves when the model scales.** If it does, the route fails at a phase gate, which is correct but costs the attempt.
- **Quaternion sign flips.** If the engine flips the sign of raw_28 (q and −q are the same rotation), the gate fails falsely. Not observed; unverified.
- **Timer cadence.** Callbacks are timer pumps. The failed run saw about 11 per second, so a 60-callback phase hold lasted about 5-6 s. At 60 per second a hold is about 1 s. I kept `hold_ticks=60` per FP §3c. The lead-in and lead-out have wall-clock floors; the phase holds do not.
- **Capture:** 60 FPS exact-window cadence (prerequisite 4); the new build hash; the fresh harness snapshot.
- **Route-step screenshots under Gamescope have never run.** Only periodic shots are proven (FP §5 claim block).
  - *Correction (F2): r1 said a failed still would stop the run at step 11. That was false.* `scenario.py:1968-1985` gives the step status `"ok"` with the detail `no screenshot taken`, and the route continues.
  - A missing still is caught only after the run, by `postrun-gate.py` (§4e), which makes it a run failure.
  - A stalled still can cost up to 30 s (`channel.screenshot(timeout=30)`). All stills are outside the cadence window.
  - L1 runs the same screenshot path first, so it exposes this risk before V1.
- **Harness-state output is not retained beyond about 200 characters per `lua` step.** The full camera fields are in the scene's `camera_construct` and `camera_watch` native-log lines.
- **The typed command length** (about 100 characters) and console typing reliability. F12 #1 is shorter than in the failed run (about 250 characters). Unverified live.
- **The G1-G6 thresholds come from FP.** The 55° FOV behind the tolerance arithmetic is assumed. The baseline receipt logs `base_view_angle` to check it.

## 9. Claim blocks

```
claim: V1 route loads, has exactly three physical F12 submissions, and its Lua compiles.
referent: validation-output.txt lines "V1 Scenario.load: ok, steps=46, physical_console_commands=3…", "LuaJIT compile … ok, chunks=76"
checked: python3 -I -S -B validate.py (exit 0) against WT scenario.py 98f1b367…
verdict: holds
confidence: high for parsing/syntax; says nothing about live behaviour
```
```
claim: the camera gate fails the run when raw_28 moves during the giant phase, and before any F12 on a build without kp.camera.
referent: validation-output.txt "SIM negative …" lines (step 25; step 5)
checked: stub simulation in validate.py
verdict: holds in simulation
confidence: medium; live raw-field semantics are unverified
```
```
claim: 1.9 is the largest round giant scale that keeps >= 60 px headroom in all five clip-consistent fits across the whole G1 band (<= 230 px, treating measured as model).
referent: framing-fit-output.json max_scale_60px@230 = 1.933 (worst fit 670/+5/-5); 1.95 > 1.933
checked: framing-fit.py reproduces FP §2c table values exactly (e.g. 36.9 / 1.161 / 1.286 / 1.435)
verdict: holds as an estimate
confidence: medium; calibrated on the RUN view only
```
```
claim: the failed build cannot run V1.
referent: grep -a -c "kp.camera.capture" kphasor.dll (fd8e069a…) -> 0
checked: here
verdict: holds
confidence: high
```

```
claim (r2, F1): the one-launch precondition is listed, and it is checked after the run.
referent: §0 P2/P3 and item 6. WT session.py grep -c KP_MAX_BOOT_ATTEMPTS = 4; FAILED snapshot = 0. postrun-gate fixtures: "boot budget 5=FAIL", "two launches=FAIL", "KP_MAX_BOOT_ATTEMPTS unset=FAIL"
checked: grep; validate.py (8) on a scratch copy, exit 0
verdict: holds offline
confidence: high for the check logic. The field names come from WT session.py:1504-1506 and creative.py:163-164, which are the current WT, not the future $SNAP
```
```
claim (r2, F2): a missing, empty or wrong-size framing still fails the run, and the r1 statement is corrected.
referent: postrun-gate.py; validate "still 2 not taken=FAIL", "still 1 empty=FAIL", "still 3 800x600=FAIL"; §8 correction
checked: validate.py (8)
verdict: holds offline
confidence: high. The live report.json detail format is taken from the CAL run (screenshot detail = absolute PNG path)
```
```
claim (r2, F3): L1 is a separate, blocking, non-acceptance route. It fails early without kp.camera and records R1/R2 before any camera-state gate.
referent: validation-output.txt "L1 Scenario.load: ok, steps=47, console_command=0…", "SIM L1 negative (build without kp.camera): FAILS at step 5", "SIM L1 non-chase behaviour: R1/R2 recorded … FAILS at settle rehearsal step 27"
checked: validate.py (7), WT loader and the LuaJIT stub sim
verdict: holds in simulation
confidence: medium. Live raw-field semantics are exactly what L1 exists to find out
```
```
claim (r2, M1): the 16 px-margin maximum at the RUN camera is 1.876-2.046.
referent: framing-fit-output.json run_max_scale_16px, min 1.876 max 2.046 (the python one-liner in §4b)
checked: here
verdict: holds
confidence: high
```
```
claim (r3, Finding I1): F3's "BLOCKING" status is now mechanically enforced. A V1 acceptance
  check with no L1 path refuses (nonzero exit, one line) instead of silently passing, and a V1
  check with a supplied L1 path refuses unless L1's own gate passed *for the L1 route specifically*
  (its receipt's route_sha256 checked, not just its verdict), L1's runner-recorded route hash
  matches the checked-in l1-camera-diagnostic.toml, L1's boot-attempts.json (read directly) shows
  launch_count=1, admission.json's A1-A5 hold under re-derivation (rejecting missing/non-finite
  fields as problems, not defaulting them to 0 or "no motion", and taking abs() of every signed
  displacement), A6 (build match) holds via both run-dirs' creative-run.json runtime-file hashes,
  and L1 finished before V1 started.
referent: validation-output.txt, lines under "require-l1:" -- RED-FIRST pre-r3 reproduces
  Finding I1 (PASS, exit 0, no L1 anywhere) against postrun-gate.py.pre-r3; the r3 gate on that
  same directory REFUSEs (green, same dir, not a separate lookalike); then twelve more cases:
  well-formed pair=PASS; no --require-l1=REFUSE; L1 failed its own gate=REFUSE; wrong L1
  route hash=REFUSE; L1 launch_count=2 with a stale PASS receipt=REFUSE (proves re-derivation,
  not trust); L1 after V1 started=REFUSE; out-of-band still-3 height 272px=REFUSE via A3;
  dx=-10 (negative, still exceeds the 4px band via abs())=REFUSE via A4; dq=NaN (does not
  silently satisfy "<=1e-4")=REFUSE via A4; admission.json missing entirely=REFUSE
  ("unreadable", distinct from a failed rule); mismatched runtime hashes (different build)
  =REFUSE via A6
checked: validate.py (9), subprocess calls to postrun-gate.py itself (not just its internal
  gate() function), on scratch run directories under this session's TMPDIR. The five admission/
  build cases were added mid-session after an advisor pass over this transcript noted
  check_admission()/check_build_match() had shipped with no negative-path test of their own,
  and separately caught: a signed dx/dy that abs() had to be added for; float('nan') passing
  Python's `x > 1e-4` (False) and so needing an explicit math.isfinite() rejection in _num();
  A2 only checking ps_r1a, not ps_r3a as prep-report.md §5b's own text requires; and A6 comparing
  report.json 'build' (a status string, session.py:1423) rather than the runner's own recorded
  runtime-file hashes. All four were real bugs in the first draft of this fix, not just
  missing tests; each is now both fixed and covered by its own case above.
verdict: holds
confidence: high for the mechanics now under test (every REFUSE case was constructed to trip
  exactly one named condition and the reason text was asserted, not just the exit code).
  Medium for whether an operator will fill in admission.json's raw measurements (heights,
  doorbox deltas) honestly from a live L1 run -- the arithmetic on those numbers is now
  mechanical, but the numbers themselves are still hand-entered, not re-derived from the PNGs
  by this script -- see Grill me below
```

## Grill me

1. **(Weakest, r3) `admission.json`'s numbers are still operator-supplied. Doesn't `check_admission()` just move the trust problem, the same way F2 used to trust a route step?**
   - Not the same way, but not fully closed either. F2's flaw was that a route step could not even *notice* a missing still (`scenario.py` always said `"ok"`); nothing offline could learn the truth. Here, every field in `admission.json` traces to something already sitting in the L1 run directory, just typed in by hand rather than parsed: `height_still3`/`height_still4` and the doorbox `feature_disp_*` values need an actual pixel measurement on the stills (no machine record exists for these yet); but `beh_r1a`, `ps_r1a`, `beh_r3a`, `ps_r3a` and `dolly` are transcriptions of L1's own `R1a`/`R3a` receipt strings already in `report.json`, and `r4_vs_r3`/`r2_vs_r1`'s `idsame`/`dcfg`/`dq`/`dp38`/`dp50` are transcriptions of its `"R2 vs R1 …"` / `"R4 vs R3 …"` delta-receipt strings (§5b, `validation-output.txt`'s `SIM L1 nominal` lines show the exact format, e.g. `R2 vs R1 idsame=1 dcfg=0 dq=0 dp38=0 dp50=0 …`). `admission.json` has eleven top-level keys; of those, only four (`height_still3`, `height_still4`, `feature_disp_3_4`, `feature_disp_1_2`) need a real, un-machine-checked measurement. The other seven (`beh_r1a`, `ps_r1a`, `beh_r3a`, `ps_r3a`, `dolly`, `r4_vs_r3`, `r2_vs_r1`) are a copy a human could get wrong but that a regex against `report.json` could check instead.
   - What r3 actually closes: the *arithmetic* (is 210 inside 192-230? is `dcfg` ≤ 1e-4? does `idsame` read 1?) is now mechanical, not eyeballed, and a launch_count or route-hash mismatch is caught even if the human who filled in `admission.json` missed it. What r3 does not close: whether the orchestrator transcribed the receipts correctly and measured the heights/doorbox deltas honestly, rather than typing in whatever happens to pass. That gap is `unverified`.
   - Revised "what an r4 pass should do", cheapest first: (a) parse `beh`/`ps`/`dolly`/`idsame`/`dq`/`dp38`/`dp50` straight out of L1's `report.json` step details with a regex and cross-check them against `admission.json` — this is strictly cheaper than image decoding and covers most of A2/A4/A5's transcription risk; (b) only then, separately, extend `check_admission()` to decode the stills and run the silhouette/doorbox measurement itself for A3/A4/A5's `height_*`/`feature_disp_*` fields, which is the harder, still-undone half.
   - Referent: `postrun-gate.py`'s `check_admission()` re-derives the five thresholds from the recorded numbers; it does not open the PNGs or re-parse `report.json`. `validate.py` (9)'s fixtures supply the numbers directly for this reason. The receipt format referent is `validation-output.txt`'s `SIM L1 nominal` block (R1a/R1b/.../R2 vs R1/R4 vs R3 lines).
2. **(Weakest, r2) Will the §5b admission thresholds actually be met, or does L1 just move the failure one launch earlier?**
   - `unverified`. The only measured mode-2 views are 272 px (RUN and CAL 0006) and about 220 px (CAL 0007), and CAL 0007 looked in a different direction (FP §2a). If the settled view at this spot is 272 px again, A3 fails and V1 does not run.
   - That is the intended outcome. It spends a non-acceptance launch instead of the acceptance attempt, and it is what the review's condition 3 and FP §0.6(b) require.
3. **Can a route step really not check that a still exists?**
   - It cannot. `scenario.py:1968-1985` always returns `"ok"`. `shots.py:118` unlinks the in-game PPM, so harness Lua cannot see it either. No step kind reads host files. So F2 is an offline gate (`postrun-gate.py`), mandatory before acceptance.
   - Referent: the code reads cited, and validate (8) fixtures, e.g. `still 2 not taken=FAIL`.
4. **Why not gate `max_boot_attempts_source == "env"`?**
   - On the current WT runner the session budget comes from the kwarg: `creative.py:160` calls `resolve_max_boot_attempts(1)`, and `session.py:101-125` makes an explicit kwarg win. So the record reads `kwarg` even when the env is set. Gating `env` would fail every correct run.
   - The env precondition is instead proven by `creative-run.json` `boot_attempts.env == "1"` (`creative.py:163-164`).
   - Referent: validate (8) `KP_MAX_BOOT_ATTEMPTS unset=FAIL`. That this receipt field is present on the fresh `$SNAP` is `unverified` until the snapshot exists, because WT is changing (`creative.py` hash moved during this prep).
5. **Does the L1 settle rehearsal test exactly what V1 will run?**
   - Yes, for the code. `generate-l1.py` and validate (7) both assert byte-identity of V1 steps 5, 6, 8, 9 and 14 (map 5→5, 6→7, 8→27, 9→28, 14→47).
   - Not for the timing. In L1, the R1/R2 pair adds about 180 ticks plus 13 receipt steps before the settle, so V1's settle starts earlier after mode 2 than L1's did. If L1 settles only because of that extra time, V1 still has its own 300 s settle budget. That this is enough is `unverified`.
6. **Do the receipts survive report.json truncation?**
   - Yes in simulation. The longest receipt is 136 characters with adversarial values, and 77 in the nominal run. The cut is 200 characters including the 20-character `lua -> {"values": ["` prefix (`scenario.py:699`), and validate asserts ≤ 150 with no quotes or backslashes.
   - Live, the value types are unverified (for example, `dolly` could be garbage). The format is still bounded by `%.9g` plus hex strings.

7. **Is the 76-chunk split verified, not just quoted?**
   - Yes. `validate.py:117-128` builds the `chunks` list as: 1 scene script + one entry per V1 step with `code` in its raw form + one entry per V2 `[[step]]` table with `code` (V2 is rejected by the loader, but its raw TOML is still read and scanned) + one entry per L1 step with `code` + the 1-line probe.
   - Independent recount, this pass, loading V1 and L1 through the WT `Scenario` object directly (not `validate.py`'s own code): V1 has 18 code-bearing steps, L1 has 36 (of its 47 total steps — most of L1's steps are waits, snapshots and stills with no `code=`), and a direct TOML read of V2's `[[step]]` array gives 20 `code` entries. `1 + 18 + 20 + 36 + 1 = 76`, matching `validation-output.txt:17`. r1's 39 was `1 + 18 + 20` before L1 existed.
8. **(r3) `--require-l1` reads WT field names (`route_source`, `runtime`, `attempts[].started`, `report.json` `started`/`finished`) that no earlier r1/r2 check ever depended on. What if `$SNAP` doesn't have them?**
   - Same shape as r2 Grill #3: these field names come from the **current** WT, re-verified this pass (`creative.py` `f160f81f…e29ee6`, unchanged since r2's last re-verify; `session.py` and `scenario.py` also unchanged; `recording.py` `939160e9…35deb9`, newly read this pass for `artifact()`/`sha256()`), not from `$SNAP`, which does not exist yet. Whether `route_source`, `runtime` and `attempts[].started` survive into `$SNAP` unrenamed is `unverified`.
   - Consequence if they don't: `--require-l1` fails closed (a `KeyError`-shaped `None`/missing-field problem, not a silent skip), so a field rename costs the launch window rather than silently accepting an ungated V1 run — but it does cost the window. P2 (§0 item 3) already re-greps `KP_MAX_BOOT_ATTEMPTS` against `$SNAP` before re-running `validate.py`; the same re-grep must now also cover `route_source`, `'runtime'` and `"started"`/`"finished"` in `$SNAP`'s `creative.py` and `scenario.py`, or a rename would only be discovered live.
   - Referent: §7's new rows above; `validate.py` (9)'s fixtures hardcode these field names in synthetic JSON, so they pass regardless of what `$SNAP`'s actual writers emit — check 9 tests `postrun-gate.py`'s logic, not the WT harness's field stability.
9. **(r3) Does `--require-l1` prove the §5b admission measurements were actually decided *before* V1 launched, not written after the fact to make a bad V1 look retroactively authorized?**
   - No. R5 proves L1's `report.json` `finished` is earlier than V1's `boot-attempts.json` launch time -- that the L1 *run* happened first. It says nothing about when `admission.json` itself was written: nothing here timestamps that file, so it could in principle be edited any time before the V1 gate check runs, including after seeing V1's own result. `postrun-gate-result.json`'s `checked_at` cannot substitute either -- it is overwritten by every gate call on that run-dir, including a later one, so it records the most recent check, not the first.
   - This is `unverified` and out of scope for this pass: the ruling asked for A1-A6 to be "recorded as passing" and for the L1-before-V1 run order, not for `admission.json`'s own write time. Closing it would need a signed or filesystem-independent timestamp on `admission.json` itself, which nothing here produces.
   - Also disclosed, not just implied: the malformed-record `except Exception` wrapper in `main()` (added so a non-dict `admission.json` refuses in one line instead of a traceback) has no test case of its own in `validate.py` (9). It is a narrow, mechanical catch-and-format around already-tested code paths, but it is unverified in the same sense as anything else added without a red/green pair.

**Unsettled question (unchanged from r2):** is the settled mode-2 view at this spot 192-230 px, with the raw fields still when the view is still? Only the L1 launch settles it (§5b A3-A5). No offline check can. **New in r3, narrower:** does `admission.json` get filled in honestly from that live L1 run, or could a careless orchestrator type in whatever passes (or mistranscribe a receipt)? `check_admission()`'s arithmetic on the recorded numbers is now mechanical. Seven of its eleven top-level fields (`beh_r1a`, `ps_r1a`, `beh_r3a`, `ps_r3a`, `dolly`, and both delta blocks `r4_vs_r3`/`r2_vs_r1` with their `idsame`/`dcfg`/`dq`/`dp38`/`dp50`) are transcriptions of receipt strings already in L1's `report.json`, and a cross-check regex against that file (cheap, an r4 pass should do this first) would close the transcription half of this gap. The remaining four fields (`height_still3`, `height_still4`, `feature_disp_3_4`, `feature_disp_1_2`) need an actual measurement with no existing machine record to check against; closing that half needs `check_admission()` to decode the stills itself, which is the harder, still-undone part.

## Your options (Compound Engineering)

- `/ce-code-review` on this directory (route, script, validator) before any freeze. A subagent `prove-the-effort-reviewer` can attack the Grill me answers.
- Authorize the L1 launch (`l1-camera-diagnostic.toml` with `l1-launcher-args.json`, P1-P3 and P6 first). Then run `postrun-gate.py --route l1-camera-diagnostic.toml --run-dir <L1 run>` (writes the receipt `--require-l1` reads later), do the §5b measurements into `admission.json`, and only then run V1 with `postrun-gate.py --route task7s2-v1-readonly-camera.toml --run-dir <V1 run> --require-l1 <L1 run>` (§4e) to decide acceptance on A1-A6.
- `/ce-work` for the new build that includes kp.camera and a fresh harness snapshot. Then re-run `python3 -I -S -B validate.py` against that snapshot.
