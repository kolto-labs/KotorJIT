# Codecaves

A codecave is a span of bytes inside the game's own executable that nothing runs: compiler alignment padding between two functions, or unused space at the end of a section. Writing your own bytes there gives a script somewhere to put a small stub of injected code, without patching over anything real.

This is a different thing from the hook sites in `data/hooksites.toml`. A hook site is a specific function the runtime detours on every supported build, resolved to a per-build address ahead of time. A codecave is just empty space. Nothing points to it. Nothing expects it to be there. It only exists because the compiler happened to leave it unused.

## Finding one

`kp.mem.findsig(pattern)` scans the executable sections of the running game for a byte pattern and returns the address it starts at, or `nil`. `data/codecaves.toml` lists verified patterns, one per cave, each anchored on the real code immediately before the cave rather than on the cave's own filler bytes. Filler bytes repeat constantly across a binary. They are not a safe way to find one specific spot.

```lua
local sig = "568bf1740ee8eed8eaff56e8c8e1fbff83c4045ec3909090"
local hit = kp.mem.findsig(sig)
if hit then
    local cave = hit + 0x18   -- sig length in bytes; see the entry's `note`
    -- cave is now a real address, verified 3632 bytes of unused space
end
```

The offset from the signature match to the cave's own start is always the signature's own byte length in bytes (`#sig / 2`, since `sig` is hex). The curated entries near the top of `data/codecaves.toml` also spell this out per-entry in a `note` field. The much larger bulk section further down states it once, in that section's header, and leaves it out of each individual entry. `size` is how many bytes are actually free.

## Using one

Nothing on the C++ side restricts a write to an executable section (`src/api/memory.hpp` explains why: this runtime does not gate code writes at all, so there is no permission to ask for). Write your bytes with `kp.mem.write*` the same way you would write anywhere else:

```lua
kp.mem.writebyte(cave,     0xE9)              -- jmp rel32
kp.mem.writedword(cave, 1, target - cave - 5)  -- relative displacement
```

Nothing checks that what you wrote is valid machine code, or that the cave is big enough for it. Getting either wrong corrupts the process the next time execution reaches that address. There is no undo. Keep what you write inside `size` bytes, and prefer a short trampoline (a jump out to Lua-driven logic elsewhere) over trying to fit real logic in a 15-byte gap.

## Why signatures, not addresses

A codecave's address moves every time the compiler's output shifts by even one byte. A different game patch, a different distributor's build, sometimes even a different compiler flag. `data/codecaves.toml` never writes down an address as something to use directly. Every `[[cave]]` entry's `addr` fields exist only as a comment, documenting what a given signature resolved to on the one binary it was checked against. The signature is what a script actually calls `findsig` with. It keeps working on any build where the surrounding real code happens to match. For two builds sharing identical `.text` bytes (KOTOR 1's Steam and GOG builds are one such pair; see `docs/steam-gog-equivalence.md`), that is every one of them at once.

## What's verified today

16,184 caves total, across nine builds. Six of them are KOTOR builds this project cares about. Three of them are other engines/architectures documented for future reference only.

**Installable now.** A script can actually run against these: `k1_gog_103`/`k1_steam_103`/`k1_steam_103_unpacked`, `k2_gog_aspyr`, `k2_steam_aspyr` (3,593 caves). `k2_steam_linux` was checked and has nothing usable: its `.text` carries almost no compiler alignment padding at all, unlike the MSVC-built Windows binaries.

**Corpus-only, runtime unbound.** `k1_amazongames`, `k2_win_cd_10`, `k2_win_cd_10b` (1,816 caves). Their prior runtime tables were withdrawn because cross-placed function identities were not target-native proof. Codecave discovery is separate static analysis of each binary's own bytes, so the entries remain useful research data, but scripts cannot run on these builds until target-native hook bindings land. `k2_win_cd_10` and `k2_win_cd_10b` share one entry set because their `.text` is byte-identical.

**Not usable by KotorPhasor at all today.** `JadeEmpire`, `k2_android_x86`, `nwmain` (10,775 caves). These are not KOTOR/Odyssey builds this project's hook engine can install on, at all. `JadeEmpire.exe` runs a different BioWare engine. `k2_android_libkotor2.so_x86android` is Android (a different injection mechanism than dropping a DLL next to a Windows executable). `nwmain.exe` (Neverwinter Nights, the Aurora engine Odyssey descends from) is a 64-bit binary. The hook engine's hard `sizeof(void*) == 4` assumption rules it out entirely. They're documented so this discovery work does not have to be repeated from scratch if this project, or a fork of it, ever targets one of them. `k1_android_ARMEABI` (ARM) was attempted and deliberately left out. ARM code embeds data (literal pools) directly in its executable section the way x86 never does. A run of zero bytes there cannot be trusted as genuinely unused without disassembly-level checking this pass did not have budget for. `daorigins.exe`/`DragonAge2.exe` (no raw binary recoverable on this machine), the Xbox builds (no raw binary present at all), and the remaining Mach-O/64-bit-ELF targets (iOS, Mac, ARM64/x86-64 Android: present but not reached this pass) are undone, not rejected.

See `data/codecaves.toml` for the full list, sizes, and signatures.

The file has two kinds of section per build. A small **curated** section near the top hand-picks a sample by theme (combat, GUI, AI, resource loading, ...) with a full prose `note` per entry. That is for a script that just wants one obvious, well-described spot. A much larger **bulk** section below it holds close to the entire remaining candidate pool. Every run of 12+ bytes of compiler filler across each binary's whole `.text` was enumerated directly from the raw file (2,912 / 3,501 / 3,509 runs for `k1_gog_103` / `k2_gog_aspyr` / `k2_steam_aspyr`). That set was narrowed to the ones anchored on a real (non-`FUN_xxxxx`) function name (1,579 / 2,008 / 34). Every one of those that could be independently re-verified was written down (1,557 / 1,996 / 34). The rest failed only because a unique signature couldn't be derived even after extending context to 96 bytes, not because of any doubt about the cave itself. The three not-yet-installable builds skip the curated/bulk split. Their pools are smaller (5,022 / 3,083 runs for `k1_amazongames` / `k2_win_cd_10`, narrowed to 1,064 / 751 real-name-anchored candidates, all of which found a unique signature). Those builds get one flat section each instead.

Every entry, curated or bulk, was checked two ways before being written down. The signature matches exactly once when scanned against the real binary. The curated entries use this project's own `findsig` semantics with per-nibble `?` wildcards. The bulk and not-yet-installable entries use an exact byte sequence with no wildcards at all, since a function's own real tail bytes are deterministic and need none. The bytes at the resulting cave address are a single uniform filler byte for the entry's whole declared `size`. That read is from the file, not assumed from a reverse-engineering corpus's function-boundary data. The corpus was occasionally a few bytes short of a function's real end. Trusting it would have reported a false cave inside the previous function's own tail instructions.
