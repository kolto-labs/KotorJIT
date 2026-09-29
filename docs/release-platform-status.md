# Release platform status

Evidence checked 2026-09-27. The combined K1/K2 GOG console preview is built from ca329e5 plus four reviewed string/adapter-key overlays, three reviewed normal-load completion files and the final K2 profile. Its exact DLL/proxy pair passed 44 K1 live checks and eight K2 console commands after loading one copied save. K2 world/HUD and F12-over-world screenshots were visually inspected after requiring main_menu=0. Runs used Wine; this is not native Windows or Mac execution evidence.

| Target | Current evidence | Next acceptance gate |
|---|---|---|
| K1 GOG PE32 | Exact executable identity, installed runtime, physical F12, native state restoration and string boundary tests passed under Wine | Native Windows install/input/removal validation |
| K2 GOG PE32 | Exact GOG executable + installed Steam assets passed private boot/channel/physical F12 and typed Lua result under Wine | Broader native APIs, movement/combat, intact GOG install and native Windows execution |
| K1 Mac corpus image | Mach-O32 i386 executable; independently reviewed portable parser passes against private image; static-only runtime profile | Darwin loader/memory backend, ABI and renderer/input integration; real Mac execution |
| K2 Mac corpus image | Mach-O32 i386 executable; independently reviewed portable parser passes against private image; static-only runtime profile | Same layered gates, independently verified for K2 |

The two existing Mac corpus images are legacy 32-bit binaries. They do not establish compatibility with other installed Mac variants or modern 64-bit binaries. Build identity, architecture and capability must be explicit; a different binary requires its own matching evidence and ABI.

## Shared developer contract

AgentDecompile currently exports agentdecompile.hookpack/v1 logical entities with per-build instances, expected-byte windows and optional adapter keys. KotorPhasor now consumes an explicit adapter_key as the stable runtime operation name and rejects duplicate effective names. Legacy packs without that field retain their existing names.

Feature code should use these stable operations and capability checks. The platform adapter owns image format, relocation, pointer width, calling convention, object layout, memory protection and input/render integration. A matched function name or byte window alone does not prove a callable ABI or compatible object layout. Unknown or unsupported operations must refuse explicitly.

Existing native ABI/layout adapters remain authoritative until the producer exports verified typed equivalents. Do not infer calling conventions from prototype strings or introduce an alternative recovery engine. No connection to the Unity game engine is intended.

## Packaging boundary

The shipped preview excludes unfinished playback, experimental projectile replacement and proprietary corpus reports. Retail executables/assets/saves remain local and are never packaged. Source profiles and capability status must distinguish static mapping, build success, loader success and live feature acceptance.

The portable Mach-O metadata parser supports thin little-endian 32/64-bit images. Its focused CTest passed; 1,095 synthetic checks and four additional checks against the private Mac images passed. Independent review found no actionable issues. Fat and big-endian containers explicitly refuse. This parser is not yet wired into runtime loading.

K2 startup receipt: /home/brunner56/kp-live-20260922/private-gpu-runs/20260926-235959/k2-startup-result.json. Exact released DLL/proxy loaded 19 hooks, physical F12 and typing `1 + 1` returned exactly `number: 2`, request1 completed. Source receipt unchanged and owned namespace exited0. Installed Override mods were omitted in the private stage; no save loaded. VM was not yet bound and missing sites remain explicitly reported; no gameplay/native API parity claim.

2026-09-27 private K2 save run20260927-000511 passed with one experimentally corrected field (client.net_layer, internal+0x10). The copied save reached gameplay with a bound VM and valid PC; seven physically typed console commands passed, including tag, position, HP and arithmetic recovery. Model capabilities correctly reported unsupported. Original save hashes and source receipts remained unchanged. The authoritative profile update and exact final-profile replay are pending; the existing distributed ZIP remains K1-only.

The existing kp_imagetool identify/sections commands now accept thin little-endian Mach-O32/64 through the shared parser, preserving64-bit addresses on32-bit hosts. Synthetic CLI tests, actual private Mac image inspection and independent review passed. Runtime loading is still unsupported; mapped/classify/dump explicitly refuse for Mach-O.

Correction after visual inspection of final-profile run20260927-000933: eight physical-console commands and world queries passed, including exact atton string. However the main menu remained visible (main_menu=1). This is NOT accepted playable gameplay; the state-only gate was insufficient. Combined packaging is held while the normal load-completion path is repaired and the stronger visible-world gate is tested. Existing K1 preview is unaffected.

Normal-completion correction accepted on K2 in run20260927-001824: rebuilt runtime loaded the copied save, retired the main menu (main_menu=0), bound the VM and passed eight physical-console commands including exact nonempty tag atton/length5. Controller visually inspected both the game world with F12 closed and the console over the world. Save hashes and asset receipts unchanged. This is one-save console/read-only bridge acceptance, not movement/combat/full-API coverage. K1 regression of the same rebuilt runtime is pending before combined packaging.

Delivered combined archive: /home/brunner56/kp-release-20260927/kotorphasor-k1-k2-gog-console-preview.zip (10,168,030bytes), SHA2560388d0806c74c0ad158f7d120165a5d530798c14fbbaa1674b8c6c759ce867c9. K1 final44/44 regression passed on the same rebuilt DLL pair. ZIP CRC,17manifest entries,606source files, reviewedfix hashes, exactDLL-to-live equality and runtime profile-site equality passed controller verification. Old K1 archive preserved. Earlier pending/failed entries above document the investigation and are superseded only for these explicitly accepted gates. Full goal remains open.

## macOS x86_64 runtime landed 2026-09-29 (this session)

The K1 and K2 Mac targets in the table above are the legacy 32-bit corpus
images. Separately, the **x86_64 Steam macOS builds** (K1 `KOTOR_Exe`, K2
`KOTOR2sub` x86_64 slice) are now first-class:

- `src/image` parses and identifies thin/fat 64-bit Mach-O from the mapped
  image and verifies the code-section hash, like the PE/ELF path.
- A Darwin platform layer (`mach_vm_*`, dyld image base, W^X with VM_PROT_COPY
  for the signed code pages) and the x86_64 detour engine (14-byte absolute
  jump, RIP/rel32/rel8 relocation, near-trampoline) carry the hooks.
- The routine bridge, all sixteen event/VM hook sites, `kp.mem`, timers and the
  F12 Lua console (Objective-C-runtime swizzle of `flushBuffer` and
  `nextEventMatchingMask`) work on the System V ABI, with 64-bit object ids.
- Address tables: K2 from its own symbols; K1 (stripped) from ≥2 agreeing
  derivations per binding (`data/adjudication/mac_x64_bindings.json`). Both are
  regenerated and verified by `tools/mac/gen_mac_tables.py [--check]`;
  `tools/mac/mac_tables_test.py` is the binary-free structural gate.
- `kp.model` and `kp.animation` bind on K2 x86_64 from a corpus-verified
  profile. `kp.struct` is gated off on 64-bit (raw `kp.mem` unaffected).
  Motion/camera native offsets are recovered and recorded but not yet wired.
- Build: `scripts/mac/build.sh` (x86_64 dylib + vendored LuaJIT). Install:
  `scripts/mac/install_to_game.sh` + a `DYLD_INSERT_LIBRARIES` launch option.

Not yet done, and not claimed: execution on real macOS hardware. Everything
above is static verification and cross-ABI compilation; the new code has not
been run inside a game. The next gate is a live Rosetta/Intel bring-up (attach,
identify, install hooks, fire an event, call a routine, open the console) with
a receipt, matching how the Windows/Wine gates were taken.
