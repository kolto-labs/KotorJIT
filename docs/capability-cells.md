# Capability cells

Evidence cutoff: 2026-09-27, afternoon (the host-only refresh is in "Host evidence added 2026-09-27" below). Everything here comes from receipts, reviews and source that already existed. Writing this file started no game, Wine, Gamescope, Xwayland or FFmpeg process, and it ran no test suites.

The directive is that capability cells for Wayland, X11, GNOME, KDE, macOS, Windows and ChromeOS stay honest and each have their own evidence. K1 and K2 support on Windows GOG and native macOS comes through binary identity, signatures and per-build profiles. The Unity game engine plays no part in it. Browser/WASM is lower priority, and it must run from the player's own installed game files.

A cell is one game and build, on one host, for one capability. Each cell holds exactly one of five statuses:

| Status | Meaning |
|---|---|
| `live-accepted` | A real run of this exact build on this host passed the capability's gate. The cell cites the run and the `kphasor.dll` SHA-256 from that run, or says the receipt does not record it. |
| `host-test-only` | Only synthetic or host tests cover it. The cell names the test. |
| `static/metadata-only` | Only parsing, profiles or identity checks specific to this build or platform exist. |
| `not attempted` | No run and no test for this cell. |
| `known-failing` | A real run or a recorded refusal shows the capability does not work here. The cell cites the evidence. |

## Rules applied to every cell

1. Host tests, nominal frame rates and source presence never raise a cell to `live-accepted`.
2. A test that proves a backend refuses a host is not evidence for the capability. The Mac-unsupported test, the `windows-k1` refusal and the Crostini refusal all leave their cells `not attempted`.
3. `static/metadata-only` needs static work specific to that platform or build. The Mach-O parser runs against the private Mac images qualify. Native Windows has no Windows-specific static work: its PE tables are the same ones the Wine runs use, so native Windows cells are `not attempted`.
4. A host desktop is credited only when the run receipt records it. Only run `20260927-102706-0523fa70` records it, as KDE on Wayland. All other Gamescope runs removed host display authority and record no desktop, so they count under "host desktop not recorded". They are not credited to KDE, even though they probably ran on the same workstation.
5. Wine is not native Windows. Xwayland under Gamescope on a Wayland host is not native Wayland support. The game still takes X11 input and presents to an X11 window.
6. Several harness modules and tests cited below are uncommitted files in this worktree, not commits on the branch. These are `display_backends.py`, `gamescope_*.py`, `owned_x11.py`, `physical_console.py`, `src/image/macho.cpp`, `tools/kpharness_gamescope_backend_test.py` and `tools/kpharness_physical_console_test.py`. The docs call the Gamescope backend "checked-in". Here it is called "in-tree" to be exact.

## Capabilities and their gates

| Id | Capability | What `live-accepted` requires |
|---|---|---|
| C1 | Boot and inject | The exact executable hash is identified, the runtime loads, and hooks install in a real process |
| C2 | Console (F12) | The in-game overlay opens with F12, and a typed request completes with the expected result |
| C3 | Lua VM and `kp.*` | Lua runs in the game, and at least one native `kp.*` facility returns a working result (not only a capability refusal) |
| C4 | `nwscript.call` bridge | Engine routines called through `nwscript.call` return correct typed values |
| C5 | Save load | A save or checkpoint loads into gameplay |
| C6 | Gameplay API subsets | Named gameplay predicates pass in the engine. The cell states which subset. |
| C7 | Capture and recording | Follows the current policy in `docs/creative-runner.md`: a full continuous master, measured cadence, no MIT-SHM fallback, a content check, and visual review. A trimmed excerpt that was visually accepted does not meet this gate. |
| C8 | Physical input | OS-level input reaches the owned game window, and the game's own input path counts it |

## Builds

| Build id | Game | Format | Identity (SHA-256 prefix) | Profile state |
|---|---|---|---|---|
| `k1_gog_103` | K1 | PE32 | `9c10e045` | `data/addresses/k1_gog_103.json`, 199 adjudicated bindings |
| `k1_steam_103` | K1 | PE32, SteamStub-encrypted `.text` | See `docs/steam-gog-equivalence.md` | `data/addresses/k1_steam_103.json` |
| `k1_steam_103_unpacked` | K1 | PE32, deciphered Steam image | `2719ed2c` | `data/addresses/k1_steam_103_unpacked.json` |
| `k2_gog_aspyr` | K2 | PE32 | `777bee23` | `data/addresses/k2_gog_aspyr.json` plus the reviewed `client.net_layer` binding |
| `k2_steam_aspyr` | K2 | PE32 | `6a522e71` | `data/addresses/k2_steam_aspyr.json`. The table carries a `.text` digest (`ecf37a15…`) and `expected_bytes` on all 12 required sites; its own caveat note is stale. |
| K2 native Linux (`k2_steam_linux`) | K2 | ELF32 | none on record | `scripts/harness/kpharness/targets.py` declares the `k2-native` target, but this worktree has no address table for it |
| K1 Mac corpus | K1 | Mach-O32 i386 | `aa628373` | Static only (`/home/brunner56/kp-live-20260922/mac-image-baseline.json`) |
| K2 Mac corpus | K2 | Mach-O32 i386 | `f14f285b` | Static only (same file) |
| K1/K2 Mac Steam | K1, K2 | `macos64` according to Steam appinfo | not acquired | none. Ledger ruling: the `macos64` metadata does not match the old Mac32 corpus profile. |

## Hosts

- **Linux, Wine, owned Xvfb.** The in-tree `linux-wine-k1` software path, rendered with llvmpipe.
- **Linux, Wine, private Gamescope prototype.** Controller scripts in `/home/brunner56/kp-live-20260922/` that are not in the repo. They use headless Gamescope with nested Xwayland on an AMD Radeon RX 460 (radeonsi) and record no host desktop.
- **KDE Plasma Wayland host.** The in-tree `linux-wine-k1-gamescope` backend, which nests a private Gamescope/Xwayland display. This is the only host whose desktop appears in a receipt.
- **GNOME Wayland, GNOME Xorg, KDE Xorg.** Separate cells, as `docs/user-directive-audit.md` requires.
- **Native Windows, macOS (legacy Intel, modern Intel, Apple Silicon), ChromeOS (Crostini, Borealis), browser/WASM.**

The evidence workstation is Fedora 44 on kernel 7.1.9-200.fc44.x86_64 (from the 102706 receipt).

## Matrix

Keys in square brackets point to the evidence index below the matrix.

### Linux under Wine

| Game / build · host | C1 boot/inject | C2 console F12 | C3 Lua + `kp.*` | C4 bridge | C5 save load | C6 gameplay subsets | C7 capture | C8 physical input |
|---|---|---|---|---|---|---|---|---|
| K1 `k1_gog_103` · owned Xvfb | live-accepted [E1] | not attempted | live-accepted [E2] | live-accepted [E2] | live-accepted [E1] | live-accepted [E2] | not attempted [N1] | host-test-only [T1] |
| K1 `k1_steam_103_unpacked` · owned Xvfb, pre-API-v2 runtime (Sep 9–16) | live-accepted [E3] | not attempted | live-accepted [E3] | live-accepted [E3] | live-accepted [E3] | live-accepted [E3] | not attempted | not attempted |
| K1 `k1_steam_103_unpacked` · owned Xvfb, post-migration runtime (Sep 22) | live-accepted [E7] | not attempted | not attempted [N8] | known-failing [K5] | live-accepted [E7] | known-failing [K5] | not attempted | not attempted |
| K1 `k1_steam_103` shipped encrypted · Wine without Steam client | known-failing [K1] | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted |
| K1 `k1_steam_103` shipped encrypted · Wine with Steam client | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted |
| K1 `k1_gog_103` · private Gamescope prototype, host desktop not recorded | live-accepted [E4] | live-accepted [E4] | live-accepted [E4] | live-accepted [E4] | live-accepted [E4] | live-accepted [E4] | known-failing [K2] | live-accepted [E4] |
| K2 `k2_gog_aspyr` · private Gamescope prototype, host desktop not recorded | live-accepted [E5] | live-accepted [E5] | not attempted [K3] | live-accepted [E5] | live-accepted [E5] | live-accepted [E5] | not attempted [N2] | live-accepted [E5] |
| K2 `k2_gog_aspyr` · owned Xvfb | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted |
| K2 `k2_steam_aspyr` · any Linux/Wine host | static/metadata-only [S1] | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted |
| K2 native ELF (`k2-native`) · Linux X11, no Wine | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted |

### Linux desktop hosts (the game runs inside nested Gamescope/Xwayland under Wine)

| Game / build · host | C1 boot/inject | C2 console F12 | C3 Lua + `kp.*` | C4 bridge | C5 save load | C6 gameplay subsets | C7 capture | C8 physical input |
|---|---|---|---|---|---|---|---|---|
| K1 `k1_gog_103` · KDE Plasma Wayland | live-accepted [E6] | live-accepted [E6] | live-accepted [E6] | live-accepted [E6] | live-accepted [E6] | live-accepted [E6] | known-failing [K4] | live-accepted [E6] |
| K2 `k2_gog_aspyr` · KDE Plasma Wayland | not attempted [N3] | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted |
| K1 `k1_gog_103` · GNOME Wayland | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted |
| K2 `k2_gog_aspyr` · GNOME Wayland | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted |
| K1 `k1_gog_103` · GNOME Xorg | not attempted [T2] | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted |
| K2 `k2_gog_aspyr` · GNOME Xorg | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted |
| K1 `k1_gog_103` · KDE Xorg | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted |
| K2 `k2_gog_aspyr` · KDE Xorg | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted |

On a KDE or GNOME Wayland host, the native portal path is a separate cell that nothing has tried. That path would use ScreenCast and RemoteDesktop through xdg-desktop-portal, PipeWire and EIS. No row above covers it.

### Native Windows

| Game / build · host | C1 boot/inject | C2 console F12 | C3 Lua + `kp.*` | C4 bridge | C5 save load | C6 gameplay subsets | C7 capture | C8 physical input |
|---|---|---|---|---|---|---|---|---|
| K1 `k1_gog_103` · native Windows | not attempted [N4] | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted |
| K1 `k1_steam_103` · native Windows with Steam | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted |
| K2 `k2_gog_aspyr` · native Windows | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted |
| K2 `k2_steam_aspyr` · native Windows with Steam | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted |

### macOS

| Game / build · host | C1 boot/inject | C2 console F12 | C3 Lua + `kp.*` | C4 bridge | C5 save load | C6 gameplay subsets | C7 capture | C8 physical input |
|---|---|---|---|---|---|---|---|---|
| K1 Mac corpus i386 · Intel macOS 10.14 or earlier | static/metadata-only [S2] | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted |
| K2 Mac corpus i386 · Intel macOS 10.14 or earlier | static/metadata-only [S2] | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted |
| K1 Mac Steam `macos64` · modern Intel macOS | not attempted [N5] | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted |
| K2 Mac Steam `macos64` · modern Intel macOS | not attempted [N5] | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted |
| K1 Mac Steam `macos64` · Apple Silicon (Rosetta) | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted |
| K2 Mac Steam `macos64` · Apple Silicon (Rosetta) | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted |

### ChromeOS

| Game / build · host | C1 boot/inject | C2 console F12 | C3 Lua + `kp.*` | C4 bridge | C5 save load | C6 gameplay subsets | C7 capture | C8 physical input |
|---|---|---|---|---|---|---|---|---|
| K1 `k1_gog_103` · Crostini | not attempted [N6] | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted |
| K2 `k2_gog_aspyr` · Crostini | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted |
| K1 Steam · Borealis | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted |
| K2 Steam · Borealis | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted |

### Browser/WASM (runs from the player's own local install)

| Game / build · host | C1 boot/inject | C2 console F12 | C3 Lua + `kp.*` | C4 bridge | C5 save load | C6 gameplay subsets | C7 capture | C8 physical input |
|---|---|---|---|---|---|---|---|---|
| K1, local install · browser/WASM | not attempted [N7] | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted |
| K2, local install · browser/WASM | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted | not attempted |

## Evidence index

Unless noted, paths are under `/home/brunner56/kp-live-20260922/`.

### Live runs

- **[E1]** `stage-k1/runs/20260922-094527/report.json`. The preflight passed 5/5 steps: `load_save "000001 - AUTOSAVE"`, then module `danm14aa`, then phase `gameplay`, with Bastila valid in the party. The runtime log identifies executable `9c10e045…` with runtime 0.1.0. The receipt does not record the `kphasor.dll` hash.
- **[E2]** `stage-k1/runs/20260922-095936/report.json`. This is the rancor roulette route. It passed 11/11 steps, including "appearance rows changed". It deployed the current-byte `cursed/10_rancor_roulette.lua` (`1bca2de3…`, which uses `kp.registertimer` and `kp.print`). It checks appearance rows through the bridge. Source-before and source-after receipts are equal. The receipt does not record the `kphasor.dll` hash.
- **[E3]** `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/tmp/k1_harness/runs/`, pre-API-v2 era. 63 of 205 route reports pass, all on `k1_steam_103_unpacked`. Examples: `20260916-100912` (rancor roulette, 11/11: `load_checkpoint endar_room3`, gameplay, appearance rows changed) and `recorded-k1_state_drive-20260910-001325`. They predate the API v2 namespace migration (Task 1, committed 20 September); their bridge was `kotor.<Name>`, not `nwscript.call` (`runs/20260916-100912/kotorphasor.log:37`), and `docs/user/api-status.md:3` says older live observations are not a new live test. The receipts do not record the `kphasor.dll` hash. The version string does not tell the eras apart: every run logs `KotorPhasor 0.1.0`.
- **[E7]** `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/tmp/k1_harness/kotorphasor.log` (22 Sep 17:07) and `runs/20260922-160943`. This is the post-migration runtime. The log shows executable `2719ed2c…`, `.text` deciphered and verified, 19 hooks installed, and `nwscript.call` registered for 769 routines. The report shows `load_save '000003 - endar_room3'` reaching `phase=gameplay`, module `END_M01AA`. The receipt does not record the `kphasor.dll` hash.
- **[E4]** `stage-k1/runs/20260927-001952` (the receipt does not record the DLL hash; the installed file is `4e14d0fe…`, the DLL shipped in the combined release, corroborated by `private-gpu-runs/20260927-001824/provenance.json`). It passed 44/44 steps. It loads `000001 - AUTOSAVE`, sends F12 with `xdotool` (`live_example_gpu.py:54`) and physical W movement recorded in `owned-input.jsonl` on window `0xc00004`, runs `kp.model.snapshot/resize/restore`, and makes 7 `nwscript.call` calls including the native string boundary. The renderer is AMD Radeon RX 460 (radeonsi) with direct rendering. More physical-input evidence for the same host: `private-gpu-runs/20260927-014019/supported-result.json` (`kphasor.dll` `fd8e069a…`). There the production `OwnedX11Input` and `PhysicalConsoleDriver` sent F12, text and Enter, DirectInput poll calls (`input_calls`, not keystrokes; `overlay.cpp:100,131`) went up by 30, and request 1 succeeded.
- **[E5]** `private-gpu-runs/20260927-001824` (`kphasor.dll` `4e14d0fe…`). The GOG executable `777bee23…` ran with installed Steam assets and an empty private Override. It loaded one copied cloud save and reached `main_menu=0`. The controller visually checked `k2-world.png` and `k2-gameplay-console.png`. Eight physically typed console commands passed. They include `GetFirstPC`, `GetTag`, `GetPosition`, `GetCurrentHitPoints`, and the party member tag `atton` with length 5 (`k2-console-*.json`). Save and source hashes were unchanged. C6 covers only this read-only query subset. Movement, combat and mutation were not attempted. The earlier startup-only run is `private-gpu-runs/20260926-235959/k2-startup-result.json`: 19 hooks, F12, and `1 + 1` returned `number: 2`, with no save loaded.
- **[E6]** `next-k1-preparations/20260927-task7-scale-102038-74cb804b/runs/20260927-102706-0523fa70` (`kphasor.dll` `fd8e069a…`), with review `task7-k1-scale-run-review.md`. The receipt's `creative-run.json` block `platform.detected` records os linux, session wayland, desktop KDE, and no Crostini. Admission reads "owned Gamescope Xwayland lease". The run passed 23/23 route steps. It starts with `load_save`, then three physical F12 requests with exact runtime, session and request `Succeeded` outcomes. `kp.model` moved scale 1.0 → 0.35 → 2.4 → 1.0 and restored it. The route checks typed bridge getters (`GetFirstPC`, `GetModuleFileName`, `GetArea`, `GetIsInCombat`, `GetLocalNumber`) in `executed-route.toml` lines 30–138, and `SetLocalNumber` restored locals 5 through 9. Source and save preservation passed, and cleanup ran recorder → game_wine → display.

### Known failures

- **[K1]** `docs/steam-gog-equivalence.md`. Without Steam, the shipped Steam executable stops with SteamStub's "Application load error 5:0000065434" before the game gets control. With the Steam client running, nothing has been tried.
- **[K2]** Capture fails the current gate on the private prototype. Each run's `ffmpeg.log` shows the typed `capture_shm_fallback` failure: "Continuing without shared memory" appears in `stage-k1/runs/20260927-001952`, `20260926-234927`, `20260922-124445` and `20260922-130515`. All of them used `x11grab -window_id` through `live_example_gpu.py:203`. No full-master cadence was ever measured on this path. Run `20260922-114443` had no fallback line but also no cadence measurement. Trimmed excerpts were visually accepted and delivered: `media/f12-native-size-swap/review.json` (a 19 s excerpt, with 300 of 300 sampled frames distinct), `media/native-size-swap`, and `media/f12-giant-bow`. Those excerpts do not meet the C7 gate.
- **[K3]** `private-gpu-runs/20260927-001824/k2-console-native.json`. On K2, `kp.model.capabilities()` returned `native unsupported`, `unsupported`, `no verified host binding`. The Lua VM itself works: `1 + 1` gave `number: 2` and `6 * 7` recovered. `kp.model` is the only `kp.*` facility exercised on K2, and it reports unsupported. Nothing else was exercised. This is a correct refusal, not a crash, so the cell is `not attempted`: C3 needs one working `kp.*` call and none other was tried. Rule 2 does not apply: that rule covers host tests refusing a backend at admission, while this is a live refusal inside the running game.
- **[K5]** `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/tmp/k1_harness/runs/20260922-160943`, `-162824` and `-165126` (footlocker blaster routes, post-migration runtime). Save load reached gameplay in all three. Then `160943` failed its first bridge call with `GetFirstPC: live VM context or command slot is unavailable; waiting for a trusted script context`. `162824` failed step 3, "warm the harness Lua VM / command slot", after 188 s with `pc: null`, and `165126` failed with the same `assert_lua` mismatch. No gameplay predicate was reached. The cause is now diagnosed from the host side: commit `5cffd0f` made `vm.wrapper_internal` and `vm.internal_command_implementer` table-driven. The two Steam tables lacked them (196 bindings against GOG's 199), so `layout_resolved` was false and `capture_vm` returned without binding (`runtime.cpp:899`). The RCA is `steam-k1-vm-binding-rca.md`. The table fix is host-tested (`address_table_layout_test`, 8/8 in the fix, 26/26 after the test extension) and independently confirmed (`steam-k1-vm-layout-fix-review.md`, "CONFIRMS"). The cells stay `known-failing`: no live run has used the fixed tables, and the harness still stages the old ones (`57b1368a…` and `541c5c3e…` instead of `c52447bd…` and `5cc67517…`).
- **[K4]** Run `20260927-102706-0523fa70` with review `task7-k1-scale-run-review.md`. The behaviour passed, but presentation and capture failed. The master averaged 54.49 FPS against a nominal 60. FFmpeg reported `drop=1293`. It had 803 intervals over 16.8 ms and a worst gap of 616.7 ms. The log shows the MIT-SHM error followed by "Continuing without shared memory". At 2.4× the player's head was clipped. The automatic representative interval left out the restoration.

### Not attempted, with context

- **[N1]** The Xvfb runs recorded root `x11grab` masters (`stage-k1/runs/20260922-095936/continuous.mp4` among others) with software rendering, and `media/index.json` holds visual excerpts from them. No fallback line appears, but no cadence was measured on any of them. The C7 gate has never been run on Xvfb. The user later rejected some of these clips (rave, low-FPS combat) for their content.
- **[N2]** K2 has screenshots only (`k2-world.png`, `k2-gameplay-console.png`) and no continuous video.
- **[N3]** `display_backends.admit_backend` refuses the Gamescope backend when `target != "k1"` ("Gamescope adapter is Linux K1 only"). The Xvfb backend has the same limit.
- **[N4]** The Windows runtime DLL and Win32/WGL/DirectInput overlay are cross-built with MinGW on Linux, and they only ever ran under Wine. `admit_backend("windows-k1")` is refused in `test_admission_is_separate_from_host_desktop`. The GitHub Actions attempt (run `35491392460`) was an Ubuntu job, rejected for billing before it started. It is not a Windows host attempt. As of 2026-09-27 a Windows installer and a receipt script exist and are host-tested (W0/W1, see [H6]). The receipt script has never run on Windows, and no Windows receipt exists.
- **[N5]** Only Steam appinfo metadata exists (`steam-appinfo.txt`: `oslist windows,macos`, `osextended macos64`). The image has not been acquired or hashed. An x86_64 detour engine and fat Mach-O slice parsing are host-tested (M0/M1, see [H5]), but they ran only on Linux against synthetic input. They say nothing about a Mac host.
- **[N6]** The in-tree Gamescope backend refuses Crostini (`test_admission_is_separate_from_host_desktop`, "Crostini requires a separate live GPU/input/capture admission"). This is a refusal, not capability evidence.
- **[N8]** In the post-migration Steam runs, harness Lua chunks executed. The failing `assert_lua` returned `false` rather than raising an error. No `kp.*` check was reached before the bridge warm-up failed ([K5]). The [K5] cause and its host-only fix do not change this cell, because no `kp.*` call has run on the fixed tables.
- **[N7]** Corpus, CPU/backend and KotOR.js comparator research exists, but no backend has been adopted. Rulings in the progress ledger keep this as low-priority background work. The browser plan (`fanout-browser-wasm-plan.md`) made harness hardening (H0) a gate. H0 is now closed host-only ([H7]), and the plan itself says that work does not close any browser/WASM cell.

### Static and host-test evidence

- **[S1]** `data/addresses/k2_steam_aspyr.json` holds 12 required VM and stack sites, hand-adjudicated against the `gog_aspyr` donor (`data/adjudication/k2_steam_aspyr_vm_bindings.json`). At HEAD the table has the `.text` sha256 `ecf37a15…` and `expected_bytes` on all 12 required sites; the table's caveat note saying they are missing is stale. No live install has been tried.
- **[S2]** `src/image/macho.cpp` (uncommitted), `tools/kp_machotest.cpp`, `tools/kp_imagetool_macho_test.py`, and `macho-parser-report.md`, `macho-parser-review.md` and `macho-cli-report.md`. The Mach-O parser passed 1,095 synthetic checks and 4 checks against the two private i386 images, and its independent review passed. `kp_imagetool identify/sections` accept Mach-O. On 2026-09-27 M0 added fat (universal) slice parsing, and `kp_machotest` grew to 27,808 checks. The fat path is synthetic-only because no fat Mac container is on disk ([H5]). This changes nothing for these two i386 cells. Runtime loading is refused: `src/image/parse.cpp` and `load.cpp` recognise only PE32 and ELF32. There is no Darwin loader, ABI, overlay or input support. Modern macOS cannot run i386 binaries.
- **[T1]** `tools/kpharness_physical_console_test.py::test_display_identity_and_key_input_rejections` and `test_non_linux_owned_input_is_explicitly_unsupported` (uncommitted file). `OwnedX11Input` binds to the Xvfb `GameSession`. No physical-input live run has used Xvfb.
- **[T2]** `tools/kpharness_gamescope_backend_test.py::test_admission_is_separate_from_host_desktop` (uncommitted file). It checks admission logic only, with fake host facts; it never loads the runtime, so the GNOME Xorg C1 cell is `not attempted` for (x11, GNOME) and (wayland, KDE). It does not cover GNOME Wayland or KDE Xorg. The (wayland, KDE) case has since been superseded by [E6].

## Host evidence added 2026-09-27

This section records host-only work that landed on 2026-09-27, after the matrix was first written. No game, Wine, Gamescope or FFmpeg capture ran for any item here. Rule 1 still holds: none of it raises a cell to `live-accepted`.

A cell could move from `not attempted` to `host-test-only` only if two things held. A named test passes, and an independent review of that work passes. The work also has to target that cell's build, host and capability. The native Windows and macOS rows stay `not attempted` whatever their host tests show, because no receipt from a real Windows or Mac machine exists.

**Result: no cell changed status.** Totals are still 32 / 1 / 3 / 231 / 5. Some notes and evidence keys changed, as listed after the table.

Review paths are under `/home/brunner56/kp-live-20260922/`. Writer reports are under `.superpowers/sdd/lua-boundary-validation-plan/` in this worktree.

| Key | Work | Named test and result | Independent review | Effect on cells |
|---|---|---|---|---|
| H1 | Camera Stage 1: read-only `kp.camera.snapshot` and `capabilities`, K1 GOG (`camera-stage1-report.md`) | `kp_cameratest`, 1,818 checks, rc 0 after the line-103 fix. That rerun was by the orchestrator. | `camera-stage1-review.md`: **FAIL** at line 153, on `kp_cameratest.cpp:103` only. No independent re-review of the fix is on file. | None. Fails the review condition. The K1 GOG C3 cells are already `live-accepted` on other facilities. |
| H2 | Motion M1: read-only `kp.motion.capabilities` and `capture`, K1 GOG (`motion-m1-report.md`) | `kp_motiontest`, 20/20, 2,926 checks. MinGW compile 4/4. | `motion-m1-review.md`: **FAIL**. No engine-thread guard on the getter, and not wired into the runtime. | None. Fails the review condition. |
| H3 | Lua utilities U1/U2: `kp.vec` and function-valued timers, plus follow-up (`lua-utilities-u1-u2-report.md`) | `kp_vectortest` 15/0 and `kp_supporttest` 49/0 after the follow-up. | `lua-utilities-u1u2-review.md`: **PASS** (line 230). `lua-utilities-followup-review.md`: **PASS**. | None. Both conditions hold, but the tests do not target any build or host. The review also says `kp.vec` cannot yet be reached from the runtime, since nothing outside the tests calls `register_vector`. |
| H4 | Lua lifecycle L1/L2: script load, unload and reload, `kp.scripts.*` (`lua-lifecycle-l1-l2-report.md`) | `kp_lifecycletest` 21/0 and `kp_scriptsapitest` 9/0. | `lua-lifecycle-l1l2-review.md`: **FAIL** (I1 nested dispatch during staging; I2 case-variant duplicate load). | None. Fails the review condition. |
| H5 | Platform M0/M1: fat Mach-O slices and the x86_64 detour engine (`platform-m0m1-report.md`) | `kp_machotest` (27,808 checks), `kp_imagetool_macho_test`, and `kp_hooktool_x64`. After the fix, the self-test passes 654 checks. | `platform-m0m1-review.md`: **FAIL**. `platform-m0m1-rereview.md`: **PASS** (line 150). | None. Native macOS stays `not attempted` with no Mac receipt. The fat path is synthetic-only because no fat Mac container is on disk. The x86_64 engine ran on Linux x86_64 only. Notes [N5] and [S2] were updated. |
| H6 | Platform W0/W1: consistency test, host-identity Wine flag, Windows installer and receipt scripts (`platform-w0-w1-report.md`) | `platform_receipt_test`, 55/55, under pwsh 7.3.12 on Linux. | `platform-w0-w1-review.md`: **FAIL**. `platform-w1-rereview.md`: **PASS** at line 234, on the condition that W1-I1 lands before any W2 receipt counts. The ledger does not clear W1 for W2. | None. Native Windows stays `not attempted` with no Windows receipt. Note [N4] was updated. |
| H7 | H0: harness hardening against malformed or HTTP-shaped first lines (`h0-harness-hardening-report.md`) | `kp_harnesstest`, 140/140, 20 repeat runs. | `h0-harness-hardening-review.md`: **FAIL**. `h0-followup-review.md`: **CONFIRMS**. One item is still open: the real `stream_events` regression is not checked in, because `kp_harnesstest` does not link `commands.cpp`. | None. The browser plan says H0 does not close browser/WASM cells. Note [N7] was updated. |
| H8 | Steam K1 table layout fix (`steam-k1-vm-layout-fix-report.md`, RCA `steam-k1-vm-binding-rca.md`) | `address_table_layout_test`, 8/8 in the fix and 26/26 after the test extension. | `steam-k1-vm-layout-fix-review.md`: **CONFIRMS**. | None. The Steam K1 bridge cells stay `known-failing` until a live rerun uses the restaged tables. Note [K5] was updated. |
| H9 | Creative packaging P0–P4 (`creative-packaging-p0-p4-report.md`) | 77 packaging tests in the container and on the host. | `creative-packaging-p0-p4-review.md`: **FAIL**. `creative-packaging-rereview.md`: **PASS** (line 389). | None. Packaging is not a capability in this matrix. |
| H10 | Capture cadence rounds 10, 11 and 12: content gate, geometry precondition, and the `capture_diagnostic` driver (reports `task-7-capture-cadence-fix-round-10/11/12-report.md`) | Round 12 writer suites: 266 tests in each environment. | Round 10: correctness and adversarial reviews both **FAIL** (`task7-capture-cadence-fix-review.md:1284` with R10-1 Critical, and `task7-capture-cadence-adversarial-review.md:1143`). Round 11: both **FAIL** (`task7-capture-cadence-fix-review.md:1393` with R11-C1 Critical, and `task7-capture-cadence-adversarial-review.md:1130`). Round 12: reviews dispatched, **no verdict on file**. | None. C7 on Gamescope stays `known-failing` until the diagnostic runs. The diagnostic itself runs no game and would not change a game cell by itself. |

These notes and keys changed. No status changed.

- **K1 `k1_steam_103_unpacked`, post-migration runtime:** C4 and C6 ([K5]) now carry the diagnosed cause and the host-only fix. C3 ([N8]) now says the fix does not reach it.
- **K1 and K2 Mac corpus i386, C1** ([S2]): fat-slice note added.
- **K1 and K2 Mac Steam `macos64`, modern Intel, C1** ([N5]): x86_64 engine note added.
- **K1 `k1_gog_103`, native Windows, C1** ([N4]): installer and receipt-script note added.
- **K1, local install, browser/WASM, C1** ([N7]): H0 note added.
- **K1 `k1_gog_103`, private Gamescope and KDE Plasma Wayland, C7** ([K2], [K4]): the status in "Where capture stands" was updated for rounds 10–12.

The K1 GOG C3 cells rest on the facilities exercised in [E2], [E4] and [E6]: `kp.registertimer`, `kp.print` and `kp.model`. That status does not extend to `kp.camera`, `kp.motion`, `kp.vec` or `kp.scripts`. None of those has run live, and several are not yet wired into the runtime.

## Where capture stands

- **Legacy Xvfb.** Software llvmpipe root capture records continuous masters, and none shows a SHM fallback. No cadence was ever measured, so it makes no frame-rate claim.
- **Private Gamescope prototype.** Child-window `x11grab -window_id` lost MIT-SHM on the first frame in every recent run and fell back to synchronous `xcb_get_image`. Visually accepted excerpts exist. No master passes the current gate.
- **In-tree Gamescope backend, K1 scale run `20260927-102706-0523fa70`.** The behaviour passed. Capture failed on cadence: 54.49 FPS average, 1,293 drops, 803 gaps over 25 ms and a worst gap of 616.7 ms, caused by the same SHM fallback (`task7-capture-cadence-audit.md`). Framing also failed, with the head clipped at 2.4×. The failed media stays quarantined as failure evidence.
- **Root capture on rootless Xwayland is expected to be black.** The research is in `task7-rootless-root-capture-research.md`. Gamescope starts Xwayland `-rootless`. The root then has a 0x0 pixmap and an empty `borderClip`, so root `ShmGetImage` returns zero-filled frames with no error, while the cadence and SHM gates still pass. This comes from reading the source. No empirical root capture on a private display exists. The planned root-capture fallback was therefore dropped.
- **Rounds 10–12 (host-only, not live).** The round-10 brief is `task7-capture-cadence-round-10-brief.md`. It closes the empty-ledger rollback defect R9-1 and refuses root capture on rootless or unknown Xwayland. It goes back to child-window capture, with a geometry precondition checked before FFmpeg starts: realized, at 0,0, inside the screen, and equal to the lease. It adds a mandatory content gate for black or static frames, and a `capture_diagnostic` driver that has not been launched. The relevant tests are `test_root_capture_is_refused_on_rootless_or_unknown_xwayland`, `test_geometry_precondition_refuses_each_shm_condition_before_exec`, `test_content_gate_rejects_black_and_static_before_cadence_can_pass` and `test_execution_gate_requires_exact_window_geometry_and_bound_content`. They are uncommitted. Round 10 failed both independent reviews: under R10-1, a half-duplicate capture scored 99.58% and passed the distinct-frame gate. Round 11 recalibrated the noise floor and failed both reviews again: under R11-C1, the 1.2 floor was invalid for a slower pattern that was fully fresh. Round 12 changed the pattern and recalibrated at 1024x768 (floor 3.9, guard band 1.3 to 11.7). Its writer suites pass 266 tests in each environment, but its reviews have no verdict on file. No C7 cell changes because of any of these rounds ([H10]).
- **Fallback plan.** If child-window SHM still fails once geometry is verified, the next adapter is a separately reviewed PipeWire node reader. Gamescope already publishes a node without `-e` (`display-only-runs/20260927-100845-8cd691c3/gamescope.log`, node 248). Its cadence is unverified.

## Next evidence to collect

Ordered by value to the directive: K1/K2 GOG first, then native Windows and Mac, with browser last.

1. **K1 GOG · KDE Wayland · C7 capture.** After both round-12 reviewers pass, run the bounded `capture_diagnostic` on one owned private Gamescope display. It needs no game, just an animated X client. It must record `xwininfo -id` and `xwininfo -root` at FFmpeg start, show no `capture_shm_fallback`, pass the content gate, and meet the `gamescope-cadence-v1` cadence. Only then run one K1 route with the framing plan (`task7-k1-framing-plan.md`) under the canonical lock. If SHM still fails with geometry verified, stop and review a PipeWire adapter.
2. **K1 GOG · native Windows · C1, C2, C8.** A real Windows 10 1903+ machine, installed through the package. The installer and receipt script exist and are host-tested ([H6]). W1-I1 must land before any W2 receipt counts, because Lua output can forge a native session block. Job Object ownership, HWND binding, and `SendInput` for F12, text and Enter. Exact `kp.console.v1` request correlation and the DirectInput counter. The runtime and overlay are already Win32, so this is the cheapest native host. C7 then needs a Windows Graphics Capture recorder.
3. **K2 GOG · KDE Wayland · C1–C8 through the in-tree backend.** First extend `admit_backend` to K2 under review. Then take the 001824 physical-console route through the in-tree lease and exact-window path, add movement and input restoration, and apply C7 once item 1 passes.
4. **K2 GOG · any host · C3 `kp.*` and C6 mutation.** A reviewed K2 model profile and ABI binding so that `kp.model.capabilities()` reports available. Then a K2 scale-and-restore route, and movement or combat predicates beyond the read-only subset.
5. **K1 GOG · GNOME Wayland, GNOME Xorg and KDE Xorg · C1, C2, C8.** Run the same in-tree backend on real hosts of each kind, each with its own receipt that records the host facts. GNOME results say nothing about KDE, and the reverse holds too.
6. **K1/K2 Mac · C1.** This is gated on work that mostly does not exist yet. The x86_64 detour engine and fat-slice parsing now exist host-only ([H5]); the fat path has only synthetic input. First acquire and hash the Steam `macos64` images, then build the Darwin memory and module backend, live dyld image mapping, a hook ABI per architecture, and a loader and signing model. The legacy i386 rows need an Intel Mac on 10.14 or earlier. That is a separate preservation target and not a shortcut to modern macOS.
7. **K1 `k1_steam_103_unpacked` · post-migration runtime · C4, then C3 and C6.** The cause is found and the table fix is confirmed host-only ([K5], [H8]). Restage the fixed tables in the harness (expect `c52447bd…` and `5cc67517…`), then rerun the footlocker route. Then re-run one E3 route with a recorded DLL hash, so Steam K1 no longer depends on pre-API-v2 evidence.
8. **ChromeOS · C1.** Run a read-only feasibility probe on a named Crostini Chromebook before writing any backend. Borealis stays refused until an allowed deployment path is shown.
9. **Browser/WASM · C1.** Low priority. It needs a playable runtime with read-only local folder access and no retail files in any published output.

## Cell counts

34 rows × 8 capabilities = 272 cells: 32 `live-accepted`, 1 `host-test-only`, 3 `static/metadata-only`, 231 `not attempted`, 5 `known-failing`. Recounted 2026-09-27 after the host-only refresh, with no change. The count reads each table row under `## Matrix` only. It skips header and separator rows and takes the first status token of each of the 8 capability cells. It fails if a row does not have 8 cells or a cell has no status token. A one-line check of the totals, without the row-shape checks: `awk '/^## /{m=($0=="## Matrix")} m&&/^\| K/' docs/capability-cells.md | tr '|' '\n' | grep -oE '^ (live-accepted|host-test-only|static/metadata-only|not attempted|known-failing)' | sort | uniq -c`.
