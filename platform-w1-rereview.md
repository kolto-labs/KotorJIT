# Platform W1 fix round: independent re-review

Reviewer: independent subagent, 2026-09-27. Source was read-only. Probes and fake game folders
live only under `/home/brunner56/kp-live-20260922/review-probes-w1-r2/`. No game, no Wine, and
no real game install was used. The live-game lock was not touched. No git writes.

Targets, hashed at review time (`review-probes-w1-r2/source-shas.txt`):
- `scripts/install/windows/Install-KotorPhasor.ps1`: `1498e4e0…`, 435 lines
- `scripts/receipts/windows-native-receipt.ps1`: `d308dfe8…`, 301 lines
- `tools/platform_receipt_test.py`: 886 lines

Probe copy: `Install-probe.ps1` is the fixed installer plus the same two synthetic allowlist lines
the prior review used (`diff` shows only `71a72` and `79a81`). Runner: `host-cmd pwsh`,
PowerShell 7.3.12 on Linux.

Writer report: the "Fix round" section of `platform-w0-w1-report.md` has three sentences and
**no Grill-me section**. It cites stale counts and says the suite stalled. Per protocol rule 2,
its claims are `unverified` until my own runs below.

## Stage 1: prior findings against the fix

| prior | status | referent |
|---|---|---|
| C1 uninstall trusts manifest paths | **closed** | T1 `.`, T9 `..`, T2 `../sentinel.txt`, T2b `..\sentinel.txt`, null, empty or missing backup_dir: all "uninstall refused, nothing removed". The sentinel outside the game folder survives every case (`inst.out`). |
| I1 later log line overrides the Wine signal | **partly closed** | Prior `synthetic.log` gives "no KotorPhasor start banner" and is refused. A doubled host line is refused (`F4_no_banner_control`). **A forged banner reopens it: see W1-I1 below.** |
| I2 no field-vs-line cross-checks | **closed** | R1 `gl_line` llvmpipe vs `gl.*`: REJECT. R2 `log_os`/`overlays` disagree: REJECT (`receipt_probe_r2.out`). |
| R3 Mesa + wine=no validated | **closed** | REJECT, "names 'radeonsi'". |
| R4 two `host:` tokens on one line | closed | REJECT, anchored format |
| I3 proxy undo registered after the copy | closed | Install-KotorPhasor.ps1:392-394, the undo now goes before `Copy-Item` |
| Missing backup refuses although the original is on disk | closed | T3 and T4 restore from `binkw32_real.dll` with a warning. T4b, with both copies tampered, refuses and removes nothing. |
| No execution-policy guidance | closed | .SYNOPSIS "RUNNING IT" in both scripts |
| Receipt `-OutFile` defaulted into the game folder | closed | receipt :142-150, `%LOCALAPPDATA%\KotorPhasor\receipts` |
| ARM64 detection | closed | receipt :189-214, IsWow64Process2 first. Not executed: no Windows here. |
| "F12 pressed?" wording | closed | receipt :297-300 |
| Installer copied every `*.json` | closed | :389 copies only `<build>.json` |

Prior probes re-run on the fixed installer, with the same outcome where it should be the same:
- Happy path on `KotOR [GOG] Ünï 字`: install, status all `ok`, reinstall refused, uninstall restored `da32b9be…`.
- T5 read-only Bink: ok.
- T6 pre-existing table: rolled back, and only the user's file is left.
- T7 unknown Bink: refused, naming the sha. The uppercase `-TrustBinkSha256` then installs, and `bink_trusted_override` is recorded.
- T8 relative GameDir: ok.

## Findings

### Critical

None.

### Important

**W1-I1. A Lua mod can still produce a receipt that validates from a Wine run. It forges a whole new session block, banner included, through `print`.**

- Mechanism:
  - The parser reads only the block after the **last** line matching `BannerPattern` (receipt :92, py `session_evidence`).
  - `print` does not split embedded newlines. compat.cpp:73 calls `platform::log(Info, "[%s] %s", name, line)`, and `Runtime::log` writes `"[%s] %s\n"` with no escaping (runtime.cpp:278-289).
  - So `print("x\n[running] KotorPhasor 0.1.0 starting (embedded role)\n[running] kp-session=<any 32 hex> start\n…host: wine=no…\n…gl: vendor=\"NVIDIA Corporation\"…")` writes four physical lines in the exact runtime shape.
  - The runtime's real wine=yes lines are left in the previous "block", so the doubling rule never fires.
  - The forged payload is 381 bytes, inside `platform::log`'s 512-byte buffer.
  - The mod does not need to read the log, because the id only has to agree with itself.
- Two more routes into the same sink:
  - `kp.diagnostic` splits on `\n` but leaves a lone `\r` (output.cpp:37-52). Both parsers split on `\r` (receipt `Get-Content`; py `split_log_lines`).
  - Script load-error text goes through `log("script: %s")` raw (runtime.cpp:730, host.cpp:521).
- Result, with synthetic logs built from reading compat.cpp:73, output.cpp:37-52 and runtime.cpp:278-289. They were not captured from the runtime, because Wine and the game were out of scope. The source path is short and does no escaping, so confidence stays high (`receipt_forge.py`):
  - `F1_print_newline`: VALID, with `--log` re-derivation.
  - `F2_diag_cr`: VALID.
  - `F3_error_text`: VALID.
  - The receipt script's own PS parser agrees on all three: host=`… wine=no …`, problems empty (`ps_parse.out`).
- Claims this falsifies:
  - overlay.cpp:468-475 says "a script cannot produce a line of this shape through the log API".
  - The receipt header, :23-26, says "a script's print or kp.diagnostic output cannot take their exact shape … A block with a second host or gl line … is refused". The forged-banner case is not refused. It is accepted.
- Why it is Important and not Critical: the header already discloses that the Lua `io` library can write the log directly, and `io` is still loaded (host.cpp:126 `luaL_openlibs`, nothing nils `io`). A user can also edit the receipt and the log directly. So this is a second route to a disclosed capability. It is not new power. The prior review graded I1 Important and non-blocking, and I keep that grade.
- Fix, one choke point: in `Runtime::log`, replace `\r` and `\n` in `body` with a visible escape before the fprintf. That closes print, diagnostic and error text together. Add a `forged_banner.log` fixture next to `cr_split_host.log`. Correct the overlay.cpp comment and the receipt header.
- Required before W2 counts a receipt as evidence of a native run.

### Minor

- **M1. Get-Field unrolls one-element arrays, so the value that is checked differs from the value that is used.**
  - `return $prop.Value` turns `["kotorphasor/backup/…"]` into a string for Assert-Manifest. The use at :289 reads `$m.backup_dir` directly and gets the array.
  - N4arrBD: pass 2 ran (Bink restored, runtime files removed), and then :289 threw "backup_dir is null or empty". Two more runs throw again the same way (`n4arrbd_rerun.out`). The manifest can never be removed by the script.
  - Contained, with no deletion outside the game folder.
  - Fix: use Get-Field (or `,$prop.Value`) at every use site, or type-check `$m.backup_dir` and `$f.*` directly.
- **M2. `action` type confusion bypasses the per-action rules.**
  - N5actArr: `action = ["created","replaced"]` passes Assert as `created`, because `-eq` on an array filters. Pass 1 and pass 2 then treat the entry as `replaced`, with `backup = 'chitin.key'`.
  - The script then copied `chitin.key` over `kphasor.dll` and reported "restored original kphasor.dll".
  - Contained: the destination must match `$CreatedPattern`, and the source is resolved inside the game folder.
  - Fix: require `$action -is [string]`.
- **M3. Entry order is trusted.**
  - N10order: `binkw32_real.dll` moved after `binkw32.dll`, and the backup folder removed. Pass 1 picked `binkw32_real.dll` as the restore source. Pass 2 deleted it first, then failed.
  - End state: proxy in place, no `binkw32_real.dll`, and **no copy of the original Bink left in the folder**. A store "verify files" recovers it.
  - Fix: in pass 2, run `replaced` steps before `created` ones, whatever the manifest order.
- **M4. Assert allows zero `replaced` entries.**
  - N4filesObj and N11onlyKp: a manifest listing only `kphasor.dll` gives "uninstalled". The manifest is gone and the proxy stays.
  - The proxy degrades softly: binkw32.cpp:43-50 logs and carries on. Status then says "proxy present but no manifest: installed by another tool; not managed here" (`n11_status.out`).
  - Fix: require exactly one `replaced` `binkw32.dll` entry.
- **M5. Duplicate entries** (N9dup): pass 2 throws on the second `Remove-Item`, midway. A rerun completes. Pass 1 could reject duplicate paths.
- **M6. Containment is lexical.**
  - `GetFullPath` does not resolve links.
  - S1: `kotorphasor\backup\<ts>` is a symlink to an outside folder. pwsh 7 on Linux removed the link only, and `victimdir/precious.txt` survived.
  - S2: `kotorphasor` itself is a symlink. Only owned files were touched, and `scripts/mine.lua` survived.
  - **Windows PowerShell 5.1 `Remove-Item -Recurse` on an NTFS junction is unverified here.** Do not infer it from Linux.
  - A planted link needs deliberate action, the same class as a malicious mod.
  - Fix: before :290, refuse when `(Get-Item $backupDir).Attributes -band ReparsePoint`.
- **M7. .NET regex `$` matches before a final `\n`.** N2trailnl: `BackupDirPattern` accepted `…Z\n`. A later check refused it. Use `\z` in both patterns.
- **M8. Type confusion that is accepted but harmless:** `schema` as a one-element array (N4schema), `sha256` as an array (N4arrSha), upper-case `backup_dir` (N2case; on NTFS it is the same folder).

### Checked, holds (null moves)

- **Rooted, UNC and device paths:** `\\?\C:\…` (N2unc), `\\.\C:` (N2dev), absolute (N2abs), `C:kphasor.dll` (N3drive). All refused.
- **Alternate data stream** `kphasor.dll:evil`: refused (N3ads).
- **Trailing dot or space** (`kphasor.dll.`, `kphasor.dll `): refused (N3trdot, N3trsp).
- **8.3 short name** `KPHASO~1.DLL`: refused as "not a file this script creates" (N3short).
- **Game file named in the manifest** (`chitin.key`): refused (N3gamefile).
- **Tail `..`** (`…Z/..`): refused (N2dotdotTail).
- **Manifest type confusion on `files`** (string, null, empty): refused (N4filesStr, N4filesNull, N4filesEmpty).
- **Huge manifest:** 20,000 entries, 2.9 MB. Uninstall took 29 s and was correct (H1). A 3,000-deep JSON object hits MaxDepth 1024 and is refused with nothing removed (H2).
- **Receipt:**
  - A newest session with no host or gl line (crash before the first frame) is refused, even when an older clean block exists (F5).
  - A host line before the start line is refused (F6).
  - Multiple ids are refused (fixture `session_id_mismatch`).
  - Clock tricks do not apply, because ordering is by line position and never by timestamp.
- **R3b:** Mesa only in the GL version string gives VALID. That is by design: platform_receipt_test.py:83-84 documents that Microsoft's ARM64 GL compatibility layer reports Mesa there. Real Mesa renderer strings carry `radeonsi`, `Mesa`, `zink` or `DRM n`, and those are refused.
- **R5 and R6** (build or manifest sha null): VALID, by design.

## Grill me (the writer's section is missing; these are mine)

1. *Weakest point: can Lua reach the "native-only" sink?* Yes. Runtime::log is shared, and it does not escape newlines. F1–F3 above.
2. *Is every manifest value checked in the same form it is used?* No. M1 and M2 show the check and the use diverge.
3. *Does uninstall hold up if the manifest is reordered?* No. M3.
4. *Is the 5.1 behaviour of `Remove-Item -Recurse` on a junction known?* Unverified. M6.

## Protocol blocks

```
claim: "Uninstall ... checks every path ... A manifest that fails any check is refused and nothing is removed" (Install-KotorPhasor.ps1:16-20)
referent: T1/T9/T2/T2b/N1*/N2*/N3* refused, sentinel ok; N4arrBD removed files then threw at :289
checked: review-probes-w1-r2/inst.out, n4arrbd_rerun.out
verdict: holds for containment; does not hold for "nothing is removed" under array type confusion (M1)
confidence: high; changes if Get-Field is used at every use site

claim: owned-only uninstall (C1)
referent: every traversal/rooted/UNC/device/ADS/trailing-dot probe refused; sentinel survived all 40+ runs
checked: inst.out, inst2.out
verdict: holds
confidence: high on pwsh 7; medium for 5.1 junctions (M6, not runnable here)

claim: "a script cannot produce a line of this shape through the log API" (overlay.cpp:468-475)
referent: F1 print with \n, F2 kp.diagnostic with \r, F3 error text -> VALID wine=no receipt from a wine=yes run
checked: receipt_forge.out (python validate with log_bytes), ps_parse.out (receipt's own PS parser)
verdict: does not hold
confidence: high; changes if Runtime::log escapes \r and \n

claim: wine=yes rejected as native
referent: fixtures wine_yes, spoofed_later_host_line, F4 refused; F1-F3 accepted
checked: as above
verdict: holds against a doubled or unanchored line; does not hold against a forged banner block
confidence: high

claim: container 55 OK / host 55 OK / consistency 23 OK (orchestrator)
referent: my own runs, see Commands
checked: python3 tools/platform_receipt_test.py; tools/platform_profile_consistency_test.py
verdict: holds. Receipt 55 OK (skipped=8, no KP_PWSH). The 8 skipped tests are ReceiptParserParity and InstallerBehaviour, run separately with KP_PWSH=host-cmd pwsh: 8 OK. Consistency 23 OK. None of these tests covers F1-F3 or M1-M4
```

## Commands and outputs

```
$ host-cmd pwsh -Version                         -> PowerShell 7.3.12
$ diff Install-KotorPhasor.ps1 Install-probe.ps1 -> 71a72, 79a81 (two synthetic allowlist lines)
$ review-probes-w1-r2/inst.sh   (output: inst.out)
  HAPPY: installed / 3x ok / 'already installed' rc=1 / restored, uninstalled, bink da32b9be412a
  T1 '.'  T9 '..'  T2 ../sentinel.txt  T2b ..\sentinel.txt  N1 null/''/missing  -> refused, sentinel ok
  N2dotdotTail N2abs N2unc N2dev -> refused; N2trailnl -> refused by backup-file check; N2case -> uninstalled
  N3ads N3trdot N3trsp N3short N3drive N3gamefile -> refused
  N4arrBD -> bink restored, kphasor/real removed, then "backup_dir is null or empty" rc=1, manifest kept
  N4arrPath -> refused before pass 1 changes; N4arrSha, N4schema -> uninstalled (benign)
  N4filesObj -> "uninstalled", proxy d2ca9cd3a5c8 + binkw32_real left, manifest gone
  N4filesStr/Null/Empty -> refused
  N9dup -> "Cannot find path …kphasor.dll" rc=1 mid pass 2; rerun -> uninstalled
$ review-probes-w1-r2/inst2.sh  (output: inst2.out)
  T3, T4 -> WARNING restoring from binkw32_real.dll; uninstalled, bink da32b9be412a
  T4b -> refused, Files: binkw32.dll, binkw32_real.dll
  T5 ok; T6 rolled back (user file kept); T7 refused then override recorded; T8 ok
  S1 symlinked backup ts -> uninstalled; victimdir: binkw32.dll precious.txt (intact)
  S2 symlinked kotorphasor -> uninstalled; kpreal/scripts/mine.lua intact
  N5actArr -> "restored original kphasor.dll"; kphasor.dll content now "data" (= chitin.key)
  N10order -> "Cannot find path …binkw32_real.dll" rc=1; binkw32.dll = proxy d2ca…, no binkw32_real
  N11onlyKp -> "uninstalled"; proxy + binkw32_real left, manifest gone
  H1 20000 entries, 2909979 bytes -> uninstalled in 29.24 s
  H2 depth 3000 -> "MaxDepth of 1024 has been exceeded", refused, nothing removed
$ host-cmd pwsh -File Install-probe.ps1 -GameDir games/nest-N4arrBD/g -Action Uninstall  (x2)
  manifest backup_dir is null or empty   (both runs)
$ python3 review-probes-w1-r2/receipt_forge.py   (output: receipt_forge.out)
  forged block bytes: 381
  F1_print_newline:  host_line … wine=no …  validate(with --log): VALID
  F2_diag_cr:        VALID
  F3_error_text:     VALID
  F4_no_banner_control: REJECT (2 start / 2 ids / 2 host / 2 gl)
  F5_old_clean_new_empty: REJECT (0 host, 0 gl)
  F6_host_before_start:   REJECT
$ host-cmd pwsh -File review-probes-w1-r2/ps_parse.ps1   (receipt's own Get-SessionEvidence)
  F1/F2/F3: id=0123…cdef host=… wine=no … problems=(none);  F4: 2 start/2 ids/2 host/2 gl
$ python3 review-probes-w1-r2/receipt_probe_r2.py   (output: receipt_probe_r2.out)
  R1 REJECT  R2 REJECT  R3 REJECT (radeonsi)  R3b VALID (by design)  R4 REJECT  R5 VALID  R6 VALID
  prior synthetic.log -> ['no KotorPhasor start banner in the log']
$ host-cmd pwsh -File review-probes-w1-r2/ps_parse2.ps1   (prior lastmatch input, receipt's PS parser)
  synthetic.log  problems=no KotorPhasor start banner in the log
  native_pass.log  id=0f1e2d3c…  host=… wine=no …  problems=(none)
$ host-cmd pwsh -File Install-probe.ps1 -GameDir games/nest-N11onlyKp/g -Action Status
  proxy present but no manifest: installed by another tool; not managed here
$ KP_PWSH="host-cmd pwsh" KP_SCRATCH=review-probes-w1-r2/unit-scratch python3 tools/platform_receipt_test.py ReceiptParserParity InstallerBehaviour
  Ran 8 tests in 147.145s  OK
$ grep -n luaL_openlibs src/lua/host.cpp -> 126 (io not removed)
$ PYTHONDONTWRITEBYTECODE=1 python3 tools/platform_receipt_test.py        (unit_receipt.out)
  Ran 55 tests in 552.266s  OK (skipped=8)  rc=0   (host python; the 8 skips need pwsh in-process)
$ PYTHONDONTWRITEBYTECODE=1 python3 tools/platform_profile_consistency_test.py  (unit_consistency.out)
  Ran 23 tests in 27.604s  OK  rc=0
```

## Handoff: the one question I could not settle

Does Windows PowerShell 5.1 `Remove-Item -LiteralPath <junction> -Recurse -Force` delete the
junction's target contents? The check that settles it: on Windows 10 with 5.1, run
`mklink /J`, then Remove-Item, then list the target. Until then, add the ReparsePoint check (M6).

## Your options (Compound Engineering)

- `/ce-work`: escape `\r` and `\n` in `Runtime::log` and add a forged-banner fixture (W1-I1). Then re-run `review-probes-w1-r2/receipt_forge.py`, which should print REJECT for F1–F3.
- `/ce-work`: installer hardening M1–M4 and M6. Re-run `review-probes-w1-r2/inst.sh` and `inst2.sh` afterwards.
- `/ce-code-review` on that re-spin before W2.

The verdict holds only while two conditions stay true: W1-I1 remains a second route to a capability that is already disclosed (Lua `io` stays loaded and the receipt header's caveat stays), and M1–M8 stay contained inside the game folder, as every probe here showed. Owned-only uninstall (C1) is closed. W1-I1 must land before any W2 receipt counts as evidence of a native run.

W1 re-review verdict: PASS
