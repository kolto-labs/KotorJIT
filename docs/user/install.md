# Install KotorPhasor

You need a legal copy of KOTOR 1 (Steam, Windows). Build the runtime first, or use the `kphasor.dll` and proxy `binkw32.dll` from a release.

## Build

You need a 32-bit Windows cross-compiler and LuaJIT built for that target.

```sh
sudo dnf install mingw32-gcc-c++ mingw32-binutils glibc-devel.i686 libstdc++-devel.i686

git clone --branch v2.1 https://github.com/LuaJIT/LuaJIT third_party/luajit
make -C third_party/luajit HOST_CC="gcc -m32" CROSS=i686-w64-mingw32- TARGET_SYS=Windows

cmake -S . -B build
cmake --build build
```

That produces `build/kphasor.dll` and the proxy `build/binkw32.dll`.

## Put it in the game folder

```sh
./scripts/install_to_game.sh install /path/to/swkotor
```

The installer:

1. Copies the original `binkw32.dll` to `binkw32_real.dll`
2. Drops the proxy in as `binkw32.dll`
3. Copies `kphasor.dll` next to the game
4. Copies address tables into `kotorphasor/addresses/`
5. Creates `kotorphasor/scripts/`

Nothing else in the game folder is rewritten.

```sh
./scripts/install_to_game.sh status    /path/to/swkotor
./scripts/install_to_game.sh uninstall /path/to/swkotor
```

Uninstall restores the original `binkw32.dll` and removes `kphasor.dll`. Scripts and `kotorphasor.log` stay.

## Optional config

Create `kotorphasor.ini` next to the executable if you want to change defaults.

```ini
script_dir = kotorphasor/scripts
log_path = kotorphasor.log
error_budget = 8
hot_reload = true
```

Paths are relative to the game directory. `error_budget` is how many errors a script may raise before it is unloaded. `hot_reload` re-reads changed `.lua` files about once a second.

## First check

1. Start the game and load a save.
2. Open `kotorphasor.log` and look for `KotorPhasor 0.1.0 starting` and `installed 15 hooks`.
3. In the cheat console type `lua status`. The same facts appear in the log.
4. Drop a `.lua` file in `kotorphasor/scripts/` and type `lua reload`, or wait for hot reload.

Enable the cheat console the same way you always do for this game (in-game cheats). The runtime does not turn cheats on for you.
