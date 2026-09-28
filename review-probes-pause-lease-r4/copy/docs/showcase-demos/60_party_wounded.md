# 60_party_wounded

Retired from the public showcase on 2026-09-22. This is an internal regression
playbook; its source is `tools/tests/examples/fixtures/legacy/showcase/60_party_wounded.lua`.
Historical live results and unresolved obligations remain unchanged.

**Script:** `tools/tests/examples/fixtures/legacy/showcase/60_party_wounded.lua`
**Hook:** `OnRunScript` / `k_def_damage01`  
**Save:** `pick_save.sh endar` (Carth in party on Endar Spire)  
**Module:** `end_m01aa`

## Trigger semantics

Party member below **35% HP** when `k_def_damage01` runs on that member.

## Success oracle

```text
[wounded] <tag> below 35%
```

## Queue sequence

1. `heal`
2. `warp end_m01aa` → verify `MOD=end_m01aa`
3. `#console` closed; `#key w` ×6 into scripted Sith encounter
4. Tab + attack clicks for 12+ rounds. Focus fire can stay on PC; companions take AoE.
5. Retry fight rounds if `[wounded]` missing

Expect `[probe] script:k_def_damage01` before `[wounded]`.

## Recording

Endar combat walk + sustained fight until companion callout (~60s).
