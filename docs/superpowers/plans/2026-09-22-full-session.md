# Full session plan (past the packageable ASAP slice)

Extends `2026-09-22-packageable-platform-profiles.md`. That slice is **done**
(`5183ffa`: packager, profiles, pioneer pause/play/ff/rewind, docs). This plan
covers every remaining directive from the ChatGPT session export.

## Done

| Item | Evidence |
|---|---|
| Release zip + offline zip checker | `scripts/package_release.sh`, `dist/kotorphasor-0.1.0.zip` |
| AgentDecompile-style profiles (Mac `static_only`) | `data/profiles/builds.toml` |
| Pioneer TAS transport verbs (offline) | `TestPioneer` in `tools/kpharness_offline_test.py` |
| AIO per-program canon (49 packages) | `~/agentdecompile-nvme/AIO/programs/` |
| Lua/NWScript namespace contract (bridge) | `nwscript.call` + `kp.*` (boundary plan Tasks 1–2 largely landed) |

## Active workstreams (priority order)

### 1. Footlocker blaster (in progress)

- Script: `scripts/examples/cursed/110_footlocker_blaster.lua`
- Route: `scripts/harness/scenarios/cursed/110_footlocker_blaster.toml`
- Requirements still to **prove live**: flying `footlker001` on the bolt path,
  console `footammo` retarget, dual-wield/burst, knockback tumble, gif/mp4.
- Native LoadModel trampoline (sig `k1.after_load_model_5`) is located at arm
  time; in-place mdl rewrite is the follow-on once the placeable path is green.

### 2. Example gallery quality + validation

- Retired from public pack: `50_chaos_roulette`, `60_rave` → `scripts/examples/_retired/cursed/`
- Remaining cursed demos must pass `record_cursed.sh` with gif evidence.
- Doppelganger and any documented failures stay individually tracked.

### 3. kp.* / nwscript.call + harness TOML docs

- Finish boundary plan Task 3 (driver/scenario TOML references, recursive offline parse).
- Keep zero bare engine routine names as Lua globals.

### 4. F12 / live Lua console

- Cheat-console `lua exec` + `OnConsoleCommand` already live.
- F12 Chrome-devtools-like overlay: basic execute ASAP; Godot-like editing roadmap.

### 5. Live pioneer TAS proof

- Offline verbs done; need one live K1 session pause/play/ff/rewind against harness.

### 6. Mac Mach-O

- Profiles registered `static_only`; `src/image` is PE/ELF only.
- Next: Mach-O `Format` + loader, then address tables for k1_mac / k2_mac.

### 7. WASM / browser embed (lowest)

- No game IP in git; user-supplied local assets.
- Shared tooling pipeline with F12 console.

## Constraints (unchanged)

1. No game content / IP in the repo or release zip.
2. `kp.*` vs `nwscript.call` strict separation.
3. Harness/route TOML owned separately from runtime INI.
4. Builds identified by content hash / portable signatures.
5. Completion requires behavior + evidence, not mocks alone.
