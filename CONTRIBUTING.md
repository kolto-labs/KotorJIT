# Using KotorPhasor

Build, install, supported builds, and where the scripting docs live. Why this exists is in [README.md](README.md).

## Build

You need a 32-bit Windows cross-compiler and LuaJIT built for that target.

```sh
sudo dnf install mingw32-gcc-c++ mingw32-binutils glibc-devel.i686 libstdc++-devel.i686

git clone --branch v2.1 https://github.com/LuaJIT/LuaJIT third_party/luajit
make -C third_party/luajit HOST_CC="gcc -m32" CROSS=i686-w64-mingw32- TARGET_SYS=Windows BUILDMODE=static

cmake -S . -B build
cmake --build build
```

That produces `build/kphasor.dll` and the proxy `build/binkw32.dll`. `BUILDMODE=static` matters. Without it, LuaJIT's Windows build only produces `lua51.dll`, not the static archive `kphasor.dll` needs.

On Debian/Ubuntu the packages are `g++-multilib`, `g++-mingw-w64-i686`, and `binutils-mingw-w64-i686`. The exact CI recipe, including the native Linux build for KOTOR 2, is [`.github/workflows/cmake-multi-platform.yml`](.github/workflows/cmake-multi-platform.yml).

Build, install, and first-run steps: [`docs/user/install.md`](docs/user/install.md).

## Install into the game

```sh
./scripts/install_to_game.sh install /path/to/swkotor
```

Scripts go in `<game>/kotorphasor/scripts`. The log is `<game>/kotorphasor.log`. In the cheat console: `lua exec`, `lua status`, `lua reload`.

## Supported builds

| Game | Build | Status |
|---|---|---|
| KOTOR 1 | GOG, Windows | Supported |
| KOTOR 1 | Steam, Windows | Supported (identical `.text` to GOG once deciphered) |
| KOTOR 1 | Amazon Games, Windows | Registered, not yet installable: no matchable engine symbols to bind hook sites |
| KOTOR 1 | Mac (Aspyr) | Registered / static_only: corpus signatures exist; no Mach-O loader in the PE/ELF runtime yet |
| KOTOR 2 | Native Linux (Aspyr) | Supported: routines and events. `kotor.struct` is unverified on this build (see below) |
| KOTOR 2 | GOG Aspyr, Windows | Supported |
| KOTOR 2 | Steam Aspyr, Windows | Supported |
| KOTOR 2 | Mac (Aspyr) | Registered / static_only: same Mach-O loader gap as K1 Mac |
| KOTOR 2 | Retail CD 1.0 / 1.0b, Windows | Registered, not yet installable: same reason as K1 Amazon Games |

Machine-readable profile table: [`data/profiles/builds.toml`](data/profiles/builds.toml) (`python3 tools/list_profiles.py`). See [`docs/user/platform-profiles.md`](docs/user/platform-profiles.md).

"Supported" means every required hook site resolves and the runtime installs. The routine bridge (`kotor.<Name>`) and event dispatch both work. It does not mean every corner is verified. K2's struct field layouts (`kotor.struct` / `kp.struct`) were researched against the K1 build only. Typed field access on a K2 build may read the wrong offset. Raw `kotor.mem.*` does not use that research. Full detail: [`docs/user/api-status.md`](docs/user/api-status.md).

The runtime identifies a build by hashing its code section, never by filename or file size. An executable it doesn't recognize is left unpatched. The game runs as if KotorPhasor weren't installed.

## What fires today

These callbacks run in a live game: `OnScriptLoad`, `OnScriptUnload`, `OnTick`, `OnRunScript`, `OnRunScriptDone`, `OnConsoleCommand`, `OnSave`, `OnLoad`, `OnModuleLoad`, `OnModulePlayerEnter`, `OnAreaEnter`, `OnCreatureAttacked`. Every other `EventHandler` name (doors, placeables, triggers, encounters, areas-of-effect, the store, waypoints) is installed and fires when the engine raises that event id.

Two names look like they should work and don't: `OnCreatureHeartbeat` and `OnDialogConditional` never run. The engine doesn't route those cases through a name a Lua callback can bind. Filter `OnRunScript` by `script_name` instead. See [`docs/user/scripts.md`](docs/user/scripts.md).

769 of KOTOR 1's 772 engine routines, and 803 of KOTOR 2's 877, are callable as `kotor.<Name>`. Bound, spec-only, or proven live: [`docs/user/api-status.md`](docs/user/api-status.md). Argument lists (from the engine's own signatures) are in [`docs/lua-api.md`](docs/lua-api.md) and [`docs/nwscript-api.md`](docs/nwscript-api.md).

## Write a script

Full guide: [`docs/user/scripts.md`](docs/user/scripts.md).

```lua
priority = 10

function OnScriptLoad(game, build)
    print("loaded on " .. tostring(game) .. " " .. tostring(build))
end

function OnRunScript(script_name, object_id, has_object, relevant)
    if script_name == "k_ambush_spawn" then
        return false
    end
end
```

`AssignCommand`, `DelayCommand`, and `ActionDoCommand` need a script closure NWScript can build and Lua can't. Use `kp.as(object_id, function() ... end)` and `kotor.registertimer(ms, "callback_name", data)`.

## Multiplayer

Direct UDP between two game instances, using the engine's own socket library. No proxy DLL. No relay server. Script: [`scripts/examples/multiplayer/10_avatar_sync.lua`](scripts/examples/multiplayer/10_avatar_sync.lua). Tests: `10_avatar_sync_test.lua`.

## Finding a codecave

`data/codecaves.toml` has thousands of individually verified unused-byte spans (16,184 today) across every supported build. They are addressed by `kotor.mem.findsig`, not a hardcoded VA, so the same script works where the surrounding bytes match. See [`docs/user/codecaves.md`](docs/user/codecaves.md).

## Testing

Two tiers. Neither needs Star Wars IP in this repo.

**Tests** (default, offline, no game): the Lua host, event arbitration, struct layout, entity API, memory module, and hook engine. Script fixtures live under `scripts/examples/`. Generated tables live under `src/generated/`. Memory and hook tools probe this process.

```sh
cmake -S . -B build && cmake --build build
ctest --test-dir build --output-on-failure
```

**Real-game smoke test** (opt-in, your Steam KOTOR 1 install and Wine): `scripts/harness/` runs the game under Xvfb, for K1 and K2.

```sh
./scripts/harness/spike_headless_k1.sh
```

The rest of [`scripts/harness/`](scripts/harness/) covers live sessions, gameplay regression tests, and demo scenes.

`/agentdecompile_projects/` is local scratch for `agentdecompile-cli` (a Ghidra project built from your own game binary). It is gitignored. That path was removed from `main`'s history. Do not commit it.

Regenerating `data/addresses/*.json` or `src/generated/builds.inc` needs the local reverse-engineering corpus and the per-build reference images. Without the images, `tools/gen_address_tables.py` drops `expected_bytes` and can truncate `builds.inc`. Do not commit a regen that was run without those images.

## Uninstall

```sh
./scripts/install_to_game.sh status    /path/to/swkotor
./scripts/install_to_game.sh uninstall /path/to/swkotor
```

Restores the original `binkw32.dll` and removes `kphasor.dll`. Scripts and `kotorphasor.log` stay.

## Further reading

- [`docs/user/`](docs/user/) starts at [`docs/user/README.md`](docs/user/README.md)
- [`docs/event-semantics.md`](docs/event-semantics.md): how the engine dispatches events, from recovered source, including slots you can't reach through the obvious hook
- [`ATTRIBUTION.md`](ATTRIBUTION.md): what this design is built on
- [`CHANGELOG.md`](CHANGELOG.md): what shipped, by version
