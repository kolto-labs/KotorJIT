# Nits pass, 2026-09-27

Two queued nit batches from the platform-m0m1 and scanner-hardening follow-up
reviews. No git writes. No game/Wine. Live-game lock untouched.
`TMPDIR=/home/brunner56/kp-live-20260922/tmp-nits` (host /tmp quota full).
This report was revised once after an advisor pass; the changes from that
pass are folded in below rather than kept as a separate addendum.

## Batch A: x64 detour nits (src/hooks/x64/*, tools/kp_hooktool_x64.cpp)

Source: `/home/brunner56/kp-live-20260922/platform-m0m1-followup-review.md`.

**(a) TOCTOU clause at the header.** `src/hooks/x64/trampoline.hpp:88` said
only "Not thread-safe: install/uninstall assume nothing else is executing the
patched bytes" — no mention that another thread unmapping the target during a
patch is out of contract. First draft of the added clause said "install/
uninstall read /proc/self/maps, then later read/write the described bytes" —
that overstated it. Checked directly:
`grep -n "HookStatus Detour::uninstall" -A20 src/hooks/x64/trampoline.cpp`
shows `uninstall()` never calls `code_window()`/`page_prot()`; it `memcmp`s
`target_` directly against the recorded patch bytes and calls `write_code()`
with the protection recorded at install (`prot_`), never re-reading
`/proc/self/maps`. Only `install()` reads maps. Reworded: install reads maps
and only then reads/writes the target bytes it described; uninstall never
reads maps again, it writes to the mapping recorded at install. Either one
racing a concurrent unmap/remap of the target is out of contract, can fault
instead of returning `Unreadable`.

**(b) Unreadable vs DecodeFailed mislabel (grill #2).** The review's referent:
a 17-byte over-length instruction (10x `0x66` + `8b 84 00` + disp32) sitting
entirely on 20 readable bytes, followed by a guard page, was reported as
`Unreadable` ("target page is unmapped or not readable") instead of
`DecodeFailed` ("instruction longer than 15 bytes"). Root cause:
`decode.cpp` had the `avail >= kMaxInsnLen ? "instruction longer than 15
bytes" : "truncated"` distinction at only two of eleven `refuse(...)` sites
(the legacy-prefix loop and the trailing immediate check); the other nine —
including the ModRM/SIB/disp32 path at the old line 229 and the REX path at
the old line 132 (now 144), both named by the review — returned a bare
`"truncated"`. `trampoline.cpp:395` then treats any `DecodeFailed` with
detail `"truncated"` next to a window cut short by a guard page as "the
window did it" and relabels it `Unreadable`.

Red first: added `tools/kp_hooktool_x64.cpp:
"grill#2: an over-length instruction inside the readable window is
DecodeFailed, not Unreadable"` reproducing the review's exact byte pattern
and page layout. Ran red (confirmed `Unreadable`, not `DecodeFailed` —
selftest 1 of 655 FAILED). Fix: factored a `too_long()` lambda in
`decode.cpp` and routed all nine remaining bare `refuse("truncated")` sites
through it. Ran green (655/655).

Why the uniform fix is correct at every site, not just the one the probe
hit, by construction rather than by assertion: `too_long()` closes over
`avail`, which is fixed for the whole call to `decode()` — it does not
change as `at` advances. `too_long()` returns `"instruction longer than 15
bytes"` exactly when `avail >= kMaxInsnLen (15)`, i.e. `limit == 15`. Any
refusal that hits `limit` under that condition means decoding needed more
than 15 bytes while the caller had offered at least 15 readable ones — which
can only be a genuine over-length instruction, never a short window, because
a short window requires `avail < 15` by definition. So the two cases are
mutually exclusive by the `avail >= kMaxInsnLen` test itself, at every call
site, not merely at the two the review had already fixed.

I also checked this isn't hypothetical for the REX site specifically (the
review's second citation, `:132`/now `:144`), which is reachable only if
`at` is already near 15 before the REX byte — i.e. many legacy prefixes were
consumed first. Added a second red-then-green case,
`"grill#2 REX path: prefixes + REX alone overrun 15 bytes -> DecodeFailed,
not Unreadable"` (14x `0x66` + `0x48`, same 20-readable-then-guard-page
layout). Then isolated that one site with a matched pair, same build
pipeline both times: copied just the four x64 hook-engine files into
`$TMPDIR/rex-light/`, compiled standalone
(`g++ -std=c++20 -Isrc -fcf-protection=none -no-pie decode.cpp
trampoline.cpp kp_hooktool_x64.cpp`). With only line 144 reverted to a bare
`refuse("truncated")`: `1 of 656 checks FAILED` — exactly the two new
REX-path checks, nothing else. With line 144 restored to `too_long()` (the
same standalone build, otherwise identical): `PASS 656 checks`. Both numbers
are from the standalone binary, not mixed with the CMake build's count, so
the red/green pair is apples-to-apples. This proves the `:132`/`:144` site
is independently load-bearing, not redundant with `:229`.

**(c) Stale m8 referent.** The review's verdict also named this as a nit to
carry: "the out-of-date m8 referent (:413 cannot be reached)" — the
`page_prot` loop's `NotExecutable` check at `trampoline.cpp:413` is dead
code from the caller's perspective since `code_window()` (around line 103)
already refuses a non-exec target page earlier, before `install()` gets this
far; the review confirmed by deleting :413 and re-running the selftest
unchanged. Added a comment at that site saying so, so the next reader does
not think this line is what's under test. No behavior change; selftest
still `PASS 656` after the edit.

### Validation

- x64 selftest (fresh `cmake -G Ninja RelWithDebInfo`, build dir under
  `$TMPDIR/build-nits-a`, targets `kp_hooktool_x64 kp_machotest kp_imagetool`
  only — the full `-m32` luajit copy is not needed and was skipped per the
  review's note about it hanging):
  - Baseline (before any edit): `PASS 654 checks`, rc 0 — matches the prior
    baseline exactly.
  - Red (ModRM/SIB test added, fix not yet applied): `1 of 655 checks
    FAILED`.
  - Green (fix applied): `PASS 655 checks`, rc 0.
  - After adding the REX-path test on top: `PASS 656 checks`, rc 0.
  - Isolated revert of just the REX-path site (`$TMPDIR/rex-light`, standalone
    compile): `1 of 656 checks FAILED` — only the REX-path checks. Same
    standalone build with that one line restored: `PASS 656 checks`.
  - After the m8-referent comment (item c, no behavior change): `PASS 656
    checks`, rc 0.
- `ctest -R "kp_machotest|kp_imagetool_macho_test|kp_hooktool_x64"` (via
  `host-cmd ctest`, since the container has no `ctest` binary of its own):
  `100% tests passed, 0 tests failed out of 3` before and after, and again
  after the REX-path addition (`kp_machotest`, `kp_imagetool_macho_test`,
  `kp_hooktool_x64.selftest`).

Files touched: `src/hooks/x64/trampoline.hpp` (header clause, reworded after
the advisor pass), `src/hooks/x64/decode.cpp` (the `too_long()` fix),
`src/hooks/x64/trampoline.cpp` (comment only, item c), `tools/kp_hooktool_x64.cpp`
(two new red-then-green tests: ModRM/SIB path and REX path). Nothing else
under `src/hooks/x64/*` changed.

## Batch B: release scanner nits (tools/scan_release_zip.py, its test file, the proposed patch)

Sources: `/home/brunner56/kp-live-20260922/scanner-hardening-review.md` (S-5),
`.superpowers/sdd/lua-boundary-validation-plan/progress.md:286` (the ledger
line naming both items: "Queued minor: wrapper-folder list
(scripts/src/docs/tools/third_party)" and "RULING: accept the 11 new /tmp
findings per ZIP as non-private ... → add to accepted list at next patch
edit"). I looked for a standalone write-up of the wrapper-folder nit beyond
that ledger line (`find boundary-followup -type f` = 64 files, none of them
a matching `.md`; `grep -rn -i "wrapper.folder"` across the review `.md`s
and `boundary-followup/` turns up only S-5's "data, tmp or runs" wording and
the S-5 test's own FAIL lines in `tests/red.out`) — the ledger line is the
only source for the five-name list; there is no separate report to
cross-check it against.

**(1) Wrapper-folder list nit.** `NOT_WRAPPER_PARTS` only knew `data` (plus
`tmp`/`runs` from `PRIVATE_ROOT_PARTS`) as "this lone top folder is the
repository root itself, not a synthetic wrapper" (S-5's fix). The repo has
five more real top-level directories — `docs`, `scripts`, `src`,
`third_party`, `tools` — that were still missing, so a ZIP shipping only one
of them (a component export) was misread as wrapped, shifting `root_depth`
by one and turning an ordinary nested `tmp/`/`runs/` subfolder into a false
"private folder" hit. Red first: added
`test_lone_scripts_src_docs_tools_third_party_folder_is_not_a_wrapper` to
`tools/package_creative_harness_test.py` (`FollowupScanTests`), parametrized
over the five names, plus a control case confirming a genuine synthetic
wrapper (`kotorphasor-preview/`) still correctly shifts root_depth. Ran red
(5 of 5 subtests failed, each a false "private folder" hit on
`<name>/tmp/a.lua`). Fix: added the five names to `NOT_WRAPPER_PARTS` in
`tools/scan_release_zip.py`, mirroring the existing `data` case exactly. Ran
green.

This fix has a real, checked cost, disclosed rather than fixed (see grill
#1, weakest answer in this batch): a wrapper folder that happens to be named
exactly `src`, `docs`, `scripts`, `tools` or `third_party` and that wraps a
*full* repo tree (including `data/` and `tmp/` nested one level inside it)
now loses detection of the private content nested inside it, because
`root_depth` is now computed as 0 instead of 1. This is not a new trade-off
I introduced from nothing — it is the exact same shape of trade-off S-5's
own `data` entry already accepted, extended in kind to five more names, and
verified against the same pre-existing behavior below.

**(2) Accept the 11 /tmp findings.** Backed up
`/home/brunner56/kp-live-20260922/release-builder-proposed.patch` to
`release-builder-proposed.patch.pre-nits` first, then edited the patch file
as text only (not applied to any tree). Added the exact 11
`(entry, kind, detail): reason` tuples the boundary-followup ruling named —
pulled from the rerun scan JSONs
(`boundary-followup/rerun/scan-container-kp-release-2026092{2,7}.json`),
identical set for both ZIPs:

  - `source/.gitignore` line 12 and line 29 (`/tmp/` rule and comment)
  - `source/scripts/harness/harness_paths.sh` line 43 (df/du hint)
  - `source/third_party/luajit/doc/install.html` line 568 (upstream DESTDIR example)
  - `source/third_party/luajit/src/lib_os.c` line 86 (upstream tmpnam fallback)
  - `source/third_party/luajit/src/lj_trace.c` lines 92 and 113 (upstream perf map path)
  - `source/tools/kp_hooktool.cpp` lines 678 and 679 (self-test scratch paths)
  - `source/tools/kp_namespacetest.cpp` line 140 (self-test scratch path)
  - `source/tools/tests/examples/evidence_test.py` line 73 (rejected-path test literal)

Each is the exact `(entry, kind, detail)` 3-tuple already keying `ACCEPTED`
in the patch (no globs), with a one-line reason citing the boundary-followup
ruling. Updated the enclosing hunk's `@@ -1,6 +1,22 @@` header to
`@@ -1,6 +1,33 @@` (11 new lines, old side unchanged) so the patch stays a
valid unified diff. Also updated the patch's own prose, which had gone
stale: the preamble said "5 reviewed exceptions" and the trial note said
"all 5 ACCEPTED keys matched, and it blocked on 21" with the 11 /tmp
findings still listed as pending an owner decision. Both now say 16 keys,
cite `progress.md:286`'s ruling, and the trial note's blocked-count (10 =
9 DLL `/home/` + 1 run id) is explicitly marked as derived from the
already-recorded 26-finding trial, not re-run.

### Validation

- Test suites, both container and host (`host-cmd python3 -m unittest`), same
  four modules the reviews used
  (`package_creative_harness_test creative_host_check_test
  kpharness_commit_inputs_test kpharness_export_verify_test`):
  **118/118 OK** in both environments (baseline 117, taken from the ledger/
  prior review counts, not re-measured on an unmodified tree this session,
  + the 1 new wrapper-folder test).
- `git apply --check -p1` of the edited patch, against a disposable scratch
  git repo (`git init` inside `$TMPDIR`, not the worktree — no worktree git
  write) seeded from the real external `package.py` and `source/` files at
  `/home/brunner56/kp-release-20260927/` (never touched in place): **rc 0**,
  clean apply on all 6 hunks, both before and after the prose-staleness
  edits (which sit outside any hunk).
- Rescanned both real release ZIPs read-only
  (`kotorphasor-k1-k2-gog-console-preview.zip`,
  `kotorphasor-k1-gog-console-preview.zip`) with the scanner as edited, and
  parsed `ACCEPTED` straight out of the edited patch text (regex-extract the
  `+ACCEPTED={...+}` block, strip the leading `+` per line, `ast.literal_eval`
  it — not a hand-retyped copy, so a typo in the patch would show up here):
  - Raw findings as a multiset (not just a count) are identical to the
    review's own `rerun/scan-container-kp-release-*.json`, both ZIPs — the
    scanner edit (item 1) moved nothing on the real ZIPs, because their real
    top folder (`kotorphasor-preview`) was never in `NOT_WRAPPER_PARTS`
    either way.
  - 16 of 16 `ACCEPTED` keys, parsed from the patch, are found in each ZIP's
    findings (mirrors the round-3 review's own "5 of 5" check).
  - Blocked count (findings not in `ACCEPTED`) drops from 638→627
    (20260927) and 639→628 (20260922) — exactly 11 per ZIP — and the dropped
    set is exactly the 11 new tuples, nothing else (set equality, not just
    count equality).
  - ZIP bytes unchanged: sha256 `0388d080…67c9` (20260927) and
    `de14c126…7131` (20260922) match the review's recorded values exactly —
    confirms read-only.
- Confirmed, by construction, that the wrapper-folder trade-off disclosed in
  item (1) is not new: a ZIP of `['data/data/codecaves.toml',
  'data/tmp/x.lua']` (a wrapper literally named `data`, the pre-existing S-5
  case) already produced `[]` (no findings) before any of this session's
  edits. A ZIP of `['src/data/codecaves.toml', 'src/tmp/x.lua']` also
  produces `[]` after this session's fix, and produced the two expected
  findings (`excluded file`, `private folder`) when `NOT_WRAPPER_PARTS` was
  simulated back to its pre-fix value. Same shape, same cost, now extended
  to five more names as the ledger asked.

Files touched: `tools/scan_release_zip.py` (`NOT_WRAPPER_PARTS`),
`tools/package_creative_harness_test.py` (new red test),
`/home/brunner56/kp-live-20260922/release-builder-proposed.patch` (11 new
`ACCEPTED` entries plus the two stale-prose fixes; not applied anywhere).
Backup at `release-builder-proposed.patch.pre-nits`.

## Counts summary

| Check | Before | After |
|---|---|---|
| x64 selftest | PASS 654 | PASS 656 (655 + REX-path test) |
| x64 ctest (3 targets) | 3/3 | 3/3 |
| scanner/packager tests (container) | 117 | 118 |
| scanner/packager tests (host) | 117 | 118 |
| 20260927 ZIP raw findings (multiset) | 643, identical to review's rerun | unchanged |
| 20260922 ZIP raw findings (multiset) | 644, identical to review's rerun | unchanged |
| 20260927 ZIP gate-blocked (simulated, parsed from patch) | 638 | 627 (−11) |
| 20260922 ZIP gate-blocked (simulated, parsed from patch) | 639 | 628 (−11) |
| `git apply --check` on edited patch | n/a | rc 0 |

## Grill me

1. **[Weakest] The wrapper-folder fix opens a false negative — did I just
   trade one nit for a worse one, and why these five names?** Checked
   directly, by construction: a ZIP of `['src/data/codecaves.toml',
   'src/tmp/private.log']` (a wrapper folder literally named `src`, wrapping
   a full repo tree) now scans clean — `Z.scan_bytes(...)['findings'] == []`
   — where before this fix it correctly flagged both (`excluded file` on the
   codecaves path, `private folder` on `tmp`). This is real and I'm not
   fixing it, because it is exactly the same shape of trade-off the
   pre-existing `data` entry in `NOT_WRAPPER_PARTS` already has (checked the
   same way: `['data/data/codecaves.toml', 'data/tmp/x.lua']` already scanned
   clean before I touched anything this session) — the ledger names these
   five ("scripts/src/docs/tools/third_party", `progress.md:286`) for parity
   with the existing `data` entry, not a redesign of wrapper-detection, and
   `ls -d */` on the repo root confirms they are exactly the five real
   top-level directories not already covered. If this trade-off is
   unacceptable, it was already unacceptable for `data` before this session.
   A discriminator that would actually close it, for both the old `data` case
   and the new five: `_root_depth` only reaches this check when every ZIP
   entry shares one top folder (so there is never a sibling top-level dir to
   compare against — a first idea of mine to check for a sibling doesn't
   work, since siblings can't exist here by construction); instead, checking
   whether that lone folder's *children* include other known repo names
   (`data`, `tmp`, `docs`, `scripts`, `src`, `tools`, `third_party`) would
   tell a genuine wrapper (one repo dir wrapping the whole tree) from the
   dir being the repo root itself. Correct, but a bigger change than either
   nit calls for — flagging, not fixing.

2. **Is the DecodeFailed/Unreadable fix load-bearing at both named sites
   (not just the one the probe hit), and why fix all nine `"truncated"`
   sites uniformly rather than just those two?** Holds for both named sites,
   checked two different ways: the ModRM/SIB site (old `:229`) by the
   original red/green cycle in the real tree; the REX site (old `:132`, now
   `:144`) by constructing a byte pattern that can only reach that site (14x
   prefix + REX, nothing else) and then, separately, reverting only that one
   line in an isolated standalone build (`$TMPDIR/rex-light`, same `g++`
   invocation both times) to prove it specifically — not just "the tree as a
   whole" — is necessary: `1 of 656 checks FAILED` with only that line
   reverted, `PASS 656` with it restored. Fixed the other seven sites
   uniformly rather than leaving them bare because `too_long()` is a pure
   function of `avail` (fixed per call, not `at`), so the same `avail >=
   kMaxInsnLen` test is correct at every site by the same argument (see Batch
   A body) — a consequence of `limit = min(avail, kMaxInsnLen)` being
   computed once at function entry, not an assumption. Did not hand-construct
   probes for the other seven individually, since the argument does not
   depend on which site is asking.

3. **Are the 11 accepted entries really the same 11 for both ZIPs?** Checked
   directly: pulled marker findings with `/tmp` in the detail from both
   `boundary-followup/rerun/scan-container-kp-release-20260927.json` and
   `...-20260922.json` — identical 11 `(entry, detail)` pairs in both,
   because both ZIPs wrap the same
   `kotorphasor-preview/source.tar.gz!source/...` tree. Re-confirmed this
   round by parsing `ACCEPTED` out of the patch itself (rather than a
   hand-typed copy) and checking 16-of-16 keys present in each ZIP's
   findings.

4. **Does editing the patch as text risk a hunk mismatch a fuzzy `git apply`
   might paper over?** Only checked against the exact external file this
   patch already targets (`/home/brunner56/kp-release-20260927/package.py`
   and its `source/` siblings), copied into a disposable scratch git repo —
   not against the 0922 copy, which the patch's own note says is
   byte-identical only for the CMake hunks and has no equivalent patched
   `package.py` hunk at all (out of scope per the patch's own "Note"
   section). Unverified for any third copy of `package.py` that might exist
   elsewhere.

**Hand-off.** The one question I could not settle: is the grill #1
trade-off (a lone `src`/`data`/etc. wrapper folder that wraps a *full* repo
tree loses private-content detection inside it) in scope for the release
gate at all, or is a real release ZIP guaranteed to never take that shape?
That's an owner call, not something I can settle by testing — the single
check that would settle it is whether any real or planned release/export
layout ever produces a ZIP whose sole top folder is one of these seven names
(`data`, `tmp`, `runs`, `docs`, `scripts`, `src`, `third_party`, `tools`)
while also containing a nested `data/` or `tmp/` of its own; if yes, the
children-based discriminator above is needed before this trade-off ships.

Grill me.
