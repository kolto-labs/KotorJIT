# Codecaves

A codecave is a span of bytes inside the game's own executable that nothing runs -- compiler alignment padding between two functions, or unused space at the end of a section. Writing your own bytes there gives a script somewhere to put a small stub of injected code, without patching over anything real.

This is a different thing from the hook sites in `data/hooksites.toml`. A hook site is a specific function the runtime detours on every supported build, resolved to a per-build address ahead of time. A codecave is just empty space; nothing points to it, nothing expects it to be there, and it only exists because the compiler happened to leave it unused.

## Finding one

`kotor.mem.findsig(pattern)` scans the executable sections of the running game for a byte pattern and returns the address it starts at, or `nil`. `data/codecaves.toml` lists verified patterns, one per cave, each anchored on the real code immediately before the cave rather than on the cave's own filler bytes -- filler bytes repeat constantly across a binary and are not a safe way to find one specific spot.

```lua
local sig = "568bf1740ee8eed8eaff56e8c8e1fbff83c4045ec3909090"
local hit = kotor.mem.findsig(sig)
if hit then
    local cave = hit + 0x18   -- sig length in bytes; see the entry's `note`
    -- cave is now a real address, verified 3632 bytes of unused space
end
```

Every entry's `note` gives the exact offset from the signature match to the cave's own start -- it is the signature's own byte length, always. `size` is how many bytes are actually free.

## Using one

Nothing on the C++ side restricts a write to an executable section (`src/api/memory.hpp` explains why: this runtime does not gate code writes at all, so there is no permission to ask for). Write your bytes with `kotor.mem.write*` the same way you would write anywhere else:

```lua
kotor.mem.writebyte(cave,     0xE9)              -- jmp rel32
kotor.mem.writedword(cave, 1, target - cave - 5)  -- relative displacement
```

Nothing checks that what you wrote is valid machine code, or that the cave is big enough for it. Getting either wrong corrupts the process the next time execution reaches that address -- there is no undo. Keep what you write inside `size` bytes, and prefer a short trampoline (a jump out to Lua-driven logic elsewhere) over trying to fit real logic in a 15-byte gap.

## Why signatures, not addresses

A codecave's address moves every time the compiler's output shifts by even one byte -- a different game patch, a different distributor's build, sometimes even a different compiler flag. `data/codecaves.toml` never writes down an address as something to use directly; every `[[cave]]` entry's `addr` fields exist only as a comment, documenting what a given signature resolved to on the one binary it was checked against. The signature is what a script actually calls `findsig` with, and it keeps working on any build where the surrounding real code happens to match -- which, for two builds sharing identical `.text` bytes (KOTOR 1's Steam and GOG builds are one such pair; see `docs/steam-gog-equivalence.md`), is every one of them at once.

## What's verified today

39 caves, across the three Windows builds this runtime can currently install on (`k1_gog_103`/`k1_steam_103`/`k1_steam_103_unpacked`, `k2_gog_aspyr`, `k2_steam_aspyr`) -- see `data/codecaves.toml` for the full list, sizes, and signatures. This is a curated sample from an exhaustive scan, not the whole of what exists: that scan enumerated every run of 12+ bytes of compiler filler across each binary's `.text`, found 2,912 / 3,501 / 3,509 such runs respectively, and narrowed those to the subset anchored on a real (non-`FUN_xxxxx`) function name -- 1,678 / 2,127 / 35. `k2_steam_linux` was checked and has nothing usable: its `.text` carries almost no compiler alignment padding at all, unlike the MSVC-built Windows binaries.

Every entry was checked two ways before being written down: the signature matches exactly once when scanned against the real binary with this project's own `findsig` semantics (hex string, `?` is a per-nibble wildcard), and the bytes at the resulting cave address are confirmed to be a single uniform filler byte for the entry's whole declared `size` -- read directly from the file, not assumed from a reverse-engineering corpus's function-boundary data, which was occasionally a few bytes short of a function's real end and would otherwise have reported a false cave inside the previous function's own tail instructions.
