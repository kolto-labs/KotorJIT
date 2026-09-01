# KotorPhasor

A Lua scripting engine for Star Wars: Knights of the Old Republic that replaces NWScript's event model instead of extending it.

## The problem with NWScript

Every event in KOTOR — a heartbeat, a door opening, a module loading — resolves to exactly one script, named in a GFF field, picked by a resource-resolution order you hope goes your way. Two mods that both want to react to the same event have to fight over that one slot, patch each other's files, or give up. This is why script conflicts are the most common reason KOTOR mods break each other.

## The alternative

Drop a `.lua` file into a scripts folder. It runs once at startup and decides for itself which events it cares about — no GFF field, no resref, no slot to claim.

```lua
priority = 10

function OnRunScript(script_name, object_id, has_object, relevant)
    if script_name == "k_ambush_spawn" then
        return false  -- block this one ambush, leave everything else alone
    end
end
```

As many scripts as you want can watch the same event. Every one of them runs; the first decisive answer wins, and every later script is told so (`relevant = false`) rather than being skipped. Nobody has to know the others exist. See [`docs/user/scripts.md`](docs/user/scripts.md) for the exact rule.

This model isn't new — it's the same one [Phasor](https://github.com/urbanyoung/Phasor) used for Halo: Combat Evolved servers. KotorPhasor is that idea rebuilt for KOTOR's engine. See [`ATTRIBUTION.md`](ATTRIBUTION.md) for the specifics of what carried over.

## What you get past the scripting model

- **The engine, not a subset of it.** 769 of KOTOR 1's 772 routines are callable directly as `kotor.GetFirstPC()`, `kotor.AdjustAlignment(...)`, and so on — no NWScript compiler, no `.nss` file. The three that aren't (`AssignCommand`, `DelayCommand`, `ActionDoCommand`) need a script closure NWScript can build and Lua can't; `kp.as` and `kotor.registertimer` cover the same ground.
- **Raw memory, when the API doesn't reach far enough.** `kotor.mem.readbyte`/`writebyte`/`findsig` and friends read and write the game's own memory directly. A blaster that fires speeders instead of bolts, a minimap that pings a webserver on every player move — the API surface doesn't have to have a name for your idea already.
- **Multiplayer as a first-class idea, not an afterthought.** KOTOR's engine already treats a single-player game as a server with one connected client; KotorPhasor's event model was built around that fact from the start. A real, working example — direct UDP sync between two game instances with no external server, no extra process, just a Lua script and the engine's own socket library — ships in [`scripts/examples/multiplayer/`](scripts/examples/multiplayer/).

## Try it

Build, install, and scripting instructions, start to finish: **[USAGE.md](USAGE.md)**.

## Status

KOTOR 1 (Steam and GOG, Windows) and KOTOR 2 (native Linux, and GOG/Steam Aspyr on Windows) install cleanly and run scripts today, including the full routine bridge and event dispatch. K2's typed struct access (`kotor.struct`) is the one piece not yet verified — see [USAGE.md](USAGE.md#supported-builds) for the exact list and [`docs/user/api-status.md`](docs/user/api-status.md) for what fires.

## Credits

Built on other people's work — see [`ATTRIBUTION.md`](ATTRIBUTION.md).

Not affiliated with BioWare, Obsidian, LucasArts, Aspyr, or Disney. Ships no game content. Bring your own copy of the game.

## Licence

AGPL-3.0. If you run a modified version as a network service, publish your changes.
