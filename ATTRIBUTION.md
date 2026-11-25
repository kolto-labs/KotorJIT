# Attribution

KotorJIT stands on work other people did first. Who, and for what:

## Architectural model

**[Phasor](https://github.com/urbanyoung/Phasor)**: urbanyoung, MIT.

Phasor is a Lua scripting host for Halo servers. KotorJIT borrows its shape, and the
borrowing is deliberate rather than incidental:

- Scripts live in a folder and define only the event callbacks they care about.
- Undefined callbacks are detected once at load time and skipped thereafter, so a script
  that ignores a high-frequency event pays a hash lookup rather than a Lua call.
- When several scripts answer the same event, the first one to return a usable value claims
  the result; later scripts still run, and are told their answer will be ignored.
- Events that nobody claims fall back to a per-event default.

Two defects in Phasor's implementation are fixed here rather than reproduced. Its
`OnHashValidation` event is dispatched but missing from the list used to build the
undefined-callback set, so every script that does not define it throws on every call; we
generate dispatch and that list from one table so the mismatch cannot occur. Its
error-quarantine path is commented out, so a script failing in a per-tick event logs forever;
quarantine is on by default here.

## Patching and hooks

**[kotor-patch-manager](https://github.com/LaneDibello/kotor-patch-manager)**: Lane Dibello
and contributors, MIT, 2025.

The prior art for running native code inside KOTOR. Credited for its code caves, injection
points, published reverse-engineering findings for both games, and its deployment tooling:

- **Deployment and packaging designs adopted here**:
  - Data-driven hook verification (expected original bytes, per-version executable hashes).
  - Native Windows process-injection launching (`CreateProcess` with `CREATE_SUSPENDED` +
    remote `LoadLibraryA`, and delayed Steam/attach launching for packed builds).
  - Address-preserving ELF32 `DT_NEEDED` injection (`PT_NOTE` repurposed to `PT_LOAD`) via
    `tools/elf_needed.py`.
  - DLL-only `.kpatch` packaging (`kpatch/`, `scripts/package_kpatch.py`) so KPM itself can
    load KotorJIT without duplicating hook definitions.

KotorJIT implements its own hook engine and address tables rather than using
`KotorPatcher` detours, and is **strictly incompatible with any other code patching**:
every hook site requires exact expected prologue bytes, and KotorJIT refuses to install
hooks cleanly if another patch or module has modified those bytes.

Individual patches in that project are credited to their own authors: Lane, Vriff, J,
Synchro, VexFlint, Shae Condon, and Arniel_Stanislaus.

**Kotor-Script-Extender**: MIT. Credited for the pattern of waiting on a sentinel until the
Steam build's encrypted code section has been deciphered in memory, and for publishing
offsets for that build.

## Reverse-engineering corpus

The address tables in `data/addresses/` are generated from a long-running reverse-engineering
effort covering 24 builds of the Odyssey and Aurora engines across Windows, macOS, Linux,
Android, iOS, and Xbox. Function names, structure layouts, calling conventions, and the
cross-build identity layer that makes unnamed builds usable all come from that corpus.

## The games

KOTOR and KOTOR II are the work of BioWare, Obsidian Entertainment, LucasArts, and Aspyr.
KotorJIT is an unaffiliated fan project. It ships no game content and redistributes no
game binaries. You need your own copy of the game.

## Dependencies

**[LuaJIT](https://luajit.org/)**: Mike Pall, MIT. Fetched at build time, not vendored.
