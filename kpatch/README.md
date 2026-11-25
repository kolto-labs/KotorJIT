# KotorJIT KPM Package (.kpatch)

This folder defines KotorJIT's **DLL-only `.kpatch`** package for
[KotOR Patch Manager (KPM)](https://github.com/LaneDibello/kotor-patch-manager).

## How it works

KPM loads this archive using its DLL-only patch flow (`manifest.toml` + a
`hooks.toml` containing zero `[[hooks]]` entries + `binaries/<platform>`).
KPM's `KotorPatcher` calls `LoadModule` (`LoadLibraryA` / `dlopen`) on the
KotorJIT runtime library, which then:

1. Verifies the host executable SHA-256 (or unmodified `.text` / `__text` on
   `DT_NEEDED` ELF32 / `LC_LOAD_DYLIB` Mach-O builds).
2. Resolves hook addresses from `<game>/kotorjit/addresses/<build>.json` if
   staged on disk, falling back to the embedded address table compiled into the
   runtime binary.
3. Refuses strictly if any hook site fails exact prologue-byte verification
   (KotorJIT is incompatible with other code patches).
4. Loads Lua scripts from `<game>/kotorjit/scripts/` (or legacy
   `<game>/kotorphasor/scripts/`) and opens the F12 ImGui overlay console.

## Build `.kpatch`

```sh
python3 scripts/package_kpatch.py build
# -> dist/kotorjit.kpatch
```
