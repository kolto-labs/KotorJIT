# Example fixes round 3 review (2026-09-27)

Reviewer: independent. I did not write to the worktree. I did not run the game or Wine, and I did not touch the live-game lock.
I did not git reset, stash, stage or commit.
Probes and outputs are in `/home/brunner56/kp-live-20260922/review-probes-examples-r3/`.

Order: I read `40_chain_reaction.lua` (`74c0ca1a…`) and `fixture.lua` first. I built probes R3-1 to R3-4 and ran them.
Only then did I read the writer's Round 3 section and its Grill me.
R3-5 was added afterwards to settle grill #3.

## Byte identities

- `sha256sum scripts/examples/cursed/40_chain_reaction.lua` = `74c0ca1ac5ddfef52e83c1338315135d62a0fd6d77736848b4afa44e73fff6e4` (as briefed).
- `sha256sum scripts/examples/cursed/70_doppelganger.lua` = `5d9864b22241ff135d3bb0c1ecb3f2671af218b58cdf2f44eb7bc62c95f62c42` (unchanged, as required).
- `tools/tests/examples/manifest.json` contains `74c0ca1a` once (the chain entry).

## Prior probes rerun (current bytes)

Command (host, from the worktree root):
`host-cmd sh -c "cd <worktree> && /usr/bin/luajit <r1>/chain_attacks.lua <r3>/sources.lua; /usr/bin/luajit <r1>/pc_probe.lua <r3>/sources.lua; /usr/bin/luajit <r1>/mutations.lua <r3>/sources.lua <r1>/airstrike_HEAD.lua; /usr/bin/luajit <r2>/pc_swap_probe.lua"`.
`sources.lua` is a copy of `/tmp/kp-example-sources.lua`, the map the round 1 review used.
Output: `review-probes-examples-r3/prior_probes_rerun.out`.

- A1–A8: all HOLDS. A1 was BREAKS in round 1 and is now `new-id bastila min_one_hp=0`.
- P1–P3: all HOLDS. P3 was BREAKS in round 1 and is now `new-id PC min_one_hp=0`.
- M1–M3: all HOLDS.
- `pc_swap_probe.lua`: `old_pc=0 replacement_pc=1` (round 2 printed `old_pc=1 replacement_pc=0`). The round 2 Important finding is closed.

## New probes

File: `review-probes-examples-r3/r3_probes.lua`. It uses the repo fixture unchanged. An optional `arg[1]` swaps in another source file.
Output on current bytes: `r3_probes.out`.
The same probes against `mut-noclaim.lua` are in `r3_probes_vs_noclaim.out`. That file is the writer's own mutant, `/tmp/kp-chain-r3-mut-noclaim.lua`. It is identical to the final bytes except that line 87 reads `return valid(m)`, with no `owned` check. `diff` confirms a single-line difference.

| probe | current `74c0ca1a` | `mut-noclaim` (no `owned`) |
|---|---|---|
| R3-1 two gone PC entries → one new object | `sets=[12<-0 12<-1] old_pc(11)=1 … pending_logged=false` | same |
| R3-2 PC recreated under a recycled ID the script owned | `after_load=1 after_blast_settle_unload=1 pending_logs=5 sets=[2<-1 2<-1]` | `after_load=0 … =0 pending_logs=0` |
| R3-3 member recreated under a recycled owned ID | `bastila(1)=1 pending=true` | `bastila(1)=0 pending=false` |
| R3-4 unload while a member is absent | `bastila_flag=1 pending_logged=true`, then the state is discarded | same |
| R3-5 stored ID still valid, same tag, not a party member | `sets=[2<-0] impostor(2)=0 real_bastila(5)=1` | same |

## Grill follow-up (writer's order, weakest first)

### Grill #1: two gone entries resolving to the same new object

claim: "both write it, last one wins. Unverified as reachable; no test."
referent: R3-1. PC 1 (prior 0) is guarded. Control swaps to atton 7 (prior 1) while 1 stays valid. A blast guards 7 as `pc=true`, because `current(1)` still returns 1 (line 90). Then both objects are recreated as 11 and 12, with `GetFirstPC`=12.
Both entries take the `entry.pc` branch (lines 91–93) with no tag check. Both resolve to 12 and write it: `12<-0 12<-1`.
checked: `r3_probes.out` line R3-1.
verdict: holds as the writer described it, but the consequence is worse than "last wins".
- Object 12 ends correct in this run only because of `pairs` iteration order.
- The load-bearing part is that both entries are consumed. Object 11 (the original PC) keeps min-one-HP=1 with no record and no "restore pending" line. The flag is silently lost.
- The same output on `mut-noclaim` shows this path predates this round.
confidence: high for the Lua path. It is conditional on the round 2 open precondition (`GetFirstPC` changes while the old PC is valid) plus both objects being recreated.
Classification: **Minor** (pre-existing, doubly conditional). Checking `entry.tag` on the PC lookup would close it. So would refusing a candidate that another pending entry in the same pass also resolves to.

### Grill #2: can `owned` block a legitimate lookup?

claim: "Then the entry stays 'restore pending' and nothing is overwritten (fails safe, but that creature keeps min-one-HP until unload)."
referent: R3-2.
1. A blast guards PC 1 and Bastila 2. Settle restores both, so `owned={1,2}` with no live entries.
2. A second blast guards PC 1 (prior 0).
3. Module load recreates the PC under the recycled ID 2, with `GetFirstPC`=2.

`current(1)`: 1 is invalid, so it takes the `entry.pc` branch. `unclaimed(2,1)` is false because `owned[2]` is set and never cleared (line 124). It returns nil, and the entry is logged pending.
- `OnAreaEnter` repeats this, and so does `OnScriptUnload` (line 186). Unload runs one more `restore_guards` pass that also fails, and then the script state is gone.
- Before that, the next blast's `guard(2)` finds no matching entry and reads `GetMinOneHP(2)` = the stuck 1 as the new prior (lines 119–123). Settle then "restores" 1: `sets=[2<-1 2<-1]`.
- End state: the PC has min-one-HP=1 for good, and the script's own record now says 1 is correct. There were 5 pending lines.
checked: `r3_probes.out` R3-2. The one-line `mut-noclaim` gives `after_load=0 … =0 pending_logs=0`, so `owned` alone causes this. R3-3 shows the same for a companion: `bastila(1)=1 pending=true`.
verdict: **does not hold.**
- "until unload" is false. Unload does not restore. It drops the record.
- "fails safe" is false for the property the script exists to keep: each flag is put back to its prior. The PC becomes permanently unkillable, and the state goes into every later save.
- "nothing is overwritten" holds in the narrow sense (no foreign prior is written), and that is all.
confidence: high for the Lua counterexample. Medium for live impact: it depends on K1 reusing numeric object IDs across a module load.
- The repo names that hazard itself: `docs/devtools-design.md:86` says "module transitions cannot leave a write targeting a recycled ID. Never store only a pointer or reuse a raw numeric ID as project identity."
- That line is a design-doc referent, not live proof.
- `owned` is exactly a session-lifetime set of raw numeric IDs.

Classification: **Important. It is a regression this round introduced** (isolated by the one-line mutant).
- Its outcome, a permanently immortal PC, is worse than the round 2 finding, which misdirected a restore.
- It meets the same standard round 2 failed on: a Lua counterexample with medium live impact that depends on unverified engine behavior.
- Simply deleting `owned` is not the fix. The writer's `mut-noclaim` fails their own "gone PC … never resolved onto another guarded member" test.
- Both failures come from using raw IDs as identity across a load. The fix direction is to expire ownership at a transition (IDs from before the load mean nothing after it) and to compare stored identity (tag, and the PC flag) instead. Two more things are needed:
  - `guard` must not take a fresh prior from a creature that a pending entry could still own.
  - An unresolved PC entry must not end up re-read as prior 1.
- This is a direction, not a checked patch.

### Grill #3: same-tag ID reuse

claim: "a reused ID with a different tag falls through to lookup … Same-tag reuse: unverified."
referent: R3-5. Bastila 2 is guarded (prior 0). After the load, ID 2 is valid but names a non-party creature tagged `bastila` (flag 1), and the real Bastila is ID 5 (flag 1).
Line 90 returns 2 on `valid(id)` plus a tag match, with no `IsObjectPartyMember` check (only the `GetObjectByTag` fallback at line 102 checks party membership).
Result: `sets=[2<-0] impostor(2)=0 real_bastila(5)=1 pending=false`. A non-party creature has its flag cleared, the real companion stays at 1, and nothing is logged.
checked: `r3_probes.out` R3-5.
verdict: the writer's different-tag statement holds (line 90). The same-tag case does not hold: it writes onto a non-party object.
confidence: high for the Lua path, low for live reachability. It needs a recycled ID to land on a same-tag non-party creature, and the check is the same live readback as #2.
Classification: **Minor.** Adding `IsObjectPartyMember(id)` to line 90 would close it.

### Grill #4: why a gone PC stays pending rather than taking a guarded Bastila

That holds. The referent is the "a gone PC is never resolved onto another member this script guarded…" test, which is green in receipt d, and `mut-noclaim` fails it (writer's mutations.out).
My R3-2 shows the cost of the mechanism chosen to get this.

### Grill #5: `guard` carry-over

That holds for a never-owned new ID. The referent is the "a member that cannot be re-resolved…" test, green.
For an owned recycled ID the carry-over does not happen, and the stuck 1 is read as the prior (R3-2 above).

## Own grill questions the writer missed

claim (header lines 18–20 and README row 13): the flag is put back "on a module load, area enter or script unload", and a creature that cannot be found "is … tried again at the next settle, area enter or module load".
referent: R3-4. When unload runs with a member absent, the entry is logged pending and then discarded with the Lua state. The flag stays at 1.
checked: `r3_probes.out` R3-4. The same result on `mut-noclaim` shows this predates this round.
verdict: does not hold as a complete statement. Neither the header's "Not covered" list nor README row 13 names a pending entry at unload. They also do not name the recycled-ID permanent-pending case (R3-2).
confidence: high.
Classification: **Minor** (docs).

claim: NWScript is reached only through `nwscript.call`, and no Lua name duplicates an NWScript routine.
referent: `nwscript.` appears only at lines 58–59 and 64–65 (inside `q` and `call`).
- The global functions are hook entry points (`OnTick`, `OnModuleLoad`, `OnAreaEnter`, `OnScriptUnload`, `OnRunScript`) plus `chain_settle`.
- The locals are all lowercase: `q`, `yes`, `call`, `norm`, `tag_of`, `valid`, `unclaimed`, `current`, `guard`, `restore_guards`, `dist`, `armed`, `disarm`, `is_death_script`, `detonate`.
checked:
- `rg -n 'nwscript\.' …40_chain_reaction.lua`
- `rg -n '^\s*(local\s+)?function\s+[A-Z]'` (hooks only)
- `rg -n -i '(Get|Set|Is)[A-Za-z0-9_]+\s*='` (only `SETTLE_MS`/`settle_gen`)
verdict: holds. confidence: high.

## Validator rerun vs receipt d

Command (identical to rounds 1–2 except for the receipt path):
`/home/brunner56/.local/bin/host-cmd sh -c 'cd <worktree> && /usr/bin/python3 tools/example_validation.py --luajit /usr/bin/luajit --host /home/brunner56/kp-validation-20260922-build/kp_luatest --receipt /home/brunner56/kp-live-20260922/review-probes-examples-r3/rerun-receipt.json'`.

Output: `PASS: 41 original syntax/host regression sources, 96 per-file cases; 8 retired from public catalog; 0 live receipts attached; no public quality promotion`, exit 0 (`review-probes-examples-r3/validator.out`).
The receipt SHA-256 is `91fdae1f1c90c88adfb887f8ee3663e10c76d8c2d168da209ae19bbc33ccb9f8`.

I compared it field by field with receipt d (`2a98839a…`). Both have 1177 leaf fields, and 4 differ:
- `generated_utc`
- `dirty_diff_sha256` (`850863e9…` → `cd9a08f9…`). The shared worktree is dirty from other writers.
- the random `/tmp/kp-example-map-*` path in command 43
- the wall time in command 41 (`evidence_test.py`: "Ran 14 tests in 71.526s" → "1.413s")

All four are expected. All of these are present:
- chain `74c0ca1ac5dd`
- doppelganger `5d9864b22241`
- `kp_luatest` `9309dd6a`
- `fixture.lua` `cb74dc7b`, `cursed.lua` `61b07d84`, manifest `8e787165`

verdict: receipt d reproduces. The host suite is green, but R3-2, R3-3 and R3-5 are not in it, so green does not decide this round.

## Summary

- Critical: 0.
- Important: 1. R3-2/R3-3: the session-wide `owned` set of raw IDs, new this round, can leave the PC or a companion at min-one-HP=1 for good if K1 recycles an owned ID across a load.
  - Unload does not clear it.
  - The next blast re-reads the stuck 1 as the prior.
  - The writer's grill #2 answer ("until unload", "fails safe") does not hold.
- Minor: 3.
  - R3-1: two gone PC entries consume each other and silently drop the original PC's restore. This predates the round and needs two conditions.
  - R3-5: a valid stored ID with a same-tag non-party creature takes the restore. There is no party check at line 90.
  - Docs omit the unload-with-pending case and the recycled-ID case.
- Closed: round 2 Important (`pc_swap_probe` now `old_pc=0 replacement_pc=1`), A1 and P3. All A1–A8, P1–P3 and M1–M3 hold.
- Doppelganger bytes unchanged.

Unsettled question and the single check: does K1 reassign numeric object IDs across party members (and the PC) on a module load?
Settle it with a live readback of every party member's numeric ID and `GetTag`, and of `GetFirstPC`, taken before and after one module load. If IDs never recycle, R3-2, R3-3 and R3-5 are unreachable and only the docs gap remains.

Example fixes round 3 verdict: FAIL
