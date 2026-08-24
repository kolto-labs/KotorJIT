# What here is reusable, and what is not

Most of this codebase is not about KOTOR. It is about loading code into a running
32-bit process, deciphering a packed image, patching x86, and arbitrating between
scripts — none of which cares what program it is pointed at. Keeping that
separation deliberate means these parts can be lifted into an unrelated project
without carrying a game with them.

The rule: **generic engine, specific data.** Domain knowledge lives in files under
`data/`. Adding a game, a build, an event, or a routine is a data change. If a
new variant needs a code change, the split is in the wrong place.

## Domain-free

These modules mention no game, and would work against any target.

| Module | What it does | Depends on |
|---|---|---|
| `src/image/` | Detect encrypted sections by entropy plus structural markers, wait for an in-process unpacker to finish, re-parse PE32/ELF32 from live memory, verify a digest, dump the result | nothing |
| `src/hooks/trampoline.*` | x86 inline detours with a length disassembler that refuses on anything it does not recognise, relocating relative branches and widening short forms | `src/platform` |
| `src/hooks/registry.*` | Load a table of named addresses, install a set all-or-nothing with rollback, verify expected bytes before patching | `trampoline` |
| `src/platform/` | Page protection, W^X executable allocation, module base lookup, logging | nothing |
| `src/lua/` | Per-script `lua_State`, priority ordering, first-claimant arbitration, error quarantine, hot reload | LuaJIT |
| `src/events/contract.hpp` | The arbitration rule and its vocabulary | nothing |
| `src/proxy/` | A DLL that impersonates another by forwarding its exports and loading something first | nothing |
| `tools/kpdiscover.py` | Locate installed software by content: Steam library lists, platform roots, Windows registry | `data/app_signatures.toml` |

`src/image/` and `src/hooks/` between them are a usable answer to "run my code
inside someone else's packed 32-bit program", which is a problem that has nothing
to do with any particular game.

## Domain-specific, and deliberately data

| File | What it encodes |
|---|---|
| `data/app_signatures.toml` | How to recognise an installed application |
| `data/hooksites.toml` | Which functions to hook, named logically |
| `data/addresses/*.json` | Where those functions are, per build — generated |
| `data/events.toml` | The event contract — what a script can define |
| `data/routines/*.json` | The engine routine table — generated |
| `data/adjudication/` | Hand-established bindings for a stripped build |

## The thin specific layer

Only two places tie the generic parts to this game:

- `src/runtime/hook_bodies.cpp` — the three hook bodies, which have to know the
  real function signatures.
- `src/api/routines.*` — the bridge that pushes arguments onto this VM's stack.

Everything else is either an engine or a table.

## Lifting a module out

`src/image/` and `src/platform/` have no dependency on anything else here.
`src/hooks/` needs `src/platform/`. `src/lua/` needs `src/events/contract.hpp`
and LuaJIT. Copy the directory, keep the include path, and it builds.

If you find yourself adding a game-specific branch inside one of the domain-free
modules, that is the signal to add a field to a data file instead.
