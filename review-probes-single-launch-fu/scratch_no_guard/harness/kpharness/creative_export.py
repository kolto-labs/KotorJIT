"""Export a reviewed interval only from a currently accepted Gamescope master."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import stat
import subprocess
import tempfile
import uuid
from pathlib import Path

from .creative_accept import _read_regular, _stable_regular_copy, verify_acceptance
from .display_backends import GAMESCOPE_BACKEND, execution_evidence_ready
from .recording import encode_clip, probe_video, sha256


def accepted_receipt(run_dir: Path, *, route_sha256: str, ffprobe_sha256: str,
                     cleanup_ledger_sha256: str) -> tuple[dict, bytes]:
    """Read fresh evidence, including the actual master, never a cached pass flag."""
    receipt_path = run_dir / 'creative-run.json'
    try:
        raw = _read_regular(receipt_path)
    except OSError as error:
        raise ValueError('accepted receipt must be a regular non-symlink file') from error
    receipt = json.loads(raw)
    if (not isinstance(receipt, dict) or receipt.get('schema') != 2
            or receipt.get('backend') != GAMESCOPE_BACKEND
            or not isinstance(receipt.get('run_dir'), str)
            or Path(receipt.get('run_dir', '')).resolve() != run_dir
            or not execution_evidence_ready(receipt, require_completion=True)
            or not verify_acceptance(receipt, route_sha256=route_sha256,
                                     ffprobe_sha256=ffprobe_sha256,
                                     cleanup_ledger_sha256=cleanup_ledger_sha256)):
        raise ValueError('export requires current accepted Gamescope receipt and unchanged master')
    return receipt, raw


def export(run_dir: Path, *, start_seconds: float, end_seconds: float,
           route_sha256: str, ffprobe_sha256: str, cleanup_ledger_sha256: str,
           gif_fps: int = 25,
           ffmpeg: str = 'ffmpeg', ffprobe: str = 'ffprobe') -> dict:
    """Publish derivatives separately; never modify the accepted execution receipt."""
    run_dir = Path(run_dir).resolve()
    receipt, original = accepted_receipt(run_dir, route_sha256=route_sha256,
                                         ffprobe_sha256=ffprobe_sha256,
                                         cleanup_ledger_sha256=cleanup_ledger_sha256)
    if any(isinstance(value, bool) or not isinstance(value, (int, float))
           or not math.isfinite(value) for value in (start_seconds, end_seconds)):
        raise ValueError('clip start/end must be finite numbers')
    if not 0 <= start_seconds < end_seconds:
        raise ValueError('clip requires 0 <= start < end')
    if isinstance(gif_fps, bool) or not isinstance(gif_fps, int) or not 1 <= gif_fps <= 60:
        raise ValueError('GIF FPS must be an integer in [1,60]')
    source = Path(receipt['media']['continuous']['path'])
    duration = end_seconds - start_seconds
    destination = run_dir / ('accepted-media-' + uuid.uuid4().hex)
    # Incomplete or unverified derivatives never acquire a published sidecar.
    with tempfile.TemporaryDirectory(prefix='.creative-export-', dir=run_dir) as temporary:
        staging = Path(temporary)
        stable_source = staging / 'accepted-master.mp4'
        _stable_regular_copy(source, stable_source, receipt['media']['continuous']['sha256'])
        info = probe_video(stable_source, ffprobe)
        if end_seconds > info['duration_seconds']:
            raise ValueError('clip end exceeds master duration; refusing truncated interval')
        if accepted_receipt(run_dir, route_sha256=route_sha256,
                            ffprobe_sha256=ffprobe_sha256,
                            cleanup_ledger_sha256=cleanup_ledger_sha256)[1] != original:
            raise ValueError('accepted provenance changed before rendering')
        artifacts = encode_clip(stable_source, staging, start_seconds=start_seconds,
            duration_seconds=duration, gif_fps=gif_fps, ffmpeg=ffmpeg, ffprobe=ffprobe)
        for name, item in artifacts.items():
            tolerance = max(0.1, 1 / gif_fps) if name.endswith('.gif') else 0.1
            if abs(item['duration_seconds'] - duration) > tolerance:
                raise ValueError(f'{name} duration does not cover the requested interval')
            item['path'] = str(destination / name)
        current, current_raw = accepted_receipt(run_dir, route_sha256=route_sha256,
                                                ffprobe_sha256=ffprobe_sha256,
                                                cleanup_ledger_sha256=cleanup_ledger_sha256)
        if current_raw != original:
            raise ValueError('accepted provenance changed during rendering')
        sidecar = {
            'schema': 1, 'run_dir': str(run_dir),
            'source_video': dict(current['media']['continuous']), 'source_geometry': info,
            'accepted_execution_sha256': current['visual_review']['execution_receipt_sha256'],
            'accepted_receipt_sha256': hashlib.sha256(original).hexdigest(),
            'selected_route_sha256': route_sha256,
            'selected_ffprobe_sha256': ffprobe_sha256,
            'selected_cleanup_ledger_sha256': cleanup_ledger_sha256,
            'accepted_content_artifact_sha256': current['visual_review']['content_artifact_sha256'],
            'accepted_geometry_precondition_sha256': current['visual_review']['geometry_precondition_sha256'],
            'start_seconds': start_seconds, 'end_seconds': end_seconds,
            'duration_seconds': duration, 'selection': 'explicit reviewed interval',
            'settings': {'gif_fps': gif_fps, 'gif_width': 480, 'mp4_width': 640,
                         'mp4_cadence': 'preserve source timestamps; no interpolation',
                         'ffmpeg': ffmpeg, 'ffprobe': ffprobe},
            'artifacts': artifacts,
            'scope': 'accepted master derivatives; review output readability and GIF smoothness',
        }
        stable_source.unlink()
        (staging / 'export.json').write_text(json.dumps(sidecar, indent=2) + '\n')
        staging.rename(destination)
    return sidecar


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir')
    parser.add_argument('--start-seconds', type=float, required=True)
    parser.add_argument('--end-seconds', type=float, required=True)
    parser.add_argument('--gif-fps', type=int, default=25)
    parser.add_argument('--route-sha256', required=True)
    parser.add_argument('--ffprobe-sha256', required=True)
    parser.add_argument('--cleanup-ledger-sha256', required=True)
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--ffprobe', default='ffprobe')
    args = parser.parse_args(argv)
    try:
        receipt = export(Path(args.run_dir), start_seconds=args.start_seconds,
            end_seconds=args.end_seconds, route_sha256=args.route_sha256,
            ffprobe_sha256=args.ffprobe_sha256,
            cleanup_ledger_sha256=args.cleanup_ledger_sha256,
            gif_fps=args.gif_fps, ffmpeg=args.ffmpeg, ffprobe=args.ffprobe)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}))
        return 1
    print(json.dumps({'ok': True, 'artifacts': receipt['artifacts']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
