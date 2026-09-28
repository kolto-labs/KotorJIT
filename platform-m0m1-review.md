# Platform M0 + M1 independent review (correctness + adversarial)

Reviewer: independent. Worktree: `.worktrees/lua-boundary-validation`. Source was read only; nothing in it was edited. Scratch builds and probes are under `/home/brunner56/kp-live-20260922/review-probes-m0m1/`. No Wine or game ran, the live-game lock was not touched, and no retail bytes appear in this file.

FAIL threshold, written down before classifying: any Critical fails the milestone. So does an Important that makes the code break its own documented contract in a way that crashes or corrupts memory in a scenario the task names. A literal-but-misleading claim or an undefined-encoding looseness is Minor.

## Commands run

```
cmake -S <worktree> -B review-probes-m0m1/build -G Ninja                                   -> exit 0
cmake --build review-probes-m0m1/build --target kp_machotest kp_hooktool_x64 kp_imagetool  -> 19/19, no errors
host-cmd ctest -R "kp_machotest|kp_imagetool_macho_test|kp_hooktool_x64"                   -> 100% tests passed, 0 failed out of 3
```

Decoder differential against capstone 5.0.7 (scratch venv on the host):

- `review-probes-m0m1/fuzz/dec_cli.cpp` is a thin CLI over `decode()`.
- `fuzz.py` ran 300k biased random streams (prefixes, REX, 0F).
- `enum.py` enumerated every one-byte and 0F-map opcode, times all 256 ModRM values, times 3 SIB values, times 11 prefix sets.

```
fuzz.py 300000 2: accepted=189067 len_mismatch=234 rel_mismatch=0 cs_invalid=23953
enum.py: cases 1641904, kp-accepted 1129845
  926817 ok (length + RIP-relative flag + disp offset all agree with capstone)
  199266 capstone-invalid (architecturally undefined encodings)
  every length mismatch on a valid instruction is 66 + REX.W with an immz-shaped immediate:
    66 48 05 imm32 (add rax, imm32): kp len 5, capstone len 7
    same for 0D 15 1D 25 2D 35 3D A9 68 69 81 C7 F7/0-1
  RIP mismatches: 0
echo 66480512345678 | dec_cli  ->  "5 0 0 0 -"   (true length is 7)
```

An objdump cross-check of the capstone-invalid set was attempted and dropped. The objdump output desyncs on `(bad)` encodings, so the lengths it gives there mean nothing.

The dynamic probe program for the M1 failure paths was not built or run; the session stopped that step. Findings I2 and I3 below rest on code reading only and are marked that way.

## Findings

| ID | Sev | Area | Finding | Failure scenario | Evidence |
|---|---|---|---|---|---|
| I1 | Important | M1 decode | `immz = opsize ? 2 : 4` ignores REX.W precedence over `66`. With REX.W the immediate stays 32 bits. | A stolen `66 48 81/05/..` instruction decodes 2 bytes short. The trampoline copies a split instruction, and the patch overwrites mid-instruction. Compilers do not emit this form in prologues, so the practical risk is low, but it breaks the decoder's own "refusal is the cheap outcome" contract. Fix: `immz = (opsize && !rex_w) ? 2 : 4`. | decode.cpp:233; dec_cli output above; enum.py 3,786 mismatches, all 66+REX.W |
| I2 | Important | M1 lifetime | `~Detour()` and move-assign call `release()` (munmap of the trampoline) even when `uninstall()` failed with `PatchClobbered` or `ProtectFailed`. | A foreign hook chains on top of ours: uninstall correctly refuses, then the Detour goes out of scope and unmaps the trampoline. The target still reaches our detour through the foreign stub, and `original()` now points at unmapped memory. The next call crashes. This is the "uninstall when another hook chained" scenario named in the task. Fix: when uninstall fails, leak the page instead of unmapping it. | trampoline.cpp:268-271, 277-278, 294-298 (code reading; no dynamic run) |
| I3 | Important | M1 W^X rollback | `write_code` does not roll back when the RX restore fails. The new bytes are already written and the page is left RW, not executable. `install` then unmaps the trampoline and returns `ProtectFailed` with `installed_=false`. | This is the SELinux execmod case the header itself names. The target page is left non-executable and holds a jump to the detour, so any later execution on that page faults. The header's claim holds literally (it reports ProtectFailed and never goes RWX), but the state it leaves behind is not documented and is not recoverable. `uninstall` has the same shape. Fix: restore the original bytes while the page is still RW, attempt RX, and document that execmod is fatal after a write. | trampoline.cpp:142-157, 357-360, 374-375 (code reading) |
| m1 | Minor | M1 decode | About 199k of the accepted encodings are architecturally undefined. Examples: LOCK on non-lockable ops, mod=3 on memory-only 0F ops, any 0F 38 or 0F 3A third byte. The header calls the decoder an allowlist. | These only matter if the target is not real code. The caller's `expect` bytes mitigate that. | enum.py capstone-invalid bucket; decode.cpp:137-138, 180 |
| m2 | Minor | M1 plan | A short function that ends in a call to a noreturn function, followed by NOP padding, is planned Ok and its stolen range reaches into the next function. Only ret, traps, E9 and FF/4 stop the walk. | Hooking a tiny noreturn wrapper overwrites the first bytes of the next function. | trampoline.cpp:235-249 (code reading) |
| m3 | Minor | M1 alloc | `map_near` searches near the target, not near the RIP or rel32 referents. It fails safe (OutOfRange). The AllocFailed detail string says "within +/-2GiB" even on the plain-mmap path. | A spurious refusal when a referent lies far from the target, and a misleading diagnostic. | trampoline.cpp:182-208, 325-329 |
| m4 | Minor | M1 W^X | `write_code` always restores RX instead of restoring the original protection, and the own-page guard does not cover libc `mprotect`/`memcpy`. | Hooking a libc function on the same page as mprotect or memcpy faults. A page that was RWX or R-only before comes back RX. | trampoline.cpp:151, 162-178 |
| m5 | Minor | M0 build | `kp_machotest` unity-includes `sha256.cpp`. The writer already listed this as a follow-up. | Build hygiene only. | writer report |

Null moves (the claim survived the question):

- Concurrency: "Not thread-safe" is documented in trampoline.hpp:30-31.
- Jumps from elsewhere in the function into bytes 1-13: listed as a limit in the writer report.
- rel8 branches (EB, 70-7F, E0-E3): refused (decode.cpp:220-227).
- RIP-relative instructions with an immediate after the displacement: the displacement offset and the `referent` computation are correct. There were 0 mismatches over 926,817 agreeing encodings, and `referent` uses the full instruction length.
- A prologue shorter than 14 bytes that ends in ret refuses (DecodeFailed). One that ends in jmp refuses (FlowEnds).
- A second Detour on an already-patched target refuses: `FF 25` decodes as FF/4 with ends_flow at offset 6.
- Page-spanning patches: `write_code` covers `[page_down(addr), page_down(addr+len-1)+page)`. Code reading only; no dynamic test.
- An AllocFailed failure writes nothing, because the allocation happens before any write.

## M0 (code reading plus the writer's ctest, which I re-ran)

| Attack | Result |
|---|---|
| offset+size overflow | Holds. `range()` checks `offset <= limit && size <= limit - offset` (macho.cpp:15-17), and the overlap arithmetic runs after that check. |
| fat64 offsets on a 32-bit build | Holds by construction: offsets are `uint64_t` and `limit = n`. Not rerun at -m32 here; the writer compiled -m32 with -Werror but only ran the tests at 64-bit. |
| alignment exponent | Capped at 15 before the shift (macho.cpp:151-152). |
| slice pointing at the header or table | Refused (`offset < table_end`). |
| zero-size slice | Refused. |
| cpusubtype masking | The high byte is masked on both sides and used for duplicate detection. x86_64 and x86_64h stay distinct, which matches lipo. |
| duplicate LC_UUID, or wrong size | Refused (macho.cpp:99-104). |
| thin file passed to `select_slice` | Returned as a whole-file slice only if the CPU matches. |
| Java class collision | count > 32 is refused. |
| thin-parser regression | `kp_imagetool_macho_test` passes (re-run above). |

No M0 findings above Minor.

## Claim blocks

claim: "`66` shrinks immz to 16 bits"
referent: dec_cli `66480512345678` gives 5; capstone gives 7
checked: enum.py, fuzz.py
verdict: does not hold under REX.W
confidence: high

claim: "Nothing is ever RWX"
referent: trampoline.cpp:146,151,326,345; the writer's `/proc/self/maps` test
checked: code reading, plus ctest pass
verdict: holds
confidence: high

claim: "Uninstall ... restores the original bytes and unmaps the trampoline"
referent: trampoline.cpp:371-381
checked: code reading
verdict: holds for `uninstall()`. The destructor and move-assign unmap even when uninstall failed (I2).
confidence: medium. A fork-child run of the chained-hook scenario would raise it to high.

claim: "An RX restore failure reports ProtectFailed ... does not fall back"
referent: trampoline.cpp:151-155
checked: code reading
verdict: holds literally. The state it leaves behind is patched and non-executable (I3).
confidence: medium. Not run dynamically.

claim: ctest 3/3 green
referent: host-cmd ctest output above
checked: re-run
verdict: holds
confidence: high

## Weighing

- M0 passes.
- M1: I1 is a real length bug, but no compiler emits that form in a prologue.
- M1: I2 crashes the process in a scenario the task names (uninstall with another hook chained, then the Detour is destroyed). By my FAIL threshold that fails M1, even though the evidence is code reading. The code path is short and direct: a failed uninstall is followed by an unconditional `release()`.
- M1: I3 is the documented execmod path, and it leaves the target non-executable.
- All three fixes are small and local.

M0+M1 verdict: FAIL
