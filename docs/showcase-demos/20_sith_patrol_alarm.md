# 20_sith_patrol_alarm

**Script:** `scripts/examples/showcase/20_sith_patrol_alarm.lua`  
**Hook:** `OnRunScript` / `k_def_percept01` (runs on the perceiver)  
**Save:** `pick_save.sh endar`  
**Module:** `end_m01aa` (Endar Spire opening)

## kq research

```bash
./scripts/harness/kq.sh grep 'ScriptOnNotice = "k_def_percept01"' -m end_m01aa
```

Creatures include `end_bridgesith1`, `end_reinforce`, etc.

## Success oracle

```text
[alarm] <name> raised the alarm (<n> so far)
```

Also expect `[probe] script:k_def_percept01` and `[trace]` if position trace deployed.

## Queue sequence (discovery)

Repeat up to **3 rounds** until `[alarm]` appears:

1. `warp end_m01aa`
2. `#sleep 4` (module still loading; live_session adds ~45s on warp internally)
3. `#console` (close console for movement)
4. Six times: `#key w`, `#sleep 1.5`
5. `#sleep 3`
6. `#console` (reopen)
7. Grep log for `\[alarm\]`

## Notes

The hostile **first-perceives-PC** moment is one-shot. Scripted Endar combat often
aggros before the party reaches the sentry. This demo is flaky by design.
Retry fresh warps; do not use `ExecuteScript` for the happy path.

## Recording

`demo_play.sh` runs three Endar rounds then ~8 ground `#click` steps for visible movement (~60s total).
