# Method: binding the KOTOR 2 script VM onto the native Linux ELF

Target: `binary_id = 18`, `TSL__k2_linux_swkotor2.elf`, md5 `b3420a36a4385fec8189f37c5d5eaad1`.
Corpus: `/home/brunner56/biodecompwarehouse/kotorxid/db/kotorxid.sqlite` (opened read-only throughout, `file:...?mode=ro`).
Raw image: `/home/brunner56/biodecompwarehouse/kotorxid/extract/raw/TSL__k2_linux_swkotor2.elf`.

Result: 55 accepted bindings, 45 rejected matcher proposals, 1 insufficient_evidence.
All 46 required target functions are accepted; the single insufficient_evidence verdict is a
bonus target that was not on the required list.

## 1. Calibrate the matcher before trusting any of it

The `match` run `v1` from binary 22 into binary 18 has ~12,527 edges. Binary 19 (mac) is
fully named, so run `v1` from 22 into 19 has a knowable answer. Measuring name agreement
there, bucketed by `margin`:

| margin | strict agreement | agreement allowing namespace noise |
|---|---|---|
| 0.000 | 8.9% | 10.2% |
| 0 - 0.01 | 15.9% | 17.3% |
| 0.01 - 0.05 | 31.2% | 33.9% |
| 0.05 - 0.15 | 75.1% | 81.0% |
| 0.15 - 0.30 | 84.8% | 91.4% |
| 0.30+ | 71.0% | 89.2% |

The 0.30+ dip under the strict oracle is oracle noise, not matcher error: `canon_key`
records `LoadSpellsTable` vs `CSWClass::LoadSpellsTable` as a disagreement. The loose
column is the fair reading.

**Consequence: run v1 alone can never justify `accept`.** Even the best bucket is ~90%,
and a wrong binding silently hooks the wrong function. The rule used here is:

> accept requires at least two independent signals, at least one of which is not run v1.
> Injectivity is enforced across the final set.

Of the 56 accepted bindings, run v1 agrees with 8. The other 48 were found without it.

## 2. Discriminators that worked

**a. Unique string literals (strongest single signal).** `func.strings` is populated for
binaries 16, 18, 19 and 22. Distinctive literals pin functions outright:

- `"a_createhk47"` occurs in exactly one function on binary 18 -> `CVirtualMachine::RunScript` = `0x08463382`.
- `["CodeSize","InstructionPtr","SecondaryPtr","Stack","StackSize"]` occurs in exactly two -> `Save`/`LoadScriptSituation`.
- `"FadeDelayOnDeath"` -> `CSWSCreature::EventHandler`. `"Playing next anim in queue: %s"` -> `CClientExoAppInternal::MainLoop`.

**b. Literal reference sites, not Ghidra's string attribution.** When a literal is shared
by several functions, resolve the literal's vaddr from the raw file (`file_off + 0x08048000`)
and grep the full `objdump` for code that references it. Grouping reference sites by which
literals they co-reference reproduced the donor string sets exactly and separated Door
(`NW_G0_Transition` + `k_trg_transfail` + `k_hen_dialogue01`) from Trigger (no
`k_hen_dialogue01`) from Placeable (`k_hen_dialogue01` only).

**c. Translation-unit layout isomorphism.** The `CVirtualMachineInternal` TU appears in
identical source-declaration order on binary 19 (mac) and binary 16 (android x86 - a
different compiler and platform). Binary 18 reproduces that order 1:1 across 24 consecutive
functions, with `n_blocks` and `n_callees` matching almost exactly and several sizes
identical (`RunScriptFile` 238 = 238, `RunScriptSituation` 347 = 347). Validating the
invariant on *two* donors before relying on it is what makes this admissible.

**d. `func.consts` as a class-layout fingerprint.** The constant vectors are member offsets
into the class (428/440/444/980 for the VM), and they are stable across Mac and Linux
because the class layout is. They matched element-for-element and positionally. Jaccard
similarity against the mac counterpart cleanly separated good candidates from bad:
`CSWSArea` 1.000 (18/18) and `CSWSModule` 0.941 (32/33) versus the matcher's rejected
Door/Trigger/Placeable proposals at 0.083/0.064/0.089.

**e. Disassembly of semantic immediates.** The NWScript stack type codes are literal
immediates: 3 = INTEGER, 4 = FLOAT, 5 = STRING, 6 = OBJECT, 0x10+ = engine structure.
`StackPushInteger` does `mov [esp+4],0x3`; `StackPopObject` does `cmp byte ptr [..],0x6`;
`StackPopVector` calls `StackPopFloat` three times into `[edi+8]/[edi+4]/[edi]`. This is
ground-truth-grade and it resolves the Integer/Object pairs that are byte-identical in shape.

**f. Callee identity for thin wrappers (this is what cracked the degenerate cluster).**

**g. GCC Itanium RTTI walk -> vtables.** The ELF is stripped but RTTI is intact
(`12CSWSCreature`, `8CSWSDoor`, ...). Walk: typeinfo-name string -> the dword pointing at it
is `typeinfo+4` -> the dword pointing at the typeinfo is vtable slot 1 -> virtual functions
start at `vtable+8`. Filter to the *primary* vtable (`offset_to_top == 0`); secondary
multiple-inheritance vtables give wrong slots. Calibrating on the four EventHandlers already
pinned by strings showed `EventHandler` is **slot 31** for every `CSWSObject` subclass, which
then read out Store, Waypoint, Encounter, AreaOfEffectObject and SoundObject directly.

**h. Call-graph isomorphism.** For non-virtual methods, where the vtable route is unavailable,
the caller set works instead. `CSWSArea::EventHandler` and `CSWSModule::EventHandler` each
have exactly one direct caller on binary 18, and it is the same caller for both; mac shows
exactly the same structure, with both called only from `CServerAIMaster::UpdateState`, whose
shape matches (71 vs 72 blocks, 19 = 19 callees, cyclomatic 48 = 48).

**i. Control-flow component analysis for Ghidra's coverage gaps.** Union-find over the whole
1.74M-instruction disassembly, unioning each instruction with its fall-through successor
(unless it is `ret`/`jmp`/`hlt`) and with direct `j*` targets, but never across `call`.
The component containing a known site gives the function extent. Validated against
ground truth: it reproduced Ghidra's `CSWSCreature::EventHandler` entry and size exactly.
Caveat: the component minimum is the GCC **exception landing pad**, not the entry; the real
prologue follows the last `_Unwind_Resume`. The vtable dword confirms which is correct.

## 3. The degenerate stack-accessor cluster

Nine `CVirtualMachine::` accessors were collapsed by the matcher onto `0x086abcb0` at score
0.965, margin 0.000. They are 28-byte, 1-block, 1-callee thunks; they carry no strings, no
distinguishing constants, and identical shapes. **They contain no information that
distinguishes them except their callee.**

The fix is ordering, not cleverness:

1. Resolve the `CVirtualMachineInternal::` layer first, using TU-layout isomorphism to place
   them and the NWScript type-code immediates (2e) to prove each placement.
2. Then read each wrapper's single `calledge` callee and label it from the resolved layer.

All 18 wrappers resolved uniquely and with no residual ambiguity, and the resulting order
independently reproduced the `CVirtualMachine` declaration order seen on both donors. The
matcher's `0x086abcb0` is an unrelated 33-byte function; all nine proposals are rejected.

Seven degenerate destination clusters were rejected in total, including `0x08620030`, which
the matcher offered for `StackPopEngineStructure` and which actually calls `lseek64`.

## 4. The 877 anchor

Verified and load-bearing. At vaddr `0x0858b02d` (file `0x54302d`):

```
858b002: push esi ; sub esp,0x8 ; mov esi,[esp+0x10]
858b00a: mov DWORD PTR [esp],0x1b68      ; 0x1b68 = 7016 = 877 * 8
858b011: call 818e744 <_Znaj>            ; operator new[]
858b016: mov [esi+0xc],eax               ; this->table
858b01b: mov [eax+ecx*8+0x4],0 ; mov [eax+ecx*8],0 ; inc ecx ; cmp ecx,0x36d ; jne
```

That is `CSWVirtualMachineCommands::InitializeCommands` at `0x0858b002`. Following the
`[this+0xc]` member led to the `cmp eax,0x36c` bounds check at `0x085b8797` inside
`CSWVirtualMachineCommands::ExecuteCommand` at `0x085b878e`, which dispatches through the
Itanium ABI `{ptr, adj}` pointer-to-member-function pair. Closing the loop: `0x085b878e`
appears once in `.rodata` at `0x087889d4`, inside the vtable whose vptr value `0x087889c8`
the CSWVirtualMachineCommands destructor installs at `0x0858afbb`.

## 5. What did not work

- **`decomp.skeleton_hash`** - the `decomp` table has **zero rows for binaries 18 and 16**.
  The discriminator does not exist for this target. (Rows exist only for 19 and 22.)
- **`score`** - as the brief warned. Nine functions collapsed at score 0.965 and three more
  at 0.9973 / 0.9783, all at margin 0.000, all wrong.
- **Naive `n_instr` comparison** - binary 18 consistently reports ~10% fewer instructions
  than mac for the same function. `n_blocks` and `n_callees` are far more stable and were
  used instead.
- **Bounds-check pattern search for `ExecuteCommand`** - grepping for
  `call DWORD PTR [reg+reg*8]` returned nothing, because GCC loads the pointer into a
  register first. Searching for the `0x36c` immediate worked instead.
- **BSim** - deliberately not attempted; see `unresolved.md`.

## 6. How to redo or extend this

1. `sqlite3 "file:<db>?mode=ro"` - never open the corpus read-write; a `-wal`/`-shm` pair is present.
2. Calibrate on binary 19 first. Any change to the matcher must be re-calibrated before use.
3. `objdump -d -M intel <raw elf> > b18.asm` (about 1.74M lines, ~1 minute).
4. `vaddr = file_offset + 0x08048000` for every section in this image (`.text` and `.rodata` both).
5. To extend to another class: find its RTTI name string, walk to the primary vtable, read
   slot 31 for `EventHandler`. To extend to another VM function: find its position in the
   mac TU listing and count into the corresponding binary-18 block.
6. Re-verify every candidate against `n_blocks` and `n_callees` on binary 19, and against a
   disassembled semantic constant where one exists.
7. Always disassemble the proposed entry. If it begins `mov reg,eax` followed by a call and
   `_Unwind_Resume`, it is an exception landing pad and the real prologue is later. This
   failure mode is invisible to size, block-count and `consts` checks, because the function
   body is the same either way.
8. Two absence checks are worth running on every binding. Zero dword references anywhere in
   the file means the function is not in a vtable, which is fine for a non-virtual method but
   must then be backed by direct callers. Zero dword references *and* zero callers means the
   address is unreachable and therefore not a function entry.
