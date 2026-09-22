"""K1 creative session: private staging and teardown scoped to its own Wine prefix."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from . import discover
from .recording import artifact, sha256
from .session import BootFailure, GameSession, display_in_use, pids_by_name, preflight_tmp_write

OWNER = 'kpharness.creative.v1'


def disjoint(left: Path, right: Path) -> bool:
    left, right = left.resolve(), right.resolve()
    return left != right and not left.is_relative_to(right) and not right.is_relative_to(left)


def claim_directory(path: Path, source: Path) -> Path:
    """Only empty/new directories or this runner's prior marked directory may mutate."""
    if path.is_symlink() or not disjoint(path, source):
        raise ValueError('owned directory aliases or overlaps source: ' + str(path))
    path = path.resolve()
    marker = path.parent / ('.' + path.name + '.kp-creative-owner.json')
    expected = {'owner': OWNER, 'path': str(path), 'source': str(source.resolve())}
    if marker.exists():
        if marker.is_symlink() or json.loads(marker.read_text()) != expected:
            raise ValueError('directory ownership record does not match: ' + str(path))
    else:
        if path.exists() and (not path.is_dir() or any(path.iterdir())):
            raise ValueError('refusing nonempty unowned directory: ' + str(path))
        path.mkdir(parents=True, exist_ok=True)
        with marker.open('x') as stream:
            json.dump(expected, stream)
    return path


def private_tree(path: Path) -> None:
    """Materialize source symlinks inside an already-owned stage before writing."""
    if not path.exists() and not path.is_symlink():
        path.mkdir(parents=True)
        return
    if not path.is_dir():
        raise ValueError('expected staged directory: ' + str(path))
    if not path.is_symlink() and not any(p.is_symlink() for p in path.rglob('*')):
        return
    with tempfile.TemporaryDirectory(prefix='.creative-copy-', dir=path.parent) as temp:
        copied = Path(temp) / 'tree'
        shutil.copytree(path, copied, symlinks=False)
        if path.is_symlink():
            path.unlink()
        else:
            shutil.rmtree(path)  # Owned local copy; symlink root handled above.
        copied.rename(path)


def source_receipt(source: Path) -> dict:
    """Bound the mutable-source preservation check; static game assets aren't rescanned."""
    names = {'swkotor.exe', 'swkotor.ini', 'kotorphasor.ini', 'kphasor.dll', 'binkw32.dll',
             'binkw32_real.dll', 'steam_appid.txt', 'kotorphasor.log', 'kotorphasor-proxy.log'}
    result = {name: sha256(source / name) if (source / name).is_file() else None for name in sorted(names)}
    for directory in ('Saves', 'Override', 'kotorphasor/scripts'):
        root = source / directory
        for path in sorted(root.rglob('*')) if root.is_dir() else []:
            if path.is_file():
                result[str(path.relative_to(source))] = sha256(path)
    return result


def owned_pid(pid: int, prefix: Path, stage: Path, proc_root: Path = Path('/proc')) -> bool:
    try:
        proc = proc_root / str(pid)
        env = (proc / 'environ').read_bytes().split(b'\0')
        return (f'WINEPREFIX={prefix.resolve()}'.encode() in env
                and (proc / 'cwd').resolve() == stage.resolve())
    except OSError:
        return False


class LinuxWineCreativeSession(GameSession):
    def __init__(self, *, source: Path, scripts: list[Path], recorder, run_dir: Path, **kwargs):
        super().__init__('k1', reset_saves=True, **kwargs)
        self.source = source.resolve()
        self.scripts = scripts
        self.recorder = recorder
        self.run_dir = run_dir.resolve()
        self._closed = False
        self.deployed = []

    def _validate_staged_path(self):
        if not disjoint(self.staged, self.source) or not disjoint(self.wineprefix, self.source):
            raise BootFailure('unsafe stage', 'source/stage/prefix must be disjoint')
        return self.source, self.source

    def acquire_lock(self):
        # GameSession's quota fallback may suggest a caller-owned display.
        # This runner records only a newly allocated, owned Xvfb.
        if display_in_use(self.display):
            raise BootFailure('display owned elsewhere', str(self.display))
        super().acquire_lock()

    def boot(self, resources=None):
        if os.environ.get('KP_HARNESS_REUSE_DISPLAY'):
            raise BootFailure('display ownership', 'creative recording requires its own Xvfb')
        problem = preflight_tmp_write()
        if problem:
            raise BootFailure('display preflight', problem)
        return super().boot(resources)

    def game_pids(self):
        return [pid for pid in pids_by_name(self.target.process_name)
                if owned_pid(pid, self.wineprefix, self.staged)]

    def process_alive(self):
        return bool(self.game_pids()) or (self.launcher is not None and self.launcher.poll() is None)

    def _stage_resources(self, install, resources):
        # The parent has created the overlay, but has not yet installed runtime
        # files. Privatize writable subtrees before any nested symlink writes.
        names = (*self.target.writable_dirs, 'Override', 'harness-resources')
        for name in names:
            matches = [path for path in self.staged.iterdir() if path.name.casefold() == name.casefold()]
            for path in matches or [self.staged / name]:
                private_tree(path)
        super()._stage_resources(install, resources)

    def stage(self, resources=None):
        super().stage(resources)
        scripts = self.game_dir / 'kotorphasor/scripts'
        if scripts.is_symlink() or not scripts.resolve().is_relative_to(self.staged):
            raise BootFailure('script ownership', 'script directory escaped owned stage')
        # Everything here was created/materialized in the runner-owned stage.
        for path in scripts.iterdir():
            if path.is_file() or path.is_symlink():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)
        for source in self.scripts:
            destination = scripts / source.name
            shutil.copy2(source, destination)
            self.deployed.append({'source': artifact(source), 'deployed': artifact(destination)})
        (self.run_dir / 'deployed-scripts.json').write_text(json.dumps(self.deployed, indent=2) + '\n')
        prior_logs = {}
        for name in ('kotorphasor.log', 'kotorphasor-proxy.log'):
            path = self.game_dir / name
            if path.is_symlink() or not path.resolve().is_relative_to(self.staged):
                raise BootFailure('log ownership', str(path))
            prior_logs[name] = {'bytes': path.stat().st_size, 'sha256': sha256(path)} if path.is_file() else None
            path.write_bytes(b'')
        (self.run_dir / 'prior-log-identities.json').write_text(json.dumps(prior_logs, indent=2) + '\n')

    def start_xvfb(self):
        super().start_xvfb()
        self.recorder.start(self.display, self.screen, self.runtime_log)

    def teardown(self, graceful=True):
        if self._closed:
            return
        self._closed = True
        try:
            # Also runs on GameSession.boot's exception path, before Xvfb dies.
            self.recorder.stop()
        finally:
            super().teardown(graceful=graceful)
