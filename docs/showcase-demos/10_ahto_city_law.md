# 10_ahto_city_law

**Script:** `scripts/examples/showcase/10_ahto_city_law.lua`  
**Hook:** `OnRunScript` / `k_def_attacked01`  
**Save:** `pick_save.sh any`  
**Module:** `manm26ad` (Manaan Sith base — not peaceful Ahto City)

## Trigger semantics

Fires when **PC is the attacker** on Manaan (`GetModuleName()` prefix `man`):

- `object_id` = victim
- `GetLastAttacker(object_id) == GetFirstPC()`

Enemy-only combat (PC is victim) does **not** print `[ahto]`.

## Success oracle

```text
[ahto] strike <n> witnessed on Manaan
```

## Queue sequence

1. `heal`, `addlevel`
2. `warp manm26ad` → verify `MOD=manm26ad` in log
3. `#console` closed; 14× `#click 0.52 0.62` (`#sleep 1` between)
4. `#key Tab` + attack clicks (`#click 0.50 0.38`) for several rounds
5. If no `[ahto]`: `ActionAttack` nearest hostile via console, then more attack clicks

## kq

```bash
./scripts/harness/kq.sh grep -m manm26ad -t utc | head
```

## Recording

Combat clicks + `[trace]` lines prove real movement under headless llvmpipe.
