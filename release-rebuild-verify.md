# Release rebuild verification: prefix maps and -s, without -DNDEBUG

Date: 2026-09-27. This was a verification build only. Nothing was published, no game was run, and the
live-game lock was not touched. Nothing under `/home/brunner56/kp-release-*` was modified, and the
worktree was only read (the scanner).

## Verdict

**PASS.** The proposed CMake flags, with `-DNDEBUG` dropped, remove every build-path string from
`kphasor.dll`. `binkw32.dll` had none before and has none after.

- Counts drop from 18 to 0 for `/home/`, the user name, and `kp-release`. The control rebuild has 18
  scratch-root hits; the patched build has 0.
- The same 18 `__FILE__` strings are still present in their mapped form
  (`./src/runtime/../../third_party/imgui/...`), so asserts stay compiled in.
- No behavioural surface changed:
  - imports and exports are identical
  - `.text`, `.data`, `.bss`, `.idata`, `.tls` and `.edata` have identical sizes
  - every differing `.text` byte is explained by relocation or image base
- Only the path strings and the symbol and debug data were removed.

Two stripping side effects are documented below: `.eh_frame` is renamed `.eh_fram`, and the 4-byte
`.sxdata` is dropped. Both were checked and are harmless. A DLL with `.eh_fram` still catches C++
exceptions under wine.

One caveat for the release gate: `scan_release_zip.py` has no `/tmp/` marker. It passes the control
build, which carries 18 `/tmp/kp-rebuild-verify/...` paths. The scanner passing here proves nothing on
its own. The proof is the base-vs-patched count.

## Counts before and after (`strings -a`, and `strings -a -e l` for UTF-16)

| string | shipped kphasor | base kphasor (unpatched, /tmp) | patched kphasor | shipped / base / patched binkw32 |
|---|---|---|---|---|
| `/home/` | **18** | 0 | **0** | 0 / 0 / 0 |
| `brunner56` (build user) | **18** | 0 | **0** | 0 / 0 / 0 |
| `.superpowers` | 0 | 0 | 0 | 0 / 0 / 0 |
| `kp-live` | 0 | 0 | 0 | 0 / 0 / 0 |
| `kp-release` | **18** | 0 | **0** | 0 / 0 / 0 |
| `/run/media` | 0 | 0 | 0 | 0 / 0 / 0 |
| `/tmp/` | 0 | **18** | **0** | 0 / 0 / 0 |
| `kp-rebuild-verify` (scratch root) | 0 | **18** | **0** | 0 / 0 / 0 |
| mapped `./…third_party/imgui/…` | 0 | 0 | **18** (17 + 1 `./third_party/imgui/imgui.h`) | 0 |
| any of the above, UTF-16 (`-e l`) | 0 | 0 | 0 | 0 |

Why the base column matters: building under `/tmp` zeroes `/home/` whether or not the flags work. The
control build uses the same scratch root without the patch, and it still carries 18 scratch-root paths.
The patched build carries 0, and the same 18 strings appear in mapped form. The mapping is one-to-one:

```
base (sorted, root shown as <SRC>)                          patched
<SRC>/src/runtime/../../third_party/imgui/imgui.h  x4    ->  ./src/runtime/../../third_party/imgui/imgui.h  x4
<SRC>/src/runtime/../../third_party/imgui/imgui_internal.h x4 -> ./src/runtime/../../third_party/imgui/imgui_internal.h x4
<SRC>/src/runtime/../../third_party/imgui/{imgui,imgui_draw,imgui_tables,imgui_widgets}.cpp,
   imstb_{rectpack,textedit,truetype}.h, backends/imgui_impl_{win32,opengl2}.cpp  x1 each -> same, "./" prefix
<SRC>/third_party/imgui/imgui.h                             ->  ./third_party/imgui/imgui.h
```

The shipped DLL carries the same 18 strings, rooted at `/home/brunner56/kp-release-20260927/source/...`.
All 18 are ImGui `IM_ASSERT` `__FILE__` strings. No project source path appears in any build.

## Setup (commands)

```
R=/tmp/kp-rebuild-verify
cp -a /home/brunner56/kp-release-20260927/source $R/base/source      # control, unpatched
cp -a /home/brunner56/kp-release-20260927/source $R/patched/source   # patched
# CMake hunks only (everything from the first "diff -ru a/source"), with the orchestrator's ruling applied:
awk '/^diff -ru a\/source/{f=1} f' release-builder-proposed.patch | sed 's/ -DNDEBUG$//' > $R/cmake-only.patch
  -> 5 file diffs, 0 NDEBUG; sha256 5b60b0c5...8af63
cd $R/patched && patch -p1 --dry-run < ../cmake-only.patch && patch -p1 < ../cmake-only.patch   # 5 files, clean
```

The `package.py` hunk was not applied, and `build-reviewed.py` was not run. That script overlays files
from the worktree and rewrites `source-provenance.json`. The copied `source/` already contains the
release overlays. All four `root-reviewed-fix.json` hashes matched: engine_k1.cpp, fields.hpp,
kp_harnesstest.cpp and k2_gog_aspyr.json.

Per-file check after the patch:

```
CMakeLists.txt            ffpm=1 fmpm=1 NDEBUG=0 -s=0
src/hooks/hooks.cmake     ffpm=1 fmpm=1 NDEBUG=0 -s=0
src/api/structs.cmake     ffpm=1 fmpm=1 NDEBUG=0 -s=0
src/runtime/runtime.cmake ffpm=1 fmpm=1 NDEBUG=0 -s=1   (kphasor.dll link)
src/proxy/proxy.cmake     ffpm=1 fmpm=1 NDEBUG=0 -s=1   (binkw32.dll compile+link)
```

Build: on the host via `host-cmd` (the MinGW toolchain is host-only). These are the release's own
configure and build arguments from `build-reviewed.py`, except that paths point into the scratch tree
and `VERBOSE=1` is added:

```
export TMPDIR=$R/<d>/tmp CCACHE_DISABLE=1
cmake -S $R/<d>/source -B $R/<d>/build -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=/usr/bin/python3 \
  -DKP_EXAMPLE_LUAJIT=/usr/bin/luajit -DKP_MODEL_LUAJIT=/usr/bin/luajit -DKP_ANIMATION_LUAJIT=/usr/bin/luajit \
  -DKP_MINGW_CXX=/usr/lib64/ccache/i686-w64-mingw32-g++
cmake --build $R/<d>/build --target kphasor_dll binkw32 -j4 -- VERBOSE=1
```

The only deviations from the release build are `CCACHE_DISABLE=1` (no stale cache hits), `-j4` and
`VERBOSE=1`. None of them changes the compiler output.

- Toolchain: `i686-w64-mingw32-g++ (GCC) 16.1.1 20260501 (Fedora MinGW 16.1.1-1.fc44)`, cmake 4.3.0.
- The release logs do not record the MinGW version, but the shipped DLL's own DWARF does:
  `strings -a package/kphasor.dll | grep -oE 'mingw-(gcc|crt)-[0-9.]+-build'` finds
  `mingw-gcc-16.1.1-build` (692 hits) and `mingw-crt-13.0.0-build` (184). That is the same toolchain as
  this rebuild. The base build also reproduces the shipped file sizes byte for byte (18482001 and
  99978).
- Both builds finished with 0 errors and 0 warnings in the logs. The whole run took 5m03s.

Verbose-log flag audit:

```
            compile lines  with -ffile-prefix-map  with -fmacro-prefix-map  NDEBUG  link(-shared)  link with -s
base              54                0                       0                 0          2              0
patched           54               54                      54                 0          2              2
```

Coverage check: `grep 'KP_MINGW_CXX}'` finds two compile sites the patch does not touch,
`src/api/entity.cmake:90` and `src/api/support.cmake:110`. Neither object is linked into either DLL:

- the kphasor link line takes `KP_RT_WIN32_OBJECTS`, `KP_WIN32_OBJECTS` and `KP_HOOKS_WIN32_OBJECTS`
  (runtime.cmake:131-132)
- neither target is built by `--target kphasor_dll binkw32`
- the 54-of-54 audit above confirms this

They need the same flags only if their objects ever ship.

Output hashes (scratch builds, not for release):

```
base    kphasor.dll a24c18e6...5f6d (18482001 B)  binkw32.dll 14795bd3...4ba2 (99978 B)
patched kphasor.dll 0c12f172...968c (4233216 B)   binkw32.dll fdc39ab6...01b2 (17920 B)
shipped kphasor.dll 4e14d0fe...95c8 (18482001 B)  binkw32.dll fce8c207...ec34 (99978 B)
```

## (2) scan_release_zip.py, read-only

Scanner: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/tools/scan_release_zip.py`
(sha256 be2fedae...98fa). It has no file mode, so each pair of DLLs was put in its own scratch ZIP under
`kotorphasor-preview/`, matching the gate's entry names.

```
python3 scan_release_zip.py --allow '*.dll' <n>-dlls.zip
shipped  exit=1  ok=False  markers=21  finding_counts={'marker': 9}  (all kphasor.dll "/home/", lines 112954..114413)  unchanged=True
base     exit=0  ok=True   markers=21  finding_counts={}  expected=2 (dll magic)  unchanged=True
patched  exit=0  ok=True   markers=21  finding_counts={}  expected=2 (dll magic)  unchanged=True
```

The shipped ZIP is the positive control. It reproduces the 9 `kphasor.dll "/home/"` findings the patch
note reports; the scanner merges the 18 raw strings into 9 text "lines".

`base` passing shows the scanner blind spot: its `FIXED_MARKERS` (scan_release_zip.py:114-116) contain
no `/tmp/`, so 18 scratch-root paths go unflagged. The real release builds under `/home/...`, where the
scanner does see them. The flags remove the prefix whatever the root is, and the base-vs-patched count
proves that.

## (3) Behavioural surface: objdump -p / -h

```
kphasor.dll   imports 317 / exports 0 (no export table) in shipped, base and patched; import sets identical (shipped==patched, base==patched)
binkw32.dll   imports 33  / exports 59 in all three; import and export sets identical
Entry point   0x11f0 in all; Subsystem 3; DllCharacteristics 0x0140 (DYNAMIC_BASE|NX_COMPAT) in all
Characteristics 0x2106 -> 0x230e  (+LOCAL_SYMS_STRIPPED, +DEBUG_STRIPPED header bits only)
Data directories (patched vs shipped): same set: Import, BaseReloc, TLS, IAT. No Load Config directory in any build.
```

Section sizes in bytes (kphasor.dll):

| section | shipped | base | patched | patched-base |
|---|---|---|---|---|
| .text | 3197008 | 3197008 | 3197008 | 0 |
| .data | 7152 | 7152 | 7152 | 0 |
| .rdata | 447964 | 447804 | 447228 | -576 (shorter `__FILE__` strings) |
| .sxdata | 4 | 4 | - | dropped |
| .eh_frame | 484556 | 484556 | `.eh_fram` 484556 | 0 (renamed, see below) |
| .bss | 930216 | 930216 | 930216 | 0 |
| .idata | 8876 | 8876 | 8876 | 0 |
| .tls | 8 | 8 | 8 | 0 |
| .reloc | 85436 | 85424 | 85432 | +8 (page layout) |
| .debug_* (9 sections) | 11 986 455 total | same | - | removed by -s |

Section sizes in bytes (binkw32.dll): `.text` 5600, `.data` 44, `.rdata` 1724, `.bss` 140, `.edata` 3703,
`.idata` 1024, `.tls` 8, `.reloc` 524. These are identical in all three. `.eh_frame` (1868) becomes
`.eh_fram` (1868). The nine `.debug_*` sections (60 KB) are removed.

So the 18 MB DLL was mostly DWARF. The compile lines have no `-g`; the `.debug_*` sections come from
Fedora's prebuilt static runtime. The `DW_AT_comp_dir` values in the base DLL are
`/builddir/build/BUILD/mingw-crt-13.0.0-build/...` (92), `mingw-gcc-16.1.1-build/.../libstdc++-v3/...`
(99), `.../libgcc` (10) and `mingw-winpthreads-13.0.0-build/...` (7). No LuaJIT or project unit
appears, and no user path. `-s` shrinks kphasor.dll from 18482001 to 4233216 bytes.

Code identity (base vs patched `.text`, extracted with `objcopy -O binary -j .text`):

- binkw32: the address-normalized instruction streams are equal (1600 = 1600, 0 non-equal blocks).
- kphasor, bytes: 69407 bytes differ. Relocation sites in `.text` are at identical offsets in both
  builds (39185 relocations each). All differing bytes except 162 fall inside a base-relocated 32-bit
  word.
- kphasor, the other 162 bytes: all of them sit inside the rel32 fields of 81 branches to absolute
  address 0 (68 `call 0` and 13 tail `jmp 0`). The check confirmed the 162 offsets are a subset of those
  fields, and that every site decodes to target 0 in both builds.
- Those 81 branches go to weak-undefined symbols in libstdc++'s transactional-memory clones:
  `__ZGTtNSt13runtime_errorD0Ev` and the other `_ZGTt*` functions, plus `_txnal_cow_string_*`.
  objdump labels them `AddVectoredExceptionHandler`, the nearest symbol at address 0. Their
  displacement is `0 - (ImageBase + rva + 5)`, so it changes only with the image base.
- Image base: ld's auto image base is derived from the output path. It is 653c0000 shipped, 66a40000
  base and 6b540000 patched, so it differs between any two builds anyway (DYNAMIC_BASE is set).
- Normalized disassembly matches for the first 847770 of 866851 instructions. The remainder is
  `.gcc_except_table` data merged into `.text`, which has 0 differing bytes; the objdump disassembly
  only desyncs there because the stripped file has no symbol boundaries.

Stripping side effects, both checked:

- **`.eh_frame` → `.eh_fram`.** `ld -s` drops the COFF string table, so section names longer than 8
  characters are truncated. The unwinder finds frames through crtbegin's `__EH_FRAME_BEGIN__` address,
  not the section name.
  - Check: a minimal `throw`/`catch` program built with the same compiler, `-O2 -static -s`, has a
    section `.eh_fram` and prints `caught boom` with exit 0 under wine. So does the unstripped build.
  - DLL check: a DLL built with `-O2 -shared -static -static-libgcc -static-libstdc++ -s` has
    section `.eh_fram`. Its export throws and catches `std::runtime_error` internally. Loaded with
    `LoadLibraryA` from a small host EXE under wine, it returned `probe=42` with exit 0 (d_s.dll).
    The unstripped control (d_full.dll, `.eh_frame`) gave the same result.
  - `-Wl,--strip-debug` is **not** a way to keep the name. That build (d_sd.dll) also shows
    `.eh_fram`, and also catches (probe=42). Any strip truncates the name here.
  - These tests used a scratch WINEPREFIX under /tmp. They were not the game.
- **`.sxdata` (4 bytes) dropped.** The SafeSEH table is only used through the Load Configuration
  directory, and no build has one (data directory listing above). The loader never read it.
- **Self-symbol readers.** A grep of `src/` for `dbghelp`, `SymFromAddr`, `SymInitialize`, `StackWalk`,
  `backtrace`, `CaptureStackBackTrace`, `IMAGE_SYMBOL`, `PointerToSymbolTable` and `NumberOfSymbols`
  finds nothing. No code reads the DLL's own COFF symbols or DWARF, so removing them changes nothing
  at runtime.

## (4) Asserts still compiled in

- `-DNDEBUG` is absent from all 5 patched CMake files and from every command in the verbose build log
  (0 hits).
- `kphasor.dll` still imports `msvcrt!_assert` (hint 0x0122) in shipped, base and patched.
- Assert-expression strings (`strings -a | grep -c '&& "'`) number 104 in shipped, base and patched.
  Examples: `(g.CurrentWindowStack.Size > 1) && "Calling End() too many times!"` (2) and `GImGui != __null
  && "No current context..."` (2).
- The 18 `IM_ASSERT` `__FILE__` strings are present, mapped to `./...`.

The patch note also claims that project `assert()` calls in `src/api/structs.cpp` and
`src/hooks/trampoline.hpp` would be lost to `-DNDEBUG`. That claim **does not hold** for this export.
`grep -rnE '(^|[^_a-z])assert\(' src | grep -v static_assert` finds no matches, and no `<cassert>` or
`<assert.h>` is included anywhere. trampoline.hpp:46 is a `static_assert`, which NDEBUG does not
affect. The only runtime asserts in the DLL are ImGui's `IM_ASSERT`, which maps to `assert` and
therefore to `_assert`. The ruling to drop NDEBUG is still what keeps those live.

## Release folder untouched

- `find /home/brunner56/kp-release-20260927 -newermt '2026-09-27 14:45' | wc -l` → `0`.
- `sha256sum package/*.dll build/*.dll` matches `build-artifacts.json`: kphasor 4e14d0fe...95c8,
  binkw32 fce8c207...ec34.

## Cleanup

`/tmp/kp-rebuild-verify` was removed after this report was written: both source copies, both builds,
the ZIPs, the objdump dumps and the wine test prefix. `wineserver -k` ran first. After cleanup,
`ls /tmp/kp-rebuild-verify` prints `No such file or directory`. The report is at
`/home/brunner56/kp-live-20260922/release-rebuild-verify.md`.

## Grill me

1. **Does the `.eh_frame` → `.eh_fram` rename break C++ exceptions inside the game?** (weakest)
   Checked under wine, not in the game.
   - A static `-s` DLL from the same toolchain has section `.eh_fram`. Loaded under wine, it throws
     and catches `std::runtime_error` (`d_s.dll probe=42 exit=0`). So does a stripped EXE
     (`t_s.exe`: `caught boom`).
   - Registration goes through crtbegin by address, and kphasor `.text` is code-identical.
   - `--strip-debug` also truncates the name (d_sd.dll: `.eh_fram`), so there is no cheaper strip
     that keeps it.
   - If it ever failed in-game, the fallback is to drop `-s` entirely. The prefix maps alone remove
     the 18 path strings, which live in `.rdata`; `-s` only removes symbol and debug data.
   - Still unverified: unwinding inside the real game process.
2. **Is a /tmp build proof for a /home release?** On its own, no. That is why the unpatched control
   under the same root exists: 18 scratch-root hits there, 0 in the patched build, and 18 mapped `./`
   strings. The maps replace the literal `${CMAKE_SOURCE_DIR}`, which is the release's
   `/home/.../source` when it builds there. All 18 base paths begin with `<SRC>`, and none uses a
   symlink-resolved or other root. The actual `/home` rebuild was not run, because it would have to
   write into kp-release.
3. **Why does the scanner pass the control build?** Its markers have no `/tmp/` (scan_release_zip.py:114).
   The scanner is not the evidence here; the counts table is. Adding `/tmp/` to `FIXED_MARKERS` would
   close the gap, but it is a separate change for the owner.
4. **Were any compile sites missed?** Two `KP_MINGW_CXX` sites are unpatched, entity.cmake:90 and
   support.cmake:110. Their objects are not in either DLL: the runtime.cmake:131-132 link inputs don't
   include them, and all 54 of 54 compile lines in the targeted build carry both maps.
5. **Is this the same compiler as the release?** The release logs do not name the MinGW version. The
   base build matches the shipped file sizes exactly (18482001 and 99978), and every section size
   matches except the path-dependent `.rdata` and `.reloc`.

Open question I could not settle: in-game C++ exception unwinding through a stripped kphasor.dll
(Grill 1). A wine DLL test passes. A single live run that throws and catches inside kphasor.dll
would settle it.
