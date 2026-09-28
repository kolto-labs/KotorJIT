# capability-cells.md review (opposer pass)

Target: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/docs/capability-cells.md`.
Read-only pass on 2026-09-27. No Wine, game, Gamescope or FFmpeg was started, and the live-game lock was not touched. Paths are under `/home/brunner56/kp-live-20260922/` unless they are absolute.

Tally check. The matrix holds 32 live-accepted, 6 known-failing, 2 host-test-only and 3 static cells. I recounted the rows by hand and got the same numbers. That makes 43 cells reviewed.

The verdict in each block is on the cell's status. Mistakes in the doc's wording that leave the status unchanged are listed separately at the end.

## Live-accepted cells

### K1 k1_gog_103, owned Xvfb (E1, E2)

claim: C1 boot/inject live-accepted [E1]
referent: stage-k1/runs/20260922-094527/report.json has ok=true and 5/5 steps. Its kotorphasor.log line 3 has sha256 9c10e045…, followed by "installed 19 hooks" and "running: build k1_gog_103".
checked: report.json, kotorphasor.log
verdict: holds
confidence: high

claim: C3 Lua + kp.* live-accepted [E2]
referent: stage-k1/runs/20260922-095936. deployed-scripts.json has 10_rancor_roulette.lua at 1bca2de3…, and the worktree file hashes to the same value. The script calls kp.print (line 95) and kp.registertimer (line 141). The log's final session, which starts at line 321, prints "[10_rancor_roulette] [cursed] armed" and 8 roulette lines. That shows kp.print working and the timer firing. The log is appended, and its earlier sessions ran 00_probe and 50_chaos_roulette. That does not affect this cell.
checked: deployed-scripts.json, sha256sum of the worktree script, kotorphasor.log lines 321-395
verdict: holds
confidence: high

claim: C4 bridge live-accepted [E2]
referent: The executed-route.toml assert_lua steps round-trip nwscript.call through GetFirstPC, Set/GetLocalNumber, CreateObject, GetAppearanceType and others. All 11 steps pass. source-before.json and source-after.json are byte-identical.
checked: executed-route.toml lines 30-83, report.json, cmp
verdict: holds
confidence: high

claim: C5 save load live-accepted [E1]
referent: The 094527 steps are load_save "000001 - AUTOSAVE", then module danm14aa, then phase gameplay. All are ok.
checked: report.json
verdict: holds
confidence: high

claim: C6 gameplay subsets live-accepted [E2]
referent: The 095936 route passes "at least three enemies were redrawn as monsters" and "appearance rows changed". Both are assert_lua checks through GetAppearanceType.
checked: report.json, executed-route.toml line 83
verdict: holds
confidence: high

### K1 k1_steam_103_unpacked, owned Xvfb, pre-API-v2 (E3). Covers C1, C3, C4, C5 and C6.

claim: 63 of 205 route reports pass, all on k1_steam_103_unpacked. Example 20260916-100912 is rancor at 11/11. Example recorded-k1_state_drive-20260910-001325 passes.
referent: A Python pass over /run/media/brunner56/MyBook/Workspaces/KotorPhasor/tmp/k1_harness/runs/*/report.json found 205 reports and 63 with ok=true. Every report is k1_steam_103_unpacked. All 63 passing runs are dated 2026-09-10 to 2026-09-16. In 100912, load_checkpoint endar_room3 leads to gameplay at END_M01AA. The "curse is armed" step passes, the log has "[10_rancor_roulette] [cursed] armed" at line 68, and "appearance rows changed" passes. The git commit "Integrate API v2" is dated 2026-09-20 (47df55a), so these runs are pre-v2.
checked: the report scan, runs/20260916-100912/report.json and kotorphasor.log, git log
verdict: holds for all five cells
confidence: high for C1, C5 and C6, and medium for C3 and C4. The 100912 log has sha256 2719ed2c… and 19 hooks. Its bridge is "registered 769 engine routines as kotor.<Name>" (log lines 37 and 58), not `nwscript.call`. The C4 gate text names `nwscript.call`, so the substance holds but the wording does not match (see text correction T-g).

### K1 k1_steam_103_unpacked, post-migration (E7)

claim: C1 live-accepted [E7]
referent: tmp/k1_harness/kotorphasor.log (17:07) has sha256 2719ed2c…, "code section verified", 19 hooks and 769 routines. runs/20260922-160943/kotorphasor.log has the same identity.
checked: both logs
verdict: holds
confidence: high

claim: C5 live-accepted [E7]
referent: runs/20260922-160943 steps 1-2 run load_save '000003 - endar_room3' and reach phase=gameplay at END_M01AA.
checked: report.json
verdict: holds
confidence: high

### K1 k1_gog_103, private Gamescope prototype (E4). Covers C1, C2, C3, C4, C5, C6 and C8.

claim: 001952 passed 44/44 steps with physical F12. It ran kp.model snapshot/resize/restore and 7 nwscript.call calls, rendered on the RX 460.
referent: stage-k1/runs/20260927-001952/report.json has 44 steps, all "ok". Among them:
- load_save 000001 AUTOSAVE reaches gameplay at danm14aa.
- console_open reports "F12 overlay open=True".
- console_command results pass, for example 1+1 gives number: 2.
- kp.model.resize 0.35 passes, followed by restore and the check snapshot.base==1.
- executed-route.toml has 7 lines with nwscript.call.

renderer.txt shows AMD with direct rendering. The owned W keydown moved the PC ("game movement input works before opening overlay"). 014019/supported-result.json has ok=true, kphasor.dll fd8e069a…, input_calls_delta 30 and request 1 Succeeded.
checked: report.json, executed-route.toml, renderer.txt, owned-input.jsonl, live_example_gpu.py:50-60, supported-result.json
verdict: holds for all seven cells
confidence: high on status. The citation is inexact (see text corrections T-a and T-b).

### K2 k2_gog_aspyr, private Gamescope prototype (E5). Covers C1, C2, C4, C5, C6 and C8.

claim: C1. GOG executable 777bee23… with 19 hooks.
referent: k2-stage/runs/*/kotorphasor.log line 3 has sha256 777bee23…, followed by "installed 19 hooks" and "running: build k2_gog_aspyr".
checked: that log
verdict: holds
confidence: high

claim: C2. F12 and eight physically typed console commands passed.
referent: k2_save_gpu.py:129-180 sends F12 and types each command with xdotool. There are 8 k2-console-*.json files for request ids 1-8, and every one has a result line.
checked: the files, k2_save_gpu.py
verdict: holds
confidence: high

claim: C4. GetFirstPC, GetTag, GetPosition and GetCurrentHitPoints return typed values, and the party tag is atton with length 5.
referent: The console results were:
- pc: number 2147483646
- tag: "" with length 0 and no embedded NUL
- position: three numbers
- hp: 241
- npc_tag: "atton" and 5
checked: k2-console-*.json
verdict: holds
confidence: high

claim: C5. One copied cloud save loaded, and main_menu=0.
referent: k2-save-result.json has save_loaded=true. Its last_state and final_world_state both have phase gameplay with main_menu 0 and server_mode 2. visual-review.json has accepted_gameplay_view=true.
checked: both files
verdict: holds
confidence: high

claim: C6 covers only the read-only query subset.
referent: As for C4, the query results pass. The visual-review scope says "no movement/combat/fullAPI acceptance".
checked: visual-review.json
verdict: holds, because the cell states its subset
confidence: medium. These are engine reads rather than "gameplay predicates" in the E2 sense.

claim: C8. Physical input reaches the game.
referent: xdotool F12 toggled the overlay, which runs through the hooked DirectInput device (overlay.cpp:91-135). Typed text completed requests 1-8 in order. No W-movement or counter-delta check was run on K2.
checked: k2_save_gpu.py, the console JSONs, src/devtools/overlay.cpp
verdict: holds
confidence: medium. This is weaker than E4, which has the movement assert.

### K1 k1_gog_103, KDE Plasma Wayland (E6). Covers C1, C2, C3, C4, C5, C6 and C8.

claim: The platform.detected block in run 20260927-102706-0523fa70 records linux, wayland and KDE. The run passed 23/23 with kphasor.dll fd8e069a….
referent: creative-run.json .platform.detected has os linux, session wayland, desktop KDE and crostini false. Admission says "owned Gamescope Xwayland lease". .runtime.kphasor.dll sha256 is fd8e069a…. report.json has 23/23 "ok". The log shows exe 9c10e045…, 19 hooks and 769 routines.

The route covers the following:
- load_save leads to gameplay at danm14aa.
- There are three console_open F12 requests. Each console-command JSON has request 1/2/3 "Succeeded", and submitted counts 0, 1 and 2.
- kp.model moves through 1 → 0.35 → 2.4 → 1, driven by kp.registertimer.
- executed-route.toml lines 30-138 contain GetFirstPC ×7, GetModuleFileName ×6, GetArea ×5, GetIsInCombat ×5, GetLocalNumber ×12 and SetLocalNumber ×2.
checked: creative-run.json, report.json, the console-command JSONs, executed-route.toml, kotorphasor.log, gamescope-lease.json, scripts/harness/kpharness/display_backends.py:410-421, and a live check of `ps` and /run/user/1000
verdict: holds for all seven cells under the doc's Rule 4
confidence: medium. The KDE credit rests on two environment strings and on nothing the run exercised:
- `detect_host` sets session and desktop only from `XDG_SESSION_TYPE` and `XDG_CURRENT_DESKTOP`.
- The lease command is `gamescope --backend headless` on nested rootless Xwayland :1.
- No receipt records a host WAYLAND_DISPLAY or socket. Every "wayland" hit in the prep and run files is Xwayland.
- The task7 review never mentions KDE.
- KWin was never in the display, input or capture path.

The strings are not stale: `kwin_wayland` has been running since Sun Sep 20 07:06:45, and /run/user/1000/wayland-0 has existed since the same time. That span covers this run. It also covers E4 (001952) and E5 (001824). So the "host desktop not recorded" rows almost certainly ran on this same KDE session. The difference between the KDE row and the E4 row is bookkeeping, not evidence.

This would change if the doc adopted a rule that host credit needs the host compositor in the path. Then all seven cells would drop to "not attempted", and E6 would fold into the prototype row.

## Known-failing cells

claim: K1 k1_steam_103 encrypted, Wine without Steam, C1 known-failing [K1]
referent: docs/steam-gog-equivalence.md:24 has "Application load error 5:0000065434".
checked: grep
verdict: holds
confidence: high

claim: K1 steam unpacked post-migration, C4 known-failing [K5]
referent: In 160943 step 5, GetFirstPC fails with "live VM context or command slot is unavailable; waiting for a trusted script context". 162824 and 165126 both fail step 3 with "assert_lua mismatch: expected true, got false", after 188 s and 221 s. Every run reached gameplay first.
checked: all three report.json files
verdict: holds
confidence: medium. The cause is undiagnosed. A timing fix could flip it, which the doc already says.

claim: K1 steam unpacked post-migration, C6 known-failing [K5]
referent: Same as above. No gameplay predicate was reached in any of the three runs.
checked: same
verdict: holds
confidence: medium

claim: K1 GOG prototype, C7 known-failing [K2]
referent: "Continuing without shared memory" appears once each in the ffmpeg.log of 001952, 234927, 124445 and 130515. 114443 has 0 and no cadence. live_example_gpu.py:203 uses `x11grab … -window_id`. media/f12-native-size-swap/review.json is an excerpt from 124445.
checked: grep -c on each ffmpeg.log, the script line, review.json
verdict: holds
confidence: high

claim: K2 GOG prototype, C3 known-failing [K3]
referent: k2-console-native.json, request 7, gives "string: native unsupported". It is the only kp.* call made on K2, and 0 scripts were loaded (k2-save-result.json scripts=0).
checked: both files, the gate wording at doc line 32, the known-failing definition at line 15, and N8 at line 163
verdict: does not hold
confidence: medium. The C3 gate is an existence claim: "at least one native kp.* facility returns a working result". A single facility that refuses by design cannot disprove it, and it does not show "the capability does not work". The doc rates the same pattern `not attempted` for the Steam post-migration C3 cell (N8), where Lua ran and no working kp.* result was reached. The correct status is `not attempted`, with K3 kept as context. One K2 console line such as `kp.print('x')` or `kp.registertimer` decides it.

claim: K1 GOG KDE Wayland, C7 known-failing [K4]
referent: ffmpeg.log shows drop=1293 and one "Continuing without shared memory". The review gives an average of 19179/352 ≈ 54.49, 803 intervals over 16.8 ms and a worst gap of 616.666 ms. The cadence audit gives 803 over 25 ms. Timestamps are quantized to 16.667 ms, so those two counts select the same set. The review also records the head clipped at 2.40× and a representative clip [206.1, 216.1] that misses the restoration at about 218 s. creative-run.json has acceptance_ready=false.
checked: ffmpeg.log, task7-k1-scale-run-review.md lines 13-41, task7-capture-cadence-audit.md lines 41-61, creative-run.json
verdict: holds
confidence: high

## Host-test-only cells

The criterion for this status: the test must run code on the capability's own path. A pre-launch admission decision does not count.

claim: K1 GOG Xvfb, C8 host-test-only [T1]
referent: tools/kpharness_physical_console_test.py:389 `test_display_identity_and_key_input_rejections` binds `OwnedX11Input.from_session` to an Xvfb-shaped session and gets target window 0x10. Line 382 is a darwin refusal and adds nothing. The file is untracked (`??`).
checked: the test source and git status
verdict: holds
confidence: medium. The test covers the C8 input binding path with a fake session.

claim: K1 GOG GNOME Xorg, C1 host-test-only [T2]
referent: tools/kpharness_gamescope_backend_test.py around line 584, in `test_admission_is_separate_from_host_desktop`, admits the Gamescope backend with fake facts for (x11, GNOME).
checked: the test source
verdict: does not hold
confidence: medium. `admit_backend` is a gate decision made before launch. It never identifies a hash, loads the runtime or installs a hook, and those are the whole C1 gate. The doc's Rule 2 already says admission tests are not capability evidence when they refuse, and the same applies when they admit. The correct status is `not attempted`, with T2 kept as context.

## Static/metadata-only cells

claim: K2 k2_steam_aspyr on any Linux/Wine host, C1 static/metadata-only [S1]
referent: data/addresses/k2_steam_aspyr.json. Its note says all 12 required VM/stack sites were hand-adjudicated against gog_aspyr. data/adjudication/k2_steam_aspyr_vm_bindings.json exists.
checked: JSON parse of the table at HEAD and in the worktree
verdict: holds on status. The cell's text is wrong (see text correction T-c).
confidence: high

claim: K1 Mac corpus i386, C1 static/metadata-only [S2]
referent: macho-parser-report.md:9 reports 1095 synthetic checks and 1099 including the private K1/K2 images (1095 + 4). macho-parser-review.md:3 says PASS. macho-cli-report.md shows a CTest pass. mac-image-baseline.json has K1 aa628373… and cpu 7. tools/kp_machotest.cpp and tools/kp_imagetool_macho_test.py exist. src/image/macho.cpp is untracked. load.cpp handles only ELF and PE.
checked: the listed files, grep, git status
verdict: holds
confidence: high

claim: K2 Mac corpus i386, C1 static/metadata-only [S2]
referent: Same as above, with K2 f14f285b in mac-image-baseline.json.
checked: same
verdict: holds
confidence: high

## Upgrades from host tests, nominal rates, source presence or Wine to a native claim

None found:
- No live-accepted cell rests on a host test, a nominal FPS figure or source presence.
- Every native Windows and native macOS cell is `not attempted` or static.
- The KDE row is explicitly scoped to nested Gamescope/Xwayland under Wine (Rule 5 and the section header). Its only weak point is the KDE attribution itself, covered in the E6 block above.
- No capture cell is live-accepted anywhere.

## Text corrections (status unchanged)

- T-a. E4 says `kphasor.dll 4e14d0fe…`, but the 001952 receipt does not record that hash. It was inferred from the current hash of /home/brunner56/kp-release-20260927/build/kphasor.dll, which session.log line 5 names as the install source. It is corroborated by private-gpu-runs/20260927-001824/k2-stage/runs/20260927-001829/provenance.json one minute earlier. The doc's own live-accepted definition requires it to say "the receipt does not record it (inferred from …)".
- T-b. E4 says "physical F12 with owned-input.jsonl on window 0xc00004", but owned-input.jsonl holds only 4 `w` key events. F12 went through `xdotool windowfocus … key F12` (live_example_gpu.py:54) and is not in that file.
- T-c. The S1 cell and the Builds table (line 47) say `expected_bytes` and the known-text digest are missing. At HEAD and in the worktree, data/addresses/k2_steam_aspyr.json has known_text .text sha256 ecf37a15…. All 12 required sites and 33 sites in total carry expected_bytes. The CAVEAT in the table's own note is stale, and the doc copied it.
- T-d. E4 says input calls went up by 30. `input_calls` counts DirectInput GetDeviceState and GetDeviceData polls (overlay.cpp:100 and 131), not keystrokes, so the delta shows polling rather than delivery. E4 C8 still stands on the W-movement assert, and E6 C8 on the submitted counter going 0 → 1 → 2.
- T-e. E3 dates the API v2 migration as "Task 1, 22 September". The git commit 47df55a "Integrate API v2…" is dated 2026-09-20. This does not change the pre/post split, because the E3 runs end on Sep 16 and E7 falls on Sep 22.
- T-g. E3 C4 is credited against the `nwscript.call` gate, but the pre-v2 runtime exposed the bridge as `kotor.<Name>`. runs/20260916-100912/kotorphasor.log lines 37 and 58 read "registered 769 engine routines as kotor.<Name>", and nwscript.call does not appear. The E3 entry should say which bridge name it used.
- T-f. Rule 4 says the other Gamescope runs "probably ran on the same workstation". `kwin_wayland` has been up since Sep 20 07:06, which covers E4 and E5, so they ran inside the same KDE session. The doc should say so, even if it keeps them uncredited.

## Cells whose status must change

| Cell | Current | Correct | Referent |
|---|---|---|---|
| K1 `k1_gog_103` · GNOME Xorg · C1 | host-test-only [T2] | not attempted (keep T2 as context) | tools/kpharness_gamescope_backend_test.py `test_admission_is_separate_from_host_desktop`: admission with fake facts only, no hash, load or hook |
| K2 `k2_gog_aspyr` · private Gamescope prototype · C3 | known-failing [K3] | not attempted (keep K3 as context: kp.model refuses by design and no other kp.* was exercised) | private-gpu-runs/20260927-001824/k2-console-native.json request 7; gate wording at doc line 32; N8 precedent at doc line 163 |

Watch item, not a change yet:
- The KDE row E6 is medium. It changes only if the doc requires the host compositor to be in the path.

Counts: 41 holds, 2 do not hold, 0 unresolved.

stop: referents arrived for all 43 cells. Two fail on mechanism: T2's admission test never reaches the C1 gate, and K3's single by-design refusal cannot disprove an existence gate.
