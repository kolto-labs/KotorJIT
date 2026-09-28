"""Checkpoints: named save folders, in and out of the game's save directory.

A module load under llvmpipe costs tens of seconds, so a scenario that
needs a plot point loads a checkpoint instead of replaying the chain that
led there. A checkpoint is a copy of one save folder (SAVEGAME.sav,
PARTYTABLE.res, GLOBALVARS.res, savenfo.res and whatever else the engine
wrote) kept under tmp/checkpoints/<target>/<name>/ together with a
meta.json that records the folder name the engine knows it by.

Loading is the engine's own path: the folder is copied back under its
original name and `load_save` is issued; the caller then waits for phase
gameplay through the same watchdog as any other wait.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import discover, targets as T
from .client import Channel
from .oracle import Watchdog
from .waits import phase_is, wait_until

META = "meta.json"


class CheckpointError(Exception):
    pass


class Checkpoints:
    def __init__(self, target: T.Target, save_dir: Path, root: Optional[Path] = None):
        self.target = target
        self.save_dir = Path(save_dir)
        self.root = Path(root) if root else discover.repo_root() / "tmp" / "checkpoints" / target.name
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, name: str) -> Path:
        if "/" in name or name in (".", ".."):
            raise CheckpointError(f"bad checkpoint name {name!r}")
        return self.root / name

    def names(self) -> List[str]:
        return sorted(p.name for p in self.root.iterdir() if (p / META).is_file())

    def meta(self, name: str) -> Dict[str, Any]:
        p = self.path(name) / META
        if not p.is_file():
            raise CheckpointError(f"no checkpoint {name!r} under {self.root}")
        return json.loads(p.read_text())

    # -------------------------------------------------------------- copy --
    def save_folders(self) -> List[str]:
        return sorted(p.name for p in self.save_dir.iterdir()
                      if p.is_dir() and (p / "SAVEGAME.sav").is_file()
                      or p.is_dir() and (p / "savegame.sav").is_file())

    def store(self, name: str, folder: str, extra: Optional[Dict[str, Any]] = None) -> Path:
        """Copy save folder `folder` out of the save dir as checkpoint `name`."""
        src = self.save_dir / folder
        if not src.is_dir():
            raise CheckpointError(f"no save folder {folder!r} in {self.save_dir}")
        dst = self.path(name)
        if dst.exists():
            shutil.rmtree(dst)
        dst.mkdir(parents=True)
        shutil.copytree(src, dst / folder)
        meta = {"name": name, "folder": folder, "target": self.target.name,
                "stored": time.strftime("%Y-%m-%dT%H:%M:%S")}
        if extra:
            meta.update(extra)
        (dst / META).write_text(json.dumps(meta, indent=2, default=str))
        return dst

    def restore(self, name: str) -> str:
        """Copy checkpoint `name` back into the save dir. Returns the folder name."""
        meta = self.meta(name)
        folder = str(meta["folder"])
        src = self.path(name) / folder
        if not src.is_dir():
            raise CheckpointError(f"checkpoint {name!r} has no folder {folder!r}")
        dst = self.save_dir / folder
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        return folder

    # -------------------------------------------------------------- load --
    def load(self, name: str, channel: Channel, *, timeout: float = 300.0,
             watchdog: Optional[Watchdog] = None) -> Dict[str, Any]:
        folder = self.restore(name)
        # The load runs the export and the whole engine call sequence, so the
        # request gets the configured load ceiling, not the channel default.
        channel.request("load_save", dir=folder, timeout=timeout)
        return wait_until(channel, phase_is("gameplay"), timeout, what=f"gameplay after {name}",
                          watchdog=watchdog)

    def load_folder(self, folder: str, channel: Channel, *, timeout: float = 300.0,
                    watchdog: Optional[Watchdog] = None) -> Dict[str, Any]:
        """Load a folder already in the save dir (the shipped autosave)."""
        if not (self.save_dir / folder).is_dir():
            raise CheckpointError(f"no save folder {folder!r} in {self.save_dir}")
        channel.request("load_save", dir=folder, timeout=timeout)
        return wait_until(channel, phase_is("gameplay"), timeout, what=f"gameplay after {folder}",
                          watchdog=watchdog)
