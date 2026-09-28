# Native projectile visual selection

The first projectile capability observes the engine's existing projectile model loads and can select another locally installed model for newly loaded PC blaster projectiles. It requires the verified Windows K1 GOG executable. Other images/platforms report unsupported. It starts disabled, with observation off.

Use F12 and the normal engine-thread Lua command service:

```lua
kp.projectiles.status()
kp.projectiles.observe(true)
-- Fire ordinary blasters, then inspect the actual load records:
for _, r in ipairs(kp.projectiles.records()) do print(r.sequence, r.reason, r.original, r.load_ok) end

assert(kp.projectiles.configure { model = 'plc_footlker' })
-- Subsequent matching projectile loads select the footlocker model.
assert(kp.projectiles.configure { model = 'plc_crate' })
kp.projectiles.disable()
kp.projectiles.observe(false)
```

`configure` returns the new status, or `nil, reason`. It validates a 1–16 character resource name, asks the running engine for MDL and MDX availability, and reads its installed ammunition table before publishing a new immutable configuration. Invalid selections leave the previous configuration intact. Availability does not prove that every model is compatible with the engine's projectile animation wrapper. A selected-model load failure follows the original engine failure path; Phasor does not retry a potentially half-initialized wrapper.

The initial filter covers verified ammunition rows labelled Blaster, Ion, Disruptor, Sonic and Bowcaster, with Model0/Model1 variants. It reads actual model names from those installed rows and requires the captured load's row, variant and original resource to match. Unknown rows, variants, changed tables, unresolved sources and non-PC sources retain stock arguments. The current PC server identity is freshly resolved and converted to client identity for each observed load. Configuration has no cached actor pointer. Equipment modes, both hands, repeated bursts, misses and complete weapon coverage require separate live evidence.

`status()` includes `supported`, `reason`, `build`, `epoch`, `observing`, `enabled`, `version`, `model`, `observed`, `replaced`, `dropped` and `capacity`. Observation counters describe model loads, not hits or combat rounds. `disable()` restores stock selection for future loads while leaving observation on if requested. `observe(false)` suppresses stock observation; replacement still records its filtering decisions while enabled. To return to the minimal stock path, disable both.

`records()` returns the newest 128 load records in order. Each includes `sequence`, `projectile_token`, `epoch`, `version`, `source_client`, `target_client`, `ammo_row`, `model_variant`, `original`, `selected`, `replaced`, `load_ok` and `reason`. The token identifies this load observation, not a persistent engine object or an impact. Records include exclusions (`other_callsite`, `source_unresolved`, `non_pc`, `unclassified`, `ammunition_table_changed`) so zero replacements are distinguishable from absent observation. Unrecognized callers are not decoded and their source/resource fields are unset. Oldest records are evicted with an explicit dropped count. Rebinding starts a new epoch and clears records/configuration.

The hook calls the original loader once, preserving the original two loader flags and return result. The engine continues to own model wrappers, flight, targeting, attachment, damage and destruction. Changing or disabling selection does not replace already loaded projectiles. The hook runs no Lua, resource scans or model construction outside the original engine load; configuration queries run through the existing engine command pump. Model assets remain local and are not shipped with Phasor.

This capability does not implement hit correlation, knockback, tumbling, articulated ragdolls, projectile scale/orientation controls, or the complete object-blaster example. Those require further native authority and live validation. Runtime hook uninstall follows the existing quiescent-shutdown requirement; arbitrary DLL unloading while engine callbacks are executing is unsupported.

Native slot installation uses compare-and-swap against the verified original loader. A changed slot is left untouched. If native page protection cannot be restored, status reports an unsupported cleanup reason and both replacement and observation remain disabled; retained transaction state allows a later quiescent cleanup retry without forgetting the original protection or overwriting another slot owner.
