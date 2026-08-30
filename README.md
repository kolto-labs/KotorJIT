# KotorPhasor

Lua scripts for Star Wars: Knights of the Old Republic.

The runtime loads with the game, embeds LuaJIT, and hands the engine's own script events to your `.lua` files. You can watch an event, change it, or stop it. Files reload without restarting the game.

**0.1.0** supports KOTOR 1 on Steam (Windows). See [docs/user/](docs/user/) for install, scripting, and what is live.

```lua
priority = 10

function OnRunScript(script_name, object_id, has_object, relevant)
    if script_name == "k_ambush_spawn" then
        return false
    end
end
```

769 of the game's 772 engine routines are `kotor.GetFirstPC()`, `kotor.AdjustAlignment(...)`, and so on. `AssignCommand`, `DelayCommand`, and `ActionDoCommand` are not bound. Use `kp.as` and `kotor.registertimer` instead.

## Supported games

| Game | Build | 0.1.0 |
|---|---|---|
| KOTOR 1 | Steam, Windows | Supported |
| KOTOR 2 | Steam, native Linux | Not yet |

The runtime identifies the executable by hash. An unknown build is left unpatched. The Steam KOTOR 1 image is encrypted on disk; KotorPhasor waits for it to decipher, then checks it. Details: [docs/steam-gog-equivalence.md](docs/steam-gog-equivalence.md).

## Install

Build (32-bit Windows cross-compiler and LuaJIT):

```sh
sudo dnf install mingw32-gcc-c++ mingw32-binutils glibc-devel.i686 libstdc++-devel.i686

git clone --branch v2.1 https://github.com/LuaJIT/LuaJIT third_party/luajit
make -C third_party/luajit HOST_CC="gcc -m32" CROSS=i686-w64-mingw32- TARGET_SYS=Windows

cmake -S . -B build && cmake --build build
./scripts/install_to_game.sh install /path/to/swkotor
```

Scripts go in `<game>/kotorphasor/scripts`. The log is `<game>/kotorphasor.log`. In the cheat console: `lua exec`, `lua status`, `lua reload`.

Full steps: [docs/user/install.md](docs/user/install.md).

## What works

These callbacks fire in a running 0.1.0 game: `OnScriptLoad`, `OnTick`, `OnRunScript`, `OnConsoleCommand`, `OnSave`, `OnLoad`, `OnModuleLoad`, `OnModulePlayerEnter`, `OnAreaEnter`, `OnCreatureAttacked`. Other EventHandler names (doors, placeables, triggers, …) are installed and fire when the engine raises that id.

Do not use `OnCreatureHeartbeat` or `OnDialogConditional` as function names. They never run. Filter `OnRunScript` by `script_name` instead.

The full list, with a status on each name: [docs/user/api-status.md](docs/user/api-status.md). How to write a script: [docs/user/scripts.md](docs/user/scripts.md).

Argument catalogs (generated, not status): [docs/lua-api.md](docs/lua-api.md), [docs/nwscript-api.md](docs/nwscript-api.md).

## Testing without a screen

`scripts/harness/` runs the game under Xvfb and Wine:

```sh
./scripts/harness/spike_headless_k1.sh
```

## Credits

Built on other people's work. See [ATTRIBUTION.md](ATTRIBUTION.md).

Not affiliated with BioWare, Obsidian, LucasArts, Aspyr, or Disney. Ships no game content. Bring your own copy of the game.

## Licence

AGPL-3.0. If you run a modified version as a network service, publish your changes.
