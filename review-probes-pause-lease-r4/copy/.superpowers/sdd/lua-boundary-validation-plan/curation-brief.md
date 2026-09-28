# Original41 example curation

Read-only recommendation, September22 2026. Active worktree `.worktrees/lua-boundary-validation`. No edits, tests/builds or game sessions. Decisions below are editorial recommendations from current script contracts, public documentation and the existing original41 evidence audit; they are not new visual reviews or fresh live acceptance.

## Decision

Stop treating41 as a public showcase target. It mixes regression fixtures, debugging tools, operator snippets, experimental networking and authored effects. Preserve the useful test cases, but curate the public catalog around deliberate, legible changes in the game: a clear trigger, unmistakable outcome, short finite sequence and visible restoration/cleanup. Random flashes, incidental text, logs and successful API calls do not meet the user's visual-power goal.

No original41 item gains a public quality pass through this audit. Retain four original cursed scripts as candidates for focused review, not featured demos. The recent native bow/freeze, scale and motion scenes are outside the41 inventory; promote only individual scenes with their actual verified behavior/footage, without using them to satisfy unrelated original obligations.

## Specific disposition of all41

Paths below are relative to `scripts/examples/`.

| Current files | Count | Recommended disposition | Reason |
|---|---:|---|---|
| `arbitration/10_abstain_nil.lua`, `20_abstain_badstring.lua`, `25_claims_via_string.lua`, `30_claims_false.lua`, `40_too_late.lua`, `50_number_two_is_false.lua` |6|Move to internal real-Host regression fixtures; delete from public examples catalog/tree when path migration is ready.|Ordering/coercion tests are valuable, but deliberate interception/abstention is not a gameplay showcase.|
| `edge_fallback/all_abstain.lua`, `edge_number_two/50_number_two_is_false.lua`, `edge_quarantine/always_errors.lua` |3|Internal real-Host fixtures.|Preserve fallback, numeric-false and quarantine coverage. The duplicate numeric-false file serves an isolated scenario; do not delete coverage merely because bytes duplicate another fixture.|
| `multiplayer/10_avatar_sync_test.lua` |1|Internal standalone regression test.|This is explicitly a system-LuaJIT test, not a runnable gameplay example.|
| `coverage/10_cover.lua`, `probe/00_probe.lua`, `probe/10_position_trace.lua` |3|Developer diagnostics outside public showcase, retaining existing regression/live obligations appropriate to tool use.|Useful observability and route control; no visual scene.|
| All11 `harness/*.lua` listed below |11|Operator/modding recipes, outside showcase.|Useful reusable reads/actions, often require configured tags and independent completion readback. Do not market them as authored scenes or force one-shot snippets through event ownership unnecessarily.|
| `showcase/10_ahto_city_law.lua` |1|Retire public demo; preserve internal fixture.|Cosmetic strike commentary, no law-enforcement mechanic; title oversells observable behavior.|
| `showcase/20_sith_patrol_alarm.lua` |1|Retire public demo; preserve internal fixture.|Text bark, no actual AI alarm propagation.|
| `showcase/30_battle_meditation.lua` |1|Remove from visual showcase; retain a gameplay-buff recipe/fixture.|Useful party/effect/expiry regression and modding mechanism, but not strong visual content by itself.|
| `showcase/40_alignment_drift.lua` |1|Retire public demo; preserve internal fixture.|Polling plus commentary, visually weak.|
| `showcase/50_enclave_arrival.lua` |1|Retire public demo; preserve internal persistence fixture.|Arrival text adds little visual power; retain save/composition regression value.|
| `showcase/60_party_wounded.lua` |1|Retire public demo; preserve internal threshold/dedup fixture.|A warning line, not an authored scene.|
| `cursed/10_rancor_roulette.lua` |1|Retire from public catalog; internal appearance/event fixture.|Random humanoid disguise despite rancor title, weak deliberate composition.|
| `cursed/20_fus_ro_dah.lua` |1|Retire current public implementation; keep force-push/event regression.|Flash/VFX plus attack trigger is redundant with ordinary power presentation; any future native spatial choreography should be a distinct authored scene with actual displacement proof.|
| `cursed/30_necromancer.lua` |1|Retain as unfeatured candidate.|A readable causal scene—corpse rises as a new hostile—has stronger potential; require actual timed spawn, ownership, appearance, bounded lifecycle and clear continuous shot.|
| `cursed/40_chain_reaction.lua` |1|Retain as unfeatured candidate.|A staged causal cascade can be visually legible; require measured propagation and controlled cleanup, not incidental combat HP loss or explosion count.|
| `cursed/50_chaos_roulette.lua` |1|Retire public demo; preserve internal branch fixtures.|Ten unrelated random effects have poor coherence and dilute the strongest capabilities; valuable branch regression remains.|
| `cursed/60_rave.lua` |1|Retire public demo; preserve timer/action fixtures.|Strobes, music and plasma obscure the scene; named dance requests previously needed stronger visible proof. Native bow/freeze offers a much clearer comparison.|
| `cursed/70_doppelganger.lua` |1|Retire public demo; preserve appearance fixture/known-failure history.|Overlaps roulette; original audit recorded incorrect copied appearance. That historical defect is not a current-source diagnosis without rechecking later edits. Even fixing it does not automatically make it compelling.|
| `cursed/80_loot_pinata.lua` |1|Retain as unfeatured candidate.|Readable corpse-to-loot/spawn event; require identifiable credit objects/values, causal spawn and bounded collection/removal. Generic floor-item counts are insufficient.|
| `cursed/90_bullet_time.lua` |1|Retain as unfeatured candidate.|Strong potential temporal contrast; require actual observed speed and restoration, world continuing visibly, and clean effect cleanup. Interrupted earlier run is not a pass.|
| `cursed/100_item_airstrike.lua` |1|Retire current public demo; keep acquisition/level-up regression.|Room-clearing VFX spam tied to arbitrary pickup, with an unrelated ascension effect; poor focused presentation and broad mutation footprint.|
| `multiplayer/10_avatar_sync.lua` |1|Keep separately as experimental networking recipe, unfeatured.|Potentially useful technical demonstration but not full multiplayer and requires real two-client proof; no fake promotion from mocks.|

Count reconciliation:10 host/test fixtures +3 diagnostics +11 operator recipes +6 former showcase entries +6 retired cursed entries +4 cursed candidates +1 experimental networking entry =41. Only4 original items remain candidates for future visual promotion; candidates are not published-quality passes.

The11 operator recipes are `10_world_probe.lua`, `20_dialog_state.lua`, `30_move_to.lua`, `40_attack_nearest.lua`, `50_doors.lua`, `60_area_dump.lua`, `70_pc_status.lua`, `80_signal_event.lua`, `90_run_script.lua`, `100_module_transition.lua`, `110_loot_container.lua`. Keep them reachable in a clearly named tools/recipes index and through normal F12 Lua use. Reclassification should not break the user's access to useful modding operations.

## Minimal first implementation batch

1. Introduce a small explicit public catalog listing only reviewed featured scenes and clearly separate unfeatured candidates. Do not enumerate every scripts/examples file or use automatic `all`/historical `ship` as the public gallery. The default public set may be smaller than four or initially contain only newly verified native scenes. Keep native scenes outside original41 accounting.
2. Remove all six former showcase scripts and rave/chaos from public discovery and default demonstration recording/deploy selections. Relocate their source unchanged to `tools/tests/examples/fixtures/legacy/...` (or a similarly explicit internal root); retain meditation as a recipe link if useful. This eight-file batch removes the clearest weak content without rewriting effects or scheduling more live runs.
3. Add stable original-entry identity and explicit current source location to validation, then route actual-script fixtures through that mapping. Preserve the exact-byte code and existing assertions; do not replace fixtures with mocks of rewritten behavior. This enables later moves of arbitration/edges/standalone avatar test and operator recipes without another validator redesign.
4. Rewrite public showcase/cursed indexes so retired files are not described as shipped demos. Archive relevant detailed playbooks under internal regression docs rather than erasing historical observations. Keep a concise migration note for old filenames. Do not spend implementation time reskinning weak text demos to justify keeping them public.
5. Run the current offline regression/evidence tests with relocated sources and catalog integrity checks. Confirm existing behavioral case counts remain accounted for and no retired demo remains in default public deploy/record selection. No new live test is needed merely to justify editorial retirement.

A later small batch can move the remaining categorized tools and retire the other four cursed entries after references are updated. This staged file migration is a mechanical risk reduction, not a proposal to keep weak items featured temporarily: catalog removal can be immediate and explicit.

## References that must move with sources/catalog

Actual inspected coupling:

- `tools/tests/examples/manifest.json`: current schema1 stores41 relative paths/hashes and mixes original identity with file location. Preserve an original_id/current_source_path/disposition mapping or equivalent schema2. Keep hashes bound to actual current source.
- `tools/example_validation.py`: lines108–118 hardcode41 and10 host-only, recursively equate all `scripts/examples/**/*.lua` with manifest; source reads at74,118,123,133,187; real-Host directories at146–155; standalone multiplayer test path162; printed PASS41 at201. All need deliberate compatibility changes, not deletion of assertions until the suite turns green.
- `tools/tests/examples/fixture.lua`, `showcase.lua`, `cursed.lua`, `harness.lua`, `probes_coverage.lua`, `run.lua`: fixture loading and suite filenames must resolve stable IDs to moved exact sources. `tools/tests/examples/evidence_test.py` and `tools/example_configuration.py` assume source root/path for provenance/configured snippets; preserve their anti-substitution checks across mapping.
- `CMakeLists.txt` example validation target/comments; `README.md` public inventory/examples; `docs/example-validation.md` exactly41 shipped wording; `docs/lua-boundary-validation-plan.md`; current `docs/devtools-design.md`/`docs/user-directive-audit.md` where they describe scope. Update current product claims, retain dated historical scope.
- `docs/showcase-demos/README.md`, six per-demo playbooks, `docs/showcase-demos/cursed.md`, `scripts/examples/cursed/README.md`, `scripts/examples/harness/README.md`.
- `scripts/harness/deploy_showcase.sh`, `record_showcase.sh`, `record_cursed.sh`, `demo_scenes/showcase.scene.sh`, `demo_scenes/arbitration.scene.sh`, `demo_scenes/quarantine.scene.sh`; gameplay tests `test_arbitration.sh`, `test_quarantine.sh`, the six showcase `test_*.sh`, and `gameplay_tests/lib.sh`.
- `scripts/harness/live_session.sh`, `drive_k1_console.sh`, `kpharness/world.py`, `kpharness/creative.py` and ten `scenarios/cursed/*.toml` may retain old source/deploy names. Update operational path references without renaming historical run directories or invalidating recorded hashes.
- `docs/original41-live-evidence-audit.md` is historical evidence: add dated disposition/migration context; do not rewrite old failures/unvalidated results to retired-pass. Older research/ideation references can remain historical with links where needed rather than broad unrelated edits.

This list is scoped search evidence, not a promise every string reference was audited. Implementation should perform one bounded reference search for each moved path and a dead-link/selection check.

## Honest validation/reporting

Separate editorial disposition from verification state. Suggested dispositions: featured, candidate, recipe, diagnostic, internal_fixture, retired_public. Verification fields remain syntax/host/live with their real provenance. A retirement decision is never `live:not_applicable` unless the actual semantic obligation was always host-only; removing a game-facing demo from release does not prove its former live behavior irrelevant or successful.

Preserve the original41 ledger as41 stable historical IDs. For each retired original entry show `retired from public catalog`, reason/date, current internal fixture path, preserved source hash and last-known live status (pending/partial/fail). Closed public-release obligation means removed scope, not passed behavior. New native demos have their own IDs and evidence; no one-for-one substitution to manufacture41 passes.

Generated receipts should report separate counts: active public featured/candidate files; internal regression sources checked; passed syntax/host cases; active applicable live obligations satisfied/open; intentionally retired public entries; retained historical failures. Avoid printing “41 validated” when this means41 host fixtures or fewer public entries after curation. Missing/unmapped files or untested relocated fixtures must fail the inventory gate. A maintained41-source regression set can still pass offline checks, independently of a small quality-focused public catalog.

For a candidate to become featured, require an understandable opening frame, one clear visible change, a readable cause/effect sequence, finite duration and explicit cleanup, independent native state predicates, exact source/runtime identity, and continuous footage reviewed for actual render cadence. The current source-only curation has not supplied those passes.

## Concrete schema and physical-removal contract for the accepted first batch

The controller accepted removing all six text/buff showcase files plus cursed rave/chaos from the public gallery, retaining internal regressions/history. This requires actual source relocation and deployment exclusion, not just removing README links. Do not leave a forwarding script, symlink or copied legacy implementation under scripts/examples that a recursive public deploy can pick up. No implementation is performed by this audit.

Use schema2 with stable existing `path` as the original41 identity to minimize receipt breakage, and a new repository-relative `source_path` for actual reads:

```json
{
  "schema": 2,
  "inventory_count": 41,
  "examples": [{
    "path": "showcase/10_ahto_city_law.lua",
    "source_path": "tools/tests/examples/fixtures/legacy/showcase/10_ahto_city_law.lua",
    "disposition": "retired_public",
    "retirement": {
      "date": "2026-09-22",
      "reason": "Cosmetic commentary does not meet the curated visual showcase goal"
    },
    "sha256": "retain the exact current source hash",
    "syntax": {"status": "required", "evidence": "generated host receipt"},
    "host": {"status": "required", "tier": "controlled_backend", "evidence": "generated host receipt cases"},
    "live": "retain the existing complete object and unresolved obligations unchanged"
  }]
}
```

The abbreviated live value above is explanatory, not literal valid production schema; retain its original status/evidence/predicate fields verbatim. Unmoved entries also get explicit source_path pointing to their current scripts/examples location. Preserve path as the evidence predicate namespace and historical receipt identity; do not reinterpret it as a filesystem path anywhere. Require unique valid source_path values, repository-contained regular files, and reviewed hash membership. The41 count remains a regression/history invariant, not a public shipped count.

Physical first moves: `scripts/examples/showcase/{10_ahto_city_law,20_sith_patrol_alarm,30_battle_meditation,40_alignment_drift,50_enclave_arrival,60_party_wounded}.lua` → matching `tools/tests/examples/fixtures/legacy/showcase/` names; `scripts/examples/cursed/{50_chaos_roulette,60_rave}.lua` → matching `tools/tests/examples/fixtures/legacy/cursed/` names. Relocation should preserve bytes until separately reviewed.

Add a separate small public catalog (proposed scripts/demos/catalog.json) with its own schema and explicit featured/candidate records. Exact native scale/animation and new object-blaster source entries are added only by the owning implementer after checking their actual files/evidence; this audit does not invent their status or path. Public packaging/deployment reads that catalog, excludes tools/tests entirely, and rejects a featured item without an explicit source and reviewed acceptance status. Internal fixture paths must never be reachable through public demo `all`.

Consumer changes:

- Centralize Python `source_for(entry)` in tools/example_validation.py; use source_path for every read/hash/syntax compile/configuration input. The live evidence importer still matches stable path and current source hash. Reject unknown schema/mapping rather than silently resolving a retired path back into scripts/examples.
- tools/tests/examples/fixture.lua:64 currently calls loadfile('scripts/examples/'..path). Have the runner supply one generated stable-ID→source-path Lua table as an explicit argument/environment initialized before suites. F.new(path) remains unchanged and resolves that map; missing IDs fail. Generate it from the validated manifest at run time, with correct Lua string escaping and temporary cleanup, rather than duplicate a hardcoded map or add a product JSON dependency. Existing source override branches retain their test labeling.
- tools/tests/examples/evidence_test.py:63–65 currently selects by path and reads oldroot/path. Read through the same resolver. tools/example_configuration.py:106 currently labels diffs using old public paths; label fromfile using source_path while preserving stable path identity in configuration/evidence. Test expected diff/provenance must match the new mapping.
- Actual real-Host directory fixtures and standalone avatar test are unmoved in this first eight-file batch; keep their existing calls until their separate move. Do not drop them from regression inventory.
- Validation source hashing currently uses tools/tests/examples/*.lua rather than recursive fixtures. Hash every mapped script individually and include resolver/generated-map provenance in receipt; do not double-count mapped fixtures as extra original entries. Public tree scan changes from equal41 to exact agreement with entries whose source_path is in that tree, plus independent public catalog rules. Scan the internal fixture root for unexpected/unmapped Lua so relocation cannot hide drift.
- Deploy/record helpers must fail clearly for a retired public name, or require an explicitly internal regression mode that resolves the manifest. No fallback to a similarly named candidate or whole-directory copy.

Additional focused acceptance tests for this refactor: all eight old public files absent; eight exact-hash internal files present; prior named host cases still execute those bytes; public catalog/default deploy excludes all eight; historical path evidence resolves relocated source correctly; stale or swapped internal content is rejected; configured snippet provenance still reconstructs exact bytes; a retired unvalidated/failed live item remains unvalidated/failed in its historical section and never increases active-public pass totals.
