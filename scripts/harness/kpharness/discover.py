"""Find things by content, never by a path written down.

Thin wrapper over tools/kpdiscover.py, imported by file path so this package
needs no install step and the discovery rules stay in one place. On top of
it: the repository root (from this file's location), the build directory, the
Wine and native executables for a target, and the optional kotorphasor.toml
[harness] table for the few knobs a machine may need (a K2 Windows exe the
depot does not ship, a 32-bit libGLU directory for the ELF).

Search order for every answer is explicit argument, environment variable,
kotorphasor.toml, then discovery. That mirrors kpdiscover so a person who
learned one learns both.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import targets as T


def repo_root() -> Path:
    """scripts/harness/kpharness/discover.py -> the repository."""
    selected = os.environ.get("KP_GAMESCOPE_REPO_ROOT")
    return Path(selected).resolve() if selected else Path(__file__).resolve().parents[3]


def _load_kpdiscover():
    path = repo_root() / "tools" / "kpdiscover.py"
    spec = importlib.util.spec_from_file_location("kpdiscover", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("kpdiscover", mod)
    spec.loader.exec_module(mod)
    return mod


_KPD = None


def kpdiscover():
    global _KPD
    if _KPD is None:
        _KPD = _load_kpdiscover()
    return _KPD


def harness_config() -> Dict[str, Any]:
    """Use the same selected file and relative paths as install discovery."""
    return kpdiscover().read_workspace_config().get("harness", {})


def build_dir(explicit: Optional[str] = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("KP_BUILD_DIR")
    if env:
        return Path(env).expanduser().resolve()
    cfg = harness_config().get("build_dir")
    if cfg:
        return Path(str(cfg)).expanduser().resolve()
    return repo_root() / "build"


def data_dir(target: T.Target, explicit: Optional[str] = None) -> Path:
    """The directory holding chitin.key for this target's game.

    For K2 that is steamassets/ (kpdiscover recognises it by content), for
    K1 the install root. `explicit` and KOTOR1_DIR / KOTOR2_DIR are honoured
    by kpdiscover itself.
    """
    found = kpdiscover().find_app(target.game, explicit)
    if found is None:
        raise FileNotFoundError(
            f"no {target.game.upper()} install found: set KOTOR{target.game[-1]}_DIR "
            f"or add [paths] {target.game} = \"...\" to kotorjit.toml (or kotorphasor.toml)")
    return Path(found).resolve()


def install_root(target: T.Target, data: Path) -> Path:
    """Where the executable lives: the data dir, or its parent for the ELF."""
    if target.exe_in_data_dir:
        return data
    return data.parent


def executable(target: T.Target, data: Path) -> Optional[Path]:
    """The game executable for this target if one is present.

    K2 under Wine needs swkotor2.exe, which the Linux depot does not ship.
    KP_K2_EXE or [harness] k2_exe names one; otherwise a file already placed
    in the data dir or the install root counts.
    """
    root = install_root(target, data)
    if target.name == "k2-wine":
        for cand in (os.environ.get("KP_K2_EXE"), harness_config().get("k2_exe")):
            if cand and Path(str(cand)).expanduser().is_file():
                return Path(str(cand)).expanduser().resolve()
    for d in (root, data):
        p = d / target.exe
        if p.is_file():
            return p
    return None


def _has_libglu(p: Path) -> bool:
    """True when p/libGLU.so.1 resolves to a real file.

    Some Steam runtime trees (seen on this machine under
    SteamLinuxRuntime_sniper, SteamLinuxRuntime_soldier and umu's steamrt3)
    ship only the versioned library (libGLU.so.1.3.x) with no un-versioned
    SONAME symlink. That does not satisfy the ELF's DT_NEEDED entry for
    "libGLU.so.1", so a directory only counts once the exact name is present
    -- is_file() follows the symlink, so this also rejects a dangling one.
    """
    try:
        return (p / "libGLU.so.1").is_file()
    except OSError:
        return False


def libglu_dirs() -> List[Path]:
    """Candidate directories holding a working 32-bit libGLU.so.1 for the K2 ELF.

    The distro may not ship it; Steam's Linux runtime does. KP_LIBGLU_DIR
    and [harness] libglu_dir come first, but they are held to the same bar
    as everything discovered below: no point preferring an override that
    turns out not to resolve.
    """
    out: List[Path] = []
    for cand in (os.environ.get("KP_LIBGLU_DIR"), harness_config().get("libglu_dir")):
        if cand:
            p = Path(str(cand)).expanduser()
            if _has_libglu(p):
                out.append(p)

    roots = list(kpdiscover()._steam_roots())
    umu = Path.home() / ".local" / "share" / "umu"
    if umu.is_dir():
        roots.append(umu)

    # Fixed relative paths for runtime layouts that keep a stable directory
    # name across versions.
    fixed_rels = (
        "steamapps/common/SteamLinuxRuntime/steam-runtime/usr/lib/i386-linux-gnu",
        "ubuntu12_32/steam-runtime/usr/lib/i386-linux-gnu",
        "ubuntu12_32/steam-runtime/lib/i386-linux-gnu",
    )
    # Glob patterns for layouts that version-stamp an inner directory (sniper
    # and soldier runtimes, and umu's steamrt3 cache) so a new platform
    # release is still found without editing this list.
    glob_pats = (
        "steamapps/common/SteamLinuxRuntime_sniper/*/files/lib/i386-linux-gnu",
        "steamapps/common/SteamLinuxRuntime_soldier/*/files/lib/i386-linux-gnu",
        "steamrt3/*/files/lib/i386-linux-gnu",
    )
    for root in roots:
        for rel in fixed_rels:
            p = root / rel
            if _has_libglu(p):
                out.append(p)
        for pat in glob_pats:
            for p in sorted(root.glob(pat)):
                if _has_libglu(p):
                    out.append(p)

    seen, uniq = set(), []
    for p in out:
        r = p.resolve()
        if r not in seen:
            seen.add(r)
            uniq.append(r)
    return uniq


def xdg_game_dir(xdg_home: Path, target: T.Target) -> Path:
    """The port's own folder under XDG_DATA_HOME, found by listing.

    Two public sources disagree on the folder name, so the driver lists
    `aspyr-media/` and takes the entry that mentions the game rather than
    trusting either. Before first launch nothing exists; the fallback name
    is created so the ini can be written ahead of the run.
    """
    parent = xdg_home
    for part in target.xdg_subdir[:-1]:
        parent = parent / part
    fallback = parent / target.xdg_subdir[-1]
    if parent.is_dir():
        for entry in sorted(parent.iterdir()):
            if entry.is_dir() and ("kotor2" in entry.name.lower()
                                   or "republic ii" in entry.name.lower()):
                return entry
    return fallback


def describe(target: T.Target) -> Dict[str, Any]:
    """What the CLI prints for `kpharness status` before a boot."""
    out: Dict[str, Any] = {"target": target.name, "build_dir": str(build_dir())}
    try:
        data = data_dir(target)
        out["data_dir"] = str(data)
        out["install_root"] = str(install_root(target, data))
        exe = executable(target, data)
        out["executable"] = str(exe) if exe else None
    except FileNotFoundError as e:
        out["error"] = str(e)
    if target.name == "k2-native":
        out["libglu_dirs"] = [str(p) for p in libglu_dirs()]
    return out
