# Creative packaging P0–P4 report

Date: 2026-09-27. Plan: `/home/brunner56/kp-live-20260922/fanout-creative-packaging-plan.md`.
Worktree: `.worktrees/lua-boundary-validation` (HEAD `ca329e5`, dirty).

Scope held:
- New files only (9). `git status --short` shows all nine as `??`. No existing file was edited.
- No Wine, game, Gamescope, FFmpeg or FFprobe run. The lock file was not touched.
- No package was published. Test packages were built only under `tempfile.TemporaryDirectory()`.
- Every test ran with `PYTHONDONTWRITEBYTECODE=1` and `sys.dont_write_bytecode = True`. No `.pyc` exists for any new module (`ls __pycache__ | grep -E "commit_inputs|export_verify|package_creative|creative_host_check"` returns nothing).

Test totals: 51 tests in 4 files (10 + 10 + 16 + 15). All pass in the container (Python 3.12.3) and on the host (Python 3.14.7). The final rerun came after every edit.

## P0. Host check

Files:
- `tools/creative_host_check.py`
- `tools/creative_host_check_test.py` (10 tests)

Behavior:
- It reads files only: PATH lookup, `realpath`, and a 4-byte ELF magic read. It also globs `/dev/dri/renderD*` and checks Python >= 3.12. It prints one JSON line. Exit 0 means ok; exit 1 means blocked.
- Deviation 1: `wrapper` blocks only `ffmpeg` and `ffprobe`, the two tools the harness hashes and runs directly. For the other tools `wrapper` is information only.
- Deviation 2: `mpv` is non-blocking because only the diagnostic uses it.
- New field `elf_elsewhere` names the first later PATH entry that is an ELF.

Red: `ModuleNotFoundError: No module named 'creative_host_check'`.
Green: container `Ran 10 tests ... OK`; host `Ran 10 tests in 0.082s OK`.

Live host result (read-only):
- `python3 tools/creative_host_check.py` returns `ok=false` with `blocked_by=["ffmpeg","ffprobe"]`.
  - PATH `ffmpeg` resolves to `~/.local/bin/_host_wrap_template`, which is a script.
  - PATH `ffprobe` resolves to `~/.local/bin/ffprobe`, which is also a script.
  - `elf_elsewhere` points to the brew ELF for both.
- `--path /usr/bin:/bin` returns `ok=true`. All 10 tools are ELF there, including `bwrap`, `glxinfo` and `xdotool`. That settles three items on the plan's "unverified" list.
- Two render nodes were found: `renderD128` and `renderD129`.

## P1. Package builder and dry-run test

Files:
- `tools/package_creative_harness.py`
- `tools/package_creative_harness_test.py` (15 tests)

Builder API: `select_files`, `deny_reason`, `clean_bytes`, `path_scan`, `check_provenance`, `verify_zip`, `build`, `closure_files_sha256`.

CLI flags:
- `--source-root`
- `--provenance`
- `--out`, which must not exist
- `--dry-run`, which writes nothing

It mirrors release `package.py` steps 1–8:
1. It refuses symlinks.
2. It checks provenance.
3. It stages with `mkdir(exist_ok=False)`.
4. It sanitizes JSON and records every change and exclusion.
5. It writes `manifest.json`.
6. It writes the ZIP with mode `'x'` under `kotorphasor-creative-harness/`. Entries get fixed timestamps.
7. It runs `testzip()` and re-hashes every entry.
8. It writes `zip-sha256.txt` and `verification.json`.

Red: `ModuleNotFoundError: No module named 'package_creative_harness'`.

Intermediate red, after the builder existed and before P2: `RealTreeDryRun` failed with `ValueError: required package file is missing: docs/user/creative-harness.md`. That was expected, and P2 fixed it.

Green:
- Final container run: `Ran 15 tests in 18.875s OK`. An earlier run took 55 s because the drive was cold.
- Final host run: `Ran 15 tests in 16.438s OK`.
- Slowest test: the real-tree closure test at 28 s in the container. The cost is AST parsing on the MyBook drive.

Tests, mapped to the plan's list:
1. Planted items are excluded with a deny reason. The `.sav`, `.gif`, `continuous.mp4`, `accepted-media-x/export.json`, `creative-run.json` and `__pycache__/*.pyc` sit inside walked folders. Each is absent from the ZIP, and each reason appears in `exclusions`. `data/adjudication/x.json`, the K2 table and the retired `50_*.toml` are also absent.
2. A symlink refuses the build, and no `--out` is created.
3. The absolute-path scan fails the build with `scripts/harness/kpharness/shared.py:1`. Dry-run lists the same hit.
4. Every manifest entry re-hashes equal from the ZIP. `testzip()` returns None, the entry set equals the manifest plus `manifest.json`, and `zip-sha256.txt` matches.
5. A second build into an existing `--out` refuses and leaves the folder unchanged.
6. The module set equals `runtime_module_paths(fake_tree, ENTRIES)`. `playback.py` and `pioneer.py` are absent. Extra test: a closure that imports `playback` raises `ValueError`.
7. Extracted ZIP, no `.git`: `creative.shared_lock_path(tree)` returns `tree/tmp/harness-locks/live-game.lock`, and no `tmp/` is created.
8. Sanitization removes `reference_image` and the private `source_path`, and records `removed_metadata_keys`.
- Extra 9: the extracted ZIP passes the real `gamescope_snapshot.create_snapshot(<extracted>/scripts/harness, …)`. The snapshot `files` equal the package's recorded `snapshot_files`, and their hash matches `snapshot_files_sha256`.
- Extra 10: provenance must bind every file.
  - A file missing from the overlay, with no git base, gives `unbound`.
  - A changed file gives `provenance mismatch`.
  - A missing `--provenance` refuses.
  - None of the three creates `out`.
- Extra 10b: git-base binding.
  - `git init` and a commit on the fake tree, then provenance `{"base_commit":"HEAD","overlay_sha256":{}}`.
  - All selected files are `bound_by_base`, and the build passes.
  - After one edit, that file is `unbound` and the build refuses.
- Extra 11: no absolute temp path appears in `packaging-receipt.json`, `manifest.json`, `source-provenance.json` or `verification.json`.
- Extra 12: `--dry-run` writes nothing.

Real-tree dry run: `python3 tools/package_creative_harness.py --dry-run` gives rc=0 (output kept in `/tmp/p1-dryrun.json`).
- 60 files selected. The closure has 32 modules.
- **`playback.py`, `pioneer.py` and `cli.py` are not in the closure.** This settles the plan's unverified closure question for today's tree.
- The only path-scan hit is `scripts/harness/kpharness/capture_diagnostic.py:54 (/home/)`. The plan cited line 52; round 11 has since shifted it. This is the referent for the P5 ruling: a non-dry build refuses until the capture writer fixes `DEFAULT_FFPROBE`.
- Sanitization: `data/addresses/k1_gog_103.json` loses `reference_image`.
- Exclusions:

  | Reason | Count |
  |---|---|
  | `__pycache__` | 63 |
  | Not allowlisted: the four other address tables | 4 |
  | Not in closure: `cli`, `pioneer`, `playback`, `__main__` | 4 |
  | Retired: `50_chaos_roulette.toml`, `60_rave.toml` | 2 |

- `scripts/examples/showcase/` is empty in this worktree, so no showcase example is packaged. Showcase routes have no scenarios folder, which matches the plan's note. Revisit after the examples writer lands.
- `snapshot_files_sha256` today: `15e6cdb9…c74f`. It is not stable, because round 11 is editing the closure.
- Base-commit dry run: `--provenance {"base_commit":"ca329e5","overlay_sha256":{}}`, output kept in `/tmp/p1-dryrun-base.json`.
  - 28 files are bound by the base. 32 are unbound. The 32 are the concrete G2 worklist:
    - Harness modules (22): `capture_diagnostic`, `console_protocol`, `console_steps`, `creative`, `creative_accept`, `creative_export`, `creative_steps`, `creative_wine`, `discover`, `display_backends`, `gamescope_processes`, `gamescope_snapshot`, `gamescope_socket`, `gamescope_xwayland`, `owned_x11`, `physical_console`, `recording`, `scenario`, `session`, `waits`, plus new `commit_inputs` and `export_verify`.
    - Other files: `data/addresses/k1_gog_103.json`, `docs/creative-runner.md`, `docs/user/creative-harness.md`, `tools/creative_host_check.py`, `tools/tests/examples/manifest.json`, `scenarios/cursed/70_doppelganger.toml`, and cursed `100_item_airstrike.lua`, `40_chain_reaction.lua`, `70_doppelganger.lua` and `README.md`.
  - Each needs an overlay entry or a commit.

Findings that change the plan:
- **F1. The allowlist was missing two snapshot inputs.** When the source root ends in `scripts/harness`, `gamescope_snapshot.create_snapshot` hashes `tools/tests/examples/manifest.json` and `data/app_signatures.toml` (`gamescope_snapshot.py:170-172`). `creative.py:109-110` also reads the examples manifest. Both are now in `FIXED`. Without them, `create` fails from an extracted candidate. Extra test 9 is the referent.
- **F2. The G4 check on `snapshot_manifest_sha256` cannot pass as written.** The snapshot manifest holds `created_utc` and an absolute `repository_root` (`gamescope_snapshot.py:164-171`). No precomputed hash can equal a user run's `manifest_sha256`.
  - The builder records `snapshot_files` and `snapshot_files_sha256` instead. That is the canonical hash of the sorted `{path, sha256}` list from `DEFAULT_ENTRIES`, the entries the `create` CLI uses.
  - **Proposed G4 wording:** hash the run's `gamescope-harness-manifest.json` `files` list with `closure_files_sha256`. The result must equal the candidate's `snapshot_files_sha256`.
  - No snapshot manifest goes into the package, because it carries a local path.
- **F3. Package closure versus snapshot closure.**
  - The package closure uses the plan's 5 entries plus `commit_inputs` and `export_verify`. The guide tells users to run those two.
  - The run snapshot closure uses only `DEFAULT_ENTRIES` (`creative`, `gamescope_snapshot`). Both are recorded.
- **F4. Provenance binding.** The overlay is checked per file. A file outside the overlay passes only when `git rev-parse <base>:<path>` equals `git hash-object <path>`. Anything else is `unbound`, and the build refuses. This matches G2's "base plus overlay" form.

## P2. User guide draft

File: `docs/user/creative-harness.md`. It is packaged, and the path scan passes on it.

Content:
- A status box at the top says no run has passed capture, so acceptance cannot succeed today.
- The support table lists one live cell: K1 GOG 1.03, Wine, Gamescope, KDE Wayland. Capture is marked known-failing. Accept and export are marked offline-only. K1 Steam is known-failing. K2 is not supported. GNOME, Xorg, Windows and macOS are not attempted. Crostini is refused.
- Run and export are marked *(pending)*.
- Every example path uses `~/`.

Deviations from the plan's draft:
- The inputs step uses `python3 -m kpharness.commit_inputs` instead of hand-run `sha256sum`.
- The verify step passes `--route-sha256`, `--ffprobe-sha256`, `--cleanup-ledger-sha256` and `--ffprobe`, as P3 requires.

Slop audit:
- The `plain-ui-copy` skill was read from `~/.agents/skills/plain-ui-copy/`. The guide uses Mode B.
- Every heading starts with a verb.
- Grep for the buzzword list and for `/home/`, `/run/media/` and `/Users/` gives rc=1 (no hits).
- Two list sentences were rewritten as bullets or short sentences.

## P3. Sidecar verifier

Files:
- `scripts/harness/kpharness/export_verify.py`
- `tools/kpharness_export_verify_test.py` (16 tests)

It is pinned to sidecar `schema: 1`. It is read-only. Imports:
- `verify_acceptance` from `creative_accept`
- `probe_video` from `recording`
- `ffprobe_identity` from `commit_inputs`

Checks, in order:
1. The folder is a real `accepted-media-*` folder.
2. `export.json` is a regular file with schema 1.
3. The supplied route, FFprobe and ledger hashes equal the sidecar's `selected_*` values.
4. `run_dir` is this run.
5. `accepted_receipt_sha256` equals the current `creative-run.json` bytes.
6. `verify_acceptance(...)` returns True.
7. Execution, content-artifact and geometry hashes equal `visual_review`.
8. `source_video.sha256` equals the receipt master hash, and the master still hashes to it.
9. The interval is finite, `0 <= start < end`, and `duration == end - start`.
10. `gif_fps` is in [1,60].
11. The sidecar lists exactly the MP4 and the GIF, and the folder holds no extra files.
12. FFprobe must be an ELF.
13. For each artifact:
    - The path is either the absolute export-folder path or the bare name. Anything else is refused.
    - The file is a regular non-symlink and its SHA-256 matches.
    - The re-probed duration is within 1 ms of the sidecar value, and width and height are equal.
    - The duration matches the interval within the exporter's tolerance: 0.1 s for MP4, `max(0.1, 1/gif_fps)` for GIF.
14. The report gives `shareable` and `local_path_fields`.

Red: `ImportError: cannot import name 'export_verify' from 'kpharness'`.
First green run: 14 of 15 passed. `test_relative_artifact_paths_pass_and_are_shareable_when_run_dir_absent` failed with `AssertionError: False is not true : ['source_video.path']`. The verifier was right. The test was fixed to relativize that field too.
Green: final container run `Ran 16 tests in 0.170s OK`; final host run `Ran 16 tests in 0.126s OK`.

Tests:
- The untampered export passes, and the absolute paths are flagged.
- The relative form passes, with `shareable=true`.
- `verify_acceptance` returning False refuses.
- Each supplied hash mismatch refuses.
- 15 single-field tampers each refuse.
- Changed receipt bytes, a changed master and changed artifact bytes each refuse.
- A re-probe outside the interval refuses.
- A re-probe that disagrees with the sidecar refuses.
- An extra file refuses.
- A symlinked artifact refuses.
- A folder outside a run refuses.
- An FFprobe script refuses before any probe.
- `main` gives exit 0 or 1 with JSON output.
- Round trip: the real `creative_export.export()` builds the sidecar and folder, and `verify_export` passes on them. The test mocks only the exporter's acceptance and evidence gates, `probe_video` and the encoder `subprocess.run`.
  - The folder holds exactly `export.json` plus the MP4 and the GIF, so the exporter's staging unlink works.
  - `shareable` is false and `source_video.path` is flagged.

Findings:
- **F5. Sidecar defect 1 is wider than the plan lists.** `source_video.path` also carries the absolute master path, because `creative_export.py` copies `receipt['media']['continuous']` whole. P5 should make it relative as well.
- **F6. Deviation: the CLI needs four inputs, not only the folder path.** Those are the route, FFprobe and ledger hashes plus an explicit ELF `--ffprobe`. Taking the hashes from the sidecar would verify the sidecar against itself.

**Rerun after round 11 lands:** `tools/kpharness_export_verify_test.py`. `creative_accept.verify_acceptance` is mocked in the test, so a signature change there would not be caught. Also run one unmocked check once a real accepted run exists (G5). Bump `SIDECAR_SCHEMA` if round 11 changes the sidecar.

## P4. Input commitment helper

Files:
- `scripts/harness/kpharness/commit_inputs.py`
- `tools/kpharness_commit_inputs_test.py` (10 tests)

`commit_inputs(route, ffprobe, log, runs_dir)` works in four steps:
1. It admits the log through `creative_accept.validate_commitment_log(log, runs_dir)`, imported read-only. The rules are: the file exists, is regular, is not a symlink, has one link, and sits outside the runs folder.
2. It hashes the route with `O_NOFOLLOW`. The file must be regular.
3. It resolves FFprobe with `shutil.which` and `realpath`, and refuses a non-ELF.
4. It writes one `O_APPEND` line and checks the identity before `fsync`. The line holds `kind: kpharness.input-commitment.v1`, `route{path,sha256}`, `ffprobe{command,resolved_path,sha256}` and `utc`.

Hash compatibility, the referent that the two hashes match what acceptance compares:
- Route: `creative.py:233-236` copies the route byte-for-byte with `shutil.copy2` to `executed-route.toml`. It then checks `sha256(route_copy) == input_before[str(route)]`, the hash of the original file. `route_source` is `artifact(route_copy)` (`creative.py:249`). So a file hash taken before launch equals `route_source.sha256`, as long as the same file is passed to `--route`.
- FFprobe: `recording.py:759` sets `cadence.probe_tool` from `probe_tool_identity(self.ffprobe)`. That function does `shutil.which`, then `resolve`, then hashes the resolved file (`recording.py:243-252`). `commit_inputs.ffprobe_identity` does the same steps. The two agree when both get the same `--ffprobe` value.

Design choice: the helper writes a separate inputs log, passed as `--log ~/kp-inputs.log` together with `--runs-dir`. This follows the plan's section 3 reasoning. The tool-owned commitment chain stays clean.

Red: `ImportError: cannot import name 'commit_inputs' from 'kpharness'`.
Green: container `Ran 10 tests in 0.065s OK`; host `Ran 10 tests in 0.013s OK`.

Tests:
- A normal append works.
- A second append keeps earlier lines, including a user line.
- A missing log, a symlinked log, a hard-linked log and a log inside the runs folder each refuse and write nothing.
- An FFprobe wrapper script refuses.
- A PATH lookup resolves to the real file.
- A missing route, a symlinked route and a directory route each refuse.
- `main` gives exit 0 or 1.

Minor: a refusal message says "cleanup commitment log", because the text comes from the imported validator. It is cosmetic.

**Rerun after round 11 lands:** `tools/kpharness_commit_inputs_test.py`. It imports `creative_accept.validate_commitment_log`, and round 11 changes log validation ("re-validates the log before appending").

## Wiring snippets (not applied; the target files are owned by others)

P6 CTest, as a hunk-only edit to `CMakeLists.txt:33` through the index owner. Add the four new gates to the existing foreach:

```cmake
foreach(gate kpharness_offline_test kpharness_world_test kpharness_creative_test kpharness_physical_console_test kpharness_gamescope_backend_test
             kpharness_export_verify_test kpharness_commit_inputs_test creative_host_check_test package_creative_harness_test)
```

- `package_creative_harness_test` needs about 60 s on the MyBook drive. The current `TIMEOUT 300` covers it.
- The plan also lists `kpharness_capture_diagnostic_test` and `kpharness_gamescope_boot_repair_test` as missing today. Those belong to the capture writer.

CLI entries: none needed. The new commands are standalone.
- `PYTHONPATH=scripts/harness python3 -m kpharness.commit_inputs …`
- `PYTHONPATH=scripts/harness python3 -m kpharness.export_verify …`
- `python3 tools/creative_host_check.py`
- `python3 tools/package_creative_harness.py [--dry-run] …`

If `kpharness/cli.py` (Pioneer unit) should expose them later, add these two subcommands:

```python
# in kpharness/cli.py subcommand table
'commit-inputs': lambda argv: __import__('kpharness.commit_inputs', fromlist=['main']).main(argv),
'export-verify': lambda argv: __import__('kpharness.export_verify', fromlist=['main']).main(argv),
```

## Residual gates

| Gate | State after P0–P4 |
|---|---|
| G1 round-11 review | Open. Rerun `kpharness_export_verify_test` and `kpharness_commit_inputs_test` once it lands. Rerun `package_creative_harness_test` too, because it imports `kpharness.creative`. |
| G2 source binding | Open. The builder refuses without `--provenance`. Against base `ca329e5`, 32 selected files are unbound; the list is in P1. |
| G3a candidate | Blocked by two things. `capture_diagnostic.py:54` hard-codes a brew path, which is a P5 fix for the capture writer. G2 must also pass. |
| G3, G4 live | Not started. Adopt the G4 wording from F2. |
| G5 export and verify | The verifier exists. The sidecar fixes are still owed in P5: defects 1–3, plus `source_video.path` from F5. |
| G6, G7 | Not started. |

Other residual items:
- The showcase examples are absent in this worktree.
- Guide ledger-head step: the guide now picks the last line whose `run_dir` is this run. It no longer takes the file's last line, which could belong to another run.
- The inputs log and the helper exist. Having `creative.py` call `commit_inputs` itself stays optional work for P5.

## Protocol blocks

claim: 51 new tests pass in the container and on the host.
referent: per-file `Ran N tests … OK` lines above (10 + 10 + 16 + 15).
checked: `PYTHONDONTWRITEBYTECODE=1 python3 tools/<test>.py` in the container; `host-cmd sh -c 'cd <worktree> && …'` on the host.
verdict: holds
confidence: high. A round-11 change to `creative_accept`, `recording` or `creative` imports could change it.

claim: the harness import closure does not reach playback, pioneer or cli.
referent: `/tmp/p1-dryrun.json` closure list (32 modules); test `RealTreeDryRun.test_real_closure_excludes_unfinished_modules`.
checked: real-tree `--dry-run`.
verdict: holds
confidence: medium. It holds for today's tree only, and round 11 is still editing.

claim: G4's `snapshot_manifest_sha256` equality cannot pass as written.
referent: `gamescope_snapshot.py:164-171`, where the manifest has `created_utc` and an absolute `repository_root`.
checked: code read, plus extra test 9, which shows the `files` list is the stable identity.
verdict: holds
confidence: high

claim: no existing file was modified.
referent: this session's tool record. Every Write, Edit and heredoc targeted one of the nine new paths or this report. `git status --short` on those paths shows `??` for each.
checked: tool record; git status. `git status` alone cannot rule out edits to other files.
verdict: holds
confidence: high

## Fix round: review I-1..I-4, M-1..M-9 (2026-09-27)

Review: `/home/brunner56/kp-live-20260922/creative-packaging-p0-p4-review.md`. The probes `adversarial.py` and `race.py` became red tests first. Scratch output is in `/home/brunner56/kp-live-20260922/review-probes-packaging/fixround/`. No game, capture or lock was used. Nothing was published, and no git write was made.

Files touched: `tools/package_creative_harness.py`, `tools/package_creative_harness_test.py`, `tools/creative_host_check.py`, `tools/creative_host_check_test.py`, `scripts/harness/kpharness/commit_inputs.py`, `tools/kpharness_commit_inputs_test.py`, `scripts/harness/kpharness/export_verify.py`, `tools/kpharness_export_verify_test.py`, `docs/user/creative-harness.md`, new `tools/scan_release_zip.py`, and this report.

### Red first

The new tests were run against the unfixed code (container, Python 3.12.3):
- `creative_host_check_test`: 4 of the 4 new tests red (2 FAIL, 2 ERROR).
- `kpharness_commit_inputs_test`: 2 of the 2 new tests red (3 failing subtests).
- `kpharness_export_verify_test`: 1 of the 1 new test red.
- `package_creative_harness_test AdversarialTests ReleaseZipScanTests`: 18 of the 19 new tests red. The one that stayed green, `test_i4_zip_holds_exactly_the_bound_bytes`, is a guard test.

Existing tests changed on purpose, because the contract changed:
- The host check test `test_never_launches_a_process` was replaced by `test_m3_only_ffmpeg_and_ffprobe_version_are_run`. `setUp` now mocks `subprocess.run` with a version banner.
- In the export verify tests, `FFPROBE_SHA` is now `sha256(ELF)`. Under M-8, a mismatched FFprobe makes `ok` false.
- `BuilderTests` now shares a `TreeCase` base with `AdversarialTests`. No assertion changed.

### Green

Container (Python 3.12.3):
- host check: `Ran 13 tests … OK`
- commit_inputs: `Ran 12 tests … OK`
- export_verify: `Ran 17 tests … OK`
- package builder: `Ran 34 tests in 13.378s OK`

Host (`host-cmd`, Python 3.14.7):
- host check: 13 OK
- commit_inputs: 12 OK
- export_verify: 17 OK
- package builder: `Ran 34 tests in 22.926s OK`

Total: 76 in each place.

Real-tree dry run after the fixes (`fixround/dryrun.json`, rc=0, 13.6s):
- 60 files are selected.
- Content refusals: none.
- The only `path_scan` hit is `scripts/harness/kpharness/capture_diagnostic.py:54 /home/`. That is the same known hit as before; the line is out of scope and unchanged.
- Sanitization: `k1_gog_103.json` loses `reference_image`.

### Protocol blocks

claim: I-1 fixed. A symlink in any path part refuses the build.
referent: `refuse_links()` walks every part from the root with `os.lstat`. It also requires `realpath(root/rel) == root/rel`. It runs on each walked folder, each FIXED file and each selected file, and again at read time.
checked: tests `test_i1_symlinked_parent_of_a_fixed_file_refuses` (docs/user), `test_i1_symlinked_parent_of_a_walked_folder_refuses` (scripts/examples) and `test_i1_symlinked_data_folder_refuses`. All three were red, and now pass.
verdict: holds
confidence: high

claim: I-2 fixed. Private folder names are denied at any depth.
referent: `scan_release_zip.PRIVATE_PARTS`:
- `.superpowers`, `.worktrees`, `tmp`, `runs`, `Saves`, `saves`, `adjudication`, `research`
- patterns `kp-live*`, `kp-release*`, `kp-runs*`

`deny_reason` checks them on every folder part. Example and scenario folders must also be flat.
checked: `test_i2_private_folder_names_are_denied_at_any_depth` (9 paths) and `test_i2_example_and_scenario_folders_must_be_flat`.
verdict: holds
confidence: high

claim: I-3 fixed. Every packaged file must be strict UTF-8 with no NUL byte and no media, archive, executable or retail magic. The privacy markers are expanded.
referent: `scan_release_zip.content_problems`, `magic_kind` (with a BioWare `XXXXV1.0` rule), `privacy_markers` and `path_scan`.
- The markers now include `/root/`, `C:\Users`, `kp-live`, `kp-release`, `.superpowers`, `MyBook`, `.worktrees`, `linuxbrew` and the run ID shape.
- They also include the user names from `$USER`, `$LOGNAME` and the `$HOME` basename at build time. User names match as whole words. Common names such as root or runner are skipped. Reports label a hit "user name" and never print the name.
- Non-UTF-8 bytes are now scanned as Latin-1 instead of being skipped.
checked:
- `test_i3_png_bytes_under_a_lua_name_refuse`
- `test_i3_utf16_text_refuses`
- `test_i3_magic_bytes_refuse_even_when_valid_utf8` (8 cases)
- `test_i3_privacy_markers_refuse` (9 cases)
- `test_i3_common_or_short_usernames_are_not_markers`
- the real-tree dry run: no new false positive
verdict: holds
confidence: high for the tested shapes. A format with no leading magic, such as TPC, relies on the suffix denylist plus the UTF-8 rule.

claim: I-4 fixed. Each file is read once, and provenance binds those bytes. The ZIP is built from the same bytes. The sources are re-read at the end.
referent: `read_source()` uses `O_NOFOLLOW` and checks `fstat`, then compares `lstat` inode identity after the read.
- `check_provenance(..., staged_raw)` hashes only the staged bytes. The git binding uses `git hash-object --stdin --path=` on the staged bytes.
- `_zip_bytes()` builds the ZIP in memory, and `verify_zip()` checks it.
- Every source is then re-read, and any change refuses the build with "nothing was written".
- Only after that is `out` created. The ZIP on disk is re-hashed against the verified bytes.
- A non-dry build refuses an existing `out`, or a missing `--out` or `--provenance`, before any work starts.
checked:
- `test_i4_edit_reverted_inside_the_window_refuses` (the race.py case, now `provenance mismatch`)
- `test_i4_source_changed_after_staging_refuses`
- `test_i4_zip_holds_exactly_the_bound_bytes`
- `test_existing_out_refuses_before_any_work`
- `test_files_equal_to_git_base_are_bound_without_overlay`, still green
verdict: holds
confidence: high

claim: M-1 and M-2 fixed. Hard links (`st_nlink != 1`) and unsafe names refuse the build. Unsafe names are backslash, control character, absolute or `..`.
referent: `read_source()`, `scan_release_zip.unsafe_name`.
checked: `test_m1_hard_link_to_an_outside_file_refuses`, `test_m2_backslash_in_a_name_refuses`.
verdict: holds
confidence: high

claim: M-3 fixed. For ffmpeg and ffprobe, an ELF is `ok` only when `-version` names the tool. Otherwise the status is `not_the_tool`, which blocks the run.
referent: `creative_host_check.version_banner`. It runs `[resolved, '-version']` with a 10 s timeout, a fixed small env and no stdin. Nothing else is started.
checked:
- tests `test_m3_*` (3)
- `ffmpeg` symlinked to `/usr/bin/env`: `{"status": "not_the_tool", "blocking": true}`
- host with `--path /usr/bin:/bin`: `ok=true`, with `"version": "ffmpeg version 8.1.2"` and `"ffprobe version 8.1.2"`
verdict: holds
confidence: high

claim: M-4 fixed. The claim is softened, and a route inside the runs folder is refused.
referent: the `commit_inputs.py` docstring now says it is a procedural safeguard. It says the line is not chained or signed, the time is self-reported, and acceptance and export do not read the log. A realpath check refuses a route under `runs_dir`, including through a symlinked runs folder.
checked: `test_m4_route_inside_runs_dir_is_refused`
verdict: holds
confidence: high

claim: M-5 fixed. The guide and the host check agree on one rule: use the distribution FFmpeg, never a wrapper.
referent: host `host-cmd` run:
- `/usr/bin/ffmpeg` and `/usr/bin/ffprobe` are ELF from `ffmpeg-8.1.2-3.fc44`, and report version 8.1.2.
- The brew `ffmpeg` and `ffprobe` are ELF 9.0.1 symlinks into the Cellar.
- `~/.local/bin/ffmpeg` and `~/.local/bin/ffprobe` are the PATH-first wrappers.

`elf_elsewhere` now prefers `/usr/bin`, `/bin` and `/usr/local/bin`. The default-PATH host run printed `"elf_elsewhere": "/usr/bin/ffmpeg"` and `"/usr/bin/ffprobe"`; before, it pointed at brew. The guide now says:
- use the distribution package
- check it with `file -L` and `-version`
- treat `elf_elsewhere` as a hint

The guide never names the brew path, because the guide is packaged and scanned.
checked: `test_m5_elf_elsewhere_prefers_a_system_folder`, the host runs, and a self-scan of the edited guide (0 hits).
verdict: holds
confidence: high

claim: M-6, M-7 and M-9 fixed.
referent:
- M-6: the status box and the Run section now say the release ZIP DLLs have not been used in a creative run.
- M-7: the two comma-list cells are split into one row each. A grep for comma table cells finds none, and the buzzword grep gives rc=1.
- M-9: `commit_inputs` rewords the shared validator's message to "inputs log".
checked: `test_m9_log_refusals_name_the_inputs_log` (missing and outside).
verdict: holds
confidence: high

claim: M-8 fixed. `ok` is false, and `main` exits 1, when the FFprobe used to re-probe differs from the one bound at acceptance.
referent: `export_verify.verify_export` sets `ok` to `same_ffprobe` and adds `error`.
checked: `test_m8_other_ffprobe_program_makes_ok_false`
verdict: holds
confidence: high

### Release ZIP scan (read-only)

Command: `python3 tools/scan_release_zip.py --allow '*.dll' --allow source.tar.gz <zip>`. The scan reads the ZIP bytes once and checks nested tar and zip members in memory.

Size, mtime and SHA-256 are equal before and after the scan (`fixround/zips-before.txt` and `fixround/zips-after.txt`):
- `0388d080…67c9` for the 0927 ZIP
- `de14c126…7131` for the 0922 ZIP

Both ZIPs: `ok=false`. The findings below are real and were not softened.

- `kphasor.dll`: 11 embedded absolute build paths hold the user's home folder and user name. Example: `/home/<user>/kp-release-2026092x/source/…/third_party/imgui/imgui.cpp`. These are ImGui `__FILE__` or assert strings.
- `packaging-receipt.json`: lines 4–8 list `.superpowers/sdd/lua-boundary-validation-plan/*.md` paths, which are private report names.
- `source.tar.gz!source/data/research/phasor_structs.json` (149018 bytes): a `data/research` file ships inside the source tarball. Spec §2 excludes `data/research/`.
- `source.tar.gz!source/data/events.draft.toml:5`: a comment holds `/home/<user>/biodecompwarehouse/kotorxid/output/kotor_readable/`.
- `source.tar.gz!source/third_party/luajit/src/host/minilua`: a 139392-byte ELF build product inside the source tarball.
- 0922 ZIP only: `live-acceptance.json:10` has `run_directory` `/home/<user>/kp-live-20260922/stage-k1/runs/20260926-234927`. The 0927 ZIP does not have this hit.

Low risk, reported for completeness:
- `source.tar.gz!source/.gitignore:40` names `.worktrees`.
- `third_party/luajit/doc/install.html:165,189` is upstream example text (`/home/myself/lj2`).
- `third_party/luajit/doc/img/contact.png` is upstream documentation media.

Expected under the allow-list: the two PE DLLs and the gzip `source.tar.gz`.

claim: both published-candidate release ZIPs hold the local user name and home path, a private `data/research` file, and private report names.
referent: `fixround/scan.json`, plus the string extraction above.
checked: `scan_release_zip.py`, run read-only. The ZIP hashes are unchanged.
verdict: holds
confidence: high. The release builder (`kp-release-20260927/package.py`) is outside this round's allowed files and was not changed.

### Fix round, second pass (the counts here replace the ones above)

- **Receipt leak (I-2 follow-up).** `packaging-receipt.json` copied the path of each excluded file. So a nested private folder still shipped its name inside the receipt.
  - Red test `test_i2_receipt_does_not_name_private_folders` failed, with `.superpowers` found in the receipt.
  - Fix: a private or marker-matching exclusion is now recorded as `<walked folder>/(name withheld)`. `deny_reason` no longer repeats the folder name.
  - Backstop: before zipping, `path_scan` runs over the generated `packaging-receipt.json`, `source-provenance.json` and `manifest.json`. The build refuses on any hit.
- **Run IDs.** The scan found `runs/20260926-234927` in the 0922 ZIP, a shape the first pattern missed. `RUN_ID` is now `\b\d{8}-\d{6}(?:-[0-9a-f]{8})?\b`, and a red assertion was added to `test_i3_privacy_markers_refuse`.
  - The real-tree dry run now finds one new hit: `scripts/harness/kpharness/oracle.py:246`, a comment that reads `# exact 20260910-095338 failure mode.`
  - That is a real run-folder name, not a false positive. `oracle.py` is committed (last commit `5cffd0f`) and outside this round's files, so it is left unchanged.
  - The real build now refuses on two lines: `capture_diagnostic.py:54` and `oracle.py:246`.
- **M-5.** `/usr/local/bin` was dropped from `SYSTEM_DIRS`. It holds local builds, not the distribution package.
- **Guide.** "an earlier build" now reads "a different build". The only referent is that the two hashes differ.
- **I-4 git binding on real files.** Command per file: `git hash-object <rel>` compared with `git hash-object --stdin --path=<rel> < <rel>`. Both forms were equal for all five files tested:

  | File | State | Hash |
  |---|---|---|
  | `LICENSE` | clean | `be3f7b28…`, equal to HEAD |
  | `data/app_signatures.toml` | clean | `c88e5f2c…`, equal to HEAD |
  | `scripts/examples/cursed/10_rancor_roulette.lua` | clean | `f3583970…`, equal to HEAD |
  | `scripts/harness/kpharness/recording.py` | modified | `520f5bff…` |
  | `scripts/harness/kpharness/gamescope_snapshot.py` | untracked | `a6bedb9b…` |

  `git check-attr -a` printed no attributes and returned rc=0.
- **Reviewer probes rerun.** The copies are in `fixround/adversarial.py` and `fixround/race.py`, with output in `fixround/adversarial.out` and `fixround/race.out`.
  - 9 of 11 adversarial cases are REFUSED.
  - The other two are BUILT with nothing leaked: `case_variants` and `nested_private` (`leaked entries=[]`, `leaked bytes=[]`).
  - `race.py` now ends in `ValueError: provenance mismatch: scripts/examples/cursed/10_rancor.lua`.
- **Final counts**, the same in the container (Python 3.12.3) and on the host (Python 3.14.7):

  | Test file | Tests | Result |
  |---|---|---|
  | host check | 13 | OK |
  | commit_inputs | 12 | OK |
  | export_verify | 17 | OK |
  | package builder | 35 | OK |
  | **Total** | **77** | **OK** |

  Red first: 26 of 27 new tests failed before the fix. The one that passed, `test_i4_zip_holds_exactly_the_bound_bytes`, is a guard test.
- **Release ZIP rescan** with the broader run-ID pattern (`fixround/scan2.json`):
  - The ZIP hashes are still `0388d080…` and `de14c126…`, and size and mtime are unchanged.
  - New hits are run-folder names in source comments inside `source.tar.gz`: `oracle.py:246`, `k1_fresh_trask_quest.toml:141` (`tmp/k1_harness/runs/20260915-071620`), `engine_k1.cpp`, `kp_harnesstest.cpp:517`, and in the 0922 ZIP also `fields.hpp:356`.

### Resume verification (2026-09-27)

This continuation inspected the existing partial report, permitted-path mtimes, and
`review-probes-packaging/` before doing new work.  No source change was needed.

Focused unit-suite rerun (container Python 3.12.3, with
`PYTHONDONTWRITEBYTECODE=1`):

| Test file | Tests | Result |
|---|---:|---|
| `creative_host_check_test.py` | 13 | OK (0.766 s) |
| `kpharness_commit_inputs_test.py` | 12 | OK |
| `kpharness_export_verify_test.py` | 17 | OK |
| `package_creative_harness_test.py` | 35 | OK (15.361 s) |
| **Total** | **77** | **OK** |

The package test rerun includes all I-1 through I-4 and M-1, M-2 adversarial
coverage, plus `ReleaseZipScanTests`.  The input-commit, host-check, and export
reruns include M-3 through M-9 coverage listed above.

Release ZIP scan rerun (read-only):

```
python3 tools/scan_release_zip.py --allow '*.dll' --allow source.tar.gz \
  /home/brunner56/kp-release-20260927/kotorphasor-k1-k2-gog-console-preview.zip
python3 tools/scan_release_zip.py --allow '*.dll' --allow source.tar.gz \
  /home/brunner56/kp-release-20260922/kotorphasor-k1-gog-console-preview.zip
```

The 20260922 preview is in `kp-release-20260922` (not `kp-live-20260922`).
Both commands returned `ok=false`, `markers=16`, and `unchanged=true`:

- 20260927 K1/K2 GOG preview SHA-256:
  `0388d0806c74c0ad158f7d120165a5d530798c14fbbaa1674b8c6c759ce867c9`.
- 20260922 K1 GOG preview SHA-256:
  `de14c1261e0e1b0e0aec124c8676f8e40ec696b47a258d9e1b0adc97af677131`.

The findings reproduce the prior report: DLL `/home/` build-path markers,
private `.superpowers` receipt paths, `data/research` in the embedded source
tarball, source comments containing paths/run IDs, and the embedded `minilua`
ELF.  The 20260922 archive additionally contains the `live-acceptance.json`
home-path marker and `fields.hpp` run-ID marker.  This round does not authorize
changing either release builder or candidate archive; neither was modified.

## Publication-boundary hardening (2026-09-27, sole writer, host-only)

Inputs: `/home/brunner56/kp-live-20260922/release-zip-marker-triage.md` (M1 tar owners, F6, F10, M4) and
`/home/brunner56/kp-live-20260922/creative-packaging-rereview.md` (R-1..R-7, scanner too-narrow/too-broad list).
Orchestrator rulings applied: (1) run ID = `runs/<stamp>` or `<stamp>-<8 hex>` only; (2) private folders:
`data/research` (docs/research allowed), `tmp/` and `runs/` only at the repository root; (3)
`data/codecaves.toml` and `data/events.draft.toml` held back from every package.

Scope held: files edited were `tools/scan_release_zip.py`, `tools/package_creative_harness.py`,
`tools/package_creative_harness_test.py`, `tools/creative_host_check.py`, `tools/creative_host_check_test.py`
and this report. No git write, no game, no lock, and no ZIP or builder under `kp-release-*` was modified,
rebuilt or published (the two builders' mtimes are 00:17/23:50, before this session; ZIP sha256 and
size+mtime unchanged per scan). The proposed builder patch was written, not applied.

### Red first

- Host check: `test_r7_version_output_capture_is_bounded` failed before the fix with
  `AssertionError: 12.476524868048728 not less than 5.0` (unbounded capture until the 10 s timeout).
- Scanner and packager: 23 new tests plus the ruling-(2) edit of `test_i2_...`, run before any source
  change: `Ran 25 tests ... FAILED (failures=26, errors=5)` (subtests count separately). Every new test red.
- After the first scan of the real ZIPs, case-insensitive `/home/` hit ImGui's "PageDown/Home/End"
  comment (`imgui.cpp:13248, 13526`). Red test added to `test_r1_...` (failed with the `/home/` hit),
  then Linux path prefixes were made case-sensitive again.

### What changed

`tools/scan_release_zip.py`
- Tar members: `uname`/`gname` equal to the build user or a git identity, any other non-root account
  name, and nonzero uid/gid are `tar owner` findings (the name is never echoed). Pax headers are scanned.
- ZIP: entry names are marker-scanned; ZIP comment, entry comments, central and local extra fields and
  bytes before the first entry are scanned; Info-ZIP `0x7875` nonzero uid/gid is a `zip owner` finding.
- Encrypted entries are an `encrypted` finding (no `RuntimeError`); `main` prints JSON for any exception.
- Nested gzip/bzip2/xz/tar/zip are opened by magic (single gzip/xz/bzip2 streams are expanded and scanned);
  7z, RAR, zstd and other compressed suffixes are `unscanned archive`, which `--allow` never hides. A
  nested archive whose suffix names its format is scanned and its own magic is no longer a finding
  (triage R9(a)).
- Markers ignore case (R-1), except `/home/ /run/media/ /media/ /root/ /var/home/` (Linux paths are
  case-sensitive). `/media/` and `/Volumes/` added. Identity boundary is `[A-Za-z0-9]`, so `_` separates.
  Git `user.name`, `user.email` (and its local part) and `github.user` are read at scan time.
- Run ID narrowed per ruling (1). Private parts per ruling (2), case-insensitive (R-2). Held-back files
  per ruling (3) are `excluded file` findings.
- Magic: optional UTF-8 BOM skipped (R-6); full signatures at offset 0 with enough bytes (PE needs 64 bytes
  and a PE signature or header NULs; Bink needs a lowercase revision byte; ID3, bzip2, gzip, RIFF, DDS,
  RAR, xz, PDF tightened). `MZ = 1` and `KB2267602` no longer match. UTF-16LE strings in binaries scanned.
- Names: Windows device names, `<>:"|?*`, trailing dot/space, Unicode `Cf` characters (`unportable name`)
  and NFC/case-fold twins (`name collision`) (R-3).
- New `scan_bytes()` for in-memory use; the report gains `finding_counts`.

`tools/package_creative_harness.py`
- Mandatory final gate: `_scanner.scan_bytes()` on the exact ZIP bytes, no allow globs, before re-read and
  before anything is written; `verification.json` records `release_scan: PASS`.
- `deny_reason` holds back `data/codecaves.toml` and `data/events.draft.toml`; `runs/` joins the root
  private prefixes; prefix and private-name checks ignore case, so case variants are withheld from the
  receipt (R-2); unportable exclusion names are withheld too.
- `name_problems()` refuses unportable names and NFC/case twins among selected files (R-3).
- `st_nlink == 0` reports "replaced while reading" (R-4).
- The whole `scripts/harness/kpharness` tree is link-checked before the closure is parsed; `SyntaxError`
  becomes a JSON error (R-5).

`tools/creative_host_check.py`: `-version` runs through `Popen` with a selector loop that reads at most
64 KiB before the 10 s deadline, then kills (R-7). Tests now mock `H._run_version`.

### Tests (all four files, container Python 3.12.3 and host Python 3.14.7 via host-cmd)

| Test file | Container | Host |
|---|---|---|
| `tools/package_creative_harness_test.py` | `Ran 58 tests in 81.856s OK` | `Ran 58 tests in 49.943s OK` |
| `tools/creative_host_check_test.py` | `Ran 15 tests in 0.154s OK` | `Ran 15 tests in 0.195s OK` |
| `tools/kpharness_commit_inputs_test.py` | `Ran 12 tests in 0.084s OK` | `Ran 12 tests in 0.020s OK` |
| `tools/kpharness_export_verify_test.py` | `Ran 17 tests in 2.575s OK` | `Ran 17 tests in 0.121s OK` |
| **Total** | **102 OK** | **102 OK** |

(The package test count rose from 35 to 58; the host check from 13 to 15.) Those runs came before the
`/home/` case fix. A full rerun of all four files after the fix was green in both places: container 58/15/12/17
(`166.181s`, `0.510s`, `0.190s`, `0.495s`), host 58/15/12/17 (`150.952s`, `1.646s`, `0.025s`, `0.355s`),
102 OK each.

### Release ZIP scans (read-only, updated scanner, `--allow '*.dll'`)

| ZIP | sha256 | entries | findings (host) | findings (container) | tar owner | unchanged |
|---|---|---|---|---|---|---|
| `kp-release-20260927/kotorphasor-k1-k2-gog-console-preview.zip` | `0388d080…67c9` | 18 | 632 | 632 | 606 | true |
| `kp-release-20260922/kotorphasor-k1-gog-console-preview.zip` | `de14c126…7131` | 17 | 633 | 633 | 606 | true |

`finding_counts` 0927: `tar owner 606, marker 19, excluded file 2, magic 2, private folder 1, not UTF-8 1,
NUL byte 1`; 0922 has `marker 20` (plus `live-acceptance.json:10`). Every tar owner finding reads
`uname is the build user; gname is the build user; uid 1000 gid 1000 (nonzero)`. Expected (allowed): the two
DLLs' `pe/dos` magic. Versus the triage's 28/30: new are 606 tar owners (M1) and 2 excluded files (ruling 3).
Removed are the bare run IDs (4 in 0927 and 5 in 0922, per ruling 1) and the `source.tar.gz` gzip magic
(R9(a)). Still reported: DLL `/home/` ×9, receipt `.superpowers` ×5, `.gitignore:40`,
`events.draft.toml:5`, `phasor_structs.json`, `k1_fresh_trask_quest.toml:141` (runs/ shape), LuaJIT
`contact.png` and `install.html` ×2, and `minilua` ×3.

### Proposed builder patch (not applied)

`/home/brunner56/kp-live-20260922/release-builder-proposed.patch` (6 files, 9 hunks, `patch -p1 --dry-run`
OK against a /tmp copy). For 0927 `package.py`:
- scanner gate on a `*.zip.unscanned` holding name, with 5 reviewed exceptions;
- blank tar owner fields, uid/gid 0, a fixed mtime and a gzip header with no file name;
- minilua, codecaves and events.draft excluded, with a program-magic assert;
- private exclusion names counted and hashed in the receipt instead of listed.

For the CMake compile lines: `-ffile-prefix-map=${CMAKE_SOURCE_DIR}=. -ffile-prefix-map=${CMAKE_BINARY_DIR}=build
-fmacro-prefix-map=${CMAKE_SOURCE_DIR}=. -DNDEBUG` on the five MinGW compile lines, and `-s` on the two
DLL links. The patch header carries the 0922 note: the CMake files are identical per `cmp`, and the
`package.py` line map is included.

Trial of the patched `package.py` on a /tmp copy of the 0927 inputs, with the existing DLLs (not rebuilt):
- exit 1; the ZIP was held as `*.zip.unscanned`;
- the gate blocked on exactly 10 findings: kphasor.dll `/home/` ×9, which needs the CMake rebuild, and
  `k1_fresh_trask_quest.toml:141` run ID;
- the tar has 603 members, all `('', '', 0, 0)` with mtime 1790467200;
- the receipt lists 175 exclusions and withholds 15.

### Real-tree dry run (host, after the changes)

`ok True, selected 60, closure 32, content_refusals []`. There are two path-scan hits, and both are content
that other writers changed today, not new rules:
- `docs/creative-runner.md:479` has a literal `/home/<user>/kp-live-20260922/r12-calibration/` path (file
  mtime 14:22).
- `capture_diagnostic.py:73` is the known `DEFAULT_FFPROBE='/home/linuxbrew/…'`, which moved from line 54
  (file mtime 14:19).

`oracle.py:246` (a bare stamp) no longer hits, per ruling 1. A real build would refuse on those two lines
before the gate is reached.

### Grill me

1. **Is `-DNDEBUG` safe to ship? (weakest)** Unverified. The orchestrator asked for it, but the triage R1
   warned that it turns off live ImGui asserts and the project's own `assert()`
   (`src/api/structs.cpp` and `src/hooks/trampoline.hpp` use it; `grep -rlw assert`). The prefix maps alone
   remove `__FILE__` paths. No rebuild was run here, so "the DLL has 0 `/home/` hits after the patch" is
   also unverified. The patch header marks it as an owner decision.
2. **Does ruling (2) weaken the packager?** Nested `tmp/`, `runs/` and `research/` are no longer
   *private*. In the creative package they are still left out, by the flat-folder and closure rules:
   `test_i2_private_folder_names_are_denied_at_any_depth` builds with `cursed/tmp/n.lua`, `cursed/runs/n.lua`
   and `kpharness/tmp/n.py` planted, and `leaked == []`. The receipt now names such paths, which is what the
   ruling asks for.
3. **Why are `/home/` and the other Linux prefixes case-sensitive when R-1 asked for IGNORECASE?**
   `imgui.cpp:13248` and `:13526` ("PageDown/Home/End") became false positives. Linux paths are
   case-sensitive, so `/Home/` names no home folder. The macOS and Windows paths, workspace names and
   identities stay case-insensitive (`test_r1_markers_ignore_case_and_treat_underscore_as_a_boundary`).
4. **Does reducing MZ/KB false positives let a binary through the packager?** No. A real PE carries NUL
   bytes, and the packager requires strict UTF-8 with no NUL. `test_i3_magic_bytes_refuse_even_when_valid_utf8`
   now uses a real DOS header. A 64+ byte `MZ` text with no NUL and no PE signature is not flagged as
   magic. Such a file is not an executable.
5. **Is a tar-owner finding per member (606) the right granularity?** It counts every leaking header, which
   the brief asked for. The cost is report length. `finding_counts` summarises it.

Open question I could not settle: does the patched CMake build produce a `kphasor.dll` with zero `/home/`
strings, and does `-DNDEBUG` change live behaviour? One check settles it. In a fresh /tmp copy, apply the
patch, run `build-reviewed.py`'s cmake commands, then run
`scan_release_zip.py --allow '*.dll'` on the resulting package. A live run would also be needed for the
behaviour half. Both are outside this round (no rebuild, no game).

## Publication-boundary follow-up (2026-09-27, sole writer)

Inputs: `scanner-hardening-review.md` (PASS, with P-1, P-2 and S-1 to S-7) and `release-rebuild-verify.md`
(prefix maps and `-s` remove every `/home` path; the scanner has no `/tmp/` marker; the patch note about
project asserts is wrong). Evidence: `/home/brunner56/kp-live-20260922/boundary-followup/`.

Scope held:
- No git write.
- Nothing under `kp-release-*` was modified, rebuilt or published. The tree fingerprint (`find -printf '%P %s
  %T@ %m'`, sha256) is identical before and after (`baseline/release-trees.before` = `scans/release-trees.after`).
  `find -newermt '2026-09-27 18:00'` on both folders gives 0.
- No game was run, and the live-game lock was not touched.
- `/tmp/kpf-*` scratch was removed.
- Another session ran tests in this worktree during this round: new `.pyc` files appeared for
  `kpharness_gamescope_backend_test` and `kpharness_capture_diagnostic_test`. I did not run those, and I left
  the files alone.

Files:
- `tools/scan_release_zip.py` (sha256 `65f01e51…13ba`)
- `tools/package_creative_harness_test.py`: new `FollowupScanTests` (15 tests) and the `hand_zip` helper. This
  is the only existing home of the scanner tests, so no new file was added.
- `/home/brunner56/kp-live-20260922/release-builder-proposed.patch` (sha256 `cf7a9844…c1b`)
- `tools/package_creative_harness.py` was not changed. Its mtime is 14:20:49, before this round, and
  `name_collisions(names)` still takes one argument.

### Red, then green

`tests/red.out`: the 15 new tests against the original scanner give `FAILED (failures=32, errors=2)`, and 14 of
15 tests fail. The one that passes is the false-positive guard `test_s3_data_descriptors_are_covered_not_flagged`.
The advisor then found that a shell default such as `${ROOT:-/tmp/x}` was missed. The path-start lookbehind
counted `-` as a path character. The red step is `tests/red-default-value.out` (2 subtests fail). I removed
`-` from the class, and the whole table below was rerun (`rerun/`).

| Suite | Container (Py 3.12.3) | Host via `host-cmd` (Py 3.14.7) |
|---|---|---|
| `package_creative_harness_test.py` | `Ran 73 tests … OK` (58 + 15) | `Ran 73 tests … OK` |
| `creative_host_check_test.py` | `Ran 15 tests … OK` | `Ran 15 tests … OK` |
| `kpharness_commit_inputs_test.py` | `Ran 12 tests … OK` | `Ran 12 tests … OK` |
| `kpharness_export_verify_test.py` | `Ran 17 tests … OK` | `Ran 17 tests … OK` |
| **Total** | **117 OK, rc=0** | **117 OK, rc=0** |

### Scanner changes

- **`/tmp/` and `/var/tmp/`.**
  - Both are `FIXED_MARKERS`, case-sensitive like the other Linux prefixes.
  - They count only at the start of a path, so `scripts/tmp/x` is not one, and `/var/tmp/` does not also fire `/tmp/`.
  - Criterion: the name right after them passes only when it is fixed, is the same on every machine and run, and holds no build tree or run output.
  - That covers `.X11-unix`, `.ICE-unix`, `.XIM-unix`, `.font-unix`, `.X<n>-lock` and `.tX<n>-lock`, plus the harness's own write-probe file `.kp_harness_write_probe[.<pid>|.$$|.{…}]`, as a file only.
  - `.kp_harness_write_probe/…`, `.X11-unixfoo` and `.X0-lock/x` are flagged.
  - Tests: `test_tmp_and_var_tmp_are_markers`, `test_tmp_marker_spares_relative_folders_and_fixed_system_names`, `test_tmp_markers_are_fixed_markers_not_identities`.
  - The real creative closure's dry run (`tests/creative-dryrun.json`) gives `path_scan []`.
  - The exemptions hold on real shipped code as well as the synthetic tests. The 0927 `source/` ships these
    exempt `/tmp` names, and none of them is among the new findings:
    - `session.py:155,181,262,264,999`
    - `harness_paths.sh:31,35`
    - `gameplay_tests/README.md:6`
    - `kpharness_offline_test.py:2175`
  - Not caught: `/tmp/` directly after a letter, such as `-I/tmp/x`. A letter there cannot be told apart
    from a relative path such as `scripts/tmp/`. `-`, `=`, `:`, quotes, spaces and NUL before it do count.
- **S-1.** `wide_scan` runs whenever NUL bytes are present. Test: `test_s1_…`, with a UTF-8-valid DLL, a `.dat` and UTF-16BE.
- **S-2.** Identities come from:
  - `git config --get-all` for `user.name`, `user.email` and `github.user`, across every scope
  - the owner parsed from `git remote get-url origin` (`owner_from_url`: https, `ssh://`, scp-like)
  - `GENERIC_IDENTITIES`, an allow-list of names never treated as identities (Copilot, GitHub, `github-actions[bot]`, dependabot and similar)

  Here that gives 6 git identities and 26 markers, against 21 before. `Copilot` is not a marker. Tests: `test_s2_…` ×3.
- **S-3.** A new `uncovered bytes` finding covers:
  - ZIP gaps between records
  - bytes after the end record
  - deflate slack after the stream end
  - nonzero bytes after a tar's end

  Coverage accounts for data descriptors (with and without a signature, and zip64 widths) and for zip64 end records. Nested `.tar.gz`, `.tar.bz2` and `.tar.xz` are now expanded first, so the tar end can be checked. Labels are unchanged. Tests: `test_s3_…` ×3, including a streamed zip64 ZIP that must stay clean.
- **S-4.** Names are scanned from `orig_filename`: a NUL is reported, and the tail is marker-checked.
- **S-5.** A lone top folder named `data`, `tmp` or `runs` is the root, not a wrapper.
- **S-6.** Owners are read from `0x7855`, `0x5855` and `0x000d` (u16 uid/gid, local copy only).
- **S-7.** Exact duplicates and file-vs-folder clashes are now caught, in both ZIP and tar.

### Release ZIPs, read-only rescan (`scans/`)

| ZIP | before | after (container = host, identical findings) | delta | sha, size, mtime |
|---|---|---|---|---|
| 20260927 | 632 (marker 19) | **643** (marker 30), markers 26 | +11 `/tmp/`, 0 removed | unchanged |
| 20260922 | 633 (marker 20) | **644** (marker 31), markers 26 | +11 `/tmp/`, 0 removed | unchanged |

The rerun after the `:-` fix gives identical findings: host equals container, and both equal the pre-fix
scan. No shipped 0927 line has the `-/tmp/` shape (`grep -rnE -- '-/(var/)?tmp/' source` is empty).

- The same 11 lines are new in both ZIPs, all in `source.tar.gz`:
  - `.gitignore:12,29`
  - `harness_paths.sh:43`
  - LuaJIT `install.html:568`, `lib_os.c:86`, `lj_trace.c:92,113`
  - `kp_hooktool.cpp:678,679`
  - `kp_namespacetest.cpp:140`
  - `evidence_test.py:73`
- None of them names a user or a build tree. S-1 and S-3 to S-7 add 0 findings on the real ZIPs.

### Patch changes (P-1, P-2 and the note)

- **P-1.** `grep -c '^+.*-DNDEBUG'` gives **0**, with 5 prefix-map lines and 2 `-s` link lines kept.
- **P-2.** Three changes:
  - A top-level `if not __debug__: raise SystemExit(…)` guard, because all 17 pre-existing acceptance checks in `package.py` are asserts.
  - The gate, the program-binary check and the ZIP-unchanged check use explicit `raise SystemExit`.
  - `+` lines now contain 0 assert statements.
- **Note corrected.**
  - There is no project runtime `assert()`. `trampoline.hpp:46` is a `static_assert`.
  - The rebuild result is cited: 18 → 0.
  - The unpatched `entity.cmake:90` and `support.cmake:110` sites are named.
- **Proof on /tmp copies of the 0927 inputs** (`patch-proof/`):
  - `patch -p1 --dry-run`: 6 files, rc=0.
  - Old patch with `python3 -O`: **rc=0, and the release-named ZIP was written** past a failing gate. This reproduces P-2.
  - New patch with `-O`: rc=1 at the guard, nothing written.
  - New patch with the guard line deleted, with `-O`: rc=1 at the gate, only `*.zip.unscanned`.
  - New patch, normal run: rc=1. There are 26 gate findings, 5 of 5 `ACCEPTED` keys match, and it blocks on 21: 9 `kphasor.dll /home/`, 1 run id and the 11 `/tmp/` lines. The tar has 603 members, all `('', '', 0, 0)`.

### Grill me

1. **Is exempting `/tmp/.kp_harness_write_probe` a hole? (weakest)**
   - It is not an X11 path, so it goes beyond the X11 exemption asked for. It is a fixed file name, created and deleted by `session.py:217` to test that `/tmp` can be written. It holds no output.
   - Without the exemption, the creative closure's own source would make the package refuse to build.
   - The exemption is narrow. It covers the file only, with an optional pid, `$$` or `{…}` suffix, and a folder of that name is flagged (`test_tmp_marker_spares_…`).
   - The cost: a leaked `/tmp/.kp_harness_write_probe.123` passes, but it carries no user or run identity.
2. **Are 11 new release findings noise?**
   - Yes, in the sense that none leaks anything. That is the fail-closed price of a bare `/tmp/` marker.
   - A scanner cannot tell a code-chosen `/tmp/kp_selftest_*.json` from a leaked scratch root such as `/tmp/kp-rebuild-verify/…`, which is exactly what `release-rebuild-verify.md` showed passing unflagged.
   - The owner puts the 11 in `ACCEPTED` or fixes them in the repo. I did not add them.
3. **Does expanding `.tar.gz` before parsing change behaviour?**
   - Labels and the honest-suffix magic rule are unchanged.
   - Both ZIPs keep all 606 tar-owner findings, and 0 findings were removed.
   - Expansion keeps the 1 GiB cap (`_expand`). An over-cap stream is now an `unreadable archive` rather than the old per-member size-limit finding. Both fail closed.
4. **Could S-3 flag a legit ZIP writer?**
   - Checked: Python streamed output with data descriptors, including the zip64 variant (`test_s3_data_descriptors_…`), and both real ZIPs (0 `uncovered bytes`).
   - Unverified: `zip -fd`, 7-Zip and Windows Explorer outputs. A >65535-entry zip64 end record is coded but untested.
5. **Why is `GENERIC_IDENTITIES` an allow-list and not config-driven?**
   - It is small and static, and tested. It removes names that are public tools, not people.
   - No explicit `KP_PRIVATE_IDENTITIES` env var was added. The review suggested one, and the brief's list is git config plus the remote owner. The report also does not print which identities loaded.

Checked after writing: a wrapper-less ZIP rooted at a repo folder still guesses a wrapper. `scan_bytes` on
`['scripts/tmp/a.lua']` and on `['src/runs/x.md']` both report `private folder`. That is a false positive, and
it fails closed. The real ZIPs always have the `kotorphasor-preview/` wrapper, so they are unaffected. Only
`data`, `tmp` and `runs` were exempted, as the brief asked.
Open question for the next reviewer: should `NOT_WRAPPER_PARTS` also hold the repo's other top folders
(`scripts`, `src`, `docs`, `tools`, `third_party`)? One check settles it: list the top folders of every ZIP
the project builds, and confirm that none uses one of those names as a wrapper.
Seen during the round, not mine: the dirty worktree's `docs/creative-runner.md:479` held a
`/home/<user>/kp-live-…` path, which both scanners flagged. Another session rewrote that file at 18:46, and it
now has 0 `/home/`, so the creative dry run is clean.
