# Release ZIP marker triage: KotorPhasor console previews

Read-only triage. I did not modify, rebuild, move or publish any ZIP, builder or receipt. Date: 2026-09-27.

## What was scanned

| ZIP | sha256 (full) | entries | findings | expected |
|---|---|---|---|---|
| `/home/brunner56/kp-release-20260927/kotorphasor-k1-k2-gog-console-preview.zip` | `0388d0806c74c0ad158f7d120165a5d530798c14fbbaa1674b8c6c759ce867c9` | 18 | 28 | 2 |
| `/home/brunner56/kp-release-20260922/kotorphasor-k1-gog-console-preview.zip` | `de14c1261e0e1b0e0aec124c8676f8e40ec696b47a258d9e1b0adc97af677131` | 17 | 30 | 2 |

Both hashes match the brief's prefixes (`0388d080…`, `de14c126…`).

Command, run from the worktree `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`:

```
python3 tools/scan_release_zip.py --allow '*.dll' <zip>
```

Both runs exit 1 (`ok: false`) and report `"unchanged": true`, so the ZIP size and mtime were the same before and after.

**Correction to the brief.** The brief's "16 markers" is the scanner's `"markers": 16` field. That field counts the privacy patterns the scanner uses: 15 fixed patterns plus the username. It does not count findings. The real finding counts are 28 and 30. The 2 `expected` findings in each ZIP are the PE magic of `kphasor.dll` and `binkw32.dll`, both allowed by `--allow '*.dll'`.

## Every finding, classified

Classes:
- **a:** intentional and acceptable.
- **b:** harmless, but strip it in the next build.
- **c:** a real leak of private information.
- **d:** a scanner false positive.

`Z7` is the 20260927 ZIP and `Z2` is the 20260922 ZIP. Entry paths are inside `kotorphasor-preview/`.

### F1. `kphasor.dll`: 9 `/home/` hits (Z7 lines 112954, 113084–113086, 114111, 114121, 114123, 114149, 114413; Z2 lines 112973, 113103–113105, 114130, 114140, 114142, 114168, 114432) — class b

- **What it is.** 12 unique strings in `.rdata`, such as `/home/brunner56/kp-release-20260927/source/src/runtime/../../third_party/imgui/imgui.cpp` and `…/imgui.h`, `imgui_internal.h`, `imstb_*.h`, and `backends/imgui_impl_{win32,opengl2}.cpp`. Z2 has the same strings with `kp-release-20260922`. I extracted them from the DLL in memory with a printable-run regex.
- **Cause.** ImGui's `IM_ASSERT` falls back to `assert()` (`third_party/imgui/imgui.h:92`). The Windows compile rule never defines `NDEBUG`, so every assert embeds `__FILE__`. That rule is `src/runtime/runtime.cmake:111` in the ca329e5 export and `:120` in the worktree. It passes absolute `${src}` paths.
- **What leaks.** The local username (`brunner56`) and the private release-directory name. No project-code DWARF is present. The DLL does carry about 12 MB of `.debug_*` sections, but those come from the static MinGW CRT and libstdc++, and their paths are Fedora `/builddir/...` and `/usr/i686-w64-mingw32/...`. The PE section table shows `.debug_info` at 7.6 MB and `.debug_loclists` at 2.1 MB. These sections matter for size, not privacy.
- **Why b and not c.** The brief puts these paths in b, and I agree on the mechanism: path remapping removes them. The username is still exposed, so treat this as the most urgent item in b.
- **Fix.** See R1 and R2.

### F2. `packaging-receipt.json` lines 4–8: `.superpowers` (both ZIPs) — class b

- **What it is.** These lines are entries in the receipt's `exclusions` list, such as `.superpowers/sdd/lua-boundary-validation-plan/task-10-console-report.md`. Only the file names ship, not their contents. The scanner reports only the `.superpowers` lines. The same list, which is identical in both ZIPs with 187 entries, also names:
  - `data/adjudication/*_bindings.json`
  - 40+ `docs/harness-research/*.md` titles, some carrying dates (`live-softlock-recovery-crash-20260909.md`)
  - a Ghidra project (`docs/agentdecompile_projects/my_project.gpr`, `.rep/*`)
  - `data/research/phasor_{inventory,mapping}.json`
- **Why it is listed at all.** On purpose. Z2 `README-preview.md:24` says: "Its packaging receipt records every exclusion". Z7 `README-preview.md:5` points to `packaging-receipt.json`.
- **Why b.** No username, no absolute path and no content. It still reveals the names of internal work items.
- **The real problem is upstream.** The "clean ca329e5 export" in `…/source/` contained `.superpowers/` and a Ghidra project in the first place.
- **Fix.** See R5.

### F3. `source.tar.gz!source/data/research/phasor_structs.json`: private folder `research` (both) — class a

Evidence that this file is meant to ship:
- The receipt's `research_exception` field: "retained because structs.cmake requires it to regenerate the shipped layout table".
- Z2 `README-preview.md:24`: "The layout generator input data/research/phasor_structs.json is retained because the build requires it."
- Z7 `README-preview.md:24`: "The required layout-generator input phasor_structs.json is retained".
- `src/api/structs.cmake:37` lists it in `DEPENDS` of the `gen_structs.py` rule when Python3 is found.

What the file holds: 149 KB, 25 Ghidra-derived struct layouts with field offsets, `how_to_obtain` prose, and an `access_notes` block. `access_notes` describes the private corpus workflow (`kpdiscover.py --corpus`, `binary_id=8`, `tmp/structwork/*`), with no username or absolute path.

The file cannot simply be trimmed. `tools/gen_structs.py:232` parses `access_notes` for the CExoArrayList census, and `:467` emits `how_to_obtain` into the generated `.inc`, so that text already ships inside the DLL.

The scanner flags this file because `research` is in `PRIVATE_PARTS`. See R9 for a documented-exception tweak.

### F4. `source.tar.gz` magic `gzip` (both) — class d

The scanner opens this archive as a nested archive and scans inside it. It also reports the archive's own gzip magic, even though the `.tar.gz` suffix agrees with it. Fix: see R9(a).

### F5. `source.tar.gz!source/.gitignore:40`: `.worktrees` (both) — class d

Line 40 is the ignore pattern `.worktrees/`. It is not a path to anything. Fix: see R9(b).

### F6. `source.tar.gz!source/data/events.draft.toml:5`: `/home/` (both) — class c, severity MEDIUM

- **Line 5.** `#   /home/brunner56/biodecompwarehouse/kotorxid/output/kotor_readable/`
- **Line 6.** `K1__k1_win_gog_swkotor.exe/src/AspyrBuild/depot/KOTOR/PC_Source/Dev/`
- **What leaks:**
  - the username
  - the private decompilation-warehouse root
  - the recovered-source tree layout
  - 137 `*.cpp:NNN` citations into recovered C, with paraphrased branch logic and Ghidra field names (for example line 124: `nwscreature.cpp:11934-11989 case 1: … RunScript(script_resrefs+1)`). I found no verbatim code blocks, only paraphrase and citations.
- **Is it needed?** No. Nothing in the build reads it. Its only consumer is `tools/merge_event_draft.py`, and no `CMakeLists.txt` or `*.cmake` file references it.
- **Is it already public?** No. The file is in commit ca329e5 (`git grep` hit), but `gh repo view bodencrouch/KotorPhasor` returns `"visibility":"PRIVATE"`. This package would be its first publication.
- **Fix.** See R4.

### F7. Run-ID markers in source comments — class c, severity INFORMATIONAL

| File | Z7 line | Z2 line | Run ID quoted |
|---|---|---|---|
| `scripts/harness/kpharness/oracle.py` | 246 | 246 | `20260910-095338` |
| `scripts/harness/scenarios/k1_fresh_trask_quest.toml` | 141 | 141 | `tmp/k1_harness/runs/20260915-071620` |
| `src/harness/engine_k1.cpp` | 1009 | 995 | `20260909-091519` |
| `tools/kp_harnesstest.cpp` | 517 | 517 | `20260909-055643` |
| `src/harness/fields.hpp` | — | 356 | `20260909-055643` |

- **What they are.** UTC timestamps of private live runs, cited as evidence in comments. They contain no username or absolute path, and the run data does not ship.
- **Why c.** The repo is private, so these IDs are unpublished. The brief lists private run IDs under c. The exposure is only "a developer ran a test at this time", hence informational.
- **Why Z7 has one fewer.** Z7 replaced `fields.hpp` with a reviewed overlay (`source-provenance.json` overlay sha `37cf59e1…`), and the overlay dropped this comment.
- **Fix.** Optional: see R6.

### F8. `source.tar.gz!source/third_party/luajit/doc/img/contact.png`: magic `png` (both) — class d

This is an upstream LuaJIT documentation image, pinned at `luajit_commit 1ee778a4…`. It is not game content. Fix: see R9(c).

### F9. `source.tar.gz!source/third_party/luajit/doc/install.html:165, 189`: `/home/` (both) — class d

The lines are upstream example text: `make PREFIX=/home/myself/lj2`. Fix: see R9(c).

### F10. `source.tar.gz!source/third_party/luajit/src/host/minilua`: `magic: elf`, `not UTF-8`, `NUL byte` (3 findings, both) — class b

- **What it is.** The file is 139,392 bytes, mode 0755. It is a 32-bit i386 ELF (`e_ident[EI_CLASS]=1`, `e_machine=0x03`) built on this Fedora host; it embeds `GCC: (GNU) 16.2.1 … (Red Hat 16.2.1-2)`. It contains no `/home` string.
- **Decision: it is a build-time host tool and should not ship.**
  - LuaJIT's `src/Makefile` compiles `minilua` from `host/minilua.c` and uses it only while building to run DynASM and `genminilua.lua`.
  - `host/minilua.c` ships in the same tarball, so the corresponding source is complete without the binary.
  - A user who rebuilds LuaJIT gets a fresh `minilua` from make. The prebuilt Linux ELF is not needed to build `kphasor.dll`, and it is useless on Windows.
- **Why it slipped through.** The builder's name list blocks `third_party/luajit/src/luajit` and `…/host/buildvm` but not `…/host/minilua`. That list is at Z7 `package.py:40` and Z2 `package.py:19`. `minilua` has no suffix, so the `.o`/`.exe` suffix filter misses it too. The receipt shows `host/minilua.o` and `host/buildvm` were excluded.
- **Fix.** See R3.

### F11. `live-acceptance.json:10` (Z2 only): `/home/` — class c, severity LOW-MEDIUM

- **What it is.** `"run_directory": "/home/brunner56/kp-live-20260922/stage-k1/runs/20260926-234927"`.
- **What leaks.** The username, the private evidence directory and a private run ID, in a file placed at the package top level.
- **Status in Z7.** Fixed. Z7's `live-acceptance.json` has no path field, and the scanner reports no finding for it.
- **Fix.** See R7, to keep the fix from regressing.

## Counts per class

The count is findings, with each scanner line counted separately.

| Class | Z7 (0927) | Z2 (0922) | Items |
|---|---|---|---|
| a: intentional | 1 | 1 | F3 |
| b: harmless, strip next build | 17 | 17 | F1 (9), F2 (5), F10 (3) |
| c: real leak | 5 | 7 | F6 (1, MEDIUM), F7 (4 in Z7, 5 in Z2, INFO), F11 (Z2 only, 1, LOW-MEDIUM) |
| d: scanner false positive | 5 | 5 | F4, F5, F8, F9 (2) |
| **Total** | **28** | **30** | |

## Scanner misses (outside classes a–d, found by hand)

These did not appear in the scanner output, but they drive the top risks.

**M1. Tar headers carry the username (c, MEDIUM, both ZIPs).**
- All 606 members of `source.tar.gz` have `uname=gname=brunner56` and `uid=gid=1000`. Their mtimes are the real ones from 2026-08/09.
- Cause: `tf.gettarinfo(str(f), …)` copies the owner from the filesystem, at Z7 `package.py:86` and Z2 `package.py:58`.
- The scanner never checks `TarInfo.uname` or `gname`.
- This leaks the same username as F1 and F6, through a path that `-ffile-prefix-map` cannot fix.

**M2. `codecaves.toml` carries retail instruction bytes, including bytes from other games (owner decision, not asserted as infringement).**
- `source/data/codecaves.toml` is 4.15 MB and holds 16,184 `sig` entries.
- Together the entries hold 349,212 signature bytes. 289,273 of those bytes are not fill bytes (`CC`, `90` or `00`), so they are real instruction bytes from retail executables.
- Entries by `build`:

  | Build | Entries |
  |---|---|
  | `nwmain` (Neverwinter Nights) | 9,214 |
  | `k2_gog_aspyr` | 1,996 |
  | `k1_gog_103` | 1,562 |
  | `JadeEmpire` | 1,544 |
  | `k1_amazongames` | 1,064 |
  | `k2_win_cd_10` | 752 |
  | `k2_win_cd_10b` | 752 |
  | `k2_steam_aspyr` | 35 |
  | `k2_android_x86` | 17 |

- Comment lines such as 43793 name the corpus layout (`Other_BioWare_Engines/Aurora/nwmain.exe`).
- Neither package supports NWN or Jade Empire.
- Each signature is short (16 bytes median, 96 maximum), which is the usual size for patch signatures. The total volume and the other-game entries still deserve an explicit owner decision.
- The address tables also carry 16-byte `expected_bytes` per hook site (for example `535556578b7c2414…` for `RunScript`). That is standard interop data.

**M3. The private corpus layout ships in tools and comments.**
- `tools/gen_address_tables.py:84-111` hardcodes corpus-relative `reference_image` paths such as `biodecompwarehouse/agentdecompile/target/swkotor-gog/swkotor.exe.gog`, `agentdecompile-nvme/agentdecompile_projects/extract/raw/…`.
- `src/harness/engine_k1.cpp:7-8` names `kotor_readable … AspyrBuild/depot/KOTOR/PC_Source/Dev`.
- `tools/kpdiscover.py:291` names `biodecompwarehouse/kotorxid/db/kotorxid.sqlite`.
- None of these carries a username. They do undercut the builder's JSON sanitization, which strips `reference_image` from JSON (receipt `sanitizations`, 8 in Z2 and 9 in Z7) while the generator source still lists the same paths.
- Severity: LOW.

**M4. The builders never run the scanner.**
- The scanner's docstring says "The package builder (package_creative_harness.py) imports these rules". Neither `package.py` imports them.
- Z7 checks CRC and manifest hashes (`package.py:97-101`) but never scans for privacy. That is how F1, F6, F10 and M1 reached a ZIP that then got a `verification.json` with `"zip_crc":"PASS"`.

**Retail content check: no retail game assets are present in either ZIP.**
- Top level: 18 or 17 entries. The only binaries are `kphasor.dll` and `binkw32.dll`.
- `binkw32.dll` is the project's own proxy, not RAD's library:
  - It is 99,978 bytes, built by MinGW from `binkw32.cpp` (string present).
  - It exports only forwarders to `binkw32_real._Bink*@N`.
  - Its build rule is `src/proxy/proxy.cmake:31`.
- Source tarball: 606 files. The magic check finds only `contact.png` and `minilua`. There are no BioWare `XXXXV?.?` headers, and no Bink, media, archive or GFF files. No file has a retail suffix (`.bif .key .mdl .mdx .rim .erf .mod .sav .ncs .nss .bik .tlk .2da .ut* .dlg .tga .tpc .dds .lip .lyt .are .ifo .exe`).
- The package ships no saves.
- The one retail-derived category is the byte signatures in M2 and the `expected_bytes` above.

## Recommended release-builder changes (not applied)

Line numbers refer to the builder files under `/home/brunner56/kp-release-2026092{2,7}/`. CMake lines are given for the worktree first, with the ca329e5 export in brackets.

**R1. Remap build paths (fixes F1).** Add these flags to every `add_custom_command` compile line:

```
-ffile-prefix-map=${CMAKE_SOURCE_DIR}=.
-fmacro-prefix-map=${CMAKE_SOURCE_DIR}=.
```

- Put them on `src/runtime/runtime.cmake:120` [export :111]. That is the only line producing hits today.
- Also put them on:
  - `src/hooks/hooks.cmake:111` [:92]
  - `src/api/structs.cmake:117`
  - `src/proxy/proxy.cmake:31`
  - `CMakeLists.txt:103` [:94]
- `add_compile_options` and `CMAKE_CXX_FLAGS` do not reach these custom commands, so each line needs the flags directly.
- Do not use `-DNDEBUG` as the path fix. It turns off live ImGui asserts in the shipped DLL, which is a separate behavior decision.

**R2. Strip debug sections (size, not privacy).** Add `-s` or `-Wl,--strip-debug` to the `kphasor.dll` link at `src/runtime/runtime.cmake:138` [export :129]. This removes about 12 MB of static-runtime DWARF and 54,609 COFF symbols. Do the same for the proxy at `proxy.cmake:31`, which has 1,094 symbols.

**R3. Reject executables in the source tarball (fixes F10).** In `source_allowed`, at Z7 `package.py:32-41` and Z2 `:11-20`:
- Add `third_party/luajit/src/host/minilua` to the name set.
- Better: after reading `data` at Z7 `:85` / Z2 `:57`, reject any `scan_release_zip.magic_kind(data)` result in `{'elf','pe/dos','mach-o','wasm'}`. That catches the next unlisted host binary too.
- Optionally, drop LuaJIT's generated build outputs (`buildvm_arch.h`, `lj_*def.h`, `vmdef.lua`) by exporting LuaJIT from its pinned commit rather than from a built tree.

**R4. Keep non-build research files out of `data/` (fixes F6).**
- Add `data/events.draft.toml` to the exclusions. It is not a build input.
- Better: turn `roots` at Z7 `:26` / Z2 `:5` into an explicit allowlist of the `data/` files CMake consumes, instead of the whole `data` root.
- Fix line 5 of the file itself in the repo so that it does not return.

**R5. Normalize tar metadata (fixes M1).** At Z7 `package.py:86` / Z2 `:58`, after `gettarinfo`:

```
info.uid = info.gid = 0
info.uname = info.gname = ''
info.mtime = <SOURCE_DATE_EPOCH>
info.mode = 0o644  # or 0o755 for executables
```

**R6. Clean the export and shrink the receipt (fixes F2).**
- Build `source/` from `git archive ca329e5` plus the overlays, so `.superpowers/`, `docs/agentdecompile_projects/` and LuaJIT objects never enter it.
- In the receipt, record exclusions as `{glob, count, sha256-of-sorted-list}` for private directories rather than listing every file name. That keeps the audit trail without disclosing the file names.
- Optional: reword the run-ID comments (F7) as "a live run on 2026-09-09" in the repo.

**R7. Guard receipts copied into the package (fixes F11 regression).** Z7 `package.py:74` and Z2 `:47` copy `live-acceptance.json` and the other receipts as they are. Before copying, assert that no string value in them starts with `/` or contains a pattern from `privacy_markers()`.

**R8. Gate the ZIP on the scanner (fixes M4).**
- After writing the ZIP (Z7 `:93-95`, Z2 `:65-67`), and before `zip-sha256.txt`, call `scan_release_zip.scan(z, allow=('*.dll',))` and fail unless `ok`.
- Commit an explicit allowlist for the known d-class items (R9) so the gate stays strict.

**R9. Scanner tweaks in `tools/scan_release_zip.py` (for the d class and M1).**
- (a) In `_scan_blob` (line ~180), skip the `magic` finding when `nested` is true and the kind matches the suffix: gzip for `.tar.gz`/`.tgz`, zip for `.zip`.
- (b) In `path_scan`, for entries named `.gitignore`, skip lines that are pure ignore patterns (no `/home/`-style absolute prefix).
- (c) Add `--allow-marker GLOB:MARKER` so reviewed upstream content can be allowlisted. Examples: `third_party/luajit/doc/*:/home/`, `third_party/luajit/doc/img/*.png:magic`, and `source/data/research/phasor_structs.json:private folder`.
- (d) In `_scan_tar`, flag `member.uname`/`gname` when they match `usernames()`, and flag non-zero uid/gid (M1).

## Summary table

| # | Entry | Z7 | Z2 | Class | Severity | Fix |
|---|---|---|---|---|---|---|
| F1 | `kphasor.dll` `__FILE__` `/home/brunner56/kp-release-*/source/...imgui*` | 9 | 9 | b | username exposed | R1 (+R2 size) |
| F2 | `packaging-receipt.json` `.superpowers/...` names | 5 | 5 | b | names only | R6 |
| F3 | `data/research/phasor_structs.json` | 1 | 1 | a | — | R9(c) allow |
| F4 | `source.tar.gz` gzip magic | 1 | 1 | d | — | R9(a) |
| F5 | `.gitignore:40` `.worktrees/` | 1 | 1 | d | — | R9(b) |
| F6 | `data/events.draft.toml:5` corpus path + username | 1 | 1 | c | MEDIUM | R4 |
| F7 | run IDs in 4–5 source comments | 4 | 5 | c | INFO | R6 (optional) |
| F8 | luajit `doc/img/contact.png` | 1 | 1 | d | — | R9(c) |
| F9 | luajit `doc/install.html` `/home/myself` | 2 | 2 | d | — | R9(c) |
| F10 | `third_party/luajit/src/host/minilua` ELF | 3 | 3 | b | — | R3 |
| F11 | `live-acceptance.json:10` `run_directory` | 0 | 1 | c | LOW-MEDIUM | R7 (fixed in Z7) |
| M1 | tar `uname/gname=brunner56` on 606 members | miss | miss | c | MEDIUM | R5, R9(d) |
| M2 | `codecaves.toml` retail bytes incl. NWN/Jade Empire | miss | miss | owner decision | — | R4-style exclusion or trim |
| M3 | corpus layout in tools/comments | miss | miss | c | LOW | optional |
| M4 | builders do not run scanner | — | — | process | — | R8 |

## Grill me

**1. Why is F7 in class c and not b? (weakest answer)**
- The brief lists "private run IDs" under c.
- `gh repo view bodencrouch/KotorPhasor --json visibility` returned `PRIVATE`, so these comments would be published for the first time.
- The run IDs are only timestamps, so I rated the severity INFO. If the repo goes public before release, F7 moves to b and F6 drops to LOW.
- I did not finish checking whether `origin/main` contains the same lines, because the `git grep` over `origin/main` timed out and I stopped it. ca329e5 does contain `events.draft.toml` (`git grep` hit).

**2. Why is F1 in class b when it exposes the username?**
- The brief assigns `__FILE__` paths to b, and `-fmacro-prefix-map` removes them fully.
- The only source is ImGui asserts through `runtime.cmake:120` [export :111]. No project DWARF is present: `.debug_line_str` holds only `/builddir` and `/usr` paths.
- I still flag it as the most urgent item in b.

**3. Is `phasor_structs.json` really required?**
- It is required only when Python3 is found. `structs.cmake:37` lists it in `DEPENDS`. Without Python, the checked-in `src/generated/structs_k1.inc` is used.
- Keeping it matches both READMEs.
- It cannot be trimmed without changing the generator: `gen_structs.py:232` and `:467` read `access_notes` and `how_to_obtain`.

**4. Is `minilua` really build-time only?**
- LuaJIT's `src/Makefile` builds `host/minilua` from `host/minilua.c`, which ships, for DynASM and code generation.
- The shipped file is an i386 Linux ELF, so the Windows DLL cannot load it.
- I did not rebuild to prove that removing it breaks nothing. Not checkable here under the read-only constraint.

**5. Is M2 (codecaves) really out of scope?**
- The NWN and Jade Empire entries are not referenced by the K1 or K2 support these packages claim. I base this on the entry counts by `build`.
- I did not check whether any Lua example calls `findsig` with an NWN signature. Unverified.

**Open question I could not settle.** Is `origin/main` already carrying `events.draft.toml:5` and the run-ID comments? One check settles it: `git grep -n 'biodecompwarehouse/kotorxid/output' origin/main -- data/events.draft.toml`. It only matters if the repo is made public.
