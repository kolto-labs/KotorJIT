"""Per-target facts: what differs between K1, K2 under Wine, and the K2 ELF.

Nothing in here is a path on this machine. A Target names files relative to
the install the discovery step finds, and the session composes them. The
three targets:

  k1         swkotor.exe under Wine. The data tree is the install root; the
             ini and Saves/ sit next to the exe. Build ids come from the
             deciphered Steam image or the GOG image.
  k2-wine    swkotor2.exe under Wine over the steamassets/ data tree. The
             exe is not shipped by the Linux depot; the harness expects one
             to have been placed in the staged tree (see discover.py).
  k2-native  the kotor2 ELF with libhyperstim.so preloaded. The ELF is the
             parent of the data tree. The port writes its ini and saves
             under XDG_DATA_HOME/aspyr-media/<name>/; the name is not
             agreed on by the two public sources, so the session discovers
             it by listing after first launch and falls back to KOTOR2.

Ini keys forced for a headless boot, from the earlier harness and the
prior-art notes: windowed at the Xvfb size so no mode switch is tried,
cheats on so the engine's console path is armed, movies off because the
client loop does not iterate while a movie plays, Frame Buffer=0 because
llvmpipe renders the world black otherwise, VBOs off for the same driver.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# (section, key, value). A key present under another section is set there
# too, because K2 keeps FullScreen and Disable Movies in [Display Options]
# while K1 keeps them in [Graphics Options] and [Game Options].
IniKey = Tuple[str, str, str]

SCREEN_W = 1024
SCREEN_H = 768


def _common_ini(w: int = SCREEN_W, h: int = SCREEN_H) -> List[IniKey]:
    return [
        ("Graphics Options", "FullScreen", "0"),
        ("Graphics Options", "AllowWindowedMode", "1"),
        ("Graphics Options", "Width", str(w)),
        ("Graphics Options", "Height", str(h)),
        ("Graphics Options", "Frame Buffer", "0"),
        ("Graphics Options", "Disable Vertex Buffer Objects", "1"),
        ("Game Options", "EnableCheats", "1"),
        ("Game Options", "Disable Movies", "1"),
        # Headless: every autopause would stall the world timers mid-route.
        ("Autopause Options", "End Of Combat Round", "0"),
        ("Autopause Options", "Enemy Sighted", "0"),
        ("Autopause Options", "Mine Sighted", "0"),
        ("Autopause Options", "Party Killed", "0"),
        ("Autopause Options", "Action Menu", "0"),
        ("Autopause Options", "New Target Selected", "0"),
    ]


@dataclass(frozen=True)
class Target:
    name: str                       # "k1" | "k2-wine" | "k2-native"
    game: str                       # "k1" | "k2": the kpdiscover app id
    platform: str                   # "wine" | "native"
    exe: str                        # file name of the executable
    process_name: str               # what to kill, by name only
    ini_name: str                   # game ini file name
    save_dir_name: str              # save folder name inside the data dir
    start_module: str               # first module of a new game
    image_base: int
    builds: Tuple[str, ...]         # build ids `status` may report
    runtime_files: Tuple[str, ...]  # what to install from build/
    # Directories the game or the runtime writes into. They are real in the
    # staged tree; everything else is a symlink into the install.
    writable_dirs: Tuple[str, ...] = ()
    ini_keys: List[IniKey] = field(default_factory=_common_ini)
    steam_appid: str = ""           # written next to the exe when non-empty
    # k2-native only: where the port keeps its ini and saves, relative to
    # XDG_DATA_HOME. The last element is the fallback folder name.
    xdg_subdir: Tuple[str, ...] = ()

    @property
    def wine(self) -> bool:
        return self.platform == "wine"

    @property
    def exe_in_data_dir(self) -> bool:
        """K2 native keeps the ELF one level above the data tree."""
        return self.name != "k2-native"


K1 = Target(
    name="k1", game="k1", platform="wine",
    exe="swkotor.exe", process_name="swkotor.exe",
    ini_name="swkotor.ini", save_dir_name="Saves",
    start_module="end_m01aa", image_base=0x00400000,
    builds=("k1_steam_103_unpacked", "k1_gog_103"),
    runtime_files=("hyperstim.dll", "binkw32.dll"),
    # futuregame is where the engine's own load path stages a save before the
    # server reads it, so the harness writes there too. A staged tree that
    # symlinks it instead of owning it fails the load with no useful error.
    writable_dirs=("Saves", "hyperstim", "currentgame", "gameinprogress",
                   "futuregame", "Temp", "logs"),
    steam_appid="32370",
)

K2_WINE = Target(
    name="k2-wine", game="k2", platform="wine",
    exe="swkotor2.exe", process_name="swkotor2.exe",
    ini_name="swkotor2.ini", save_dir_name="saves",
    start_module="001EBO", image_base=0x00400000,
    builds=("k2_gog_aspyr", "k2_steam_aspyr"),
    runtime_files=("hyperstim.dll", "binkw32.dll"),
    writable_dirs=("saves", "hyperstim", "currentgame", "gameinprogress",
                   "futuregame", "temp", "logs"),
    steam_appid="208580",
)

K2_NATIVE = Target(
    name="k2-native", game="k2", platform="native",
    exe="kotor2", process_name="kotor2",
    ini_name="swkotor2.ini", save_dir_name="saves",
    start_module="001EBO", image_base=0x08048000,
    builds=("k2_steam_linux",),
    runtime_files=("libhyperstim.so",),
    writable_dirs=("hyperstim",),
    steam_appid="208580",
    xdg_subdir=("aspyr-media", "KOTOR2"),
)

TARGETS: Dict[str, Target] = {t.name: t for t in (K1, K2_WINE, K2_NATIVE)}


def get(name: str) -> Target:
    key = name.strip().lower()
    if key == "k2":
        key = "k2-native"
    if key not in TARGETS:
        raise KeyError(f"unknown target {name!r}; one of {', '.join(TARGETS)}")
    return TARGETS[key]


def names() -> List[str]:
    return list(TARGETS)
