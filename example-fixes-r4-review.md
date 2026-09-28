# Example fixes round 4 review (2026-09-27)

Reviewer: independent. I made no writes to the worktree and no git writes. I did not run the game and did not touch the live-game lock.
Probes and outputs: `/home/brunner56/kp-live-20260922/review-probes-examples-r4/`.

Order:
1. I read `40_chain_reaction.lua` (`e7b65781…`) and `fixture.lua`.
2. I wrote and ran `r4_probes.lua` (R4-1 to R4-8) and `r4_probe8_detail.lua`.
3. Only then did I read the writer's Round 4 section and its Grill me.
4. I added `r4_probes2.lua` (the grill #1 carry case and two R4-1b follow-ups).
5. I ran every probe against the comparators listed next.

Comparators, all run through `run_compare.sh` with output in `compare.out`:
- The final bytes, `e7b65781ca5b`.
- The real round-3 bytes, `chain_r3_74c0ca1a.lua`. This is a copy of `/tmp/kp-chain-r4-old-74c0ca1a.lua`, and its sha256 `74c0ca1ac5dd…` is verified.
- HEAD, `a346b5a8`. It has no settle timer, so most probes assert out on `f:fire`. It is used only for attribution.
- `mut-nobump-areaenter.lua`: the final bytes with one line changed. Line 252 has no `epoch = epoch + 1` in `OnAreaEnter`, and the `OnModuleLoad` bump is kept. `diff` shows the single change.

## Byte identities

- `40_chain_reaction.lua` = `e7b65781ca5b4911f738c46fc75fcc0c39ac7a5893bb5f13c943220d0ca69bef`, as briefed.
- `70_doppelganger.lua` = `5d9864b22241ff135d3bb0c1ecb3f2671af218b58cdf2f44eb7bc62c95f62c42`, unchanged as required.

## Prior probes rerun (current bytes)

Command: the round-3 command plus `r3_probes.lua`. Output: `prior_probes_rerun.out`, exit 0.
- A1–A8, P1–P3 and M1–M3: all HOLDS.
- `pc_swap_probe`: `old_pc=0 replacement_pc=1`.
- R3-1: `sets=[11<-0 12<-1] old_pc(11)=0`. Closed.
- R3-2: `after_load=0 after_blast_settle_unload=0 pending_logs=0`. The round-3 Important is closed.
- R3-3: `bastila(1)=0 pending=false`. Closed.
- R3-4: `bastila_flag=1 pending_logged=true`. This is the documented limit, and it is now named at unload.
- R3-5: `sets=[5<-0] impostor(2)=1 real_bastila(5)=0`. Closed.

This matches the writer's `example-fixes-r4-probes.out`.

## New probes: results and attribution

The three result columns are: final bytes `e7b6` / round 3 `74c0` / the final bytes without the area-enter bump (`nobump`). HEAD asserted out on these probes, so it has no column. Rows R4-1L and R4-2L come from `r4_probes3.lua` (`r4_probes3.out`).

| probe | e7b6 | 74c0 | nobump | reading |
|---|---|---|---|---|
| R4-1a PC `GetTag` errors, new ID after load | `new_pc(7)=0` | `=0` | `=0` | holds |
| R4-1b PC tag `""`, control swapped to bastila, same-module `OnAreaEnter`, settle, unload | PC `1/1/1`, 3 pending lines, unload line targets `GetFirstPC` | `0/0/0` | `0/0/0` | **regression from the area-enter bump** |
| R4-1c same without the enter | `0` | `0` | `0` | control |
| R4-1b(a) PC blasted again while still swapped | `1 → 0` | – | – | the carry keeps prior 0 |
| R4-1b(b) control stays swapped, 3 more blast and settle cycles elsewhere | `pc1=1`, 5 pending lines | `0` | `0` | stuck for as long as the swap lasts |
| R4-1b(b2) control back on the PC, next settle | `0` | `0` | `0` | recovers in-session |
| R4-2 two party members tagged `twin`, same-module enter | `after=0,1`, 1 "prior unknown" line, 0 pending, 0 NOT-restored | `0,0` | `0,0` | regression from the bump. The second twin stays at 1 with no log |
| R4-2b stuck twin blasted again, settle | `twin4=1` | `0` | `0` | its stuck 1 is recorded as the prior |
| R4-3 member leaves the party in the window, rejoins later | `after_settle=1 pending=1 after_rejoin=0` | `0` | `1 … 0` | ruling cost (party-only), logged, recovers |
| R4-3b left the party, then unload | `1`, NOT-restored line by tag | `0` | same as e7b6 | ruling cost, logged |
| R4-4 empty roster at load, old settle timer fires in the new module | `pending=2`, then `pc=0 bastila=0` | same | same | holds |
| R4-4b death inside the load window | `EffectDamage` delta 0 | 0 | 0 | holds |
| R4-5 unload right after load | 2 NOT-restored lines | 0 lines, nothing restored | 2 | holds (loud as ruled) |
| R4-6 five same-module enters, tagged members | `pc=0 bastila=0`, 0 pending | same | same | holds |
| R4-6b untagged non-PC member, same-module enter | `1/1/1`, unload line `SetMinOneHP", <the object>, 0` | `0/0/0` | `0/0/0` | regression from the bump |
| R4-6c stale settle timer after re-arm | old timer leaves 1, new one gives 0 | same | same | holds |
| R4-7 recycled corpse ID in the next module | never detonates (`1 → 1`) | same | same | pre-existing (`exploded[]` since HEAD). Functional only, non-blocking |
| R4-8d PC tag `""`, same-module enter with control on an untagged member 5 whose own flag is 1 | `sets=[5<-0] pc1=1 member5=0 logs=0` | `sets=[1<-0] pc1=0 member5=1` | `sets=[1<-0] pc1=0 member5=1` | **regression from the bump**: the PC's prior is written onto an unguarded creature, and the PC stays at 1 with no log |
| G1 PC tag `""`, control on tagged bastila, same-module enter, untagged member 5 (flag 1) blasted, then settle | `sets=[5<-1 5<-0] member5=0 pc1=1` | `member5=1 pc1=0` | `member5=1 pc1=0` | regression from the bump |
| R4-8 as R4-8d, but through `OnModuleLoad` (IDs unchanged) | `member5=0 pc1=1 pending=0` | `member5=1 pc1=0` | `member5=0 pc1=1` | **not reverted by nobump**. The ruling's load bump causes it. Silent misdirected write. Needs an untagged companion |
| R4-1L as R4-1b, but through `OnModuleLoad` (IDs unchanged) | `1/1/1`, 3 pending, unload line targets `GetFirstPC` | `0/0/0` | `1/1/1`, same line | **not reverted by nobump**. Ruling cost. Logged, but the unload line is misdirected |
| R4-2L same-tag pair across `OnModuleLoad` | `0,1`, 1 "prior unknown" line, 0 pending | `0,0` | `0,1` | not reverted by nobump. Collision rule |

`nobump` passes all 22 of the writer's chain tests. The source is `compare.out`, the last section, run through the writer's own runner (`runner.lua`, a copy of `/tmp/kp-chain-r4-runner.lua`).
- No test depends on the epoch bump in `OnAreaEnter`.
- Every row above marked "regression from the bump" returns to the round-3 result when that one line is removed.
- The same classes survive a module load under `nobump`: R4-8, R4-1L and R4-2L. There the ruling itself requires the bump. Removing line 252 closes the in-module rows only, not the class.
- The orchestrator's ruling calls for discarding IDs on a module load. The area-enter bump is the writer's own extension.

## Orchestrator question: is the epoch bump on `OnAreaEnter` too aggressive?

Yes.
- It drops IDs that are still valid inside the same module.
- Tagged companions come through (R4-6).
- These cases go wrong, all with IDs unchanged and no module load:
  - an untagged entry (R4-6b)
  - a PC with tag `""` under a control swap (R4-1b)
  - two same-tag members (R4-2)
  - a PC with tag `""` while another untagged member is `GetFirstPC` (R4-8d, G1)
- Two of these are silent: R4-8d, and the second twin in R4-2.
- `A8` (pre-existing) says `OnAreaEnter` fires for any entering object. If so, a bump happens every time a creature enters the area, not once per transition.
- Nit (pre-existing since HEAD): the signature is `OnAreaEnter(area, entering, relevant)`, but `docs/lua-api.md:471` gives `(area, entering, from_save_game, relevant)`. The script therefore cannot tell a save load from any other enter.

## Grill follow-up (weakest first)

### Grill #3: does the PC entry depend on K1's PC tag?

claim: "If K1's PC tag is `""` and a control swap leaves another untagged member as `GetFirstPC`, the two records collide. The creature then goes to 0 and a 'prior unknown' line is logged."
referent: R4-8d.
- Member 5 has no entry of its own, so there is no collision and no log.
- `find(PC entry)` takes `GetFirstPC`=5 (tag `""`, a party member) at line 107, and restore writes the PC's prior onto 5: `sets=[5<-0]`.
- The real PC keeps 1: `pc1=1 logs=0`.
- The round-3 bytes and `nobump` both give `sets=[1<-0] pc1=0 member5=1`.
checked: `compare.out`, rows R4-8d.
verdict: **does not hold.** This is the round-2 Important class: a restore written onto an unguarded `GetFirstPC` object. This time it happens silently, inside one module.
confidence: high for the Lua path.
Live reach: it needs an untagged non-PC companion. The repo records K1 companions as tagged lowercase (`tools/tests/examples/fixtures/legacy/showcase/30_battle_meditation.lua:47`). Vanilla reach is therefore low.

The same grill, for a tagged companion (R4-1b):
- claim: "It uses the stored tag in every lookup". That holds. `GetFirstPC`=bastila is refused, and nothing is misdirected.
- The cost: the PC entry stays pending, and the PC keeps min-one-HP=1 for as long as control stays swapped. That is 5 pending lines over 3 more settle cycles in R4-1b(b).
- It recovers when control returns (b2), or when the PC itself is blasted (a: the carry keeps prior 0).
- A save made during that span persists the flag. The documented limit covers only "a save written inside the SETTLE_MS window".
- If unload happens during the span, the printed fix is `nwscript.call("SetMinOneHP", nwscript.call("GetFirstPC"), 0)`. That line targets bastila, not the PC. It is wrong in exactly the case where it gets printed, because the entry is pending only because `GetFirstPC` did not fit.
- On round-3 bytes and `nobump`, R4-1b gives `0/0/0`.

### Grill #1: is the untagged carry truthful?

claim: "If the member really is a different creature with a genuine 1, it later gets 0. Unknown is also 0, so both choices clear it."
referent: G1, with the PC tag `""`, control on tagged bastila, a same-module enter, then untagged member 5 (flag 1) blasted and settled.
- Result: `sets=[5<-1 5<-0] member5=0 pc1=1`.
- The first half is as the writer said: 5 loses its genuine 1.
- What the writer did not say: the carry also consumes the PC's entry. The real PC then keeps 1 with no NOT-restored and no later pending line for it.
- Round 3 and `nobump` give `member5=1 pc1=0`.
checked: `compare.out` G1.
verdict: does not hold in full.
confidence: high for Lua, low for vanilla reach (it needs an untagged companion).

### Grill #2: why does `OnAreaEnter` bump the epoch when any object enters?

claim: "Only an untagged non-PC member goes pending until unload."
referent: R4-1b (PC with tag `""` under a swap), R4-2 (same-tag pair, one silently stuck, and then its 1 is recorded as a prior) and R4-8d (misdirected write). None of these is an untagged non-PC member.
checked: `compare.out`, plus `nobump` passing 22/22.
verdict: does not hold. The bump is not needed by any test or by the ruling. It is the direct cause of every regression in the table.
confidence: high.

### Grill #5: `GetObjectByTag` with two same-tag creatures

claim: a non-party first match is refused, and the entry stays pending.
referent: the writer's test "a non-party creature with the companion tag…" is green, and R3-5 is closed.
verdict: holds. The two-party-members case is R4-2 above.

### Grill #4: why not store the prior durably?

The writer said it would need a slot the script does not own. That holds.
- `OnSave`/`OnLoad` exist (`docs/lua-api.md:1026-1036`).
- They are bound to `vm.save_script_situation`, are rated medium confidence, and are not a module-save hook.
- This is advisory only.

## Own claims checked

claim (header line 30 and README row 13): "the script never records its own 1 as a prior".
referent: R4-2b, `twin4=1` after a blast and settle. The collision pass drops both entries and leaves twin 4 at 1. The next `guard` reads that 1 as twin 4's prior.
checked: `compare.out`.
verdict: does not hold (same-tag pair). confidence: high. Live reach is low (companion tags are unique).

claim (header lines 36–38 and README): unload names each creature "with the F12 console line that clears it".
referent:
- R4-1b: the line targets `GetFirstPC`, which is the swapped-in companion.
- R4-6b: the line reads `SetMinOneHP", <the object>, 0`, which cannot be run.
verdict: does not hold for a PC with tag `""` or an untagged member. confidence: high.

claim: NWScript is reached only through `nwscript.call`, and no Lua name duplicates an NWScript routine.
referent:
- `rg -n 'nwscript\.'` finds lines 68–69 and 74–75 (`q`/`call`). Lines 259–263 are strings only.
- The globals are hook entry points plus `chain_settle`.
- The locals are `q yes call norm tag_of valid label fits find resolve_all drop guard restore_guards dist armed disarm is_death_script detonate`, none of them NWScript names.
- A case-insensitive `(Get|Set|Is)…=` grep hits only `PARTY_DIVISOR`, `SETTLE_MS`, `settle_gen` and a local named `list`.
verdict: holds. confidence: high.

Null moves (hold, no finding): R4-1a, R4-4, R4-4b, R4-5 (loud as ruled), R4-6, R4-6c.
- R4-3 and R4-3b are the ruling's party-only cost. They are logged and recover on rejoin.
- R4-7 is pre-existing and non-blocking.

## Validator rerun vs receipt e

Command:
`host-cmd sh -c 'cd <worktree> && /usr/bin/python3 tools/example_validation.py --luajit /usr/bin/luajit --host /home/brunner56/kp-validation-20260922-build/kp_luatest --receipt <r4>/rerun-receipt.json'`
- It ran at load average about 134. `evidence_test.py` did not time out.
- Output: `PASS: 41 original syntax/host regression sources, 105 per-file cases; 8 retired from public catalog; 0 live receipts attached; no public quality promotion`, exit 0 (`validator.out`).
- The receipt SHA-256 is `ba0defeb…`.

Compared field by field with receipt e (`b28ca4bf…`): both have 1187 leaves. Three differ, and all three are expected:
- `generated_utc`
- the tmp map path in command 43
- the `evidence_test.py` wall time (0.768 s → 1.003 s)

`dirty_diff_sha256` is identical. Every pinned value is present: chain `e7b65781ca5b`, doppelganger `5d9864b22241`, `kp_luatest` `9309dd6a`, `fixture.lua` `cb74dc7b`, `cursed.lua` `34ec0977`, manifest `1ec55bdb`.
verdict: receipt e reproduces. The suite is green, but R4-1b, R4-2, R4-6b, R4-8d and G1 are not in it.

## Classification

- Critical: 0.
- **Important: 1.** The epoch bump in `OnAreaEnter` (line 252) is new this round and does not come from the ruling. Isolation: one line, `nobump` passes 22/22 and reverts every row.
  - It turns in-module cases that round 3 handled correctly into stuck or misdirected min-one-HP:
    - R4-1b: the PC with tag `""` stays immortal while control is swapped. That persists into any save made then, and the unload fix line targets the wrong creature.
    - R4-8d/G1: the PC's prior is written onto an unguarded creature, and the PC stays at 1 silently.
    - R4-2: the second same-tag member stays stuck silently, and its 1 later becomes its prior.
    - R4-6b.
  - This meets the bar rounds 2 and 3 set: a Lua counterexample, a regression against the previous round, and a live impact that rests on unverified engine facts:
    - the K1 PC tag is `""`
    - `GetFirstPC` follows the controlled leader
    - `OnAreaEnter` fires in-module for entering objects (A8)
  - R4-1b needs only those three and a tagged companion. It is logged and recoverable, unlike R3-2. It is still Important:
    - The window is no longer 3 s.
    - The ruling's "loud unload" line is misdirected in exactly this case.
    - Removing line 252 costs no test (`nobump` 22/22). It does not close the class across a load (see fix direction).
  - Fix direction (not a checked patch; it narrows the class and does not close it):
    - (a) Bump the epoch only in `OnModuleLoad`. If a save-game load must also bump, use `OnAreaEnter`'s `from_save_game` argument (fix the signature first). This reverts the in-module rows: R4-1b, R4-2, R4-6b, R4-8d and G1.
    - (b) Build the unload line for a PC with tag `""` from something other than `GetFirstPC`, or tell the user to switch control back to the PC first. This is independent of (a): R4-1L shows the misdirected line after a load under `nobump` too.
    - (c) Add what remains after a load to "Not covered" and README row 13:
      - a PC with tag `""` cannot be found while control is on another creature (R4-1L);
      - a PC with tag `""` resolves onto an untagged `GetFirstPC` member (R4-8);
      - a same-tag pair loses one member's restore (R4-2L).
      Or close them. A new test is needed for each one that is closed.
- Minor: 3.
  - R4-2L/R4-2b across a load: the collision rule drops the other same-tag creature silently, and its 1 later becomes a prior. This is the ruling's cost, and live reach is low. The in-module R4-2 is part of the Important above.
  - Docs: "never records its own 1 as a prior" and "the console line that clears it" do not hold as stated (R4-2b, R4-1b, R4-6b).
  - R4-7 (pre-existing): `exploded[]` is keyed by raw ID across epochs, so a recycled corpse ID never detonates.
- Closed: round-3 Important R3-2/R3-3, and Minors R3-1, R3-4 (docs, now loud) and R3-5.
- Doppelganger bytes are unchanged.

Unsettled question, and the single check that settles it: what `GetTag(GetFirstPC())` returns in K1, and whether `GetFirstPC` changes after a control swap, plus whether `OnAreaEnter` fires in-module for a non-PC entering creature.
- One live readback of `GetFirstPC` and its tag before and after a leader swap would settle it.
- So would an `OnAreaEnter` log while an NPC spawns.
- If the PC tag is not `""`, R4-1b, R4-8d and G1 are unreachable and only R4-2 plus the docs remain. Even so, the bump has no test and no ruling behind it.

Example fixes round 4 verdict: FAIL
