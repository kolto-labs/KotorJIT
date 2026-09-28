# Creative packaging fix round: independent re-review

Date: 2026-09-27. Reviewer: separate agent, round 2.
Worktree: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`.
Prior review: `/home/brunner56/kp-live-20260922/creative-packaging-p0-p4-review.md` (I-1..I-4, M-1..M-9).
Writer report: `.superpowers/sdd/lua-boundary-validation-plan/creative-packaging-p0-p4-report.md`, fix-round sections.
Scratch: `/home/brunner56/kp-live-20260922/review-probes-packaging-r2/`. Nothing was published.

Scope held:
- No source file was edited.
- No git write was made (no reset, stash, staging or commit).
- No game, Wine, Gamescope or capture was started, and the live-game lock was not touched.
- Every probe tree lives under the scratch folder, and each probe script deletes its own trees at the end (`cleanup done: True` in each output).

- Disclosure: I once ran `pkill -f` with a pattern naming the 20260927 console release ZIP path. It matched its own shell (exit 144) and killed my own inspection task. I cannot prove it matched no process from another session, though any such process would have had that exact ZIP path on its command line.
- Every probe set `sys.dont_write_bytecode` or `PYTHONDONTWRITEBYTECODE=1` before any import. One `.pyc` of a reviewed module appeared during the session: `tools/__pycache__/scan_release_zip.cpython-312.pyc` at 13:36:15. Other writers were active in the same minutes; for example, `kpharness_capture_diagnostic_test` and `playback` `.pyc` files appeared at 13:50 and 13:43, and I ran neither. So the file's origin is unattributed. I left it alone, because deleting it would be a worktree write.

Order: I read the source and ran every probe before reading the writer's fix-round text. Every claim below rests on this reviewer's own probe output or a file:line.

## Prior findings: rerun of the prior probes

The prior probes were copied and fixed so they finish:
- Cleanup now handles links and never raises.
- Each case catches its own refusal.
- `race.py` no longer dies on the refusal it now meets.

Output: `adversarial.out`, `race.out`.

| Prior finding | Probe | Round-1 result | Round-2 result | Verdict |
|---|---|---|---|---|
| I-1 symlinked parent (fixed file) | `parent_symlink_fixed` | BUILT, outside doc shipped | REFUSED `source contains a symlink … docs/user` | holds |
| I-1 symlinked parent (walked folder) | `parent_symlink_walked` | BUILT | REFUSED `… scripts/examples` | holds |
| I-2 nested private folders | `nested_private` | BUILT, 3 leaked | BUILT, `leaked entries=[]`, receipt names `[]` | holds for the listed names (see R-2) |
| I-3 PNG bytes under `.lua` | `binary_lua` | BUILT | REFUSED `magic: png; not UTF-8; NUL byte` | holds |
| I-3 UTF-16 text | `utf16_lua` | BUILT | REFUSED `not UTF-8; NUL byte` | holds |
| I-3 private markers | `markers` | BUILT | REFUSED `m.lua:1` | holds (case gap: R-1) |
| I-4 edit reverted in the window | `race.py prior_edit_reverted_after_staging` | BUILT, unbound bytes shipped | REFUSED `provenance mismatch: …10_rancor.lua` | holds |
| M-1 hard link | `hardlink` | BUILT | REFUSED `source is a hard link (2 names)` | holds |
| M-2 backslash name | `backslash_name` | BUILT | REFUSED `unsafe name in source (backslash in name)` | holds |
| leaf symlink | `symlink_leaf` | REFUSED | REFUSED | holds |
| `/Users/` in README | `users_in_readme` | REFUSED | REFUSED | holds |
| retail/media suffix case variants | `case_variants` | excluded | excluded | holds |
| M-3 host check, `ffmpeg -> /usr/bin/env` (`hc/`) | `creative_host_check.py --path hc/a` | `status: ok` | container and host: `ffmpeg status not_the_tool, blocking True`; `ffprobe` shell wrapper gives `wrapper, blocking True`; `ok False` | holds |
| write-once output (`twice/`) | `twice.py` | refused | `second build refused: output folder already exists`; `out unchanged: True` (28 files); a dangling-symlink `--out` is refused and its target is not created | holds |

M-4 to M-9 were checked only through the writer's tests (`commit_inputs` 12, `export_verify` 17, host check 13, all OK in both places) and by reading the code. I did not probe them independently this round.

P0 spec note (M-3 fix). Plan §5 P0 (`fanout-creative-packaging-plan.md:192-195`) says the tool "Reads only", runs `command -v`, `realpath` and an ELF magic check, and "never launches a tool that opens a display". The fix now runs `[resolved, '-version']` for ffmpeg and ffprobe (`creative_host_check.py:60-66`), which departs from "Reads only". The hard rule still holds: `-version` opens no display. The writer declared the change: the `--help` text says "Only ffmpeg -version and ffprobe -version are run", the JSON has `scope: "file checks plus ffmpeg -version and ffprobe -version; no display was opened"`, and `test_never_launches_a_process` was replaced on purpose. Minor, declared. See R-7 for one side effect.

## New evasions tried

### Symlink swap during the build (`race.py`, `race_brief.py`)

A thread swaps a source folder between the real folder and a symlink to an outside copy. The outside copy holds either secret bytes or byte-identical files plus one outside-only file. The outside-only file is also bound in the overlay, so provenance alone cannot stop it.

| Swapped folder | Builds | BUILT clean | BUILT with outside bytes | Refusals seen |
|---|---|---|---|---|
| `scripts/examples` (50/50 duty) | 25 | 0 | **0** | symlink ×25 |
| same, identical bytes + outside-only file | 25 | 0 | **0** | symlink ×21, does-not-resolve ×4 |
| `scripts/examples` (brief swap) | 40 | 5 | **0** | symlink ×34, does-not-resolve ×1 |
| `scripts/examples/cursed` (brief) | 40 | 9 | **0** | symlink, does-not-resolve, source-changed |
| `docs/user` (brief) | 40 | 7 | **0** | required-file-missing ×19, symlink, open-without-follow, source-changed, does-not-resolve |
| `scripts/harness/kpharness` (brief) | 40 | 0 | **0** | `SyntaxError` ×28 (see R-5), symlink, replaced-while-reading, source-changed |
| `cursed`, identical + outside-only file (brief) | 40 | 4 | **0** | symlink, does-not-resolve, source-changed, `FileNotFoundError` ×1 |

Other race shapes (`race.out`):
- Edit after staging, left in place: REFUSED `source changed during the build; nothing was written`.
- Edit after staging, reverted before the final re-read: BUILT, and `shipped==overlay: True`. The bytes that ship are the bound ones.
- File replaced with a new inode between `open` and the post-read check: REFUSED, but with a misleading message (R-4).

Verdict on I-4 and symlink swaps: **holds**. There were 0 leaks across 250 swap builds. Every build that shipped had only bound, in-tree bytes.

### Case-variant private names (`adversarial.out`)

- `case_private_nested_examples` plants `.SuperPowers`, `TMP`, `Adjudication`, `SAVES`, `KP-LIVE-x` and `Research` under `scripts/examples/cursed/`. The files do not ship, because the folder must be flat. But the shipped `packaging-receipt.json` names all six folders (`receipt names=[b'SuperPowers', b'TMP', b'Adjudication', b'SAVES', b'KP-LIVE', b'Research']`). See R-2.
- `case_private_in_closure` and `lower_private_in_closure`: REFUSED `required Gamescope harness module is missing or linked`. The closure resolver does not follow subpackages, so no closure file sits in a subfolder.
- `case_markers`: BUILT with `Brunner56`, `KP-LIVE`, `c:\users` (another person's name), `/Volumes/` and `/media/bob`. See R-1.

Wine-shaped paths with the builder's own user name (`wine_markers.out`, name redacted to `<user>`):

| Text | Result |
|---|---|
| `c:\users\<user>\x` | REFUSED |
| `drive_c/users/<user>/x` | REFUSED |
| `C:\USERS\<user>` | REFUSED |
| `Z:\home\<user>\x` | REFUSED |
| `/media/<user>/disk` | REFUSED |
| `/mnt/c/Users/<user>` | REFUSED |
| `prefix_<user>_suffix` | BUILT (underscore is a word character) |
| `<USER>` all caps | BUILT |
| `<User>` capitalized | BUILT |
| `drive_c/users/steamuser/AppData` | BUILT (a generic Wine name, not private) |

Every path shape that carries the builder's name is refused. Only bare word variants get through. See R-1.

### UTF-8 BOM, overlong sequences and other encodings

| Probe | Result |
|---|---|
| BOM, then `/home/secretuser` | REFUSED by marker |
| BOM, then PNG | REFUSED `not UTF-8; NUL byte` |
| Overlong `/` (`C0 AF`) | REFUSED `not UTF-8` |
| CESU surrogate `ED A0 80` | REFUSED `not UTF-8` |
| BOM, then `MZ` ASCII | BUILT: magic is matched at byte 0 and the BOM is not skipped (R-6) |
| `/ho\u200bme/secretuser` (zero-width) | BUILT (informational) |
| `\uff0fhome\uff0fsecretuser` (fullwidth) | BUILT (informational) |

### Polyglots

| Probe | Result |
|---|---|
| ZIP appended after Lua text | REFUSED `not UTF-8; NUL byte` |
| PNG with a leading newline | covered by the UTF-8 rule (PNG is not UTF-8) |
| Pure-ASCII PDF after a Lua comment | BUILT |
| `\nGFF V3.2` (magic not at byte 0) | BUILT |
| Base64 PNG inside a Lua string | BUILT |

The last three are valid UTF-8 text that holds no private marker. Real media and retail formats are binary and fail the strict UTF-8 rule. These three cases are informational only: they need deliberate encoding and are not accidental leaks.

### ZIP entry name normalization

| Probe | Result |
|---|---|
| NFC `café.lua` and NFD `café.lua` side by side | BUILT, two entries that collide on macOS |
| `Twin.lua` and `twin.lua` | BUILT, two entries that collide on Windows and macOS |
| `CON.lua`, `aux.lua`, `a:b.lua`, `q?.lua`, `st*r.lua` | BUILT |
| `trail.lua.`, `sp.lua ` | not selected (the suffix is not `.lua`) |
| `x\u202eaul.txt.lua` (bidi override) | BUILT |
| `..lua`, `...lua` | BUILT (not `..` parts, so this is safe) |

See R-3. The package scope is Linux only (`SCOPE`, `package_creative_harness.py:40-41`).

## Real build from the tree

Script: `build_real.py`. It builds an overlay by hashing all 60 selected files (`prov-real.json`), then runs two builds. Total 633.9 s: the drive's queue was saturated, and the process waited in `blk_mq_get_tag`.

1. **Unpatched build: REFUSED**, `absolute local paths or private names in packaged text: scripts/harness/kpharness/capture_diagnostic.py:54, scripts/harness/kpharness/oracle.py:246`. It names exactly the two dry-run hits and nothing else.
2. **Inspection build.** It suppresses only those two exact `(path, line)` pairs. Every other check stayed live: content, links, hard links, provenance, final re-read and the generated-metadata scan.
   - Result: rc=0, `zip_crc PASS`, `manifest_hashes PASS`, `files_checked 62`.
   - `zip_sha256 569c56600b6d072ec8f2dedf8112c0203922ee3968b085ed8f7132fb3969f63a`, equal to `sha256sum` and to `zip-sha256.txt`.
   - `suppressed only: [(capture_diagnostic.py, 54, '/home/'), (oracle.py, 246, 'run id')]`.

   The final re-read found no change, so no concurrent writer touched these 60 files during the window.

Scan with `tools/scan_release_zip.py` (`scan_real.json`): `ok False`, `entries 63`, `unchanged True`. The only findings are the two suppressed lines, `capture_diagnostic.py line 54: /home/` and `oracle.py line 246: run id`.

Independent scan (`scan_independent.out`). The regex is case-insensitive, covers entry names as well as content, and includes the git and GitHub identities and the workspace names:
- 63 entries, `testzip None`.
- Empty ZIP comment, no entry comments or extra fields, and 0 bytes before the first local header.
- Suffixes: 34 `.py`, 10 `.lua`, 9 `.toml`, 5 `.json`, 4 `.md`, 1 with none.
- No case collisions. The name and content findings list is `[]`: no unsafe or non-NFC or `Cf` name, no non-regular mode, no non-UTF-8, no NUL, no magic with or without a BOM, and no BioWare header.
- Marker hits beyond the two known lines, all benign:
  - `k1_gog_103.json:4059 "by_adjudication": 216` is an integer count.
  - `docs/user/creative-harness.md` uses `~/kp-runs` as the folder it tells users to create.
  - `gamescope_xwayland.py:429` uses "adjudication" as an ordinary word in a comment.
  - `tools/kpdiscover.py:18,282,291-292` holds relative discovery defaults `biodecompwarehouse/kotorxid/db/kotorxid.sqlite` and the env var `KOTORXID_DB`. These are workspace names, not paths or identities. This file is committed and was already in round 1. Informational.
- `brunner56`, `bodencrouch`, `arrenkaetris`, `halomastar`, `MyBook`, `.superpowers`, `.worktrees`, `kp-live`, `kp-release`, `/media/`, `/Volumes/`, `drive_c`: none.

Binding and rehash:
- Manifest rehash: `True`, for 62 files. Only `manifest.json` is outside the manifest.
- `source-provenance.json` overlay: 60 entries, all equal to the pre-build overlay.
- Shipped bytes equal the bound raw bytes for 59 of 60. The one other file is `k1_gog_103.json`, whose sanitization (`reference_image` removed) is recorded in the receipt.
- The receipt's `snapshot_files_sha256 492289a3…a8334` equals the dry run's.
- `extractall`: 63 files, all under `kotorphasor-creative-harness/`. The on-disk `package/` tree is byte-equal to the ZIP entries (`cmp` over every file).

Verdict on the real tree: **no leak**. Only the two known lines hold markers, and the builder refuses on both. So the real tree cannot ship until the owner decides on those two lines.

## Real-tree dry run

Command: `PYTHONDONTWRITEBYTECODE=1 python3 tools/package_creative_harness.py --dry-run`. Result: rc=0 in 5m24s on the cold drive (`dryrun.json`, `dryrun.err`).
- 60 files are selected, and the closure has 32.
- `content_refusals`: `[]`.
- Sanitization: `data/addresses/k1_gog_103.json` loses `reference_image`.
- Exclusions: 63 cache entries, 4 other address tables, `__main__`/`cli`/`pioneer`/`playback`, and the retired `50_chaos_roulette.toml` and `60_rave.toml`.
- `path_scan` has **two** hits:
  - `capture_diagnostic.py:54 /home/`: known from round 1, `DEFAULT_FFPROBE = '/home/linuxbrew/…'`.
  - `oracle.py:246 run id`: the comment `# exact 20260910-095338 failure mode.`, which is a bare timestamp.

  The writer's I-3 block says "the real-tree dry run: no new false positive", and the second pass then names this hit as intended. The two statements agree only if a bare timestamp counts as private. That is the open question below.

A case-insensitive grep over the 60 selected files looked for the shapes the markers miss:
- `c:\users`, `drive_c`, `steamuser`
- `/media/`, `/mnt/`, `/Volumes/`
- `arrenkaetris`, `bodencrouch`, `halomastar`
- `brunner`, `MyBook`, `kp-live`, `.superpowers`, `.worktrees`, `linuxbrew`, `/home/`, run IDs

Output: `files 60 hits 8`. None of the hits is live:
- `k1_gog_103.json:4040` is `reference_image`, which the JSON cleaner removes.
- `app_signatures.toml:55-56` are generic `/mnt/c/GOG Games` and `/mnt/c/Program Files (x86)/LucasArts` install paths.
- The rest are the two known hits.

The gaps in R-1 are latent today.

## Grill-me handshake

The writer's report has **no "Grill me" section** (`grep -n -i grill` on the report: no match). That is a protocol miss. In its place, I attacked the weakest protocol blocks myself.

1. **I-2, second pass: "the receipt does not name private folders."** The claim holds for the literal names, `test_i2_receipt_does_not_name_private_folders` passes, and my `nested_private` probe finds receipt names `[]`. It fails for case variants: the `case_private_nested_examples` receipt names `.SuperPowers`, `TMP`, `Adjudication`, `SAVES`, `KP-LIVE-x` and `Research`. Cause: `private_part` compares exactly (`scan_release_zip.py:110`), and the backstop marker scan is case-sensitive (`:151-152`). Only names leak, with no content. Verdict: holds in part. Minor (R-2).
2. **I-3: "confidence high" on markers.** Every path shape that carries this user's name is refused, including the Wine lowercase `c:\users\…` and `drive_c/users/…` shapes (`wine_markers.out`). The case gaps (all-caps or capitalized name, `KP-LIVE`, `.SUPERPOWERS`) and the underscore boundary let bare words through. None exists in the tree (grep above). Verdict: holds for real path shapes. Minor (R-1).
3. **I-4: "each file read once, provenance binds those bytes."** Holds (`race.out`, `race_brief.out`: 0 leaks in 250 swap builds). The one soft spot is on another path: closure parsing reads module files through a folder symlink before the link check runs (R-5). It fails closed.
4. **I-1: "a symlink in any path part refuses."** Holds (`parent_symlink_*` REFUSED, and every swap build that hit a link refused).

Questions the writer missed:
- Why does an inode swap report "hard link (0 names)"? The `fstat` is taken after the name was unlinked (R-4).
- Why can a `SyntaxError` escape `main`? `main` catches only `ValueError` and `OSError` (`package_creative_harness.py:459`) (R-5).
- Is a bare timestamp a private run ID? This is open (see "Open question").

## Findings

### Critical

None.

### Important

None. No probe shipped private or outside bytes from a plausible accidental shape.

### Minor

**R-1. Privacy markers are case-sensitive, and the user-name boundary treats `_` as part of a word.**
claim: markers catch private names.
referent: `adversarial.out case_markers` BUILT with `KP-LIVE`, `c:\users\bob`, `/Volumes/`, `/media/bob`. `wine_markers.out` BUILT for `prefix_<user>_suffix`, `<USER>` and `<User>`.
checked: `scan_release_zip.py:61-63` (fixed markers, plain `re.escape`, no `re.I`); `:155` (look-around `[A-Za-z0-9_]`).
verdict: does not hold for case or underscore variants. Holds for every real path shape with this user's name.
confidence: high. A real tree hit would raise it to Important; the grep over the 60 files found none.

Also latent: the git and GitHub identities (`arrenkaetris`, `bodencrouch`) and the email local part (`halomastar`) are not builder markers, because only `$USER`, `$LOGNAME` and the `$HOME` basename are. The independent scan finds none of them in the real ZIP.

Fix shape:
- Compile the fixed markers and the user name with `re.IGNORECASE`.
- Use `(?<![A-Za-z0-9])` for the name, so `_` counts as a boundary.
- Add `/Volumes/` and `/media/`.

**R-2. Case-variant private folder names reach the shipped receipt.**
claim: I-2 second pass, "the receipt does not name private folders".
referent: `adversarial.out case_private_nested_examples`: receipt names `SuperPowers, TMP, Adjudication, SAVES, KP-LIVE, Research`.
checked: `scan_release_zip.py:107-112` compares exactly. `package_creative_harness.py:184` withholds only when `private_part` or a marker matches.
verdict: holds for the listed spellings, does not hold for case variants. Names only; the files are excluded.
confidence: high.
Fix shape: compare `part.lower()` against a lowercased set, and use `fnmatch` on the lowercased part. Or withhold every exclusion name under the flat folders.

**R-3. Entry names are not normalized.**
claim: `unsafe_name` refuses unsafe names.
referent: `adversarial.out`: `nfc_nfd_twins`, `case_twins`, `windows_reserved` (`CON.lua`, `a:b.lua`, `q?.lua`, `st*r.lua`) and `bidi_name` (U+202E) all BUILT.
checked: `scan_release_zip.py:91-104` checks only backslash, C0/DEL, absolute and `..`.
verdict: holds for the Linux scope. Portability and deception gaps remain.
confidence: high.
Fix shape: refuse names whose NFC form or casefold collides with another name. Refuse Unicode `Cf` (format) characters. Refuse `<>:"|?*`, trailing dot or space, and Windows device names.

**R-4. The inode-swap refusal names the wrong cause.**
claim: the refusal names why the file was refused.
confidence: high.
referent: `race.out`: `inode_replaced_during_read -> REFUSED … source is a hard link (0 names)`.
checked: `package_creative_harness.py:248-252`. `fstat` sees `st_nlink == 0` because the opened inode was unlinked.
verdict: fails closed, but the message misleads.
Fix shape: when `st_nlink == 0`, say "source was replaced while reading".

**R-5. Closure parsing reads through a symlinked folder, and its `SyntaxError` escapes `main`.**
claim: I-1, "a symlink in any path part refuses", read as "no byte is read through a link".
confidence: high for the ordering. Low impact, because no build completed through a link.
referent: `race_brief.out`: `scripts/harness/kpharness` swap gives `SyntaxError: invalid syntax (export_verify.py, line 1)` ×21 and similar lines.
checked:
- `select_files` calls `runtime_module_paths` (`:149`) before any `refuse_links`, and that call parses module sources.
- `main` catches `(ValueError, OSError)` only (`:459`), so the user sees a traceback and no JSON.

verdict: fails closed (no build), but the error path is wrong.
Fix shape: call `refuse_links(root, HARNESS + '/kpharness')` before computing the closure, and catch `SyntaxError` in `main`.

**R-6. The magic check does not skip a UTF-8 BOM.**
claim: magic bytes refuse whatever the prefix.
referent: `adversarial.out bom_gzip_ascii` BUILT (`\xef\xbb\xbfMZ …`).
checked: `scan_release_zip.py:115-124` uses `head.startswith`.
verdict: does not hold at byte 3. Minor, because every binary format with a BOM prefix still fails UTF-8 (`bom_then_png` REFUSED).
confidence: high.
Fix shape: strip a leading BOM before the magic test.

**R-7. The host check captures `-version` output with no size cap.**
claim: M-3, a small bounded `-version` call.
referent: `hc/flood.c` is an ELF that ignores its arguments and writes 64 KiB blocks forever, linked as `ffmpeg` in `hc/y`. Under `ulimit -v 3000000`, `/usr/bin/time -v` gives `Maximum resident set size (kbytes): 2108628` and `Elapsed 0:13.23`, and the result is `ffmpeg status not_the_tool, blocking True`.
checked: `creative_host_check.py:63-65`, `subprocess.run(..., capture_output=True, timeout=10)`.
verdict: fails closed, but memory grows with the tool's output rate for up to 10 s.
confidence: high.
Fix shape: use `Popen` and read at most 64 KiB from stdout, then kill the process.

(`yes -version` is no test here: GNU `yes` rejects `-v` and exits at once. `hc/yes.err` shows 0.22 s and 13 MB.)

### Informational (not findings)

Zero-width and fullwidth-slash paths, base64 media, pure-ASCII PDF text and `GFF V3.2` after a newline all build. These take deliberate obfuscation, and a text-only rule cannot catch them. Treating them as findings would invent flaws.

## `scan_release_zip.py`: are the markers too broad or too narrow?

Probes: `scanner_probes.py`, with output in `scanner_probes.out` and crafted ZIPs in `scanner/`. Both real console release ZIPs were also scanned read-only, and `unchanged: True` was reported for each.

Usage: only `package_creative_harness.py` (imports) and its tests reference it (grep over `*.py *.md *.sh *.toml`). No release gate calls it yet. The builder scans entry names itself (`package_creative_harness.py:359`). So the narrow spots below matter if this scanner becomes a release gate for ZIPs from other builders.

**Too narrow. Each crafted ZIP scanned `ok`:**
- Markers in entry names are not scanned: `pkg/<user>-notes.md`, `pkg/20260927-102706-0523fa70/report.md`, `pkg/home/<user>/x.md`, `pkg/kp-live-20260922.md` all scan ok. `_scan_blob` scans data only (`:185-195`), and `private_part` skips the last part (`:109`).
- The ZIP comment, entry comment, extra field and prepended bytes are not scanned. Each carried `/home/<user>/…` and scanned ok.
- Private folders and markers are case-sensitive: `.SuperPowers/`, `TMP/`, `Adjudication/`, `c:\users\bob`, `Brunner56` and `KP-LIVE` scan ok.
- A NUL in a name: Python truncates it at the NUL, so the scanner sees `pkg/a.lua`.
- Names are not normalized: bidi, NFC/NFD twins, case twins and Windows-reserved names scan ok.
- A BOM before `MZ`, and an ASCII PDF after a comment, scan ok.
- `--allow` on a compressed type the scanner does not unpack hides everything inside. A `.tar.xz` holding `/home/<user>/x` is `ok` under `--allow '*.xz'`. Only `.tar.gz`, `.tgz`, `.tar` and `.zip` are opened (`:70`).
- UTF-16LE strings inside an allowed DLL (`C:\Users\<user>\x.pdb` in wide form) are not found. Only the `pe/dos` magic fires.
- An encrypted entry raises an uncaught `RuntimeError`. The CLI exits rc=1 with a traceback and no JSON (`main` catches `OSError` and `BadZipFile` only, `:285`). It fails closed.

**Too broad. Each flagged a plausible public text:**
- `RUN_ID` (`:65`) matches any `YYYYMMDD-HHMMSS` token. `CHANGELOG.md "Built 20260927-102706 on CI"` is flagged, and so is today's `oracle.py:246` comment.
- The two- and three-byte magics fire on plain text at byte 0: `MZ = 1` in a `.lua` gives `pe/dos`, and `KB2267602 …` in a `.md` gives `bink2`. `BIK`, `ID3` and `BZh` behave the same way.
- `research`, `runs` and `tmp` on any folder part (`:36-37`) are broader than spec §2, which names only `data/research/` and root `tmp/`. This repo tracks a public `docs/research/native-animation-sites.md`, and `pkg/docs/research/…` is flagged.
- `linuxbrew` and `MyBook` fire as plain words.
- Upstream third-party doc text is flagged (`luajit/doc/install.html` `/home/myself/lj2`).

Balance: it is tight enough for this builder's allowlist, which selects 60 known files. The breadth costs friction only, because every false positive fails closed. As a standalone release gate it is too narrow on names and metadata, and too case-sensitive.

**Real console release ZIPs (read-only, out of this round's scope).** Both scans return `ok: False` and `unchanged: True`.
- `/home/brunner56/kp-release-20260922/kotorphasor-k1-gog-console-preview.zip`: 17 entries.
- `/home/brunner56/kp-release-20260927/kotorphasor-k1-k2-gog-console-preview.zip`: 18 entries.

The true positives match the writer's report:
- `kphasor.dll` holds absolute build paths under the home folder, at 9 marker lines.
- `packaging-receipt.json:4-8` names `.superpowers/...` files.
- `source.tar.gz!source/data/research/phasor_structs.json` ships.
- `source.tar.gz!source/data/events.draft.toml:5` has `/home/`.
- 0922 only: `live-acceptance.json:10` has `/home/`.

The false positives, or upstream text:
- `.gitignore:40 .worktrees`
- `luajit install.html`
- the run-ID comments

This is a standing hazard for any published copy of those ZIPs. It is not part of the creative packager.

## Commands and outputs

Tests. Container is Python 3.12.3; host is `/home/brunner56/.local/bin/host-cmd sh -c 'cd <worktree> && PYTHONDONTWRITEBYTECODE=1 python3 tools/<t>.py'`, Python 3.14.7. Outputs are in `tests/`.

| Test file | Container | Host |
|---|---|---|
| `tools/package_creative_harness_test.py` | `Ran 35 tests in 85.246s OK` | `Ran 35 tests in 88.339s OK` |
| `tools/creative_host_check_test.py` | `Ran 13 tests in 0.269s OK` | `Ran 13 tests in 0.159s OK` |
| `tools/kpharness_commit_inputs_test.py` | `Ran 12 tests in 0.193s OK` | `Ran 12 tests in 0.021s OK` |
| `tools/kpharness_export_verify_test.py` | `Ran 17 tests in 0.610s OK` | `Ran 17 tests in 0.246s OK` |
| **Total** | **77 OK, rc=0** | **77 OK, rc=0** |

The writer's "77/77" holds in both places.

Probes (all in `review-probes-packaging-r2/`):
- `adversarial.py` → `adversarial.out`, `adversarial.json`: 32 cases in 31 s.
- `race.py` → `race.out`: 6 race shapes.
- `race_brief.py` → `race_brief.out`: 200 brief-swap builds.
- `wine_markers.py` → `wine_markers.out`: user name redacted.
- `twice.py` → `twice.out`.
- `hc/` host-check targets, run in the container and on the host (`host-cmd`). Also `hc/flood.c`, `hc/flood.err` and `hc/yes.err`.
- `scanner_probes.py` → `scanner_probes.out`, `scanner/`.
- `dryrun.json`, `dryrun.err`: the real-tree dry run.
- `build_real.py` → `build_real.out`, `out-real/`, `prov-real.json`: the real build.

## Open question

Is a bare run timestamp such as `20260910-095338` in `oracle.py:246` private? The builder treats it as private, so the real build refuses until the line changes. A single owner decision settles it: either edit that comment, or scope `RUN_ID` to the `runs/<id>` and `<id>-<8 hex>` shapes.

## Verdict

The four Important findings from round 1 are fixed.
- I-1 and M-1: parent symlinks and hard links refuse. There were 0 leaks in 250 symlink-swap builds.
- I-2: nested private names are denied at any depth, and the listed names are withheld from the receipt.
- I-3: non-UTF-8, NUL and magic bytes refuse. Every real path shape with the builder's name refuses.
- I-4: provenance binds the staged bytes. The reverted-edit race now refuses, and the shipped bytes equal the bound bytes.

The M items I checked hold: M-1 and M-2 by probe, and M-3 to M-9 through the 77 passing tests. The real tree builds a clean ZIP apart from the two known lines, and the builder refuses on both.

What remains is Minor:
- R-1: markers are case-sensitive, and `_` does not count as a name boundary.
- R-2: case-variant private folder names reach the receipt, as names only.
- R-3: entry names are not normalized for other operating systems.
- R-4: one refusal message names the wrong cause.
- R-5: a `SyntaxError` escapes `main`, and closure parsing reads through a folder symlink before the link check.
- R-6: the magic check does not skip a BOM.
- R-7: the host check captures `-version` output with no size cap. P0 now runs `-version`, a declared departure from the plan's "Reads only".

`scan_release_zip.py` is too narrow as a standalone gate: it skips entry names, comments and extra fields, and it matches case-sensitively. It is too broad on bare timestamps, short magic prefixes and `research`, `runs` and `tmp` on any folder. None of that changes the builder's boundary today.

The writer's report has no Grill-me section, which is a protocol miss.

Unsettled question: is `oracle.py:246`'s bare timestamp private? An owner decision settles it: edit the comment, or narrow `RUN_ID`. Until then, the real build refuses, which is correct fail-closed behavior.

Packaging re-review verdict: PASS
