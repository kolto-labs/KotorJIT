# Unresolved, and what would settle it

Every function on the commissioned target list has an accepted binding. What follows is
residual risk and work that would raise confidence or extend coverage, ordered by how much
it matters to KotorPhasor.

## 1. RESOLVED: the two bindings that lacked a vtable cross-check

`CSWSArea::EventHandler` = `0x08483176` and `CSWSModule::EventHandler` = `0x08541674` were
initially the weakest accepted bindings, because neither address occurs as a dword anywhere
in the file, while every vtable-confirmed binding occurs exactly once.

That is now explained rather than merely tolerated. Both functions are **non-virtual**: each
has exactly one direct caller on binary 18, and it is the *same* caller for both,
`0x085c0038`. On mac both likewise have exactly one caller and it is the same function,
`CServerAIMaster::UpdateState` at `0x003dc3ce`. The caller shapes agree closely:

| | size | n_blocks | n_callees | cyclomatic |
|---|---|---|---|---|
| binary 18 `0x085c0038` | 1851 | 71 | 19 | 48 |
| mac `CServerAIMaster::UpdateState` | 1747 | 72 | 19 | 48 |

A non-virtual function is in no vtable, so zero dword references is the expected result, not
a warning sign. Both entry points were additionally disassembled and carry real prologues
(`push ebp; push ebx; push edi; push esi; sub esp,0xac` and `push ebx; push edi; push esi;
sub esp,0x30`), ruling out the failure mode where Ghidra's function start is a GCC exception
landing pad and the hook address is silently 0x12-0x30 bytes early.

Confidence raised to 0.96 and 0.95.

**Incidental result:** `CServerAIMaster::UpdateState` on binary 18 is `0x085c0038`. It was
not adjudicated as a target and is recorded here only as a lead.

## 2. `CSWSSoundObject::EventHandler` is the one insufficient_evidence verdict

`0x0858033e`, a bonus target not on the required list. Only one signal supports it - vtable
slot 31 - which does not meet the two-independent-signal rule applied to everything else.
Disassembly shows a bare `ret` followed by `nop` padding and a fresh prologue at
`0x08580340`. The likely reading is identical-code-folding on an empty virtual override,
which would make `0x0858033e` the folded tail byte of the preceding function. Likely is not
established, so the verdict is `insufficient_evidence`.

**What would settle it:** check whether other classes' vtables point at the same address; if
several empty overrides share it, folding is confirmed and the binding is harmless but also
meaningless to hook.

## 3. Ghidra's analysis of binary 18 has substantial coverage gaps

Nine of the accepted bindings are at addresses with **no `func` row at all** on binary 18:

| function | ELF address |
|---|---|
| `CSWVirtualMachineCommands::ExecuteCommand` | `0x085b878e` |
| `CSWVirtualMachineCommands::InitializeCommands` | `0x0858b002` |
| `CSWSDoor::EventHandler` | `0x0850cc24` |
| `CSWSPlaceable::EventHandler` | `0x08562518` |
| `CSWSTrigger::EventHandler` | `0x085863aa` |
| `CSWSEncounter::EventHandler` | `0x08524b92` |
| `CSWSAreaOfEffectObject::EventHandler` | `0x08582264` |
| `CSWSWaypoint::EventHandler` | `0x0858a54c` |
| `CSWSSoundObject::EventHandler` | `0x0858033e` |

This is why the brief's premise that "every function we need already has a proposed candidate"
did not hold: for these the matcher had no destination to propose, so it was forced onto
nearby unrelated functions. It also means `binary.func_count = 14743` understates binary 18,
and any future run over this corpus inherits the same blind spots.

**What would settle it:** re-run Ghidra analysis on binary 18 with aggressive function
recovery (Decompiler Parameter ID, and seeding entry points from the RTTI vtables, which are
fully intact in `.rodata`). Every vtable slot is a guaranteed function entry; there are
thousands of them and they cost nothing to harvest. Re-import, then re-run the matcher.

## 4. Function extents are measured for entries, not always for sizes

For the nine gap functions above, the *entry* address is measured (prologue disassembled and,
where the function is virtual, confirmed as a vtable dword). The *extent* comes from
control-flow component analysis, which over-merges when a function tail-calls into shared
code. `InitializeCommands` reported 309,040 bytes, which is certainly wrong; `CSWSEncounter`
reported 1194 and manual reading of the terminating `ret` gave 325 against mac's 338.

For hooking purposes only the entry matters, so this does not block KotorPhasor. It does mean
the `size` field should not be trusted for those nine.

**What would settle it:** parse `.eh_frame` / `.gcc_except_table`, which give exact FDE ranges
per function. The ELF is not stripped of unwind data.

## 5. BSim was deliberately not used

`/home/brunner56/biodecompwarehouse/kotorxid/bsim/` holds an 18 MB signature set including
`sigs/TSL__k2_linux_swkotor2.elf` and an H2 database `kotor.mv.db` (334 MB). It was not
queried: standing up Ghidra's `bsim` CLI against H2 is a substantial time cost, and strings,
`consts`, RTTI and the type-code immediates already produced disassembly-grade evidence.

**Where it would still add value:** as a genuinely independent fourth opinion on items 1 and 2
above, and as a bulk method for extending beyond the VM. It is the natural next tool, not a
gap in the current result.

## 6. Not investigated (out of scope for this commission)

- `CVirtualMachineStack::*` (`CopyFromStack`, `SaveStack`, `LoadStack`, `AddToTopOfStack`,
  `SetStackPointer`). `AddToTopOfStack` is incidentally pinned at `0x0846539c` - every
  confirmed `StackPush*` calls it - but the rest were not adjudicated.
- `CVirtualMachineInternal::SetUpScriptSituation` (`0x08468734`),
  `DeleteScriptSituation` (`0x08468e7e`), `SetCommandImplementer` (`0x08468ea0`),
  `DeleteScript`, and the constructors. These fall inside the confirmed TU block and their
  positions follow from the same isomorphism, but they were not on the target list and carry
  no individual verification here.
- The 877 command-handler table contents. `InitializeCommands` writes each entry as
  `[table + i*8] = {member_fn_ptr, this_adjustment}`; reading the table out would name all 877
  `ExecuteCommandXxx` handlers on binary 18 in one pass, cross-checked against the
  `nwscript.nss` routine order. That is the single highest-yield follow-up in this corpus and
  it is now unblocked, because both the initialiser and the table member offset are known.
- Whether these addresses are stable across Aspyr Linux patch revisions. Only md5
  `b3420a36a4385fec8189f37c5d5eaad1` was examined. KotorPhasor should gate on that md5, or
  re-derive at load time from the RTTI vtables, which is cheap and version-independent.
