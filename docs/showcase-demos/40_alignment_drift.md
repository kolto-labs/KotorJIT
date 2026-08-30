# 40_alignment_drift

**Script:** `scripts/examples/showcase/40_alignment_drift.lua`  
**Hook:** `OnTick` (samples every **180** ticks ≈ 45s at ~4 ticks/s)  
**Save:** `pick_save.sh any`

## Success oracle

```text
[conscience] +<delta>, now <value>
```

## Queue sequence

1. Optional: `lua exec print(kotor.GetGoodEvilValue(kotor.GetFirstPC()))`
2. `lua exec kotor.AdjustAlignment(kotor.GetFirstPC(), 2, 30)` — shift **toward light** by 30
3. `#sleep 90` (two tick samples)
4. If no `[conscience]`: `AdjustAlignment(..., 1, 30)` toward dark + `#sleep 90`

Uses `GetGoodEvilValue`, not `GetAlignmentGoodEvil`. Crossing a **decade**
boundary (e.g. 58→80) is required.

## Notes

No warp or combat needed. Primary path is engine `AdjustAlignment`; dialogue
alignment shifts are optional for manual discovery.

## Recording

Short walk clicks after alignment line for visible gameplay in mp4.
