# Changelog

## Unreleased

Everything below is merged to `main` but not yet cut into a numbered release.

- **Renamed KotorPhasor to ScriptForge** (`scriptforge.dll` / `libscriptforge.so` / `libscriptforge.dylib`, `<game>/scriptforge/`, `scriptforge.ini`, `scriptforge.log`, `scriptforge-proxy.log`, `SCRIPTFORGE_*` environment variables), keeping `KotorPhasor` fallbacks (`kphasor.dll`, `kotorphasor/`, `kotorphasor.ini`, `KOTORPHASOR_*`, `libkphasor.dylib` symlink) and preserving the Lua API (`kp.*`, `nwscript.*`) and serialized schema ids (`kotorphasor.native-receipt/v1`, `kotorphasor.install-manifest/v1`).
- **Strict exact-bytes hooking:** ScriptForge requires exact expected bytes at every hook site and refuses to install if another code patch has altered those bytes (never chains foreign detours).
- **KPM-style deployment methods & optional `binkw32.dll` proxy:**
  - Windows runtime-injection launcher (`scriptforge-launch.exe`): `CREATE_SUSPENDED` + remote `LoadLibraryA` (`direct` mode for GOG/unpacked/K2 Aspyr) plus delayed Steam/attach injection for SteamStub builds (`steam` / `attach` modes).
  - Address-preserving ELF32 `DT_NEEDED` editor (`tools/elf_needed.py`) repurposing `PT_NOTE` into a read-write `PT_LOAD` segment, paired with exact `.text` / `__text` verification in `kp::image::load()` for loader-modified ELF32 and Mach-O executables.
  - `--method` / `-Method` switches in `scripts/install_to_game.sh` (`auto|proxy|inject|linked|preload`) and `Install-ScriptForge.ps1` (`Auto|Inject|Proxy`), keeping `binkw32.dll` proxy support for Proton/Wine and packed Steam K1.
  - DLL-only `.kpatch` package (`kpatch/`, `scripts/package_kpatch.py` -> `dist/scriptforge.kpatch`) and compiled-in embedded address-table fallback (`tools/gen_embedded_addresses.py` -> `src/generated/embedded_addresses.inc`) so KPM can load ScriptForge directly without an extracted `addresses/` folder.

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
