# Gamescope boot repair: next bounded implementation

Read `/home/brunner56/kp-live-20260922/task7-actual-boot-cause.md` first.

The retained run `20260927-081255-56942ef0` failed before gameplay. Its original exception was masked by teardown; its readiness payload has DISPLAY only. No current game/Gamescope processes were observed on resumption. Do not promote that run or repeat it unchanged.

## Required repair

1. Reap the direct Popen leader during cleanup before deciding that executable process-group members survived. Preserve PID/start/PGID/session ownership checks; distinguish zombies from running descendants. A genuinely live descendant must still fail cleanup after bounded escalation.
2. Preserve the original boot exception alongside cleanup exceptions in durable evidence. Retrying teardown must retain per-attempt evidence without corrupting the expected component ordering.
3. Establish the actual private Xwayland authority mechanism. DISPLAY-only readiness cannot be accepted solely because it names a syntactically valid display. Either provision a valid owned authority path or verify the launched private Xwayland/socket ancestry and explicit access model before admitting it. Do not relax foreign-display protections.
4. Regression tests: S-to-Z direct leader requiring reap; still-running descendant; recycled PID; DISPLAY-only retained payload; boot+cleanup dual failure; repeated cleanup; reaper intermediary ancestry.

## Scope and proof

Single writer after snapshot/provenance writer releases files. Independent scoped review required. First test host lifecycle logic; only after review permit one bounded owned display bring-up with no game, retaining original failure and complete teardown evidence. A live K1 retry remains serialized and uses the verified snapshot. Do not touch host desktop processes or original assets/saves.
