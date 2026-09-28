"""Check an exported clip folder against its accepted run.

Give it one `accepted-media-*` folder from a run. It re-reads the accepted
receipt and master, re-hashes the MP4 and GIF, and re-probes both with the
FFprobe program you name. It refuses on any mismatch. It changes no file.

Pinned to export sidecar schema 1.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import stat
import subprocess
from pathlib import Path

from .commit_inputs import ffprobe_identity
from .creative_accept import verify_acceptance
from .recording import probe_video

SIDECAR = 'export.json'
SIDECAR_SCHEMA = 1
ARTIFACTS = ('representative.gif', 'representative.mp4')
# Same bounds the exporter applies before publishing (creative_export.py).
MP4_TOLERANCE_SECONDS = 0.1
REPROBE_TOLERANCE_SECONDS = 1e-3
INTERVAL_EPSILON = 1e-6
MAX_SIDECAR_BYTES = 1024 * 1024
MAX_RECEIPT_BYTES = 8 * 1024 * 1024


def _read_regular(path: Path, maximum: int, what: str) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as error:
        raise ValueError(f'{what} must be a regular file, not a link: {path.name}') from error
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError(f'{what} must be a regular file: {path.name}')
        chunks, total = [], 0
        while block := os.read(descriptor, 1024 * 1024):
            total += len(block)
            if total > maximum:
                raise ValueError(f'{what} is too large: {path.name}')
            chunks.append(block)
        return b''.join(chunks)
    finally:
        os.close(descriptor)


def _sha256_regular(path: Path, what: str) -> str:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as error:
        raise ValueError(f'{what} must be a regular file, not a link: {path.name}') from error
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError(f'{what} must be a regular file: {path.name}')
        digest = hashlib.sha256()
        while block := os.read(descriptor, 1024 * 1024):
            digest.update(block)
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def _number(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _artifact_path(export_dir: Path, name: str, recorded: object) -> Path:
    """Accept the exporter's absolute form or a relative name; nothing outside the folder."""
    _require(isinstance(recorded, str) and recorded != '', f'{name}: path is missing')
    candidate = Path(recorded)
    expected = export_dir / name
    if candidate.is_absolute():
        _require(Path(os.path.abspath(candidate)) == expected, f'{name}: path is outside the export folder')
    else:
        _require(candidate.as_posix() == name, f'{name}: path is outside the export folder')
    return expected


def _local_path_fields(sidecar: dict) -> list[str]:
    fields = []
    if isinstance(sidecar.get('run_dir'), str) and os.path.isabs(sidecar['run_dir']):
        fields.append('run_dir')
    source = sidecar.get('source_video')
    if isinstance(source, dict) and isinstance(source.get('path'), str) and os.path.isabs(source['path']):
        fields.append('source_video.path')
    for name, item in sorted((sidecar.get('artifacts') or {}).items()):
        if isinstance(item, dict) and isinstance(item.get('path'), str) and os.path.isabs(item['path']):
            fields.append(f'artifacts.{name}.path')
    for key in ('ffmpeg', 'ffprobe'):
        value = (sidecar.get('settings') or {}).get(key)
        if isinstance(value, str) and os.path.isabs(value):
            fields.append(f'settings.{key}')
    return fields


def verify_export(export_dir: os.PathLike | str, *, route_sha256: str, ffprobe_sha256: str,
                  cleanup_ledger_sha256: str, ffprobe: str) -> dict:
    """Raise ValueError on the first failed check. Otherwise return a report.

    `ok` is true only when every check passes, including that the re-probe used
    the FFprobe program recorded for acceptance.
    """
    given = Path(os.path.abspath(Path(export_dir).expanduser()))
    _require(given.is_dir() and not given.is_symlink(), 'export folder must be a real folder')
    export = given.resolve()
    _require(export.name.startswith('accepted-media-'), 'export folder must be named accepted-media-*')
    run_dir = export.parent

    sidecar = json.loads(_read_regular(export / SIDECAR, MAX_SIDECAR_BYTES, 'sidecar'))
    _require(isinstance(sidecar, dict), 'sidecar must be a JSON object')
    _require(sidecar.get('schema') == SIDECAR_SCHEMA,
             f'unsupported sidecar schema {sidecar.get("schema")!r}; this verifier reads schema {SIDECAR_SCHEMA}')
    for key, value in (('route_sha256', route_sha256), ('ffprobe_sha256', ffprobe_sha256),
                       ('cleanup_ledger_sha256', cleanup_ledger_sha256)):
        _require(sidecar.get('selected_' + key) == value, f'{key} does not match the sidecar')
    if isinstance(sidecar.get('run_dir'), str):
        _require(Path(sidecar['run_dir']).resolve() == run_dir, 'sidecar run_dir is not this run')

    # The accepted receipt must be unchanged since export, and still verify now.
    raw = _read_regular(run_dir / 'creative-run.json', MAX_RECEIPT_BYTES, 'creative-run.json')
    _require(hashlib.sha256(raw).hexdigest() == sidecar.get('accepted_receipt_sha256'),
             'creative-run.json changed since export')
    receipt = json.loads(raw)
    _require(isinstance(receipt, dict), 'creative-run.json must be a JSON object')
    _require(verify_acceptance(receipt, route_sha256=route_sha256, ffprobe_sha256=ffprobe_sha256,
                               cleanup_ledger_sha256=cleanup_ledger_sha256) is True,
             'accepted run no longer passes acceptance verification')
    try:
        review = receipt['visual_review']
        continuous = receipt['media']['continuous']
    except (KeyError, TypeError) as error:
        raise ValueError('accepted receipt lacks review or master media') from error
    _require(sidecar.get('accepted_execution_sha256') == review.get('execution_receipt_sha256'),
             'accepted_execution_sha256 does not match the review')
    _require(sidecar.get('accepted_content_artifact_sha256') == review.get('content_artifact_sha256'),
             'accepted_content_artifact_sha256 does not match the review')
    _require(sidecar.get('accepted_geometry_precondition_sha256') == review.get('geometry_precondition_sha256'),
             'accepted_geometry_precondition_sha256 does not match the review')
    source = sidecar.get('source_video')
    _require(isinstance(source, dict) and source.get('sha256') == continuous.get('sha256'),
             'source_video.sha256 does not match the accepted master')
    master = Path(continuous['path'])
    _require(master.resolve().is_relative_to(run_dir), 'accepted master is outside the run')
    _require(_sha256_regular(master, 'master') == continuous['sha256'], 'accepted master changed')

    start, end, duration = (sidecar.get(key) for key in ('start_seconds', 'end_seconds', 'duration_seconds'))
    _require(all(_number(value) for value in (start, end, duration)), 'interval values must be finite numbers')
    _require(0 <= start < end, 'interval must satisfy 0 <= start < end')
    _require(abs((end - start) - duration) <= INTERVAL_EPSILON, 'interval duration does not equal end - start')
    gif_fps = (sidecar.get('settings') or {}).get('gif_fps')
    _require(isinstance(gif_fps, int) and not isinstance(gif_fps, bool) and 1 <= gif_fps <= 60,
             'settings.gif_fps must be an integer in [1,60]')

    artifacts = sidecar.get('artifacts')
    _require(isinstance(artifacts, dict) and tuple(sorted(artifacts)) == ARTIFACTS,
             'sidecar must list exactly representative.mp4 and representative.gif')
    present = sorted(entry.name for entry in export.iterdir())
    _require(present == sorted((SIDECAR, *ARTIFACTS)),
             'unexpected files in export folder: ' + ', '.join(sorted(set(present) - {SIDECAR, *ARTIFACTS})))

    tool = ffprobe_identity(ffprobe)
    checked = {}
    for name in ARTIFACTS:
        item = artifacts[name]
        _require(isinstance(item, dict), f'{name}: entry must be an object')
        path = _artifact_path(export, name, item.get('path'))
        _require(_sha256_regular(path, name) == item.get('sha256'), f'{name}: SHA-256 does not match')
        probed = probe_video(path, tool['resolved_path'])
        recorded = item.get('duration_seconds')
        _require(_number(recorded) and abs(probed['duration_seconds'] - recorded) <= REPROBE_TOLERANCE_SECONDS,
                 f'{name}: probed duration does not match the sidecar')
        for key in ('width', 'height'):
            _require(probed.get(key) == item.get(key), f'{name}: probed {key} does not match the sidecar')
        tolerance = max(MP4_TOLERANCE_SECONDS, 1 / gif_fps) if name.endswith('.gif') else MP4_TOLERANCE_SECONDS
        _require(abs(probed['duration_seconds'] - duration) <= tolerance,
                 f'{name}: duration does not cover the interval')
        checked[name] = {'sha256': item['sha256'], 'duration_seconds': probed['duration_seconds']}

    local = _local_path_fields(sidecar)
    # The re-probe must use the same FFprobe program that acceptance bound; otherwise ok is false.
    same_ffprobe = tool['sha256'] == ffprobe_sha256
    report = {'ok': same_ffprobe, 'sidecar_schema': SIDECAR_SCHEMA, 'export': export.name, 'artifacts': checked,
              'interval': {'start_seconds': start, 'end_seconds': end},
              'ffprobe_sha256': tool['sha256'],
              'ffprobe_matches_acceptance': same_ffprobe,
              'shareable': not local, 'local_path_fields': local}
    if not same_ffprobe:
        report['error'] = 'the FFprobe program differs from the one recorded for acceptance'
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog='python3 -m kpharness.export_verify',
        description='Check an exported clip folder against its accepted run. Nothing is changed.')
    parser.add_argument('export_dir', help='an accepted-media-* folder inside a run folder')
    parser.add_argument('--route-sha256', required=True, help='route hash from your inputs log')
    parser.add_argument('--ffprobe-sha256', required=True, help='FFprobe hash from your inputs log')
    parser.add_argument('--cleanup-ledger-sha256', required=True, help='last head from your commitment log')
    parser.add_argument('--ffprobe', required=True, help='FFprobe program file to re-probe the clips')
    options = parser.parse_args(argv)
    try:
        report = verify_export(options.export_dir, route_sha256=options.route_sha256,
                               ffprobe_sha256=options.ffprobe_sha256,
                               cleanup_ledger_sha256=options.cleanup_ledger_sha256,
                               ffprobe=options.ffprobe)
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
