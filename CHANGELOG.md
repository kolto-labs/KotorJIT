# Changelog

## Unreleased

Everything below is merged to `main` but not yet cut into a numbered release.

- KOTOR 2 support: native Linux, GOG Aspyr (Windows), and Steam Aspyr (Windows) all install cleanly and run scripts — the routine bridge and event dispatch both work. `kotor.struct` field offsets are the one piece still unverified on K2 (researched against K1's build only); `kotor.mem.*` and everything else are unaffected.
- A self-contained multiplayer example (`scripts/examples/multiplayer/10_avatar_sync.lua`): direct UDP sync between two game instances, no external process, using the engine's own socket library from Lua.
- `data/codecaves.toml`: thousands of individually verified, signature-addressed unused-byte spans across every supported build, for scripts that need somewhere to inject raw code.
- CI (`.github/workflows/cmake-multi-platform.yml`) actually builds the project now, on both gcc and clang, from a clean checkout — it had never once passed before this pass found and fixed the toolchain gaps.
- A standalone, rigorously self-tested ARM32 (Thumb-2) length-disassembler and detour engine (`src/hooks/arm32/`) — not yet wired into the real runtime, and Android/iOS/Xbox support more broadly is still unstarted, but the hardest single piece (correctly patching ARM instructions without corrupting them) is built and proven under `qemu-arm`.

## 0.1.0 — 2026-08-30

First public cut. KOTOR 1 Steam (Windows) is the supported game.

What works in a running game:

- 15 hooks install on the unpacked Steam image
- Lua scripts load from `<game>/kotorphasor/scripts`
- `OnRunScript`, `OnTick`, `OnScriptLoad`, `OnConsoleCommand`, `OnSave`, `OnLoad`
- Typed object events that reach `EventHandler` (module load, area enter, creature attacked, and the rest of that set)
- 769 of 772 engine routines as `kotor.<Name>`
- Cheat-console commands `lua exec`, `lua status`, `lua reload`
- `kp.as`, `kotor.registertimer`, `kotor.obj` / `kp.obj`, `kotor.struct` / `kp.struct`, `kotor.mem`

What does not work yet:

- Named callbacks such as `OnCreatureHeartbeat` and `OnDialogConditional` never fire. Filter `OnRunScript` instead.
- `AssignCommand`, `DelayCommand`, and `ActionDoCommand` are not bound
- Most `kp.*` names in `data/hostapi.toml` are not registered (use the names in [docs/user/api-status.md](docs/user/api-status.md))
- KOTOR 2 native Linux is not a 0.1.0 target
- `DelayCommand` resumes (`vm.run_script_situation`) are not hooked

See [docs/user/](docs/user/) for install, scripting, and the full status list.
