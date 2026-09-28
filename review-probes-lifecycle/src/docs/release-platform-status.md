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
