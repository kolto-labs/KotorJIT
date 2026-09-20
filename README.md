# KotorPhasor

Drop a `.lua` file in `<game>/kotorphasor/scripts`. It loads once at startup, picks the events it cares about, and can call almost every engine routine. No GFF field. No resref. No slot to claim.

The complete callback, compatibility, and generated routine reference is in [`docs/lua-api-complete.md`](docs/lua-api-complete.md).
The harness-specific Lua surface and startup-loading details are in [`docs/lua-harness-api.md`](docs/lua-harness-api.md).

Native facilities live only under `kp`; direct engine calls use `nwscript.call`.
API version 2 removes the former host root and bare compatibility aliases. See
the [migration reference](docs/api-dialects.md), including `kp.print` and explicit event registration.

NWScript still resolves each event to one script. Two mods that both want that slot have to patch each other or give up. That fight is the usual way KOTOR mods break each other.

```lua
priority = 10

function OnRunScript(script_name, object_id, has_object, relevant)
    if script_name == "k_ambush_spawn" then
        return false  -- stop the game's own script; later Lua still runs
    end
end
```

Every Lua file that registered for that event runs. The first usable return wins. Later scripts still run, with `relevant = false`. Returning `false` from `OnRunScript` also stops the engine's own script. The exact rule is in [`docs/user/scripts.md`](docs/user/scripts.md).

This is the [Phasor](https://github.com/urbanyoung/Phasor) model, rebuilt for KOTOR. What carried over is in [`ATTRIBUTION.md`](ATTRIBUTION.md).

## What you can do

769 of KOTOR 1's 772 routines are callable through `nwscript.call(name, ...)`. No NWScript compiler. No `.nss` file, and no routine names injected into host tables. `AssignCommand`, `DelayCommand`, and `ActionDoCommand` need a closure Lua can't build. Use `kp.as` and `kp.registertimer`.

When the named API does not reach, `kp.mem.readbyte` / `writebyte` / `findsig` talk to the process directly. Hook sites are logical names (`vm.run_script`). A recorded VA is a hint; unique `expected_bytes` bind the site if that hint is missing or stale.

KOTOR already treats a single-player game as a server with one client. A working UDP sync between two game instances ships in [`scripts/examples/multiplayer/`](scripts/examples/multiplayer/). No extra process.

## Build and install

Start to finish: [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Status

KOTOR 1 (Steam and GOG, Windows) and KOTOR 2 (GOG/Steam Aspyr on Windows) install and run scripts today. Other corpus builds remain fail-closed until target-native bindings are recovered. The routine bridge and event dispatch both work. `kp.struct` on K2 is the one piece that is still unverified. The build table is in [`CONTRIBUTING.md`](CONTRIBUTING.md#supported-builds). What fires is in [`docs/user/api-status.md`](docs/user/api-status.md).

## Credits

Other people's work is listed in [`ATTRIBUTION.md`](ATTRIBUTION.md).

Not affiliated with BioWare, Obsidian, LucasArts, Aspyr, or Disney. Ships no game content. Bring your own copy.

## Licence

AGPL-3.0. If you run a modified version as a network service, publish your changes.
