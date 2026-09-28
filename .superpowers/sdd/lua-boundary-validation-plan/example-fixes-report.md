# Example fixes report (2026-09-27)

Spec: `docs/example-behavior-ledger.md`. It covers the five needs-fix rows,
the avatar-sync mock, and the arbitration/50 retire recommendation.
Worktree: `.worktrees/lua-boundary-validation`. Nothing was staged, committed
or pushed. No Wine or game was run.

Scope kept: I edited only `scripts/examples/**` (not the Doppelganger
script), `tools/tests/examples/{cursed,fixture,probes_coverage}.lua`,
`tools/tests/examples/manifest.json` (4 hashes and 2 obligation strings,
edited in place) and the ledger.

## Red-first record

Tests were added before each behavior change. The red run used a
non-stopping copy of `run.lua` (`/tmp/kp-run-all.lua`) on host LuaJIT
`/usr/bin/luajit`:

```
FAIL cursed/40_chain_reaction.lua  party min-one-HP guard restores ... : prior flag must be read before protection
FAIL cursed/40_chain_reaction.lua  unreadable prior min-one-HP flag leaves that party member untouched
FAIL cursed/100_item_airstrike.lua strikes only hostile non-party creatures ... : neutral and party excluded
PASSED 75 FAILED 3
FAIL coverage/10_cover.lua help describes pick as print-only ... : pick help overclaims: [cover] pick <n> queue reply index ...
FAIL: first spawn must SetFacing(90) with the ghost as caller            (avatar test, before mock fix)
FAIL: facing change 90 -> 100 must SetFacing(100) with the ghost as caller
```

After the fixes: `PASSED 79 FAILED 0`, and the avatar test printed
`OK: all checks passed`. The full validator run is below.

## Fix 1: chain reaction

- File: `scripts/examples/cursed/40_chain_reaction.lua`
- SHA before: `a346b5a8381d3fcdcfadf7c3c1ef859539fe8eb9208ee05f33db647cbdeb5c3f`
- SHA after: `daed75d1161720112c7d8ee8cffacfb4544a9fd7f8a2ef8e484d5b0573a7043b`

Changes:

- `guard` (line 59) reads `GetMinOneHP` once, before the first
  `SetMinOneHP(v, 1)`. It sets the flag through `nwscript.call`.
- `restore_guards` (line 68) calls `SetMinOneHP(member, prior)` through
  `nwscript.call`. It runs from:
  - the `chain_settle` timer, 3 s after the latest blast (lines 73 and 169).
    A generation stamp makes superseded timers do nothing.
  - `disarm`, on module load or area enter (line 113).
  - `OnScriptUnload` (line 120).
- A party member whose prior flag cannot be read is left out of the blast
  (line 155).
- The comments now say local 6 is requested damage, not a measurement.

Fixture (`tools/tests/examples/fixture.lua:107-108`): `GetMinOneHP` and
`SetMinOneHP` now keep a per-object `min_one_hp`.

Tests in `tools/tests/examples/cursed.lua`:

- "party min-one-HP guard restores each prior flag after settle, transition and unload"
- "unreadable prior min-one-HP flag leaves that party member untouched"
- "frag VFX is unreachable when blast deaths arrive after the hook returns"
- "frag VFX is reached only if a death script re-enters during the damage call"

`VFX_FRAG` verdict: it is reachable only if a victim's death script runs
inside the `ApplyEffectToObject` bridge call (depth > 0 exists only inside
the victim loop). `Host::dispatch` (`src/lua/host.cpp:296`) has no re-entry
guard, so the host does not rule it out. The script header records blast
deaths arriving a frame later, which gives thermal only. The two tests prove
each case. A live chained kill must decide which one the engine does. The
code is unchanged here.

## Fix 2: Doppelganger README

- File: `scripts/examples/cursed/README.md`, line 14. Lines 13 and 17 also
  changed for fixes 1 and 3.
- README SHA before: `edfe2b5466bac561258a7c545bdc7f2fd2769cadb76134e0db21c3abb00d1dd8`
- README SHA after: `dfe19850dc48c7a9e3f91da7b69c2bea2de599ad5f28986babd01bd1dddd24b5`
- Script bytes, unchanged before and after:
  `5d9864b22241ff135d3bb0c1ecb3f2671af218b58cdf2f44eb7bc62c95f62c42` (frozen)

New text:

- Trigger: your first attack on a living non-party creature. The engine
  never sends `OnCreatureAttacked` with the PC as victim (`api-status.md:118`,
  script line 205).
- Each creature you attack takes your pre-Malak look.
- Restore: after combat, 40 quiet ticks (lines 179-186) or an area enter or
  module load (lines 163-164). Only the script's own disguises are removed.
- The script re-arms 200 ticks later and does nothing during a conversation
  (line 204).

## Fix 3: item airstrike

- File: `scripts/examples/cursed/100_item_airstrike.lua`
- SHA before: `b528fb644559a9f6db31dee129d07277d8ca64bb57c14790516de3d17925848d`
- SHA after: `ce2e1504f9b45cfe5edb85a694df6330613f2d3ec7a3033e4f1c72e0256e0e11`

Changes:

- Line 67 adds `yes(q("GetIsEnemy", o, pc))`, via `nwscript.call`. Neutrals
  and party members are excluded.
- The header comment (lines 19-23) now records the live risk. The header
  (lines 10-11) and README line 17 mark level-up as unproven. It is only
  "Bound" (`api-status.md:150`), and a host run cannot prove engine dispatch.
- Manifest obligation `targets_damage` now names the `GetIsEnemy` filter and
  neutral exclusion.

Test: "strikes only hostile non-party creatures by GetIsEnemy against the PC".

## Fix 4: coverage `pick`

- File: `scripts/examples/coverage/10_cover.lua`
- SHA before: `a8f0b06fe282c6a08bbc55045740b5fdbec2e0df27c25b26d273be5c75e45462`
- SHA after: `c13f64247ba86895849d42d4b32816957a4530a4ad5079d2a886818a879e77b3`

Line 47 help now reads "prints the index only; no reply is chosen". The
comment at lines 119-121 was corrected. No proven API queues a reply, so
only the text changed.

Test (`tools/tests/examples/probes_coverage.lua:39`): "help describes pick as
print-only with no reply chosen".

## Fix 5: avatar-sync test mock

- File: `scripts/examples/multiplayer/10_avatar_sync_test.lua`
- SHA before: `e74521ac0275c60917a1e12e9b3a8928d22e65853f90b554c9221daa348078c6`
- SHA after: `784e2e98d56e4d491b06572243f82ef8311934fff163cc2dd202f355ef89e556`

Changes:

- `kp.as` is removed. `10_avatar_sync.lua` has no `kp.as` use (grep is
  empty).
- The mock adds `nwscript.with_caller` (line 100), which sets and restores
  `current_caller` and rethrows errors.
- The `SetFacing` mock logs the caller (line 90).

New checks:

- First spawn: `SetFacing(90)` with the ghost as caller.
- Facing change 90 to 100: `SetFacing(100)` with the ghost as caller.
- Facing unchanged: no `SetFacing` call.

This exercises `10_avatar_sync.lua:560-561`.

## Fix 6: retire arbitration/50. Blocked, not done.

The `ab387d6` convention moves the file to
`tools/tests/examples/fixtures/legacy/` and flips its manifest disposition.
That also needs edits to forbidden files:

- `tools/example_inventory.py:11-16`: the hardcoded `RETIRED` set, which
  raises "reviewed retirement set drift".
- `tools/example_validation.py:147-149`: the arbitration expectations
  `called: 6`, `abstained: 2`, `ignored: 3` and the `[50_number_two_is_false]`
  regex.
- `tools/example_validation.py:205-206`: the hardcoded "8 retired" print.

A partial move would break the validator, so the file is unchanged. The
ledger row now reads "retire (recommended; blocked)" with these referents.

## Host receipt

Build: `host-cmd cmake --build /home/brunner56/kp-validation-20260922-build --target kp_luatest`.
This is the existing build directory configured for this worktree. It built
without errors; the only output was two existing `-Wmissing-field-initializers`
warnings.

Command (on the host, from the worktree root):

```
/usr/bin/python3 tools/example_validation.py --luajit /usr/bin/luajit \
  --host /home/brunner56/kp-validation-20260922-build/kp_luatest \
  --receipt /home/brunner56/kp-live-20260922/example-host-receipt-20260927.json
```

Output: `PASS: 41 original syntax/host regression sources, 90 per-file cases; 8 retired from public catalog; 0 live receipts attached; no public quality promotion` (exit 0).

Receipt facts:

| Field | Value |
|---|---|
| Path | `/home/brunner56/kp-live-20260922/example-host-receipt-20260927.json` |
| Receipt SHA-256 | `1d75734f964c779172a43526076d39279efb48a9a8b641b6b32170aa80ccdfdc` |
| Generated | 2026-09-27T16:15:51Z |
| HEAD | `ca329e52dd27` |
| Dirty diff | `819b4b1cfd33…` |
| `kp_luatest` SHA-256 | `9309dd6a3a5b…` |
| Manifest | `f530e825c7e2…` |
| Inventory | 41 entries, 8 retired, 33 remaining, 0 public quality passes claimed |

All 41 entries show syntax passed and host passed. Live is `unvalidated` or
`not_applicable` for every entry, and no live evidence is attached.

Host case counts for the changed rows:

| Example | Bytes | Host cases |
|---|---|---|
| `cursed/70_doppelganger.lua` | `5d9864b22241` (current, frozen bytes) | 5 |
| `cursed/40_chain_reaction.lua` | `daed75d11617` | 7 |
| `cursed/100_item_airstrike.lua` | `ce2e1504f9b4` | 3 |
| `coverage/10_cover.lua` | `c13f64247ba8` | 12 |
| `multiplayer/10_avatar_sync_test.lua` | `784e2e98d56e` | 1 (mocked multiplayer) |
| `arbitration/50_number_two_is_false.lua` | `938a7b525dc7` | 1 (real host) |

Test file SHA-256 values:

| File | Before | After |
|---|---|---|
| `tools/tests/examples/cursed.lua` | `c8ec4edb…` | `80b9bd95…` |
| `tools/tests/examples/fixture.lua` | `cb11cdf9…` | `cb74dc7b…` |
| `tools/tests/examples/probes_coverage.lua` | `eecd81d4…` | `19b60326…` |
| `tools/tests/examples/manifest.json` | `82dab5ef…` | `f530e825…` |

All 41 examples, from the receipt:

| Example | sha12 | Disposition | Syntax | Host | Tier | Cases | Live |
|---|---|---|---|---|---|---|---|
| `arbitration/10_abstain_nil.lua` | `91308fbe2548` | retained | passed | passed | real_host | 1 | not_applicable |
| `arbitration/20_abstain_badstring.lua` | `e38c5adb9dce` | retained | passed | passed | real_host | 1 | not_applicable |
| `arbitration/25_claims_via_string.lua` | `2fb4eb30a9e5` | retained | passed | passed | real_host | 1 | not_applicable |
| `arbitration/30_claims_false.lua` | `41757499f42a` | retained | passed | passed | real_host | 1 | not_applicable |
| `arbitration/40_too_late.lua` | `7e18f0bfae1e` | retained | passed | passed | real_host | 1 | not_applicable |
| `arbitration/50_number_two_is_false.lua` | `938a7b525dc7` | retained | passed | passed | real_host | 1 | not_applicable |
| `coverage/10_cover.lua` | `c13f64247ba8` | retained | passed | passed | controlled_backend | 12 | unvalidated |
| `cursed/100_item_airstrike.lua` | `ce2e1504f9b4` | retained | passed | passed | controlled_backend | 3 | unvalidated |
| `cursed/10_rancor_roulette.lua` | `1bca2de3ca5f` | retained | passed | passed | controlled_backend | 2 | unvalidated |
| `cursed/20_fus_ro_dah.lua` | `e84102b15810` | retained | passed | passed | controlled_backend | 2 | unvalidated |
| `cursed/30_necromancer.lua` | `af24b0172f83` | retained | passed | passed | controlled_backend | 2 | unvalidated |
| `cursed/40_chain_reaction.lua` | `daed75d11617` | retained | passed | passed | controlled_backend | 7 | unvalidated |
| `cursed/50_chaos_roulette.lua` | `5d796ae8cca1` | retired_public | passed | passed | controlled_backend | 10 | unvalidated |
| `cursed/60_rave.lua` | `56e47290dd37` | retired_public | passed | passed | controlled_backend | 2 | unvalidated |
| `cursed/70_doppelganger.lua` | `5d9864b22241` | retained | passed | passed | controlled_backend | 5 | unvalidated |
| `cursed/80_loot_pinata.lua` | `a72857b81e3b` | retained | passed | passed | controlled_backend | 3 | unvalidated |
| `cursed/90_bullet_time.lua` | `57d1cfbc9f91` | retained | passed | passed | controlled_backend | 1 | unvalidated |
| `edge_fallback/all_abstain.lua` | `71ce5320521c` | retained | passed | passed | real_host | 1 | not_applicable |
| `edge_number_two/50_number_two_is_false.lua` | `938a7b525dc7` | retained | passed | passed | real_host | 1 | not_applicable |
| `edge_quarantine/always_errors.lua` | `314dc45cda17` | retained | passed | passed | real_host | 1 | not_applicable |
| `harness/100_module_transition.lua` | `5e9eedb00450` | retained | passed | passed | controlled_backend | 1 | unvalidated |
| `harness/10_world_probe.lua` | `9d043fdb12bc` | retained | passed | passed | controlled_backend | 1 | unvalidated |
| `harness/110_loot_container.lua` | `d97d16a1c8d9` | retained | passed | passed | controlled_backend | 1 | unvalidated |
| `harness/20_dialog_state.lua` | `d0edc3dc6399` | retained | passed | passed | controlled_backend | 1 | unvalidated |
| `harness/30_move_to.lua` | `f986d44610e6` | retained | passed | passed | controlled_backend | 1 | unvalidated |
| `harness/40_attack_nearest.lua` | `ee74e4739f35` | retained | passed | passed | controlled_backend | 2 | unvalidated |
| `harness/50_doors.lua` | `c1793deb1426` | retained | passed | passed | controlled_backend | 1 | unvalidated |
| `harness/60_area_dump.lua` | `41dc5b3191fd` | retained | passed | passed | controlled_backend | 1 | unvalidated |
| `harness/70_pc_status.lua` | `c8154f8045f2` | retained | passed | passed | controlled_backend | 1 | unvalidated |
| `harness/80_signal_event.lua` | `8728b4cd6e10` | retained | passed | passed | controlled_backend | 1 | unvalidated |
| `harness/90_run_script.lua` | `560dbdc1ea4c` | retained | passed | passed | controlled_backend | 1 | unvalidated |
| `multiplayer/10_avatar_sync.lua` | `954b9cdee1f1` | retained | passed | passed | mocked_multiplayer | 1 | unvalidated |
| `multiplayer/10_avatar_sync_test.lua` | `784e2e98d56e` | retained | passed | passed | mocked_multiplayer | 1 | not_applicable |
| `probe/00_probe.lua` | `cafcf88daf06` | retained | passed | passed | controlled_backend | 1 | unvalidated |
| `probe/10_position_trace.lua` | `1dd76b8b044e` | retained | passed | passed | controlled_backend | 1 | unvalidated |
| `showcase/10_ahto_city_law.lua` | `7f263c2f5784` | retired_public | passed | passed | controlled_backend | 1 | unvalidated |
| `showcase/20_sith_patrol_alarm.lua` | `c06f339b5b74` | retired_public | passed | passed | controlled_backend | 1 | unvalidated |
| `showcase/30_battle_meditation.lua` | `6aaf0ad7a0c9` | retired_public | passed | passed | controlled_backend | 10 | unvalidated |
| `showcase/40_alignment_drift.lua` | `5d151bc4be02` | retired_public | passed | passed | controlled_backend | 1 | unvalidated |
| `showcase/50_enclave_arrival.lua` | `35d87eb81d43` | retired_public | passed | passed | controlled_backend | 1 | unvalidated |
| `showcase/60_party_wounded.lua` | `d6e7c59d7d2e` | retired_public | passed | passed | controlled_backend | 2 | unvalidated |

## Residuals

- **No live or video proof for any fix.** Every result above is Lua host
  evidence against a fixture bridge.
- **Airstrike.** `GetIsEnemy(x, pc)` answered 0 inside `OnRunScript` on
  2026-09-16. The same comment appears in scripts 10, 20 and 30. If
  `OnModuleAcquireItem` behaves the same way, strikes will hit nothing. A
  live pickup with a hostile in range decides this. Airstrike still has no
  conversation guard, and level-up is still unproven.
- **Chain reaction.** Two things need a live chained kill: whether frag VFX
  ever fires, and actual min-one-HP readback after settle.
- **Chain reaction, module-load restore.** The restore uses object IDs
  captured before the transition. If party members get new IDs after
  `StartNewModule`, it misses them and they keep min-one-HP=1. The
  Doppelganger "unavailable actor" path (`cursed.lua:134-136`) shows actors
  can be gone at module load. The fixture cannot decide this.
- **Coverage.** `tools/coverage_walk.py:6` still mentions a digit fallback in
  `cover pick`. That file was out of scope.
- **Arbitration/50.** Retirement needs a writer who may edit
  `tools/example_inventory.py` and `tools/example_validation.py`.

## Fix 6 retry (2026-09-27, sole writer): still blocked, no files changed

The second pass could edit `tools/example_inventory.py`,
`tools/example_validation.py`, `manifest.json` and the ledger. The retirement
still fails, because `tools/tests/examples/evidence_test.py` is outside that
list. The validator runs it (`example_validation.py`, the `evidence_test.py`
command), and it asserts three things arbitration/50 cannot meet:

- line 60: `assertEqual(len(retired), 8)`. With arbitration/50 there are 9.
- line 64: every retired entry has live status `unvalidated`. arbitration/50
  is `not_applicable`. Changing it breaks `example_validation.py`'s
  "host-only inventory drift" check (`== 10`).
- line 65: every retired entry has non-empty `required_predicates`.
  arbitration/50 has none.

Two more notes for the next writer:

- `example_validation.py` labels host cases by identity prefix (`arbitration/`),
  not by `source_path`. After the move it would record "real Lua host dispatch
  assertions: arbitration" for a file that run no longer loads. Its coverage
  should come from its own run of the relocated file, or cite the identical
  `edge_number_two` bytes (`938a7b525dc7`).
- `tools/tests/examples/fixtures/legacy/README.md` says "These eight files".

Nothing was moved or edited. The file stays at
`scripts/examples/arbitration/50_number_two_is_false.lua`
(`938a7b525dc7bbba931788f0a9801a6690b770c99a50656cf89fff63e05af3e4`, same as
`edge_number_two/50`). No validator rerun and no new receipt: sources are
unchanged since receipt `1d75734f…`.

## I1 fix round (2026-09-27, sole writer): review I1, N2, N3, N5

Review: `/home/brunner56/kp-live-20260922/example-fixes-review.md`. Files changed:
`scripts/examples/cursed/40_chain_reaction.lua`, `scripts/examples/cursed/README.md`
(rows 13 and 14), `tools/tests/examples/cursed.lua` (3 new tests),
`tools/tests/examples/manifest.json` (chain sha and `party_survival` text),
`docs/example-behavior-ledger.md`. `fixture.lua` and `70_doppelganger.lua` untouched.

claim: probes A1 and P3 are now host regressions, red on the old bytes and green on the new.
referent: `/home/brunner56/kp-live-20260922/example-fixes-i1-red.out` (script `daed75d1…`: 3 FAIL with the tests' own messages "party member re-created under a new ID kept min-one-HP=1", "PC re-created under a new ID left immortal", "PC not cleared while another member was missing") and `example-fixes-i1-green.out` (script `24ad2057…`: all 10 chain cases PASS).
checked: `luajit /tmp/kp-chain-only.lua /tmp/kp-example-sources.lua` on the host through `host-cmd`.
verdict: holds. confidence: high.

claim: the reviewer's unmodified probes now pass.
referent: `example-fixes-i1-green.out`: `chain_attacks.lua` A1-A8 all HOLDS (A1 "new-id bastila min_one_hp=0"), `pc_probe.lua` P1-P3 all HOLDS (P3 "new-id PC min_one_hp=0"). A1 passes although it keeps the stale party roster `{1,2}`, because of the `GetObjectByTag` fallback (party members only).
checked: same host run.
verdict: holds. confidence: high.

claim: each new assertion is load-bearing.
referent: `example-fixes-i1-mutations.out`. Mutant 1 (no carry-over of a pending prior in `guard`) fails only "stale guard entry made the stuck flag the new prior". Mutant 2 (no `GetFirstPC` branch) fails the PC test and the missing-member test. Mutant 3 (no restore call) fails 4 cases.
checked: mutants at `/tmp/kp-chain-mut{1,2,3}.lua`.
verdict: holds. confidence: high.

What the script now does (I1). `restore_guards` no longer trusts pre-transition IDs. `current(id, entry)` resolves the PC through `GetFirstPC`. It resolves a party member by the tag stored at guard time: first through `GetPartyMemberCount`/`GetPartyMemberByIndex`, then `GetObjectByTag` if `IsObjectPartyMember`. A stored ID is used only if it is still valid and its tag still matches. An entry that cannot be resolved is printed as `[cursed:boom] min-one-HP restore pending: <tag|PC> not found` and kept for the next settle, area enter or module load. Every other entry is restored in the same pass. If a blast reaches a pending creature under its new ID, `guard` carries the stored prior over instead of reading the stuck 1. All engine access stays in `q`/`call` over `nwscript.call`; `boundary_scan.py` reports 0 collisions for the new bytes. Header and README:13 say what is guaranteed, and that a save written inside the 3 s window and loaded in a new session is not covered.

N3: README:14 now says `OnCreatureAttacked` with the PC as victim was "not seen firing, verified 2026-09-16". The "everyone gets their old look back" claim is gone. A creature dead or gone at cleanup keeps its disguise and is logged, which matches `cursed.lua:134-136`. A failed removal is retried with no new copies until cleanup ends.
N5: README:13 and the header state that a member whose flag cannot be read (error or `false`) is left out of the blast.
N2: ledger references to `api-status.md:118`, `:150` and `host.cpp:296` now cite the `OnCreatureAttacked` / `OnModulePlayerLevelUp` rows and `Host::dispatch` / `DepthGuard` by name. Chain-reaction line numbers in the ledger are replaced by function names, since the edit moved them.

claim: validator passes on the current bytes, and Doppelganger is unchanged.
referent: `host-cmd bash -c 'cd <worktree> && /usr/bin/python3 tools/example_validation.py --luajit /usr/bin/luajit --host /home/brunner56/kp-validation-20260922-build/kp_luatest --receipt /home/brunner56/kp-live-20260922/example-host-receipt-20260927c.json'` printed `PASS: 41 original syntax/host regression sources, 93 per-file cases; 8 retired from public catalog; 0 live receipts attached; no public quality promotion`, exit 0. Receipt SHA-256 `e8786e0ab36d98edc5a68a35ba7fced998276dd7e6080807903c199ab346ba0f`, generated 2026-09-27T17:47:18Z at `ca329e5`, dirty diff `bfb15695…`. (A first run at 17:31:42Z, receipt `2e98f8d0…`, was overwritten after one README:13 wording fix: the script reuses a still-valid old ID whose tag matches, so "not by the old object ID" became "does not trust the old object IDs". Same PASS line.) Receipt entries: chain `24ad2057e6eb` with 10 cases (was 7), doppelganger `5d9864b22241` with 5 cases. `sha256sum 70_doppelganger.lua` = `5d9864b22241ff135d3bb0c1ecb3f2671af218b58cdf2f44eb7bc62c95f62c42`. `kp_luatest` = `9309dd6a3a5b…` before and after.
checked: the command above; case count 90 → 93 is the three new chain tests.
verdict: holds. confidence: high.

Still open: whether K1 re-IDs party objects on `StartNewModule` (unverified; the fix does not depend on it), live damage and restore readback, and the save-inside-3s case.

claim: the receipt binds the final tracked state of every validated file.
referent: a Python check recomputed SHA-256 for all 13 `validation_sources` and all 41 example sources in the receipt against the worktree: 0 mismatches. Manifest `67b08f4b…d5ef68e3`, `cursed.lua` `c29375de…`, `fixture.lua` `cb74dc7b…` (not edited this round).
checked: run after the 17:47:18Z validator run; the ledger and this report are untracked or ignored, so they do not enter the dirty diff.
verdict: holds. confidence: high.

Stale-reference sweep: `grep -rn "daed75d1|90 per-file|7 cases"` over `docs`, `scripts`, `tools` and `progress.md` has no hits after the ledger update.

Note for later (no code change): `OnAreaEnter` fires for any entering object (review A8). While a guarded member cannot be found, every creature entry and every settle prints "restore pending" again, which can repeat in the log if that member left the game for good.

## Round 3 (2026-09-27, sole writer): chain reaction PC identity

Review: `/home/brunner56/kp-live-20260922/example-fixes-r2-review.md` (Important: restore followed
whatever `GetFirstPC` returned; `pc_swap_probe.lua` printed `old_pc=1 replacement_pc=0`).
Files changed: `scripts/examples/cursed/40_chain_reaction.lua` (`current`, new locals `unclaimed`
and `owned`, two `owned[member] = true` lines in `guard`, header), `scripts/examples/cursed/README.md`
(row 13), `tools/tests/examples/cursed.lua` (3 new tests), `tools/tests/examples/manifest.json`
(chain sha, `party_survival` text), `docs/example-behavior-ledger.md`. `fixture.lua` and
`70_doppelganger.lua` untouched.

What changed. `current(id, entry)` checks the stored object first for every entry, PC included: if
`GetIsObjectValid(id)` and its tag still matches, that object is restored, whatever `GetFirstPC`
says. Only an entry whose object is gone is looked up again (PC through `GetFirstPC`, member through
the roster, then `GetObjectByTag`). A looked-up candidate is refused if the script has keyed any
entry on it this session (`owned`, set in `guard` on a fresh guard or a carry-over move, never
cleared). So a gone PC never writes its prior onto a companion the script guarded, in the first
pass or any later one; that entry stays "restore pending" instead. Pending/retry and the carry-over
in `guard` are otherwise unchanged. Why `owned` and not a strict tag match on the PC lookup: it does
not depend on K1's PC tag, which is unknown from here (the tests use `''` for both PC and
replacement). Its cost is grill #2 below. All engine access still goes through `q`/`call` over
`nwscript.call`; `rg` for Lua declarations named `Get*|Set*|Is*` finds only the old
`SETTLE_MS`/`settle_gen` constants.

Mid-round correction (advisor): my first fix (`24531c97…`) refused only objects that were live
guard keys at that moment. After Bastila's own entry was restored and removed, a second pass or a
blast let the gone PC's entry resolve to her and write 0. I extended the third test to cover a
second pass and a blast+settle; it went red on `24531c97…` ("…(second pass)",
`/home/brunner56/kp-live-20260922/example-fixes-r3b-red.out`), then added `owned`.

claim: the review probe is a host regression, red on the old logic and green on the final bytes.
referent: `/home/brunner56/kp-live-20260922/example-fixes-r3-red.out` (script `24ad2057…`, the
reviewed bytes: FAIL "module load restores the original PC while it is still valid; a new
GetFirstPC object is left alone" and FAIL "a PC swap onto another guarded member restores both
objects to their own priors", both "original PC left at min-one-HP 1").
`example-fixes-r3-green.out` (script `74c0ca1a…`): 13/13 chain cases PASS, and the reviewer's
unmodified `pc_swap_probe.lua` prints `old_pc=0 replacement_pc=1`.
checked: `host-cmd sh -c 'cd <worktree> && /usr/bin/luajit /tmp/kp-chain-only.lua <sources>'`.
verdict: holds. confidence: high.

claim: old-invalid → replacement still works (A1/P3).
referent: green out: "module load re-resolves a guarded party member whose object ID changed",
"module load re-resolves the guarded PC through GetFirstPC when its object ID changed" and "a
member that cannot be re-resolved is recorded and retried…" PASS.
checked: same run. verdict: holds. confidence: high.

claim: each new branch is load-bearing.
referent: `/home/brunner56/kp-live-20260922/example-fixes-r3-mutations.out`. `mut-pcfirst`,
`mut-noclaim` and `mut-liveonly` are built from the final bytes. `oldlogic` is not: it is the
reviewed `24ad2057…` `current` spliced into the superseded `24531c97…` file (no `owned` lines),
so it behaves like the reviewed code. It fails all three new tests.
`mut-pcfirst` (PC lookup before the stored-ID check) fails the two coexistence tests. `mut-noclaim`
(`unclaimed` = `valid`) fails "a gone PC is never resolved onto another member this script
guarded…" at "(first pass)". `mut-liveonly` (my first fix, live keys only) fails the same test at
"(second pass)".
checked: `/tmp/kp-chain-r3-{oldlogic,mut-pcfirst,mut-noclaim,mut-liveonly}.lua` via the runner.
verdict: holds. confidence: high. The blast+settle leg of that test is not isolated by a mutant
(`mut-liveonly` fails earlier, at the second pass).

claim: validator passes on the final bytes; Doppelganger unchanged.
referent: `host-cmd sh -c 'cd <worktree> && /usr/bin/python3 tools/example_validation.py --luajit
/usr/bin/luajit --host /home/brunner56/kp-validation-20260922-build/kp_luatest --receipt
/home/brunner56/kp-live-20260922/example-host-receipt-20260927d.json'` printed `PASS: 41 original
syntax/host regression sources, 96 per-file cases; 8 retired from public catalog; 0 live receipts
attached; no public quality promotion`, exit 0. Receipt SHA-256
`2a98839a01bbfc850bb9b46213485b6bc424a9e0c49806f6942f56a360dba021`, generated
2026-09-27T19:12:42Z at `ca329e5`, dirty diff `850863e9…`. (It overwrote a 18:42:38Z run, receipt
`4fe1b967…`, taken on the superseded `24531c97…` bytes.) Chain `74c0ca1ac5dd` 13 cases (was 10),
doppelganger `5d9864b22241` 5 cases; `sha256sum 70_doppelganger.lua` =
`5d9864b22241ff135d3bb0c1ecb3f2671af218b58cdf2f44eb7bc62c95f62c42`. `kp_luatest` `9309dd6a…`.
Python recheck of the receipt: 13 `validation_sources` and 41 example hashes, 0 mismatches.
Manifest `8e787165…bcb9a9ec`, `cursed.lua` `61b07d84…`, `fixture.lua` `cb74dc7b…` (unchanged).
checked: the command above; 93 → 96 is the three new chain tests. The `git diff HEAD --binary`
step inside the validator takes 10+ minutes on the MyBook disk.
verdict: holds. confidence: high.

Still open (unchanged by this round): whether K1's `GetFirstPC` can change while the old PC object
stays valid at all, live damage and restore readback, and the save-inside-3s case.

### Grill me

1. Two gone entries resolving to the same new, never-owned object (a gone PC and a gone member
   whose stored tag matches that object): both write it, last one wins. Unverified as reachable;
   no test. A case where both resolve to one ID would settle it.
2. Could `owned` block a legitimate lookup? Only if K1 hands a returning PC or member an ID the
   script already keyed an entry on this session. Then the entry stays "restore pending" and
   nothing is overwritten (fails safe, but that creature keeps min-one-HP until unload). ID reuse
   across a load: unverified. A live before/after `GetFirstPC`/`GetTag` readback settles it.
3. How come a valid stored ID with the same tag counts as "the same actor"? Tag is the only
   identity the script keeps; a reused ID with a different tag falls through to lookup (`current`,
   first line). Same-tag reuse: unverified, same live check as #2.
4. Is there a reason a gone PC stays pending rather than taking a guarded Bastila? Her own entry
   holds her prior; writing the PC's prior onto her clobbers it, and my first fix still did so on
   the second pass. Referent: test "a gone PC is never resolved onto another member this script
   guarded…", `mut-liveonly` line in `example-fixes-r3-mutations.out`.
5. Does `guard`'s carry-over still work? Yes: a pending entry resolves to a new, never-owned ID.
   Referent: "a member that cannot be re-resolved…" PASS in the green run.

Unsettled question for the reviewer: can K1 change `GetFirstPC` while the old PC object is still
valid, or reuse an ID across a load? Single check: a live identity readback before/after a party
leader swap and a module load.

## Round 4 (2026-09-27, sole writer): chain reaction identity epochs

Review: `/home/brunner56/kp-live-20260922/example-fixes-r3-review.md` (FAIL. Important R3-2/R3-3: the
session-wide `owned` ID set left a PC or companion that came back under a recycled ID permanently
pending. Unload dropped the record, and the next blast read the stuck 1 as the prior. Minor: R3-1,
R3-4 docs, R3-5.) Orchestrator ruling followed: identity epochs, truthful prior, loud unload,
party-only candidates.
Files changed: `scripts/examples/cursed/40_chain_reaction.lua` (`74c0ca1a…` → `e7b65781…`),
`scripts/examples/cursed/README.md` (row 13), `tools/tests/examples/cursed.lua` (9 new chain tests,
`61b07d84…` → `34ec0977…`), `tools/tests/examples/manifest.json` (chain sha, `party_survival` text,
`8e787165…` → `1ec55bdb…`), `docs/example-behavior-ledger.md`. `fixture.lua` (`cb74dc7b…`) and
`70_doppelganger.lua` (`5d9864b22241…`) are untouched.

What changed in the script:
- `owned`, `unclaimed` and `current` are removed. The `guarded[id]` table is replaced by an array,
  `guards`, of `{ id, epoch, tag, pc, prior }`.
- `epoch` is bumped in `OnModuleLoad` and `OnAreaEnter` before `disarm()`. `disarm` still starts
  with `restore_guards()`, so the M1 mutant's text substitution still applies.
- `find(entry)` tries candidates in this order:
  1. the stored ID, only when `entry.epoch == epoch`
  2. `GetFirstPC`, only for a PC entry
  3. the roster by tag
  4. `GetObjectByTag`

  Every candidate must pass `fits`: valid, `IsObjectPartyMember`, and the same tag. An old ID is
  never trusted after a transition.
- `resolve_all()` resolves every entry in one pass. If two or more entries land on one creature,
  its prior is unknown. `restore_guards` then writes 0 (the NWScript default), logs "prior unknown"
  and drops those entries.
- `guard`:
  - An entry from the current epoch with the same ID means the creature is already guarded.
  - An entry that resolves to the member carries its prior over and is rebound to the member's ID
    and the current epoch.
  - If more than one entry resolves to the member, one record is kept with prior unknown.
  - Otherwise the flag is read. A read of 1, when an entry that could not be resolved has the same
    tag, is treated as the script's own flag, not as a prior. This is the untagged-member case.
  - An unreadable flag still leaves the member out of the blast (A6).
- `OnScriptUnload` restores what it can find. For each entry left over it prints "min-one-HP NOT
  restored at unload: <who> …", with the F12 console line that clears it:
  - `nwscript.call("SetMinOneHP", nwscript.call("GetObjectByTag", "<tag>", 0), <prior>)`
  - `GetFirstPC` for an untagged PC
  - never a stale numeric ID

  Then it clears `guards`.
- NWScript is still reached only through `q`/`call` over `nwscript.call`. The reviewer's greps find
  no `Get*/Set*/Is*` Lua names except `SETTLE_MS` and `settle_gen`.

Why the round-2 and round-3 tests stay green without trusting IDs across a load: in pc_swap, the
old PC (id 1) is not in `f.party={7,2}`, so it is found by its tag `pc` through `GetObjectByTag` with
party confirmation. In "a PC swap onto another guarded member", it is found by tag in the roster
`{1,2}`. `GetFirstPC`=2 is refused because its tag is `bastila`. The first test's carth (id 3, not in
`f.party`) is found through `GetObjectByTag`. In none of these cases is the stored ID used after the
epoch bump.

claim: R3-1, R3-2, R3-3, R3-4 and R3-5 are host regressions. They fail on the reviewed bytes and
pass on the final bytes.
referent: `/home/brunner56/kp-live-20260922/example-fixes-r4-red.out`: chain `74c0ca1a…` with
`cursed.lua` `34ec0977…`, 8 FAIL and 14 PASS.
- The 8 failures are R3-1, R3-2, R3-3, R3-5, R3-4 (unload names the creature and gives the fix),
  "an old ID recycled onto another untagged party member…", "two entries that resolve to one
  creature…" and "an untagged member that cannot be found…".
- The ninth new test, "a non-party creature with the companion tag is never taken…", passes on the
  old bytes too. It guards the `fits` party check (see the mutants below).

`example-fixes-r4-green.out`: chain `e7b65781…`, 22/22 PASS. That covers the 13 earlier cases (A1,
P3, pc_swap and the round-3 tests) plus the 9 new ones.
checked: `host-cmd sh -c 'cd <worktree> && /usr/bin/luajit /tmp/kp-chain-r4-runner.lua <map>'`,
with stdout written to a file on the host. Piped stdout from `host-cmd` lost lines in two runs, so
only the file outputs count.
verdict: holds. confidence: high.

claim: the reviewer's probes, rerun unmodified, all hold.
referent: `/home/brunner56/kp-live-20260922/example-fixes-r4-probes.out` (the reviewer's command:
`chain_attacks.lua`, `pc_probe.lua`, `mutations.lua`, `pc_swap_probe.lua`, `r3_probes.lua`).
- A1–A8, P1–P3 and M1–M3 all hold.
- `old_pc=0 replacement_pc=1`.
- R3-1: `sets=[11<-0 12<-1] old_pc(11)=0`.
- R3-2: `after_load=0 after_blast_settle_unload=0 pending_logs=0 sets=[2<-0 2<-1 2<-0]`.
- R3-3: `bastila(1)=0 pending=false`.
- R3-5: `sets=[5<-0] impostor(2)=1 real_bastila(5)=0`.
- R3-4 still prints `bastila_flag=1`. That is the documented limit: the creature is absent at
  unload, and the new "NOT restored at unload" line names it.
checked: same file. verdict: holds. confidence: high.

claim: each new branch is load-bearing.
referent: `/home/brunner56/kp-live-20260922/example-fixes-r4-mutations.out`. The mutants are
`/tmp/kp-chain-r4-mut-*.lua`, each a one-line edit of the final bytes.

| mutant | edit | failing tests |
|---|---|---|
| `idtrust` | trust the stored ID across epochs | "old ID recycled onto another untagged party member" |
| `bumpafter` | restore before the epoch bump in `OnModuleLoad` | the same test |
| `noparty` | drop `IsObjectPartyMember` from `fits` | "non-party creature with the companion tag…" |
| `idtrust-noparty` | both of the above | R3-5 as well |
| `pcnotag` | `GetFirstPC` without the tag check | pc_swap, PC swap onto a guarded member, gone PC never resolved onto a member, R3-1 |
| `nocollide` | no collision rule | "two entries that resolve to one creature…" |
| `nountaggedcarry` | no untagged carry | "an untagged member that cannot be found…" |
| `nounloadlog` | no unload log | R3-4 |
| `nobytag` | no roster/`GetObjectByTag` lookup | party min-one-HP guard after transition; original PC restored while still valid |

The advisor flagged `idtrust` and `bumpafter` as passing every test at first. I added the
recycled-untagged test for them, and `noparty` got its own test.
checked: same file. verdict: holds. confidence: high.

claim: the validator passes on the final bytes, and Doppelganger is unchanged.
referent: `/home/brunner56/kp-live-20260922/example-fixes-r4-validator.out`.
- Output: `PASS: 41 original syntax/host regression sources, 105 per-file cases; 8 retired from
  public catalog; 0 live receipts attached; no public quality promotion`, exit 0.
- Receipt `/home/brunner56/kp-live-20260922/example-host-receipt-20260927e.json`, SHA-256
  `b28ca4bf96f6faa0ef25bb0020b6205ec1fc6cbec6b3bc9754bfe9681cafd43d`.
  - Generated 2026-09-27T23:09:26Z at `ca329e52`, dirty diff `162fd55b…`.
  - It contains chain `e7b65781ca5b` (`examples[11]`), doppelganger `5d9864b22241` (`examples[14]`),
    manifest `1ec55bdb…`, `cursed.lua` `34ec0977…`, `fixture.lua` `cb74dc7b…` and `kp_luatest` `9309dd6a`.
- 96 → 105 is the 9 new chain cases.
- The ledger and this report were edited after the run, so the dirty diff will not match a rerun.
checked: `host-cmd sh -c 'cd <worktree> && /usr/bin/python3 tools/example_validation.py --luajit
/usr/bin/luajit --host /home/brunner56/kp-validation-20260922-build/kp_luatest --receipt
/home/brunner56/kp-live-20260922/example-host-receipt-20260927e.json'`.
verdict: holds. confidence: high.

Closeout after the rate-limit cut (resumed writer):
- The first round 4 bytes (`047e3790…`) were changed once more, in `resolve_all`: `table.insert(claims[m], entry)` became an explicit `list[#list + 1] = entry`. Behavior is the same. The previous writer left no reason (unverified). Red, green, probes and all 9 mutants were rerun on `e7b65781…` at 15:09. `example-fixes-r4-green.out` prints that sha, and each `/tmp/kp-chain-r4-mut-*.lua` differs from `e7b65781…` by one line (two for `idtrust-noparty`). Every mutant is still caught.
- The first 20260927e receipt (`8d684683…`, 19:57:51Z) bound `047e3790…` and is overwritten. Two reruns at 15:14 and 15:20 local failed: `evidence_test.py` hit the validator's 90 s subprocess timeout under host load. It passes in 22 s alone now (`Ran 14 tests … OK`, load average 77). The rerun at 23:09:26Z passed and wrote the receipt above. `example-fixes-r4-validator.out` holds that run and ends with `exit=0`.

Naming: `rg -n 'nwscript\.'` finds only `q`/`call` (lines 68–75) and the strings in the unload
message (258–262). `rg -n -i '(Get|Set|Is)[A-Za-z0-9_]+\s*='` finds only `PARTY_DIVISOR`, `SETTLE_MS`
and `settle_gen`. `PARTY_DIVISOR` matches only because of the case-insensitive "is" in "DivISor". It
is an old constant.

Still open: whether K1 reuses numeric IDs across a load, the PC's real tag in K1, live damage and
restore readback, and the save-inside-3s case.

### Grill me

1. Is the untagged carry in `guard` truthful? Case: a flag reads 1 on an untagged member, and some
   other untagged entry could not be resolved. The script takes that entry's prior. If the member
   really is a different creature with a genuine 1, it later gets 0. Unknown is also 0, so both
   choices clear it. The tag is the only identity the script keeps after a transition. Referent:
   test "an untagged member that cannot be found after a load keeps its first prior…". Whether K1
   companions are ever untagged: unverified.
2. How come `OnAreaEnter` bumps the epoch when any object enters? A8 already disarms on any enter
   (pre-existing). After a bump, tagged members and a PC are found again by tag. Only an untagged
   non-PC member goes pending until unload. Referent: A8 HOLDS in `example-fixes-r4-probes.out`,
   plus the header's "Not covered" list. The alternative, an `entering == GetFirstPC` filter, is
   untested and out of scope.
3. Does the PC entry depend on K1's PC tag? It uses the stored tag in every lookup. If K1's PC tag
   is `""` and a control swap leaves another untagged member as `GetFirstPC`, the two records
   collide. The creature then goes to 0 and a "prior unknown" line is logged. Referent: test "two
   entries that resolve to one creature…". K1's PC tag: unverified.
4. Is there a reason unload does not keep the prior somewhere durable, like a local on the
   creature? That would write new state into saves and needs a slot the script does not own. The
   ruling asked for a loud log. Referent: R3-4 test and `r3_probes` R3-4 `bastila_flag=1`.
5. Is `GetObjectByTag(tag, 0)` enough when two creatures share a tag? It returns only the first,
   and the roster scan runs before it. A non-party first match is refused, and the entry stays
   pending even if a second match is the real companion. Referent: test "a non-party creature with
   the companion tag…". Unverified whether K1 ever has two same-tag creatures, one of them the
   companion.

Unsettled question for the reviewer: does K1 recycle numeric IDs across a load, and what is the
PC's tag? Single check: a live readback of `GetFirstPC`, each party member's ID and `GetTag`,
taken before and after one module load.

## Round 5 (redesign) (2026-09-27, sole writer): chain reaction leaves the party out

Ruling (orchestrator, after four review rounds; criterion blast radius + reversibility): the example
must never change the PC's or a party member's min-one-HP flag, or any other creature state it would
have to put back. The PC and party are left out of blast damage and chain triggering, judged at blast
time by `GetFirstPC` and `IsObjectPartyMember`.

Files (no git writes, no game, live-game lock untouched):
- `scripts/examples/cursed/40_chain_reaction.lua`: `e7b65781ca5b…` -> `9152960ef3c02818f78146289ba0bc709a727a3c7751839352ea2ccb99ae6d8c`.
  Round-4 bytes kept at `/home/brunner56/kp-live-20260922/review-probes-examples-r5/chain_r4_e7b65781.lua` for comparison.
- `tools/tests/examples/cursed.lua` (`56165e59420a…`): the 17 restore cases are gone, and 10 exclusion cases are new. The spec-loop `boom` branch is rewritten.
- `tools/tests/examples/manifest.json` (`c3766715…c3e4ea77`): chain sha, plus the `damage_readback` and `party_survival` texts. Predicate IDs are unchanged.
- `scripts/examples/cursed/README.md`: chain row.
- `docs/example-behavior-ledger.md`: header, receipt, chain row and curation note.
- `fixture.lua` is unchanged (`cb74dc7b…`). `70_doppelganger.lua` is still `5d9864b22241ff135d3bb0c1ecb3f2671af218b58cdf2f44eb7bc62c95f62c42`.

What changed in the script:
- Removed: `guards`, `epoch`, `settle_gen`, `find`, `resolve_all`, `drop`, `guard`, `restore_guards`, `label`, `fits`, `tag_of`, `chain_settle` and its timer, `OnScriptUnload`, `PARTY_DIVISOR` and local 6.
- `spared(o)` runs right before each hit and once per corpse in `OnRunScript`. It reads `GetFirstPC` and `IsObjectPartyMember` at that moment.
  - A yes to either leaves the creature out.
  - So does an error or an unrecognised answer.
  - `in_party` uses its own `pcall(nwscript.call, "IsObjectPartyMember", o)`, because `q()` folds `false` into nil. A boolean `false` therefore means "not in the party".
- `exploded[]` is emptied on `OnModuleLoad` and on `OnAreaEnter` with `from_save_game == 1`. The compare is to 1 because 0 is truthy in Lua.
- `OnAreaEnter(area, entering, from_save_game, relevant)` now matches `docs/lua-api.md:471`. Any enter still disarms (A8, as before).
- Visible behaviour kept: thermal/frag VFX, the fade, 40 fire damage in 7 m, arming, the oracle line and local 7.
- Changed by the ruling: the party takes no damage, and local 6 is no longer written.

### Tests

Chain cases: 15/15 PASS (`/home/brunner56/kp-live-20260922/r5-chain-tests.out`, first line `cursed.lua 56165e59420a chain 9152960ef3c0`). New cases:
- static: no `MinOneHP` substring anywhere in the file (comments included), every `nwscript.X` is `call`, and no Lua name defined in the file appears as a routine in `src/generated/routines_k1.inc`
- hostiles chain; the PC, a tagged member and an untagged member are never hit, and their flags are never read or set
- after a module load: a member re-created under a new ID is left out, an old party ID now on a hostile is hit, and a recycled corpse ID detonates again (R4-7)
- leader swap: `GetFirstPC` alone keeps out a controlled creature that answers "not party", and membership alone keeps out the real PC
- within one module, with no load: a member who left the party is hit and detonates, a hostile who joined and a new member are spared, and a former leader is hit. This kills any design that stores answers by ID.
- shared tags and untagged hostiles are judged by membership only
- a death during a module transition does nothing
- unload mid-chain leaves nothing to put back, and no timer exists
- `OnAreaEnter` `from_save_game` 0 vs 1
- party answers: error / unknown / boolean false

The oracle records every `ApplyEffectToObject` whose target is the current `GetFirstPC` or a current fixture party member. It checks the list after the scenario. An assert inside the override would be swallowed by the script's `pcall`. The first draft had that bug, and the no-firstpc mutant exposed it.

Mutants (`/home/brunner56/kp-live-20260922/review-probes-examples-r5/mutants.out`, driver `run_mutants.sh`). Every one is killed, and the current bytes pass 15/15:

| mutant | killed by |
|---|---|
| drop the `o == pc` clause | leader swap, same-module (2 fails) |
| drop the party clause | 11 fails, including hostiles-chain, leader swap, tags |
| drop the `OnModuleLoad` clear | after-a-module-load / R4-7 |
| `if from_save_game then` (truthy) | OnAreaEnter from_save_game |
| fail open (`in_party(o) == true`) | party answers |
| boolean false read as unknown | party answers |
| cache `spared` by ID until module load | same-module, party answers |
| cache `IsObjectPartyMember` by ID until module load | same-module only (passes the other 14) |

### Prior reviewer probes on the new bytes

Runner: `/home/brunner56/kp-live-20260922/review-probes-examples-r5/run_blocks.lua`.
- It runs each top-level `do … end` block in isolation, so one restore-only assert cannot hide the blocks after it.
- It adds an independent check per block: min-one-HP calls, and effects on the current `GetFirstPC` or a current party member.
- Output:
  - `prior_probes.out` (strict)
  - `prior_probes_tolerant.out` (with `KP_TOLERANT=1`, a missing timer fires as a no-op, a missing `OnScriptUnload` is a no-op, and the probe's own `assert` logs `PROBE-ASSERT-FAILED` instead of throwing, so every scenario runs to its end)
  - Driver: `run_prior.sh`
- Result: all 38 blocks give `SAFETY minonehp_calls=0 party_or_pc_effects=0` in both modes. That is 35 chain blocks plus 3 `mutations.lua` blocks.
- In tolerant mode all 35 chain blocks run to their end. The only two `ERROR` lines are M2/M3, which are airstrike and unmapped here.

| probe | verdict on 9152960e | reason |
|---|---|---|
| A1, A2, A3, A4, A5 | N/A by design | They measure the restore of a flag the script no longer sets. Replaced by the after-a-module-load, unload mid-chain and hostiles-chain cases. |
| A6 | holds | Its assertion is 0 SetMinOneHP calls. |
| A7 | N/A by design | Party damage 13 is now 0. Replaced by the hostiles-chain case (no damage on 1/2/3). |
| A8 | holds | Any enter still disarms. |
| P1, P2, P3 | N/A by design | PC restore. The PC is never set. Replaced by the leader-swap and after-load cases. |
| M1 | N/A by design | It mutates `restore_guards`, which no longer exists ("mutation not applied"). |
| M2, M3 | N/A (scope) | Airstrike probes. The file is untouched this round. The runner's map is chain-only. |
| pc_swap_probe | N/A by design | It asserts the PC was guarded. Replaced by the leader-swap case. |
| R3-1 to R3-5 | N/A by design | ID re-resolution for restore. In tolerant mode R3-2 and R3-5 log their "was guarded" precondition and run to the end with `sets=[]`. |
| R4-1a to R4-1c, R4-1b(a/b/b2), R4-1L | N/A by design | PC tag and swap restore. The script reads no tag. Flags stay at the preset value (`pc1=nil`, i.e. never written). |
| R4-2, R4-2b, R4-2L | N/A by design | The same-tag pair. Tolerant mode gives `after=0,0 sets=[]`. |
| R4-3 | applies, covered | Its setup is a member leaving the party mid-window. It is covered by the "within one module…" case (the member who left is hit, and the one who joined is spared). |
| R4-3b, R4-4, R4-5, R4-6, R4-6b, R4-6c | N/A by design | These probe restore and pending behaviour. R4-4b holds (EffectDamage delta 0 during the load window). |
| R4-7 | **fixed** | `detonations before=1 after=2`. It is now a host case. |
| R4-8, R4-8d, G1 | N/A by design | The misdirected-write class. `sets=[]` and `member5=1` stay untouched. |

### Validator

Command: `host-cmd sh -c 'cd <worktree> && /usr/bin/python3 tools/example_validation.py --luajit /usr/bin/luajit --host /home/brunner56/kp-validation-20260922-build/kp_luatest --receipt /home/brunner56/kp-live-20260922/example-host-receipt-20260927f.json'`
- It exited 0 with `PASS: 41 original syntax/host regression sources, 98 per-file cases; 8 retired from public catalog; 0 live receipts attached; no public quality promotion`. The output is in `review-probes-examples-r5/validator.out`.
- `evidence_test.py` ran inside the run, "Ran 14 tests in 4.629s", OK, with no timeout.
- Receipt `example-host-receipt-20260927f.json`, generated 23:59:58Z: SHA-256 `79701638b22cc98f77b9613cca37fcd0327177f45b2c76b2a49ea87767a9905a`, dirty diff `25ba32f4…`. It overwrote a first 20260927f receipt (`b46060c3…`, 14 cases) from before the same-module case.
  - Chain `9152960ef3c0`, with its 15 cases listed.
  - Doppelganger `5d9864b22241`.
  - Manifest `c3766715`, `cursed.lua` `56165e59`, `fixture.lua` `cb74dc7b`.
  - `e7b65781` does not appear.
- Editing the ledger (untracked) and this report (ignored by `.superpowers/sdd/.gitignore`) after the run leaves the dirty diff unchanged.

Stale outside my allowed files (not edited):
- `scripts/harness/scenarios/cursed/40_chain_reaction.toml`: the last step gates on PC local 6 >= 10 ("party damage"). It will fail live now.
- `docs/showcase-demos/cursed.md:31,50`: still describe party damage.

### Grill me

1. **What if `IsObjectPartyMember` answers wrong inside the hook?**
   - A 0 for a companion would put that companion in the blast at full damage.
   - That is not new. Rounds 1-4 used the same answer to decide who got the floor, and a wrong 0 meant full damage then too. The redesign adds the `GetFirstPC` clause, so the controlled character is safer than before.
   - An error or an odd value fails closed, and the curse goes quiet.
   - Referent: the "party answers" case covers error, unknown and false.
   - Live evidence that it answers 1 for party in `OnRunScript`: the round-1 bytes `a346b5a8` used the same routine to pick party victims, and run `20260922-101511` published party damage (`docs/showcase-demos/cursed.md:50`).
   - Whether it answers 0 wrongly for a companion in some state (for example one not yet joined after a load): unverified. `GetIsEnemy` gave a wrong answer inside a hook once (probe M2, 2026-09-16).
2. **Why aren't the PC local-number writes (5 = armed, 7 = count) "state it would have to restore"?**
   - They are the script's own published counters, written since HEAD, and the harness reads them.
   - No gameplay rule reads them, and a stale value changes no creature behaviour.
   - They do persist into a save.
   - Referent: `grep -n SetLocalNumber` gives lines 104, 111 and 156 of the new file.
   - If the ruling means "no persistent writes at all", these must go too. That would break the harness gates.
3. **How come any `OnAreaEnter` still disarms?**
   - It kept the pre-existing behaviour (A8 holds) under the "keep visible behaviour" rule.
   - A creature spawning in-module pauses the curse for 200 ticks.
   - Only `exploded[]` clearing is gated on `from_save_game == 1`.
   - Referent: the OnAreaEnter case. Whether `from_save_game` is ever 1 on the PC's enter after a load: unverified live.
4. **Is dropping local 6 a visible-behaviour change beyond the ruling?**
   - The party taking no damage is the ruling, so "requested party damage" is always 0.
   - Writing a constant 0 would keep the harness gate failing anyway, just less obviously.
   - Referent: the harness toml's last step, listed above as stale.
5. **Does reading `GetFirstPC` per victim (not once per blast) break the "transient PC failure" retry?**
   - No. The third read is still `detonate`'s own, and the test passes (case 3 of 15).

Unsettled, and the single check that settles it: does `IsObjectPartyMember` answer 1 for every companion, and 0 for hostiles, inside `OnRunScript` in live K1? One live readback in a chained kill settles it: log both answers per victim.

## Round 5 follow-up

Fixed the two stale references the round-5 review flagged. `40_chain_reaction.lua`
was not touched (still `9152960ef3c0`); `70_doppelganger.lua` was not touched
(still `5d9864b22241`).

### Files, before/after

**`scripts/harness/scenarios/cursed/40_chain_reaction.toml`** (last step)

Before:
```
label = "the party was inside at least one blast (script-reported party damage in local number 6) and the player lives"
code = "local pc=nwscript.call('GetFirstPC'); return nwscript.call('GetIsDead',pc)~=1 and nwscript.call('GetLocalNumber',pc,6) >= 10"
```

After:
```
label = "the player and every party member survived the fight (the round-5 redesign excludes the PC and party from blast damage entirely, so the script no longer records a damage counter; nothing here can tell blast damage apart from ordinary trooper attacks, so we check survival, not zero HP loss)"
code = "local pc=nwscript.call('GetFirstPC'); if nwscript.call('GetIsDead',pc)==1 then return false end; local n=nwscript.call('GetPartyMemberCount'); for i=0,n-1 do local m=nwscript.call('GetPartyMemberByIndex',i); if nwscript.call('GetIsObjectValid',m)==1 and nwscript.call('GetIsDead',m)==1 then return false end end; return true"
```

Rationale: the script now writes only local 5 (armed flag) and local 7
(detonation count) — `grep -n SetLocalNumber scripts/examples/cursed/40_chain_reaction.lua`
gives lines 104, 111, 156, none touching slot 6. There is no engine-readable
signal in this arena that isolates blast damage from the ordinary trooper
attacks the PC and party take during ​`clear_room` (both are real combat, and
the route has no per-effect damage-type readback), so the gate asserts what
is honestly checkable: the PC and every current party member are alive at
the end of the fight. This keeps the earlier `>= 3 detonations` gate (local 7,
unchanged) as the only counter-based check.

**`docs/showcase-demos/cursed.md`**

Line 31 (table), before:
```
| 40 chain reaction | >= 3 detonations; party damage >= 10 and PC alive | ship |
```
after:
```
| 40 chain reaction | >= 3 detonations; PC and party excluded from blast, both alive | ship |
```

Line 50 (historical note), before:
```
- **40 chain reaction**: 11/11; 6 detonations, party damage published.
```
after:
```
- **40 chain reaction**: 11/11; 6 detonations. Round 5 redesign: the PC and party take no blast damage. The script checks each victim against `GetFirstPC` and `IsObjectPartyMember` right before the hit, so it never damages them in the first place. There is no more damage counter to publish.
```

Left untouched (out of scope, historical ledger entries that already
document this exact staleness in past tense): `docs/example-behavior-ledger.md:139,259`
and `docs/original41-live-evidence-audit.md:28`.

### Validation

- Harness loader (`PYTHONPATH=scripts/harness`, `kpharness.scenario.Scenario.load`)
  parses the edited toml cleanly: 11 steps, no schema error.
- `TMPDIR=/home/brunner56/kp-live-20260922/tmp-chainfu` (created), ran on the
  host via `/home/brunner56/.local/bin/host-cmd`:
  `python3 tools/example_validation.py --luajit /usr/bin/luajit --host
  /home/brunner56/kp-validation-20260922-build/kp_luatest --receipt
  .../receipt-followup.json` → `PASS: 41 original syntax/host regression
  sources, 98 per-file cases; 8 retired from public catalog; 0 live receipts
  attached; no public quality promotion` — byte-identical PASS line to the
  round-5 receipt.
- Diffed the fresh receipt against `example-host-receipt-20260927f.json` key
  by key: `git_commit` matches (`ca329e52…`); all 41 `examples[]` entries are
  identical, including `cursed/40_chain_reaction.lua` (still `9152960ef3c0`,
  `syntax`/`host` both `passed`). Only expected fields differ:
  `generated_utc`, the `commands` list (different absolute run paths),
  `dirty_diff_sha256`. One unexpected diff: `tools/tests/examples/object_blaster.lua`
  hash differs (`119cfb38…` in the reference vs `77cf0bc5…` here) — confirmed
  via `git status --porcelain` that this file is untracked (`??`) in this
  worktree, i.e. pre-existing dirty state from before this session, not
  something this follow-up touched.
- `grep -rn "party damage" scripts/harness/scenarios/cursed/40_chain_reaction.toml docs/showcase-demos/cursed.md` → no hits.

### Grill me

1. **Is "PC and party alive" a weaker check than "PC and party not damaged"?**
   Yes, honestly. It cannot detect a companion taking damage from a stray
   blast and surviving — only a kill. I chose this over guessing at a
   damage-isolation signal that does not exist in this route (combat damage
   from the six troopers and blast damage are both plain `EffectDamage` with
   no readback distinguishing cause). Referent: no `GetLastDamager` or
   per-effect-type query is used anywhere else in this repo's toml routes
   either (`grep -rn GetCurrentHitPoints scripts/harness/scenarios/` shows
   every existing "no damage" check is a same-target before/after HP compare
   around a single isolated action, not an open melee fight). Unverified
   whether a live run would ever actually show a companion HP dip from this
   script (no game, per this task's constraints).
2. **Why not also assert on the printed `[cursed:boom] ... 0 hit` case (zero
   victims) as evidence the party was excluded?** That line only appears in
   `kotorphasor.log`, not through `nwscript.call`, and this task's own Lua
   constraint for routes is `kp.* plus nwscript.call only` — no log-line
   assertion mechanism was available to reach for without inventing one.
   Unverified whether the route runner exposes oracle-line assertions
   elsewhere; a quick grep of `scripts/harness/scenarios/cursed/*.toml`
   found none using log-line matches, only `assert_lua`.
3. **Could `GetPartyMemberByIndex` include the PC at index 0, double-counting
   the alive check?** Possibly (based on `scripts/harness/demo_lib.sh:97`'s
   `if m~=pc and IsObjectPartyMember(m)==1` pattern, which explicitly guards
   against that). Harmless here: checking `GetIsDead(pc)` twice is not a
   correctness bug, just redundant, and the loop only returns `false` (fails
   the gate) if any member is dead — a duplicate live PC check never causes
   a false pass or false fail.
4. **Did I touch `40_chain_reaction.lua` or `70_doppelganger.lua`?** No.
   `sha256sum` on both matches the required values exactly (checked at the
   start of this follow-up and unchanged since): `9152960ef3c02818f78146289ba0bc709a727a3c7751839352ea2ccb99ae6d8c`
   and `5d9864b22241ff135d3bb0c1ecb3f2671af218b58cdf2f44eb7bc62c95f62c42`.

Grill me
