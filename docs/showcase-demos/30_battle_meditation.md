# 30_battle_meditation

**Script:** `scripts/examples/showcase/30_battle_meditation.lua`  
**Hook:** `OnRunScript` / `k_def_attacked01`  
**Save:** `pick_save.sh dantooine_party` (**Game37** — Bastila in party)  
**Module:** `manm26ad` (combat after party verified)

## Trigger semantics

- Victim must be a **party member** (`IsObjectPartyMember(object_id)`)
- **Bastila** must be conscious in party (`GetTag` lowercase `bastila`)

Endar Spire save fails: no Bastila. Real combat on `manm26ad` usually makes the
Sith the victim, not the party.

## Success oracle

```text
[meditation] round <n>: steadied <m> of the party
```

## Queue sequence

1. `pick_save.sh dantooine_party` — console is **open** after boot; do not `#console` first
2. `heal`, `addlevel` (optional)
3. **Deterministic hook first** (console must stay open):

   ```text
   lua exec kotor.ExecuteScript('k_def_attacked01', kotor.GetFirstPC(), 0)
   ```

   Wait for `[meditation]` in `kotorphasor.log` before warping.
4. `warp manm26ad` (closes console — reopen with one `#console` before typing)
5. Walk + combat for footage (`#key w` / Tab + attack clicks)

**Do not** toggle `#console` before the first `lua exec` — that closes the boot-opened console and types into gameplay instead.

## Recording

Show party combat first; meditation line should appear before end of ~60s clip.
