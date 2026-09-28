# Publication-boundary hardening: independent review (spec, then adversarial)

Date: 2026-09-27. Reviewer: a separate agent, round 3.
Worktree: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation` (read only).
Scratch: `/home/brunner56/kp-live-20260922/review-probes-scanner/`.

Scope held:
- No worktree file was edited, and no git write was made.
- Nothing under `kp-release-*` was modified, rebuilt or published. Before and after my scans, both ZIPs had the same size, mtime and sha256 (`zipstat-*.txt`, `zipsha-*.txt`, `diff` empty, `UNCHANGED`).
- No game was started, and the live-game lock was not touched.
- Every test and probe ran with `PYTHONDONTWRITEBYTECODE=1`.

Order: I read the three changed tools and wrote down my own attack list before I read the triage, the prior re-review, the writer's section or the patch.

## 1. Spec check: the orchestrator rulings

| Ruling | Where | Check | Verdict |
|---|---|---|---|
| Narrow run IDs to `runs/<id>` and `<id>-<8hex>` | `scan_release_zip.py:120-121` | `probes.out`: `runs/20260915-071620` and `…-0523FA70` are flagged. The bare `20260910-095338` is ok. | holds |
| Block only `data/research/`, so `docs/research` stays public, and `tmp/` and `runs/` count only at the repository root | `:60-65`, `:240-254` | `data_research` and `root_tmp` are flagged. `docs/research`, `lib/tmp` and `lib/runs` are ok. The 20260927 ZIP flags only `phasor_structs.json`. | holds (see S-5 for a root-detection gap) |
| Hold back `codecaves.toml` and `events.draft.toml` | `:67`, `:257-260`; packager `deny_reason:101` | Both show as `excluded file` in both ZIPs. The rule ignores case (`Data/Events.Draft.toml` is flagged) and applies inside a nested tar. `--allow '*'` does not hide it. | holds |
| Drop `-DNDEBUG` from the patch | `release-builder-proposed.patch` | `grep -n '^+.*-DNDEBUG'` gives **5** added lines. The patch still carries it on all five compile lines. | **does not hold yet** (P-1) |
| Accept `.gitignore:40`, `phasor_structs.json` and 3 LuaJIT doc items | patch `ACCEPTED` | All 5 keys match current scanner findings exactly: `accepted present in current findings: 5 of 5`. | holds |

## 2. Reruns

Tests (outputs in `tests/`):

| Test file | Container (Py 3.12.3) | Host via `host-cmd` |
|---|---|---|
| `package_creative_harness_test.py` | `Ran 58 tests in 114.319s OK` | `Ran 58 tests in 123.822s OK` |
| `creative_host_check_test.py` | `Ran 15 tests in 0.094s OK` | `Ran 15 tests in 0.105s OK` |
| `kpharness_commit_inputs_test.py` | `Ran 12 tests in 0.022s OK` | `Ran 12 tests in 0.192s OK` |
| `kpharness_export_verify_test.py` | `Ran 17 tests in 8.187s OK` | `Ran 17 tests in 0.124s OK` |
| **Total** | **102 OK, all rc=0** | **102 OK, all rc=0** |

Scans of the release ZIPs, read-only, with `--allow '*.dll'`. Outputs are in `scan-{container,host}-*.json`.

| ZIP | sha256 | entries | findings (container / host) | tar owner | markers | unchanged |
|---|---|---|---|---|---|---|
| 20260927 | `0388d080…67c9` | 18 | **632 / 632** | 606 | 21 | true |
| 20260922 | `de14c126…7131` | 17 | **633 / 633** | 606 | 21 | true |

- All 606 owner findings read the same: `uname is the build user; gname is the build user; uid 1000 gid 1000 (nonzero)`.
- `finding_counts` in 0927: tar owner 606, marker 19, excluded file 2, magic 2, private folder 1, not UTF-8 1, NUL byte 1. In 0922, marker is 20.
- Expected, allowed by the glob: the `pe/dos` magic of both DLLs.

The writer's counts hold exactly.

Prior probes from round 2 (copied to `prior/`, paths repointed, outputs in `prior/*.out`):
- `scanner_probes.py`:
  - Now flagged: every former "too narrow" case except two. This covers entry-name markers, comments, extra fields, prefix bytes, case variants, bidi names, NFC and case twins, Windows names, encrypted entries (JSON, rc=1) and `.tar.xz` under `--allow '*.xz'`.
  - Every former "too broad" case except `linuxbrew` is now ok. That covers the bare stamp, `MZ = 1`, `KB2267602`, `docs/research` and `lib/runs`.
  - Still ok: `nul_in_name` and `bom_magic`. `nul_in_name` is S-4. `bom_magic` is text, not a PE, so it is correct.
- `adversarial.py`, 32 cases, `cleanup done: True`:
  - All round-2 refusals still refuse.
  - The R-3 name cases now refuse: twins, `CON`, `a:b`, `q?`, `st*r` and bidi.
  - `case_markers` now refuses.
  - Case-variant `.SuperPowers`, `KP-LIVE-x`, `Adjudication` and `SAVES` are withheld from the receipt. `TMP`, `Research` and nested `/tmp/` are named in the receipt, which ruling (2) intends.
  - Deliberate obfuscations still build. These are zero-width, fullwidth, base64, ASCII PDF and `GFF` after a newline, and they are informational, as in round 2.
- `wine_markers.py`: all 10 cases refuse, including the builder's name in `prefix_<user>_suffix`, in all caps and capitalized.
- `twice.py`: a second build is refused, and a dangling-symlink `--out` is refused with no target created.
- `race_brief.py`: rerun only for the kpharness swap, through `main` (`race_r5.py`). See R-5 below. The other swap folders were covered by `race.py`.
- `race.py`: the reverted edit refuses on provenance mismatch. The left-in-place edit refuses on "source changed". An inode swap now says "replaced while reading" (R-4 fixed). 25 + 25 symlink-swap builds gave `leaks=[]`.
- Host check `hc/` (container): `a` gives ffmpeg `not_the_tool` and ffprobe `wrapper`, both blocking. The flood ELF gives `not_the_tool`. Peak RSS **13,496 KB** in 5.05 s wall time, against 2,108,628 KB in round 2. R-7 is fixed.

Round-2 minors R-1 to R-7:

| Item | Referent this round | Verdict |
|---|---|---|
| R-1: case, `_` boundary | `prior/wine_markers.out`: 10 of 10 refuse. `probes.out`: `identity_underscore`, `identity_git_name` (`ArrenKaetris`) and `identity_email_full` are flagged. | holds |
| R-2: case-variant receipt names | `prior/adversarial.out`: `case_private_nested_examples` names only `TMP` and `Research` (nested, not private under ruling 2) | holds |
| R-3: names | `prior/adversarial.out`: twins, device names, reserved characters and bidi all REFUSED | holds (S-7 covers the leftovers) |
| R-4: refusal message | `prior/race.out`: `inode_replaced_during_read -> … replaced while reading` | holds |
| R-5: closure parse through a link, `SyntaxError` | `prior/race_r5.out`: 40 kpharness-swap builds through `B.main`, all 40 a JSON error: 28 symlink, 8 `harness module does not parse`, 2 missing or linked, 2 does-not-resolve. 0 escaped `main`, 0 built, `leaks []`. | holds for the error path. The parse can still read swapped bytes between the link walk and the parse (8 of 40), but it fails closed. Informational. |
| R-6: BOM before magic | `probes.out`: `bom_elf_bin` and `bom_png_in_lua` are flagged | holds |
| R-7: output cap | `hc_probe.*.out`, `prior/hc/flood-r3.err` (13,496 KB peak RSS) | holds |

## 3. Adversarial probes (new this round)

Scripts: `probes.py` → `probes.out`, `probes2.py`, `gate_probe.py`, `hc_probe.py`, `rootdepth.out` and `identity_grep.out`.

### Tar owner checks: hold
- Flagged:
  - `uname` = the user
  - `uname` = the user in all caps
  - `gname` = the git email local part
  - numeric-only `uid=gid=1000`
  - base-256 `uid=2**40`
  - any other account name (`bob`)
  - a pax per-member `uname` or `uid` override
  - pax `SCHILY.xattr` or `comment` markers
  - a **global** pax header `comment` or `uname` (tarfile folds it into each member's `pax_headers`)
  - a GNU long name with `kp-live`
  - a ustar `prefix` field that carries the name
  - a symlink with a GNU longlink target (flagged as a link)
- Also flagged:
  - a tar nested in a `.tar.gz`, and the same bytes under a plain `.gz` suffix
  - a tar in `.tar.xz`
  - a 4-deep nest, reported as `unscanned archive: nested too deep`
- Clean controls: `root/root 0/0` and blank `0/0` are ok.

### ZIP metadata: holds for what it claims, with gaps in bytes that no entry covers (S-3, S-4, S-6)

### `--allow` cannot hide unscanned content: holds
Under `--allow '*'`, each of these is still a finding:
- an encrypted entry
- a `.7z`
- a `.zst` suffix
- zstd magic under a `.dll` name
- a truncated `.gz`
- a ZIP named `.dll` that holds a `/home/` marker
- a held-back `codecaves.toml`

Only `magic` findings are ever moved to `expected` (`scan_bytes:606`). By design, `--allow '*'` also hides the magic finding of a real PNG (`allow_star_hides_png_media (by design) ok`), so the operator owns the globs.

### Case-insensitive markers vs false positives: the writer's call holds
- `/HOME/<USER>/x` is flagged through the identity marker.
- `/HOME/bob/x` is ok. A Linux path in upper case names no home folder, and it carries no builder identity.
- `PageDown/Home/End` is ok, which is the reason Linux prefixes are case-sensitive.
- `/users/bob` is flagged, since macOS paths ignore case.

My verdict is **holds**: keep Linux prefixes case-sensitive. The cost runs the other way. `/Users/` ignores case, so it also flags `drive_c/users/steamuser` (`prior/wine_markers.out` "steamuser: REFUSED", with the `/Users/` marker per `path_scan`) and any `/users/` in a URL. That fails closed, and it is informational only.

### BOM handling: holds
- A BOM before ELF is flagged `elf`.
- A BOM before PNG in `.lua` is flagged `png` and `not UTF-8`.
- A double BOM before ELF is ok. That file is no longer an executable, so I make no finding.

### Packager self-scan: holds (`gate_probe.out`)
1. The sha256 the gate saw equals the sha256 of the ZIP on disk. The `out/` folder did not exist when the gate ran. `allow=()`, and 21 markers were passed.
2. I disabled the builder's own `path_scan` and planted `/home/<user>/x` in a shipped `.lua`. The build was REFUSED with `release scan of the finished ZIP found problems; nothing was written … marker: line 1: /home/`, and `out2` does not exist. The gate works on the real bytes on its own.
3. A gate that raises leaves no `out3`.

### Host-check output cap: holds (`hc_probe.{container,host}.out`, same in both places)

| Case | rc | bytes read | seconds |
|---|---|---|---|
| flood | -9 | 65,536 | 0.01 |
| drip, never exits | -9 | 10 | 10.01 |
| closes stdout, then sleeps | -9 | 0 | 11.00 |
| background child holds the pipe | -9 | 20 | 10.02 |
| exactly 64 KiB, then exit | 0 | 65,536 | 0.01 |

Peak RSS was about 13 MB. Informational: the orphaned child in the background-child case is not killed, because the kill reaches only the direct child, not its process group. It fails closed.

## 4. Findings

No Critical findings. No Important findings on the scanner or the packager. Two items concern the unapplied patch.

**P-1. The patch still adds `-DNDEBUG`, against the ruling.**
- claim: "-DNDEBUG to be DROPPED from the patch (keep asserts)"
- referent: `grep -n '^+.*-DNDEBUG' release-builder-proposed.patch | wc -l` → `5`. The lines are in CMakeLists.txt, hooks.cmake, structs.cmake, runtime.cmake and proxy.cmake.
- checked: the patch file.
- verdict: does not hold yet.
- confidence: high. It changes once the five `-DNDEBUG` tokens are removed.
- Fix: delete the token on the five `+` lines. The prefix maps alone remove the `__FILE__` paths. That last point is unverified, because no rebuild was run; see the open question.

**P-2. The patch's privacy gate is an `assert`, and `python -O` or `PYTHONOPTIMIZE` removes it.**
- referent: `python3 -O -c "assert False,'gate'; print(...)"` printed `assert-based gate skipped, execution continued`. Patch lines: `assert not blocking, …`, then `os.rename(held, z)`.
- verdict: does not hold under `-O`. Normal `python3 package.py` is fine.
- confidence: high.
- Fix: `if blocking: raise SystemExit(…)`. Do the same for the program-magic assert and the `zip_sha == gate` assert.

**S-1 (Minor). The UTF-16 scan runs only when the entry is not valid UTF-8.**
- claim (docstring, `:28-29`): markers "in UTF-16 strings inside binaries".
- referent: `probes2.out`:
  - a 64-byte DOS header plus the UTF-16LE string `C:\Users\<user>\x.pdb`, under `--allow '*.dll'`, gives `ok [] expected=['magic']`
  - the same bytes plus one `0xff` byte give `FLAGGED marker: utf-16 C:\Users`
  - `probes.out`: `utf16le_nobom_log_marker`, `utf16le_nobom_dat_identity` and `utf16be_nobom_dat_marker` are all ok (NOT FLAGGED)
- checked: `_scan_blob:462-465` calls `wide_scan` only after `data.decode('utf-8')` fails. ASCII in UTF-16 with NUL bytes is valid UTF-8.
- verdict: does not hold for binaries that happen to be valid UTF-8. That covers BOM-less UTF-16 logs or configs under a non-text suffix. The real DLLs are covered: `dll_utf8.out` shows `kphasor.dll` and `binkw32.dll` in both ZIPs hit `invalid UTF-8 at byte 2 -> wide scan runs`.
- confidence: high.
- Fix: call `wide_scan` whenever `b'\x00' in data`. `wide_scan` already guards on this.

**S-2 (Minor, latent). Git identities come from the winning scope only, and the repo owner is never read.**
- referent: `git config --get-all user.email` lists two values: the global `<id:th3w1zard1>@users.noreply.github.com` and the repo-local `<id:halomastar>@gmail.com`. `--get` returns only the repo-local one.
- A ZIP whose text is `by th3w1zard1 and bodencrouch` scans `ok= True []`.
- With `PATH=/nonexistent`, git identities drop to 0 and markers to 18, with no warning.
- checked: `_git_config:157-164` uses `--get`. `github.user` is unset, and `bodencrouch` is configured nowhere.
- `identity_grep.out`: neither ZIP holds any of the four identities, so this is latent.
- verdict: does not hold for every identity.
- confidence: high.
- Fix:
  - Add an explicit identity list for the repo owner and the GitHub login, for example a `KP_PRIVATE_IDENTITIES` env var. Report `identities: N`, and warn when git is unavailable.
  - Caution: a blind `--get-all` would also pick up the global `user.name` `Copilot`. That name passes `_identity_ok`, so every doc that mentions GitHub Copilot would be flagged. Take the email local parts from `--get-all`, and add names only through the explicit list or a stoplist. Neither ZIP has a whole-word `copilot` today (`dll_utf8.out`: `copilot whole-word hits: {}`).

**S-3 (Minor, crafted only). Bytes that no entry covers are not scanned.**
- referent: `probes.out`. Each of these carried `/home/<user>/…` and scanned **ok**:
  - `zip_gap_before_central_dir`
  - `zip_trailing_after_eocd`
  - `zip_deflate_slack_bytes`
  - `tar_member_after_EOF_zeros`
  - `tar_member_after_invalid_header`
- GNU tar on the last file: `tar: Skipping to next header`, then `b.lua` is extracted (rc=2). So a standard tool recovers content the scanner never saw. `tar -i` does the same for the after-EOF case.
- checked:
  - `_scan_zip` scans only the ZIP comment, the prefix bytes and each entry.
  - Python `tarfile` stops silently at an invalid header after offset 0.
- verdict: does not hold for crafted archives. No builder here writes such bytes.
- Fix:
  - flag ZIP bytes not covered by local header + data + central directory + EOCD, or run `path_scan` over the raw ZIP
  - flag nonzero bytes after the tar end, using `archive.offset` against the stream length

**S-4 (Minor). A NUL in a ZIP name hides the rest of the name.**
- referent: a raw-crafted name `p/a.lua\x00/home/secretuser/x` gives `zipfile filename 'p/a.lua'` and `orig_filename` with the full name. The scan is `ok True []`. `unzip -l` shows `p/a.lua`.
- checked: `_scan_zip:564-565` uses `info.filename`, so the "control character in name" rule never sees the NUL.
- verdict: does not hold for the tail after the NUL.
- Fix: run `_scan_name` on `info.orig_filename`.

**S-5 (Minor). A single top folder named `data`, `tmp` or `runs` is taken as a wrapper folder.**
- referent: `rootdepth.out`. Each of these is `ok (NOT FLAGGED)`:
  - `['data/codecaves.toml']`
  - `['data/codecaves.toml','data/events.draft.toml','data/hooksites.toml']`
  - `['tmp/a.lua','tmp/b.lua']`
  - `['runs/x/report.md']`
- checked: `_root_depth:354-359` returns 1 whenever every name shares one top folder.
- verdict: does not hold for ZIPs made of just `data/`, `tmp/` or `runs/`.
- Fix: check the held-back and root-private rules at depth 0 and depth 1.

**S-6 (Minor). Unix owners in other ZIP extra fields are not read.**
- referent: `zip_extra_5855_uid` and `zip_extra_000d_pkware_unix` (uid/gid 1000) are ok. Only `0x7875` is flagged.
- Fix: parse `0x5855` and `0x000d` too.

**S-7 (Minor, portability). Some colliding names are not caught.**
- These pass:
  - exact duplicate names (`zip_exact_duplicate_names ok`)
  - a file and an implicit folder of the same name (`p/x` + `p/x/y.lua`, and `p/A` + `p/a/x.lua`)
- `name_collisions` requires `len(set(group)) > 1` and never compares folder parts against file names.
- Both duplicate bodies are scanned, so no content is hidden.

Informational, not findings:
- `D:\Users\…` and `runs\<stamp>` (backslash) are not markers.
- A `RuntimeError` from the gate escapes `main` as a traceback, not JSON. It fails closed.
- The host-check orphan child is noted above.

## 5. Grill me: attacking the writer's answers, weakest first

1. **"Is `-DNDEBUG` safe to ship?"** Superseded by the ruling, and the patch has not caught up (P-1). Narrower question: do the prefix maps alone clear the DLL? That is unverified here, because a rebuild is out of scope.
2. **"Does ruling (2) weaken the packager?"** That holds. `adversarial.out nested_private` gives `leaked entries=[]`, and the receipt names `/tmp/` as the ruling intends. `test_i2_…` passes in both places.
3. **"Why are Linux prefixes case-sensitive?"** That holds. See `upper_HOME_build_user FLAGGED` (identity), `upper_HOME_other_user ok` and `imgui … ok`.
4. **"Do reduced MZ/KB false positives let a binary through the packager?"** That holds for the packager: strict UTF-8 plus the NUL rule. `adversarial.out bom_gzip_ascii` builds, but it holds only ASCII. A narrower issue the writer missed sits in the scanner: S-1, where a UTF-8-valid binary skips the UTF-16 scan.
5. **"Is one finding per tar member the right granularity?"** That holds. Each owner detail is identical across all 606 findings, and `finding_counts` summarises them.

Questions the writer missed: S-1 to S-7, P-2, and "does the report say which identities were loaded?" (S-2).

## 6. Handoff: the one question I could not settle

Does the patched CMake build, without `-DNDEBUG`, give a `kphasor.dll` with zero `/home/` strings? One check settles it. In a fresh `/tmp` copy of the 0927 folder:
1. apply the patch with the five `-DNDEBUG` tokens removed
2. run the build
3. run `tools/scan_release_zip.py --allow '*.dll'` on the result

Expect `kphasor.dll` marker findings = 0.

## 7. Claim blocks

claim: "632/633 findings, 606 tar owner, both hosts"
referent: `scan-{container,host}-kp-release-2026092{7,2}.json`
checked: rerun above; sha, size and mtime unchanged
verdict: holds
confidence: high

claim: "102 tests OK in container and host"
referent: `tests/*.out`, `tests/*-rc.txt`
checked: rerun
verdict: holds
confidence: high

claim: "packager scans the exact bytes before any write"
referent: `gate_probe.out` cases 1 to 3
checked: spy plus a disabled earlier check
verdict: holds
confidence: high

claim: "`--allow` never hides unscanned or encrypted content"
referent: `probes.out allow_star_*`
checked: 7 cases
verdict: holds
confidence: high

claim: "host-check reads at most 64 KiB"
referent: `hc_probe.*.out`, `prior/hc/flood-r3.err` (13,496 KB RSS)
checked: 5 edge cases in both places
verdict: holds
confidence: high

claim: "UTF-16 strings inside binaries are scanned"
referent: `probes2.out`
checked: `_scan_blob:462-465`
verdict: does not hold for UTF-8-valid binaries (S-1)
confidence: high

claim: "git identities are read at scan time"
referent: `git config --get-all` output; the `th3w1zard1`/`bodencrouch` ZIP scans ok
checked: `_git_config`
verdict: holds in part (S-2)
confidence: high

claim: "-DNDEBUG dropped from the patch"
referent: the grep count of 5
checked: the patch file
verdict: does not hold yet (P-1)
confidence: high

## Verdict

The hardening does what the rulings and the triage asked:
- tar owners are caught, including through pax (global too), GNU and ustar headers and nested tars
- ZIP metadata is scanned
- `--allow` cannot hide unscanned content
- the packager gate sees the exact bytes before any write
- the host-check cap holds
- all 102 tests pass in both places, and the release counts reproduce exactly (632/633, 606 owners)

Remaining scanner gaps are all Minor: S-1 and S-2 are latent, and S-3 to S-7 need crafted archives or add portability hardening. No gap exposed anything in either real ZIP (`identity_grep.out` is empty, and every other real finding is accounted for).

Two conditions sit on the unapplied patch before anyone applies it:
- P-1: remove the five `-DNDEBUG` tokens.
- P-2: replace the gating `assert`s with explicit exits.

Scanner hardening verdict: PASS
