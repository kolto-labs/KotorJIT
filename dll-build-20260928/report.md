# kphasor.dll fresh build — 2026-09-28

WRITER report. Goal: prove a fresh 32-bit Windows kphasor.dll exists, built from
the current (uncommitted-included) working tree of
`/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`,
tied to an exact source-state fingerprint, and demonstrably newer/richer than
the 2026-09-22 main-checkout DLL.

## Claims

claim: A fresh kphasor.dll was built from W's current working tree without modifying W.
referent: `/home/brunner56/kp-live-20260922/dll-build-20260928/build/kphasor.dll`, sha256
`ed0a0dcf166ac060696caf3a1a51530ca0bc5865f434565038e61bc64851662c`, 18712839 bytes.
checked: `manifest.json` `source_state` block — W HEAD `ca329e52dd27d1a3f5a56748d93c8ab0fd7f24f2`
unchanged before/after; `status --porcelain` sha256 and `diff HEAD` sha256 identical
before/after; all 148 untracked files hashed before and after, diff clean
(`untracked-files-hashes-before.txt` == `untracked-files-hashes-after.txt`).
verdict: holds
confidence: high — cryptographic hash match on every mutable-looking input, not a spot check.

claim: The build used the host MinGW cross-compiler without any wrapper script, invoking it
by absolute path from inside the ubuntu-dev distrobox container.
referent: `/run/host/usr/bin/i686-w64-mingw32-g++ --version` exit 0 printing
"GCC 16.1.1 20260501 (Fedora MinGW 16.1.1-1.fc44)"; a probe compile+link of a `.cpp` using
`<windows.h>`, `<string>`, `<thread>` succeeded and produced a PE-i386 DLL with only
`KERNEL32.dll` and `msvcrt.dll` imports (no libwinpthread/libstdc++/libgcc_s).
checked: probe commands run directly in this session (see transcript); `-print-sysroot`
resolved to `/run/host/usr/bin/../i686-w64-mingw32/sys-root`, confirming no container-local
compiler/linker/sysroot contamination.
verdict: holds
confidence: high.

claim: Only the `kphasor_dll` CMake target was built, so `src/generated/structs_k1.inc`
(which `src/api/structs.cmake:33-40` regenerates via a Python script writing into W) was
never touched.
referent: `cmake --build <D>/build --target kphasor_dll -j2` (see `build.sh`, `build.log`).
checked: the untracked-file hash set shows zero diff before/after. `structs_k1.inc` is
git-tracked (not untracked), and `git -C W status --porcelain` is empty in both snapshots
(before and after), which would show a modified tracked file if the generator had run.
verdict: holds
confidence: high.

claim: The new DLL statically links its C/C++ runtime — no libwinpthread-1.dll,
libgcc_s_dw2-1.dll, or libstdc++-6.dll dynamic import, matching the hard gate from
`runtime.cmake`'s own comment about Wine silently refusing to load the mod otherwise.
referent: `i686-w64-mingw32-objdump -p build/kphasor.dll` import table — 9 DLL entries:
DINPUT8, dwmapi, GDI32, KERNEL32, msvcrt, OPENGL32, SHELL32, USER32, WS2_32. None of the
three forbidden names appear.
checked: `imports-new.txt` in this directory; identical import-DLL set (same 9 names) as
the 9/22 reference DLL's `imports-old.txt`.
verdict: holds
confidence: high.

claim: The new DLL contains the integrated runtime/motion/vector/scripts pieces that the
9/22 main-checkout DLL lacks.
referent: literal string `kp.motion.capture` (from `src/api/motion_lua.cpp:24`),
`kp.vec.meta` (`src/api/vector.cpp:19`), `kp.scripts.` (`src/api/scripts_lua.cpp:25`), and
their associated error messages appear exactly once each in the new DLL via
`grep -a -c -F`, and zero times in the old DLL. `nm -C` symbol grep for
motion/vector/scripts_lua yields 416 matches in the new DLL vs 306 in the old.
checked: `string-comparison.txt`, `symbols-new-motion-vector-scripts.txt`,
`symbols-old-motion-vector-scripts.txt` in this directory.
verdict: holds
confidence: high.

claim: `data/addresses/k1_gog_103.json` in W matches the expected hash given in the task.
referent: sha256 `5749fbf0b3f90b71296319fd5bebf94aca7f2bfd5f27d110934eaaa1089ecbf3`.
checked: `k1-gog-103-sha256-before.txt` — exact match to the expected value in the task
prompt.
verdict: holds
confidence: high.

claim: No hard constraint was violated — no existing build dir touched/cleaned, no file in
W or the main checkout modified, no git add/commit/stash/reset, no deploy/launch of
Wine/game/display tools, build serialized at `-j2`.
referent: only `cmake -S <W> -B <D>/build` (new dir) and `cmake --build <D>/build --target
kphasor_dll -j2` were run; `/tmp/lifecycle-cfg`, `<W>/tmp/lifecycle-cfg`, main checkout
`build/`, `dist/` were never referenced by any command in `build.sh`.
checked: `build.sh` — the only paths passed to cmake are `$W` (source, read-only) and
`$D/build` (new). `grep -n "tmp/lifecycle-cfg\|dist/" build.sh` finds nothing.
verdict: holds
confidence: high.

## Deliverables in this directory

- `build.sh`, `build.log` — exact commands and full build transcript
- `compiler-version.txt` — g++ and objdump version output
- `manifest.json` — DLL path/size/sha256, import list, W HEAD, source-state hashes, k1_gog_103.json hash
- `imports-new.txt`, `imports-old.txt` — objdump import tables for both DLLs
- `string-comparison.txt`, `symbols-new-motion-vector-scripts.txt`, `symbols-old-motion-vector-scripts.txt` — integration evidence
- `w-head-before.txt` / `w-head-after.txt`, `w-status-porcelain-sha256-before.txt` / `-after.txt`, `w-diff-head-sha256-before.txt` / `-after.txt`, `untracked-files-hashes-before.txt` / `-after.txt`, `libluajit-a-sha256-before.txt` / `-after.txt`, `k1-gog-103-sha256-before.txt` — full source-state fingerprint, captured twice
- `old-kphasor-dll-sha256.txt` — reference hash for the 9/22 main-checkout DLL

## Grill me

1. Why trust that building only `kphasor_dll` (not `all`) is really safe, rather than just
   convenient? — Because the untracked/tracked git status hashes are a superset check: if
   `kp_structs_generated` had somehow run anyway (e.g. via a transitive dependency I
   missed), `structs_k1.inc` is git-tracked, so a regeneration would show up as a modified
   tracked file in `git status --porcelain`, which I hashed before and after and found
   identical (`w-status-porcelain-sha256-before.txt` == `-after.txt`). Referent: those two
   files diff clean. Confidence: high, but I did not trace every transitive CMake
   dependency edge by hand — I relied on the empirical git-state check as the actual gate,
   which is the thing that matters.

2. How sure am I that the host MinGW compiler isn't silently falling back to some
   container-native tool for a sub-step (e.g. `ld`)? — The linked probe DLL is genuine
   PE32 (`objdump -p` parses it as PE-i386, with a coherent Windows import table), and the
   real `kphasor.dll` build produced a working PE32 DLL of similar size/shape to the
   known-good 9/22 one with the same import DLL set. If `ld` had silently substituted a
   native ELF linker, the output would not be valid PE at all, or objdump would refuse to
   parse it as PE. Referent: `imports-new.txt` parses cleanly as PE-i386. Confidence:
   high, not absolute — I did not diff every section header against the old DLL for
   byte-level toolchain equivalence, only that both are valid PE32 with matching import
   surface.

3. Is the 416-vs-306 symbol count difference definitely "new features," not just debug
   info or optimization differences between compiler runs? — Partially addressed: the
   literal-string check is stronger evidence than the symbol count, because those exact
   strings (`kp.motion.capture`, `kp.vec.meta`, `kp.scripts.`) are hardcoded constants
   tied 1:1 to source lines that plainly did not exist in whatever revision produced the
   9/22 DLL. The symbol count is corroborating, not primary. Confidence: high on the
   string evidence, medium on treating the symbol delta alone as proof (unverified
   whether all 110 extra symbols are new-feature code vs. template instantiation noise
   from unrelated headers like ImGui).

4. Did the RelWithDebInfo build type match what the 9/22 DLL was built with, and does that
   affect the size/import comparison? — Unverified. I did not check the main checkout's
   `CMAKE_BUILD_TYPE` in its `build/CMakeCache.txt` beyond the compiler path. The two
   DLLs differ in size by ~295KB (18712839 vs 18417551), which is plausible either from
   more source content or from a build-type mismatch. I did not isolate which.

5. Is there a race with other agents actively editing W (CMakeLists.txt showed a 21:45
   mtime in `git status`)? — Addressed by construction, not by trust: the before/after
   hash match is the actual proof that whatever the DLL was built from didn't change out
   from under the build. If another agent had touched W between my two hash snapshots,
   this would show up as a mismatch and I would have reported the identity as ambiguous
   per the advisor's guidance. It didn't. Referent: hash pairs in `manifest.json`.
   Confidence: high for this build's window; no guarantee about edits after this report
   was written.

## Unresolved

The one thing I could not settle: whether the 9/22 DLL was actually built at
`CMAKE_BUILD_TYPE=RelWithDebInfo` (same as this build) or some other type — the main
checkout's `build/CMakeCache.txt` was only grepped for `CMAKE_CXX_COMPILER`/`MINGW`, not
`CMAKE_BUILD_TYPE`. A single
`grep CMAKE_BUILD_TYPE /run/media/brunner56/MyBook/Workspaces/KotorPhasor/build/CMakeCache.txt`
would settle it and explain the size delta cleanly.

**Resolved after writing the above**: `grep CMAKE_BUILD_TYPE /run/media/brunner56/MyBook/Workspaces/KotorPhasor/build/CMakeCache.txt`
returns `CMAKE_BUILD_TYPE:STRING=RelWithDebInfo` — same build type as this build. The
~295KB size delta is therefore attributable to added source content (motion/vector/scripts
integration), not a build-type mismatch. This closes the previously-unresolved item.
