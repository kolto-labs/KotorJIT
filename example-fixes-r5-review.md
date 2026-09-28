# Example fixes round 5 (redesign) review

Scope: independent spec + adversarial review of `scripts/examples/cursed/40_chain_reaction.lua`
against the orchestrator's ruling (PC/party excluded from blast damage and chain triggering,
judged live via `GetFirstPC`/`IsObjectPartyMember`, no stored IDs, all guard/restore/epoch
machinery removed, `exploded[]` cleared on load, `OnAreaEnter` signature per
`docs/lua-api.md:471`). Read-only on the worktree; no git writes; no game; live-game lock
untouched.

## Independent view, formed before reading the writer's Grill section in detail

Read the script cold first (`scripts/examples/cursed/40_chain_reaction.lua`, lines 1-168).
Design is simple and matches the ruling on its face:

- `spared(o)`: `pc = q("GetFirstPC")`; if `pc == nil` or `o == pc`, spared. Otherwise
  `in_party(o) ~= false`. `q()` swallows pcall errors as `nil`, so a `GetFirstPC` failure fails
  closed (spared, not detonated/damaged) — correct direction for "never mutate/damage the
  party."
- `in_party(o)`: its own `pcall`, returns `true`/`false`/`nil` (nil on error or on any value that
  isn't `0/1/true/false`). `spared` treats `nil` as "spared" — fails closed on odd bridge
  answers, matches the ruling's "no clear answer -> skip."
- No stored per-object IDs anywhere except `exploded[corpse]`, keyed by the corpse's own ID,
  cleared in `OnModuleLoad` and in `OnAreaEnter` when `from_save_game == 1` (compared to `1`
  because `0` is truthy in Lua — commented explicitly at line 114-115).
- `guards`/`epoch`/`restore_guards`/`OnScriptUnload`/`PARTY_DIVISOR` etc. from rounds 3-4: grepped
  for `guard|epoch|OnScriptUnload|PARTY_DIVISOR` in the current file — zero matches. Fully
  removed.
- `OnAreaEnter(area, entering, from_save_game, relevant)` — checked against
  `docs/lua-api.md:471` directly: the doc table lists exactly `area, entering (object, caller),
  from_save_game (int, int_params[0])`, "Returns: nothing." Matches.

This reads as a correct, much simpler redesign that trades "the example restores everything it
touched" for "the example never touches party/PC state in the first place" — a strictly smaller
blast radius, which is what the criterion asked for.

## Checks performed independently (not just reading the writer's evidence files)

1. **Byte identity of the deliverables**, computed fresh in this session:
   - `scripts/examples/cursed/40_chain_reaction.lua` sha256 =
     `9152960ef3c02818f78146289ba0bc709a727a3c7751839352ea2ccb99ae6d8c` — matches claim exactly.
   - `scripts/examples/cursed/70_doppelganger.lua` sha256 =
     `5d9864b22241ff135d3bb0c1ecb3f2671af218b58cdf2f44eb7bc62c95f62c42` — matches claim exactly
     (untouched this round).
   - `tools/tests/examples/cursed.lua` = `56165e59420acb0c...` (matches), `manifest.json` =
     `c376671586df7a79...c3e4ea77` (matches), `README.md` and `example-behavior-ledger.md` present
     and consistent with claim.
   - `tools/tests/examples/fixture.lua` = `cb74dc7b22f3d955...` — matches "unchanged this round"
     claim (it does differ from git HEAD, but that's from an earlier round, consistent with the
     round-4 report which already carried this same fixture sha).
   - Receipt `/home/brunner56/kp-live-20260922/example-host-receipt-20260927f.json` sha256 =
     `79701638b22cc98f77b9613cca37fcd0327177f45b2c76b2a49ea87767a9905a` — matches claim exactly.

2. **Static safety greps**, run directly against the final bytes:
   - `grep -n -i minonehp` — zero hits.
   - `grep -n "nwscript\."` — only `nwscript.call` (the two `type(nwscript.call)` guards and the
     two `pcall(nwscript.call, ...)` calls). No other `nwscript.X`.
   - No Lua `function`/`local` name in the file collides with an entry in
     `src/generated/routines_k1.inc` (same check the file's own new static test performs; verified
     by reading `tools/tests/examples/cursed.lua:199-209`, which is a real, checked assertion, not
     a comment).
   - `grep -n "guard\|epoch\|OnScriptUnload\|PARTY_DIVISOR"` — zero hits: all round 3/4 machinery
     is gone.

3. **Validator rerun**, independent of the writer's run, via
   `host-cmd sh -c 'cd <worktree> && python3 tools/example_validation.py --luajit /usr/bin/luajit
   --host .../kp_luatest --receipt <fresh path>'`:
   - Exit 0. Output: `PASS: 41 original syntax/host regression sources, 98 per-file cases; 8
     retired from public catalog; 0 live receipts attached; no public quality promotion` — byte
     identical to the writer's `validator.out` line.
   - `evidence_test.py` ran "Ran 14 tests in 2.399s ... OK" in this rerun (writer's run: 4.629s) —
     no timeout either time; the writer's earlier-round timeout issue does not recur here.
   - Diffed the fresh receipt JSON against the writer's `example-host-receipt-20260927f.json` key
     by key: only `generated_utc`, the embedded `TMPDIR` scratch path, and `dirty_diff_sha256`
     differ (all expected — different run time, different `TMPDIR`, and the dirty-diff hash
     necessarily follows the working tree). `git_commit` and every test-count/hash field are
     identical, including chain `9152960ef3c0`, doppelganger `5d9864b22241`, manifest `c3766715`,
     `cursed.lua` `56165e59`, `fixture.lua` `cb74dc7b`.

4. **Mutants rerun**, via `host-cmd bash /home/brunner56/kp-live-20260922/review-probes-examples-r5/run_mutants.sh`:
   - Output is byte-identical (after stripping the CRLF that `host-cmd`'s pipe adds) to the
     writer's `mutants.out`. Current bytes: 15/15 PASS. All 8 mutants killed with the exact
     failing-test sets claimed:
     - drop `o == pc`: 2 fails (leader swap, same-module).
     - drop party clause (`return false`): 11 fails.
     - drop `OnModuleLoad` clear: 1 fail (after-a-module-load / R4-7).
     - `from_save_game` truthy instead of `== 1`: 1 fail (OnAreaEnter case).
     - fail-open on unknown (`in_party(o) == true`): 1 fail (party answers).
     - boolean `false` read as unknown: 1 fail (party answers).
     - cache `spared` by ID until load: 2 fails.
     - cache `in_party` by ID until load: 1 fail.
   - Additionally diffed each mutant file against `chain_r5.lua` directly (not just trusting the
     table): every mutant is a genuine single-clause edit (two clauses only for the combined
     `idtrust-noparty`-style cache mutants, which are inherently two-line insertions for the cache
     table itself). No mutant is a no-op or a broader rewrite than claimed.

5. **Prior-round reviewer probes rerun**, via
   `host-cmd bash /home/brunner56/kp-live-20260922/review-probes-examples-r5/run_prior.sh` in both
   strict and `KP_TOLERANT=1` modes:
   - Both outputs are byte-identical (modulo CRLF) to the writer's `prior_probes.out` and
     `prior_probes_tolerant.out`.
   - Every one of the 38 blocks (35 chain + 3 mutations.lua) reports
     `SAFETY minonehp_calls=0 party_or_pc_effects=0` with no exceptions — grepped for any
     non-zero SAFETY line, found none.
   - The N/A-by-design classifications in the writer's table (A1-A5, P1-P3, M1, R3-*, R4-1*
     through R4-6*, R4-8*, G1) are legitimate: those probes assert on restore/guard machinery that
     no longer exists in this design, and the safety oracle confirms no unsafe side effect
     occurred while the probe's own primary assertion was moot. R4-7 is correctly promoted to a
     first-class host test (`detonations before=1 after=2`, matches).

6. **Read the new test file's oracle directly** (`tools/tests/examples/cursed.lua:178-197`):
   `protected_now(f,id)` computes protection independently of the script's own beliefs — it reads
   the fixture's live `GetFirstPC` override and the fixture's own `party==1` flag at the moment
   each `ApplyEffectToObject` call lands, not anything the script remembers. `flags()` then
   asserts (a) zero effects ever landed on a protected object during the watched window, (b) zero
   `SetMinOneHP`/`GetMinOneHP` calls total, and (c) every named object's `min_one_hp` field is
   bit-for-bit unchanged from its preset value. This is a real, non-vacuous safety net wired into
   every test in the file, not just the named "safety" cases — confirmed by reading the test
   bodies for "hostiles chain," "leader swap," "within one module," "party answers," and "unload
   mid-chain" (lines 210-323), all of which call `flags(f, {...})` with concrete expected values
   and all of which exercise real state transitions (module load, area enter, leader swap,
   mid-module roster changes, error/unknown/false bridge answers).

7. **Stale-reference claims**, checked directly:
   - `scripts/harness/scenarios/cursed/40_chain_reaction.toml`: last step's `assert_lua` reads
     `nwscript.call('GetLocalNumber',pc,6) >= 10`, labeled "party damage." Local 6 is never
     written by the new script (confirmed by grep — no `SetLocalNumber` targets slot 6 anywhere
     in the file, only slots 5 and 7). This step will now always fail live. Confirmed stale.
   - `docs/showcase-demos/cursed.md`: line 31 (table row) reads "40 chain reaction | >= 3
     detonations; party damage >= 10 and PC alive | ship"; line 50 (historical note) reads "40
     chain reaction: 11/11; 6 detonations, party damage published." Both lines verified at the
     exact line numbers claimed via `grep -n`. Both describe behavior (party damage) that the
     redesign explicitly removes. Confirmed stale.
   - Required edits (not made by the writer, correctly out of scope for this round per the
     writer's own note): the harness toml's last step needs its gate changed to something that
     doesn't depend on local 6 (e.g., drop the party-damage clause, keep only `GetIsDead(pc)~=1`),
     and both `cursed.md` lines need "party damage >= 10" replaced with language matching the new
     behavior (party excluded, no damage published).

## Grill answers, attacked weakest-first

1. **"What if `IsObjectPartyMember` answers wrong inside the hook?"** (writer's own weakest,
   listed first). The writer concedes a wrong `0` for a real companion causes full damage on that
   companion, live evidence is `unverified`, and calls this "not new" (rounds 1-4 used the same
   answer to pick victims). That's true as far as it goes, but rounds 1-4 also *restored* whatever
   they broke; round 5 does not restore anything, so a wrong-`0` companion here takes real,
   uncompensated fire damage with no fallback. Asked narrower: does anything in this round change
   the *consequence* of a wrong answer, not just its likelihood? Re-reading the code: no — this is
   an irreducible trust boundary at the engine bridge, correctly named as such, and the ruling's
   own scope (judge at blast time via these two calls) accepts that risk by construction. This
   holds as an honestly-scoped residual risk, not a defect in the round's work.
   Referent: `spared()`/`in_party()`, `scripts/examples/cursed/40_chain_reaction.lua:53-66`; "party
   answers" test, `tools/tests/examples/cursed.lua:311-323`. Verdict: holds. Confidence: high.

2. **"Why aren't the PC local-number writes (5, 7) persistent creature state needing restore?"**
   Checked directly: `grep -n SetLocalNumber` gives exactly lines 104, 111, 156, all targeting
   `pc` with slots 5 (armed flag) and 7 (detonation counter) — both the script's own published
   counters, not engine-owned creature state like min-one-HP. The ruling's language is "min-one-HP
   (or other persistent creature state needing restore)" — these counters need no restore (no
   invariant depends on their prior value; `OnModuleLoad`/`disarm` reset them unconditionally).
   Holds. Confidence: high.

3. **"How come any `OnAreaEnter` still disarms?"** Confirmed pre-existing (A8 in round 4's probes,
   reconfirmed in `prior_probes.out`/rerun here) and explicitly scoped by the ruling's "keep
   visible behaviour" instruction, which the ruling for this round did not revoke. Holds.

4. **"Is dropping local 6 a visible-behaviour change beyond the ruling?"** No — the ruling itself
   mandates zero party damage, so a published "party damage" counter would either have to lie (log
   a nonexistent value) or read 0 forever, silently failing the harness gate anyway. Removing the
   counter is the honest choice, and the writer correctly flagged the toml as stale rather than
   quietly leaving it broken. Holds.

5. **"Does reading `GetFirstPC` per victim break the transient-PC-failure retry?"** Checked against
   the "transient inner PC failure allows retry" test (`tools/tests/examples/cursed.lua:167-172`):
   a third `GetFirstPC` call returning `nil` mid-detonate causes `detonate()` to bail (its own
   `if not pc then return end` at line 128) without incrementing the counter, and the next armed
   death succeeds normally. Holds, independently re-derived from the code, not just the writer's
   claim.

## Additional grill question the writer didn't ask

**Does `exploded[]` surviving an in-module `OnAreaEnter` (non-save) let a corpse from an earlier
part of the same module "hide" a genuine new detonation under a distinct object ID?** No — `exploded`
is keyed by the corpse's own object ID (`exploded[corpse]`), and IDs are not reused within a single
module per the file's own comment (line 77-78, unchanged design assumption carried from earlier
rounds and not disputed by any round's evidence). A second, different corpse gets a different key.
This is consistent with the "recycled corpse ID detonates again" test only firing across a module
load, never within one. Holds; no referent contradicts it.

## Unsettled

Same as the writer's: whether `IsObjectPartyMember` ever answers `0` for a genuine companion in
live K1 (e.g., mid-join, mid-load) is unverified from this review's static/host-only vantage. The
single check that would settle it — logging both `GetFirstPC` and `IsObjectPartyMember` answers
per victim during one live chained kill — is unchanged from the writer's proposal and this review
has no way to run it (no game, per this review's own constraints).

## Verdict

All five structural requirements from the ruling are met and independently reproduced:
no `SetMinOneHP` or other persistent-creature-state mutation; fail-closed on error/unknown
membership or PC answers; no stored IDs across time except `exploded[]` (which cannot misfire
across modules); all prior-round probes run and are correctly classified (N/A-by-design or
holding, with R4-7 promoted to a real test); all 8 mutants fail on the current bytes; NWScript is
reached only via `nwscript.call`; no NWScript-shaped Lua names. The validator passes with a receipt
that reproduces byte-for-byte (aside from timestamp/tmp-path/dirty-diff, all of which are expected
to vary between runs) under an independent rerun on the host. The two flagged stale references
(`scripts/harness/scenarios/cursed/40_chain_reaction.toml` last step, `docs/showcase-demos/cursed.md`
lines 31 and 50) are genuinely stale and correctly left out of this round's file list rather than
silently patched.

Example fixes round 5 verdict: PASS
