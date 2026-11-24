# Coexisting with other mods' hooks

Hyperstim is not the only thing that patches KOTOR in memory. Some known examples:

| Module | What it patches |
|---|---|
| K1SE (`binkw32.dll` proxy) | MinHook detour on `CSWVirtualMachineCommands::ExecuteCommand` (K1 Steam `0x0052C0D0`), to add NWScript routines |
| KPM | rewrites ExecuteCommand's `cmp edx, 0x304` bound to grow the routine table |
| overlays, injectors, future mods | any function they need |

Each of these works the same way: it overwrites a function's first instructions with a jump to its own code, then copies the displaced instructions into a trampoline that jumps back. Before this change, Hyperstim refused any site whose first bytes differed from its address table, and it refused the whole image if the code section's hash differed. So "another mod got there first" meant "Hyperstim does not start".

The code is in `src/hooks/foreign.{hpp,cpp}`, used by `src/hooks/registry.cpp`, `src/runtime/runtime.cpp` and `src/api/enginestruct.cpp`. The tests are in `tools/kp_foreigntest.cpp`.

## Policy

| `foreign_patches` | Behaviour |
|---|---|
| `chain` (default) | A patched site is bound if the evidence below holds. Hyperstim hooks in front of the other mod. |
| `refuse` | Exact bytes only, the old behaviour. Use it to rule a conflict in or out. |

Set it with `foreign_patches = …` in `hyperstim.ini`, or with `HYPERSTIM_FOREIGN_PATCHES` (which wins). The legacy `KOTORPHASOR_FOREIGN_PATCHES` also works.

## When is a patched site still "the right function"?

The resolver tries these in order. The log records which one bound each site.

| | Evidence | Needs |
|---|---|---|
| A | **exact**: recorded bytes untouched | (unchanged path) |
| B | **stub + tail**: a recognised detour stub at the head, and the original bytes after the displaced instructions intact | at least `kMinTail` (6) original bytes |
| C | **relocated prologue**: a stub at the head, and the displaced original instructions found in private executable memory (where hooking libraries allocate trampolines), followed by a jump back to exactly `site + boundary` | an exact copy (MinHook, Detours, PolyHook, funchook and subhook all leave one) |
| D | **build-bound**: a stub at the recorded address of an address table that the executable's own sha256 selected | a recorded VA. Never used for a scan hit |

Evidence that never binds a site:
- a head that is not a recognised stub;
- a changed byte after the displaced instructions;
- garbage between the stub and the next original instruction (only original bytes or `CC`/`90` filler are allowed);
- a site whose original code itself starts with a jump.

Without a usable recorded VA, the site is found by scanning for the surviving tail (unique or nothing), for each head length a stub can have, and is then proven with B or C. Hook-manifest sites get the same treatment with their masked patterns, but only when the pattern had **no** hit. "Ambiguous" is never rescued.

Recognised stubs: `jmp rel32`, `jmp rel8`, `jmp [abs32]`, `push imm32; ret`, `mov r32, imm32; jmp r32`, and on x86-64 `jmp [rip+disp32]`, the 14-byte `jmp [rip+0]; dq abs64` and `mov r64, imm64; jmp r64`.

## What Hyperstim does with a patched site

- **Reference / call sites** (`vm.execute_command`): the live, patched entry is used as-is. Routine calls go through the other mod's detour, so its features keep working (K1SE's extra routines live in that detour). Bypassing it through the trampoline would break them.
- **Detour sites:** chain. Hyperstim's engine moves whole instructions into its trampoline and re-aims relative jumps, so the other mod's stub moves into Hyperstim's trampoline intact. Execution then runs Hyperstim → other mod → original, whichever was installed first. Uninstalling puts the other mod's stub back exactly. If the other stub is shorter than Hyperstim's jump (5 bytes on i386, 14 on x86-64), the bytes after it must be filler, or the site refuses with a message naming the other module.
- **The dispatcher bound** (`cmp edx, imm32`, which KPM grows) is read from the relocated original prologue (evidence C) when one is found. It is never decoded out of the other mod's jump. Without a copy, i386 falls back to the stock/table bound and logs that grown slots are unreachable. x86-64 uses the table's verified count.
- **The code-section hash:** when the build was identified by the executable's own sha256, the image sits at its preferred base, and only the in-memory code differs, startup continues under `chain` with a log line saying why. Every site is then verified individually before a byte is written. Any other mismatch still stops.

## Order of loading

Hyperstim does not patch `ExecuteCommand`, so K1SE can hook it before or after Hyperstim resolves it.

For detour sites, both orders chain:
- **Hyperstim first:** a trampoline-based hooker relocates Hyperstim's `jmp rel32` like any other instruction.
- **The other mod first:** this document.

## Known limits

- **A hooker that leaves no exact trampoline copy.** If the original head was rewritten (a relative branch re-aimed, or instructions substituted) and the surviving tail is thinner than 6 bytes, the site binds only through D (recorded VA). It can't be found by scan alone.
- **Unhooking by byte restore.** A mod that later rips Hyperstim's jump out by writing back the bytes it saw is not detected after startup.
- **Mutual-exclusion order on the same proxy.** K1SE and Hyperstim both ship as `binkw32.dll`, forwarding to `binkw32_real.dll`, so today they cannot both be installed in one game folder. This document covers the in-memory half of coexisting. Loading both still needs one proxy that loads the other.
