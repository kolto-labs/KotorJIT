# W1 round 3 re-review: log escaping and installer minors

Independent reviewer, spec plus adversarial. Read-only on the worktree. Probes
and fake game folders are only under `review-probes-w1-r3/`. No game, no Wine,
no real game folder, no live-game lock, no git writes.

Bytes reviewed (sha256 matches the writer's "final bytes"):
- runtime.cpp `83fec910…`
- Install-KotorPhasor.ps1 `9bb54c24…`
- windows-native-receipt.ps1 `3f0d5ebf…`
- platform_receipt_test.py `e591fbaa…`
- overlay.cpp `539e4cbb…`

## Independent view (formed before reading the Grill section)

### 1. Every path into kotorphasor.log

| path | escaped? | script-controlled text? | referent |
|---|---|---|---|
| `Runtime::log` (banner, `script: %s`, sink lines, `kp-session` lines, fault notes) | yes, since round 3 | yes: print, kp.diagnostic and load errors all arrive through `runtime_log_sink` or `log("script: %s")` | runtime.cpp:278-319, :326, :757 |
| `platform::log` → `runtime_log_sink` → `Runtime::log` | yes (same choke point) | yes | runtime.cpp:326, :787 |
| overlay `kp-session` start/host/gl lines | yes: they call `Runtime::instance().log` | no. GL strings come from the driver. Control bytes in them are escaped. | overlay.cpp diff |
| `fault_guard.cpp emit()`: raw `CreateFileA`/`WriteFile` of `[fault] … site=…` | **no** | no. `site` is a literal at every `KP_HOOK_GUARD_BEGIN` call (hook_bodies.cpp:424…1224, commands.cpp:615/740/764), and `event_handler_common` gets the literals `"event.creature"`, `"event.door"` and so on (hook_bodies.cpp:1105-1120). | fault_guard.cpp:132-166 |
| `FaultFrame::note_fault` message | yes: goes through `Runtime::log` | no (same literal site) | fault_guard.cpp:~469 |
| **Lua `io` (and `os`) in every script state** | **no** | **yes, fully** | host.cpp:190 `luaL_openlibs(N)`. Only `debug.{get,set}metatable` and `getregistry` are removed. |
| proxy `kotorphasor-proxy.log` | n/a (different file) | no | binkw32.cpp:31 |

Result: every script text path into the log that does not go through `io` now goes through the one escape loop. The `io` path stays open.

### 2. Does the escape loop do what it says? (behaviour, not only source text)

I copied runtime.cpp:290-310 by line number (sha of the extracted lines `0998b029…`) into `review-probes-w1-r3/esc_harness.cpp` and compiled it (host g++, `-fstack-protector-all -D_FORTIFY_SOURCE=2`).
- `x\n[idle] KotorPhasor … (embedded role)\r\x01\x7f\tz` plus a literal backslash-n gives one physical line (`od -c`).
- Worst case: 1023 × `\x01` gives 4097 bytes out. That is `"[p] "` (4) + 4092 + `"\n"`, so the body is 4092 < 4096 and nothing is cut. 5000 bytes in is clipped to 1023 by vsnprintf, as before.
- Bytes ≥ 0x80 pass through. U+0085, U+2028 and U+2029 are not line ends for either parser: Python `split("\n")` (test.py:108) and PS `-split "`n"`. Probe R4 below shows this.
- An ASan build was not possible (host libasan missing). The bound follows from the arithmetic above.

### 3. Forgery probes on the round-3 runtime (`forge_r3.py`, `forge_r3.out`, `ps_parse_r3.out`)

Runtime-written lines go through `esc_harness`. `io` writes are raw. Each log is checked by the real `validate(..., log_bytes=…)` and by the receipt's own PS parser (lines 88, extracted verbatim), which agree on every case.

| case | Python validate --log | PS Get-SessionEvidence |
|---|---|---|
| R1 print `"\n"` + whole `[idle]` forged block | REJECT (9) | problems, no host |
| R2 kp.diagnostic lone `\r` joins | REJECT (9) | problems, no host |
| R3 load-error text `"\n"` + block | REJECT (9) | problems, no host |
| R4 U+2028 / U+0085 / U+2029 separators | REJECT (9) | problems, no host |
| R5 literal `\n` text | REJECT (9) | problems, no host |
| **IO1 `io` append after the overlay lines, `[idle]` banner + full block** | **VALID** | **id=0123…, host wine=no, problems empty** |
| IO2 `io` append at chunk load, before the overlay attaches | REJECT (10): doubled start/host/gl | same |

Old-DLL shapes (the writer's `receipt_forge.py`, rebased to r3):
- `[running]` banner: F1–F6 all REJECT (`receipt_forge.out`).
- The same logs with an `[idle]` banner (`receipt_forge_idle.py`): OLDIDLE_F1 and OLDIDLE_F3 are **VALID** (`receipt_forge_idle.out`). This reproduces the writer's `receipt_forge_idle_variant.r3.out`.

## Grill answers, weakest first

claim: (Grill 3) "On an old DLL a mod can write `[idle]` too … The receipt can only record the DLL sha, and the header and user doc say to check it against the shipped build."
referent: `receipt_forge_idle_variant.r3.out`; receipt ps1 header :33-35; user doc :69
checked:
- `validate()` checks `runtime.kphasor_dll_sha256` only for hex form (test.py `SHA_FIELDS` :59-61 and the HEX64 loop :206-209). No allowlist of DLL shas exists anywhere in the validator, fixtures or docs. OLDIDLE_F1/F3 → VALID.
- HEAD `overlay.cpp` has no `kp-session` line (`git show HEAD:src/devtools/overlay.cpp | grep -c kp-session` → 0). So every "older DLL" either writes no host line at all, or is an uncommitted W1 dev build. The only way to get a VALID receipt from one is for a script to forge the whole block.
- IO1 shows the round-3 DLL allows the same whole-block forgery through `io`.
verdict: holds as a disclosure; **does not hold as a control**. "Check it against the build you shipped" gives no reference sha, so nobody can act on it. The DLL-hash gap adds no attack beyond `io`, so it does not block.
confidence: high. It would change if a shipped-DLL sha list existed and `validate()` ignored it.

claim: (Grill 2) "print, kp.diagnostic and load errors all reach `Runtime::log` through `runtime_log_sink`, so this one choke point covers all three." Escaping is proven "at source level".
referent: runtime.cpp:326, :757; `test_runtime_log_escapes_line_breaks` (source grep); the writer's `/tmp/kp_esc_check.cpp`
checked:
- The table above: every non-`io` script path ends in `Runtime::log`. The raw-write path (`fault_guard emit`) takes only literal site names.
- Behaviour: `esc_harness` R1–R5 → one line each, all rejected by both parsers.
- In-suite coverage: the three `forged_banner_*` fixtures use a `[running]` banner (test.py:446). They are rejected by the `[idle]` anchor (:479) whether or not the escaping exists. So no in-suite test would go red if the escape loop were removed, except the source grep (:637-645).
verdict: holds for the code. The test coverage for escaping is only a source grep (minor, see W1R3-m2).
confidence: high. It would change if a script-controlled string reached `fault_guard emit()`.

claim: (Grill 1) "reparse-point guard … for an NTFS junction under Windows PowerShell 5.1": unverified.
referent: `inst2.out`: S1 and S2 refused, victim files kept
checked:
- The rerun on pwsh 7.3.12 gives the same results.
- No `Remove-Item -Recurse` is left (`grep -n Remove-Item`: 9 hits, none recursive).
- `Assert-NoReparsePoint` walks from the target up to the game root (:175-183) before pass 1 acts (:303-309).
verdict: holds on pwsh 7 and Linux symlinks. Unresolved on 5.1 with a junction (not checkable here).
confidence: medium. One `mklink /J` S1 run on Windows 5.1 settles it.

claim: (Grill 4) "No caller found" that meant to write several lines.
referent: `grep -rnE '(\blog|platform::log)\([^;]*\\n' src`
checked: my path table found no multi-line native caller. Tracebacks now show `\n\t` inline, which is expected.
verdict: holds
confidence: medium-high

claim: (Grill 5) "Is every manifest value checked in the form it is used? Yes for strings"
referent: installer :113-131, `inst.out` N4arr*, `inst2.out` N5actArr
checked:
- `Get-Field` returns `, $prop.Value`, and `Get-StringField` throws on a non-string.
- Rerun: N4arrBD, N4arrPath, N4arrSha, N4schema and N5actArr each give "uninstall refused, nothing removed".
verdict: holds
confidence: high on pwsh 7

## Other checks

claim: "Only this function's body changed in runtime.cpp; the other hunks there are not from this round."
checked:
- `git diff HEAD` shows the log hunk as `@@ -274,12 +276,39 @@` (+27 lines).
- `log("script: %s")` is at HEAD:722. The prior review cited it at :730 (+8 = the 2 include lines, 4 bind lines and 2 register lines already present). It is now at :757 (= 730 + 27).
- `log_path_ =` moves HEAD:749 → :784 (+35 = 8 + 27).
- So everything before :757 differs from the prior-review state only by the log body. The unbind hunks in `start`/`stop` come after that, so this offset check can't place them in time. They only call `unbind`, so they cannot affect logging.
verdict: holds
confidence: high for everything before :757, medium after it (does not matter for the verdict)

claim: receipt 65 OK, 0 skipped; consistency 23 OK
checked: rerun on the host (see "Runs" below): 65 OK with 0 skipped, and 23 OK.
verdict: holds
confidence: high

## Runs (host, this review)

- `host-cmd env KP_SCRATCH=…/review-probes-w1-r3/scratch python3 tools/platform_receipt_test.py` → `Ran 65 tests in 603.627s` / `OK` (no `skipped=`), rc=0 (`unit_receipt.out`). pwsh 7.3.12 was on PATH, so the installer and parser-parity tests ran.
- `host-cmd python3 tools/platform_profile_consistency_test.py` → `Ran 23 tests` / `OK`, rc=0 (`unit_consistency.out`)
- MinGW, fresh objects written under `review-probes-w1-r3/mingw/` (the writer's `/tmp/kp-w1-build` was not touched):
  - `i686-w64-mingw32-g++ -std=c++20 -Wall -Wextra -O2 … runtime.cpp` → rc=0, 0 warnings
  - the same for overlay.cpp → rc=0, 0 warnings (needed `TMPDIR` under r3: host `/tmp` is over the user quota; see Environment)
- Installer probes (`inst.sh`, `inst2.sh`; regenerated `Install-probe.ps1` = final installer + the same two synthetic allowlist lines, `diff` shows only those):
  - "sentinel ok" 40/40, "SENTINEL GONE" 0.
  - 35 "uninstall refused, nothing removed".
  - S1: `victimdir/precious.txt` kept. S2: `kpreal/scripts/mine.lua` kept.
  - N10order restores and uninstalls.
  - `diff` against the writer's `inst.r3final.out` / `inst2.r3final.out` (paths rebased): only timestamps, the H1 timing (61 s vs 115 s) and the writer's trailing rc lines differ.
- `receipt_probe_r2.py` rebased: R1–R4 rejected, R3b/R5/R6 VALID (as before, by design).

## Findings

**W1R3-m1 (minor, docs): the DLL-sha mitigation can't be acted on.**
- The receipt header :33-35 says "check it against the build you shipped". The user doc :69 says "so you can check which build ran".
- No reference sha is published, and `validate()` does not compare the DLL sha to anything.
- Say plainly that the validator does not check the DLL. Or publish the release DLL sha and have `--validate` refuse others.
- Cheaper option: add a log-format token to the banner or host line (for example `log=esc1`) that `BANNER_RE`/`HOST_RE` require. Pre-escape DLLs would then be refused mechanically.
- Not blocking, because IO1 gives the same forgery on the round-3 DLL.

**W1R3-m2 (minor, tests): no in-suite behavioural test of the escaping.**
- The `forged_banner_*` fixtures are pre-escape `[running]`-banner logs. They stay green without the escape loop.
- Add fixtures in the escaped form, one physical line holding `\n[idle] KotorPhasor…`, like R1–R3 here, or a small native test that runs the loop.
- `esc_harness.cpp` and `forge_r3.py` here are a ready template.

**W1R3-i1 (info, accepted limit): Lua `io` can forge a full valid session (IO1 VALID).**
- Disclosed in the receipt header :36-37, overlay.cpp comment and user doc :70.
- It was already the condition of the prior PASS (`platform-w1-rereview.md`: "W1-I1 remains a second route to a capability that is already disclosed (Lua io stays loaded…)").
- What the validator still guarantees:
  - A script's print, diagnostic or error text, or driver GL text, cannot create, split or replace a runtime line.
  - A script that writes the log through `io` before the overlay attaches is caught (IO2: doubled lines).
  - Doubled, stale, reordered or CR-split lines are refused.
- What it cannot guarantee: that nobody with write access to the log (a script through `io`, or the user) appended a whole forged session after the real one.
- Severity is low under the receipt's trust model. The F12 result is already `attested_by=user`, and the user can edit the log directly anyway.

**Environment (not a code finding):**
- Host `/tmp` (tmpfs, 13G/16G) returns "Disk quota exceeded" for this user. The first overlay compile failed on it, and the tool's shell capture was flaky.
- Unrelated `/tmp/modsync-*` trees are the bulk of it. They were not touched.

## Handoff

- One unsettled question: does `Assert-NoReparsePoint` refuse an NTFS **junction** under Windows PowerShell 5.1? Run S1 with `mklink /J` on real Windows 5.1, then list the target.
- Your options (Compound Engineering):
  - `/ce-work`: W1R3-m1 (log-format token or doc fix) and W1R3-m2 (escaped-form fixtures from `review-probes-w1-r3/forge_r3.py`).
  - W2: the native-Windows receipt run, which also settles the junction question.

W1 round 3 verdict: PASS
