# Pioneer foundation independent review

**PASS — no actionable findings in the bounded attached-policy and authoring-transaction foundation.** This does not accept future playback/pause/rewind or live-game behavior.

Reviewed frozen task-pioneer-policy-report.md and scoped pioneer.py, Pioneer cli.py handlers/help, scenario.py attached execution helper, kpharness_pioneer_policy_test.py, and pioneer-authoring.md in the lua-boundary-validation worktree. Independently recomputed all five hashes and matched the frozen report.

The issued receipt is persisted before policy/step mutation. It binds exact original route bytes, normalized settings, rendered candidate, expected index, requested step and attached runtime/session identity. Exact rendered append is parsed before dispatch. Unresolved work cannot be overwritten; dispatch/restoration/identity/content failures remain issued and noncommittable even with force. Completed result hashes, status/index validation and stale/foreign rejection are coherent. Force only permits a completed failed result. PID/build/start/uptime detection is correctly documented as neither a native load epoch nor cryptographic attestation.

The committing journal precedes atomic route replacement; committed receipts remain available for retry. A failed route replacement retries from the original digest. Replacement followed by interrupted receipt completion is recognized by the exact candidate digest and does not append twice. Existing route bytes/comments/CRLF are retained. Advisory locks serialize cooperating commands. The stated limit concerning noncooperating external editors is accurate; hash checks are not filesystem compare-and-swap. Discard has no engine request and explicitly deletes metadata only.

Attached execution uses the existing ScenarioRunner.run_step, captures current kp.game_speed, explicitly applies route policy including1x, and restores the prior scalar in finally only while the same runtime and temporary value remain current. Restoration requires acknowledgment. Successful explicit speed commands retain their intended result even if equal to route policy; independent different values are preserved. Unknown/session-changed cleanup leaves issued uncertainty rather than blindly writing. Identical writes from another owner remain indistinguishable, as documented. Full managed-run1x opt-out remains intact.

Windows uses msvcrt byte-range locks with a nonempty lock byte and reset offset; Unix uses flock. Descriptors close on exit. Windows skips directory fsync but keeps file fsync/atomic replacement. Dedicated tests simulate these adapters; no actual Windows-host durability/execution claim is made.

Inspected tests exercise real temporary route/pending files and actual ScenarioRunner dispatch against a synthetic channel: policy/default/1x, explicit speed retention, uncertain restoration/session replacement, issued-before-dispatch, locking, malformed/stale provenance, target/render rejection, symlink refusal, atomic failure windows, duplicate retries, preserved bytes, CLI behavior and metadata-only discard. The author reports21 dedicated PASS,57 existing TestPioneer/TestScenario PASS, later7 Pioneer PASS, scoped py_compile and whitespace PASS. Reviewer did not rerun tests; these are offline results, not live evidence.

Matched source hashes:
- pioneer.py:99070d2cf16d5712bdc064c870b59c928ad5b62d8d4ca92404b2726b5eeb1230
- cli.py:371063fd6fd73b6a0e74879e1b94056ae566e3c4d293a9d71e14461dc8e1ad37
- scenario.py:70fd23042892700f9b7a266607737939533e781a888c6fb03a07fe62a93f580a
- kpharness_pioneer_policy_test.py:e39fcbe245e8153dd7f4c403147d5be5ecf8de521e8ba84cab4d92c0f4347120
- pioneer-authoring.md:a36fabfaee9b10cc8a9332ab0df3ec811d962d4270d05f04641f9b0b2011b26c

No source/index edits, builds or games. Only requested report output was written. /tmp output failed with disk quota, so this durable private path is authoritative. Persistent playback, native pause ownership, verified checkpoint restore and actual game/mod-state rollback remain separate work, not findings against this foundation.
