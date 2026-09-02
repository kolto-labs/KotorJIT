## Learned User Preferences

- Prefer inline terminal commands over writing Python scripts or test files to the filesystem.
- Do not run headless swkotor harness demos to verify Lua work; confirm codecaves and Lua host accuracy instead.
- Use `ctest --test-dir build --output-on-failure` as the default, fast, offline check (no game, no Wine). `scripts/harness/` stays the separate opt-in real-game smoke test.
- When asked for hands-off execution, complete build, implement, and debug without pausing for confirmation.
- Replace Halo/Phasor-specific APIs with KOTOR-specific names; do not invent Halo-style helpers such as `getplayer` or `getobject`.
- Keep client, server, and multiplayer functions and events; treat KOTOR as multiplayer with the singleton player on the local server.
- Name functions, commands, and events from Ghidra data via `agentdecompile-cli`.

## Learned Workspace Facts

- KotorPhasor is a resident LuaJIT host that intercepts KOTOR NWScript events, arbitrates multi-script answers (first usable return wins), and exposes engine routines plus host modules to Lua.
- Lua system code lives in `src/lua`, `src/api`, `src/events`, and `src/runtime`; public contracts are `docs/lua-api.md`, `docs/api-dialects.md`, `docs/event-semantics.md`, `docs/host-api-design.md`, `docs/nwscript-api.md`, `data/events.toml`, `data/hostapi.toml`, and `data/api_aliases.toml`.
- Primary target is Steam KOTOR 1 (Windows); KOTOR 2 native Linux is in progress. Addresses live in `data/addresses/` and are keyed by executable hash.
- 769 of 772 engine routines are callable from Lua; `AssignCommand`, `DelayCommand`, and `ActionDoCommand` need NWScript closures, so use OnTick timers instead of `DelayCommand`.
- Milestone and living-plan docs live under `docs/` (including `docs/PLAN-M1.md`).
- Git on this external drive is often slow or hangs; prefer Read and Grep for inspection.
- `origin` may still say `arrenkaetris/KotorPhasor`; GitHub resolves that to `bodencrouch/KotorPhasor` (same repo).
- `/agentdecompile_projects/` is local Ghidra scratch, gitignored, and purged from `main` history. Never commit it.
- Do not regenerate `data/addresses/` or `src/generated/builds.inc` without local reference images; a corpus-only run drops `expected_bytes` and can truncate `builds.inc`.
