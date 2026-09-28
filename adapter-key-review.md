# Adapter key consumer independent review

PASS — no actionable findings in the scoped hookpack canonical-key change. Independently matched both frozen hashes supplied by controller.

Reviewed src/hooks/registry.cpp and tools/kp_hooktool.cpp diff and surrounding hookpack parser. Explicit site-level adapter_key selects the exact runtime Site.name; absence retains the legacy site-map name. Explicit null/non-string/empty/whitespace-only values fail instead of silently falling back. A set of effective names rejects explicit-explicit, explicit-legacy and duplicate legacy-name collisions. Checks happen before the site is appended.

Selected-build address, expected bytes, confidence, field offset/size and class/method handling remain in their existing path after key selection. No changes to ordinary non-hookpack parsing, native addresses or build-specific byte evidence. Tests exercise canonical lookup with the logical alias absent, selected-instance bytes and field extent, malformed key types, duplicate effective keys and legacy fallback collisions; existing legacy and field tests remain.

Read /tmp/kp-adapter-key-build.log: kp_hooktool/native runtime build completed. Read /tmp/kp-adapter-key-selftest.log: OK,0 failures. Reviewer did not rerun builds/tests or launch games. Only this requested report was written; no source/index edits.

Frozen hashes:
- src/hooks/registry.cpp d9e9a7aa3545ec8d1a0c5570e12009e0061775a76eb2085dda83cc7ac4018cc1
- tools/kp_hooktool.cpp bbea8cd4b3055721ceb93a28af50cb2e7ece820af8982e25120caad186620e49

This verifies consumer key selection and rejection behavior, not any new corpus address binding or live adapter capability.
