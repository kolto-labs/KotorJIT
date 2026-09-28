# Resume: scanner refusal repair and nits verification

## Scanner finding and repair
The pre-fix scanner accepted archives rooted at data/docs/scripts/src/third_party/tools containing tmp/a.lua; a synthetic full-tree archive under each of the five newly exempted names also hid data/codecaves.toml. The control wrapper bundle was rejected. The new regression failed in six subtests before the product change.

A shared top directory is now a possible wrapper regardless of its spelling. Root-sensitive checks examine both depth zero and that possible wrapper depth. This preserves bare data/codecaves.toml and tmp/ refusals, and removes the folder-name exemption. Ambiguous component exports such as scripts/tmp/a.lua now fail closed; public files like scripts/guide.md remain accepted. A known wrapper's top/scripts/tmp/a.lua remains allowed by the existing test. No archive is published or rewritten.

Checked: python3 tools/package_creative_harness_test.py: 74 tests, OK (28.671s). Historical 118 was a combined suite including kpharness_export_verify_test, not the package suite alone. Independent review remains pending. The related kpharness_export_verify_test suite also passed 17 cases.

## Other nits
cmake --build /home/brunner56/kp-live-20260922/review-probes-nits/build-verify --target kp_hooktool_x64 -j 2: no work to do, configured to this worktree. Executed kp_hooktool_x64 selftest: PASS 656 checks. Existing decoder source/report reasoning checked; no x64 source edits in this wave.

The object-blaster mock previously asserted that dead-event registration succeeded. Aligned it with current dispatchability refusal and checked no callback was retained. luajit tools/tests/examples/object_blaster.lua: 17 cases, all checks passed. Runtime dead-event implementation is independently under review.

## Grill me
- Could stricter ambiguity handling reject a legitimate component archive? Yes: scripts/tmp/a.lua is indistinguishable from a wrapped repository-private tmp/a.lua without trusted root metadata. This change chooses refusal; the regression records that policy.
- Does this prove every release is safe? No. It closes the demonstrated root-name bypass; real publication and complete package admission remain separate gates.
- Are nested archives covered? ZIP and tar reuse the same root-sensitive helpers. A fresh probe of seven wrapper names inside nested tar archives rejected both private-folder and excluded-file paths; receipt: /home/brunner56/kp-live-20260922/resume-scanner-nested-results.json. Independent review remains pending.

## Current hashes
- tools/scan_release_zip.py: `3565767671b2e94ec370f5104cef9506a2d3e0ebc884167c7e764a79048cefbb`
- tools/package_creative_harness_test.py: `0598bd40815e4cb75657e56ecf4b4a17a75371d499509a7ced089636c7f4b8d3`
- tools/tests/examples/object_blaster.lua: `1edb16f749540296ea6ae323a5aa1620331bd17fe16c9957d2717dbeb4b2850e`
