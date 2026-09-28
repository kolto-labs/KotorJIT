"""Record the route and FFprobe hashes before a creative run starts.

Acceptance and export later ask for these two hashes. Writing them down before
launch means they cannot be taken from the run folder after the fact. The line
goes to a log you own, outside the folder where runs go. Use a separate file
from the cleanup commitment log so the tool-owned chain stays clean.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import shutil
import stat
import sys
from pathlib import Path

from .creative_accept import validate_commitment_log

KIND = 'kpharness.input-commitment.v1'
ELF_MAGIC = b'\x7fELF'


def _sha256_regular(path: Path, what: str) -> str:
    """Hash one regular, non-symlink file through a descriptor opened without following links."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError as error:
        raise ValueError(f'{what} is missing: {path}') from error
    except OSError as error:
        raise ValueError(f'{what} must be a regular file, not a link: {path}') from error
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError(f'{what} must be a regular file: {path}')
        digest = hashlib.sha256()
        while block := os.read(descriptor, 1024 * 1024):
            digest.update(block)
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def ffprobe_identity(command: str, *, search_path: str | None = None) -> dict:
    """Resolve FFprobe the way acceptance does, and refuse a script in front of it."""
    if not isinstance(command, str) or not command:
        raise ValueError('FFprobe must be a nonempty path or command name')
    located = shutil.which(command, path=search_path)
    if located is None:
        raise ValueError(f'FFprobe was not found: {command}')
    resolved = Path(located).resolve(strict=True)
    with open(resolved, 'rb') as stream:
        if stream.read(4) != ELF_MAGIC:
            raise ValueError(f'FFprobe must be a program file (ELF), not a script: {resolved}')
    return {'command': command, 'resolved_path': str(resolved),
            'sha256': _sha256_regular(resolved, 'FFprobe')}


def _append_line(path: Path, identity: tuple[int, int], line: dict) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if (info.st_dev, info.st_ino) != identity or info.st_nlink != 1 or not stat.S_ISREG(info.st_mode):
            raise ValueError('inputs log changed while opening')
        payload = (json.dumps(line, sort_keys=True, separators=(',', ':')) + '\n').encode()
        # One O_APPEND write per line keeps concurrent writers from interleaving.
        if os.write(descriptor, payload) != len(payload):
            raise OSError('short inputs log write')
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def commit_inputs(*, route: os.PathLike | str, ffprobe: str, log: os.PathLike | str,
                  runs_dir: os.PathLike | str, search_path: str | None = None) -> dict:
    """Hash the route and FFprobe, then append one line to the inputs log."""
    runs = Path(runs_dir)
    if not runs.is_dir():
        raise ValueError(f'runs folder must exist: {runs}')
    # Same admission rule as the cleanup commitment log; imported, not copied.
    path, identity = validate_commitment_log(log, runs)
    route_path = Path(os.path.abspath(Path(route).expanduser()))
    route_sha = _sha256_regular(route_path, 'route')
    tool = ffprobe_identity(ffprobe, search_path=search_path)
    line = {'kind': KIND, 'route': {'path': str(route_path), 'sha256': route_sha},
            'ffprobe': tool, 'utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    _append_line(path, identity, line)
    return line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog='python3 -m kpharness.commit_inputs',
        description='Record the route and FFprobe hashes before you launch a run. '
                    'One line is added to your inputs log and printed.')
    parser.add_argument('--route', required=True, help='route TOML file you will run')
    parser.add_argument('--ffprobe', required=True, help='FFprobe program you will pass to the run')
    parser.add_argument('--log', required=True, help='your inputs log; it must already exist')
    parser.add_argument('--runs-dir', required=True, help='folder where runs go; the log must be outside it')
    options = parser.parse_args(argv)
    try:
        line = commit_inputs(route=options.route, ffprobe=options.ffprobe,
                             log=options.log, runs_dir=options.runs_dir)
    except (ValueError, OSError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}))
        return 1
    print(json.dumps(line, sort_keys=True, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
