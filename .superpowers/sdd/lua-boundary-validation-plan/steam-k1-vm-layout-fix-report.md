# Steam K1 VM layout fix: report

Spec: `/home/brunner56/kp-live-20260922/steam-k1-vm-binding-rca.md` (H1).
Worktree: `.worktrees/lua-boundary-validation`, HEAD `ca329e52dd27d1a3f5a56748d93c8ab0fd7f24f2`. Nothing was staged, committed, stashed or pushed. No Wine, no game, no lock. `src/**` was not edited.

## Deviation (read first)

The generator cannot produce a Steam table whose diff holds only the two VM rows. The Steam tables committed in `5cffd0f` (the last commit to touch them) do not reflect the `data/hooksites.toml` committed with them. That manifest already declares 15 sites the Steam tables lack. Any generator run adds them. I kept the generator output rather than splicing in only the VM rows, because a spliced table is not reproducible and the next regen would overwrite it. Every catch-up row matches HEAD's GOG table exactly (proof below). Overrule if you want a splice.

I generated against **HEAD's** `hooksites.toml`, not the worktree copy. The worktree copy has about 20 uncommitted `camera*`/`client*` sites from the camera writer. They would have landed in the Steam tables as unresolved rows.

## Files touched

| File | Before sha256 | After sha256 |
|---|---|---|
| `data/adjudication/k1_steam_103_unpacked_harness_bindings.json` | `f5bb54d18b2d68e7520fe1c2e83e55c1083016fa67cc00d1af98c4b2ad89bca3` | `a72655f222b45dfa40f65d9e21461f6eef88a7a64958e0dce2684e7865d8083f` |
| `data/addresses/k1_steam_103_unpacked.json` | `541c5c3e7890406ce08d2959ed90cd3a97eee8974ceff6d34ae8522ccb7182c5` | `5cc67517140e3559b939b39aecb4d741c7f2fffb83075e3445726f897c2bc155` |
| `data/addresses/k1_steam_103.json` | `57b1368a8b96d6b07edffecd1ac00f161d3c3ff5d9900d70273fdf77382a494c` | `c52447bd10a2811a2a40530ecf3696803adad0ddcebcb62ebf7a415ce7f62048` |
| `tools/address_table_layout_test.py` (new) | none | `312cacf0b564c2c0c3bffb286a56cfd8f33d5de61bdfeebe4a738580d21173ac` |

Unchanged, checked by sha256 before and after:
- `k1_gog_103.json` `65e7c2dd…f7fd66`
- `k2_gog_aspyr.json` `4e21a72a…b38187`
- `k2_steam_aspyr.json` `14eb04aa…3cc7`

`src/generated/builds.inc` was not written. `--build` skips it unless every build is targeted.

## Adjudication edit

I inserted two rows at index 0 and 1, which is where GOG has them. Every field matches the GOG rows: name, kind, owner, addr `0x00000000`, offset, size 4, verdict accept, confidence 1.0, and the GOG `evidence.disassembly` text. I added `evidence.steam_image` and `evidence.restated_from`. `counts` went from fields 127 / accept 196 to 129 / 198.

- `CVirtualMachine::internal`, offset `0x0`, size 4.
- `CVirtualMachineInternal::command_implementer`, offset `0x3d4`, size 4.

I re-read these Steam-image referents myself from `tmp/k1_harness/swkotor.exe` (sha256 `2719ed2c…3a05`, which is the `k1_steam_103_unpacked` identity):
- `.textU` (VA 0x401000, vsize 3,387,856) is byte-identical to the GOG `.text` over that range. The GOG file is `~/biodecompwarehouse/kotorxid/extract/raw/K1__k1_win_gog_swkotor.exe`, sha256 `9c10e045…1435`. There are 0 differing bytes, and both ranges hash to `39bcd9f2c21de0e24aef77bcc2912f313fe9ed57803f505819d19a59ee0d4135`.
- `0x005d1000` StackPopInteger reads `8b 09 e9 b9 14 00 00`. That is `mov ecx,[ecx]`, so the internal VM is at +0.
- `0x005d45d0` RunScript begins `53 55 56 57 8b 7c 24 14 33 ed 3b fd 8b f1`, which puts `this` in `esi` at `0x005d45dc`.
- `0x005d4650`, `0x005d466a` and `0x005d4676` each read `8b 8e d4 03 00 00`. That is `mov ecx,[esi+0x3d4]`.

### `CNetLayer::destination_net_layer`: left out

The GOG receipt's cited addresses do not hold on the (identical) bytes:
- "Initialize 0x5d4c10" is not Initialize. The bytes there are a destructor-shaped stub (`56 8b f1 e8 … c2 04 00`). The generator resolves `net.initialize` to `0x005D5550`.
- "loads [esi+0x2000c] at 0x5d4cba" lands inside the SEH prologue (`00 00 00 50 64 89`). No `+0x2000c` immediate is there.

The underlying claim does hold at other addresses:
- `0x005d5567` `89 86 0c 00 02 00` and `0x005d5572` `89 b0 0c 00 02 00`: the reciprocal stores in Initialize.
- `0x005d4ccb` `8b 85 0c 00 02 00`: SendMessageToPlayer, via `ebp`.

Citing those would be new evidence rather than a byte-identical restatement, so the condition in the task fails as written. This is a finding for the owner of `k1_gog_103_harness_bindings.json`: correct the cited addresses there, then restate the row for Steam.

Consequence: `net.destination_net_layer` stays unresolved on Steam, so multiplayer on Steam K1 still refuses with "multiplayer field unavailable" (`runtime.cpp` multiplayer block). That is unchanged from before. The embedded role is unaffected.

## Generator

The temp copy was `/tmp/kp-steamfix-gen/repo`: `tools/` and `data/` copied from the worktree, then `data/hooksites.toml` replaced by `git show HEAD:data/hooksites.toml`. Without `KP_K1_UNPACKED`, the generator refuses both builds with "reference image not available".

```
$ KP_K1_UNPACKED=/run/media/brunner56/MyBook/Workspaces/KotorPhasor/tmp/k1_harness/swkotor.exe \
    python3 tools/gen_address_tables.py --build k1_steam_103_unpacked --build k1_steam_103
k1_steam_103_unpacked  255/256 resolved (func 60, identity 0, adjudicated 195)  ok
  sentinel         : 0x0052C0D0 8b54240481fa04030000
  fields           : 127 bound
k1_steam_103           255/256 resolved (func 60, identity 0, adjudicated 195)  ok
  sentinel         : 0x0052C0D0 8b54240481fa04030000
  fields           : 127 bound
exit=0
```

`diff -rq` of the temp repo against the worktree:
- `data/`: only the two Steam JSONs differ, plus the swapped-in `hooksites.toml`.
- `tools/`: `kpharness_*_test.py`, `kp_harnesstest.cpp` and `kp_motiontest.cpp` differ. Their worktree mtimes (11:59 to 12:05) are later than the temp copy's creation time (11:55:15). The generator's only write is `data/addresses/<alias>.json` (gen_address_tables.py:926).

After that I copied only the two JSONs back.

## Diff summary for both Steam tables

The two tables are identical in their sites dict.

1. **Intended.** `vm.wrapper_internal` is now adjudicated, offset 0, size 4. `vm.internal_command_implementer` is now adjudicated, offset 980 (0x3d4), size 4. `adjudicated_bindings` went from 196 to 198.
2. **Catch-up from HEAD `hooksites.toml`.** These 12 sites are added and resolved. Each one's `addr`, `kind`, `expected_bytes`, `offset` and `size` equal the GOG HEAD entry:
   - `net.initialize`, `net.shutdown`, `net.send_message_to_player`, `net.process_received_frames`, `net.start_server_mode`, `net.non_window_messages`
   - `client.area_get_server_area`, `client_area.attach_from_server`, `server_area.attach_from_client`, `module.get_area`
   - `creature.add_move_to_point_action`, `server_object.set_position`

   `net.start_connect_to_session` changed kind from call to detour. `net.destination_net_layer` was added unresolved, as explained above.
   - Parity check: every site in the new Steam table has the same `addr`, `kind`, `expected_bytes`, `offset` and `size` as `git show HEAD:data/addresses/k1_gog_103.json`. The one exception is `net.destination_net_layer`. GOG has no site that Steam lacks.
   - Summary: total 241 → 256, resolved 241 → 255, by_func 48 → 60, by_field 125 → 127. `installable` is still true and `missing_required` is still empty.
3. **Excluded.** The camera-writer sites (`camera*`, `client.module`, `client.options`, `client_module.*`, `client_options.camera_mode`, `g.camera_style_pending`) are left out.

Live effect of the catch-up: the six new or changed detours are added only inside `if (multiplayer_enabled)` (`runtime.cpp` around 559-595). The support sites are read in two other places:
- `hook_bodies.cpp:268` and `:333` look up `server_object.set_position`, inside `replay_move_to_point` and `replay_authoritative_position`. Both return early unless a multiplayer frame arrives and the role is Server or Client (`hook_bodies.cpp:259-262` and `:324-327`).
- `hook_bodies.cpp:581-585` is inside `client_area_get_server_area_body`, a detour installed only in the multiplayer block.

So with multiplayer off, the footlocker rerun changes only the VM layout.

## Test: red, then green

`tools/address_table_layout_test.py` is standalone unittest and is not wired into CMake, because `CMakeLists.txt` is another writer's. It covers every `data/addresses/*.json` that has `vm.run_script`. It replicates the `runtime.cpp` `layout_resolved` predicate plus `parse_field_extent`: both sites must be present, kind `field`, `size` a nonzero number equal to the pointer width, and `offset` a number. Six predicate unit tests pin each rejection path.

Red, before the data fix:
```
FAIL: ... (table='k1_steam_103.json')
  k1_steam_103.json: runtime would not bind the VM: vm.wrapper_internal: absent; vm.internal_command_implementer: absent
FAIL: ... (table='k1_steam_103_unpacked.json')
  k1_steam_103_unpacked.json: runtime would not bind the VM: vm.wrapper_internal: absent; vm.internal_command_implementer: absent
Ran 8 tests  FAILED (failures=2)   exit=1
```

Green, after:
```
Ran 8 tests in 0.041s
OK   exit=0
```

Regression checks on the Python consumers of the Steam tables:
- `tools/platform_profile_consistency_test.py`: 20 tests, OK.
- `tools/platform_receipt_test.py`: 25 tests, OK.
- `tools/kpharness_offline_test.py`: 150 tests, OK.

`tools/kp_eventtest.cpp` `address_table_cases` (around line 297) loads both Steam tables. It was not built or run: it is C++ and outside this scope.

## Proposed `src/runtime/runtime.cpp:640` log change (for the integration writer)

```diff
         set_vm_sites(sites);
         log("vm: %d of 13 stack sites resolved; the two VM objects are captured "
             "from the first script the game runs",
             (sites.execute_command ? 1 : 0) + (sites.stack_push_integer ? 1 : 0) +
             (sites.stack_pop_integer ? 1 : 0) + (sites.stack_push_float ? 1 : 0) +
             (sites.stack_pop_float ? 1 : 0) + (sites.stack_push_string ? 1 : 0) +
             (sites.stack_pop_string ? 1 : 0) + (sites.stack_push_object ? 1 : 0) +
             (sites.stack_pop_object ? 1 : 0) + (sites.stack_push_vector ? 1 : 0) +
             (sites.stack_pop_vector ? 1 : 0) +
             (sites.stack_push_engine_structure ? 1 : 0) +
             (sites.stack_pop_engine_structure ? 1 : 0));
+        if (sites.layout_resolved) {
+            log("vm: layout resolved (wrapper->internal +0x%x, "
+                "internal->command_implementer +0x%x)",
+                static_cast<unsigned>(sites.wrapper_internal_offset),
+                static_cast<unsigned>(sites.command_implementer_offset));
+        } else {
+            log("vm: layout UNRESOLVED (vm.wrapper_internal %s, "
+                "vm.internal_command_implementer %s); the routine bridge will "
+                "never bind and every routine call will fail",
+                wrapper_internal == nullptr ? "absent"
+                    : !wrapper_internal->resolved ? "unresolved" : "wrong kind/size",
+                command_implementer == nullptr ? "absent"
+                    : !command_implementer->resolved ? "unresolved" : "wrong kind/size");
+        }
     }
```

`wrapper_internal` and `command_implementer` are the locals already in scope in that block. This implements the `internal.hpp:140-142` intent ("a missing site is reported during installation"). Both `*_offset` fields are `std::uint32_t` (`src/api/enginestruct.hpp:137-138`), so the `unsigned` casts are exact.

## Residuals

- **A live footlocker rerun is required.** It needs the lock owner. Restage the harness data so `tmp/k1_harness/kotorphasor/addresses/` picks up the new tables, then run one footlocker route with multiplayer off. Expect:
  - `vm: routine bridge refreshed` in `kotorphasor.log`
  - a non-null `pc`
  - step 3 or 5 passing
  - the hook-install line still succeeding

  A run that loads the new table and still shows no bind line would revive RCA H2 (world timers paused, so no RunScript).
- The GOG `CNetLayer::destination_net_layer` receipt cites wrong addresses. Its owner should correct them. After that, the row can be restated for Steam and Steam multiplayer unblocked.
- `docs/capability-cells.md` [K5] still says "undiagnosed". Update it after the live rerun (RCA fix step 6).
- The new test is not registered in CMake or CTest. Wire it in when `CMakeLists.txt` is free.

## Continuation: offline VM-boundary guard (2026-09-27)

This continues the existing test rather than creating a second test. The sole
writer change is `tools/address_table_layout_test.py`.

### Three review gaps closed

1. **Per-game layout values.** `adjudicated_layout()` reads the layout rows via
   `gen_address_tables.load_overlay()` and keys them through
   `data/hooksites.toml`; it does not hard-code a table copy. `DONOR` pins K1
   to `k1_gog_103` and K2 to `k2_gog_aspyr`. `test_every_build_agrees_with_its_games_donor`
   requires each build overlay to agree with that game's donor;
   `test_every_vm_table_carries_its_games_layout_values` checks the generated
   table too. `test_k1_derivation_matches_the_disassembly` pins the audited K1
   result: `vm.wrapper_internal = 0x0, size 4` and
   `vm.internal_command_implementer = 0x3d4, size 4`.

2. **Required VM stack sites.** `bind_sites_required()` parses the `need(...)`
   calls in `src/api/enginestruct.cpp` from `bool bind_sites(` through
   `if (!ok) return false;`. At this revision the cited lines 154-162 require:
   `vm.execute_command`, `vm.stack_push_integer`, `vm.stack_pop_integer`,
   `vm.stack_push_float`, `vm.stack_pop_float`, `vm.stack_push_string`,
   `vm.stack_pop_string`, `vm.stack_push_object`, and `vm.stack_pop_object`.
   `test_bind_sites_set_is_parsed_and_runtime_looks_each_up` also confirms
   `runtime.cpp` looks up every parsed name; every `vm.run_script` table is
   rejected when any parsed required site is absent or has no nonzero address.
   This deliberately follows the implementation rather than asserting all 13
   fields merely logged by `runtime.cpp`.

3. **Hook-pack shadowing.** `committed_hookpacks()` rejects every tracked
   `hookpack.json`, including `data/addresses/hookpack.json`, and any address
   JSON whose format is `agentdecompile.hookpack/v1`. Those cover the static
   forms that can be staged into the three locations tried by
   `runtime.cpp:394-408`: game `kotorphasor/hookpack.json`,
   `KOTORPHASOR_HOOKPACK`, and `KOTORPHASOR_ADDRESSES/hookpack.json`.
   `hookpack_problems(pack, build, overlay=None)` is the reusable helper for a
   supplied pack. It flattens per-build instances and an optional address
   overlay before applying the same layout-value and required-stack checks.
   The hook-pack tests cover a valid pack plus wrong K1/K2-style offset,
   absent required stack site, other-build instance, invalid/duplicate adapter
   key, and the case where an overlay must not overwrite a bad pack field.

### Red-first mutation evidence

The predicate tests make red inputs in memory so no address table is modified:

- `ValuePredicate.test_k2_wrapper_offset_in_k1_fails` mutates K1's wrapper
  offset to `0x1c` and expects a value mismatch.
- `ValuePredicate.test_null_addr_stack_site_fails` mutates the required
  `vm.stack_pop_object` address to `None` and expects an unresolved-site
  failure.
- `HookpackHelper.test_wrong_game_offset_fails` and
  `test_missing_stack_site_fails` mutate temporary pack dictionaries before
  calling the helper; `test_wrong_offset_is_not_rescued_by_overlay` repeats
  the offset mutation with a real overlay.

`RedTemporaryCopy.test_k1_wrong_layout_and_missing_required_stack_site_fail`
also creates a `TemporaryDirectory` copy of `k1_gog_103.json`, changes the
copy's wrapper offset to `0x1c` and `vm.stack_pop_object` address to `None`,
then re-reads that copy and requires both guards to reject it. The temporary
directory is automatically removed; no address table in the worktree changes.

The test suite is intentionally host-only and does not start Wine, a game, or
the live harness. Resumed verification completed with:

```
python3 tools/address_table_layout_test.py
Ran 26 tests in 48.823s
OK
```

The earlier 8-test count in this report predates the extension and is not the
current result.

### Grill me

1. **Why parse only nine sites when runtime logs thirteen?**
   `src/api/enginestruct.cpp:154-162` is the binding gate named by the review;
   it contains nine `need(...)` calls before `if (!ok) return false;` at line
   163. A future added gate is automatically parsed. The remaining runtime
   lookups are not silently declared required by this test. Referent: that
   source range and `bind_sites_required()`.
2. **How do K1 offsets avoid a copied magic number?** The production check
   derives values from the generator overlay and donor; the literal appears
   only in a derivation regression. Referent:
   `adjudicated_layout`, `test_every_build_agrees_with_its_games_donor`, and
   `test_k1_derivation_matches_the_disassembly`.
3. **Can this find a pack staged outside the repository?** No. Runtime paths
   are deployment- and environment-dependent; `hookpack_problems` validates a
   supplied staged pack, while the committed-file guard protects repository
   inputs. The single settling check is to call that helper on the exact staged
   pack after the harness chooses its `cfg.game_dir`/environment. `unverified`
   for live staging in this task.
