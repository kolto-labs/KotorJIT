# Creative packaging P0–P4: independent review

Date: 2026-09-27. Reviewer: separate agent. The implementer's report was read early, together with the source. Every finding below rests on this reviewer's own probe output or a file:line, not on that report.
Worktree: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`.
Spec: `/home/brunner56/kp-live-20260922/fanout-creative-packaging-plan.md`.
Report reviewed: `.superpowers/sdd/lua-boundary-validation-plan/creative-packaging-p0-p4-report.md`.
Scratch: `/home/brunner56/kp-live-20260922/review-probes-packaging/` (nothing published).

Scope held. No source file was edited. No game, Wine, Gamescope or capture ran. The lock was not touched: `tmp/harness-locks/` already existed, is empty, and its mtime is 01:41, from before this review. `kpharness/__pycache__` still holds 63 entries. No `.pyc` exists for any new module.

## Stage 1: spec compliance

| Spec item | Result | Referent |
|---|---|---|
| P0 host check: file-only, JSON line, `ok`/`missing`/`wrapper` | holds | host run below; `creative_host_check.py:386-401` |
| P1 builder API and steps 1–8 | mostly holds; gaps I-1, I-3, I-4 | `package_creative_harness.py` |
| P1 "Refuse symlinks in the source tree" | **does not hold** for symlinked parent folders | I-1 |
| Spec §2 "Exclude (deny even if an allowlist path matches)": `data/adjudication/`, `data/research/`, `.superpowers/`, `tmp/` | holds as written (root-relative; `deny_reason:90`, deny-over-allow at `:165-167`). The same names nested deeper are not denied. | I-2 (adversarial, beyond the spec text) |
| P1 absolute-path scan | holds for UTF-8 text; skips non-UTF-8 files | I-3 |
| P1 provenance binding | binds a second read, not the staged bytes | I-4 |
| P1 dry-run finds `capture_diagnostic.py` path hit | holds (line 54 now) | dry run below |
| P1 closure excludes playback/pioneer/cli | holds today | dry-run exclusions |
| P2 guide: honest cells, pending marks, plain copy | holds, with Minor items | M-5..M-7 |
| P3 verifier pinned to schema 1, no self-reference | holds | section "export_verify" |
| P4 commit helper, shared log validation | holds; the docstring claims too much | M-4 |
| New files only | not contradicted. `git status --short` completed, but other writers have left the worktree dirty (for example ` M kpharness/creative.py`, `recording.py`, `session.py`). Git alone cannot attribute edits to this implementer. | — |
| Write-once output | holds | `mkdir(exist_ok=False)` at `:308-311`, ZIP mode `'x'` at `:248`. Probe `twice/`: `second build refused: output folder already exists; choose a new one: out \| out unchanged: True` |

## Stage 2: quality and adversarial

### Publication boundary, real tree

Real dry run (container, 3m25s, cold drive):
`PYTHONDONTWRITEBYTECODE=1 python3 tools/package_creative_harness.py --dry-run` gives rc=0.
- 60 files are selected. The only `path_scan` hit is `scripts/harness/kpharness/capture_diagnostic.py:54 /home/`.
- Sanitization: `k1_gog_103.json` loses `reference_image`.
- Exclusions: 63 cache entries, 4 other address tables, `__main__`/`cli`/`pioneer`/`playback`, and retired `50_*`/`60_*` TOMLs.

Real build (`review-probes-packaging/build_real.py`):
- The unpatched non-dry build refuses with `absolute local paths in packaged text: scripts/harness/kpharness/capture_diagnostic.py:54`.
- For inspection, a second build bypassed only that refusal. It gave `zip_sha256 5642c429…2d4a`, 62 manifest files plus `manifest.json`, and `zip_crc PASS`.

Independent scan of that ZIP (`scan.py`):
- 63 entries: 34 `.py`, 10 `.lua`, 9 `.toml`, 5 `.json`, 4 `.md`, 1 with no suffix.
- `testzip() None`.
- No media or retail magic (PNG/GIF/JPG/RIFF/BIK/BIFF/KEY/ERF/RIM/TLK/2DA/GFF/ZIP/ELF/PE/MKV/MP3/OGG).
- No non-UTF-8 entry, and no unsafe entry name.
- String hits:
  - `/home/`: only `capture_diagnostic.py:54` (known, and the builder refuses it).
  - `brunner56`, `bodencrouch`, `arrenkaetris`, `halomastar`, `.superpowers`, `kp-live`, `kp-release`, `MyBook`, `.worktrees`, `linuxbrew` (other than line 54), `data/adjudication`, `data/research`, `next-k1-preparations`, run IDs: none.
  - `/tmp/`: 9 hits, all X11 socket or probe paths in harness code. That is legitimate.
- Address table: `adjudicated_bindings` is an integer count (219), not research data. It holds 16-byte `expected_bytes` prologue signatures per site. The console release ZIP already ships the same kind of data (`kp-release-20260927/package.py:77-79`), so that precedent covers it.

Independent extract and rehash:
- `extractall` into `review-probes-packaging/extract` gives 63 files, all under `kotorphasor-creative-harness/`, with none outside.
- Every `manifest.json` entry re-hashes equal. The only file not in the manifest is `manifest.json` itself.
- The ZIP SHA-256 equals `zip-sha256.txt`.

Verdict on the real tree: **no leak today**. The builder refuses the one known hit.

### Adversarial probes (fake trees, `review-probes-packaging/adversarial.py`, `race.py`)

| Probe | Result |
|---|---|
| `docs/user` is a symlink to an outside folder | **BUILT**. Outside bytes ship as `docs/user/creative-harness.md`. |
| `scripts/examples` is a symlink to an outside folder | **BUILT**. `outside_secret.lua` ships. |
| Leaf-file symlink | REFUSED (`source contains a symlink … ln.lua`) |
| Hard link to an outside private file named `hl.lua` | BUILT, and the private bytes ship |
| Case variants `A.SAV b.GIF c.Mp4 d.TPC e.Bik f.2DA` | all excluded |
| `evil.lua` holding PNG magic plus `/home/secretuser` | **BUILT**. PNG bytes and the home path ship, because the path scan skips non-UTF-8. |
| UTF-16 `.lua` holding `/home/…` | **BUILT**, and the path ships |
| `.lua` holding `brunner56`, `~/kp-live-20260922`, `.superpowers/sdd`, `C:\Users` | **BUILT**. None is a scan marker. |
| `scripts/examples/cursed/{.superpowers/sdd,data/adjudication,tmp,Saves}/n.lua` | **BUILT** for `.superpowers`, `adjudication` and `tmp`. `Saves` is denied. |
| File named `..\..\..\..\evil.lua` | BUILT. The entry name holds backslashes. |
| README with `/Users/bob` | REFUSED by the path scan |
| Source edited, then reverted, inside the stage-to-provenance window (a plain edit left in place is caught as `provenance mismatch`) | **BUILT**. It shipped `-- TAMPERED in window`, and the shipped SHA-256 does not equal the overlay (`race.py`: `shipped sha == overlay: False`). |

## Findings

### Critical

None. The real-tree ZIP is clean except for the one known hit, and the builder already refuses that.

### Important

**I-1. A symlinked parent folder is followed, not refused.**
claim: the builder refuses symlinks in the source tree (spec P1 step 1; report "It refuses symlinks"). For fairness: the release `package.py:61`, which the spec says to mirror, also checks only file-level `is_symlink()`. The task asks about symlinks that point outside the tree by name, and on the plain reading of "symlinks in the source tree" this still fails.
referent: `adversarial.py` output `parent_symlink_fixed: BUILT; leaked … docs/user/creative-harness.md; leaked bytes=[b'Secret outside doc']` and `parent_symlink_walked: BUILT; … outside_secret.lua`.
checked: `_walk` tests `base.is_symlink()` only on the walked folder itself (line 106). FIXED files test only the last component (line 158). Intermediate components (`docs/user`, `scripts/examples`, `data`, `tools/tests`) are never tested.
verdict: does not hold
confidence: high. Today's tree has no such symlink (checked with `[ -L ]` over 12 parents), so this is latent. G3a builds from a tree that is still changing.
Fix shape: for every selected path, refuse if `os.path.realpath(root/rel) != str(root/rel)`, or refuse any symlink in any component from `root` down.

**I-2. The private denylist matches only at the repository root.**
claim: private evidence cannot reach the ZIP. The spec §2 list is root-relative, and the builder honors it at the root. This finding is adversarial, beyond the spec text.
referent: `adversarial.py` output `nested_private: BUILT; leaked entries=[…/cursed/.superpowers/sdd/n.lua, …/cursed/data/adjudication/n.lua, …/cursed/tmp/n.lua]`.
checked: `deny_reason` uses `rel.startswith(PRIVATE_PREFIXES)` (line 90). `Saves`/`saves` and `RUN_EVIDENCE` already match on any path part (lines 86-92).
verdict: does not hold (for nested copies; the root-relative spec items hold)
confidence: high
Fix shape: match `.superpowers`, `adjudication`, `research`, `tmp`, `kp-live-*` and `.worktrees` on any path part, the way `Saves` is matched. Also refuse subfolders under the example and scenario folders, which should be flat.

**I-3. The path scan skips non-UTF-8 files and uses too few markers. Allowed suffixes are not checked by content.**
claim: the absolute-path scan fails the build on local paths. No media ends up in the ZIP.
referent: `adversarial.py`:
- `binary_lua: BUILT; leaked bytes=[b'\x89PNG', b'/home/secretuser']`
- `utf16_lua: BUILT`
- `markers: BUILT; leaked bytes=[b'brunner56', b'kp-live', b'.superpowers']`

checked: `path_scan` returns `[]` on `UnicodeDecodeError` (lines 199-202). `PATH_MARKERS` holds only `/home/`, `/run/media/` and `/Users/` (line 65). Selection is by suffix only (`.lua`, `.toml`, `.py`, `README.md`), with no magic check.
verdict: does not hold (the builder does not enforce it; the real tree is clean today)
confidence: high
Fix shape:
- Fail the build when a text-suffix file is not UTF-8.
- Refuse a file that opens with known media or archive magic.
- Add the basename of `$HOME`, `kp-live`, `kp-release`, `.superpowers`, `MyBook`, `.worktrees`, `linuxbrew` and `C:\Users` to the markers.

**I-4. Provenance binds a second read of the source, not the staged bytes.**
claim: every packaged file is bound to the overlay or the base commit.
referent: `race.py` output `build ok: PASS | shipped: b'-- TAMPERED in window\n' | shipped sha == overlay: False`.
checked: `build()` stages `(root/rel).read_bytes()` (line 278). `check_provenance` reads the file again (line 235). Nothing compares the two. The probe edits the file before the staging read and reverts it before the provenance read. An edit left in place is caught as a mismatch. An edit that is reverted inside the window, which a concurrent writer's save-and-undo can cause, ships unbound bytes. The real dry run took 3m25s on this drive, and the capture writer and the examples writer edit these files during round 11.
verdict: does not hold
confidence: high
Fix shape: hash the raw bytes read at staging and bind provenance to that hash. Then re-read after staging and refuse on any change, the way `create_snapshot` compares its before and after lists.

### Minor

- **M-1. Hard links are not refused.** `hardlink: BUILT; leaked bytes=[b'PRIVATE hardlinked']`. Fix: refuse `st_nlink != 1` on selected files. The real tree has none (`find … -links +1` is empty).
- **M-2. Backslashes in entry names are allowed.** `backslash_name` built `…/cursed/..\..\..\..\evil.lua`. Python `extractall` is safe. Some Windows extractors treat `\` as a folder separator. Fix: refuse `\` and control characters in `rel`.
- **M-3. The host check accepts any ELF.** A PATH `ffmpeg` symlinked to `/usr/bin/env` reports `status: ok` (`hc/` probe). The ELF magic check does not confirm the tool. Fix: also compare the realpath basename with the tool name, or flag a mismatch.
- **M-4. `commit_inputs` claims more than it does.** The docstring says writing the hashes before launch means "they cannot be taken from the run folder after the fact". Nothing enforces that:
  - `executed-route.toml` is a byte copy of the route.
  - `commit_inputs` accepts a route inside `--runs-dir`.
  - The `utc` field is self-reported and not chained.
  - Neither accept nor export reads the inputs log.

  Fix: refuse a route under `runs_dir`, and reword the text as a procedural safeguard.
- **M-5. The guide steers users to the brew build.** Guide line 49 says "Use the path shown in `elf_elsewhere`". On this host that is `/home/linuxbrew/.linuxbrew/bin/ffmpeg` (host run below). Line 63 and every example use `/usr/bin`. The plan's encoder caveat says the noise floor was calibrated on `/usr/bin/ffmpeg`. Fix: say to prefer the distribution package, and use `elf_elsewhere` only as a pointer.
- **M-6. The guide does not say the release DLL is unproven for this flow.** Line 107 tells users to use the DLLs "from the release ZIP". The only live run used `kphasor.dll fd8e069a…`. The shipped pair is `4e14d0fe…`, with no creative evidence (plan §1 "DLL binding gap"). Add one line to the status box.
- **M-7. Plain copy.** Two table cells are comma-separated noun piles, which `plain-ui-copy.md` bans:
  - line 25, "Boot, F12 console, Lua scripts, save load, route steps"
  - line 30, "GNOME, Xorg, Windows, macOS"

  Split them into rows. Everything else passes: all 13 headings are verb-first, and a grep for the buzzword list gives rc=1.
- **M-8. `export_verify` reports FFprobe identity but does not enforce it.** `ffprobe_matches_acceptance` can be `false` while `ok` is `true`. The guide says `ok: true` means "every check passes". Either enforce it or document it.
- **M-9. The refusal text in `commit_inputs` names the wrong log.** It says "cleanup commitment log", because the validator is imported. The implementer already reported this.

## export_verify: can the sidecar satisfy itself?

claim: `export_verify` cannot pass using only values taken from the sidecar.
referent: `export_verify.py:121-123` compares the required CLI hashes to `selected_*`. `:128-135` binds the `creative-run.json` bytes and calls `verify_acceptance` with the user's hashes. `creative_accept.py:574-601` recomputes the execution and acceptance receipt hashes and requires `cleanup_state_clear(run_dir, head)`, which compares the live ledger hash with the user's head (`:429-436`). `:150-152` requires the master inside this run. The tests cover each hash mismatch (`kpharness_export_verify_test.py`, 16 OK).
checked: code read plus test run
verdict: holds. The residual is by design: the only external anchor is the hashes the user copies from `~/kp-inputs.log` and `~/kp-commitments.log`. The tool never reads either log, so a user who copies the `selected_*` values from `export.json` defeats the anchor.
confidence: medium. A test with an unmocked `verify_acceptance` would raise it. None exists until G5.

## commit_inputs log semantics

The log uses the same admission rules as the cleanup log: it exists, is regular, is not a symlink, has `nlink == 1`, sits outside the runs tree, and has no inode alias. The helper opens it with `O_APPEND|O_NOFOLLOW`, re-checks the identity, and writes each line in one `write` followed by `fsync`. Each line is `kpharness.input-commitment.v1`. Nothing chains the lines and nothing parses them. The separate file keeps the tool-owned chain clean, which is the plan's stated reason. The hash semantics match acceptance:
- route: a byte-for-byte copy (`creative.py:233-249`)
- FFprobe: `which`, then resolve, then hash, the same steps as `recording.probe_tool_identity`

Holds, except for M-4.

## Host check wrapper detection

Host (`host-cmd`, Python 3.14.7): `ok=false`, rc=1, `blocked_by=["ffmpeg","ffprobe"]`.
- Both resolve to `~/.local/bin/*` scripts, and `elf_elsewhere` points at brew.
- `mpv` is a non-blocking wrapper, with `elf_elsewhere` `/usr/bin/mpv`.
- `wine` resolves to `/usr/bin/wine64` ELF.
- Render nodes: `renderD128` and `renderD129`.

With `--path /usr/bin:/bin`: `ok=true`, rc=0, `blocked_by=[]`.

Container: `ffmpeg`/`ffprobe` are wrappers, and gamescope, Xwayland, xdotool, glxinfo and wine are missing, as expected inside the container. Detection holds, except for M-3.

## User guide honesty

Only K1 GOG 1.03 under Wine, Gamescope and KDE Wayland is live. Capture is "Known to fail". Accept and export are "Tested offline only". K1 Steam is known-failing. K2 is not supported. Other hosts are not attempted, and Crostini is refused. Run and export are marked *(pending)*. The CLI flags in the guide match the parsers: `creative.py:397-415`, `creative_accept.py:945-954`, `creative_export.py:110-118`, `gamescope_snapshot.py:311-318`. The ledger-head `grep` matches the compact `sort_keys` JSON written by `_emit_head` (`creative_accept.py:356-368`). Holds, except for M-5, M-6 and M-7.

## Commands and outputs

Container (Python 3.12.3):
- `PYTHONDONTWRITEBYTECODE=1 python3 tools/creative_host_check_test.py`: `Ran 10 tests in 0.126s OK`
- `PYTHONDONTWRITEBYTECODE=1 python3 tools/kpharness_commit_inputs_test.py`: `Ran 10 tests in 0.035s OK`
- `PYTHONDONTWRITEBYTECODE=1 python3 tools/kpharness_export_verify_test.py`: `Ran 16 tests in 0.306s OK`
- `PYTHONDONTWRITEBYTECODE=1 python3 tools/package_creative_harness_test.py`: `Ran 15 tests in 105.806s OK`

Host (`/home/brunner56/.local/bin/host-cmd sh -c 'cd <worktree> && …'`, Python 3.14.7):
- `creative_host_check_test`: `Ran 10 tests in 0.029s OK`
- `kpharness_commit_inputs_test`: `Ran 10 tests in 0.034s OK`
- `kpharness_export_verify_test`: `Ran 16 tests in 4.545s OK`
- `package_creative_harness_test`: `Ran 15 tests in 111.114s OK`

All 51 tests pass in both places. The existing tests pass because none of them plants I-1 through I-4.

Probe scripts and outputs are in `/home/brunner56/kp-live-20260922/review-probes-packaging/`: `dryrun.json`, `build_real.py`, `out-real/`, `extract/`, `scan.py`, `adversarial.py` with `adv/`, `race.py` with `race/`, and `hc/`.

## Verdict

The code is well built and the real tree packages cleanly today. Four gaps remain. The builder does not refuse a symlinked parent folder (I-1). It does not deny private folder names below the root (I-2). It does not check content under allowed suffixes (I-3). It does not bind provenance to the staged bytes (I-4). Each is shown by a probe that builds a ZIP with the wrong bytes in it. Rule applied: any Important finding on the publication boundary, which is the highest-priority check, means FAIL. I-1, I-3 and I-4 are enough on their own. I-2 adds to them. Fix I-1 to I-4 and add one red test for each before G3a.

Packaging P0-P4 verdict: FAIL
