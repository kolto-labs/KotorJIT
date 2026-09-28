# Packageable platform profiles (ASAP slice)

## Goal

Ship a packageable KotorPhasor surface from what already works, with AgentDecompile-style binary profile unification for K1/K2 Windows GOG (and Mac registered), plus Ren'Py-like pioneer transport verbs for TAS authoring. No Unity Engine. No game assets in the package.

## Global Constraints

1. Ships no game content / IP; user must bring their own install.
2. Lua (`kp.*`) and NWScript (`nwscript.call`) stay strictly separate namespaces.
3. Harness/route TOML stays separate from runtime INI and is documented as driver config.
4. Runtime identifies builds by code-section hash / portable signatures, never filename alone.
5. Mac may be registered via signature tables before a Mach-O loader exists; do not claim "Supported" until hooks install.
6. Prefer reuse of existing harness channel verbs (`speed`, `clear_auto_pause`, checkpoints) over new engine paths.
7. Do not commit secrets, game binaries, or corpus.sqlite.
8. Token budget is tight: smallest working slice first; WASM and footlocker remain out of scope for this plan.

## Proof bar (prove-the-effort)

| Claim | Concrete referent that closes it |
|---|---|
| Packageable ASAP | `scripts/package_release.sh` produces a zip; `install_to_game.sh` works from that zip's contents against a built `kphasor.dll`/`binkw32.dll` layout |
| Platform unification | `data/profiles/*.toml` (or equivalent) lists logical_id→build profiles for k1_gog_103, k2_gog_aspyr, k1_mac, k2_mac with status + format; Mac marked `static_only` until Mach-O Format exists |
| Pioneer TAS transport | `kpharness pioneer pause|play|ff|rewind` maps to live channel/`load_checkpoint` and is covered by an offline unit test |

## Tasks

### Task 1: Release packager

Create `scripts/package_release.sh` that:

1. Requires existing `build/kphasor.dll` and `build/binkw32.dll` (optional `build/libkphasor.so`).
2. Stages into `dist/kotorphasor-<version>/`: DLLs, optional SO, `scripts/install_to_game.sh`, `data/addresses/`, curated `scripts/examples/cursed/` + showcase remnants that are public, `docs/user/install.md`, `README.md`, `CONTRIBUTING.md` (supported builds section), `LICENSE`/`ATTRIBUTION.md` if present.
3. Excludes game assets, corpus, logs, agentdecompile scratch, `.git`.
4. Emits `dist/kotorphasor-<version>.zip` and prints its path + sha256.
5. Add a tiny offline check (shell or python) that the zip contains required members and no forbidden paths (`*.exe` game, `corpus.sqlite`, `kotorphasor.log`).

Do not rebuild the whole project unless artifacts are missing and a fast rebuild is possible.

### Task 2: Platform profile registry (AgentDecompile-aligned)

1. Add `data/profiles/README.md` explaining: logical site names + portable signatures + per-build address cache; mirrors AgentDecompile hook-pack / portable signature concepts (NOT Unity).
2. Add machine-readable profiles for at least: `k1_gog_103`, `k1_steam_103`, `k2_gog_aspyr`, `k2_steam_aspyr`, `k1_mac`, `k2_mac` with fields: `game`, `platform`, `format`, `status` (`supported`|`registered`|`static_only`), `address_table` (path or null), `note`.
3. Wire `tools/gen_address_tables.py` BUILDS notes or a small `tools/list_profiles.py` so packaging/docs can dump the table.
4. Update `CONTRIBUTING.md` Supported builds table: Mac rows as Registered/static_only (signature tables; no Mach-O loader yet). Do not claim Mac installable.

Proof: `python3 tools/list_profiles.py` (or equivalent) prints the six profiles with statuses.

### Task 3: Pioneer pause / play / ff / rewind

Extend `scripts/harness/kpharness/` so TAS transport is idiomatic:

```
kpharness pioneer pause  --target k1
kpharness pioneer play   --target k1
kpharness pioneer ff     --target k1 [--scale 4]
kpharness pioneer rewind --target k1 --checkpoint NAME
```

Mapping:

- `pause` → channel `speed` with scale `0` if supported, else document fallback via `clear_auto_pause` NOT being pause; if engine rejects 0, use the smallest supported scale and set a paused flag via existing pause-clearing inverse only if a real pause command exists. Prefer: request `speed` scale=0.001 or existing pause path if any; if only `speed` exists, pause := very low speed + note in help text.
- `play` → `speed` scale=1.0 + `clear_auto_pause` + `unpause_timers` as best-effort.
- `ff` → `speed` with `--scale` default 4.0 (clamp to harness max 16).
- `rewind` → restore named checkpoint via `Checkpoints` + `load_save`/`load_checkpoint` path already used by scenario verbs (must reuse ScenarioRunner or Checkpoints.restore + channel load).

Also allow encoding these as pioneer `step` JSON bodies (`{"do":"pause"}` etc.) so they commit into route TOML.

Offline tests in `tools/kpharness_offline_test.py` (or a focused new test module) covering CLI parsing / step serialization without a live game.

### Task 4: Docs + offline proof gate

1. `docs/user/install.md`: mention `package_release.sh` and zip install path.
2. Short `docs/user/platform-profiles.md` linking AgentDecompile concepts (portable signature / hook pack) to KotorPhasor profiles.
3. `docs/scenario-toml.md` or harness pioneer section: document pause/play/ff/rewind.
4. Run offline proofs: package zip member check + profile list + pioneer offline tests. Record commands/output in the task report.

## Out of scope (do not implement in this plan)

- Mach-O runtime loader / Mac live inject
- Footlocker blaster / WASM browser embed
- Publishing game assets
- Full Godot-like editor / dialogue rollback beyond checkpoint rewind
