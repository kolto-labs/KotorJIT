# Steam K1 VM never binds after the 22 September migration: root-cause analysis

This was a read-only investigation. No repository file was edited. Wine, the game, Gamescope and FFmpeg were not run. The live-game lock was not touched.

Paths are relative to `/run/media/brunner56/MyBook/Workspaces/KotorPhasor`. `WT` means `.worktrees/lua-boundary-validation` (HEAD `ca329e5`).

## Verdict

**Root cause (confirmed statically, high confidence):** the migration moved two VM layout facts out of the code and into the per-build address table. It adjudicated them for K1 GOG and both K2 builds. It never added them to the Steam K1 adjudication file.

- **Before `5cffd0f`:** the code hardcoded both facts. The implementer offset was `kCommandImplementerOffset = 0x3D4`, and the code assumed the wrapper holds the internal VM at offset 0.
- **After `5cffd0f`:** both facts come from the table sites `vm.wrapper_internal` and `vm.internal_command_implementer`.

On Steam K1 those two sites are absent, so `layout_resolved` is false. `capture_vm` then returns silently on every script (`WT/src/runtime/runtime.cpp:899`), and the VM never binds.

Everything reported is a downstream symptom of that one gate:

- `pc: null`
- the `GetFirstPC: live VM context or command slot is unavailable` error
- the failed warm step

## Ranked hypotheses

### H1: the Steam K1 table lacks the VM layout fields, so the `layout_resolved` gate rejects every capture

```
claim: Both Steam K1 tables lack vm.wrapper_internal and vm.internal_command_implementer; GOG K1 and both K2 tables have them.
referent: python replica of the runtime.cpp:628 predicate over data/addresses/*.json (run in WT):
  k1_gog_103.json            run_script=True layout_resolved=True
  k1_steam_103.json          run_script=True layout_resolved=False
  k1_steam_103_unpacked.json run_script=True layout_resolved=False
  k2_gog_aspyr.json          run_script=True layout_resolved=True
  k2_steam_aspyr.json        run_script=True layout_resolved=True
  Site-set diff GOG vs Steam K1 (main, WT, and staged copies identical): only-GOG includes exactly these two vm.* fields plus 13 multiplayer/net sites.
checked: command run; same result for main data/, WT data/, and tmp/k1_harness/kotorphasor/addresses/
verdict: holds
confidence: high. Would change only if the loader synthesised the fields from somewhere else; it does not (next claim).
```

```
claim: Nothing at load time can add the missing fields.
referent: AddressTable::merge_overlay (WT/src/hooks/registry.cpp:481-500) iterates only sites_ already in the pack, and skips the rest ("if (o == nullptr) continue;"). AddressTable::find (registry.cpp:510) returns nullptr for an absent name.
checked: file read
verdict: holds
confidence: high
```

```
claim: With the fields absent, capture_vm returns before binding and logs nothing.
referent: WT/src/runtime/runtime.cpp:622-638 sets sites.layout_resolved only when both field sites resolve with kind Field and size 4.
  runtime.cpp:899 `if (!g_sites.layout_resolved || ...) return;` comes before the only success log, "vm: routine bridge refreshed" at runtime.cpp:920.
  hook_bodies.cpp:686 calls capture_vm(self) on every RunScript.
  vm_binding_live (WT/src/api/enginestruct.cpp:109) is then false, so routines.cpp:454 raises "live VM context or command slot is unavailable".
checked: file read
verdict: holds
confidence: high
```

```
claim: The run logs match the gate: no bind line in any post-migration Steam run; a bind line in every pre-migration Steam run.
referent: grep over tmp/k1_harness/runs/*/kotorphasor.log:
  Every Sep 16 k1_steam_103_unpacked run (002522 ... 150340, 31 runs) logs "routine bridge bound|refreshed".
  20260922-160943, -162824 and -165126 have bridge=0.
  In all three, the install line says "vm: 13 of 13 stack sites resolved"; that count excludes the layout fields (runtime.cpp:640), so it hides the failure.
checked: shell loop over run dirs
verdict: holds
confidence: high
```

```
claim: The DLL that ran contains the gated capture_vm.
referent: build/kphasor.dll and tmp/k1_harness/kphasor.dll are both sha256 bdf420d1b283dcd6..., mtime 2026-09-22 16:51:00. Run 165126 logged "runtime installed from .../build" at 16:52:04 and failed the same way.
  DLL string scan: "routine bridge refreshed" x1, "vm.wrapper_internal" x1, "vm.internal_command_implementer" x1, and the old "cannot bind the routine bridge" / "routine bridge bound" x0.
checked: python byte-count scan on the DLL
verdict: holds for 165126. For 160943 and 162824 (stamp 0666534c0029) the DLL was overwritten, so "same gate" is inferred from identical symptoms and the same source era: `unverified`.
confidence: medium-high for those two
```

```
claim: The migration commit removed the hardcoded layout and added the fields for K1 GOG only.
referent: git show 5cffd0f (2026-09-22 08:54, "snapshot existing Lua boundary work"):
  src/runtime/runtime.cpp: removes `constexpr std::uint32_t kCommandImplementerOffset = 0x3D4;` and `void* g_vm_wrapper`; adds the layout_resolved gate.
  data/addresses/k1_gog_103.json: adds vm.wrapper_internal (offset 0x0) and vm.internal_command_implementer (offset 0x3D4).
  data/adjudication/k1_gog_103_harness_bindings.json: added with 199 bindings, including CVirtualMachine::internal and CVirtualMachineInternal::command_implementer.
  data/adjudication/k1_steam_103_unpacked_harness_bindings.json: 196 bindings. Missing exactly CNetLayer::destination_net_layer, CVirtualMachine::internal and CVirtualMachineInternal::command_implementer. All 196 common bindings are equal on addr/offset/size/verdict.
  That file's own target_binary.note says it is "the GOG binding restated ... must not drift."
checked: git show and a python diff of the two adjudication files
verdict: holds
confidence: high
```

```
claim: The GOG values are correct for the Steam image.
referent:
  1. The Steam .textU (tmp/k1_harness/swkotor.exe, sha 2719ed2c...) is byte-identical to the GOG .text (kotorxid raw_image, sha 9c10e045...) over all 3,387,856 bytes of the virtual size. 0 differing bytes; both sha256 39bcd9f2c21de0e2...
  2. Direct Steam-image bytes:
     StackPopInteger 0x5d1000 = 8b09 e9... (mov ecx,[ecx]; jmp), so wrapper_internal is at offset 0.
     RunScript 0x5d45d0 prologue `8bf1` (esi=this), then `8b8ed4030000` (mov ecx,[esi+0x3d4]) at 0x5d4650, 0x5d466a and 0x5d4676, so command_implementer is at +0x3d4.
checked: python byte compare and a hex read of the Steam image
verdict: holds
confidence: high
```

This is the most discriminating check, and it was run here. The replica predicate returns `layout_resolved=False` for exactly the two Steam K1 tables and `True` for every build that binds. The byte comparison shows the correct values are the GOG ones. Only a live run is left, to see the bind line appear (see "Live confirmation" below).

### H2: world timers stay paused, so no NWScript runs and `capture_vm` is never reached

```
claim: No script ran after the harness load, so capture never had a chance.
referent:
  For: 162824 and 165126 never logged "unpause_timers" (the load_save log shows "paused 2 world timer(s)").
  Against: 160943 did log "unpause_timers: unpaused 2 timer(s)" and still failed 16 s later. More decisively, H1's gate rejects the bind even when RunScript fires.
checked: kotorphasor.log lines 53 and 66 (160943)
verdict: does not hold as the cause. It may be a second, masked issue for routes without clear_auto_pause; whether any OnRunScript fired is `unverified` (no ring dump in these runs).
confidence: medium. A run with the fields present that still shows no bind line would bring it back.
```

### H3: a stale staged address table

```
claim: The harness staged an outdated Steam table.
referent: The staged tmp/k1_harness/kotorphasor/addresses/k1_steam_103_unpacked.json is dated Sep 15, but its sites dict is identical to main data/ and WT data/ (python compare: same names, 0 differing). Staging copies data/addresses whenever sources change (WT/scripts/harness/kpharness/session.py:768, 807-812).
checked: python compare
verdict: does not hold. The repo copies lack the fields too.
confidence: high
```

### H4: SteamStub decipher, identify, or resolve went wrong

```
claim: The encrypted-image path mis-resolved VM sites.
referent: The runs load the unpacked image. The log shows "code section verified: 39bcd9f2...", ".textU state=plaintext", "signature resolve: 241/241 sites bound", "13 of 13 stack sites resolved", and a detour on 005d45d0 (vm.run_script) installed.
checked: kotorphasor.log lines 5-13
verdict: does not hold
confidence: high
```

### H5: `pc: null` or `player_creature_id=ffffffff` points to a separate load-path fault

```
claim: The null pc is an independent symptom of the harness load path.
referent: WT/src/harness/commands.cpp:611 fills pc only `if (runtime::vm_bound())`. There is no pc_error, so vm_bound() was false. pc:null is H1's symptom.
checked: file read
verdict: does not hold as an independent cause. Whether player_creature_id=ffffffff is normal for this load path on GOG is `unverified`.
confidence: high for "pc null comes from the unbound VM"
```

## Open item that does not change the fix

The Sep 16 Steam runs already log the newer "routine bridge refreshed" format. They bound against a table that also lacks the two fields. So the message format predates the `layout_resolved` gate. The gate entered git in `5cffd0f`, whose parent `adf975a` has no gate. The exact moment it entered the uncommitted working tree between Sep 16 15:03 and Sep 22 08:54 is `unverified`. An older DLL under `tmp/build-*` would settle it. It does not matter for the fix: gate plus absent fields fails deterministically.

## Minimal fix scope, if confirmed live

1. **Data.** Add the two accepted field bindings to `data/adjudication/k1_steam_103_unpacked_harness_bindings.json`, restated from `k1_gog_103_harness_bindings.json`:
   - `CVirtualMachine::internal`: offset 0x0, size 4
   - `CVirtualMachineInternal::command_implementer`: offset 0x3d4, size 4

   Cite the byte-identical-text receipt and the Steam-image bytes above as evidence. Optionally add `CNetLayer::destination_net_layer` so the file stops drifting. It is multiplayer-only and irrelevant to the embedded role.
2. **Generate.** Regenerate both `data/addresses/k1_steam_103_unpacked.json` and `data/addresses/k1_steam_103.json` with `tools/gen_address_tables.py`. The generator globs `<stem>_*_bindings.json`, so the `k1_steam_103` stem also picks up the `_unpacked_` file (gen_address_tables.py:598). Hand-editing only the JSON would be overwritten on the next generation.
3. **Test.** Add a host test asserting that every shipped table with `vm.run_script` yields `layout_resolved`, meaning both fields have kind field and size 4. The replica above is the logic. That test would have caught this.
4. **Visibility.** Make the install log report an unresolved VM layout. Today `runtime.cpp:640` prints "13 of 13 stack sites resolved" and hides it. That goes against the `internal.hpp:140-142` intent: "a missing site is reported during installation".
5. **Live confirmation.** Not run; this needs the lock owner. Restage, then rerun one footlocker route. Expect `vm: routine bridge refreshed` in kotorphasor.log, a non-null `pc`, and step 3 or 5 to pass.
6. **Docs.** Update the `docs/capability-cells.md` [K5] note from "undiagnosed" to this cause once the live rerun passes.
