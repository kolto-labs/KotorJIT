# Task 13 Doppelganger final route-oracle verification

## Verdict

**PASS.** The corrected TOML now encodes the complete `1 -> 2 -> 1 -> 0` disguise-count proof for each of exactly three marked, living hostile actors while retaining the same-payload baseline constructor tokens across garbage collection.

## Static verification

- **Baseline `1`:** `scripts/harness/scenarios/cursed/70_doppelganger.toml:48-50` applies one `EffectDisguise(P)` baseline to each marked hostile, retains each constructor token in `doppel_hostile_baseline_tokens`, enumerates disguise effects, requires `effects == 1`, records that value in local slot 101, and forces collection while the tokens remain globally reachable.
- **Active `2`:** route lines 63-65 require each marked living hostile to read appearance `P` and require its independently enumerated disguise count to equal recorded slot 101 plus one. Because the baseline gate fixed slot 101 at one, this proves the script-owned same-`P` disguise landed as the second effect; row and counter evidence are no longer the sole oracle.
- **Post-script cleanup `1`:** lines 77-87 require all three marked actors to remain alive at row `P` and independently enumerate exactly the recorded baseline count. This proves the script-owned disguise delta disappeared while the identical baseline survived.
- **Post-baseline cleanup `0`:** lines 90-93 retrieve each retained baseline constructor token, require recorded baseline count one, remove that exact token, and require zero disguise effects plus restoration of each actor's recorded original row `E`. It also removes the retained PC baseline token and requires zero PC disguises.
- **Exact actor scope:** the active oracle requires `copied == 3` and PC local counter `== 3`; unmarked hostile actors already reading `P` cause failure. Every later stage independently requires all three marked actors to remain living and present.

No Critical or Important findings remain in the requested TOML oracle scope. This is a static verification of the route definition; the manifest correctly continues to require an actual fresh serialized K1 run before live promotion.

No tests, inventory generation, build, or game process were run.
