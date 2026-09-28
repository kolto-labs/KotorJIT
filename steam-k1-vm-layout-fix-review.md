# Steam K1 VM layout fix: review

Reviewer: an opposer that did not write the fix. Read-only on the repo. No Wine, no game, and the live-game lock was not touched.
Worktree: `.worktrees/lua-boundary-validation`, HEAD `ca329e52dd27d1a3f5a56748d93c8ab0fd7f24f2`.
Report under review: `.superpowers/sdd/lua-boundary-validation-plan/steam-k1-vm-layout-fix-report.md`.
My scratch dirs: `/tmp/kp-review-red.Ek8Q` (HEAD tables plus the new test) and `/tmp/kp-review-regen.l75y` (fresh regen).

---

claim: "Test: red, then green" (8 tests; red fails the 2 Steam tables with "vm.wrapper_internal: absent; vm.internal_command_implementer: absent")
referent: test output, both runs
checked: green: `python3 tools/address_table_layout_test.py` in the worktree gave `Ran 8 tests ... OK`, exit 0. Red: copied the test next to `git show HEAD:data/addresses/*.json` in /tmp/kp-review-red.Ek8Q. That gave `FAILED (failures=2)`, and the two failing subtests were `k1_steam_103.json` and `k1_steam_103_unpacked.json`, with the exact messages above. The GOG and K2 tables passed in both runs.
verdict: holds
confidence: high

claim: before and after sha256 for the 3 changed files, plus the new test sha
referent: sha table in the report
checked: `sha256sum` on the worktree files gave after = a72655f2… / 5cc67517… / c52447bd…, and the test = 312cacf0…. `git show HEAD:<f> | sha256sum` gave before = f5bb54d1… / 541c5c3e… / 57b1368a…. All seven match.
verdict: holds
confidence: high

claim: "Unchanged, checked by sha256 before and after: k1_gog_103.json 65e7c2dd…, k2_gog_aspyr.json 4e21a72a…, k2_steam_aspyr.json 14eb04aa…"
referent: sha list
checked: the current worktree shas match. Note that `k1_gog_103.json` and `k2_gog_aspyr.json` are modified against HEAD (+321/-18 lines per `git diff --stat`). That is another writer's work (camera sites) and was already there before this fix. So the claim means "this fix did not change them", not "they equal HEAD". The fix's parity proof correctly uses `git show HEAD:` GOG, not the worktree GOG.
verdict: holds (as scoped)
confidence: medium. The pre-fix worktree shas cannot be re-observed. What would change it: a writer log showing these files at other shas before 11:55.

claim: "no other generated output changed" / "src/generated/builds.inc was not written"
referent: diff -rq temp vs worktree; generator write site
checked: `git diff HEAD --stat -- src/generated/` is empty. `diff -rq /tmp/kp-steamfix-gen/repo/data data` shows only (a) the swapped `hooksites.toml` and (b) `data/adjudication/k1_gog_103_motion_bindings.json`, which exists only in the worktree. That file is untracked, has mtime 12:15:05 (after the temp copy), and is not generator output, because the generator writes only `data/addresses/`. The temp `hooksites.toml` equals `git show HEAD:data/hooksites.toml`.
verdict: holds
confidence: high

claim: generator output is reproducible (the basis for keeping the full output)
referent: independent regen
checked: I built a fresh copy (`/tmp/kp-review-regen.l75y`: worktree tools/ and data/, with hooksites.toml = HEAD) and ran `KP_K1_UNPACKED=<main>/tmp/k1_harness/swkotor.exe python3 tools/gen_address_tables.py --build k1_steam_103_unpacked --build k1_steam_103`. It printed `255/256 resolved ... ok` for both. The output shas are c52447bd… and 5cc67517…, byte-identical to the shipped tables.
verdict: holds
confidence: high

claim: "every site in the new Steam table has the same addr, kind, expected_bytes, offset and size as git show HEAD:data/addresses/k1_gog_103.json. The one exception is net.destination_net_layer. GOG has no site that Steam lacks."
referent: python dict comparison
checked: for both Steam tables, the 5-field mismatch list is `['net.destination_net_layer']` and GOG-not-in-Steam is `[]`. Stronger: comparing the full site dict (every key) against HEAD GOG differs only on `net.destination_net_layer`. Against HEAD Steam: 15 sites added (the 2 VM layout rows plus the 13 listed), 0 removed, and 1 changed (`net.start_connect_to_session` kind call→detour; addr unchanged). The summary went from 241/241 to 256/255. `installable` is true and `missing_required` is []. The two Steam tables' `sites` dicts are identical.
verdict: holds
confidence: high

claim: the new rows are vm.wrapper_internal offset 0 size 4 and vm.internal_command_implementer offset 0x3d4 size 4, adjudicated; adjudication counts 127/196 → 129/198
referent: table rows and adjudication diff
checked: the table rows read `kind field, offset 0, size 4, source adjudicated` and `offset 980 (0x3D4), size 4`. `git diff HEAD --` on the adjudication file shows two rows inserted at index 0/1 and the counts changed as stated. Evidence text cites the Steam image sha and `restated_from`.
verdict: holds
confidence: high

claim: Steam image bytes at 0x5d1000 / 0x5d45d0..0x5d45dc / 0x5d4650 / 0x5d466a / 0x5d4676, and .textU byte-identical to GOG .text
referent: PE-parsed reads of both images
checked: I parsed the PE section tables myself. Steam `<main>/tmp/k1_harness/swkotor.exe` has sha 2719ed2c…3a05, and the GOG raw has sha 9c10e045…1435. `.textU` VA 0x401000 vsize 3,387,856 compares to GOG `.text` at 0 differing bytes; both sha256 39bcd9f2…4135. Byte reads (Steam = GOG):
  - 0x5d1000 `8b 09 e9 b9 14 00 00`
  - 0x5d45d0 `53 55 56 57 8b 7c 24 14 33 ed 3b fd 8b f1`
  - 0x5d4650 / 0x5d466a / 0x5d4676 each `8b 8e d4 03 00 00`
  The table agrees on the names: `vm.stack_pop_integer`=0x5d1000 and `vm.run_script`=0x5d45d0.
verdict: holds
confidence: high

claim: GOG destination_net_layer receipt cites wrong addresses (0x5d4c10 not Initialize; 0x5d4cba inside SEH prologue); the real stores are at 0x5d5567 / 0x5d5572 / 0x5d4ccb
referent: byte reads
checked: 0x5d4c10 = `56 8b f1 e8 98 fd ff ff`, while the table has `net.initialize`=0x5d5550. 0x5d4cba = `00 00 00 50 64 89`. 0x5d5567 = `89 86 0c 00 02 00`, 0x5d5572 = `89 b0 0c 00 02 00`, 0x5d4ccb = `8b 85 0c 00 02 00`. Leaving the row unresolved is the conservative call.
verdict: holds
confidence: high on the bytes; medium on "destructor-shaped" (I did not disassemble past 8 bytes)

claim: "with multiplayer off, the footlocker rerun changes only the VM layout" (the ~15 catch-up rows are inert)
referent: every reader of the 14 catch-up names at the current tree (runtime.cpp carries other writers' edits)
checked: `grep -rnE` over src/, kpharness/ and tools/*.py.
  - runtime.cpp:562-598: the 6 detours, the destination field and the support sites are all inside `if (multiplayer_enabled)`.
  - hook_bodies.cpp:259-262 / 324-327: `replay_*` return false unless the frame kind/sender match and the role is Server/Client.
  - hook_bodies.cpp:575-585: runs inside the client_area detour, which is installed only by the multiplayer block.
  - hook_bodies.cpp:1399-1408: `set.original(...)` for sites that were never added.
  - runtime.cpp:465: `start_multiplayer` only accepts a K1 receipt for `build_ == "k1_gog_103"`, so Steam K1 multiplayer is refused regardless.
  The report missed one reader: `engine_k1.cpp:156/686/816`. The harness adapter requires and calls `net.start_connect_to_session` in `load_save`, which is the route that loads a save, and this site's kind changed call→detour. It is still inert. The adapter binds non-field sites on `resolved && addr != 0` with no kind check (`engine_k1.cpp:233-241`), the addr is unchanged, and with multiplayer off nothing is installed at that address, so the call reaches the original function exactly as before. GOG has had detour at that addr all along.
verdict: holds (the report's reader list is incomplete, but the conclusion survives)
confidence: high for the code paths; the live rerun is the final referent

claim (task): would the new test catch a future table missing ANY layout field the runtime requires?
referent: runtime.cpp:631-637 `layout_resolved`, registry.cpp:312-320 `parse_field_extent`, runtime.cpp:905-908 capture_vm
checked: the runtime's required set is exactly {vm.wrapper_internal, vm.internal_command_implementer}. Each must be non-null, `resolved`, kind Field, and size == sizeof(void*). For a field, `resolved` is true iff kind Field and size is a nonzero number. The test demands presence, kind "field", a numeric nonzero size equal to pointer width (format "pe" → 4, and all 5 tables are "pe"), and a numeric offset. That is stricter than the runtime, which treats a missing offset as 0. The 6 predicate unit tests pin absent, unresolved, wrong kind, wrong size and missing offset.
verdict: holds for the layout fields
gaps (not "missing layout field", but live-bind failures the test will not catch):
  1. It does not check offset *values*. A K1 table carrying the K2 `wrapper_internal` offset 0x1c passes, and so does the runtime (`layout_resolved` has no value check; only `start_multiplayer` does).
  2. `api::bind_sites` (enginestruct.cpp:154-162) also needs 9 VM stack sites. A table missing `vm.stack_pop_object` passes this test and still never binds.
  3. It scans only `data/addresses/*.json`. A staged `hookpack.json` wins over the address JSON (runtime.cpp:390-408) and is not covered. None is staged in `<main>/tmp/k1_harness/kotorphasor/` today.
confidence: high

ruling to evaluate: keep full generator output rather than splice
criterion: reproducibility (next regen must not undo or re-change the table) plus blast radius on the multiplayer-off rerun
referent: the regen above is byte-identical; the full-dict parity with HEAD GOG has 1 difference; the reader audit is above
checked: a splice would pass the layout test, but it is a table the generator cannot produce, so the next `gen_address_tables.py` run would add the same 13 rows anyway. The full output is reproducible and adds only multiplayer-gated or kind-agnostic rows, identical to HEAD GOG.
verdict: holds. Keep the full output.
confidence: high. What would change it: the live rerun showing a hook-install or load_save difference versus the last Steam run.

---

Residual before the live rerun (already in the report; confirmed): the harness still stages the OLD tables. `<main>/tmp/k1_harness/kotorphasor/addresses/k1_steam_103.json` is sha 57b1368a… and `k1_steam_103_unpacked.json` is 541c5c3e…, both HEAD. After restaging, expect c52447bd… / 5cc67517…. A rerun without the restage tests nothing.

Steam K1 layout fix: CONFIRMS
