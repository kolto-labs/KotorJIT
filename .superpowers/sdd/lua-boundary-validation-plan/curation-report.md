# Eight-file public example curation handoff

Status: implemented and source-frozen for independent review. No git index changes, commit, game sessions, runtime builds, downloads or subagents. The native console/input changes and unrelated docs/research/native-animation-sites.md edit were not modified. CMake was not modified. Controller audit documents retain their prior bytes.

## Result

Physically relocated the six scripts/examples/showcase Lua files and cursed/50_chaos_roulette.lua plus cursed/60_rave.lua to tools/tests/examples/fixtures/legacy with identical bytes. No public source copies or forwarding symlinks remain. All41 original IDs, source hashes and complete live objects equal the pre-curation host receipt.33 source files remain in the original examples tree; the other original entries have not been migrated by this slice.

Manifest schema2 adds explicit source_path/disposition and retirement reasons, keeping original path as evidence identity. New example_inventory.py validates exact41 membership, the reviewed eight-retirement set, source location/hash, collision/symlink/traversal boundaries and unmapped Lua files. Lua fixtures receive a generated manifest-derived source map; all prior behavior suites still execute the exact original scripts. Configured-source evidence and diffs use current source locations while original IDs stay stable. Receipts distinguish regression counts/public retirements and do not promote live obligations.

Public legacy showcase deploy/record commands reject retired requests before game access. Cursed recorder rejects chaos/rave before game/preflight access; its existing all selection cannot see the physically removed files. Explicit internal gameplay tests now locate relocated showcase fixtures. Old showcase narration has been replaced with a retirement notice. Public docs link the separate native catalog: featured is empty and scale/animation entries are candidates only. Stock dance bytes are not promoted from configured bow/victory recordings. No object-blaster status or path was invented while that work belongs to another writer.

## Executed validation

- `python3 tools/example_validation.py --host /home/brunner56/kp-validation-20260922-build/kp_luatest --receipt /tmp/kp-curation-example-validation.json`: PASS,41 compile checks,41 host-covered original sources,81 named per-file cases. Includes actual Lua controlled fixtures, real Host arbitration/fallback/quarantine assertions, standalone multiplayer mocks, and14 Python provenance/curation tests.0 live receipts attached; no public quality promotion.
- Receipt generated2026-09-22T18:42:12.090719+00:00; recorded HEAD fce490ee10d2cab1765dbff4f2dfd7883074e66c and dirty-diff provenance. SHA256 dd6b6f19a82ccf60c6c11fffba2ced5b7f28fb71e5e2f514d3e4919890ef82f7.
- Existing kp_luatest SHA25645fab1a055cf00c042b121376b38a0de6f03334f96156302c93c8bc07df9154f. No rebuild. Receipt hashes validation code/source inputs; controller may subsequently change HEAD/dirty diff without changing those tested inputs. A final Markdown-only trailing-space cleanup followed the receipt; no tested Lua/Python/manifest/catalog bytes changed afterward.
- Independent comparison with /home/brunner56/kp-validation-20260922-build/example-validation.json: all41 source SHA256 values and complete live objects match; all eight old public source paths absent.
- `bash -n` passed for deploy_showcase.sh, record_showcase.sh, record_cursed.sh and all six affected internal gameplay test scripts. This is syntax validation only; no script launched a game. Python negative tests invoke retired public requests only and verify exit2 before game access.

The first full run found a source-map resolver returning assert's diagnostic as an extra Lua value, which loadfile treated as a mode. Fixed to return one local path; the complete rerun above passed. The final receipt briefly waited on existing Git dirty-diff I/O, then completed normally. No search/provenance processes remain.

## Review boundaries and remaining work

This is only the accepted eight-file batch. It does not migrate the remaining33 sources, retire all other weak candidates, or validate gameplay. Existing failures/unmet live obligations stay intact. Newly authored native scenes retain separate evidence. Public catalog is conservative and makes no featured quality claims. Browser/WASM remains outside this implementation.

The historical detailed playbooks remain, explicitly labeled internal/retired. Tests verify removal, relocated source hashes, source-path rejection, reintroduced-public-copy rejection, unlisted internal file rejection, symlink rejection, retired deploy rejection and unresolved live predicate preservation. Configured-source tamper checks remain exercised.

## Scoped tracked changes (including eight deletions)

- `README.md`
- `docs/example-validation.md`
- `docs/showcase-demos/10_ahto_city_law.md`
- `docs/showcase-demos/20_sith_patrol_alarm.md`
- `docs/showcase-demos/30_battle_meditation.md`
- `docs/showcase-demos/40_alignment_drift.md`
- `docs/showcase-demos/50_enclave_arrival.md`
- `docs/showcase-demos/60_party_wounded.md`
- `docs/showcase-demos/README.md`
- `docs/showcase-demos/cursed.md`
- `scripts/demos/showcase.scene`
- `scripts/examples/cursed/50_chaos_roulette.lua`
- `scripts/examples/cursed/60_rave.lua`
- `scripts/examples/cursed/README.md`
- `scripts/examples/showcase/10_ahto_city_law.lua`
- `scripts/examples/showcase/20_sith_patrol_alarm.lua`
- `scripts/examples/showcase/30_battle_meditation.lua`
- `scripts/examples/showcase/40_alignment_drift.lua`
- `scripts/examples/showcase/50_enclave_arrival.lua`
- `scripts/examples/showcase/60_party_wounded.lua`
- `scripts/harness/demo_scenes/showcase.scene.sh`
- `scripts/harness/deploy_showcase.sh`
- `scripts/harness/gameplay_tests/test_ahto_city_law.sh`
- `scripts/harness/gameplay_tests/test_alignment_drift.sh`
- `scripts/harness/gameplay_tests/test_battle_meditation.sh`
- `scripts/harness/gameplay_tests/test_enclave_arrival.sh`
- `scripts/harness/gameplay_tests/test_party_wounded.sh`
- `scripts/harness/gameplay_tests/test_sith_patrol_alarm.sh`
- `scripts/harness/record_cursed.sh`
- `scripts/harness/record_showcase.sh`
- `tools/example_configuration.py`
- `tools/example_validation.py`
- `tools/tests/examples/evidence_test.py`
- `tools/tests/examples/fixture.lua`
- `tools/tests/examples/harness.lua`
- `tools/tests/examples/manifest.json`
- `tools/tests/examples/run.lua`

## New files

- `tools/example_inventory.py`
- `scripts/demos/catalog.json`
- `scripts/demos/README.md`
- `tools/tests/examples/fixtures/legacy/README.md`
- `tools/tests/examples/fixtures/legacy/cursed/50_chaos_roulette.lua`
- `tools/tests/examples/fixtures/legacy/cursed/60_rave.lua`
- `tools/tests/examples/fixtures/legacy/showcase/10_ahto_city_law.lua`
- `tools/tests/examples/fixtures/legacy/showcase/20_sith_patrol_alarm.lua`
- `tools/tests/examples/fixtures/legacy/showcase/30_battle_meditation.lua`
- `tools/tests/examples/fixtures/legacy/showcase/40_alignment_drift.lua`
- `tools/tests/examples/fixtures/legacy/showcase/50_enclave_arrival.lua`
- `tools/tests/examples/fixtures/legacy/showcase/60_party_wounded.lua`
- `.superpowers/sdd/lua-boundary-validation-plan/curation-report.md`

## P2 review follow-up: public creative runner (implemented and frozen)

Independent review /tmp/kp-curation-review.md identified that the public creative runner could explicitly deploy a relocated retired fixture and performed game discovery before validating script inputs. Fixed only scripts/harness/kpharness/creative.py and tools/kpharness_creative_test.py, plus this handoff record.

script_inputs now reads the schema-2 manifest retirement metadata and rejects exact retired original IDs, old public paths, current internal source paths, absolute/repository-relative forms and resolved symlink aliases. It does not ban basenames, arbitrary external user scripts or unrelated internal host fixtures. run_creative resolves scripts before route loading, game/build discovery, staging, lock acquisition or recorder/session creation. No new internal execution mode was invented; existing internal regression tests remain independently usable.

Validation: `python3 tools/kpharness_creative_test.py` PASS27 tests, including41 rejected forms (five forms for each of8 examples plus a symlink alias) and positive retained/custom/unrelated-internal sources. Rejection tests assert no calls to route/game/build discovery, lock, mkdir or stage claim. Existing mocked driver integration cases also pass. The printed cleanup RuntimeError is an expected exercised cleanup-failure case, not a suite failure. `python3 -m py_compile` for the two changed files and scoped `git diff --check` pass. No games, runtime builds, index mutations or commits performed.

Original41 validator receipt above remains evidence for unchanged Lua/manifest/resolver test inputs; this follow-up's creative-runner changes have their separate27-test evidence and are not retroactively covered by that receipt. Source is frozen again for scoped re-review.

- `scripts/harness/kpharness/creative.py` SHA256 `b40a34512371cb0699fee51d8ca5c2cff04c7898425763808ad83f7d3a9a56e6`

- `tools/kpharness_creative_test.py` SHA256 `7d2496a9bb1d080dd06cb8b18a2fd4d2cadec5d52562b2c895d91f0cbac3bc71`

## Final alias follow-up (implemented and frozen)

Scoped rereview found that examples-relative fallback could select a symlink after the initial retirement check. script_inputs now checks the final resolved selected path against retired_paths after fallback and before appending it. Added test_examples_shorthand_symlink_rejected_before_game_access using a temporary examples-directory shorthand alias pointing to a synthetic retired fixture path. It asserts rejection before route/game/build discovery, staging, mkdir or locking. Arbitrary custom same-basename compatibility remains covered.

`python3 tools/kpharness_creative_test.py`: PASS28 tests in4.841seconds, including the added shorthand fallback regression. Scoped git diff --check passes. Expected cleanup-failure diagnostic remains part of a successful negative test. No game, build, index mutation or commit. Source frozen for rereview; these hashes supersede the preceding follow-up hashes.

- `scripts/harness/kpharness/creative.py` SHA256 `f4a7633da12bcf84c4cdc63bcb3bc764452fb39cf42d684c83e6ae6d148325f3`

- `tools/kpharness_creative_test.py` SHA256 `4c00eaa0d6c2a322aaea6da142e68f6eaaec39b9ba61f9df0296f8cd04337457`
