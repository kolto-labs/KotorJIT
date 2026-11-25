#!/usr/bin/env python3
"""Find installed software on this machine instead of assuming where it is.

Nothing here is specific to any application. It knows how to read Steam's
library list, walk per-platform install roots and the Windows registry, and test
a directory against content rules -- and the rules themselves live in
data/app_signatures.toml. Teaching it about another program is an entry in that
file, not a change here, which is what lets this module be lifted into an
unrelated project unchanged.

Hardcoding a path means the project only works on the machine it was written on,
so nothing else in this repo may contain an absolute path to anything. This
module is the single place that knows how to look.

Search order, most specific first, so an explicit answer always wins:

  1. an explicit argument
  2. an environment variable (KOTOR1_DIR, KOTOR2_DIR, KOTORXID_DB, ...)
  3. kotorphasor.toml, looked for from the current directory upward
  4. Steam's own library list, which is the only reliable way to find installs
     on a second drive
  5. per-platform default locations
  6. the Windows registry

Discovery is by CONTENT, never by directory name: a directory is the thing you
want because it contains the marker files the rules name, not because it is
called the right thing. People rename directories, and vendors use different
names per platform and per storefront.

Usage as a CLI:
    ./kpdiscover.py                  # report everything found
    ./kpdiscover.py --app k1         # print one path, exit 1 if not found
    ./kpdiscover.py --list-apps      # what this signature file knows about
"""
from __future__ import annotations

import os
import platform
import re
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    tomllib = None

CONFIG_NAME = "kotorphasor.toml"
CONFIG_NAMES = ("kotorjit.toml", "kotorphasor.toml")

# Nothing below knows what application it is looking for. Recognition rules and
# search roots come from data/app_signatures.toml, so supporting another program
# is an entry in that file rather than a change here.
SIGNATURES_FILE = "app_signatures.toml"


def _load_signatures() -> dict:
    if tomllib is None:
        return {}
    for base in (Path(__file__).resolve().parent.parent / "data",
                 Path.cwd() / "data", Path.cwd()):
        p = base / SIGNATURES_FILE
        if p.is_file():
            try:
                return tomllib.loads(p.read_text())
            except Exception:
                return {}
    return {}


_SIGS = _load_signatures()


def known_apps() -> list[str]:
    return sorted((_SIGS.get("app") or {}).keys())


def read_workspace_config() -> dict:
    """Nearest cwd/ancestor config, then checkout root; never merge files.

    Paths in the selected file are relative to that file. Malformed selected
    files fail explicitly instead of silently discovering a different install.
    """
    here = Path.cwd().resolve()
    for d in dict.fromkeys([here, *here.parents, Path(__file__).resolve().parent.parent]):
        for cfg_name in CONFIG_NAMES:
            p = d / cfg_name
            if not p.is_file():
                continue
            if tomllib is None:
                raise ValueError(f"{p}: Python 3.11+ is required")
            try:
                config = tomllib.loads(p.read_text())
                for section in ("paths", "harness"):
                    table = config.get(section, {})
                    if not isinstance(table, dict):
                        raise ValueError(f"{section} must be a table")
                    for key, value in table.items():
                        if section == "harness" and key not in ("build_dir", "k2_exe", "libglu_dir"):
                            raise ValueError(f"unknown harness setting {key!r}")
                        if not isinstance(value, str) or not value.strip():
                            raise ValueError(f"{section}.{key} must be a non-empty path string")
                        path = Path(value).expanduser()
                        table[key] = str(path if path.is_absolute() else (p.parent / path).resolve())
                return config
            except (OSError, ValueError) as e:
                raise ValueError(f"{p}: {e}") from e
    return {}


def _steam_roots() -> list[Path]:
    """Every Steam installation root we can find, before reading its libraries."""
    home = Path.home()
    cands = [
        home / ".steam" / "steam",
        home / ".steam" / "root",
        home / ".local" / "share" / "Steam",
        home / ".steam" / "debian-installation",
        home / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",
        home / "Library" / "Application Support" / "Steam",
        Path("C:/Program Files (x86)/Steam"),
        Path("C:/Program Files/Steam"),
    ]
    if os.name == "nt":
        try:
            import winreg
            for hive, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                              (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Valve\Steam")):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        val, _ = winreg.QueryValueEx(k, "SteamPath")
                        cands.append(Path(val))
                except OSError:
                    pass
        except ImportError:
            pass
    return [c for c in cands if c.is_dir()]


def _steam_libraries() -> list[Path]:
    """Every steamapps/common, including libraries on other drives.

    This is the step the usual default-path lists skip, and it is the one that
    matters: an install on a second disk appears nowhere in a table of standard
    locations, but Steam always records it here.
    """
    libs: list[Path] = []
    for root in _steam_roots():
        for common in (root / "steamapps" / "common",):
            if common.is_dir():
                libs.append(common)
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if not vdf.is_file():
            continue
        try:
            text = vdf.read_text(errors="replace")
        except OSError:
            continue
        # Both the old flat form and the newer nested form quote the path.
        for m in re.finditer(r'"path"\s*"([^"]+)"', text):
            p = Path(m.group(1).replace("\\\\", "/").replace("\\", "/")) / "steamapps" / "common"
            if p.is_dir():
                libs.append(p)
        for m in re.finditer(r'"\d+"\s*"([A-Za-z]:[^"]+|/[^"]+)"', text):
            p = Path(m.group(1).replace("\\\\", "/").replace("\\", "/")) / "steamapps" / "common"
            if p.is_dir():
                libs.append(p)
    seen, out = set(), []
    for p in libs:
        r = p.resolve()
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def _default_dirs() -> list[Path]:
    """Non-Steam install locations for this platform, from the signature file."""
    templates = (_SIGS.get("roots") or {}).get(platform.system(), [])
    out: list[Path] = []
    for t in templates:
        if "{drive}" in t:
            for drive in ("C:", "D:", "E:", "F:"):
                out.append(Path(t.replace("{drive}", drive)).expanduser())
        else:
            out.append(Path(t).expanduser())
    return [d for d in out if d.is_dir()]


def _looks_like(d: Path, app: str) -> bool:
    """Does this directory satisfy `app`'s content rules?

    Filenames are compared case-insensitively because the same install can be
    lowercase on one platform and mixed-case on another.
    """
    rules = (_SIGS.get("app") or {}).get(app)
    if not rules or not d.is_dir():
        return False
    try:
        names = {e.name.lower() for e in d.iterdir()}
    except OSError:
        return False
    if not all(r.lower() in names for r in rules.get("requires", [])):
        return False
    any_of = [a.lower() for a in rules.get("any_of", [])]
    if any_of and not any(a in names for a in any_of):
        return False
    if any(x.lower() in names for x in rules.get("excludes", [])):
        return False
    return True


def _candidate_dirs() -> list[Path]:
    """Directories worth testing, one level under each search root."""
    out: list[Path] = []
    for base in _steam_libraries() + _default_dirs():
        out.append(base)
        try:
            for child in base.iterdir():
                if child.is_dir():
                    out.append(child)
                    # Some layouts keep the data one level deeper again.
                    for sub in (_SIGS.get("nested") or {}).get("subdirs", []):
                        p = child / sub
                        if p.is_dir():
                            out.append(p)
        except OSError:
            continue
    return out


def find_app(app: str, explicit: str | None = None) -> Path | None:
    """Locate an installed application by its id in app_signatures.toml."""
    game = app.lower()
    if explicit:
        p = Path(explicit).expanduser()
        return p if _looks_like(p, game) else None

    env = os.environ.get(f"KOTOR{game[-1]}_DIR") or os.environ.get(f"{game.upper()}_DIR")
    if env:
        p = Path(env).expanduser()
        if _looks_like(p, game):
            return p

    cfg = read_workspace_config().get("paths", {}).get(game)
    if cfg:
        p = Path(cfg).expanduser()
        if _looks_like(p, game):
            return p

    for d in _candidate_dirs():
        if _looks_like(d, game):
            return d.resolve()
    return None


def find_all_apps(app: str) -> list[Path]:
    """Every install found, not just the first. Useful for testing across builds."""
    game = app.lower()
    found, seen = [], set()
    for d in _candidate_dirs():
        if _looks_like(d, game):
            r = d.resolve()
            if r not in seen:
                seen.add(r)
                found.append(r)
    return found


# Names the rest of this project uses. Thin aliases, so callers read naturally
# while the module underneath stays application-agnostic.
find_game = find_app
find_all_games = find_all_apps


def find_corpus(explicit: str | None = None) -> Path | None:
    """The reverse-engineering database the generators read.

    Only the generators need this, and only when regenerating. A checkout with
    the generated tables committed builds and runs without it.
    """
    if explicit:
        p = Path(explicit).expanduser()
        return p if p.is_file() else None
    env = os.environ.get("KOTORXID_DB")
    if env and Path(env).expanduser().is_file():
        return Path(env).expanduser()
    cfg = read_workspace_config().get("paths", {}).get("corpus")
    if cfg and Path(cfg).expanduser().is_file():
        return Path(cfg).expanduser()

    home = Path.home()
    for base in (home, home / "src", home / "Projects", Path.cwd(), *Path.cwd().parents):
        for rel in ("biodecompwarehouse/kotorxid/db/kotorxid.sqlite",
                    "kotorxid/db/kotorxid.sqlite",
                    "db/kotorxid.sqlite"):
            p = base / rel
            if p.is_file():
                return p.resolve()
    return None


def find_data_file(*relatives: str, env: str | None = None) -> Path | None:
    """A supporting data file (an nwscript.nss, an unpacked image) by relative path."""
    if env:
        v = os.environ.get(env)
        if v and Path(v).expanduser().exists():
            return Path(v).expanduser()
    home = Path.home()
    roots = [Path.cwd(), *Path.cwd().parents, home, home / "src", home / "Projects"]
    for base in roots:
        for rel in relatives:
            p = base / rel
            if p.exists():
                return p.resolve()
    return None


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--app", metavar="ID", help="application id from app_signatures.toml")
    ap.add_argument("--list-apps", action="store_true")
    # Conveniences for this project's two applications; --app is the general form.
    ap.add_argument("--k1", action="store_true", help="shorthand for --app k1")
    ap.add_argument("--k2", action="store_true", help="shorthand for --app k2")
    ap.add_argument("--corpus", action="store_true")
    ap.add_argument("--all", action="store_true", help="every install, not just the first")
    args = ap.parse_args()

    if args.list_apps:
        for a in known_apps():
            print(f"{a}\t{(_SIGS['app'][a]).get('name', '')}")
        return 0

    if args.app or args.k1 or args.k2:
        g = args.app or ("k1" if args.k1 else "k2")
        if args.all:
            hits = find_all_apps(g)
            for h in hits:
                print(h)
            return 0 if hits else 1
        p = find_app(g)
        if p:
            print(p)
            return 0
        return 1
    if args.corpus:
        p = find_corpus()
        if p:
            print(p)
            return 0
        return 1

    print(f"platform      : {platform.system()}")
    print(f"config        : {CONFIG_NAME} " +
          ("found" if read_workspace_config() else "not found (optional)"))
    libs = _steam_libraries()
    print(f"steam libraries: {len(libs)}")
    for l in libs:
        print(f"  {l}")
    for g in known_apps():
        hits = find_all_apps(g)
        print(f"{g.upper()}: {len(hits)} install(s)")
        for h in hits:
            print(f"  {h}")
    c = find_corpus()
    print(f"corpus        : {c or 'not found (only needed to regenerate tables)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
