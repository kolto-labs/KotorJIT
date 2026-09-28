# Platform M0 (fat Mach-O slice selection) and M1 (x86_64 detour engine)

Sole writer. Worktree: `.worktrees/lua-boundary-validation`. Nothing was staged, committed, stashed or pushed. No Wine or game ran, and the live-game lock was not touched. Every fixture is built in code: no retail bytes appear in any source file or in the scratch build dir.

Scratch build dir, outside the worktree: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/.scratch-build-platform-m0m1`

Configure command: `host-cmd sh -c 'cd <worktree> && cmake -S . -B <scratch> -G Ninja'` (exit 0)

## Files

| File | State | Change |
|---|---|---|
| `src/image/macho.hpp` | untracked, extended | `Headers::has_uuid/uuid`, `Slice`, `select_slice`, `Identity`, `identify` |
| `src/image/macho.cpp` | untracked, extended | LC_UUID parse at :99-104; `select_slice` at :127; `identify` at :196 |
| `tools/kp_machotest.cpp` | untracked, extended | fat builders and M0 tests (`// ---- M0 ----` at :117); the real-image loop now handles fat files and prints hashes only |
| `src/hooks/x64/decode.hpp` / `.cpp` | new | allowlist length decoder, `referent`, `relocate` |
| `src/hooks/x64/trampoline.hpp` / `.cpp` | new | `plan`, `Detour` install/uninstall, W^X writer, near mmap |
| `tools/kp_hooktool_x64.cpp` | new | selftest in three tiers: decoder, relocation/plan, native self-hook |
| `src/hooks/hooks.cmake` | +19 lines, 0 removed | `kp_hooks_x64` + `kp_hooktool_x64` + `add_test(kp_hooktool_x64.selftest)` at :68-85 |

`CMakeLists.txt` was not edited; it was already dirty from other writers. `kp_machotest` is registered there with `macho.cpp` only. `identify` needs `sha256.cpp`, so `tools/kp_machotest.cpp:6` unity-includes `image/sha256.cpp`, with a comment.

**Follow-up once CMakeLists.txt is free:** add `src/image/sha256.cpp` to `kp_machotest`'s sources and delete that include.

**Not done, noted for later:** the `k2_mac_x86_64` static-only entry in `tools/gen_address_tables.py`. That file was forbidden in this pass.

## M0: fat slice selection and identity

API (`src/image/macho.hpp`):

- `select_slice(bytes, n, cputype, cpusubtype, Slice&, error)` handles big-endian `FAT_MAGIC` (0xcafebabe) and `FAT_MAGIC_64` (0xcafebabf). A matching thin image is returned as a whole-file slice.
- Offsets and sizes are `uint64_t` on every host.
- Subtype capability bits (0xff000000) are ignored on both sides.

Refusals, all of which leave the output unchanged:

- truncated magic, header or arch table
- arch count of 0, or more than 32 (the Java-class collision)
- empty slice
- slice outside the container, including 64-bit overflow
- alignment above 2^15, or an offset that breaks its alignment
- slice overlapping the header or table
- slices overlapping each other
- duplicate architecture
- missing architecture
- little-endian fat magic
- nested fat slice
- slice that is not a thin Mach-O
- slice header CPU that disagrees with its fat entry

`identify(...)` returns `Identity{container_sha256, slice_sha256, uuid, slice, headers}` and refuses a slice without LC_UUID.

`read_file` changes:

- It now parses LC_UUID (0x1b). A cmdsize other than 24 refuses, and so does a duplicate.
- LC_UUID stays optional in `read_file`, so no thin image that parsed before is refused now.
- The fat and big-endian refusal strings are unchanged, and `kp_imagetool_macho_test` still passes.

Decision on requiring UUID in `identify`: checked first against both private i386 images. Each has exactly one LC_UUID (a Python load-command walk printed `LC_UUID count 1` for each), so requiring it rejects no known image.

### Red, then green

- Red, with stubs returning false: `FAIL LC_UUID parsed:` and exit 1.
- Green: `./kp_machotest` printed `PASS 27808 checks` with exit 0.

Named M0 checks in `tools/kp_machotest.cpp`, each run for both FAT_MAGIC and FAT_MAGIC_64 unless marked:

- `fat selects i386 slice` / `fat64 selects i386 slice`
- `fat selects x86_64 slice (cap bits ignored)` / `fat64 …`
- `identity keeps container sha, slice sha and LC_UUID (x86_64)` / `(i386)`
- `missing arch refuses`, `wrong ABI bits refuse`
- `every fat truncation refuses (x86_64)` / `(i386)`: every prefix length is tried
- `overlapping slices refuse`, `identical-extent slices refuse`, `slice over the fat header refuses`
- `misaligned slice offset refuses`, `implausible alignment refuses`
- `duplicate architecture refuses`, `empty slice refuses`, `slice past end of file refuses`
- `fat64 offset beyond 4GiB refuses`, `fat64 offset+size overflow refuses` (fat64 only)
- `nested fat slice refuses`, `garbage slice refuses`, `slice header CPU disagreeing with entry refuses`
- `slice without LC_UUID is still selectable`, `identity refuses slice without LC_UUID`
- `zero arch count refuses`, `implausible arch count (Java class) refuses`
- `little-endian fat magic refuses`, `null container refuses`
- `thin image is its own slice`, `thin identity: container and slice hash agree`, `thin image of another CPU refuses`
- `LC_UUID parsed`, `thin image without LC_UUID still parses`, `short LC_UUID refuses`, `duplicate LC_UUID refuses` (thin 32 and 64)

Each refusal test asserts a substring of the diagnostic, so it cannot pass by failing for some other reason.

Mutation checks. Each check was removed from `macho.cpp`, the tests were rebuilt and run, and the source was restored:

| Removed check | Test output |
|---|---|
| `slices overlap` | `FAIL overlapping slices refuse` |
| alignment check | `FAIL misaligned slice offset refuses` |
| `count > kMaxFatArchs` | `FAIL implausible arch count (Java class) refuses` |
| nested-fat check | `FAIL nested fat slice refuses: selected slice: fat Mach-O is unsupported…`, so `read_file` is a second guard |

### Regression builds

Build command: `cmake --build <scratch> --target kp_image kp_imagetool kp_machotest image_win32`

- No errors or warnings. `macho.cpp` compiled in three builds: native x86_64, `-m32` (kp_image) and `i686-w64-mingw32-g++` (image_win32).
- A standalone `g++ -std=c++20 {-m32,-m64} -Wall -Wextra -Werror -c src/image/macho.cpp` printed `werror-m32=ok` and `werror-m64=ok`.
- `file kp_imagetool` reports ELF 32-bit i386, and `file kp_machotest` reports ELF 64-bit x86-64.

### Private real-image run (hashes and offsets only; nothing written anywhere)

Command: `kp_machotest <K1 mac raw_image> <K2 mac raw_image>`, where the paths are under `~/biodecompwarehouse/kotorxid/output/binaries/*/artifacts/raw_image`.

```
K1: bits=32 cpu=0x7 segments=5 uuid=present
K1: thin cpu=0x7 sub=0x3 offset=0 size=8448052 container_sha256=aa6283733d3c738d11d12453f77dfc6b7e87f95326a07ee97daab1a37734b032 slice_sha256=(same) uuid=present
K2: bits=32 cpu=0x7 segments=5 uuid=present
K2: thin cpu=0x7 sub=0x3 offset=0 size=9115340 container_sha256=f14f285b1b6ed7e4bf000fe19ebcd0d6528d1d3e86d2832be6092761557c130d slice_sha256=(same) uuid=present
PASS 27814 checks
```

Both hashes match `kp-live-20260922/mac-image-baseline.json`.

**The K2 fat container was not found.** A read-only scan for fat magic ran over these roots, completed, and found no file:

- `MyBook/{kotor_vanilla_refs,Games,kotor_mod_archives,ISOs,Downloads}`
- `~/biodecompwarehouse`

So the x86_64 slice (`469067c4…` in the plan) has not been re-derived here. The `raw_image` files are the i386 slice only.

## M1: x86_64 inline detour

Design:

- **Patch.** `FF 25 00000000` plus an 8-byte absolute address, 14 bytes, at the target. Any stolen bytes past 14 are filled with int3.
- **Trampoline.** The relocated stolen instructions, then the same 14-byte jump back. The trampoline page is mapped within ±2GiB of the target (`map_near`, `MAP_FIXED_NOREPLACE` hints stepping outward in 1MiB, trampoline.cpp:71) whenever an instruction needs relocation.
- **Relocation.** Each RIP-relative disp32 and each rel32 (E8, E9, 0F 8x) is re-aimed at the same absolute address. A displacement that doesn't fit in int32 refuses with `OutOfRange` and writes nothing.
- **Decoder.** An allowlist (decode.cpp:109).
  - RIP-relative is exactly mod=00 rm=101 with no SIB (:212), whatever REX.B says. SIB base=101 with mod=00 is an absolute address and is not relocated (:208).
  - `66` shrinks immz to 16 bits. Only `B8+r` with REX.W takes imm64. `F6/F7` carry an immediate only for /0 and /1 (:224).
  - Refused: prefix 67, VEX/EVEX, rel8 branches (EB, 7x, E0-E3), returns and traps, moffs, I/O, far FF forms, xbegin, invalid 64-bit opcodes, a REX not directly before the opcode, and anything unlisted.
- **`plan`** (trampoline.cpp:120) refuses in three cases:
  - a ret or trap inside the 14-byte window (`DecodeFailed`)
  - E9 or `FF /4` ending before byte 14 (`FlowEnds`)
  - any stolen instruction naming an address inside the stolen range (`BranchIntoPatch`)
- **W^X** (`write_code`, trampoline.cpp:31).
  - The target goes RX, then RW, then RX; the trampoline is filled RW and sealed RX. Nothing is ever RWX.
  - An RX restore failure reports `ProtectFailed`, with an EACCES/SELinux hint, and does not fall back.
  - `install` refuses with `UnsafePage` when the engine's own code shares the target page (:51).
- **Uninstall** (:260) checks the patch bytes are still present (`PatchClobbered` otherwise), restores the original bytes and unmaps the trampoline.
- **Build.** `kp_hooks_x64` is a separate target, guarded by `UNIX AND NOT WIN32 AND CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|AMD64"`. It includes neither `hooks/trampoline.hpp` nor `platform/platform.hpp` and links neither `kp_hooks` nor `kp_image`, so no `-m32` leaks in.
- **i386 path unchanged.** hooks.cmake has 0 removed lines. `kp_hooks` and `hooks_win32` still build, and `objdump -f` on `kp_hooks.dir/src/hooks/trampoline.cpp.o` reports `elf32-i386`.

### Native self-hook target

The target is not compiler codegen. It is top-level `asm` in `tools/kp_hooktool_x64.cpp:219`: `push rbp; mov rbp,rsp; sub rsp,0x10; mov eax,[rip+kp_x64_global]; add eax,edi; leave; ret`.

- It lives in its own section `.text.kp_x64_hook_target`, page-aligned and int3-padded to a full page. Flipping that page RW therefore never takes the patcher's code with it.
- The stolen range is exactly 14 bytes and includes the RIP-relative load, so relocation is exercised in real execution.

### Red, then green

- Red, with stubs: `111 of 192 checks FAILED`. The first native line was `FAIL native: install not implemented`.
- First implementation run: `1 of 230 checks FAILED`. The failure was `plan: endbr64 prologue = 16`, and it was a test arithmetic error: the bytes add up to 4+1+3+2+2+1+4 = 17. I corrected the expectation, not the code.
- Green: `./kp_hooktool_x64 selftest` printed `PASS 230 checks` with exit 0.

Named M1 checks in `tools/kp_hooktool_x64.cpp`:

- **Tier 1** (`test_decoder`, :50). 42 prologue encodings, each checked three ways: length/rel/offset, exact-length input, and truncated-by-one refusal. Plus 29 refusals, a null pointer, and the 15-byte limit.
  - Traps covered include REX.B RIP, SIB-absolute, the `fs:` stack-protector load, `80 3D disp32 imm8`, `66 C7 05`, REX.W `C7`, `48 B8 imm64`, `F6 05` vs `F6 15`, and `66 F7`.
- **Tier 2** (`test_relocation`, :138):
  - `relocate: same referent, other bytes untouched`: 6 encodings × 3 deltas, up to ±~2GiB
  - `relocate: out-of-range refuses, writes nothing` (3GiB)
  - `relocate: plain copy`
  - `plan: frame + RIP load = 14, needs near`, `plan: endbr64 prologue = 17 …`
  - `plan: ret before 14 bytes refuses`, `plan: jmp before 14 bytes refuses`, `plan: jmp that ends past the window is allowed`
  - `plan: branch into stolen range refuses`, `plan: unsupported opcode refuses with detail`, `plan: fewer than 14 readable bytes refuses`
- **Tier 3** (`test_native`, :269). Two full cycles, each checking:
  - `expected-bytes mismatch refuses`, `refusal wrote nothing`, `install`
  - `stole exactly the 14-byte frame + RIP load`, `jmp [rip+0] written`, `double install refuses`
  - `trampoline within +/-2GiB of target`
  - `target page back to r-x`, `trampoline page sealed r-x`, `no writable+executable mapping in the process` (all read from `/proc/self/maps`)
  - `call goes through the detour`
  - `relocated RIP-relative load reads the same global`: the global changes after install and the trampoline sees the new value
  - `original() bypasses the detour`, `uninstall`, `bytes restored exactly` (17-byte memcmp against the pristine copy)
  - `target page r-x after uninstall`, `restored call skips the detour` (detour counter unchanged), `double uninstall refuses`

  Then, once each:
  - `clobbered patch refuses uninstall`, then `uninstall after repair`
  - `short function refuses without writing` (on an mmap'd RX page)
  - `hooking the engine's own page refuses` (asserts `UnsafePage` exactly)
  - `target intact at exit`

Mutation checks. Each change was applied, the tests rebuilt and run, and the source was restored (restoration confirmed with `cmp`):

| Change | Test output |
|---|---|
| `relocate` copies verbatim | tier 2 `FAIL relocate: same referent…`. Run alone, the native tier dies with status 139 (SIGSEGV), which shows the native hook really executes the relocated RIP load. |
| SIB base=101 treated as non-absolute | `FAIL decoder: length/rel 8b 04 25 …` |
| F6/F7 immediate on every reg | `FAIL decoder: length/rel f6 15 …` |
| target restored RWX instead of RX | `FAIL native: target page back to r-x rwxp`, `FAIL native: no writable+executable mapping` |
| clobber check removed | `FAIL native: clobbered patch refuses uninstall` |

### Final combined run

Build command: `cmake --build <scratch> --target kp_hooks hooks_win32 kp_image image_win32 kp_imagetool kp_machotest kp_hooktool_x64`, which printed no error or warning lines.

```
ctest -R 'kp_machotest|kp_imagetool_macho_test|kp_hooktool_x64'
100% tests passed, 0 tests failed out of 3
file kp_hooktool_x64: ELF 64-bit LSB executable, x86-64
g++ -std=c++20 -O2 -Wall -Wextra -Werror: werror-ok for decode.cpp, trampoline.cpp, kp_hooktool_x64.cpp
```

## Residual proof boundary

- **No Darwin runtime.** Nothing was built or run on macOS. The engine uses Linux `mmap`/`mprotect`/`MAP_FIXED_NOREPLACE` and reads `/proc/self/maps` only in the test. Darwin needs `mach_vm_protect` or `MAP_JIT` and codesigning/hardened-runtime handling, which is M2.
- **No retail hook.** The only native hook target is the synthetic asm function. No KOTOR code was decoded, planned or patched, and the decoder's allowlist has not been checked against the x86_64 slice's real prologues.
- **No x86_64 K2 container on disk here.** The fat-container scan found none, so only synthetic fat fixtures prove M0. The real run covered the thin i386 images only.
- **Engine limits.**
  - Not thread-safe: another thread executing the target page during the RW window would fault.
  - The own-page guard covers the engine's functions and `install`'s caller-return page, not every caller.
  - `plan` reads up to 28 bytes past the target unconditionally.
  - Branch-into-patch detection covers the stolen instructions only. A jump from elsewhere in the function into bytes 1-13 is not detectable without whole-function analysis.
- **`kp_imagetool identify` for fat files is not wired.** kp_imagetool was forbidden in this pass.

## Fix round (review: kp-live-20260922/platform-m0m1-review.md)

Scope: I1, I2, I3, m2, m3, m4. Only the five M1 files changed (`src/hooks/x64/{decode,trampoline}.{hpp,cpp}`, `tools/kp_hooktool_x64.cpp`). No Wine or game ran. The live-game lock was not touched. Pre-fix copies of the five files, the logs, and the scratch build are in `/home/brunner56/kp-live-20260922/fixround-m1/` (`orig/`, `red-full.log`, `green.log`, `ctest.log`, `build/`).

Order of work:

1. Added the test surface with the old behaviour kept:
   - an `mprotect` seam (`testing::set_protect_hook`)
   - `leaked_trampoline_pages()` (stubbed to 0)
   - `uninstall(detail)`
   - `Insn::is_call` and `Insn::is_nop` (never set)
2. Wrote the tests.
3. Ran them red.
4. Fixed.
5. Ran them green.

### Red run (old behaviour, new tests): `119 of 650 checks FAILED`

```
FAIL decoder: immz table 66 48 05 11 12 13 14 -> len=5 want 7            (90 immz-table failures, all 66+REX.W)
FAIL plan: call + NOP padding inside the window refuses e8 01 02 03 04 90 Ok   (18, E8 and FF 15 x 9 paddings)
FAIL I2: destructor after PatchClobbered keeps the trampoline child killed by signal 11
FAIL I2: move-assign after PatchClobbered keeps the trampoline child killed by signal 11
FAIL I2: destructor after ProtectFailed keeps the trampoline child killed by signal 11
FAIL I3 install once: original bytes rolled back ff 25 00 00 00 00 00 49 40 ...
FAIL I3: install, restore refused once: rolled back and resealed child killed by signal 11
FAIL I3: install, rollback also refused: patch live, still installed child killed by signal 11
FAIL I3: uninstall, restore refused once: patch rolled back, still installed child killed by signal 11
FAIL m4: r-- page restored as r-- r-xp
FAIL m4: mprotect's page refuses FlowEnds
```

### Green run

```
kp_hooktool_x64 selftest -> PASS 650 checks (the initial green receipt)
host-cmd ctest --test-dir fixround-m1/build -R "kp_machotest|kp_imagetool_macho_test|kp_hooktool_x64"
  -> 100% tests passed, 0 tests failed out of 3
cmake --build (RelWithDebInfo, -Wall -Wextra on the tool): 0 warning lines
g++ -std=c++20 {-O0, -O2, -O3 -fcf-protection} -Wall -Wextra -Werror on all three files: PASS 650 each
```

### Resume verification

The stopped session was resumed without replacing this fix-round section. The
current source rebuilt in the existing out-of-worktree scratch build and
`kp_hooktool_x64 selftest` printed `PASS 654 checks` (four checks were added
after the initial 650-check receipt). The requested CTest filter then passed
all three entries: `kp_machotest` (0.01 s), `kp_imagetool_macho_test` (60.56
s on the loaded host), and `kp_hooktool_x64.selftest` (0.16 s), 3/3 green.

The reviewer enumeration was rerun from
`/home/brunner56/kp-live-20260922/review-probes-m0m1/fuzz/` against a freshly
rebuilt `dec_cli` linked to the current `decode.cpp`: 1,641,904 cases,
1,129,845 decoder-accepted, 930,579 Capstone agreements, 0 LEN mismatches,
0 RIP mismatches, and 199,266 unchanged Capstone-invalid encodings.

Decoder differential against capstone 5.0.7. The reviewer's `enum.py` and `fuzz.py` were run unchanged against a `dec_cli` rebuilt from the fixed `decode.cpp` in `fixround-m1/fuzz/`. The reviewer's own `dec_cli` was not overwritten.

| Run | ok | LEN mismatch | RIP mismatch | cs-invalid |
|---|---|---|---|---|
| enum.py before (old dec_cli) | 926,817 | 3,762 | 0 | 199,266 |
| enum.py after | 930,579 | 0 | 0 | 199,266 |
| fuzz.py 300000 2 before | | 234 | 0 | 23,953 |
| fuzz.py 300000 2 after | | 0 | 0 | 23,953 |

The review says 3,786 LEN mismatches. Re-running its script gives 3,762 (380 test, 8 x 342 ALU, 304 push, 304 imul, 38 mov). The 3,762 moved exactly into `ok`. The cs-invalid bucket is unchanged because m1 was not in scope. `echo 66480512345678 | dec_cli` now prints `7 0 0 0 -`.

### Per finding

claim: I1 fixed. With 66 and REX.W both present, the immediate is imm32 (imm64 for B8+r).
referent: `decode.cpp` sets `immz = opsize && !rex_w ? 2 : 4`. The `test_immz_table` test has 16 opcodes x 8 prefix sets (none, 66, 48, 66 48, 41, 66 41, 66 49, F3 48). Each row checks the length, that exact-length input decodes, and that input one byte short refuses. The expected lengths are literals taken from capstone (`fixround-m1/table.py`). REX-then-66 rows refuse.
checked: red run had 90 failures; green passes; enum/fuzz LEN 0.
verdict: holds
confidence: high

claim: I2 fixed. Destructor and move-assign leak the trampoline, and do not unmap it, when uninstall fails.
referent: `Detour::abandon()` in trampoline.cpp. It increments `leaked_trampoline_pages()` and drops the pointer without calling `munmap`. Three forked-child tests:
- A foreign hook copies our 14 bytes into its stub and repoints the target. `uninstall()` returns PatchClobbered. The Detour is destroyed. Afterwards the trampoline is still `r-xp`, the leak count went up by 1, and `fn(5) == 10211` (foreign -> our detour -> trampoline -> original).
- The same with `d = Detour()`.
- Uninstall with the seam refusing every `mprotect` on the target page returns ProtectFailed. Destroying the Detour leaks the trampoline and the patched call still returns 211.
checked: red run had all three children killed by SIGSEGV; green passes.
verdict: holds
confidence: high

claim: I3 fixed. A refused restore rolls back to the previous bytes while the page is still writable, then retries the restore.
referent: `write_code` in trampoline.cpp. On failure it goes back to RW, copies the saved bytes back, and reseals. It reports `now_new` so callers know which bytes are live. Forked-child tests use the seam to return EACCES:
- install, refused once: ProtectFailed and not installed. Bytes are pristine, the page is `r-xp` and `fn(5) == 105`.
- install, always refused: bytes are pristine and the page is `rw-p`. This is documented as dead and is not called.
- install, rollback also refused: ProtectFailed with `installed() == true`. The trampoline is kept. A later `uninstall()` returns Ok and puts back the recorded `r-xp`.
- uninstall, refused once: ProtectFailed and still installed. The patch bytes are kept, the page is `r-xp`, the hooked call runs, and a retry succeeds.
- uninstall, always refused: ProtectFailed and still installed. The page is `rw-p`, and destroying the Detour leaks the trampoline.
checked: red run had bytes not rolled back and 3 children dead; green passes.
verdict: holds for the mechanism. A real SELinux execmod denial will normally refuse the reseal too, because the page is already a modified private copy. That case ends in "old bytes, page RW, not executable". It is documented in trampoline.hpp FAILED RESTORE and is not recoverable without RWX.
confidence: high for the seam paths. Real execmod was not run here.

claim: m2 fixed with a heuristic. A call followed by NOP padding inside the window refuses (FlowEnds).
referent: `plan()` checks `Insn::is_call` (E8, FF /2) and then `Insn::is_nop` on the next instruction: 90 without REX.B or F3, and 0F 1F. Tests cover 9 padding forms after E8 and after FF 15, including `66 90`, `66 2E 0F 1F 84 ..` and `66 66 2E 0F 1F ..`. `E8; 41 90` (xchg r8d) plans Ok, as do a call followed by real code and padding past the window.
checked: red 18 failures; green passes.
verdict: holds. Not detected: a noreturn call followed directly by the next function with no padding. That is documented in trampoline.hpp PLAN LIMITS. int3 padding already refused.
confidence: medium, because this is a heuristic.

claim: m3 fixed. The AllocFailed detail says "no free page within +/-2GiB of the target" only on the near path. The plain path says "mmap of the trampoline page failed".
referent: `Detour::install`. The header now also says the search is centred on the target, not on the referents, and fails safe (OutOfRange).
checked: code reading. There is no test, because making mmap fail would need another seam.
verdict: holds
confidence: medium

claim: m4 fixed. The original protection is restored, and the own-page guard covers libc code that runs during the write.
referent:
- install reads each target page's protection from `/proc/self/maps` (`page_prot`) before any change and records it in `Detour::prot_`. Every write, at install and at uninstall, restores exactly that. Test: a hook on an `r--` page leaves it `r--p` after install and after uninstall.
- A page that was already W+X is put back as it was found. The header's W^X paragraph now says so.
- The write path no longer calls libc `memcpy`. It uses its own volatile byte loop, `copy_code`.
- `shares_engine_page` is now `noinline`, so the return address really is in `install`. It also covers `copy_code`, `reseal`, `protect`, libc `mprotect`, `__errno_location` and the active seam. Test: `install(&::mprotect)` returns UnsafePage; the old code returned FlowEnds.
checked: red 3 failures; green passes.
verdict: holds. The guard is still a sanity check, not a proof. It checks the entry address of each function only.
confidence: high for the protection restore, medium for the guard.

### Remaining limits after this round

- Real SELinux execmod and a real two-mapping span (the patch crossing into a mapping with different protection) were not exercised. The two-page reseal path is covered by code reading only.
- A failed install can now return ProtectFailed with `installed() == true`, when the rollback's own `mprotect` was refused. Callers must check `installed()`, not only the status. This is documented at `HookStatus::ProtectFailed`.
- Leaked trampoline pages are never reclaimed. Each one costs a page per abandoned hook.
- m1 (the decoder accepts about 199k architecturally undefined encodings) and m5 (`kp_machotest` unity-includes `sha256.cpp`) were not in scope and are unchanged.
- Everything under "Residual proof boundary" above still applies: no Darwin runtime, no retail hook, not thread-safe.

## Follow-up: re-review minors m6 to m9

Scope: `src/hooks/x64/trampoline.{hpp,cpp}` and `tools/kp_hooktool_x64.cpp`. `decode.*` is unchanged. Scratch build: `/home/brunner56/kp-live-20260922/fixround-m6m9/build` (RelWithDebInfo, Ninja). Mutants and logs are in the same directory.

Results:
- Baseline before any change: `PASS 654 checks`.
- After the change: `PASS 650 checks`.
- `ctest -R "kp_machotest|kp_imagetool_macho_test|kp_hooktool_x64"`: 3/3 passed.
- The reviewer's `probe.cpp` against the new engine: `ALL PROBES PASS`.

The parent count went down because 8 parent-level m4 checks moved into 2 forked children, and 3 other new children were added. A child counts as one parent check.

claim: m6 fixed. The selftest now has the real two-mapping partial-mprotect case.
referent: the child test "m6: real two-mapping RW flip refused: page 0 resealed, nothing written". Page 0 is anonymous and r-x. Page 1 is `MAP_SHARED` from a file opened `O_RDONLY`, also r-x. The file goes in `$TMPDIR`, then `/tmp`, then the binary's directory. If none of them can be mapped executable, the check fails. It never skips.
- A precondition check confirms that a raw `mprotect` over both pages returns -1 and leaves page 0 `rw-p`.
- After a refused install, page 0 is `r-xp`, the bytes are untouched and `f(5) == 105`.
checked:
- New test on the unchanged engine: 655 pass.
- The reviewer's exact `mut/rw_no_reseal.cpp`, before the m7 to m9 changes: `FAIL m6: page 0 resealed r-x, page 1 untouched rw-p r-xs`, child killed by signal 11, 1 of 655 failed.
- The same line deleted from the final `trampoline.cpp` (`mut/final_rw_no_reseal.cpp`): only m6 fails, 1 of 650.
verdict: holds
confidence: high

claim: m7 fixed in wording, for both install and uninstall. Making this outcome leave the page executable is not feasible. It only happens after the kernel refused the restore to the executable protection, and the engine will not use RWX.
referent:
- FAILED RESTORE in `trampoline.hpp` now says the target page(s) can be left RW and not executable, and that calling the target faults.
  - For install, the target stays uncallable until `uninstall()` succeeds.
  - For uninstall, the Detour is uninstalled and its trampoline released, but the page is dead.
- The detail string now ends in "the page left RW, not executable".
- Tests:
  - The existing "rollback also refused" child now also checks the page is `rw-p`, the detail says "not executable", and a grandchild that calls the target dies with SIGSEGV.
  - A new child, "m7: uninstall, rollback also refused", checks the same for uninstall. The original bytes are back, `installed()` is false and no trampoline leaked.
checked:
- Red on the old engine: both detail checks failed.
- Mutant `m7_old_detail` (old strings): 2 children fail.
verdict: holds
confidence: high on the seam. A real double refusal was not run.

claim: m8 fixed. install refuses (new `HookStatus::NotExecutable`, added last) when a target page is not executable now. It refuses before it maps a trampoline or changes any protection.
referent:
- The check sits in `Detour::install`, in the `page_prot` loop.
- Tests:
  - An `r--` page and an `rw-` page both refuse. Bytes, protection and anonymous-mapping bytes are unchanged.
  - An `r-x | r--` split refuses.
  - The reviewer's dead-page retry, inside "restore always refused", now returns NotExecutable and the page stays `rw-p`.
- The old m4 "restores what it found, not r-x" coverage moved to an `rwx` page and an `r-x | rwx` split, inside a child.
checked:
- Red on the old engine: install returned Ok on `r--`, and Ok on the dead-page retry.
- Mutant `m8_no_exec_check`: 2 children fail.
verdict: holds
confidence: high

claim: m9 fixed in code, not only in docs. Nothing in the RW window goes through the PLT or touches errno, except the test seam.
referent:
- `protect()` is now an inline `syscall` (SYS_mprotect) that returns -errno. `reseal()` returns the first -errno, and `write_code` derives EACCES from it.
- The seam keeps the libc convention and is translated back.
- `::mprotect` and `__errno_location` stay in the own-page guard, because the seam still runs them.
- The header has a LAZY BINDING paragraph.
checked:
- `objdump -dr` of the old `trampoline.o`: 6 `mprotect@PLT` and 1 `__errno_location@PLT`.
- The new `trampoline.o`: 0 `mprotect@PLT`, and 6 inline `syscall`s.
  - The 3 `__errno_location@PLT` calls each come right after `call *%rax`, the seam, in `protect` and `reseal`.
  - `write_code`'s only PLT call is `memcpy` into `previous`, which runs before the flip.
- New check "m9: the refusal's EACCES reaches the detail". Mutant `m9_eacces_false` fails it.
verdict: holds by disassembly. A real lazy-binding fault was not reproduced.
confidence: medium. The object code shows no PLT call in the window. Nothing here proves the absence of a fault.

Remaining limits: the earlier "Remaining limits" still apply, minus the untested two-mapping reseal, which m6 now covers on a real kernel. A real SELinux execmod denial is still not exercised.

### Follow-up 2: install on an unmapped or PROT_NONE target (m10, was Grill #4)

claim: install no longer reads a target byte before it knows the page can be read. A PROT_NONE or unmapped target, or a patch window that runs into a PROT_NONE page, now returns `Unreadable`, a new status added last, instead of faulting.
referent: `code_window()` in trampoline.cpp.
- It reads `/proc/self/maps` only, never the target. It walks forward from the target while the pages are both readable and executable, capped at kMaxStolen, and records why it stopped: `Unreadable` or `NotExecutable`.
- `install` runs it before the expected-bytes compare and before `plan()`.
  - A zero window, or `expect_len` larger than the window, refuses with the stop reason.
  - `plan()` gets the window as `avail`. `decode` checks `need()` before every read, so it never reads past `avail`.
  - If the plan fails with "truncated", the stop reason is reported instead.
- A function whose stolen bytes end before a guard page still installs.
checked:
- Red on the previous engine: the three refusal children were killed by signal 11.
- Green: `PASS 654 checks`.
- Mutant `m10_no_window` (window ignored, `avail = kMaxStolen`): the same 3 children die with signal 11.
- `final_rw_no_reseal` still fails only m6.
- The reviewer's probe: ALL PROBES PASS.
verdict: holds
confidence: high for these layouts. The maps-then-read check is not atomic. Another thread that unmaps the page in between can still cause a fault. That is already out of scope under "Not thread-safe".

Red (`red_m10.log`, previous engine, new tests):
```
FAIL m10: install on a PROT_NONE page refuses child killed by signal 11
FAIL m10: install on an unmapped address refuses child killed by signal 11
FAIL m10: patch window crossing into a PROT_NONE page refuses child killed by signal 11
3 of 654 checks FAILED
```

Green (`green_m10.log`):
```
PASS 654 checks
```

Mutants, run against the final tests:
```
== m10_no_window
FAIL m10: install on a PROT_NONE page refuses child killed by signal 11
FAIL m10: install on an unmapped address refuses child killed by signal 11
FAIL m10: patch window crossing into a PROT_NONE page refuses child killed by signal 11
3 of 654 checks FAILED
== final_rw_no_reseal
FAIL m6: page 0 resealed r-x, page 1 untouched rw-p r-xs
FAIL m6: real two-mapping RW flip refused: page 0 resealed, nothing written child killed by signal 11
1 of 654 checks FAILED
```

Reviewer probe.cpp, built against the final libkp_hooks_x64.a (`probe_m10.log`):
```
pagesize=4096
PASS  I2 dtor after foreign chain: trampoline kept, chained call works, leak counted
PASS  I2 move-assign after chain; reused Detour installs+uninstalls cleanly, no extra leak
PASS  I2 move-construct from installed: source inert, one uninstall, no leak
    status=ProtectFailed detail=mprotect RW refused; nothing written errno-path
PASS  real kernel: RW refused on MAP_SHARED O_RDONLY r-x file mapping -> nothing written, no page left behind
    raw mprotect(2 pages, RW) = -1 errno=13 page0=rw-p page1=r-xs
    status=ProtectFailed detail=mprotect RW refused; nothing written page0=r-xp page1=r-xs
PASS  real kernel PARTIAL mprotect over two VMAs (anon r-x | shared-RO file r-x): page0 resealed, nothing written
    status=ProtectFailed detail=mprotect restore refused (EACCES: SELinux execmod?); previous bytes rolled back but the page is left RW, not executable page0=r-xp page1=rw-p
PASS  seam two-page: restore refused on page1 only -> rolled back; page0 r-x, page1 rw, not installed
    status=ProtectFailed installed=1 detail=mprotect restore refused (EACCES: SELinux execmod?) and rollback refused; new bytes left in place and the page left RW, not executable page0=rw-p page1=rw-p
PASS  seam two-page: restore AND second RW refused on page1 -> patch live, installed; page0 state?
    retry on the dead page: NotExecutable, page=rw-p
PASS  seam: exec ALWAYS refused on install (g_mode=1 refuses every PROT_EXEC on the page) -> page left rw-; retry install on the dead page
ALL PROBES PASS (0 failing)
```

ctest on the final tree (`ctest_m10.log`). The Mach-O Python test took 1435 s this time, against 356 s before. It was blocked on MyBook disk I/O (process state D). Nothing it covers changed.
```
Test project /home/brunner56/kp-live-20260922/fixround-m6m9/build
    Start  7: kp_machotest
1/3 Test  #7: kp_machotest .....................   Passed    0.15 sec
    Start  8: kp_imagetool_macho_test
2/3 Test  #8: kp_imagetool_macho_test ..........   Passed  1435.23 sec
    Start 11: kp_hooktool_x64.selftest
3/3 Test #11: kp_hooktool_x64.selftest .........   Passed    1.49 sec

100% tests passed, 0 tests failed out of 3

Total Test time (real) = 1437.24 sec
```

Grill me (m10, weakest first):
1. *Is the refusal race-free?* No. The maps read and the byte read are separate steps, so a concurrent unmap between them can still fault. This is covered by "Not thread-safe"; no test.
2. *Can a real plan failure be misreported as Unreadable?* Only when the window stopped short and `decode` refused with "truncated". That can only happen because the window cut an instruction. Any other refusal (a ret, a trap, a bad opcode) keeps its own status. Referent: the existing "short function refuses" check still returns DecodeFailed.
3. *Does a function next to a guard page still install?* Yes. See the child "m10: stolen bytes that end before a PROT_NONE guard page still install": install Ok, a call goes through the detour, uninstall restores the bytes and `r-xp | ---p`. It also passed on the previous engine, so it guards against regressions and is not a red test.
4. *Why Unreadable and not NotExecutable?* A PROT_NONE or unmapped page cannot be read at all. A readable page without exec keeps NotExecutable, so the dead-page retry and `r-x | r--` still return NotExecutable (m8 tests pass).
