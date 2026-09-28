# Release scanner independent review

Date: 2026-09-28. Read-only review of `tools/scan_release_zip.py` and its
package tests in the lua-boundary-validation worktree.

claim: a shared top-level folder can no longer hide root-sensitive private
paths or excluded files.

referent: `_root_depth()` at `tools/scan_release_zip.py:426-433` identifies a
possible one-folder wrapper, while `private_part()` and `excluded_file()` at
`305-331` check both depth zero and wrapper depth. Thus `scripts/tmp/a.lua`
is rejected under the component interpretation, and `top/scripts/tmp/a.lua`
continues to be checked under the wrapper interpretation.

checked: writer report's red bypass and current source; package suite
`python3 tools/package_creative_harness_test.py` completed `Ran 74 tests ... OK`.
The related export suite receipt is `/home/brunner56/kp-live-20260922/resume-scanner-nested-results.json`.

verdict: holds
confidence: high; the deliberate ambiguity policy is fail-closed.

claim: public component files remain accepted while ambiguous sensitive paths
are rejected.

referent: `tools/package_creative_harness_test.py:916-946` tests lone root
`tmp/`, `runs/`, excluded files, wrapped paths, and public `guide.md` across
component names.

checked: 74-test package suite passed; nested tar probe receipt was retained by
the writer.

verdict: holds
confidence: high.

claim: nested archive traversal applies the same root-sensitive checks.

referent: `_scan_nested()` delegates ZIP/tar and compressed tar streams back to
`_scan_zip`/`_scan_tar`; those compute `_root_depth()` and scan names again.

checked: writer's seven-wrapper nested tar receipt at
`/home/brunner56/kp-live-20260922/resume-scanner-nested-results.json`.

verdict: holds
confidence: medium-high; receipt is host-generated, with no publication.

## Verdict

**PASS.** The scanner fix closes the root-name bypass, preserves public files,
and fails closed on ambiguous `scripts/tmp` or equivalent component paths. The
74 package tests pass. No release publication or external write was performed.

Unsettled question: the full combined export verification remains an external
integration boundary; rerun its 17-case suite after the final integration diff.
