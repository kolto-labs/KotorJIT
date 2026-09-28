#!/usr/bin/env python3
"""Check this host for the programs the creative harness needs.

It looks at files. The only programs it starts are `ffmpeg -version` and
`ffprobe -version`, to confirm each is the real tool, and it reads at most 64 KiB
of their output. It never opens a display.
It prints one JSON line. The exit code is 0 when every blocking check passes.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import selectors
import stat
import subprocess
import sys
import time
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
# Distribution package folders. The capture noise floor was measured with /usr/bin/ffmpeg.
SYSTEM_DIRS = ('/usr/bin', '/bin')
VERSION_TIMEOUT_SECONDS = 10
# Real `-version` output is a few KiB. Anything longer is not the tool, so reading stops here.
VERSION_OUTPUT_LIMIT = 64 * 1024


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


def _run_version(command: list[str]) -> subprocess.CompletedProcess | None:
    """Run `command` and read at most VERSION_OUTPUT_LIMIT bytes of stdout before a deadline.

    A program that writes more, or runs longer, is killed and gets return code -9.
    """
    try:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    deadline = time.monotonic() + VERSION_TIMEOUT_SECONDS
    chunks: list[bytes] = []
    total, cut = 0, False
    with process, selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                cut = True
                break
            if not selector.select(remaining):
                continue
            block = os.read(process.stdout.fileno(), 16 * 1024)
            if not block:
                break
            chunks.append(block)
            total += len(block)
            if total > VERSION_OUTPUT_LIMIT:
                cut = True
                break
        if cut:
            process.kill()
        try:
            returncode = process.wait(timeout=max(0.0, deadline - time.monotonic()) + 1)
        except subprocess.TimeoutExpired:
            process.kill()
            returncode = process.wait()
    text = b''.join(chunks)[:VERSION_OUTPUT_LIMIT].decode('utf-8', errors='replace')
    return subprocess.CompletedProcess(command, -9 if cut else returncode, stdout=text, stderr='')


def version_banner(name: str, resolved: Path) -> str | None:
    """Run `<resolved> -version` and return the first line when it names this tool, else None."""
    result = _run_version([str(resolved), '-version'])
    if result is None:
        return None
    lines = (result.stdout or '').splitlines()
    first = lines[0].strip() if lines else ''
    if result.returncode != 0 or not first.startswith(name + ' version '):
        return None
    return ' '.join(first.split()[:3])


def _elf_elsewhere(hits: list[Path]) -> str | None:
    """Name a later ELF on PATH, preferring the distribution package folders."""
    elves = [hit for hit in hits if _is_elf(Path(os.path.realpath(hit)))]
    system = [hit for hit in elves if str(hit.parent) in SYSTEM_DIRS]
    chosen = (system or elves or [None])[0]
    return None if chosen is None else str(chosen)


def check_tool(name: str, path: str) -> dict:
    """Classify the first PATH hit as ok, wrapper (not ELF), not_the_tool or missing.

    For ffmpeg and ffprobe an ELF is ok only when `-version` names the tool.
    """
    blocking = name not in OPTIONAL
    hits = _candidates(name, path)
    if not hits:
        return {'status': 'missing', 'path': None, 'resolved': None, 'blocking': blocking}
    first = hits[0]
    resolved = Path(os.path.realpath(first))
    entry = {'path': str(first), 'resolved': str(resolved)}
    if _is_elf(resolved):
        if name not in ELF_REQUIRED:
            return {**entry, 'status': 'ok', 'blocking': False}
        banner = version_banner(name, resolved)
        if banner is not None:
            return {**entry, 'status': 'ok', 'blocking': False, 'version': banner}
        entry.update(status='not_the_tool', blocking=True)
    else:
        entry.update(status='wrapper', blocking=name in ELF_REQUIRED)
    later = _elf_elsewhere(hits[1:])
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
            'scope': 'file checks plus ffmpeg -version and ffprobe -version; no display was opened'}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Check this host for the programs the creative harness needs. '
                    'Only ffmpeg -version and ffprobe -version are run. One JSON line is printed.')
    parser.add_argument('--path', help='search these directories instead of PATH')
    parser.add_argument('--dri-dir', default='/dev/dri', help='look for render nodes here')
    options = parser.parse_args(argv)
    result = check_host(path=options.path, dri_dir=options.dri_dir)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
