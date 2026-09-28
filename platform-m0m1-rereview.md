# Platform M0 + M1 fix round: independent re-review

Reviewer: independent. I did not read the writer's fix-round prose until after my own runs. I did read the writer's failure-path tests in `tools/kp_hooktool_x64.cpp` (lines 370-430 and 531-680) before writing `probe.cpp`, so my seam modes resemble theirs. The real-kernel two-VMA cases, the foreign-chain shape and the mutants are my own. The source was read only. No git reset, stash, staging or commit was run. No game or Wine ran, and the live-game lock was not touched.

- Worktree: `.worktrees/lua-boundary-validation`
- Scratch area: `/home/brunner56/kp-live-20260922/review-probes-m0m1-r2/`, which holds `build/`, `fuzz/`, `probe.cpp` and `mut/`.

FAIL threshold, the same as the first review: any Critical or Important fails the milestone.

## Commands and outputs

### Build and ctest

```
cmake -S <worktree> -B review-probes-m0m1-r2/build -G Ninja                 -> cfg=0
cmake --build ... --target kp_machotest kp_hooktool_x64 kp_imagetool       -> 19/19, no errors
host-cmd ctest -R "kp_machotest|kp_imagetool_macho_test|kp_hooktool_x64"
  -> 3/3 passed ("100% tests passed, 0 tests failed out of 3"); kp_imagetool_macho_test 42.70 s
./kp_hooktool_x64 selftest                                                  -> PASS 654 checks
```

### I1 decoder differential against capstone 5.0.7

I used my original `enum.py` and `fuzz.py` without changes. `dec_cli` was rebuilt against the current `decode.cpp`. Python ran through host-cmd, because the venv interpreter lives on the host.

```
red   (old dec_cli from review 1): echo 66480512345678 | dec_cli -> "5 0 0 0 -"
green (rebuilt):                   echo 66480512345678 | dec_cli -> "7 0 0 0 -"
                                   echo 6605123456     | dec_cli -> "4 0 0 0 -"   (66 alone still imm16)
                                   echo 48660512345678 | dec_cli -> "0 ... R"     (REX before 66 refused)
enum.py: cases 1641904, kp-accepted 1129845 -> 930579 ok + 199266 cs-invalid; 0 LEN, 0 RIP rows
fuzz.py 300000 2: accepted=189067 len_mismatch=0 rel_mismatch=0 cs_invalid=23953   (was 234 LEN)
```

The two buckets add up: 930,579 + 199,266 = 1,129,845 accepted. So no valid instruction has a length mismatch. The fix is at decode.cpp:178: `immz = opsize && !rex_w ? 2 : 4`. MovImm with REX.W is still imm64.

The writer counted 3,762 LEN rows in review 1 and I counted 3,786. The 3,762 figure is consistent with the ok delta: 930,579 − 926,817 = 3,762. My earlier figure was a miscount. Conceded.

### I2 and I3: independent forked-child probe

`probe.cpp` is my own harness. Its target code sits in pages I map myself. The foreign hook is `movabs rax; jmp rax` through a separate stub, which is a different chain shape from the writer's.

```
g++ -std=c++20 -O1 -I<wt>/src probe.cpp <wt>/src/hooks/x64/{decode,trampoline}.cpp -o probe && ./probe
PASS  I2 dtor after foreign chain: trampoline kept, chained call works, leak counted
PASS  I2 move-assign after chain; reused Detour installs+uninstalls cleanly, no extra leak
PASS  I2 move-construct from installed: source inert, one uninstall, no leak
    status=ProtectFailed detail=mprotect RW refused; nothing written
PASS  real kernel: RW refused on MAP_SHARED O_RDONLY r-x file mapping -> nothing written, no page left behind
    raw mprotect(2 pages, RW) = -1 errno=13 page0=rw-p page1=r-xs
    status=ProtectFailed detail=mprotect RW refused; nothing written page0=r-xp page1=r-xs
PASS  real kernel PARTIAL mprotect over two VMAs (anon r-x | shared-RO file r-x): page0 resealed, nothing written
    status=ProtectFailed detail=... previous bytes rolled back but the page is left RW, not executable page0=r-xp page1=rw-p
PASS  seam two-page: restore refused on page1 only -> rolled back; page0 r-x, page1 rw, not installed
    status=ProtectFailed installed=1 detail=... and rollback refused; new bytes left in place page0=rw-p page1=rw-p
PASS  seam two-page: restore AND second RW refused on page1 -> patch live, installed; page0 state?
    retry on the dead page: Ok, page=rw-p
PASS  seam: exec refused once on install ..., then retry install
      (label corrected in probe.cpp after the run: g_mode=1 refuses EVERY PROT_EXEC on the page,
       so this is the exec-ALWAYS-refused case; that is why the page ends rw-p. The writer's
       once-refused case reseals to r-xp.)
ALL PROBES PASS (0 failing)
```

The "raw mprotect" line is the kernel itself refusing part of a two-VMA call. It changed page 0 to `rw-p` and then returned EACCES on page 1. The engine's `reseal(s, prot)` after a failed RW flip (trampoline.cpp write_code) put page 0 back to `r-xp`. The writer listed this path as "code reading only". It now has a real-kernel run.

### Red: mutants of trampoline.cpp

Each mutant is built from the current source with one fix reverted, under `mut/`.

| Mutant | What is reverted | My probe | Writer selftest |
|---|---|---|---|
| `i2_old_abandon` | abandon() becomes `if (installed_) uninstall(); release();` | 2 FAIL (dtor child SIGSEGV) | I2 dtor, move and protect FAIL (SIGSEGV) |
| `i3_no_rollback` | write_code returns ProtectFailed right after a refused reseal, with no rollback | 2 FAIL (one SIGSEGV) | I3 once, always and stuck FAIL; bytes `ff 25 ...` left in place |
| `rw_no_reseal` | drops the `reseal()` after a refused RW flip | 1 FAIL (real partial-mprotect child SIGSEGV) | **PASS 654 checks** (gap, see m6) |

Red then green holds for I2 and I3. The current source passes everything above.

## Findings status

| ID | Status | Referent |
|---|---|---|
| I1 | Closed | decode.cpp:178; enum 0 LEN and fuzz 0 LEN on valid encodings; old binary gives 5, new gives 7 |
| I2 | Closed | `Detour::abandon()` leaks the page and counts it only when uninstall fails *and* `installed_` stays true. The probes "I2 dtor after foreign chain" and "I2 move-assign after chain" pass, and the mutant crashes. Leak accounting is correct: +1 per abandoned hook, 0 on a clean uninstall, and a reused Detour adds nothing. |
| I3 | Closed | write_code rolls back while the page is RW and then reseals. `now_new` drives install and uninstall ownership. Seam probes on one and two pages pass, and the real-kernel refusals pass. Mutant red. |
| m2 | Closed (heuristic) | Writer's plan tests (18 red then green); limits documented in trampoline.hpp:24-29 |
| m3 | Closed | Split AllocFailed detail at trampoline.cpp install; header documents the target-centred search |
| m4 | Closed | `prot_` is recorded from /proc/self/maps; writer's r-- test; guard covers copy_code, mprotect, __errno_location and the seam |
| m1, m5 | Open, out of scope | unchanged |

## New findings (fix-round code)

| ID | Sev | Finding | Evidence |
|---|---|---|---|
| m6 | Minor | The writer's selftest does not cover the "RW flip refused on a two-mapping span" reseal. The `rw_no_reseal` mutant passes all 654 checks. My real-kernel probe does catch it: the child is killed by SIGSEGV because page 0 is left `rw-p`. Suggestion: add the anon plus shared-O_RDONLY-file two-VMA case from probe.cpp to the selftest. | mut table above |
| m7 | Minor (doc) | FAILED RESTORE, third outcome. The header says "the patch is live ... installed() true" but does not say the page(s) are left RW and not executable. Calling the target before a successful `uninstall()` faults. The detail string says only "new bytes left in place". The writer's own test does not call `fn` in that state. | probe: `installed=1 ... page0=rw-p page1=rw-p` |
| m8 | Minor | `install` on a page already left dead (`rw-p`) by an earlier failed install returns Ok. It records rw- as the protection and leaves the target non-executable. This is consistent with "treat that page as dead" and with the deliberate r-- test (m4). There is no guard against hooking a non-executable page. | probe: `retry on the dead page: Ok, page=rw-p` |
| m9 | Minor (partly verified) | Lazy binding. write_code reads `errno` only after a refused reseal, while the target page is RW. If `__errno_location` is still unbound in the host's PLT, ld.so's resolver runs at that moment, and the guard does not cover ld.so pages. This only matters when the hook targets ld.so or the host's PLT page. `mprotect` is bound earlier by the trampoline RX seal, so it is not affected. | The built `kp_hooktool_x64` has no BIND_NOW/FLAGS entry in `readelf -d` (so it links lazily), and `objdump -d` shows 4 `call __errno_location@plt` sites. Whether the first call ever lands inside the RW window was not run. |

Attacks that found nothing:

- **Test seam in production.** `g_protect` is file-static. It is set only by `testing::set_protect_hook`, and the only caller is `tools/kp_hooktool_x64.cpp:401`. `kp_hooks_x64` is linked only into `kp_hooktool_x64` (hooks.cmake:82). The referent is `grep -rn -I -e kp_hooks_x64 -e x64/trampoline -e set_protect_hook src CMakeLists.txt tools`, run over all file types: 10 hits, all in hooks.cmake, trampoline.{hpp,cpp} and kp_hooktool_x64.cpp. A whole-worktree grep that also covers scripts/ and data/ timed out on the slow disk, so those directories are not covered. (unverified there). No script path reaches it. The seam's own address is in the page guard. It cannot be triggered in production without a native C++ caller.
- **Rollback when the write itself partly fails.** `copy_code` cannot fail partway except by faulting. The real partial case is the mprotect call that fails partway across two VMAs. The flip path (real kernel run) and the reseal path (seam that emulates the kernel's partial application) both come out consistent. `now_new` matches the bytes in every probe.
- **Move-construct from an installed Detour.** The source becomes inert, exactly one uninstall happens, and no leak is counted.
- **Leaked-trampoline accounting.** A plain `size_t` that is not atomic. The header documents the engine as not thread-safe (trampoline.hpp:67-68).

## Writer's Grill-me section

The fix round has no Grill me section. I used the writer's "Remaining limits" as the nearest equivalent and attacked the weakest item first.

claim: "a real two-mapping span ... The two-page reseal path is covered by code reading only"
referent: probe `real kernel PARTIAL mprotect over two VMAs`; raw kernel partial-apply line above
checked: ran it; also the `rw_no_reseal` mutant
verdict: holds, and it is now run on a real kernel. The writer's selftest still does not guard it (m6).
confidence: high

claim: "Callers must check installed(), not only the status"
referent: probe `installed=1` with ProtectFailed; trampoline.hpp:92
checked: ran it
verdict: holds. The page-state wording is incomplete (m7).
confidence: high

claim: "I2 fixed"
referent: probe P1 and P2 plus the `i2_old_abandon` mutant SIGSEGV
checked: ran it
verdict: holds
confidence: high

claim: "I3 fixed"
referent: seam probes plus the `i3_no_rollback` mutant
checked: ran it
verdict: holds for the mechanism. A real SELinux execmod denial was not run here. The host is `Enforcing`, but `selinuxuser_execmod --> on` (host-cmd getsebool), so no execmod denial is possible without changing security policy, which I did not do. The probe was also rerun on the host through host-cmd: all probes pass.
confidence: high for the seam, medium for real execmod

Grill questions the writer missed:

1. Does `install` refuse a non-executable target? No (m8).
2. Does the selftest fail if the RW-flip reseal is deleted? No (m6).
3. What page state does the "rollback refused" outcome leave? RW (m7).

Unsettled question: does a real SELinux execmod denial land in outcome 1 (old bytes, page RW), as the header predicts? The check that would settle it is to run `probe` on an enforcing SELinux host, with `deny_execmem`/execmod denied for a private file-backed text page, hooking a function in a `.so` mapped from disk.

## Weighing

- I1, I2 and I3 are closed, each with red evidence that I reran myself and green evidence. The fuzz and the enumeration show 0 length mismatches on valid instructions.
- m2, m3 and m4 are closed.
- The new findings are Minor only: one test-coverage gap, two documentation or guard gaps in already-documented dead-page states, and one unverified lazy-binding edge.
- M0 is unchanged and `kp_machotest` and `kp_imagetool_macho_test` pass.

M0+M1 re-review verdict: PASS
