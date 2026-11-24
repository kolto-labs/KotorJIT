# Changelog

## Unreleased

Everything below is merged to `main` but not yet cut into a numbered release.

- **Renamed KotorPhasor to Hyperstim.** New names: `hyperstim.dll` / `libhyperstim.so` / `libhyperstim.dylib`, the `<game>/hyperstim/` data folder (scripts, hook packs, manifests, address overlays), `hyperstim.ini`, `hyperstim.log`, `hyperstim-proxy.log` and `HYPERSTIM_*` environment variables. Nothing an existing install relies on stops working:
  - the proxy loads `hyperstim.dll` and falls back to `kphasor.dll`;
  - the runtime uses `<game>/kotorphasor/` when that is the only data folder present, reads `kotorphasor.ini` when there is no `hyperstim.ini`, and accepts every `KOTORPHASOR_*` variable when its `HYPERSTIM_*` form is unset;
  - the installers recognise old proxies as ours (never as the original Bink), move a legacy `kotorphasor/` folder to `hyperstim/`, and on macOS point an existing `libkphasor.dylib` at the new runtime so old Steam launch options keep working. The Windows installer reads and uninstalls installs recorded under `kotorphasor\`;
  - receipt validation accepts both start banners.
  - Unchanged on purpose: the Lua API (`kp.*`, `nwscript.*`), and serialized format ids such as `kotorphasor.native-receipt/v1` and `kotorphasor.install-manifest/v1`. One visible difference: the Phasor-compat `host` / `serverapp` values now read `"Hyperstim"`.

- KOTOR 2 support: native Linux, GOG Aspyr (Windows), and Steam Aspyr (Windows) all install cleanly and run scripts. The routine bridge and event dispatch both work. `kotor.struct` field offsets are the one piece still unverified on K2 (researched against K1's build only). `kotor.mem.*` and everything else are unaffected.
- A self-contained multiplayer example (`scripts/examples/multiplayer/10_avatar_sync.lua`): direct UDP sync between two game instances, no external process, using the engine's own socket library from Lua.
- `data/codecaves.toml`: thousands of individually verified, signature-addressed unused-byte spans across every supported build, for scripts that need somewhere to inject raw code.
- CI (`.github/workflows/cmake-multi-platform.yml`) builds the project on gcc and clang from a clean checkout. It had never passed before the toolchain gaps in that workflow were fixed.
- ARM32 (Thumb-2) length-disassembler and detour engine in `src/hooks/arm32/`. Proven under `qemu-arm`. Not wired into the runtime yet. Android, iOS, and Xbox support are unstarted.

## 0.1.0 (2026-08-30)

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
