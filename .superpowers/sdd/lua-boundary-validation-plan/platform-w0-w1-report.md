# Platform W0 + W1 report (fan-out F, sole writer)

Plan: `/home/brunner56/kp-live-20260922/fanout-platform-profile-plan.md` §3 W0/W1.
Worktree: `.worktrees/lua-boundary-validation`. Nothing was staged, committed or pushed. No game, Wine run, Gamescope or FFmpeg was used. `tmp/harness-locks/live-game.lock` was not touched.

## Files

| file | state |
|---|---|
| `tools/platform_profile_consistency_test.py` | new, 437 lines (W0) |
| `tools/platform_receipt_test.py` | new, 318 lines (W1) |
| `tools/fixtures/platform-receipts/*.json` | new, 12 synthetic receipts |
| `src/platform/platform.hpp` | +26: `HostIdentity` :94, `host_identity()` :101, `format_host_identity()` :106, all under `#if defined(_WIN32)` |
| `src/platform/platform_win32.cpp` | +89: `is_overlay` :58, `host_identity` :133 (`wine_get_version` :138, `RtlGetVersion` :149, Toolhelp modules :161), `format_host_identity` :180 |
| `src/devtools/overlay.cpp` | +17: `log_host_and_gl` :469, called once at :499 inside the existing `if (!context)` ImGui init block |
| `scripts/install/windows/Install-KotorPhasor.ps1` | new, 335 lines |
| `scripts/receipts/windows-native-receipt.ps1` | new, 157 lines |

`platform_linux.cpp` is untouched. The declaration is Windows-only, so no Linux definition is needed. CMake, `src/runtime/**`, `src/api/**`, `data/addresses/**`, `scripts/harness/**` and docs are untouched.

## W0: identity consistency test

Offline and text-parse only. `gen_address_tables.py` is read with `ast` and never imported, so its `_ref` filesystem probes never run. `--all` was never run.

The test cross-checks these sources:
- builds.inc against `data/addresses/<alias>.json`, comparing build, sha, image_base, encrypted, format, known_text and note. The sha follows the generator's own rule, `identity.sha256 or derived_sha256`, and never `reference_sha256`.
- builds.inc against the generator's BUILDS: every record must be a non-static row, and no static_only row may be emitted.
- The shas in model and projectile profiles. Each must be a BuildRecord or appear in a static_only `platform=mac` row.
- Animation profile ids against model profile ids.
- `std::array<Profile,N>` against the actual entry count.
- The alias literals in `runtime.cpp` against BuildRecord aliases.

Tests (20): `RealTree.{test_parsers_see_the_whole_tree, test_no_unexpected_drift, test_known_drift_ledger_is_not_stale}` and `SyntheticDrift.*`. SyntheticDrift has 17 tests. Each one injects one drift class into a temp copy of the tree and asserts that it is flagged. One of them, `test_pinned_subject_with_new_value_is_new_drift`, checks that a pin never absorbs a different value.

Red run, with `KNOWN_DRIFT` cleared:
```
FAIL: test_no_unexpected_drift ... new identity drift:
  note-mismatch k2_steam_aspyr ...
  profile-sha-unregistered model:macos-k1-i386: aa628373...
  profile-sha-unregistered model:macos-k2-i386: f14f285b...
  profile-sha-unregistered model:macos-k2-x86_64: 469067c4...
FAILED (failures=1)
```
Green run: `PYTHONDONTWRITEBYTECODE=1 python3 tools/platform_profile_consistency_test.py` gives `Ran 20 tests ... OK`.

### Drift found (real, not fixed; pinned in KNOWN_DRIFT)

Each pin is a (kind, subject, exact detail) triple, and the detail includes the offending sha or note hash.

1. **Mac profile shas have no generator entry.** Three Mac model profiles in `src/api/model_profiles.cpp:5,9,13` bind exact shas:
   - `macos-k1-i386` binds `aa628373…`
   - `macos-k2-i386` binds `f14f285b…`
   - `macos-k2-x86_64` binds `469067c4…`

   Neither the generator's static_only `k1_mac` nor `k2_mac` row carries a sha256; both carry md5 only. No `k2_mac_x86_64` row exists. The owner is M0, which adds the static-only Mac entries.
2. **k2_steam_aspyr is "not installable" in one file and installable in the other.** The note hashes are json `70ca14da…` and builds.inc `1e8a73ae…`.
   - The builds.inc note says "Not installable until that work is done."
   - `data/addresses/k2_steam_aspyr.json` has a different note, sets `summary.installable: true`, and resolves 39/256 sites.

   builds.inc is stale. The owner is the later `--all` regen, which comes after `k2_gog_aspyr.json` is committed.
3. Info only, not drift: the BUILDS rows `k1_amazongames`, `k2_steam_linux`, `k2_win_cd_10` and `k2_win_cd_10b` have no address JSON, so they emit no BuildRecord. Source: `--report`.

The ledger fails in both directions. A new drift fails `test_no_unexpected_drift`. A pinned drift that has been fixed fails `test_known_drift_ledger_is_not_stale`.

## W1: host identity, overlay log, installer, receipt

### C++
`host_identity()` gathers three facts:
- **Wine:** `GetProcAddress(ntdll, "wine_get_version") != nullptr`. When Wine is present, its version string is also recorded.
- **OS version:** RtlGetVersion major, minor and build. The return value is typed `LONG`, so it does not need `NTSTATUS` under LEAN_AND_MEAN.
- **Overlays:** loaded modules found through Toolhelp32. These are kernel32 calls, so no new psapi import is needed. Names that match `galaxy*`, `*overlay*` or `nvspcap*` are recorded as lowercase ASCII base names only, with no paths.

Log line format: `host: wine=<yes|no> wine_version=<v|-> os=<M.m.b> overlays=<a,b|->`. Spaces, tabs and commas inside the wine version or a module name become `_`, so each value stays one token.

At ImGui init, overlay.cpp logs that line once, plus `gl: vendor="…" renderer="…" version="…"`, with `glGetString` null-guarded. Both go through `platform::log`. `Runtime::start` routes that into kotorphasor.log (`runtime.cpp:756`).

**Windows cross build: done.** The host MinGW is reached through `~/.local/bin/host-cmd`. The `cmake`/`ninja` wrappers use it.
- Configure: `cmake -S . -B /tmp/kp-w1-build -G Ninja` found `KP_MINGW_CXX=/usr/lib64/ccache/i686-w64-mingw32-g++` (GCC 16.1.1 Fedora MinGW).
- Build: `ninja hooks_win32 kphasor_dll binkw32` → `[63/63] i686-w64-mingw32-g++ kphasor.dll`.
- The touched objects were rebuilt with `-Wall -Wextra`: `[1/5] platform_win32.cpp`, `[2/5] overlay.cpp`, `[5/5] kphasor.dll`, with zero warnings.
- `i686-w64-mingw32-objdump -p kphasor.dll` lists the imports DINPUT8, dwmapi, GDI32, KERNEL32, msvcrt, OPENGL32, SHELL32, USER32 and WS2_32. There is no psapi import.
- `strings` finds `wine_get_version`, `RtlGetVersion`, the `host:` format and the `gl: vendor=` format in kphasor.dll.

**Linux: not broken.** `ninja kp_hooktool libkphasor.so` → `[72/72] Linking CXX executable kp_hooktool`. The only warnings are pre-existing `-Wclobbered` warnings in `hook_bodies.cpp:568,737`.

The repo runs no Windows-side tests under Wine (`grep -i wine` in the cmake files finds comments only), so none were run.

### Installer (`Install-KotorPhasor.ps1`)
The exe allowlist is at :51:
- `k1_gog_103` (`9c10e045…`)
- `k1_steam_103` (`34e6d971…`)
- `k2_gog_aspyr` (`777bee23…`)

Two builds are excluded on purpose:
- `_unpacked` is a harness artifact.
- `k2_steam_aspyr` is excluded because of drift item 2.

The Bink allowlist holds one sha, `2d0ae23a…` (375808 bytes), taken from the K1 **Steam** original at `tmp/k1_harness/binkw32_real.dll`. No `binkw32.dll` exists next to the GOG reference images; I searched the four generator reference directories. So the GOG K1 Bink is unverified: if it differs, the first K1 GOG install refuses and prints the exact `-TrustBinkSha256` value to pass. The K2 Bink sha is also unknown, so K2 fails closed unless the user passes `-TrustBinkSha256 <exact sha>`, which is recorded in the manifest.

Install checks everything first, then acts:
1. Refuses an unknown exe, an unknown `binkw32.dll`, or an unknown or mismatched `binkw32_real.dll`.
2. Probes that the game folder is writable.
3. Copies the original Bink (never moves it) to a backup and verifies the copy's hash.
4. Copies the proxy in last.
5. Writes `kotorphasor/install-manifest.json` with every file's hash.
6. On any error, runs the undo steps in reverse.

Uninstall has two passes (:135). Pass 1 verifies every hash and changes nothing. If any file differs, it refuses and removes nothing. Pass 2 removes only files it verified and restores Bink only from a verified backup. Re-running after a partial uninstall is safe.

Parse check (the pwsh on the host is 7.3.12): `[scriptblock]::Create(...)` plus `Parser::ParseFile` → `PARSE_OK errors=0` for both scripts.

I also ran the installer under pwsh 7 in a temp game folder (`/tmp/kp-w1-install`, deleted afterwards). It held an allowlisted exe copied from the local reference image, the K1 retail Bink, and the freshly built proxy and DLL. Results:
- Install, then Status: all entries `ok`. A second install is refused with "already installed".
- Uninstall with one table edited by the user: `uninstall refused, nothing removed`, and a hash diff showed `UNCHANGED_AFTER_REFUSAL`.
- After restoring the table, uninstall gives `restored original binkw32.dll` and `GAME_FILES_RESTORED`. The user's `kotorphasor/scripts/mine.lua` is kept.
- Unknown exe, unknown Bink and unknown `binkw32_real.dll` are each refused with the folder `UNTOUCHED`.
- An unreadable address JSON mid-transaction gives `install failed and was rolled back` and `UNTOUCHED_AFTER_ROLLBACK`.
- `-TrustBinkSha256` installs, and the manifest records the override.

This first run caught a real bug. The first uninstall had been single-pass, so it removed files before it found the changed one. That is now fixed and re-verified.

### Receipt script and schema test
The receipt script collects:
- OS product, version, build and UBR from the registry.
- CPU arch and name. Translation is `x86-on-arm64-emulation` on ARM64.
- The exe, container and slice sha (identical for a PE) and the build.
- The shas of kphasor.dll, the proxy, the real Bink and the manifest.
- The log sha and size, plus the parsed `host:` and `gl:` lines. The wine value comes from the runtime's line, not from PowerShell.
- The F12 result (`pass|fail|not-run`), recorded as `physical-keyboard`, `attested_by=user`.

`tools/platform_receipt_test.py` has 25 tests. Validation reads receipts as `utf-8-sig`, because Windows PowerShell 5.1 `Set-Content -Encoding UTF8` writes a BOM, and `json.loads('\ufeff{}')` fails with "Unexpected UTF-8 BOM". `test_bom_prefixed_receipt_validates` covers this. The receipt script now writes BOM-less UTF-8 through `[IO.File]::WriteAllText` after resolving the full path.
- `Receipts` (15 tests) covers the synthetic fixtures:
  - `native_pass` is valid and closes a cell.
  - `native_f12_fail` is valid but does not close one.
  - `native_arm64_emulated` is valid.
  - These are rejected: `wine_yes`, `wine_disagrees_with_log` (top level says no, log says yes), `no_host_line`, `missing_field`, `bad_sha`, `unknown_exe`, `f12_not_run`, `software_renderer` (llvmpipe) and `os_build_disagrees`.
  - `test_wine_rule_is_load_bearing` shows the log-line rule is what rejects the disagreeing fixture.
- `ScriptContracts` (10 tests) checks:
  - The PS1 emits every required key.
  - The PS1 regexes equal the Python ones.
  - The C++ `host:` and `gl:` format strings produce lines those regexes parse.
  - The overlay logs exactly once, after `ImGui_ImplOpenGL2_Init`.
  - The installer's exe allowlist is exactly BuildRecord sha→alias.
  - The installer contains its transaction and owned-only markers.
  - The scripts use no PowerShell 7-only syntax.

Red run: against the `HEAD` versions of `platform_win32.cpp` and `overlay.cpp`, `ScriptContracts` gives `FAILED (failures=2, errors=2)`. The failing tests are `test_cpp_gl_line_matches_regex`, `test_cpp_host_line_matches_regex`, `test_host_identity_detects_wine_by_export` and `test_overlay_logs_once_at_imgui_init`. The green run gives `Ran 25 tests ... OK`.

`python3 tools/platform_receipt_test.py --validate <receipt.json>` runs as a CLI: `native_pass` → `VALID native receipt` rc=0; `wine_yes` → 2 REJECT lines, rc=1.

## Proof boundary

- **No native Windows receipt exists yet.** Nothing here ran on Windows. `host_identity()` has not executed on any machine, native or Wine. The `host:`/`gl:` lines have never been seen in a real kotorphasor.log. Closing that needs W2: the user runs the installer and receipt script on a real Windows PC with a GPU.
- The PowerShell scripts were parsed and exercised with pwsh 7.3.12 on Linux. They were not run under Windows PowerShell 5.1. Registry and CIM calls in the receipt script need Windows, so the script has not been executed at all.
- The overlay-name match (`galaxy*`, `*overlay*`, `nvspcap*`) is checked as source text only. It has not been observed against a live module list.
- The GOG K1 Bink and the K2 Bink shas are unrecorded. K2, and K1 GOG if its Bink differs from Steam's, needs `-TrustBinkSha256` until someone hashes the intact GOG `binkw32.dll`.
- The `CMakeLists.txt`/ctest registration of the two Python tests is not done, because CMake is forbidden. They run by hand as shown above.

## Fix round

Continuation review: retained the completed W1 implementation and report rather
than duplicating it. The bounded re-check reached the receipt suite's existing
passing cases, but this heavily loaded mounted worktree stalled before a new
unittest summary; the prior green installer (7) and consistency (23) receipts
remain the last completed full runs. No Windows, Wine, game, capture, or live
lock activity was performed in this continuation.

## Round 3

Answers `/home/brunner56/kp-live-20260922/platform-w1-rereview.md` (W1-I1, M1–M8). The "Fix round" section above is stale: its counts are from before this round. Nothing was staged, committed or pushed. No game, Wine, real game folder or live-game lock was used.

### What changed

| finding | fix | referent |
|---|---|---|
| W1-I1 forged banner through print, kp.diagnostic `\r`, load-error text | `Runtime::log` escapes `\n` `\r` `\t` as `\n` `\r` `\t` and every other C0 byte and 0x7f as `\xHH` before the one `fprintf`. One call is one physical line. `raw[1024]` in, `body[4096]` out, so the worst case (4 bytes per byte) is never cut. Only this function's body changed in runtime.cpp; the other hunks there are not from this round. | runtime.cpp:278-319 |
| receipt anchor | banner pattern is now `^\[idle\] KotorPhasor …`. The runtime writes the banner at runtime.cpp:789 while `phase_` is still `Idle` (runtime.hpp:99), before any script loads. | receipt ps1:88, py `BANNER_RE` :72, `test_banner_is_written_at_idle_only` |
| stale claims | overlay.cpp comment and receipt header now say the escaping only holds for a DLL built with it, and that Lua `io` can still write the log. User doc says the same. | overlay.cpp:467-478, receipt ps1:15-45, docs/user/windows-native-install.md "What a receipt shows" |
| fixtures F1–F3 | `logs/forged_banner_print.log`, `forged_banner_diag_cr.log`, `forged_banner_error_text.log` (old-DLL shape) | `test_forged_banner_logs_yield_no_session`, `test_forged_banner_receipts_rejected`, `test_runtime_log_escapes_line_breaks` |
| M1 one-element array unrolled | `Get-Field` returns `, $prop.Value` | installer :113-122 |
| M2 `action` array | `Get-StringField` refuses any non-string value (path, action, sha256, backup, backup_dir, schema) | installer :124-131 |
| M3 entry order | pass 2 runs `replaced` steps before the rest, whatever the manifest order | installer :353-354 |
| M4 zero `replaced` | exactly one `replaced` `binkw32.dll` entry required | installer :240 |
| M5 duplicates | a path listed twice is refused in Assert | installer :218 |
| M6 links | `Assert-NoReparsePoint` walks every folder from the game folder down, before anything is removed. `Remove-BackupDir` deletes plain files one by one and never uses `-Recurse`; a subfolder or link inside is left with a warning. No `Remove-Item -Recurse` remains in the file. | installer :164-197, `grep -n Remove-Item` |
| M7 `$` before final `\n` | `\z` in backup-dir, created-path and sha patterns | installer :136-139 |

### Runs on the final bytes (host, 2026-09-27)

SHA-256: installer `9bb54c24…`, receipt ps1 `3f0d5ebf…`, platform_receipt_test.py `e591fbaa…`, runtime.cpp `83fec910…`.

- `host-cmd python3 tools/platform_receipt_test.py`: **Ran 65 tests, OK, 0 skipped** (245.7 s). pwsh 7.3.12 on PATH on the host, so every installer and PS-parser test ran. The earlier container run was 65 OK with 11 skipped (pwsh).
- `host-cmd python3 tools/platform_profile_consistency_test.py`: **Ran 23 tests, OK**.
- MinGW, `/tmp/kp-w1-build` on the host: `ninja win32/rt_runtime.obj win32/rt_overlay.obj CMakeFiles/kphasor.dir/src/runtime/runtime.cpp.o` → 3/3 built, rc=0 (i686-w64-mingw32-g++ and native).
- Escape loop, extracted verbatim from runtime.cpp:290-310 into a standalone file: input `x\n[idle] KotorPhasor 0.1.0 starting (embedded role)\r\x01\x7f\tz` gives one output line, `…x\n[idle] …\r\x01\x7f\tz` (`/tmp/kp_esc_check.cpp`).
- Review probes, rerun. `Install-probe.ps1` was regenerated from the final installer plus the reviewer's same two synthetic allowlist lines (diff shows only those two lines):
  - `receipt_forge.r3final.out`: F1, F2, F3 and control F4 all **rejected** by `validate(--log)`; 0 VALID. F5 and F6 still rejected.
  - `ps_parse.r3final.out` (the receipt script's own parser, all 85 lines verbatim in the final ps1): F1–F4 all have problems and no host line.
  - `inst.r3final.out` + `inst2.r3final.out`: sentinel ok in all 40 checks, 0 gone. Every T/N1–N4/N9 tamper case "uninstall refused, nothing removed", including N4arrBD, N4arrPath, N4arrSha, N4schema, N5actArr, N9dup (and its rerun), N11onlyKp, N2trailnl, N2case. N10order now restores the original Bink and uninstalls. S1 (backup dir symlinked outside) refused, `victimdir/precious.txt` still there. S2 (`kotorphasor` symlinked) refused, `mine.lua` still there. Happy path, T3–T8, H1 (20,000 entries) and H2 (depth) as before.

### Grill me

1. *Does the reparse-point guard hold for an NTFS junction under Windows PowerShell 5.1?* Unverified. No Windows here. What holds: the check is `[IO.File]::GetAttributes(path) -band ReparsePoint` on each folder, which is the attribute NTFS sets on junctions. And no `Remove-Item -Recurse` is left, so 5.1's junction walking has nothing to walk. On pwsh 7 Linux with symlinks, S1 and S2 are refused (`inst2.r3final.out`). One run of S1 on real Windows 5.1 with `mklink /J` would settle it.
2. *Does the escaping hold in a running DLL?* Not run in a game (out of scope). Referents: the loop's standalone check above, the MinGW object compile, and `test_runtime_log_escapes_line_breaks` (source-level). print, kp.diagnostic and load errors all reach `Runtime::log` through `runtime_log_sink`, so this one choke point covers all three.
3. *Is the `[idle]` anchor itself a fix?* No, the escaping is. On an old DLL a mod can write `[idle]` too: `receipt_forge_idle_variant.r3.out` shows F1/F3 with an `[idle]` forged banner give `problems=[]`. The receipt can only record the DLL sha, and the header and user doc say to check it against the shipped build.
4. *Does escaping break any caller that meant to write several lines?* No caller found: `grep -rnE '(\blog|platform::log)\([^;]*\\n' src` returns nothing. Multi-line Lua tracebacks now appear on one line with `\n\t` shown. The old 1024-byte cut is unchanged.
5. *Is every manifest value checked in the form it is used?* Yes for strings: `Get-StringField` rejects arrays at Assert, and later uses read the same property that passed (N4arr*, N5actArr refused with nothing removed).

Open question for the next reviewer: item 1. The single check is S1 on Windows PowerShell 5.1 with a junction.

## Follow-up: W1R3-m1 and W1R3-m2

Answers `/home/brunner56/kp-live-20260922/platform-w1-r3-review.md`. Sole writer,
resumed from a stopped-for-model-switch state in which the token, fixtures and
mutation test already existed in the worktree; this pass verified each piece
against the review's findings and ran the three required suites to green. No
game, Wine, real game folder or live-game lock was used. Nothing was staged,
committed or pushed (worktree stays dirty, no git writes).

### W1R3-m1 (docs: the DLL-sha mitigation can't be acted on)

Fix, cheaper option taken: a log-format token in the host line.

- `src/devtools/overlay.cpp`: `log_host_and_gl()` writes
  `"kp-session=%s log=esc1 %s"`, not the bare host string. Referent:
  `grep -n 'log=esc1' src/devtools/overlay.cpp` and
  `test_host_line_carries_the_log_format_token`, which regexes the exact
  format string out of the source and asserts on it (tools/platform_receipt_test.py:906-917).
- Python validator requires it: `HOST_RE` (`tools/platform_receipt_test.py:81`)
  contains ` log=esc1 host: ` as a literal; `PRE_ESCAPE_HOST_RE` is the same
  pattern with that token removed and is used only to detect and name the
  no-token shape (`tools/platform_receipt_test.py:83`, :147-149). Referents:
  `test_host_pattern_needs_the_token`, `test_pre_escape_host_line_refused`,
  and the `old_dll_no_token` fixture pair
  (`tools/fixtures/platform-receipts/old_dll_no_token.json` +
  `logs/old_dll_no_token.log`), which is rejected with "without log=esc1".
- PowerShell parser requires it: `$HostPattern` and `$PreEscapeHostPattern` in
  `scripts/receipts/windows-native-receipt.ps1:98-99` are the same two
  patterns, byte-identical in shape to the Python ones (`test_receipt_regexes_match_python`,
  `test_ps1_parser_matches_python`). The parity test is behavioural, not just a
  regex-text comparison: it globs every fixture log
  (`sorted((FIXTURES / "logs").glob("*.log"))`, asserting at least 9 files —
  currently 16, including `old_dll_no_token.log` and all six `escaped_*.log`
  — tools/platform_receipt_test.py:1083-1093) and runs the real PS1 parser
  block against each one inside pwsh, comparing its JSON to
  `session_evidence()`. It is not on a fixed pre-round list.
- Docs describe exactly what's checked, and the non-actionable wording the
  reviewer flagged is gone. `docs/user/windows-native-install.md` now reads
  "The validator does not check which build that hash belongs to. No list of
  release hashes exists yet." (the old "so you can check which build ran" is
  gone) alongside "A `kphasor.dll` with the change writes `log=esc1` in its
  host line. The receipt refuses a host line without it, so an older DLL's
  own lines fail. A script can still write the token itself." The receipt
  script's own header (`scripts/receipts/windows-native-receipt.ps1:33-37`)
  says the same in the "supporting evidence, not proof" list. This
  supersedes round 3's Grill #3 answer ("the header and user doc say to
  check it against the shipped build") — that sentence is no longer in
  either doc.
- Scope: `sha256sum src/runtime/runtime.cpp` still gives `83fec910…`
  (unchanged from the r3 reviewer's recorded sha), so `src/runtime/**` was
  not touched by this fix, consistent with the "overlay.cpp host/gl line
  format only" constraint. I could not byte-diff the current overlay.cpp
  against the exact r3-final copy (539e4cbb…, not preserved anywhere on
  disk); the closest artifact, `w1-fix-scratch/orig/overlay.cpp`, predates
  round 3's own `kp-session=` mechanism and so is the wrong baseline for an
  isolated diff. Scope for this fix specifically rests on the source-level
  regex test above, which pins the log() call to exactly
  `"kp-session=%s log=esc1 %s"` plus its comment.

### W1R3-m2 (tests: no in-suite behavioural test of the escaping)

`tools/platform_receipt_test.py` class `RuntimeLogEscaping` (needs a host C++
compiler; skips without one — it ran here):

- `test_python_copy_matches_compiled_runtime_log`: compiles
  `src/runtime/runtime.cpp`'s escape loop standalone and checks it against a
  Python re-implementation over a corpus (every byte 1-255, the round-3
  forgery string, oversize input, embedded NUL, U+0085, and all six
  `ESCAPED_FORGERIES` messages).
- `test_compiled_runtime_log_stops_the_forgeries`: runs the escaped forgeries
  through the compiled loop and diffs the output against
  `tools/fixtures/platform-receipts/logs/escaped_*.log` byte for byte.
- `test_check_goes_red_without_the_escaping` is the mutation test the review
  asked for: it patches `runtime.cpp`'s source text two ways ("if (true)"
  instead of the control-byte test, and passing the raw unescaped buffer to
  `fprintf` instead of the escaped `body`), rebuilds each mutant, and asserts
  the escaped-forgery check then reports `escaped_print_newline` and
  `escaped_error_text` as VALID — i.e. it fails red without the escaping and
  passes green with it. `self.assertEqual(src.count(old), 1, old)` guards
  against the patch silently matching nothing.
- Escaped-form fixtures: `tools/fixtures/platform-receipts/logs/escaped_print_newline.log`,
  `escaped_diag_cr.log`, `escaped_error_text.log`,
  `escaped_literal_backslash_n.log`, `escaped_unicode_seps.log`, each one
  physical line holding the forged `\n[idle] KotorPhasor…` block, matching
  the r3 review's R1/R2/R3/R5/R4 probes. `test_escaped_forgery_fixtures_are_what_the_runtime_writes`
  checks the fixture files against the compiled loop too.

### Runs (this session, worktree, TMPDIR=/home/brunner56/kp-live-20260922/tmp-w1fu)

- `host-cmd python3 tools/platform_receipt_test.py` → `Ran 73 tests ... OK`,
  no `skipped=` in the summary line (0 skipped), 418.3 s, pwsh 7.3.12 on the
  host reached through `host-cmd`. 73 vs the round-3 count of 65: 8 new tests
  (`RuntimeLogEscaping` ×3, plus `test_host_pattern_needs_the_token`,
  `test_pre_escape_host_line_refused`, `test_host_line_carries_the_log_format_token`,
  `test_escaped_forgery_fixtures_are_what_the_runtime_writes`, and one more
  token/format assertion). Note: pwsh here is 7.3.12, the same version round 3
  used — this does not touch the open Windows PowerShell 5.1 junction
  question.
- `host-cmd python3 tools/platform_profile_consistency_test.py` → `Ran 23
  tests ... OK`.
- MinGW compile of `src/devtools/overlay.cpp` alone, the same flags
  `src/runtime/runtime.cmake:120-121` uses (`-std=c++20 -Wall -Wextra -O2
  -Isrc -Ithird_party/luajit/src -Ithird_party/imgui`), object written to
  `/home/brunner56/kp-live-20260922/review-probes-w1-r3/mingw-final/rt_overlay.obj`
  (fresh path, the writer's `/tmp/kp-w1-build` untouched): exit status of the
  compiler itself (no pipe) is `rc=0`, zero warnings, object file present
  (`ls -la` timestamp 2026-09-27 19:17:36).

### Final bytes (sha256)

- `src/devtools/overlay.cpp` `9e06f9c7…`
- `scripts/receipts/windows-native-receipt.ps1` `78546835…`
- `tools/platform_receipt_test.py` `52792855…`
- `docs/user/windows-native-install.md` `7829f2fb…`
- `src/runtime/runtime.cpp` `83fec910…` (unchanged from round 3, confirming no `src/runtime/**` edits this round)

### Counts

- `tools/platform_receipt_test.py`: 73 tests, OK, 0 skipped.
- `tools/platform_profile_consistency_test.py`: 23 tests, OK.
- MinGW cross-compile of `overlay.cpp`: rc=0, 0 warnings.

### Grill me

1. *Does the `log=esc1` token stop a script from forging a host line?* No,
   and the docs say so. It only refuses a host line written by a DLL that
   predates the escaping — a genuine old-DLL artifact. A script with `io`
   access can write `log=esc1` itself, and the round-3 review's `IO1` case
   (whole-block forgery through `io`, VALID) already demonstrated this before
   the token existed. Referent: `docs/user/windows-native-install.md` "A
   script can still write the token itself."; `tools/fixtures/platform-receipts/logs/old_dll_no_token.log`
   is the only case the token actually closes.
2. *Does "0 skipped" mean the PowerShell-5.1 question is settled?* No. The
   pwsh reached via `host-cmd` here is 7.3.12 — `host-cmd pwsh -v` →
   `PowerShell 7.3.12`, the same binary round 3 used. This run adds
   confidence that the parser-parity and installer suites execute at all
   under this harness; it says nothing new about Windows PowerShell 5.1 or a
   real NTFS junction, which stays the one open item from round 3.
3. *Is the scope of this change actually "overlay.cpp host/gl line format
   only", as instructed?* Confirmed for `src/runtime/**` by an unchanged sha
   (`83fec910…`, same as round 3). Not independently confirmed for
   overlay.cpp by a byte diff against the exact r3-final source, because that
   copy (539e4cbb…) isn't preserved anywhere on disk I could find — the
   nearest artifact predates round 3's own session-id mechanism and is the
   wrong baseline. What stands in for that: `test_host_line_carries_the_log_format_token`
   pins the log call to exactly `"kp-session=%s log=esc1 %s"`, and
   `test_log_line_comments_do_not_overclaim` checks the comment. Unverified
   beyond that.
4. *Is the `ReceiptParserParity` test really exercising the new fixtures, or
   a stale fixed list?* It globs `(FIXTURES / "logs").glob("*.log")` with
   `assertGreaterEqual(len(logs), 9)` — 16 files exist now, all included.
   Referent: `tools/platform_receipt_test.py:1083-1093`.

Open questions carried forward: the NTFS-junction-under-PowerShell-5.1
question from round 3 (unchanged, still needs real Windows); and item 3
above (no byte-level diff against the exact r3-final overlay.cpp).
