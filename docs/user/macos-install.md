# Hyperstim on macOS (Steam, x86_64)

Hyperstim runs on the Steam macOS builds of KOTOR 1 (`KOTOR_Exe`) and KOTOR 2
(`KOTOR2sub`, the x86_64 slice of its universal binary). Both are x86_64, so on
Apple silicon they run — and Hyperstim runs with them — under Rosetta 2. On an
Intel Mac they run natively. Nothing here touches a 32-bit Mac build.

## What works

- The `.lua` script model, exactly as on Windows: drop a file in
  `<game>/hyperstim/scripts`, register for events, return to observe/block.
- Every NWScript event that funnels through `RunScript` and the ten object
  `EventHandler`s (creature, door, placeable, trigger, module, area, encounter,
  area-of-effect, store, waypoint), plus save/load situation and the console.
- `nwscript.call(name, ...)` for the full routine set (769 callable on K1),
  through the same generic bridge, with the object-id and vector calling
  conventions adjusted for the System V x86_64 ABI.
- `kp.mem.*` raw memory, `kp.registertimer`, `nwscript.with_caller`, the F12
  in-game Lua console (rendered over the game's OpenGL context, input taken
  from the Cocoa event pump).
- On KOTOR 2: `kp.model.*` and `kp.animation` native scaling/clip queries,
  bound from a corpus-verified profile.

## What does not (yet)

- `kp.struct` typed field access is unavailable on 64-bit builds — its offsets
  are 32-bit K1 layouts. Use `kp.mem` for raw reads; a wrong offset is worse
  than an honest "unsupported".
- `kp.camera` / `kp.motion` native APIs on Mac: the core functions are located
  (docs/research/mac-model-memory.md) but their full verification tables are not
  wired yet.
- The headless harness / TAS control plane and the multiplayer split: their
  adapters are Windows/Linux-ABI; on Mac the harness reports every command
  "unsupported" rather than reading a wrong offset. The listener is off by
  default regardless.

## Build

On a Mac with Xcode Command Line Tools:

```sh
scripts/mac/build.sh          # -> build-mac/libhyperstim.dylib (x86_64, ad-hoc signed)
```

LuaJIT and Dear ImGui are vendored; no network is needed. `cmake --build` on a
Mac runs this same script.

## Install

```sh
scripts/mac/install_to_game.sh install "<KOTOR app or MacOS dir>"
```

It identifies the build by its code-section hash, copies the dylib and the
matching address table into `<game>/…/MacOS/hyperstim/`, writes a starter
`hyperstim.ini` and an example script, and prints the launch line. No game
file is modified.

Then set the game's **Steam launch options** to what the installer prints:

```
DYLD_INSERT_LIBRARIES="…/MacOS/libhyperstim.dylib" %command%
```

That is the whole install. The runtime identifies the executable by hashing its
code section at load; an executable it does not recognise is left completely
unpatched. `install_to_game.sh status` and `uninstall` do what they say;
uninstalling is deleting the dylib and clearing the launch option.

## Why DYLD_INSERT_LIBRARIES and not a Bink proxy

The Windows build hijacks `binkw32.dll`. On macOS the same effect — load our
code before the game's entry point — comes from `DYLD_INSERT_LIBRARIES`, which
these builds allow because their code signature sets no library-validation or
hardened-runtime flag. A dylib constructor starts the runtime on a worker
thread, exactly as the Windows/Linux entry points do. No Bink dylib is
replaced, so Steam's integrity check stays green and there is nothing to undo
but a copied file and a launch-option line.
