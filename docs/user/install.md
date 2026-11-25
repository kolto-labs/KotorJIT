# Install KotorJIT

You need a legal copy of the game. See [CONTRIBUTING.md](../../CONTRIBUTING.md#supported-builds) in the repo root for which KOTOR 1 and KOTOR 2 builds are supported today. Build the runtime first, or use the `kotorjit.dll` and proxy `binkw32.dll` from a release.

## Build

You need a 32-bit Windows cross-compiler and LuaJIT built for that target.

```sh
sudo dnf install mingw32-gcc-c++ mingw32-binutils glibc-devel.i686 libstdc++-devel.i686 luajit lua

git clone --branch v2.1 https://github.com/LuaJIT/LuaJIT third_party/luajit
make -C third_party/luajit HOST_CC="gcc -m32" CROSS=i686-w64-mingw32- TARGET_SYS=Windows BUILDMODE=static

cmake -S . -B build
cmake --build build
```

That produces `build/kotorjit.dll`, `build/binkw32.dll` (optional proxy), `build/kotorjit-launch.exe` (Windows runtime-injection launcher), and `build/libkotorjit.so`.

Or package those artifacts (plus address tables, `Install-KotorJIT.ps1`, and `tools/elf_needed.py`) into a release zip, or build a [KotOR Patch Manager](https://github.com/LaneDibello/kotor-patch-manager) `.kpatch`:

```sh
./scripts/package_release.sh build
# -> dist/kotorjit-0.1.0.zip  (sha256 printed; tools/check_release_zip.py validates members)

python3 scripts/package_kpatch.py build
# -> dist/kotorjit.kpatch     (KPM DLL-only archive with embedded address tables)
```

Unpack the zip and install from its directory as the build dir:

```sh
./install_to_game.sh install /path/to/swkotor .
```

## Put it in the game folder

```sh
# Auto-selects proxy on Windows EXEs, or PT_NOTE DT_NEEDED link (falling back to preload) on Linux ELF32
./scripts/install_to_game.sh install /path/to/swkotor

# Or choose an explicit deployment method:
./scripts/install_to_game.sh --method proxy   install /path/to/game   # Windows / Wine / Proton / packed Steam K1
./scripts/install_to_game.sh --method inject  install /path/to/game   # Native Windows via kotorjit-launch.exe (leaves binkw32.dll untouched)
./scripts/install_to_game.sh --method linked  install /path/to/k2     # Native Linux ELF32 DT_NEEDED via tools/elf_needed.py
./scripts/install_to_game.sh --method preload install /path/to/k2     # Native Linux LD_PRELOAD wrapper (run-kotorjit.sh)
```

- **`proxy`** (required under Proton/Wine; recommended for packed Steam K1): backs up original `binkw32.dll` to `binkw32_real.dll`, drops the proxy `binkw32.dll`, copies `kotorjit.dll`, and stages `kotorjit/addresses/` and `kotorjit/scripts/`.
- **`inject`** (native Windows): leaves `binkw32.dll` untouched and installs `kotorjit.dll` + `kotorjit-launch.exe` (launches GOG/unpacked builds suspended and injects before startup, or attaches after unpack for SteamStub builds).
- **`linked`** (native Linux ELF32): repurposes `PT_NOTE` into a read-write `PT_LOAD` and adds `DT_NEEDED $ORIGIN/libkotorjit.so` without moving `.text` virtual addresses or bytes (`tools/elf_needed.py`), keeping a backup in `kotorjit/backup/`.
- **`preload`** (native Linux ELF32 fallback): copies `libkotorjit.so` and generates `run-kotorjit.sh` using `LD_PRELOAD`.

```sh
./scripts/install_to_game.sh status    /path/to/swkotor
./scripts/install_to_game.sh uninstall /path/to/swkotor
```

Uninstall reverses whichever method was installed (restoring `binkw32.dll` or the backed-up Linux ELF and removing deployed binaries). Scripts and `kotorjit.log` stay. KotorJIT requires exact expected bytes at every hook site and refuses cleanly if another code patch has modified those bytes.

## Optional config

Create `kotorjit.ini` next to the executable if you want to change defaults.

```ini
script_dir = kotorjit/scripts
log_path = kotorjit.log
error_budget = 8
hot_reload = true
```

Paths are relative to the game directory. `error_budget` is how many errors a script may raise before it is unloaded. `hot_reload` re-reads changed `.lua` files about once a second.

## First check

1. Start the game and load a save.
2. Open `kotorjit.log` and look for `KotorJIT 0.1.0 starting` and `installed 15 hooks`.
3. In the cheat console type `lua status`. The same facts appear in the log.
4. Drop a `.lua` file in `kotorjit/scripts/` and type `lua reload`, or wait for hot reload.

Enable the cheat console the same way you always do for this game (in-game cheats). The runtime does not turn cheats on for you.
