# KotorPhasor: Milestone 1 Plan

**Repo:** `arrenkaetris/KotorPhasor` (AGPL-3.0, **private until release day**)

**Priority order:**

1. **`swkotor.exe`**: the installed Steam K1 build, sha256 `34e6d971…`
2. **`kotor2`**: the installed Steam TSL native Linux ELF, md5 `b3420a36…`
3. everything else in the 24-program `Odyssey` corpus, by data addition
4. Dragon Age ↔ KOTOR cross-matching (blocked; see follow-on at the end)

**Excluded sources: hard constraint:** xoreos, xoreos-tools, KotOR.js, reone, NWNX2 are
neither used nor credited. Every fact they would have supplied comes from `nwscript.nss`,
the recovered `ScriptFunctions` enum, and the recovered C instead.

The primary target's `.text` is encrypted on disk (entropy 7.999). The `image/` module
deciphers and parses it at load time, before any address is resolved. See *Architecture*.

---

## Context

`KotorPhasor` is a native scripting runtime for KOTOR. It injects into the running game,
embeds LuaJIT, and re-exposes the game's own NWScript event and routine surface to Lua.
The shape comes from **Phasor** (urbanyoung's Halo scripting mod): scripts drop into a
folder, define only the event callbacks they care about, and their return values combine
under a documented priority rule to allow or block the underlying game event.

KOTOR modding today means editing NWScript source, recompiling NCS bytecode, and shipping
override files. Slow, static, per-module. No live reload. No way to veto an event the
engine is about to fire. A resident Lua runtime with a full event pipeline turns that
into scripts you can reload while the game is up.

The reverse-engineering corpus already exists locally (see *Verified ground truth*). The
script VM, its dispatch table, its struct layouts, and every per-object event handler are
named and addressed. This is engineering on top of finished RE, not a from-scratch RE
project.

M1 means the runtime loads into both games, runs Lua scripts, delivers real NWScript
events with correct arguments, honours their return values, exposes all 772 K1 engine
routines back to Lua, and is shown working in a live game under headless Wine. Offline
`ctest` covers the host tools. The live-game harness stays opt-in.

`kotor-patch-manager` (Lane Dibello and contributors) is credited in `ATTRIBUTION.md` for
its code caves, injection points, and RE findings, whether or not any of it is reused.
Phasor is credited as the architectural model. `kotorxid` / `biodecompwarehouse` are
credited as the RE corpus.

---

## Verified ground truth

Checked against the binaries, not inferred.

### Three checks that the K1 target is mapped

1. **Page-level:** unpacked Steam `.text` vs GOG `.text`: **828 / 828** 4 KB pages identical.
2. **Address-level:** a separate MIT project (K1SE) independently derived Steam addresses for
   the VM stack accessors: `0x5D1000`, `0x5D1010`, `0x5D1080`, `0x5D1090`: which land on
   *precisely* the GOG addresses `kotorxid` records for
   `CVirtualMachine::StackPop/PushInteger` and `StackPop/PushString`.
3. **Identity-level:** our install's `sha256` is
   `34e6d971…439f34c88`, matching KPM's `kotor1_steam_103` entry byte for byte.

Routine count is likewise triple-confirmed at **772**, using only permitted sources: our
`nwscript.nss` parse, the `ScriptFunctions` enum recovered from the binary itself, and the
binary's own `cmp edx, 0x304` bounds check.

The K1 half of this milestone therefore rests on verified ground, not inference.

### The Steam K1 binary is the GOG binary plus a DRM wrapper

| Fact | Evidence |
|---|---|
| Steam `swkotor.exe` `.text` is **encrypted on disk** | entropy 7.999/8.0 across all 13 chunks; zero `55 8b ec` prologues; zero `cc cc cc` padding |
| Entry point sits in a `.bind` section | EP VA `0x86d2ed`, inside `.bind` @ `0x86d000` |
| An **unpacked** Steam image exists on disk | `agentdecompile/target/swkotor-unpack/swkotor.exe.unpacked.exe`, md5 `bc282fd8…` |
| The packed original **is** our install | `swkotor-unpack/swkotor.exe` md5 `06b34d1b…` == Steam install exe |
| Unpacked Steam `.text` == GOG `.text` | **828 / 828** 4 KB pages identical; same EP VA `0x6fb38d`; same section VAs |

**Consequence:** the 12,041 hand-reversed **GOG addresses apply verbatim to the Steam build
at runtime**, once `.bind` has decrypted `.text` in memory. No rebasing needed for K1.

**Consequence:** hooks **must not** be installed in `DllMain`: `.text` is still ciphertext
then. Installation is deferred until after the stub decrypts (see *Injection*).

### The RE corpus

`db/kotorxid.sqlite`: 600,660 functions, 1.39 M call edges, 5,959 recovered C types.
`db/ghidra_knowledge.sqlite`: full decompiled C + full disassembly + `file_offset` per
function, complete for all 5 Windows builds.
`output/kotor_readable/K1__k1_win_gog_swkotor.exe/`: 129 MB of readable C laid out under
the original BioWare source paths, each function annotated with address, size, prototype.

Coverage by build (`USER_DEFINED` = hand-named by a human):

| build | md5 | hand-RE'd | viable for M1? |
|---|---|---:|---|
| **K1 GOG** (≡ Steam unpacked) | `9a448910…` | **12,041** | **yes: primary target** |
| K2 GOG/Aspyr | `1ffa9299…` | 10,412 | binary not on disk |
| K1 Amazon | `a2620900…` | 4 | no |
| K2 CD 1.0 / 1.0b | `4a318b51…` / `e0fdc77e…` | 0 | on disk, unnamed |

A second, complementary database: `bioware_projects/Andastra/docs/kotor_function_signatures.json`
(28 MB, 49,754 entries, 46,472 with **wildcard byte-pattern signatures**): supplies the
sigscan patterns `kotorxid` lacks. The two together give names+structs+decompiled C *and*
runtime-scannable patterns.

### The script VM: complete map

Engine-routine dispatch is a **runtime function-pointer table**, not inline code:

```c
// CSWVirtualMachineCommands, 16 bytes
struct { void* vtable; int has_caller_object; unsigned long caller_object_id;
         void* commands; };   // commands = 0x304 (772) function pointers

VirtualMachineErrorCodes ExecuteCommand(this, int command_id, int paramCount) {
  if (command_id < 0x304 && this->commands[command_id])
    return (*this->commands[command_id])(this, command_id, paramCount);
  return COMMAND_NOT_FOUND;
}
```
K1 `0x0052C0D0`. **Intercepting any engine routine is a table-entry write, not a code cave.**

The script event entry point:

```c
// K1 0x005D45D0, __thiscall, 459 bytes
int CVirtualMachineInternal::RunScript(
        CVirtualMachineInternal* this,
        CExoString* scriptName,   // e.g. "k_def_heartbeat01"
        ulong       objectId,     // OBJECT_SELF
        int         hasObject);   // returns 1 = ran, 0 = did not
```

Every NWScript event the engine fires funnels through here. One hook yields
name + owning object, the ability to **block** (skip the original) or **observe** the result.

Supporting surface, all named and addressed for K1:

| purpose | symbol | K1 addr |
|---|---|---|
| bytecode interpreter loop | `CVirtualMachineInternal::ExecuteCode` | `0x005D2BD0` |
| delayed/resumed scripts | `CVirtualMachineInternal::RunScriptSituation` | `0x005D4AD0` |
| save / load script state | `SaveScriptSituation` / `LoadScriptSituation` | `0x005D47A0` / `0x005D1100` |
| VM stack marshalling | `StackPop/PushInteger,String,Object,Vector,EngineStructure` | `0x005D1000`–`0x005D10D0` |
| server tick | `CServerExoAppInternal::MainLoop` | `0x004BABB0` |
| client tick | `CClientExoAppInternal::MainLoop` | `0x00602EB0` |
| in-game console | `DoConsole` / `ConsoleFuncs_Add` | `0x00401F00` / `0x0044BA80` |

Per-object typed event handlers (the NWScript event fan-out), all `EventHandler`:
`CSWSCreature` `0x004FECE0`, `CSWSDoor` `0x0058B850`, `CSWSPlaceable` `0x00587BA0`,
`CSWSTrigger` `0x0058F140`, `CSWSModule` `0x004C5120`, `CSWSArea` `0x0050D6C0`,
`CSWSEncounter` `0x00594220`, `CSWSAreaOfEffectObject` `0x005964E0`,
`CSWSStore` `0x005C6EE0`, `CSWSWaypoint` `0x005C7F10`.

### `CScriptEvent` is decoded: typed Lua event arguments are real

This was the load-bearing unknown behind hook #2, and it resolves in our favour.
`CScriptEvent` has a **recovered, size-asserted layout**: the classic Aurora shape:

```c
typedef struct CScriptEvent {           // 0x34 = 52 bytes, static-asserted
  unsigned short event_type;            // +0x00  the event discriminator
  unsigned short field_2;               // +0x02
  unsigned char  int_params   [0xC];    // +0x04  3 ints
  unsigned char  float_params [0xC];    // +0x10  3 floats
  unsigned char  string_params[0xC];    // +0x1C  3 strings
  unsigned char  object_params[0xC];    // +0x28  3 object ids
} CScriptEvent;
```

So a Lua handler can receive **genuinely typed arguments**: discriminated by `event_type`,
payload read from four typed param arrays: rather than only a script-name string. That is
what makes "every typical NWScript event is also a Lua event function" a mechanism instead
of an aspiration.

**Caveat to carry into implementation:** the `EventHandler` family is **not uniform in
signature**, so one shared shim will not do: hook definitions must be per-type:

```c
undefined __thiscall CSWSCreature::EventHandler(CSWSCreature*, int eventType,
                                               int* eventData, CSWSObject* caller);
void      __thiscall CSWSModule::EventHandler (CSWSModule*, ulong, ulong,
                                               void*, ulong, ulong);   // 6 params
```

Each of the ten gets its own verified prototype from the recovered C before it is hooked.

Recovered enums: `ScriptFunctions` (657 K1 / 877 K2 constants), `VirtualMachineByteCodes`
(46 opcodes), `VirtualMachineErrorCodes` (13), `VirtualMachineEngineStructures` (5).
Recovered structs with size asserts: `CVirtualMachineInternal` (984 B),
`CVirtualMachineScript` (40 B), `CVirtualMachineStack` (24 B), `CSWSCreature` (2760 B), …

### The NWScript surface to mirror

Parsed from the canonical `nwscript.nss` headers at
`bioware_projects/odynsscomp/docs/corpus/nwscript/{k1,k2}/`:

- **K1: 772 engine routines** (indices 0–771)
- **K2: 877 engine routines**

Object event slots, confirmed from `CSWSCreature::ReadScriptsFromGff` string xrefs:
`ScriptHeartbeat, ScriptOnNotice, ScriptSpellAt, ScriptAttacked, ScriptDamaged,
ScriptDisturbed, ScriptEndRound, ScriptEndDialogu, ScriptDialogue, ScriptSpawn,
ScriptRested, ScriptDeath, ScriptOnBlocked, ScriptUserDefine`: plus module, area,
trigger, encounter, placeable, door, and minigame slot sets.

### Toolchain

Present: wine 11.0 Staging, Xvfb, xdotool, xvfb-run, luajit, cmake, ninja, meson, gcc,
clang, sqlite3, Ghidra. Also **MSVC 7.1 (`cl.exe` 13.10.3077) inside a Wine prefix** at
`kotorxid/wine_vc71` with driver `scripts/compile-msvc71.sh`: the exact compiler that
produced the game, available if `__thiscall` ABI matching gets fussy.

**Missing, must install:** `mingw32-gcc-c++` (Fedora, 16.1.1, in `updates`). Only the
64-bit MinGW is present; the target is PE32 i386.

---

## Scope: KOTOR 1 Windows + TSL native Linux

Both playable installs on this machine are targeted. Verified identities:

| target | hash | status |
|---|---|---|
| K1 Steam `swkotor.exe` | sha256 `34e6d971…439f34c88` | matches KPM's `kotor1_steam_103` **and** K1SE's `offsets.h` build |
| TSL Steam `kotor2` (ELF) | md5 `b3420a36…`, sha256 `ed043d21…` | matches kotorxid binary #18 **and** KPM's `kotor2_steam_aspyr_linux.db` |

TSL Linux is a **good** injection target: `EXEC` (not PIE) so addresses are fixed, i386,
`.text` at `0x08054940` (~7.2 MB), and KPM already ships four working patches against this
exact ELF. `LD_PRELOAD` plus direct memory patching is the injection path.

### Correcting an earlier overestimate

I initially told the user TSL Linux would require reverse-engineering a stripped ELF from
scratch: "a job the size of the entire K1 runtime." **That was wrong**, and their
pushback was correct. The cross-build unification in `kotorxid` is substantially further
along than that framing assumed.

What the corpus actually contains: 24 binaries across K1, K2, and sibling BioWare engines:

| K2 build | functions | named |
|---|---:|---:|
| Mac | 15,639 | **15,638** |
| Android armeabi-v7a | 40,736 | 38,764 |
| Android x86 (32-bit ELF) | 33,286 | 31,870 |
| GOG/Aspyr Windows | 26,975 | 25,591 |
| Steam/Aspyr Windows | 26,965 | 15,311 |
| **Steam Linux ELF (our target)** | 14,743 | 1,826 |

*"Named" counts every provenance: hand-reversed, propagated, and auto-analysed. On the
Linux ELF specifically, only* **one** *name is hand-reversed; the rest arrived by
propagation. That distinction is what my original overestimate got wrong in both directions:
the hand-RE figure is far lower than 1,826, but the propagation machinery that produced the
rest is exactly what makes the remaining gap closable.*

And the script VM specifically is **already bound across seven K2 builds** through the
`logical_function` / `identity` layer: `RunScript`, `ExecuteCode`, and `ExecuteCommand` all
resolve on Android (all four arches), Mac, GOG Windows, and Steam Windows at confidences of
0.8–1.0. The Linux ELF is the **only** K2 build where they are missing.

The ELF is not blank either: 2,510 logical bindings exist on it, 2,508 with real names,
including `MainLoop` (conf 0.96) and three `EventHandler` instances (conf 0.69–0.93).

### The TSL work is adjudication, and the candidates already exist

`match` run `v1` from `binary 22` (the hand-named K2 GOG anchor) → `binary 18` (our ELF)
holds **12,527 candidate edges**: 93 `auto`, 870 `verify`, **8,918 `review`**, 2,646
`unresolved`. Only ~8% has been adjudicated. **Every VM function we need already has a
proposed candidate sitting in that backlog.**

| function | GOG addr | → ELF addr | score | **margin** | status |
|---|---|---|---:|---:|---|
| `ReadScriptFile` | `00645270` | `083aeb88` | 0.942 | **0.539** | review |
| `EventHandler` | `00687b00` | `084ad196` | 0.865 | **0.491** | **auto** |
| `EventHandler` | `00717360` | `08483176` | 0.746 | 0.381 | verify |
| `EventHandler` | `006648e0` | `08529778` | 0.801 | 0.298 | verify |
| `EventHandler` | `007f59d0` | `0817e6fc` | 0.954 | 0.053 | review |
| `ExecuteCommand` | `0077e5b0` | `08560f2e` | 0.229 | 0.028 | unresolved |
| `RunScript` | `00645540` | `0819f35c` | 0.931 | 0.024 | review |
| `ExecuteCode` | `00645160` | `08195732` | 0.974 | 0.008 | review |
| `GetRunScriptReturnValue` | `00645c50` | `08723910` | 0.987 | 0.005 | review |
| `RunScriptSituation` | `00640b50` | `08465184` | 0.978 | 0.001 | review |
| `RunScript` (`CVirtualMachine::`) | `00640af0` | `08463382` | 0.780 | **0.000** | review |

**Adjudicate on `margin`, not `score`**: that is the operative rule. A 0.997 score with
margin 0.000 means the matcher found many equally good candidates and is telling you
nothing. Filter at margin ≥ 0.05, then verify each survivor by disassembling it and checking
against the K2 GOG readable C.

**One known-degenerate cluster to route around.** Nine distinct stack accessors : 
`StackPop{Command,Float,Integer,Object,String,Vector}` and
`StackPush{Integer,Object,String}`: **all map to the same destination `086abcb0`** at
identical score 0.965, margin 0.000. They are near-identical thin wrappers and the matcher
collapsed them. Second choices are all ~0.67 at margin ≈0, equally useless. These need a
different discriminator: call-site arity from `calledge` (1.39 M rows), vtable slot order in
`CVirtualMachine`, or a targeted BSim query: the ELF has 18 MB of BSim signatures
(`bsim/sigs_b3420a36…`), so that path is live.

**Encouraging precedent:** the same pipeline *did* land `CVirtualMachine::RunScript` on the
K2 Steam Windows build at `006fd8d0` via `match:v1:auto`, confidence 0.90. It works when
score and margin clear the bar.

**Ground truth for validating our adjudication is available.** K2 Mac (94.4% named) and K2
Android x86_64 (93.6%) have the VM fully named. Any ELF binding we accept can be checked
against the structure those builds already confirm: we are not adjudicating blind.

**So TSL is a targeted propagation run, not original RE.** The easiest possible case is
available: `k2_android_x86android` is a **32-bit x86 ELF** with `ExecuteCommand` bound at
conf 0.95 and `ExecuteCode` at 0.95: same architecture, same format as our target. Seed
from there, cross-check against Mac and GOG Windows.

### Consequence for the plan

M1 opens with a **bounded propagation task**: bind ~20 named script-VM entry points onto
binary #18 using the existing `match` (192k rows) / `identity` (288k) / `skeleton_hash`
machinery. Scoped to a specific function list with a specific confidence bar, verified by
disassembling each hit and checking it against the K2 GOG readable C.

Cheap independent anchor already found, to cross-check the propagation: at file offset
`0x54302d` in the ELF sits `inc ecx; cmp ecx, 0x36D; …; jne`: a **877-iteration loop**,
and 877 is exactly TSL's engine-routine count. That is very likely the dispatch-table
initialiser. One anchor, not a map: recorded as a lead, not a conclusion.

**Fallback if propagation underperforms:** ship M1 with TSL injection + Lua host + memory
patching proven, and TSL's NWScript event pipeline explicitly deferred. The K1 half does not
depend on the TSL half.

**Invariant that makes all of this safe:** every address lives in a per-build table keyed by
a runtime hash, never inline in code. Adding or correcting a build is a data change.

### Designed for the whole binary matrix, shipped for two

The user's requirement is that **every binary in the corpus be supported**. The corpus is
24 binaries: K1 and K2 across win / mac / linux / android / ios / xbox, plus sibling BioWare
engines (Jade Empire, `nwmain`, two Eclipse titles) that serve as reference donors.

The runtime cannot *ship* support for platforms whose game we cannot run here, and claiming
otherwise would be dishonest. What it can do: and what this plan commits to: is make
platform support a **pure data question**, so no binary is structurally excluded:

- **Build identity** is a runtime hash lookup, not a compile-time `#ifdef`. Unknown build →
  clean refusal with a diagnostic, never a silent mis-patch.
- **The address table is generated** from `kotorxid`'s `logical_function` / `identity` layer,
  which already spans all 24 binaries. Adding a build means running the generator against
  another `binary_id`, not writing code.
- **Hook sites are named logically** (`CVirtualMachineInternal::RunScript`), never
  numerically. The same hook definition resolves on every build where that logical function
  is bound.
- **Injection is per-platform and pluggable**: PE proxy DLL for Windows, `LD_PRELOAD` for
  ELF, with the abstraction boundary drawn in M1 even though only two implementations land.
- **Endianness / word size / calling convention are table columns**, so a 64-bit ARM Android
  build is a data row rather than a redesign.

M1 ships and verifies **K1 Steam Windows** and **TSL Steam Linux**. Every other build in the
matrix is reachable by adding data, and the generator is written in M1 to prove it: by
emitting tables for builds we cannot run, and asserting they resolve.

K1's VM entry points are already bound across GOG Windows, Amazon Windows, Mac, Xbox, iOS,
and both Android arches, so the K1 side of that matrix is largely populated today.

---

## Architecture

### Layering

```
game process
  └── binkw32 proxy DLL  ── forwards all exports, loads:
        └── kphasor.dll
              ├── image/      ciphertext detection, decipher-wait, runtime image parse
              ├── platform/   VirtualProtect, build identity, deferred init
              ├── hooks/      trampoline engine + hook site definitions
              ├── engine/     typed wrappers over game structs (CExoString, VM, objects)
              ├── events/     dispatcher + result combiner  ← generated from event table
              ├── lua/        LuaJIT host, sandbox, error isolation, hot reload
              └── api/        NWScript routine bindings     ← generated from nwscript.nss
```

### `image/`: ciphertext is deciphered and parsed at load time

**Requirement:** any and all ciphertext must be deciphered and parsed properly at load time.
This is a required module, not a special case bolted onto init, because **three of our
targets are encrypted** and one of them is the primary target:

| binary | `.text` entropy | wrapper |
|---|---:|---|
| **K1 Steam `swkotor.exe`** (primary target) | **7.999** | SafeDisc-style, `.bind` section, EP at `0x86d2ed` |
| `daorigins.exe` | **8.000** | packed, 7,155,712 bytes |
| `DragonAge2.exe` | **8.000** | packed, 8,214,257 bytes |

Reading addresses off the on-disk file for these is meaningless: I confirmed that
empirically: dumping `0x005D0FC0` (`CVirtualMachine::RunScript`) from the Steam file yields
`ae a0 f4 4b 60 1f af c1 …`, high-entropy noise, not x86.

**The pipeline, in order:**

1. **Identify**: hash the file; look up the build record.
2. **Classify each section**: Shannon entropy per section plus wrapper heuristics
   (`.bind` / `.textU` / SteamStub markers). A section over ~7.9 bits/byte with no x86
   prologues and no `0xCC` padding is ciphertext, and is marked as such rather than parsed.
3. **Wait for decipher**: the stub decrypts during its own startup. Poll a sentinel until
   plaintext appears, reads guarded so an unexpected memory state means "not ready" rather
   than a crash. For K1 the sentinel is the dispatcher prologue,
   `8B 54 24 04 81 FA 04 03 00 00` (`mov edx,[esp+4]; cmp edx,0x304`). Bounded timeout, then
   a settle re-check.
4. **Parse the runtime image, never the file**: re-walk headers against mapped memory and
   build the canonical section map from what is actually resident. This matters concretely:
   the on-disk headers can describe the packed layout, and an unpacker rewrites section
   names (`.text` → `.textU`), so a file-derived map is wrong twice over.
5. **Verify the plaintext**: hash the deciphered `.text` and check it against the expected
   value for that build. We already have a known-good anchor: unpacked Steam K1 `.text` is
   **828/828 pages identical** to the GOG build. Mismatch means refuse to install, loudly.
6. **Then, and only then**, resolve addresses and install hooks.

**Optional dump-out.** The same module can write the deciphered image to disk. That is what
makes the "contribute the unpacked Steam K1 image to the `Odyssey` repo" deliverable a
by-product rather than a separate manual chore: and it is precisely the unlock the Dragon
Age dump needs, since DAO/DA2 have the identical problem. Prior art for the mechanism
already exists locally: `agentdecompile/scripts/pe-runtime-code-dump.py` walks
`/proc/<pid>/maps` under Wine and dumps mapped executable regions.

**ELF targets take the same path with a shorter route.** `kotor2` is unencrypted, so
classification finds no ciphertext and steps 3–5 collapse to a hash check: but the code
path is shared, so a future packed ELF is handled without new architecture.

This module is why invariant 3 exists, and it subsumes it: hooks install late *because* the
image is not real until the decipher-and-parse pipeline says so.

### Design invariants (stated, not emergent)

1. **No Lua error reaches game code.** Every callback goes through `lua_pcall`; every hook
   body is wrapped at its top level. A script that throws is logged, and: after a
   configurable strike count: unloaded. The game does not crash.
2. **Addresses are data.** No hardcoded VA in a `.cpp` file. One table, keyed by build.
3. **Nothing is read from a ciphertext image.** All ciphertext is deciphered and parsed at
   load time by `image/` before any address is resolved or any byte is patched. Hooks
   therefore install late: never in `DllMain`: and never against a section still marked
   encrypted. Address resolution reads the **runtime** image, never the on-disk file.
4. **Blocking is explicit.** A hook that blocks must still satisfy the caller's contract
   (correct return value, correct stack discipline, correct `__thiscall` cleanup).
5. **Generated glue is generated.** The event dispatcher, the Lua docs, and the 772 routine
   bindings all come from machine-readable tables. Hand-editing generated files is a bug.
6. **Hook bodies are native C++, never LuaJIT FFI callbacks.** Trampolines call into Lua
   through the C API. FFI is for script-side convenience only. This is not a style
   preference: see below.

### Why hooks must not be FFI callbacks

LuaJIT's FFI callback path is disqualified for hook bodies on four independent counts:

- `__thiscall` is **not a supported callback convention**, and every Aurora engine method is
  `__thiscall`.
- `__stdcall` **must be declared explicitly** on Windows/x86: it cannot be inferred for
  callbacks.
- There is a hard ceiling of **500–1000 concurrent callbacks**, and callbacks created by
  implicit conversion are **never reclaimed**.
- A `"bad callback"` VM **PANIC** fires when a JIT-compiled FFI call re-enters Lua: which
  is exactly the shape of a `MainLoop` or `EventHandler` hook. Callbacks also cost about a
  `lua_pcall`, so a per-object heartbeat hook would be the worst possible place for one.

The x86 concern that does **not** apply: LuaJIT's low-memory allocator constraint is
**x64-only**. On x86 every pointer is 32-bit and the whole space is reachable. The real x86
risk is address-space fragmentation starving LuaJIT's mcode arenas: mitigated by
initialising early (but post-decryption) and by LARGE_ADDRESS_AWARE. Note KPM's `4GBPatch`
already does the latter as a `static` PE-header edit, so it interacts with install order.

### Multi-script return arbitration: Phasor's actual rule

Established by reading Phasor's `scripting::Caller<ResultTypes...>::call`
(`Phasor/Scripts/scripting.hpp`). The rule is **not** "any false blocks":

> **First claimant wins, in script load order. No short-circuit, no veto.**

1. **Every** loaded, non-blocked script is called: even after a winner exists.
2. The **first** script whose returns fully unpack into the event's result types claims it.
   Later successes are silently discarded.
3. On a claim, a synthetic trailing `relevant` argument flips to `false` for all subsequent
   scripts: an advisory "your return will be ignored" back-channel.
4. **Load order is priority.** Persistent scripts load first and therefore outrank map scripts.

"Abstaining" is a *failed unpack*, not a nil check, which produces non-obvious behaviour we
must replicate exactly:

| script returns | outcome |
|---|---|
| `nil` / nothing | abstain |
| non-numeric string | abstain |
| `"5"` for a numeric result | **succeeds** (strtol path) |
| number `2` for a `bool` result | **`false`** (`x == 1` test) |
| partial multi-value tuple | **all-or-nothing**: whole tuple discarded, script abstains |
| any return on a `void` event | **always claims**: scripts 2..N always get `relevant == false` |
| nothing, on an all-optional tuple | **still claims**: merely defining the handler wins it |

When nobody claims, a **per-event fallback** applies: the closest thing Phasor has to a
policy table: `default_true` for most blockable events, `default_false` for
`OnServerCommandAttempt` (the sole fail-closed event), and *identity* for `OnTeamDecision`
(returns its input unchanged).

**Two Phasor defects we fix rather than replicate**: both verified in its source:
- `OnHashValidation` is dispatched but missing from `eventList`, so it is never added to the
  undefined-handler blocklist; every script that doesn't define it throws on every call.
  **Fix:** one generated list is the single source of truth for both dispatch and blocklist,
  making the class of bug unrepresentable.
- Error quarantine is commented out in `ScriptHandler::handleError`, so a script erroring in
  a high-frequency event logs a stack trace forever. **Fix:** strike-count quarantine, on by
  default, per invariant 1.

### The event contract table: the central artifact

A single machine-readable table (`events.toml`) is the source of truth. One row per event:

| column | meaning |
|---|---|
| `name` | Lua callback name, e.g. `OnCreatureDeath` |
| `hook` | which hook site raises it |
| `args` | ordered arg names + types |
| `returns` | result types, or `none` |
| `fallback` | `true` / `false` / `identity` / `none`: applied when nobody claims |
| `blocking` | whether a claimed result can suppress the game action |
| `engine_return` | **what the engine sees when Lua blocks**: see below |

### Blocking and the engine-facing return are different things

`blocking` and `engine_return` are deliberately separate columns, because at the `RunScript`
hook they are not the same decision. `CVirtualMachineInternal::RunScript` returns `int` to
its caller: **1 = ran, 0 = did not**, and `0` propagates into the caller's failure path.

So "Lua returned `false`" is ambiguous unless we resolve it explicitly. We do:

> **Default: blocking suppresses the NWScript handler but reports `1` to the engine.**

Rationale: blocking is meant to be *transparent* to the engine: the event was handled, just
not by the stock script. Returning `0` claims the script failed to run, which invites the
caller's error handling to fire and produces action-at-a-distance bugs that would surface as
"the game behaves oddly weeks later." A script that genuinely wants to signal failure sets
`engine_return` explicitly; it is available, but it is not what a bare `return false` does.

This is invariant 4 ("blocking must still satisfy the caller's contract") made concrete : 
recorded here rather than left for an implementer to guess.

From this one file we generate: the dispatcher glue, the undefined-handler blocklist, the
Lua API reference, and the argument marshalling. Hand-editing generated output is a bug.

**One necessary adaptation.** Phasor's load order comes from its mapcycle; KOTOR has no
such thing. Ordering source must therefore be defined explicitly, or "first claimant"
becomes nondeterministic. Proposal: an optional `priority` number declared by each script,
then filename as tiebreak: fully deterministic, and a superset of Phasor's model.

### Hook sites for M1: verified non-colliding with prior art

The engine-routine table swap is **not** counted as a code cave: it is a data write, and
listing it as one would be dishonest. It remains the highest-leverage single mechanism here:
one table write gives Lua all 772 routines.

`kotor-patch-manager` is **MIT licensed** (Lane Dibello and contributors, 2025), so both
fact reuse and code reuse are permitted with attribution. Its 52 patches occupy **61 distinct
K1 addresses**. Each site below was mechanically checked against that full inventory:
**zero collisions**. Both frameworks can therefore be installed together: which matters,
because KPM's `HookValidator` treats overlapping addresses as a hard install failure.

| # | site | K1 addr | what it enables |
|---|---|---|---|
| 1 | `CVirtualMachineInternal::RunScript` | `0x005D45D0` | every script event: observe, block, override return |
| 2 | `CSWS*::EventHandler` (10-address family) | `0x004FECE0` … `0x005C7F10` | typed per-object events with real args |
| 3 | `CServerExoAppInternal::MainLoop` | `0x004BABB0` | per-tick scheduler, timers, coroutine resume |
| 4 | `DoConsole` | `0x00401F00` | in-game `lua` command; also the headless demo surface |
| 5 | `Save`/`LoadScriptSituation` | `0x005D47A0` / `0x005D1100` | Lua state persisted across save/load |
| 6 | `CSWSModule::LoadModuleStart` | `0x004C9050` | module lifecycle, script reload boundary |

Six candidates for a required five: one can be dropped without missing the bar.

**Honest distinction on #4.** KPM's *AdditionalConsoleCommands* also adds console commands,
but by a different mechanism (detour at EXE entry `0x006FB4CE`, then `ConsoleFuncs_Add`
registration). Hooking `DoConsole` itself is genuinely different in capability, not just in
address: it intercepts the whole input line including commands the game does not recognise,
which registration-based extension cannot do. Stated plainly rather than claimed as novel.

**Interoperation note.** KPM's *ScriptExtender* expands the VM command array 772→1000
(`0x0054C964`, `0x0052C0D4`) and initialises it via a detour at `0x005CD6F6`. Since we write
table *entries* at runtime rather than patching the table's bounds, the two compose: but
the runtime must detect KPM's presence and read the actual bound rather than assuming 772.

### Ideas worth adopting from prior art

- **From Phasor:** the load-time "which callbacks does this script actually define" blocklist.
  Undefined handlers then cost one hash lookup, not a `lua_getglobal`: which is what makes a
  per-tick event affordable for scripts that ignore it.
- **From KPM:** hook description *as data*: declared address + type + `original_bytes`
  verification + SHA-gated per-version files, with cross-patch conflict validation at install
  time. We adopt the same shape, and mirror its `requires` / `conflicts` vocabulary so the two
  ecosystems' patches can coexist.

---

## Milestone 1: definition of done

1. **TSL adjudication pass**: the VM entry points bound on `binary 18` from the existing
   12,527-edge `review` backlog, filtered on margin ≥ 0.05, each survivor verified against
   the K2 GOG readable C, with the degenerate `StackPop*`/`StackPush*` cluster resolved by a
   separate discriminator. Accepted bindings written back to `identity`, so the work
   benefits the corpus and not just this project.
2. **`image/` deciphers and parses at load time**: encrypted sections classified, decipher
   awaited, runtime image parsed, plaintext `.text` hash-verified against the known-good
   anchor, and installation refused on mismatch. Demonstrated on the encrypted K1 Steam
   build and on the unencrypted TSL ELF through the same code path. Dump-out produces a
   clean image suitable for re-import.
3. Address tables generated from `kotorxid` for K1 Steam Windows and TSL Steam Linux, with
   build identity verified at runtime by hash.
4. Runtime injects into both targets and survives to the main menu with hooks installed.
5. LuaJIT host loads scripts from a directory, with hot reload and per-script isolation.
6. **Five code caves live on K1**, named explicitly so nothing is ambiguous:
   1. `CVirtualMachineInternal::RunScript` `0x005D45D0`
   2. the `CSWS*::EventHandler` family: **counts as one cave**, ten sites, per-type prototypes
   3. `CServerExoAppInternal::MainLoop` `0x004BABB0`
   4. `DoConsole` `0x00401F00`
   5. `Save`/`LoadScriptSituation` `0x005D47A0` / `0x005D1100`

   `CSWSModule::LoadModuleStart` `0x004C9050` is the spare sixth, dropped without penalty.
   The 772-entry routine-table swap is delivered too, but is **not counted** as a cave: it
   is a data write.
7. Lua receives real NWScript events with typed arguments decoded from `CScriptEvent`,
   verified field by field against the recovered C prototypes.
8. Return arbitration demonstrably matches the documented rule, proven by loading N scripts
   that return conflicting values for the same event: including the awkward cases
   (`nil`, non-numeric string, `"5"`, number `2` for a bool, partial tuples).
9. Lua can call NWScript engine routines: all 772 on K1: through the generic bridge.
10. A script error cannot crash or hang the game.
11. Live demo under headless Wine driving the game through the console.
12. **Example scripts in `scripts/`**, each with its inline terminal command, covering:
    argument correctness per event, every return-arbitration case, priority ordering, and a
    deliberately-erroring script that proves quarantine works. These are the artifact that
    *demonstrates* items 7–10 rather than asserting them.
13. `ATTRIBUTION.md` complete and accurate.

No tests are written in M1, per the stated sequencing: functionality is confirmed in the
headless harness first, and the `scripts/` corpus from item 12 becomes the basis of the
automated suite in M2.

## Status (2026-08-30)

M1 is **not closed**. Host gates are green. All five PLAN-M1 caves have fired in a
live `swkotor` process. Tier 2 console drive still needs the splash-wait so
DoConsole/OnSave are not typed into the LOADING bar.

**TSL fallback (taken):** inject and resolve VM sites on `k2_steam_linux`; skip
`console.do_console` when unresolved; EventHandler/save/load install when the table
binds them. Typed TSL events are not separately proven.

### What landed
- Five caves wired and live-fired (15 hooks). Load body is three
  stack args / `ret $0xC` (not one / `ret $4`); hook stays on the
  `0x005D1100` thunk. Cave-reality drive 2026-08-30 14:15: `DRIVE_EXIT:0`,
  gameplay at t+5s, `[probe] OnLoad x1`, no Wine fault at `0x41168A`.
  `kp_eventtest` 0 failures (`Load probe emits ret $0xC`).
- Landed (same day, 14:42): splash-wait in `scripts/harness/ui_wait.sh`.
  Cave-reality drive `DRIVE_EXIT:0`: splash gone at t+13s (`#004874`,
  69638 colours), `console smoke ok`, `status: phase=running live=yes`,
  `[probe] console:warp end_m01aa`, `[probe] OnSave x1`. All five caves
  now have unique live lines in one 15-hook session.
- Partial: EventHandler argument values still host-proven more than
  live-asserted; K2 Aspyr still has no `expected_bytes`.
- Next: coverage harness Layer 1 (`scripts/harness/coverage.sh`) is the
  modder soft-lock loop; reply-pick cave and campaign walker are Layer
  2–3: see `docs/coverage-harness.md`. External: `arrenkaetris` git
  access, Odyssey Steam-image deposit.

## Verification: tiered, so partial failure doesn't block everything

Deliberately staged because the riskiest dependency (D3D8 under llvmpipe) is also the one
that gates the least.

- **Tier 0: no rendering.** Load the runtime under Wine; confirm build identity; confirm
  `image/` classified `.text` as ciphertext, awaited decipher, parsed the runtime image, and
  matched the plaintext hash to the known-good anchor; confirm every hook site's expected
  prologue bytes match; install and uninstall hooks cleanly. Also confirm the **negative**
  case: a deliberately corrupted plaintext hash must refuse installation rather than proceed.
  Evidence: log file plus a dumped plaintext image diffed against the GOG `.text`.
- **Tier 1: headless, no display.** Boot to a state where scripts run; confirm Lua
  receives real events with correct arguments; confirm each `combine` rule empirically by
  loading N scripts that return conflicting values. Evidence: structured log + a dumped
  argument trace compared against the recovered C prototypes.
- **Tier 2: headless with virtual display and input.** `Xvfb` + `xdotool`, drive the game
  to the main menu and into a module, open the console, type `lua`-prefixed commands, and
  observe effects. Evidence: screenshots + log.

**Step 0, before any C++ is written:** prove `swkotor.exe` reaches the main menu under
`Xvfb` + Wine and that `xdotool` can drive it. `LIBGL_ALWAYS_SOFTWARE=1`, windowed mode,
`Xvfb -screen 0 1024x768x24`; fall back to the Xorg dummy driver if llvmpipe won't cope.
If Tier 2 proves impossible, that is discovered on day one, not after the runtime is built.

**Test against a pristine install.** The Steam install carries **5,918 Override files**;
mod bugs and framework bugs would be indistinguishable. The harness `rsync`s a clean copy.
A vanilla reference already exists at `MyBook/kotor_vanilla_refs/K1_vanilla/`.

---

## Prerequisites

1. **GitHub access as `arrenkaetris`.** Current `gh` auth is `bodencrouch`, which cannot
   resolve the target repo. Resolve before anything else: it gates delivery. Repo stays
   **private**; all work lands via `git` + `gh` against the private remote.
2. **Reconcile the three MizuchiRE copies** into one authoritative tree before anyone reads
   "the recovered source": they currently disagree (771 vs 430 files for K1 GOG).
3. **Contribute the unpacked Steam K1 image** to the `Odyssey` Ghidra repo (13300), closing
   a gap `PLAN.md` records as unmatchable.
4. `sudo dnf install mingw32-gcc-c++ mingw32-binutils glibc-devel.i686 libstdc++-devel.i686`
  : 32-bit Windows cross toolchain plus the 32-bit host libs LuaJIT's cross-build needs.
5. **Build LuaJIT v2.1 for `i686-w64-mingw32`**:
   `make HOST_CC="gcc -m32" CROSS=i686-w64-mingw32- TARGET_SYS=Windows`
   Host and target pointer sizes must match: hence `-m32` and the `.i686` packages above.
   Link `libluajit-5.1.a` statically into the runtime rather than shipping `lua51.dll`.
   For the Linux target, a native 32-bit LuaJIT build.
6. Working tree at `/run/media/brunner56/MyBook/Workspaces/KotorPhasor` (1.2 TB free).
7. **Pristine game copies** for the harness. The K1 Steam install carries 5,918 Override
   files; a vanilla reference already exists at `MyBook/kotor_vanilla_refs/K1_vanilla/`.

---

## Repository and licence

**Repo:** `arrenkaetris/KotorPhasor`, **AGPL-3.0**: confirmed by the user as theirs and
correct. It currently holds only `.gitignore`, `LICENSE`, `README.md`.

**Access blocker to resolve before first push:** `gh` is authenticated as `bodencrouch`,
and that token **cannot resolve `arrenkaetris/KotorPhasor`** (GraphQL "Could not resolve").
A second account, `oldrepublicwizard`, is present with an invalid keyring token. Working
push access as `arrenkaetris` must be established first: otherwise the entire delivery path
is blocked at the end rather than the start.

**Visibility: the repo stays PRIVATE until release day.** No public pushes, no public
issues, no public CI artifacts. All `gh` work targets the private repo.

### Excluded prior art: a hard constraint

**xoreos, xoreos-tools, KotOR.js, reone, and NWNX2 are excluded.** Not credited, not read
for transcription, not used as a source. Any implementer who reaches for
`game_kotor.h`, `NWScriptDefK1.ts`, `routines.cpp`, or the NWNX Lua plugin is off-plan.

This costs us nothing, because every fact those projects would have supplied is available
from sources we already control:

| need | excluded source we are **not** using | what we use instead |
|---|---|---|
| routine ID → name → signature | xoreos-tools `game_kotor.h` | **`nwscript.nss`**: BioWare's own header, at `odynsscomp/docs/corpus/nwscript/{k1,k2}/`. Already parsed and verified: **772 K1 / 877 K2** |
| routine ID enum | xoreos-tools | **`ScriptFunctions`** enum recovered from the binaries themselves in `kotorxid.ghidra_type` (657 K1 / 877 K2 constants) |
| routine semantics | KotOR.js | the recovered readable C for `nwvmachinecommands.cpp` (958 KB): the game's own implementation |
| VM model, opcodes, error codes | reone | `VirtualMachineByteCodes` (46), `VirtualMachineErrorCodes` (13), `VirtualMachineEngineStructures` (5): all recovered from the binaries |
| Lua-in-Aurora precedent | NWNX2 | our own design, informed by Phasor's architecture |

Routine counts are independently triple-confirmed without any excluded source:
our `nwscript.nss` parse, the recovered `ScriptFunctions` enum, and the binary's own
`cmp edx, 0x304` bounds check all agree on **772** for K1.

Remaining permitted prior art: **kotor-patch-manager** (MIT) and **K1SE** (MIT), used under
the "independent, borrow designs" decision, and **PyKotor** (LGPL-3.0), already a local
project. Phasor (MIT) remains the architectural model.

One licence note to carry deliberately: AGPL-3.0's network clause is essentially inert for
an injected game DLL, but it does constrain anyone embedding KotorPhasor in a hosted
service. Worth one line in the README rather than a surprise later.

## Attribution

`ATTRIBUTION.md` at repo root, written before any hook code lands:

- **kotor-patch-manager** (Lane Dibello and contributors, MIT, 2025): credited for its code
  caves, injection points, hook-as-data design, and published RE findings for K1 and K2.
  Individual patch authors are named per its manifests: Lane, Vriff, J, Synchro, VexFlint,
  Shae Condon, Arniel_Stanislaus. MIT copyright lines retained on anything reused.
- **K1SE** (MIT): credited for the Steam-build DRM-wait pattern and its published offsets.
- **Phasor** (urbanyoung, MIT): credited as the architectural model for the scripting
  pipeline, the event surface, and the return-arbitration rule.
- **kotorxid / MizuchiRE / the `Odyssey` Ghidra repo**: the RE corpus this is built on.
- BioWare / Obsidian / LucasArts / Aspyr: unaffiliated-fan-work disclaimer; no game assets
  are redistributed.

Not listed, by instruction: xoreos, xoreos-tools, KotOR.js, reone, NWNX2. They are excluded
as sources, so there is nothing to credit: see *Excluded prior art*.

## Injection

**K1 Windows: `binkw32.dll` proxy.** The community standard, and the only vector that works
uniformly across native Windows and Wine/Proton. Both games *statically* import `binkw32`,
and under Wine there is no builtin, so the loader picks ours from the game folder before the
entry point runs. The proxy forwards all **59 Bink exports** declaratively via a `.def`
(the union of K1 and K2 export sets: one proxy serves both), renames the original, and its
`DllMain` does nothing but `LoadLibrary` the runtime. An export-name list is interoperability
data, not copyrightable expression, and no RAD binary is redistributed.

Rejected alternatives, with reasons: `Mss32.dll` proxy works but is imported later with a
larger export surface; launcher-based injection breaks under Proton (a native Linux launcher
cannot inject into a Wine process); there is no ASI loader in a stock KOTOR install.

**One premise corrected:** TSL's `binkawin.asi` is **not** an ASI-loader plugin. It sits in
`miles/` and is a *Miles Sound System* codec (`.asi` = Audio Stream Interface): the Bink
Audio decoder, loaded by `Mss32.dll`. Name collision with the GTA-modding convention.

**TSL Linux: `LD_PRELOAD`.** The ELF is `EXEC`, not PIE, so addresses are fixed and no
rebasing is needed. Only 105 defined `FUNC` dynamic symbols exist, so interposition is not
the mechanism: the preloaded `.so` patches memory directly at known addresses.

### The deferred-install requirement, independently confirmed

Hooks must not install in `DllMain`. My entropy analysis showed Steam K1's `.text` is fully
encrypted on disk (7.999/8.0, zero x86 prologues); K1SE reached the same conclusion from the
other direction and solves it by polling: 50 ms cadence, 120 s timeout, plus a +100 ms
re-check to confirm settling: until the dispatcher's first ten bytes match a sentinel:

```
8B 54 24 04 81 FA 04 03 00 00     ; mov edx,[esp+4] ; cmp edx, 0x304
```

with the read wrapped in SEH so an unexpected memory state reads as "not ready yet" rather
than crashing. We adopt that pattern, generalised: **wait for build identity to verify, then
install.** Each hook site additionally verifies its expected prologue bytes before patching,
and the runtime **refuses to install** on mismatch rather than installing inert.

## Open items

- **`arrenkaetris/KotorPhasor` access.** Our `gh` token is `bodencrouch` and cannot resolve
  the repo; the account shows no public repos, consistent with it being private: which is
  where it stays until release. Push access as `arrenkaetris` must be established at kickoff.
- Whether the TSL propagation pass clears its confidence bar for all VM entry points, or
  whether the M1 fallback (TSL injection proven, TSL events deferred) applies.

---

## Resolved: "the ghosts project" is the `Odyssey` Ghidra Server repo

Dictation for *Ghidra's project*. It is live right now: `java` pid 4080000, serving
**13300/13301/13302**, launched with `-Dkotorxid_server=1` from the `kotorxid` working
directory. Three independent artifacts list the **same 24 programs** byte for byte:
`repos/_odyssey/~index.dat`, `MizuchiRE/reports/inventory.json`, and
`kotorxid/scripts/programs.txt`: matching the 24 rows in `kotorxid.sqlite.binary`.

So "support all the binaries in the ghosts project" = **the 24-program `Odyssey` corpus**,
which is exactly what the data-driven address design was already built for.

**Four gaps worth naming**, because they are cells the corpus does *not* contain:

- **K1 Windows Steam is not in the repo**: `MizuchiRE/PLAN.md` dismissed it as SecuROM
  ciphertext (`.text` entropy 8.000). **But it is our primary target, and we have solved
  it**: `agentdecompile/target/swkotor-unpack/swkotor.exe.unpacked.exe` is the unpacked
  image, verified 828/828 pages identical to the GOG build. **Contributing the unpacked
  Steam image back into the `Odyssey` repo is an M1 deliverable**: it closes a gap the
  warehouse currently records as impossible.
- K1 Windows CD (retail), K1 native Linux, K2 Windows Amazon: no binary present.
- Both `.xbe` images are `RECONSTRUCTED-NOT-BYTE-EXACT` (loaded image, no original bytes).

## Resolved: where the Mizuchi data is

Two distinct things share the name, which is the source of the confusion:

| | what | where |
|---|---|---|
| **Mizuchi** (the tool) | "Decomp Atlas": running now, `node` pid 3377461, **ports 3011** (built UI) and **5173** (Vite dev) | `kotorxid/vendor/mizuchi-build/` |
| **Mizuchi data** | 16 GB of projects, plus atlas output: and the atlas already has a `TSL__k2_linux_swkotor2.elf` entry | `kotorxid/output/mizuchi_projects/` (16 G), `output/mizuchi/` (177 M), `output/atlas/` (148 M), `data/mizuchi_home/` (11 M) |
| **MizuchiRE** (the effort) | matching decompilation: recompile to byte-identical code | `ai-projects/MizuchiRE/` is the **live git repo**; `/home/brunner56/Workspaces/MizuchiRE` is a partly-diverged working copy (771 vs 430 recovered files for K1 GOG); `MyBook/Workspaces/MizuchiRE` is the stale `$R` from `PLAN.md` |

Also found on the named ports: **8791 + 8173** = `kotorxid/scripts/dashboard.py` (coverage
dashboard, `python` pid 4158408). **3050** = an MCP gateway, unrelated to RE.

**Reconciling the three MizuchiRE copies is a prerequisite task**: right now
"the recovered source" means three different things depending on which path you open.

## New follow-on: Dragon Age ↔ KOTOR cross-matching

Requested, and it is a real gap: `daorigins.exe` (id 12) and `DragonAge2.exe` (id 11) have
**zero `identity` bindings and zero `match` edges**: the only two programs in the corpus
with nothing at all.

**Two blockers must be cleared before any matching can happen, and neither is optional:**

1. **Both binaries are DRM ciphertext.** `MizuchiRE/reports/entropy.json` records
   `daorigins.exe .text` = entropy **8.0** over 7,155,712 bytes and `DragonAge2.exe .text` =
   **8.0** over 8,214,257 bytes, both flagged `ENCRYPTED/PACKED`. Their high `named_count`
   (8,419 and 12,066) is import thunks and packer stub, not game code. **There is currently
   nothing to match against.**
2. **Neither binary is on disk**, and there is no Dragon Age install in the Steam library.

**The `image/` module does this at load time.** The `image/` module deciphers and parses
ciphertext at load time and can dump the plaintext image: which is exactly what DAO and DA2
need. Their blocker is the same one the primary target already forced us to solve, so this
follow-on reduces to: obtain the games, run them under the runtime, take the dump, re-import
to Ghidra, *then* match. `agentdecompile/scripts/pe-runtime-code-dump.py` is the existing
standalone equivalent and a useful cross-check.

Blocker 2 (not on disk, no install) remains a genuine prerequisite and is not something the
plan can resolve on its own.

**One expectation to set honestly:** Dragon Age is the **Eclipse** engine, not
Aurora/Odyssey. Cross-matching will mostly surface shared CRT, math, and container code
rather than gameplay classes. The far better bridge is **Jade Empire**: Aurora-derived,
already plaintext (entropy 6.497), already in the corpus, and currently sitting at **62
bound identities out of 15,987 functions**. If the goal is engine-lineage coverage, Jade
Empire is where the same effort buys the most.

**Sequencing:** this follow-on is **after** the two priority targets, and it does not gate
them. It is tracked here because it was requested, with its blockers stated up front rather
than discovered later.
- Whether the TSL propagation pass clears its confidence bar for all ~20 VM entry points, or
  whether the M1 fallback (TSL injection proven, TSL events deferred) applies.
