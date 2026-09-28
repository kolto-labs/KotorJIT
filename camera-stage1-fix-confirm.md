# Camera Stage 1 fix confirmation (round 2)

Worktree: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation` (read-only; no git writes, no game).
Scratch: `/home/brunner56/kp-live-20260922/review-probes-camera-r2/` (`matrix.sh`, `mut.sh`, `mut_unfixed.cpp`, `va.py`, `dis.sh`, `kpc_*` binaries, `warn_*.txt`).
Compiler: g++ (GCC) 16.2.1, run on the host via `host-cmd`. LuaJIT: 32-bit `libluajit.a` copied from `/tmp/kp-w1-build` (configured from this worktree).

The fixed assertion now sits at `tools/kp_cameratest.cpp:104`. Two comment lines moved it down from 103.

## Blocker I1: excess precision at the raw_28 assertion

claim: "static_cast<float> at 103 fixes kp_cameratest under -std=c++20 -m32"
referent: build and run matrix (`matrix.sh`). Every build has 0 warnings with -Wall -Wextra, rc=0, and prints `camera checks passed: 1818`:
```
std_O3      -O3 -DNDEBUG -std=c++20                         rc=0 1818
std_O0      -O0 -std=c++20                                  rc=0 1818
std_O2      -O2 -DNDEBUG -std=c++20                         rc=0 1818
sse_O3      -O3 -DNDEBUG -std=c++20 -msse2 -mfpmath=sse     rc=0 1818
gnu_O3      -O3 -DNDEBUG -std=gnu++20                       rc=0 1818
gnu_sse_O3  -O3 -DNDEBUG -std=gnu++20 -msse2 -mfpmath=sse   rc=0 1818
gnu_O0      -O0 -std=gnu++20                                rc=0 1818
std_fast_O3 -O3 -DNDEBUG -std=c++20 -fexcess-precision=fast rc=0 1818
__FLT_EVAL_METHOD__: 2 under -m32 -std=c++20; 0 under -msse2 -mfpmath=sse
```
Mutation (`mut.sh`): the same file with only the two casts removed fails `rc=1 line 104: c.raw_28[0]==.1f*1&&...` under `-O3 -DNDEBUG -std=c++20`, and passes under SSE and gnu++20. So the test still detects the original failure, and the cast is what makes it pass.
checked: `matrix.sh`, `mut.sh` (both run via host-cmd). Scope of the change: `diff review-probes-camera/kp_cameratest_fixed103.cpp` (the prior reviewer's one-line fix) against the worktree file shows only the comment block differs (101-102 became 101-103). The assertion line is byte-identical, and nothing else changed, so no other check was weakened.
verdict: holds
confidence: high. Only a compiler other than GCC 16 (clang, MSVC) is untested. The cast rounds to float under any FLT_EVAL_METHOD, so it is not flag-dependent.

## Writer's weakest grill answer (SSE2 / gnu++20 unverified)

claim: "Unverified for SSE builds in this round."
referent: rows sse_O3, gnu_O3 and gnu_sse_O3 above. All pass with 1818 checks.
checked: `matrix.sh`
verdict: holds. This gap is now closed.
confidence: high

## No other excess-precision assertion

claim (brief): no other test line has the same pattern
referent:
- The fixture (`tools/tests/camera_backend_fixture.hpp:32-36`) stores 6.25f, 20.f, 80.f, 3.5f, 55.f, `10.f+i` and `20.f+i`. All are exactly representable in binary, so an x87 long double compare gives the same answer. The only inexact value is `.1f*(i+1)` at line 35.
- `kp_cameratest.cpp:99,100,104` compare against exact literals. Line 104 compares against the cast `.1f` terms.
- `kp_cameratest.cpp:213-214` (Lua) compare doubles with exact values. Line 215 uses `math.abs(q[1]-0.1)<1e-6`.
- Line 177 (`value_failures`) stores NaN and ±inf and checks only the failure type, with no float equality.
- grep of `kp_cameratest.cpp` for float arithmetic inside `==` matches only line 104.
checked: grep of the test and fixture; lines read in full
verdict: holds
confidence: high

## New citations decode against the image

Image: `/home/brunner56/biodecompwarehouse/kotorxid/output/binaries/K1__k1_win_gog_swkotor.exe/artifacts/raw_image`, sha256 `9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435` (recomputed). ImageBase is 0x400000, and file offset = VA - 0x400000.

claim: options_mode 0x6d (bindings json:284) "call GetClientOptions 0x5ed700 then cmp byte [eax+0x6d],5, bytes e8ba76ffff80786d05 @0x5f6041; same cmp 80786d05 also @0x60b94b and @0x615b71"
referent: `va.py` shows all bytes match, and the call target resolves to 0x5ed700. objdump shows:
```
5f6041: e8 ba 76 ff ff  call 0x5ed700 ; 5f6046: 80 78 6d 05 cmp BYTE PTR [eax+0x6d],0x5
60b946: call 0x5ed700   ; 60b94b: 80 78 6d 05 cmp BYTE PTR [eax+0x6d],0x5
615b6c: call 0x5ed700   ; 615b71: 80 78 6d 05 cmp BYTE PTR [eax+0x6d],0x5
```
Nit: at 0x5f6041 the cmp is at 0x5f6046, so the address marks the start of the 9-byte call+cmp run. The text says so. The two extra sites also follow a `call 0x5ed700` on `[0x7a39fc]+4`, which is stronger than the text claims.
checked: `va.py`, `dis.sh`
verdict: holds
confidence: high

claim: raw_38 0x38 (json:633) "ctor (vtable 0x75165c @0x639fee) mov [esi+0x38],edi 897e38 @0x63a011 through +0x40 @0x63a017; copy-ctor (vtable store @0x63ad94) 897e38 @0x63adb4 through +0x40 @0x63adba"
referent: objdump shows `639fee mov [esi],0x75165c`, `63a011 mov [esi+0x38],edi`, `63a017 mov [esi+0x40],edi`, `63ad94 mov [esi],0x75165c`, `63adb4 mov [esi+0x38],edi` and `63adba mov [esi+0x40],edi`. edi was zeroed (`xor edi,edi`) at 0x639fec and 0x63ad8f. Each store is in the same straight-line block as its vtable store, with no intervening branch or return.
checked: `dis.sh`
verdict: holds
confidence: high

claim: raw_50 0x50 (json:658) "ctor 897e50 @0x63a026 through +0x58 @0x63a02c; copy-ctor 897e50 @0x63adc6 through +0x58 @0x63adcc"
referent: objdump shows `63a026 mov [esi+0x50],edi`, `63a02c mov [esi+0x58],edi`, `63adc6 mov [esi+0x50],edi` and `63adcc mov [esi+0x58],edi`.
checked: `dis.sh`
verdict: holds
confidence: high

Side note, not a blocker: the "copy-ctor" writes zero to +0x38..+0x58 and does not copy from a source object. This matches the prior review's M6 (the raw fields are zero-initialised on that path). The label may be loose. The store evidence is still valid.

Offsets 0x6d, 0x38 and 0x50 match `src/api/camera_profiles.cpp:13,19`. The bindings json parses (`python3 -m json.tool`).

## Overlay consistency test

claim: overlay evidence edits keep `camera_profile_consistency_test` green
referent: `python3 tools/camera_profile_consistency_test.py` (run in the worktree, read-only) printed `Ran 5 tests in 26.911s OK`. `git status --short | wc -l` was 157 before the run and 157 after.
checked: that command
verdict: holds
confidence: high

## One question not settled

clang, and MSVC for the eventual Windows build, are not tested. Settling it needs one `clang++ -m32 -std=c++20 -O3` build of the same matrix. The cast makes the result independent of FLT_EVAL_METHOD, so this is low risk.

Camera Stage 1 fix: CONFIRMS
