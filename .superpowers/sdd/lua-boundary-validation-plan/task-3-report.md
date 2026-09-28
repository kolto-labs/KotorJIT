# Task 3 implementation report

## Outcome and acceptance boundary

Implemented a checked exact41 inventory and hash-bound executable host ledger.
All41 shipped Lua files compile; all41 have assertion-based host evidence.
69 controlled-backend cases execute the actual30 gameplay/probe/coverage/harness
scripts. Together with9 real-host fixtures and2 multiplayer files, the receipt
has80 per-file case associations. All32 engine-dependent files retain explicit
unvalidated live status;9 real-host fixtures have live not_applicable. No game,
network, runtime rebuild, push or PR was performed by this worker.

Controller owns serialized live evidence and the environment preflight. Its
preflight must not promote this task's32 unvalidated live entries.

## Files and design

- tools/example_validation.py: exact paths/hash check; LuaJIT syntax-only compile;
  generated K1 routine-catalog literal audit (q, nwscript.call, pcall); executable
  Lua cases; real kp_luatest output assertions for arbitration/fallback/number2/
  fourth-dispatch quarantine; existing multiplayer regression; atomic JSON
  receipt with source/test/catalog/host-binary hashes, command logs and Git/diff
  provenance; source/test/binary stability check across validation.
- tools/tests/examples/manifest.json: all41 hashes and syntax/host/live statuses,
  per-file tier, live predicate strings and unmet preconditions. Checked manifest
  host/syntax statuses mean required; generated receipt has actual passes.
- fixture.lua: fresh Lua environments; finite object/party/inventory iteration;
  integer OBJECT_INVALID; controlled caller context; actual zero-result void
  actions; stateful HP/speed; native-only captured timers; explicit routine
  responders; unexpected routines fail even when caught inside example pcall.
- showcase.lua/probes_coverage.lua/cursed.lua/harness.lua:69 behavioral cases,
  positive/negative and request/caller/output assertions, exact scripts loaded.
  Harness configuration branches change exactly one declared local using an
  asserted replacement, never pretend that generated configuration is stock
  source live proof.
- run.lua: fail nonzero for assertions/unknown routines and emit per-file cases.
- evidence_test.py: valid receipt acceptance plus stale source/deployment,
  missing fields/predicates/artifacts, false and integer truth values, wrong
  schema/path and changed-artifact rejection.
- CMakeLists.txt: example_validation offline CTest integrates all tiers above;
  requires a system LuaJIT interpreter when kp_luatest exists.
- docs/example-validation.md: execution, proof boundaries, source identity,
  stale-receipt behavior, live attachment contract and acknowledged limits.
- README.md, showcase demo docs, cursed/harness READMEs: remove unsupported
  current-live/two-game claims; clarify historical status, requested operations,
  exact constants, timer behavior, sample periods, cosmetic scope and counts.

## Reproduced and corrected defects

Each regression was run before its corresponding fix and produced a nonzero
Lua assertion failure; then rerun through the integrated passing gate.

1. Meditation: successful void applies printed steadied0; invalid tagged
   sentinel and nonparty Bastila could pass. Now count pcall success, require
   valid party entries and a valid party Bastila whose GetIsDead returns0.
   Tests include absent, dead, nonparty, invalid party entry, wrong victim/script,
   fallback lowercase tag, constructor/apply error, suppression and next round.
2. Coverage: missing tag's integer OBJECT_INVALID queued talk/jump. Now validate
   both target and PC before entering with_caller.
3. Pinata: missing position consumed burst[corpse] before a later valid retry.
   Mark once only after obtaining a position.
4. Airstrike: an unrelated item possessor consumed seen[item]. Mark after owner
   eligibility so later legitimate acquisition can fire.
5. FUS RO DAH: repeated failed time reads became constant0, permanently blocking
   the victim. Deduplicate only when a timestamp exists.
6. Doppelganger: missing disguise constructor counted and consumed a copy.
   Require successful void application request before setting copy/PC flags.
7. Rave: dead PC could start the timer despite documented alive startup.
   Reject dead PCs in startup; existing inert polling during absence is retained.
8. Chain reaction: third PC query could fail after exploded flag was set.
   Move flag after that inner PC guard, permitting retry.
9. Controller identified native timer misrouting. Removing registertimer from
   fixture's NW responders reproduced failure; all5 callsites across4 scripts
   now use kp.registertimer, exposed only as native by the fixture.
10. Static catalog audit identified IsInConversation absent from K1. Strict
    fixture removal reproduced caught-unknown failures; all7 cursed guards now
    use registered GetIsInConversation. Permanent gate audits literal names.
11. Controller identified harness40 radius leak: sole enemy at40.5m was selected
    despite40m radius. Test40/40.5/41 reproduced it; explicit <=RADIUS fixed it.
12. Invocation comments: replace nonexistent only_two/OnScriptEvent references
    with real edge_number_two directory and OnRunScript.

## Hypotheses retained or narrowed

- Death matching broad dead/death substrings is explicitly documented in cursed
  README; no artificial narrowing based on undead_dialog mock was made.
- NWScript validity integer1 is the real bridge contract. Position probe was
  not changed just to satisfy a boolean mock.
- Rave intentionally returns true while absent/dead to keep one inert polling
  timer. Whether runtime module load cancels/restarts it is still live-unproven.
- Wounded warning lifetime and ambient speaker identity are now explicit; no
  new reset mechanic or speaker selection was invented.
- Scenario oracle/counter increments may describe requests and decisions rather
  than effects. Host coverage does not strengthen those live assertions.
- This is bounded branch coverage, not exhaustive malformed-engine-response
  fuzzing. All30 applicable files have meaningful positive and negative cases;
  not every failed routine combination is modeled.

## Commands and results

Working directory: /run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation

- luajit tools/tests/examples/run.lua:69 cases PASS after targeted red regressions.
- /usr/bin/python3 tools/tests/examples/evidence_test.py:1 unittest with multiple
  rejection subcases PASS.
- /usr/bin/python3 tools/example_validation.py --host
  /home/brunner56/kp-validation-20260922-build/kp_luatest --receipt
  /home/brunner56/kp-validation-20260922-build/example-validation.json:
  PASS41 syntax,41 host files,80 case associations,0 attached live receipts.
- cmake -S . -B /home/brunner56/kp-validation-20260922-build: configure/generate
  PASS. No runtime build or regeneration target was executed.
- ctest --test-dir /home/brunner56/kp-validation-20260922-build
  -R '^example_validation$' --output-on-failure:1/1 PASS, final run0.72s.
- git diff --check:PASS.

Receipt path: /home/brunner56/kp-validation-20260922-build/example-validation.json
It is a generated build artifact, not a committed historical pass. Source/test
hash changes invalidate it. The controller should regenerate after final commit
for final HEAD provenance and attach separately reviewed live receipts as needed.

## Self-review

Found and removed permissive native timer modeling after controller's concrete
finding; made unexpected routines fail despite script pcall protection and added
catalog guard. Corrected LuaJIT syntax invocation after discovering that passing
a filename after -e executes the chunk: now only loadfile is evaluated from -e.
Added source/test/binary end-of-run hash checks to reject mixed snapshots.
Checked stage ownership and kept all test Lua outside scripts/examples. Existing
Task1/Task2 changes were preserved. Documentation distinguishes default snippet
source from configured branches and historical observations from current passes.

## Remaining limitations

The evidence importer verifies source/deployment/artifact identity and complete
predicate claims, not truth of measurements. Review and independent live state
remain mandatory. Configured harness snippets must retain configuration/source
artifacts; the strict importer only promotes entries whose source and deployed
hashes equal the checked manifest, so configured-source acceptance needs a
reviewed manifest/configuration flow rather than substituting a different hash.
No current live pass is asserted by this report.

Commit: e2dfb28 (Add hash-bound Lua example behavior validation),38 files.
Post-commit example_validation CTest rerun passed; receipt now binds this HEAD.

# Task3 fix round1 (review base e2dfb28)

Addressed all4 findings from /tmp/kp-task3-review.md, plus controller-authorized
route-label corrections and reviewed multiplayer configuration support.

1. Added tools/example_configuration.py with an explicit per-file literal
   allowlist. Supported all documented configurable harness constants, including
   OPEN/INSPECT, nullable TARGET_TAG, offset vectors, target/event/script/loot
   tags, limits/type/radius, module/waypoint. Production multiplayer supports
   LOCAL_NAME, LISTEN_PORT and up to3 distinct IPv4 host/port peers. No arbitrary
   patch, script body edit, extra key, Lua injection, unbounded value or unchanged
   configuration is accepted. Exact stock declarations must match.
2. Configured importer retains stock source_sha256, verifies hashed configuration
   JSON/diff/effective/deployed artifacts, recomputes effective bytes and exact
   unified diff from stock plus allowlisted values, checks every artifact byte
   and configured/deployed SHA256. Unknown modifications fail even if all edited
   artifact hashes are recomputed consistently. Duplicate JSON keys also fail.
   Documented the artifact schema and generation helper. This supersedes the
   configured-source limitation in the original report above.
3. Replaced generic predicates with139 concrete IDs and obligations across31
   engine-dependent examples. Each checklist identifies actual effect/action
   outcomes, relevant guards and request/observation distinctions. Examples:
   bullet-time independent speed/restoration, necromancer appearance21 readback
   before cleanup, party HP threshold/once-state warning, inventory transfer and
   real two-client multiplayer identity. Missing one required outcome rejects
   full promotion. No live status was promoted by this fix.
4. Removed invented audible custom-SpeakString requirements from showcase docs
   and manifest. Require displayed text and actual caller instead. Explicit rave
   battle music remains an audio outcome because that script requests music.
5. Standalone multiplayer regression live status is now not_applicable. Counts
   are31 engine-dependent/unvalidated and10 host-only, superseding original32/9.
6. Corrected only text labels in cursed roulette/necro routes: a request counter
   does not prove transformed monsters, and no-hostiles cleanup does not prove
   Malak appearance. Route code/semantics were not changed.

Tests:9 evidence unittests PASS, including valid configured transition,
all10 configurable harness snippets, target and offset movement variants,
multiplayer loopback config, missing true-two-game obligation rejection,
configuration artifact/diff/source/deployment tamper (with and without updated
hashes), consistently rehashed unrelated source edits, missing concrete outcome,
wrong types/bounds/injected Lua/duplicate JSON and stale evidence rejection.
Configured harness outputs compile with LuaJIT; no game calls execute.

Final precommit CTest example_validation PASS1/1 (0.67s):41 syntax,41 host,
69 controlled Lua cases plus real-host/multiplayer assertions,80 per-file case
associations. This is offline evidence only. git diff --check PASS. git diff
--exit-code e2dfb28 -- scripts/examples PASS: all41 shipped Lua source bytes
remain frozen, including production multiplayer. No games, staged installs,
live drivers or runtime builds touched; user/controller creative-live work
remains independent. General11-snippet live acceptance remains deferred, not
removed from manifest. Ready for fresh independent review.

Fix-round commit: cdce1fb (Validate reviewed Lua configurations and concrete live obligations).
Post-commit example_validation CTest PASS; generated receipt refreshed to commit provenance.

## Separate live-evidenced wounded oracle correction after Task4

Controller observed engine GetTag returning bastila plus trailingNUL, which
truncated kp.print native logging before "below35%". Added a controlled real-Lua
case with bastila\\0\\0 and native C-string sink truncation assertion. Ran before
fix: luajit exited1 at padded-engine-tag assertion. Corrected only showcase60
by stripping trailingNUL on a string tag before choosing/formatting the warning.
Refreshed only showcase60 SHA256 in the exact41 manifest. Other40 shipped Lua
files unchanged. No warning lifetime, target, speaker, or combat mechanics were
changed. Integrated example gate now70 controlled cases/81 per-file associations;
no live pass inferred. Controller owns the corrected-source live retry.
Padded-tag correction commit:1bb1714; postcommit example_validation CTest PASS,
receipt regenerated for this HEAD. Pre-fix failure and passing host proof do
not replace controller's pending live retry.
