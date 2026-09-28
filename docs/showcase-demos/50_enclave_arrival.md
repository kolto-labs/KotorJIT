# 50_enclave_arrival

Retired from the public showcase on 2026-09-22. This is an internal regression
playbook; its source is `tools/tests/examples/fixtures/legacy/showcase/50_enclave_arrival.lua`.
Historical live results and unresolved obligations remain unchanged.

**Script:** `tools/tests/examples/fixtures/legacy/showcase/50_enclave_arrival.lua`
**Hook:** `OnTick` (every 45 ticks; fires on module prefix change)  
**Save:** `pick_save.sh any`  
**Modules:** `danm13` then `manm26ad`

## Success oracle

```text
[arrival] dan
[arrival] man
```

## Queue sequence

1. `warp danm13`
2. `#sleep 55` (allow module load + tick samples)
3. Optional: 10× `#click 0.52 0.62` with `#sleep 1` (movement for recording)
4. `#sleep 20`
5. `warp manm26ad`
6. `#sleep 55`
7. Optional: 10× ground clicks
8. `#sleep 20`

## Notes

Uses `GetModuleName()` prefix (`dan`, `man`, …). Script state `seen` persists
per save via `OnSave`/`OnLoad`. Use a save that has not already triggered both
lines, or redeploy scripts on a fresh session.

`test_enclave_arrival.sh` uses `manm26ad` (Sith base), not `manm26aa` (Ahto docks).

## Recording

Both warps and walks should appear in mp4; arrival lines may occur during `#sleep` windows.
