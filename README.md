# KotorPhasor

A Lua scripting runtime for Star Wars: Knights of the Old Republic.

KotorPhasor loads into the running game, embeds LuaJIT, and hands the engine's own script
events to Lua. Scripts define only the callbacks they care about. They can watch an event,
change what it does, or stop it happening. They reload without restarting the game.

> Early development. Nothing here is ready to use yet.

## What it does

The game runs everything through NWScript — every heartbeat, every death, every conversation
line. Modding that today means editing script source, compiling bytecode, and shipping
override files. You cannot watch an event, and you cannot stop one.

KotorPhasor puts Lua in that path:

```lua
-- scripts/no_ambush.lua
priority = 10

function OnScriptEvent(script, object)
    if script == "k_ambush_spawn" then
        return false        -- the ambush does not happen
    end
end
```

Every one of the game's 772 engine routines is callable from Lua, so a script can do anything
NWScript can.

## How several scripts share an event

Every loaded script that defines the callback is called, in priority order. The first one to
return a usable value decides the outcome; the rest still run, and are told their answer will
not be used. A script that returns nothing is abstaining, not voting.

Priority is a number a script declares. Scripts that do not declare one are ordered by
filename, so the outcome never depends on load order by accident.

## Supported games

| game | build | status |
|---|---|---|
| KOTOR 1 | Steam, Windows | primary target |
| KOTOR 2 | Steam, native Linux | in progress |

Addresses live in `data/addresses/`, generated per build and keyed by executable hash.
KotorPhasor identifies the build at load time and refuses to run against one it does not
recognise, rather than patching the wrong bytes.

The Steam KOTOR 1 executable is encrypted on disk. KotorPhasor waits for it to decipher in
memory, re-reads the image, and checks it before touching anything — see
[docs/steam-gog-equivalence.md](docs/steam-gog-equivalence.md).

## Building

You need a 32-bit Windows cross-compiler and LuaJIT built for the same target.

```sh
sudo dnf install mingw32-gcc-c++ mingw32-binutils glibc-devel.i686 libstdc++-devel.i686

git clone --branch v2.1 https://github.com/LuaJIT/LuaJIT third_party/luajit
make -C third_party/luajit HOST_CC="gcc -m32" CROSS=i686-w64-mingw32- TARGET_SYS=Windows
```

## Testing without a screen

`scripts/harness/` runs the game under Xvfb and Wine and drives it with a virtual keyboard
and mouse, so changes can be checked on a machine with no display:

```sh
./scripts/harness/spike_headless_k1.sh
```

## Credits

Built on other people's work — see [ATTRIBUTION.md](ATTRIBUTION.md).

Not affiliated with BioWare, Obsidian, LucasArts, Aspyr, or Disney. Ships no game content.
Bring your own copy of the game.

## Licence

AGPL-3.0. If you run a modified version as a network service, publish your changes.
