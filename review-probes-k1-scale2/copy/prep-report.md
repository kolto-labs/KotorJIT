# Task 7 K1 scale, attempt 2: preparation report

Prepared 2026-09-27. This is preparation only. I did not launch Wine, the game, Gamescope or FFmpeg. I did not touch `tmp/harness-locks/live-game.lock` and did not edit the worktree. Every file I wrote is in this directory. The harness was imported read-only with `-I -S -B`. No new `.pyc` appeared under `scripts/harness` (`find … -name '*.pyc' -newer framing-fit.py | wc -l` printed `0`).

Paths:

- DIR = this directory
- WT = `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`
- FAILED = `/home/brunner56/kp-live-20260922/next-k1-preparations/20260927-task7-scale-102038-74cb804b`
- FP = `/home/brunner56/kp-live-20260922/task7-k1-framing-plan.md`
- CP = `/home/brunner56/kp-live-20260922/kp-camera-api-plan.md`

## 0. Blocking prerequisites (before any launch)

1. **The run needs a new build.**
   - The failed run's `kphasor.dll` (`fd8e069a…dfac2`) does not contain the string `kp.camera.capture` (`grep -a -c` printed `0`; `kp.model.capture` printed `1`).
   - The kp.camera sources are untracked in WT (`git status`: `?? src/api/camera_backend.cpp`, `camera_lua.cpp`, `camera_profiles.cpp`).
   - The run needs a new reviewed build that includes kp.camera. Its hash is not known yet.
   - The route fails closed on a wrong build: step 5 raises `kp.camera missing: wrong build` before any F12 (proven in the stub simulation, §6).
2. **kp.camera has never been read in a running game.** See WT/docs/lua-api.md, section "Native camera", and CP §2h.
   - V1 would be its first live read.
   - Whether the one L1 diagnostic from CP §2h runs first is the orchestrator's decision. I recommend it: V1's settle step and every camera gate depend on raw fields whose meaning is unverified.
3. **Take a fresh harness snapshot.** The failed prep's frozen `creative.py` has no `--capture-marker` / `--cadence-*` flags (grep of `FAILED/harness-snapshot/runtime/kpharness/creative.py` found none). The current WT `creative.py` (`0e302254…`) has them (lines 410-413).
   - WT has other active writers right now (new files under `scripts/harness/scenarios/object-blaster`, `src/harness`, `tools`). Snapshot only after those settle, and re-run `validate.py` against the snapshot.
4. **The capture diagnostic must pass first** (FP header; WT/docs/creative-runner.md "Animated-pattern capture diagnostic"). The failed master measured about 54.5 FPS encoded, 109 gaps over 50 ms, and `drop=1293` (review).
5. **Stage the scene script.** Deploy it with a second `--script`, next to the frozen helper. Both are autoloaded as host scripts; both are inert at load (§3).

## 1. Files

| File | SHA-256 | Role |
|---|---|---|
| `task7s2-v1-readonly-camera.toml` | `0fbca9b9…803b49` | **V1** route (runnable candidate). 46 steps; 3 physical F12 submissions; `shot_interval=0`. |
| `task7s2-v2-stage2-PLACEHOLDER.toml` | `421e3eae…b4d1a3` | **V2** placeholder. **Not runnable.** The loader rejects it (§6). |
| `task7s2_scale.lua` | `9fc558d4…0928e4` | Scene script (product layer): `construct`, `arm`, `cleanup`; markers; construct-time camera line; log-only camera watch. |
| `generate-route.py` | `3ae63e04…e2a5df5` | Generator. One `GIANT` constant feeds the typed command, the phase-2 gate and the phase-2 marker. It asserts they agree, and asserts that the Lua tolerances equal the route's. |
| `launcher-args.json` | `59892fb5…0c06` | Proposed marker flags for `kpharness.creative`. |
| `framing-fit.py`, `framing-fit-output.json` | `83907263…b7f`, `b5e79125…8558` | Re-derivation of FP §2b/§2c. Used to choose the giant scale. |
| `validate.py`, `validation-output.txt` | `d17eda61…aa005`, `acb3732c…110e5` | Offline validation and its output. |
| `sim-native-log-tps10.txt`, `sim-native-log-tps60.txt` | `ffd43d73…cb75`, `9ce91a12…1ea1d` | Simulated native logs fed through the WT recorder's marker observer. Host simulation only. |

Full hashes are in `validation-output.txt` (first lines) and in the `sha256sum` output of the final report message.

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
  - The NWScript-name scan checked all 39 chunks, the script and the helper against the 772 K1 routine names. It found no bare routine names (§6).
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
  - If the settled view is still about 272 px measured, 1.9 is marginal: the 16 px-margin maximum at the RUN camera is 1.868-2.089 across fits.
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

## 6. Validation output (offline)

Command: `python3 -I -S -B validate.py`. It exited 0. The output is in `validation-output.txt`; summary:

- **Loader:** WT `Scenario.load` accepts V1: 46 steps, 3 `console_command` steps, target k1, game_speed 1.0. It rejects V2, as quoted in §5.
- **Route policy:** as `FAILED/control.py`. Three physical commands, each with `expect_values=[Boolean true]` and `return_count=1`. The allowed verbs are **widened on purpose** by `screenshot` and `lua` (steps 10, 38 and 45, record only).
- **Launcher flags:** the WT `creative.parser()` plus `marker_configuration` accept the proposed flags. Markers: `calm_end, calm_start, complete, effect_start, giant, normal, restored, tiny`; cadence runs `calm_start..calm_end`.
- **LuaJIT 2.1 (Lua 5.1 syntax)** compiles all 39 chunks. These are the script and every `code=` in V1 and V2, including the three typed commands.
- **NWScript-name scan:** no bare routine names. Routines reached through `nwscript.call` in all code, helper included: ChangeToStandardFaction, CreateObject, DestroyObject, GetArea, GetFacing, GetFirstPC, GetIsDead, GetIsInCombat, GetIsInConversation, GetIsObjectValid, GetLocalNumber, GetModuleFileName, GetPosition, GetStandardFaction, Location, SetCameraMode, SetCommandable, SetLocalNumber. The spawn-only ones are not executed with `spawn=false`.
- **Stub simulation (host only, not live evidence).** LuaJIT ran fake `kp.model`, `kp.camera`, `kp.print`, `kp.registertimer` and `nwscript.call`, with separate harness and console environments and a fake clock. It executed V1's own chunks, the scene script and the frozen helper:
  - **Nominal at 10 and 60 ticks per second:** all 46 steps pass. The WT recorder's `observe()` and `_marker_order_status()` on the simulated log give `ordered` with no duplicates. The marker order is as in §2, and every `await_log` bound holds under the harness regexes. Routines executed: GetArea, GetFacing, GetFirstPC, GetIsDead, GetIsInCombat, GetIsInConversation, GetIsObjectValid, GetLocalNumber, GetModuleFileName, GetPosition, SetCameraMode, SetLocalNumber.
  - **raw_28 moves by 0.01 during giant:** the route fails at step 25 with `camera moved at phase 3 poll: raw_28 moved 0.01`. That is one gate late (§4c).
  - **Build without kp.camera:** the route fails at step 5 with `kp.camera missing: wrong build`, before any F12.
  - **raw_28 drifts 2e-5 per tick until tick 1000:** the anchor resets 7 times, then the route passes. Baseline receipt: `…q=0.0000,0.0000,0.3800,0.9400 … r=7`.
  - **The drift never stops:** the route fails at step 8 (settle).

## 7. Input hashes

| Input | SHA-256 |
|---|---|
| FAILED/physical-native-scale.toml | `2e8e403a4ce0873aeeabd810624955502f65c9acc719737bab9dfdb473ee9e0e` |
| FAILED/generate-route.py | `9d430c2294e25641951f37cd9f6301a6e860607866a156ef34811911b114703a` |
| FAILED/control.py | `eb9ff93be492636e4f23b6122968b9b92868485d4344c2baa58d4993ebe65110` |
| FAILED/launch-once.json | `05dfbaf4be5460cb4c37d37611d82a0f81505ff52b74c9b60bc448e58db9c019` |
| task7-k1-framing-plan.md | `ff6634c4aecbeb3477cd06c31a8e993bcfcdeb2b4fcaf79f5a397342d290b999` |
| task7-scale-framing-fix-brief.md | `5ee37e449c84974796a7838df3a33ef3681ce127cc2e0cd3370e841163802c49` |
| task7-k1-scale-run-review.md | `b9757949e11eef19812ea95ab1d2467b634cdd2516be000bfcc6ab56e51133e9` |
| kp-camera-api-plan.md | `69c2da3d8feee529962e3559c344b949d51cc83ddab8fddc84c80a28977116f1` |
| WT/.superpowers/sdd/lua-boundary-validation-plan/camera-stage1-report.md | `aad97452bcd16c7c7a5f40733f5a0f63b0d4ee57c73ed703a822ac888577cdf9` |
| WT/docs/creative-runner.md | `90cd385a1af61845d8f04738674f8069669e21cc982458e6fa17440940502bfc` |
| WT/docs/lua-api.md | `f2c41e6a4a40d126fadbf7ffcb99c853de389852ca0d8db42ab28e5d37b4f64f` |
| WT/docs/scenario-toml.md | `9a6a9cae0a1e18c072bd727471485fc65e5b7b21e93d3fbc9f5690c0b397cc0b` |
| WT/src/api/camera_lua.cpp (field names) | `772d4e2125c1eff5da8866118e88d007cf36da293bb851523fedc35ede1bd106` |
| WT/scripts/harness/kpharness/scenario.py | `98f1b3678bdd5f363184a621cd5ad8ee12b2f7976c7e1262a8df9931c1bfdf47` |
| WT/scripts/harness/kpharness/creative.py | `0e302254335d0acc3e95be786365a1544642b169377c4a08c67504f373de3ee6` |
| WT/scripts/harness/kpharness/creative_steps.py | `bc1849a0c63a603766d8b63fec33077f893bfcfef256a56a301506763522c89c` |
| WT/data/routines/k1.json | `80b2a9b59096a2edfd4dee6a921f9fd0efc3ce2c142b0215f1a30d146587e957` |
| frozen model_scene.lua (used) | `07c533c28bb588507b473918b90abdb1a440d6099083155e7a86cfff32584a0e` |
| WT model_scene.lua (not used) | `2af947fe2f4384b64b3aa2a7a04d24f5706bce2739cc7f3096c9ba5d459dc287` |
| failed build kphasor.dll (lacks kp.camera) | `fd8e069a1ff5a7b489f32a6492222f396f85e7b74539deb56228395b297dfac2` |
| CAL report.json (stage-k1/runs/20260922-113712) | `40206b20d7898462f3a0d5a244d8092a27c38e9208fae992f0e26ad6a39bf95c` |

## 8. What remains unproven

- **kp.camera live behaviour.** No live read has happened. The mode-2 behaviour may not be `chase`; if it is not, step 8 times out before the marker. The meaning of raw_28/38/50 is unverified. `dolly` may be uninitialised. There is an NaN refusal risk at +0x88/+0x8c (stage-1 M6).
- **The settle hypothesis.** It is not known whether 600 ticks plus a 20 s anchor settle reaches a still view, or whether that view is about 220 px (CAL 0007) or about 272 px (RUN). G1 is judged only offline.
- **Whether the chase camera moves when the model scales.** If it does, the route fails at a phase gate, which is correct but costs the attempt.
- **Quaternion sign flips.** If the engine flips the sign of raw_28 (q and −q are the same rotation), the gate fails falsely. Not observed; unverified.
- **Timer cadence.** Callbacks are timer pumps. The failed run saw about 11 per second, so a 60-callback phase hold lasted about 5-6 s. At 60 per second a hold is about 1 s. I kept `hold_ticks=60` per FP §3c. The lead-in and lead-out have wall-clock floors; the phase holds do not.
- **Capture:** 60 FPS exact-window cadence (prerequisite 4); the new build hash; the fresh harness snapshot.
- **Route-step screenshots under Gamescope have never run.** Only periodic shots are proven (FP §5 claim block). If one fails, step 11 stops the run, before any F12.
- **Harness-state output is not retained beyond about 200 characters per `lua` step.** The full camera fields are in the scene's `camera_construct` and `camera_watch` native-log lines.
- **The typed command length** (about 100 characters) and console typing reliability. F12 #1 is shorter than in the failed run (about 250 characters). Unverified live.
- **The G1-G6 thresholds come from FP.** The 55° FOV behind the tolerance arithmetic is assumed. The baseline receipt logs `base_view_angle` to check it.

## 9. Claim blocks

```
claim: V1 route loads, has exactly three physical F12 submissions, and its Lua compiles.
referent: validation-output.txt lines "V1 Scenario.load: ok, steps=46, physical_console_commands=3…", "LuaJIT compile … ok, chunks=39"
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

## Grill me

1. **(Weakest) Can the in-route camera gate be trusted when the raw fields' meaning is unverified?**
   - Only as a motion detector. It fails closed on any change, and the offline G5 pixel check stays authoritative (§4c).
   - If raw_38 turns out to be a target and not the current position, the gate can miss real motion, and only G5 catches it.
   - If the fields jitter while the view is still, step 8 times out before the marker. That costs the launch but not the F12 sequence.
   - Detection is one gate late at worst; a move that returns within one hold is caught only by the scene-side watch (step 35).
   - Referents: `WT/docs/lua-api.md` kp.camera table ("meaning unverified"); CP §1c. Status: `unverified` live.
2. **Why spend the one attempt on kp.camera's first live read, and not run L1 first?**
   - It is not my call. The route fails early and cheaply on a wrong build or a non-chase behaviour (step 5 / step 8, before F12), but that still consumes a launch.
   - CP §2h L1 would settle `behavior`, `dolly` and raw-field motion correlation without spending an acceptance attempt.
   - Referent: CP §2h, §5. Recommendation: run L1 first.
3. **Why should waiting longer give a farther view at the same spot?**
   - CAL shows 272 px at about 180 ticks after mode 2, then about 220 px from about 380 ticks on, nearly stable through 0009.
   - The failed run waited only 120 ticks while panning.
   - Referents: CAL `report.json` steps 17-28 (ticks 843→1631); FP §2a. That the drift is a settle, not collision or yaw, is `unverified`. If the settled view is 272 px, G1 fails.
4. **Why 1.9 and not the plan's 2.0?**
   - V1 cannot set distance, so the scale must hold across the whole 192-230 px G1 band. 2.0 holds only to 217 px model (FP §2c, reproduced).
   - Referent: `framing-fit-output.json` `max_scale_60px@230` = 1.933 worst fit.
5. **Does `calm_start` really come after the console is closed?**
   - The scene waits at least 180 callbacks and at least 3 s after `arm`. The failed run closed the console 0.23 s after the arm step (FAILED `report.json` step 11).
   - Step 21 (`await_log` min 0, max 0, right after the close) fails the run if the marker came first. `creative_steps.py` returns immediately when the minimum is 0 and the maximum holds (lines 88-93).
   - The "console fully faded" visual state is `unverified`.

**Unsettled question:** is kp.camera's mode-2 behaviour `chase`, with raw_28 still when the view is still? The one check that settles it is CP §2h L1: a single diagnostic launch that takes two snapshots 180 ticks apart, each with a still.

## Your options (Compound Engineering)

- `/ce-code-review` on this directory (route, script, validator) before any freeze. A subagent `prove-the-effort-reviewer` can attack the Grill me answers.
- `/ce-plan` for the CP §2h L1 diagnostic launch (separate authorization).
- `/ce-work` for the new build that includes kp.camera and a fresh harness snapshot. Then re-run `python3 -I -S -B validate.py` against that snapshot.
