# Example fixes review (2026-09-27)

Reviewer: independent, read-only on source. No Wine, no game, live-game lock untouched.
Worktree: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation` (HEAD `ca329e5`).
Probes: `/home/brunner56/kp-live-20260922/review-probes-examples/`.

Pre-fix ledger text is not on disk (the ledger is untracked and was edited in place). Requirements were
reconstructed from the writer report, the ledger's current rows, and `progress.md` ("needs-fix 5").

## Stage 1: spec compliance

### Scope (nothing extra)

claim: the writer edited only the five example files, the ledger, and the listed test-file hunks.
referent: `/tmp/kp-before-shas.txt` (11:08) and `/tmp/kp-after-shas.txt` (11:15). I also reverse-applied only the claimed edits and hashed the result (`scope_reverse.out`).
checked:
- The five example scripts: `git show HEAD:<f> | sha256sum` equals the report's "before" hashes, and the current bytes equal its "after" hashes (a346b5a8→daed75d1, b528fb64→ce2e1504, edfe2b54→dfe19850, a8f0b06f→c13f6424, e74521ac→784e2e98).
- `manifest.json`: reverting 4 shas and 2 obligation strings gives `82dab5ef` (expected `82dab5ef`).
- `cursed.lua`: dropping the 5 new tests gives `c8ec4edb` (expected `c8ec4edb`).
- `fixture.lua`: dropping the 2 MinOneHP lines gives `cb11cdf9` (expected `cb11cdf9`).
- `probes_coverage.lua`: HEAD is `eecd81d4`, which is the report's "before".

The large doppelganger diffs in the fixture and manifest against HEAD are earlier Task 13 work. They are not this writer's.
verdict: holds. confidence: high.

### Doppelganger bytes

claim: `70_doppelganger.lua` is unchanged at `5d9864b22241…`.
referent: `sha256sum` shows `5d9864b22241ff135d3bb0c1ecb3f2671af218b58cdf2f44eb7bc62c95f62c42`. The before and after lists both hold that value.
verdict: holds. confidence: high.

### Per-fix checks

| Fix | Requirement | Result | Referent |
|---|---|---|---|
| Chain reaction | Read the prior min-one-HP flag before setting it, restore it (settle, transition, unload), and label local 6 honestly | holds | `40_chain_reaction.lua:59-76,113,120,167-170`. Mutation M1 (restore removed from `disarm`) leaves flag=1, so the test assertion is load-bearing. Red run is in the report. |
| Doppelganger README | Trigger is PC-as-attacker only, restore described, bytes frozen | holds (two wording Minors below) | README:14 against script lines 163-164, 179-186, 204-205, and `ARM_TICKS=200`, `SETTLE_TICKS=40` (lines 12-13) |
| Airstrike | Code and README agree on who gets struck; level-up marked unproven | holds (risk Minor below) | line 67 `GetIsEnemy(o, pc)`, header 10-11 and 19-23, README:17 |
| Coverage pick | Help text stops claiming a reply is queued | holds | `10_cover.lua:47,119-121`, new case in `probes_coverage.lua:39` |
| Avatar mock | `kp.as` removed, `with_caller` mocked, SetFacing caller asserted | holds | Mutant script without `with_caller` fails 2 checks; the original passes (`mutations.out`) |
| arbitration/50 | Retire | blocked, honestly recorded | The report's retry section and `progress.md` ruling |

### Ledger honesty

- Counts: static-host 31 + live-partial 10 = 41. keep-curated 32 (8+11+2+1+5+5) + retire 9 = 41. Consistent.
- No host proof is promoted to live. Chain reaction dropped from live-partial to static-host because 101511 ran `a346b5a8`. Doppelganger is static-host. There are 0 accepted videos.
- The receipt's per-row case counts (chain 7, doppel 5, airstrike 3, cover 12) match the rerun receipt.

verdict: holds. confidence: high.

## Validator rerun

Command (run on the host through `host-cmd`, because the container has no `/usr/bin/luajit`; I changed only the receipt path):

```
host-cmd bash -c 'cd <worktree> && /usr/bin/python3 tools/example_validation.py --luajit /usr/bin/luajit \
  --host /home/brunner56/kp-validation-20260922-build/kp_luatest \
  --receipt /home/brunner56/kp-live-20260922/review-probes-examples/rerun-receipt.json'
```

Output: `PASS: 41 original syntax/host regression sources, 90 per-file cases; 8 retired from public catalog; 0 live receipts attached; no public quality promotion`, exit 0.

- The original receipt's SHA-256 is `1d75734f964c779172a43526076d39279efb48a9a8b641b6b32170aa80ccdfdc`, which matches.
- `kp_luatest` is `9309dd6a3a5b…` both before and after the run.
- A leaf-by-leaf diff against the original receipt shows 4 differing leaves, all expected: `generated_utc`, `dirty_diff_sha256` (819b4b1c→c3430023, because `host.cpp` and `api-status.md` were edited by other writers after 11:15), the temporary source-map path, and the unittest wall time (3.3s→31.5s).
- Every per-example sha, case count, manifest hash and test-file hash is identical.

verdict: holds. confidence: high.

## Stage 2: adversarial

### Important

**I1. Chain reaction: public text promises restore on module load. The writer's own residual says that may not happen.**
- claim (README:13): "Their own min-one-HP flag comes back 3s after the last blast, or on an area enter, module load or script unload". Header lines 16-19 say the same thing with no condition.
- referent: The report ("Chain reaction, module-load restore") and ledger lines 236-242 say the restore uses pre-transition object IDs. If IDs change, members keep min-one-HP=1. Probes A1 and P3 (`chain_attacks.out`, `pc_probe.out`) re-create a party member or the PC under a new ID across `OnModuleLoad`. The new-ID object keeps `min_one_hp=1`, including the PC, which then cannot die.
- The ID change itself is my injected assumption. Whether K1 re-IDs party objects on `StartNewModule` is unverified.
- The window is a module transition (or a save) within 3 s of a blast. The pre-fix behaviour was worse: the flag stayed stuck always.
- fix (either one):
  - Add the caveat to README:13 and header:16-19.
  - On `OnModuleLoad`, re-resolve by stored tag or through `GetFirstPC` / `GetPartyMemberByIndex` before restoring.
- A related open item: a save or autosave inside the 3 s window would serialise flag=1, and a fresh-process load has an empty `guarded` table. This is `unverified`. It depends on save timing relative to `OnSave`, and it does not carry the verdict.
- Why this is Important and the similar Doppelganger sentence (N3) is Minor: the criterion is gameplay impact that persists. A stuck min-one-HP flag on the PC makes the player unkillable, and a save keeps it. A stuck disguise is cosmetic.

checked: README:13, header:16-19, probes A1 and P3.
verdict: holds.
confidence: high that the public text is unconditional while the residual is documented elsewhere. Low on engine ID behaviour. A live transition readback would settle it.

### Minor

- **N1. Airstrike trades a verified workaround for an unverified call.**
  - Probe M2: with `GetIsEnemy` answering 0 (the 2026-09-16 anomaly), current bytes apply 0 damage.
  - Probe M3: HEAD bytes under the same anomaly apply 2 damage.
  - Local 7 still becomes 1 with zero hits, so a route waiting on it passes vacuously.
  - The risk is documented in the header, README ("that GetIsEnemy marks hostile"), ledger and report. That is why it is Minor.
  - Recommend a live pickup with a hostile in range before featuring it.
- **N2. Stale line references.** They were valid at HEAD and drifted after concurrent edits:
  - `api-status.md:118` is now 120.
  - `api-status.md:150` is now 152.
  - `src/lua/host.cpp:296` (`Host::dispatch`) is now 532.

  The "no re-entry guard" claim still holds: `DepthGuard` counts depth and never refuses re-entry.

  The ledger's other references are current: the doppelganger test lines in `cursed.lua` (63, 108, 124, 139, 149 and 134-136) and the chain-reaction script lines (59, 68, 113, 120, 136, 169).
- **N3. Doppelganger README wording overclaims.**
  - "everyone gets their old look back" and "An area enter or module load does the same" are not true on the unavailable-actor path. The test prints "transition terminal: unavailable actor was not restored" (`cursed.lua:134-136`). This is Minor rather than Important because the effect is cosmetic; see the criterion under I1.
  - "the engine never sends it" states as absolute what `api-status.md` records as "verified 2026-09-16".
- **N4. `with_caller` mock fidelity.**
  - Unlike `routines.cpp:l_as`, the mock has no `luaL_checkinteger` or function-type check and no live-VM refusal.
  - `unpack(results, 2)` truncates at nil holes.
  - It is still adequate for this test. The mutation shows the new assertions detect a missing caller switch.
- **N5. Chain README omissions and pre-existing behaviour.**
  - The README omits that a member whose flag cannot be read is spared (so is a boolean `false` read; probe A6: the `q` wrapper maps false to nil).
  - `OnAreaEnter` from any entering object disarms and restores mid-cascade (probe A8). That behaviour existed before this change.

### Attacks that held

- **A3, P2: unload during the pending 3 s timer.** Flags are restored on unload, and the late timer makes 0 extra `SetMinOneHP` calls.
- **A4: re-entrant death during damage.** `GetMinOneHP` is read once, the original prior is kept, and the final flag is 0.
- **A5: nested generations.** Only the last timer restores (gens 1,2; the mid flag stays 1).
- **A2: failed restore.** The entry is kept, and the next `disarm` retries it successfully.
- **A7: party damage.** Party members take floor(40/3)=13.
- **P1: PC in the blast.** The PC is guarded, then restored at settle.
- **Timer API.** `kp.registertimer(ms, "chain_settle", {gen=…})` matches `timers.cpp:232-300` (string callback plus one data value). `return false` means the timer does not repeat.

### Boundary (nwscript.call only)

- The scan (`boundary_scan.py`) is case-insensitive over every `name` field in `data/routines/k1.json` and `k2.json`. That is 1345 names, a superset that includes parameter names. The ledger's routine-only count is 878.
- Product scripts `40_chain_reaction`, `100_item_airstrike`, `10_cover`, `70_doppelganger` and `10_avatar_sync` have 0 routine collisions. The single hit, `x`, is a parameter-name artefact.
- The test-mock hits in `10_avatar_sync_test.lua`, `fixture.lua`, `cursed.lua` and `probes_coverage.lua` are all table keys, reachable only through the mocked `nwscript.call`. None is a global or a `kp.*` field. `kp.as` is gone from `scripts/examples/multiplayer/` (grep is empty).

verdict: holds. confidence: high.

## Summary

- Critical: 0.
- Important: 1 (I1, chain-reaction module-load restore claim).
- Minor: 5.

Stage 1 passes in full. Under the project convention, any open Important is a FAIL. `progress.md:218` records the Pioneer Stage 0+5 review as FAIL with 0 Critical and 5 Important. `progress.md:191` records round-9 adversarial as FAIL on R9-1 Important. I1 decides the verdict, and a one-sentence caveat in README:13 and header:16-19 would clear it.

Example fixes verdict: FAIL
