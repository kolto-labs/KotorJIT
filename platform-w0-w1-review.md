# Platform W0 + W1 independent review

Reviewer: independent subagent, 2026-09-27. Source was read-only. Scratch lived under
`/home/brunner56/kp-live-20260922/review-probes-w0w1/`. No game, no Wine, no real game
install, and the live-game lock was not touched. The fake game folders held synthetic
bytes only. The installer probes ran on a copy of the installer (`Install-probe.ps1`). That
copy adds one synthetic exe sha and one synthetic Bink sha to the two allowlists and is
otherwise byte-identical (diff: 2 added lines at :52 and :63).

Spec: `fanout-platform-profile-plan.md` §3 W0/W1. Implementer report:
`.superpowers/sdd/lua-boundary-validation-plan/platform-w0-w1-report.md`.

## Stage 1: spec compliance

| spec item | status | referent |
|---|---|---|
| W0 offline cross-check of builds.inc, address JSON, profile shas, MP aliases, static_only; C++ text-parse | met | `platform_profile_consistency_test.py` check() :158-262; 20 tests OK; `--report` rc=0 |
| W1 `host_identity()` with RtlGetVersion, wine_get_version, overlay modules | met | platform_win32.cpp :133-177 |
| W1 overlay logs GL vendor/renderer/version and host identity | met | overlay.cpp :469-480, called once at :499 |
| W1 installer: sha allowlist | met | Install-KotorPhasor.ps1 :51-63, :216, :224 |
| W1 installer: transactional | met, with one gap (I3) | :273-331; T6 rollback probe |
| W1 installer: **owned-only uninstall** | **not met** | T1 and T9: one manifest field recursively deletes the game folder or its parent (C1) |
| W1 receipt script with the stage-3 field set | met | windows-native-receipt.ps1 :136-148 |
| W1 `platform_receipt_test.py`: wine=yes rejected as native | met for the runtime's own line; spoofable by in-process log lines (I1) | 25 tests OK; lastmatch probe |

## Findings

### Critical

None, if Critical means "fires in normal use". C1 below is the item that blocks the verdict.

### Important

**C1. Uninstall trusts manifest paths. `backup_dir` gets a recursive delete with no containment check.**
- Where: Install-KotorPhasor.ps1 :189-190: `$backupDir = Join-Path $GameDir $m.backup_dir` → `Remove-Item -LiteralPath $backupDir -Recurse -Force`. `files[].path` (:143, :185) and `files[].backup` (:160, :182) are also joined without validation.
- **T1** (`backup_dir = '.'`): the whole game folder was deleted, including `swkotor.exe` and `chitin.key`. `ls` afterwards: `No such file or directory`. The script then failed at :199 because its own manifest was gone.
- **T9** (`backup_dir = '..'`, game at `games/nest/t9`): `games/nest` vanished, including the sibling `sibling-data.txt`, which is **outside the game folder**.
- **T2** (`files[]` gets `{"path":"../victim.txt","action":"created","sha256":<its hash>}`): the file outside the game folder was deleted. `files[]` entries are hash-gated, so this one needs a deliberate hash. `backup_dir` has no hash gate.
- Under pwsh 7.3.12, `Join-Path '/g/game' $null` and `Join-Path '/g/game' ''` both return `/g/game/`. So a null or empty `backup_dir` also means "delete the game folder". This was not tested on Windows PowerShell 5.1. `'.'` and `'..'` do not depend on that behaviour.
- Trigger: the manifest is edited, corrupted or produced by a future bug. Lua scripts get full `luaL_openlibs` (src/lua/host.cpp:126), so a mod script can write that file. A malicious script could already delete files itself. The real risk is an accidental or malformed manifest turning "owned-only uninstall" into an unbounded recursive delete.
- Fix: before pass 1, reject any manifest path that is rooted or has a `..` segment. Require `backup_dir` to match `^kotorphasor[\\/]backup[\\/]\d{8}T\d{6}Z$`. Resolve every joined path and assert it starts with `$GameDir + separator`.
- Why it blocks: "owned-only uninstall" is a named W1 deliverable. W2 hands this script to a user's real game folder.

**I1. The one Wine signal in a receipt can be overridden by any later log line, including script output.**
- The runtime line is `[phase] info: host: …`. Lua `print` logs `[name] <text>` (src/api/compat.cpp:73). `kp.diagnostic` logs the raw text with no prefix (src/api/output.cpp:129). Both land in the same kotorphasor.log.
- The receipt script takes the **last** matching line (`Get-LastMatch`, :41-45). Its regex is unanchored, and so is the Python one (`re.search`, platform_receipt_test.py:94).
- Probe (`lastmatch.ps1`, the real function and pattern extracted from the script): the synthetic log had a runtime `wine=yes` line and then a script-printed `[spoof] host: wine=no …` line. Result: `HOST: [running] info: [spoof] host: wine=no …`. The GL line was replaced the same way, so the Mesa renderer line was overridden by a later NVIDIA line.
- The log opens with `"ab"` (runtime.cpp:285), so a host line from an older session can also be paired with today's F12 claim.
- Under Wine, `os.build` is not a second signal. The registry build and RtlGetVersion both come from the prefix's configured Windows version, so the validator has exactly one Wine signal.
- `HideWineExports` (the wine-staging patch that hides `wine_get_version`) is **unverified**. I have no referent that current staging still ships it.
- Probe R3: a receipt with `wine=no` and GL `… (radeonsi …) Mesa 24.1.6` validates as VALID.
- Cheap fixes:
  1. Take the host and gl lines from the runtime's own sink format, anchored `^\[\w+\] info: host: `, and refuse more than one distinct host line per session. Or add a session id to both lines and to the start banner.
  2. Reject `Mesa` in the GL version and `radeonsi`/`llvmpipe`/`zink` in the renderer.
  3. In the PS1, add `Test-Path 'HKLM:\Software\Wine'` as a second, independent Wine signal.

**I2. The validator does not cross-check its derived fields against the lines they came from.**
- R1: `log.gl_line` says llvmpipe while `gl.renderer` says a GPU → VALID. The software-renderer rule reads only `gl.renderer` (:117).
- R2: `host.log_os` and `host.overlays` disagree with `host_line` → VALID.
- The Wine rule treats the log line as authoritative (:93-104). The GL rule does not, which is inconsistent.
- Fix: parse `gl_line` with GL_RE and require it to equal `gl.*`. Require `log_os` and `overlays` to equal the host_line groups.

### Minor

- **I3. The proxy undo is registered after the copy** (:293-294). If `Copy-Item … $Proxy -Force` fails partway (disk full), no undo restores `binkw32.dll`, but the message still says "rolled back". The backup folder survives because the sha check at :320 fails, so the original is still recoverable by hand. Fix: add the undo before the copy.
- **Missing backup refuses even when the original is on disk.** T3: backup deleted, `binkw32_real.dll` is the verified original (`da32b9be…`), uninstall refuses with "Files: binkw32.dll". The warning at :147/:162 points at a backup that no longer exists. Fall back to `binkw32_real.dll` when its hash equals `original_sha256`.
- **No execution-policy guidance.** Neither script nor any doc mentions `Set-ExecutionPolicy -Scope Process Bypass` or `Unblock-File` (grep: 0 hits). Windows client default policy stops `.\Install-KotorPhasor.ps1` before line 1. Fix before the W2 hand-off.
- **Overlay name patterns.** The header comment (platform.hpp:91) says Discord matches `*overlay*`. Discord's hook DLL is `DiscordHook.dll` (medium confidence, not checked here), and RTSS is `RTSSHooks.dll`. Neither matches.
- **ARM64 detection** reads `PROCESSOR_ARCHITECTURE`/`W6432`. An x64-emulated PowerShell on ARM64 reports AMD64, so translation would show `none`. Windows PowerShell 5.1 on ARM64 is native, so the default path is fine. `IsWow64Process2` or `Win32_Processor.Architecture=12` is more robust.
- **Toolhelp snapshot failure is silent.** `CreateToolhelp32Snapshot` can transiently fail with ERROR_BAD_LENGTH. overlays then logs `-`, a false negative. One retry fixes it.
- **An overlays list that overflows 256 bytes ends with a truncated name**, because snprintf writes the partial name before the break.
- **The receipt defaults `-OutFile` into the game folder.** Under Program Files without elevation, that write fails after all the work is done.
- **The installer copies every `*.json` in AddressDir,** including `k2_steam_aspyr.json` and `k1_steam_103_unpacked.json`. That is harmless, since the runtime picks `<build>.json`, but it is noise in the manifest.
- **Consistency-test parser reach.** `parse_projectiles_profile` reads only the first `Profile p{`. `parse_runtime_aliases` reads only the `build_ == "x"` form. The engine_k1.cpp game-string gate is out of scope for W0, which the spec defers to later.
- **The receipt script's warning "was F12 pressed?" is inaccurate.** ImGui init, and so the host line, happens on the first swap with a GL context (overlay.cpp:485-499), not on F12.
- Under pwsh 7, Status shows `installed_at` as a localized DateTime because ConvertFrom-Json converts ISO strings. This is cosmetic. 5.1 keeps the string.

### Checked, holds (null moves)

- Happy path on `KotOR [GOG] Ünï 字` (spaces, brackets, CJK), from `cwd=/tmp`, and with a relative GameDir from another cwd (T8): install, status all `ok`, reinstall refused, uninstall restored the Bink sha `da32b9be…` and kept `kotorphasor/scripts`.
- T4, a tampered backup: refused, nothing removed.
- T6, a pre-existing `addresses/k1_gog_103.json`: "install failed and was rolled back", with only the pre-existing file left.
- T7, an unknown Bink: refused with the exact sha. An uppercase `-TrustBinkSha256` then installed and was recorded in `bink_trusted_override`.
- T5, a read-only original (Linux chmod 444): install and uninstall OK. NTFS ReadOnly-attribute behaviour is unverified here.
- Case-insensitivity: hashes are lowercased on both sides, and a PowerShell `@{}` hashtable is case-insensitive. File-name case on NTFS is unverified on Linux. The paths are fixed names under `Test-Path -LiteralPath`.
- PS 5.1 static read: both scripts are pure ASCII, LF, no BOM. No `??`, `?.`, `&&`, `||` or `-AsHashtable`. `Get-FileHash`, `[ordered]`, `Get-CimInstance`, `Get-Content -Raw` and `GetNewClosure` are all 3.0-4.0 features. Under StrictMode 2, `$f.backup` and `$f.original_sha256` are read only on `replaced` entries, via `-and` short-circuit. The manifest BOM from 5.1 `Set-Content -Encoding UTF8` is read back by `Get-Content -Raw`. Not executed on 5.1.
- Privacy: the receipt records the OS product and build, the CPU name, the exe name only (no GameDir), shas, and two log lines with overlay base names only. It records no username, machine name or path. The manifest holds relative paths only.
- C++ `wine_get_version`: `const char*(__cdecl*)()` matches Wine's `CDECL` declaration. `RtlGetVersion`: `LONG(WINAPI*)(OSVERSIONINFOW*)` matches `NTSTATUS NTAPI (PRTL_OSVERSIONINFOW)`, stdcall on i386. FARPROC is copied into the typed pointer with memcpy and a size static_assert. The ntdll handle is null-guarded in `proc`.
- No psapi, no new exports: objdump of `/tmp/kp-w1-build/kphasor.dll` shows 9 imports and no psapi or ntdll import. ntdll is reached through GetModuleHandle. The DLL has **no export table at all**. `host_identity` appears in nm only as a local text symbol.
- Logs once: `context` is assigned nullptr only at its definition (overlay.cpp:29). Nothing resets it, so the `if (!context)` block runs once per process. The cross-thread race on the unguarded static `context` is pre-existing code, not a W1 regression. W1 adds only work inside the block, on the render thread with the GL context current.
- W0 pins are correct:
  - builds.inc:60 says "Not installable until that work is done". k2_steam_aspyr.json summary says `installable: True`, 39/256.
  - model_profiles.cpp:5, :9 and :13 bind `aa628373…`, `f14f285b…` and `469067c4…`.
  - The generator rows `k1_mac` (:150) and `k2_mac` (:134) carry `md5` only.

## Protocol blocks (implementer claims)

```
claim: "Uninstall ... removes only files it verified" / owned-only uninstall
referent: T1 (backup_dir='.' deleted whole game dir), T9 (backup_dir='..' deleted parent incl. sibling file)
checked: review-probes-w0w1/tamper.out, t9.out; Install-KotorPhasor.ps1:189-190
verdict: does not hold
confidence: high; would change if manifest paths were validated before pass 1

claim: "Pass 1 verifies every hash and changes nothing. If any file differs, it refuses"
referent: T3, T4 refused with nothing removed
checked: tamper.out T3/T4
verdict: holds
confidence: high

claim: "wine=yes rejected as native"
referent: fixtures wine_yes -> 2 REJECT rc=1; but lastmatch.ps1 shows later script line wins
checked: --validate wine_yes; lastmatch.ps1 output
verdict: holds for the runtime's line; does not hold against later in-process log lines
confidence: high

claim: "no psapi import" / no new exports
referent: objdump -p: 9 DLL imports, no psapi; no Export Table
checked: i686-w64-mingw32-objdump -p /tmp/kp-w1-build/kphasor.dll
verdict: holds
confidence: high (this build is the implementer's /tmp build, not rebuilt by me)

claim: KNOWN_DRIFT pins are real drift
referent: builds.inc:60 note vs json installable True; generator k1_mac/k2_mac md5-only
checked: grep builds.inc, gen_address_tables.py:134-158, model_profiles.cpp:5-13; --report rc=0
verdict: holds
confidence: high

claim: tests green (20 + 25)
referent: "Ran 20 tests in 42.742s OK", "Ran 25 tests in 51.956s OK"
checked: python3 tools/platform_*_test.py
verdict: holds
confidence: high

claim: "The overlay logs exactly once, after ImGui_ImplOpenGL2_Init"
referent: single call site at :499; context never reset
checked: grep 'context = nullptr' overlay.cpp -> only :29
verdict: holds
confidence: high
```

## Commands and outputs

```
$ PYTHONDONTWRITEBYTECODE=1 python3 tools/platform_profile_consistency_test.py
Ran 20 tests in 42.742s  OK
$ python3 tools/platform_profile_consistency_test.py --report ; rc=0
  KNOWN note-mismatch k2_steam_aspyr, KNOWN x3 profile-sha-unregistered macos-*, INFO x4
$ PYTHONDONTWRITEBYTECODE=1 python3 tools/platform_receipt_test.py
Ran 25 tests in 51.956s  OK
$ python3 tools/platform_receipt_test.py --validate .../native_pass.json  -> VALID native receipt rc=0
$ python3 tools/platform_receipt_test.py --validate .../wine_yes.json     -> 2 REJECT, rc=1
$ python3 review-probes-w0w1/receipt_probe.py
R1 gl_line llvmpipe, gl.renderer says GPU: VALID
R2 host.log_os/overlays disagree with host_line: VALID
R3 Wine w/ hidden wine_get_version (Mesa radeonsi GL, 10.0.19045): VALID
R5 build null / R6 manifest sha null: VALID (by design)
$ host-cmd pwsh -File Install-probe.ps1 (PowerShell 7.3.12)
  happy path on "KotOR [GOG] Ünï 字": install/status ok/reinstall refused/uninstall restored da32b9be…
  T1 backup_dir='.'  -> game dir gone
  T2 ../victim.txt   -> victim.txt gone
  T3 backup missing  -> refused (binkw32_real.dll holds original)
  T4 backup tampered -> refused, nothing removed
  T5 read-only bink  -> ok (Linux semantics)
  T6 pre-existing table -> rolled back
  T7 unknown bink -> refused; -TrustBinkSha256 (uppercase) -> installed, override recorded
  T8 relative GameDir -> ok
  T9 backup_dir='..' -> parent 'games/nest' gone incl. sibling-data.txt
$ host-cmd pwsh -File joinpath.ps1
  [] -> [/g/game/]   (null)   [] -> [/g/game/]  (empty)
$ host-cmd pwsh -File lastmatch.ps1
  HOST: [running] info: [spoof] host: wine=no wine_version=- os=10.0.19045 overlays=-
$ host-cmd i686-w64-mingw32-objdump -p /tmp/kp-w1-build/kphasor.dll | grep 'DLL Name'
  DINPUT8 dwmapi GDI32 KERNEL32 msvcrt OPENGL32 SHELL32 USER32 WS2_32   (no Export Table section)
```

## Your options (Compound Engineering)

- `/ce-work`: installer manifest-path validation (C1), undo-before-copy (I3), `binkw32_real.dll` fallback, and an execution-policy note in the .SYNOPSIS.
- `/ce-work`: receipt anchoring and a session id (I1), plus field-vs-line cross-checks and a Mesa rejection (I2). Add fixtures `spoofed_later_host_line.json` and `gl_line_disagrees.json`.
- `/ce-code-review` on the re-spin, then re-run T1, T2 and T9 from `review-probes-w0w1/tamper.sh` and `t9.sh`. Point them at the fixed script with the same two-line allowlist patch.

W0+W1 verdict: FAIL

W0 on its own passes. W1 fails on a named deliverable, owned-only uninstall (C1). I1 and I2 should land in the same re-spin, before the W2 hand-off.
