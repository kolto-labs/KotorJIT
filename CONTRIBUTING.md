# Using KotorPhasor

Technical reference: build, install, supported builds, and where to go for scripting details. For what this is and why, see [README.md](README.md).

## Build

You need a 32-bit Windows cross-compiler and LuaJIT built for that target.

```sh
sudo dnf install mingw32-gcc-c++ mingw32-binutils glibc-devel.i686 libstdc++-devel.i686

git clone --branch v2.1 https://github.com/LuaJIT/LuaJIT third_party/luajit
make -C third_party/luajit HOST_CC="gcc -m32" CROSS=i686-w64-mingw32- TARGET_SYS=Windows BUILDMODE=static

cmake -S . -B build
cmake --build build
```

That produces `build/kphasor.dll` and the proxy `build/binkw32.dll`. `BUILDMODE=static` matters: without it, LuaJIT's Windows build only produces `lua51.dll`, not the static archive `kphasor.dll` needs to link against.

On Debian/Ubuntu, the equivalent packages are `g++-multilib`, `g++-mingw-w64-i686`, and `binutils-mingw-w64-i686`; see [`.github/workflows/cmake-multi-platform.yml`](.github/workflows/cmake-multi-platform.yml) for the exact native tooling and Windows cross-compile recipe.

Full build, install, and first-run steps: [`docs/user/install.md`](docs/user/install.md).

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
| KOTOR 1 | Amazon Games, Windows | Unbound — target-native recovery required |
| KOTOR 2 | GOG Aspyr, Windows | Supported |
| KOTOR 2 | Steam Aspyr, Windows | Supported |
| KOTOR 2 | Native Linux (Aspyr) | Unbound — prior cross-placed bindings were withdrawn |
| KOTOR 2 | Retail CD 1.0 / 1.0b, Windows | Unbound — target-native recovery required |

"Supported" means every required hook site resolves and the runtime installs cleanly: the `nwscript.call(name, ...)` routine bridge and event dispatch both work. It does **not** yet mean every corner is verified — K2's struct field layouts (`kp.struct`) were researched against the K1 build only, so typed field access on a K2 build is unverified and may read the wrong offset. Raw `kp.mem.*` reads and writes are unaffected; they don't depend on struct research. Full detail: [`docs/user/api-status.md`](docs/user/api-status.md).

The runtime identifies a build by hashing its code section, never by filename or file size. An executable it doesn't recognize is left completely unpatched — the game runs as if KotorPhasor weren't installed.

## What fires today

These callbacks run in a live game: `OnScriptLoad`, `OnScriptUnload`, `OnTick`, `OnRunScript`, `OnRunScriptDone`, `OnConsoleCommand`, `OnSave`, `OnLoad`, `OnModuleLoad`, `OnModulePlayerEnter`, `OnAreaEnter`, `OnCreatureAttacked`. Every other `EventHandler` name (doors, placeables, triggers, encounters, areas-of-effect, the store, waypoints) is installed and fires when the engine raises that event id.

Two names look like they should work and don't: `OnCreatureHeartbeat` and `OnDialogConditional` never run, because the engine doesn't route those cases through a name a Lua callback could bind to. Filter `OnRunScript` by `script_name` instead — see [`docs/user/scripts.md`](docs/user/scripts.md) for exactly how.

769 of KOTOR 1's 772 engine routines, and 803 of KOTOR 2's 877, are callable through `nwscript.call(name, ...)`. The full status of every name — bound, spec-only, or proven live in a running game — is in [`docs/user/api-status.md`](docs/user/api-status.md). Argument lists (generated from the engine's own signatures, not a status report) are in [`docs/lua-api.md`](docs/lua-api.md) and [`docs/nwscript-api.md`](docs/nwscript-api.md).

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

`AssignCommand`, `DelayCommand`, and `ActionDoCommand` need a script closure NWScript can build and Lua can't. Use `kp.as(object_id, function() ... end)` and `kp.registertimer(ms, "callback_name", data)` instead.

## Multiplayer

A complete, self-contained example — no proxy DLL, no relay server, direct UDP between two game instances using the engine's own socket library — lives at [`scripts/examples/multiplayer/10_avatar_sync.lua`](scripts/examples/multiplayer/10_avatar_sync.lua), with its own standalone test suite at `10_avatar_sync_test.lua`.

## Finding a codecave

If a script needs to inject raw bytes somewhere in the game's code — a small trampoline, a patch stub — `data/codecaves.toml` has thousands of pre-located, individually verified unused-byte spans across every supported build, addressed by `kp.mem.findsig` rather than a hardcoded address so the same script works across builds where the surrounding bytes match. See [`docs/user/codecaves.md`](docs/user/codecaves.md).

## Testing

Two tiers. Neither needs Star Wars IP checked into this repo.

**Tests** (default, offline, no game required): the Lua host, event
arbitration, struct layout, entity API, memory module and hook engine.
Script fixtures live under `scripts/examples/`; generated tables under
`src/generated/`; memory and hook tools probe this process.

```sh
cmake -S . -B build && cmake --build build
ctest --test-dir build --output-on-failure
```

**Real-game smoke test** (opt-in, needs your own Steam KOTOR 1 install and
Wine): `scripts/harness/` runs the game itself under Xvfb, for K1 and K2:

```sh
./scripts/harness/spike_headless_k1.sh
```

See the rest of [`scripts/harness/`](scripts/harness/) for the full set — live sessions, gameplay regression tests, and demo scenes.

`/agentdecompile_projects/` is local scratch for `agentdecompile-cli` (a Ghidra project built from your own game binary). It is gitignored, and that path was removed from `main`'s history. Do not commit it.

Regenerating `data/addresses/*.json` or `src/generated/builds.inc` needs the local reverse-engineering corpus *and* the per-build reference images. Without the images, `tools/gen_address_tables.py` drops `expected_bytes` and can truncate `builds.inc`. Do not commit a regen that was run without those images.

## Uninstall

```sh
./scripts/install_to_game.sh status    /path/to/swkotor
./scripts/install_to_game.sh uninstall /path/to/swkotor
```

Restores the original `binkw32.dll` and removes `kphasor.dll`. Scripts and `kotorphasor.log` are left alone.

## Further reading

- [`docs/user/`](docs/user/) — the whole user-facing doc set, starting from [`docs/user/README.md`](docs/user/README.md)
- [`docs/event-semantics.md`](docs/event-semantics.md) — how the engine actually dispatches events, from recovered source, including which script slots are unreachable through the obvious hook
- [`ATTRIBUTION.md`](ATTRIBUTION.md) — what this project's design is built on, and what's original to it
- [`CHANGELOG.md`](CHANGELOG.md) — what shipped, by version
