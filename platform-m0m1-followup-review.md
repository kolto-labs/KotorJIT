# x64 detour engine follow-ups (m6-m9, m10 PROT_NONE/Unreadable): independent review

Reviewer is not the writer. I formed a view from trampoline.{hpp,cpp} and decode.cpp before I read "Follow-up" or "Follow-up 2".
Worktree was read-only. No game, no live-game lock, no git writes.
Scratch: /home/brunner56/kp-live-20260922/review-probes-m0m1-r3/ (fresh cmake -G Ninja RelWithDebInfo = -O2 -g, GCC 16.2.1).

## Own builds

- `build/kp_hooktool_x64 selftest` -> `PASS 654 checks`, rc 0, no FAIL lines (selftest.log).
- ctest -R "kp_machotest|kp_imagetool_macho_test|kp_hooktool_x64" (via host-cmd, targets kp_machotest kp_imagetool kp_hooktool_x64 built) -> `100% tests passed, 0 tests failed out of 3`: kp_machotest 0.01 s, kp_imagetool_macho_test 113.58 s, kp_hooktool_x64.selftest 0.86 s (ctest.log, rc=0). The first full `cmake --build .` attempt hung copying third_party/luajit for -m32 targets and was killed. Those targets are not needed for these tests.
- Reviewer probe r2/probe.cpp against the fresh libkp_hooks_x64.a -> `ALL PROBES PASS (0 failing)`, 8/8 (probe_r2.log).
- My own forked probe probe3.cpp -> 10 PASS, 1 FAIL (probe3.log). The FAIL is the mislabel below (grill #2).
- Mutant selftest output is saved per mutant in mut/<name>.log.

## Mutants (mut/)

The r2 mutants are whole copies of the pre-m6 engine. Run as they are, they fail the new m8/m10 tests on any old engine, which proves nothing. So I diffed each against fixround-m6m9/trampoline.baseline.cpp, took only the mutation and ported it onto the current trampoline.cpp.

| mutant | mutation | selftest |
|---|---|---|
| i2_old_abandon | abandon() unmaps after a failed uninstall | FAIL (I2 dtor/move/protect children, SIGSEGV) |
| i3_no_rollback | return right after a refused restore, no rollback | FAIL (I3 + m8 + m9 checks) |
| rw_no_reseal | drop the reseal after a refused RW flip (line 164) | FAIL 1/654 (m6 child SIGSEGV) |
| own_no_window | avail = kMaxStolen (m10 window ignored) | FAIL 3/654, children SIGSEGV |
| own_no_cut | never map "truncated" to the window stop reason | FAIL 2/654 (m8 split, m10 split) |
| own_prot_none_readable | treat PROT_NONE as readable in code_window | FAIL 2/654 (reports NotExecutable) |
| own_no_exec | delete the m8 exec check at trampoline.cpp:413 | PASS 654, survives |

own_no_exec survives because code_window() (trampoline.cpp:103) already refuses non-exec pages before install reaches line 413. Since m10, the m8 check at :413 cannot be reached. It is harmless defense in depth. The m8 behaviour is still tested, but now through code_window.

## Refusal cases (probe3.cpp, each in a forked child)

- PROT_NONE target -> Unreadable, "target page is unmapped or not readable". Same with expect bytes.
- Unmapped target -> Unreadable.
- 8 bytes of r-x, then `---` -> Unreadable. Bytes unchanged, no trampoline.
- 8 bytes of r-x, then unmapped -> Unreadable.
- expect_len 12 with an 8-byte window -> Unreadable. No read past the window.
- Guard page: 17 bytes of real code end exactly at a `---` page -> Ok, stolen 14. The call goes through the detour, original() returns 105, and uninstall restores the bytes.
- Exact edge: the 14 stolen bytes end on the page boundary, followed by `---` -> Ok, stolen 14. uninstall restores the bytes. The selftest guard child (kp_hooktool_x64.cpp:839) leaves slack (leave+ret), so this case is new.
- One byte short: 13 r-x bytes then `---` -> Unreadable. code_window has no off-by-one either way.
No child was killed by a signal.

## objdump, -O2 (tramp_O2.dis, host objdump on build/.../trampoline.cpp.o)

- 0 mprotect references, 6 `syscall`.
- The 3 `__errno_location@PLT` calls come right after `call *%rax`, the seam (0x480->0x490, 0x690->0x696, 0x763->0x76b).
- write_code's own body has one PLT call, memcpy at 0x801, before the flip.
- Writer's grep missed this: `page_size()` is called inside the window by reseal (0x6c3, 0x6d1, 0x745). Its cold path has `__cxa_guard_acquire@PLT`, `sysconf@PLT` and `__cxa_guard_release@PLT` (0x3d1, 0x3f5, 0x406).
- That cold path cannot run inside the window. The fast path at 0x3b0-0x3c2 is a guard-byte test and `ret`. install calls page_size before any flip: at 0xb81 and inside shares_engine_page/code_window. write_code also calls it at 0x7bc, before memcpy. uninstall needs an earlier install.
- So no PLT call runs inside the window. The claim is true, but it rests on that call order, not only on "no PLT symbol in the window".

## Claim blocks

claim: m6 fixed. The selftest has the real two-mapping partial-mprotect case.
referent: the rw_no_reseal mutation ported onto current code fails only m6 (child SIGSEGV). r2 probe "real kernel PARTIAL mprotect over two VMAs" PASS.
checked: mut/self_rw_no_reseal selftest; probe_r2.log
verdict: holds
confidence: high

claim: m7 fixed in wording. A doubly refused restore leaves the page RW and not executable, and that is documented and tested.
referent: trampoline.hpp:61-79; the i3_no_rollback mutation fails the I3 checks; r2 probe "restore AND second RW refused" PASS with detail "...the page left RW, not executable".
checked: mut/self_i3_no_rollback; probe_r2.log
verdict: holds
confidence: high on the seam. A real SELinux double refusal was not run (the writer says so too).

claim: m8 fixed. install refuses NotExecutable on a non-exec target page.
referent: the behaviour holds (m8 split and m8 dead-page checks pass). The check that enforces it is now code_window (trampoline.cpp:103), not the page_prot loop (:413) the writer cites. Deleting :413 still gives PASS 654.
checked: mut/self_own_no_exec
verdict: holds (behaviour). The referent in the writer's text is out of date.
confidence: high

claim: m9 fixed in code. Nothing in the RW window goes through the PLT or touches errno, except the test seam.
referent: tramp_O2.dis. No mprotect PLT; errno only after the seam. page_size() has PLT calls on its init path and is called in the window, but the init has always run before any flip (0xb81, 0x7bc).
checked: host objdump -dr on the -O2 object
verdict: holds
confidence: medium-high. It is static evidence plus call order. What would lower it: a build where page_size is first called from reseal, e.g. someone calls write_code from a new entry point.

claim (m10): a PROT_NONE target, an unmapped target, or a patch window running into PROT_NONE returns Unreadable and does not fault. A guard page next to complete stolen bytes still installs.
referent: probe3 cases above, all PASS in forked children. The own_no_window mutant makes 3 selftest children SIGSEGV.
checked: probe3.log; mut/self_own_no_window
verdict: holds
confidence: high for single-threaded layouts

## Grill answers, weakest first

1. "maps-then-read race is unguarded; covered by Not thread-safe". The race is real: code_window reads /proc/self/maps and memcmp/plan read later. But trampoline.hpp:88-89 only says install/uninstall "assume nothing else is executing the patched bytes". It says nothing about another thread changing or unmapping the target mapping. The header's m10 paragraph (:38-45) presents the check as before any target byte is read, with no TOCTOU note. The answer holds in substance: no hooker can defend against a concurrent munmap of its target. It does not hold as "already documented". Nit: add one clause to :88.
2. "Can a real plan failure be misreported as Unreadable? Only when the window cut an instruction." Does not hold. decode.cpp:229 (and :132 in the REX path) returns "truncated" for an over-15-byte instruction even when every byte is readable, because limit = min(avail, 15). Measured in probe3: the same 17-byte invalid instruction (10x 66, 8b 84 00 disp32) gives
   - fully mapped page: `DecodeFailed detail=truncated`
   - 20 readable r-x bytes before a `---` page: `Unreadable detail=target page is unmapped or not readable`
   All 17 bytes were on the readable page. It still refuses and writes nothing, so it is a mislabel, not a safety bug. Severity: nit. Possible fix: only map "truncated" to the stop reason when the failing decode's `avail - off < kMaxInsnLen`, i.e. the window was actually the limit (needs plan to expose the offset), or have decode say "instruction longer than 15 bytes" whenever at > kMaxInsnLen.
3. "m9 proven only by disassembly". That holds, with the page_size note above. I did not reproduce a lazy-binding fault either. A runtime proof would need a target sharing a page with a lazily bound resolver path, which is not worth building.
4. Guard page still installs. Holds (probe3 + selftest m10 guard child).
5. Why Unreadable and not NotExecutable. Holds. own_prot_none_readable shows the tests pin the difference.

## Questions the writer missed

- The m8 check at trampoline.cpp:413 cannot be reached since m10 (mutant survives). Keep it as belt-and-braces, but say so, or the next reviewer will think it is tested there.
- The m10 split test hard-codes 4096 (kp_hooktool_x64.cpp:832). Fine on x86_64 Linux. Noted only.

## Hand-off

One unsettled question: none of these checks show real-kernel behaviour for a doubly refused restore (SELinux execmod). Settling it needs a run on an SELinux-enforcing box with an execmod deny on a file-backed text mapping. Not checkable here.

## Verdict criterion

Does any finding let install or uninstall write or fault where it should refuse, or does any claimed fix fail its test?
- m6, m7, m8 (behaviour), m9 and m10 all hold on my builds and probes.
- Grill #2 does not hold as stated. Its effect is a wrong status label (Unreadable instead of DecodeFailed) on a refusal that still writes nothing. That is a nit, not a safety gap.
- The m8 referent (:413) is out of date and the race wording is missing. Both are doc nits.
- ctest 3/3 passed.

Nothing lets install or uninstall write or fault where it should refuse, and no claimed fix fails. Nits to carry: the Grill #2 mislabel (decode.cpp:229/:132 "truncated" for >15-byte instructions becomes Unreadable next to a non-readable page), the out-of-date m8 referent (:413 cannot be reached), and the missing TOCTOU clause at trampoline.hpp:88.

x64 follow-ups: CONFIRMS
