#!/usr/bin/env python3
"""Check this host for the programs the creative harness needs.

This only looks at files. It never starts a program and never opens a display.
It prints one JSON line. The exit code is 0 when every blocking check passes.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import stat
import sys
from pathlib import Path

KIND = 'kpharness.creative-host-check.v1'
TOOLS = ('ffmpeg', 'ffprobe', 'gamescope', 'Xwayland', 'xdotool', 'xwininfo',
         'glxinfo', 'bwrap', 'wine', 'mpv')
# The harness hashes and runs these two directly, so a script in front of them fails later.
ELF_REQUIRED = frozenset({'ffmpeg', 'ffprobe'})
# mpv is used only by the capture diagnostic; its absence does not block a route run.
OPTIONAL = frozenset({'mpv'})
MINIMUM_PYTHON = (3, 12)
ELF_MAGIC = b'\x7fELF'


def _is_executable_file(path: Path) -> bool:
    try:
        info = os.stat(path)
    except OSError:
        return False
    return stat.S_ISREG(info.st_mode) and os.access(path, os.X_OK)


def _is_elf(path: Path) -> bool:
    try:
        with open(path, 'rb') as stream:
            return stream.read(4) == ELF_MAGIC
    except OSError:
        return False


def _candidates(name: str, path: str) -> list[Path]:
    found = []
    for directory in path.split(os.pathsep):
        if not directory:
            continue
        candidate = Path(directory) / name
        if _is_executable_file(candidate):
            found.append(candidate)
    return found


def check_tool(name: str, path: str) -> dict:
    """Classify the first PATH hit as ok (ELF), wrapper (not ELF) or missing."""
    blocking = name not in OPTIONAL
    hits = _candidates(name, path)
    if not hits:
        return {'status': 'missing', 'path': None, 'resolved': None, 'blocking': blocking}
    first = hits[0]
    resolved = Path(os.path.realpath(first))
    entry = {'path': str(first), 'resolved': str(resolved)}
    if _is_elf(resolved):
        return {**entry, 'status': 'ok', 'blocking': False}
    entry.update(status='wrapper', blocking=name in ELF_REQUIRED)
    later = next((str(hit) for hit in hits[1:] if _is_elf(Path(os.path.realpath(hit)))), None)
    if later is not None:
        entry['elf_elsewhere'] = later
    return entry


def check_host(*, path: str | None = None, dri_dir: str | os.PathLike = '/dev/dri') -> dict:
    search = os.environ.get('PATH', '') if path is None else path
    tools = {name: check_tool(name, search) for name in TOOLS}
    render_nodes = sorted(glob.glob(os.path.join(os.fspath(dri_dir), 'renderD*')))
    version = tuple(sys.version_info[:3])
    python = {'version': '.'.join(str(part) for part in version),
              'minimum': '.'.join(str(part) for part in MINIMUM_PYTHON),
              'ok': version[:2] >= MINIMUM_PYTHON}
    blocked = [name for name, entry in tools.items()
               if entry['blocking'] and entry['status'] != 'ok']
    ok = not blocked and bool(render_nodes) and python['ok']
    return {'kind': KIND, 'ok': ok, 'blocked_by': blocked, 'python': python,
            'render_nodes': render_nodes, 'tools': tools,
            'scope': 'file checks only; no program was started and no display was opened'}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Check this host for the programs the creative harness needs. '
                    'Nothing is started. One JSON line is printed.')
    parser.add_argument('--path', help='search these directories instead of PATH')
    parser.add_argument('--dri-dir', default='/dev/dri', help='look for render nodes here')
    options = parser.parse_args(argv)
    result = check_host(path=options.path, dri_dir=options.dri_dir)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
