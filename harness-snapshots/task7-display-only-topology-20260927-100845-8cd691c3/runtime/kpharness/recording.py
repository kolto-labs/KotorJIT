"""Owned X11 recording and marker-selected media, independent of game control."""
from __future__ import annotations

import hashlib
import copy
import json
import math
import re
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from .display_backends import OwnedWindow

# Skip arming/startup announcements: these do not describe a creative effect.
CREATIVE_MARKER = r'\[(?:cursed:(?:roulette|shout|necro|boom|wheel|rave|mirror|pinata|slowmo|strike)|ahto|alarm|meditation|conscience|arrival|wounded)\](?!\s*(?:armed|the beat drops)\b)'


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def artifact(path: Path) -> dict:
    return {'path': str(Path(path).resolve()), 'sha256': sha256(path)}


def probe_video(path: Path, ffprobe: str = 'ffprobe') -> dict:
    data = json.loads(subprocess.check_output(
        [ffprobe, '-v', 'error', '-select_streams', 'v:0', '-show_entries',
         'stream=width,height,nb_frames,avg_frame_rate,r_frame_rate:format=duration', '-of', 'json', str(path)],
        text=True, timeout=30))
    stream = data['streams'][0]
    duration = float(data['format']['duration'])
    if not math.isfinite(duration) or duration <= 0 or int(stream['width']) <= 0 or int(stream['height']) <= 0:
        raise ValueError('recording has no valid video dimensions/duration')
    return {'duration_seconds': duration, 'width': int(stream['width']), 'height': int(stream['height']),
            'encoded_average_frame_rate': stream.get('avg_frame_rate'),
            'encoded_nominal_frame_rate': stream.get('r_frame_rate'),
            'encoded_frame_count': stream.get('nb_frames'),
            'render_cadence': 'unvalidated; encoded frames may repeat the same game frame'}


class X11Recorder:
    """Only signal the Popen recorder owned by this instance; stop is idempotent."""
    def __init__(self, run_dir: Path, *, ffmpeg: str = 'ffmpeg', fps: int = 60,
                 marker_pattern: str = CREATIVE_MARKER):
        if isinstance(fps, bool) or not isinstance(fps, int) or not 1 <= fps <= 120:
            raise ValueError('capture FPS must be an integer in [1,120]')
        self.run_dir = Path(run_dir)
        self.ffmpeg, self.fps = ffmpeg, fps
        self.pattern = re.compile(marker_pattern)
        self.process = None
        self.log = None
        self.started = None
        self.marker = None
        self.error = None
        self._thread = None
        self._stop = threading.Event()
        self._offset = 0
        self._pending = b''
        self.capture = {}

    def start(self, display: int, screen: tuple[int, int], native_log: Path) -> None:
        if self.process is not None:
            raise RuntimeError('recorder already started')
        width, height = screen
        if display < 0 or width <= 0 or height <= 0 or width % 2 or height % 2:
            raise ValueError('capture needs a real display and positive even screen dimensions')
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.log = (self.run_dir / 'ffmpeg.log').open('wb')
        self._offset = native_log.stat().st_size if native_log.exists() else 0
        command = [self.ffmpeg, '-nostdin', '-y', '-threads', '2', '-f', 'x11grab',
                   '-framerate', str(self.fps), '-video_size', f'{width}x{height}',
                   '-i', f':{display}.0', '-an', '-c:v', 'libx264', '-preset', 'ultrafast',
                   '-crf', '28', '-pix_fmt', 'yuv420p', '-threads', '2', str(self.run_dir / 'continuous.mp4')]
        self.started = time.monotonic()
        self.capture = {'display': display, 'screen': [width, height], 'fps': self.fps,
                        'capture_sampling_fps': self.fps, 'interpolation': False,
                        'render_cadence': 'unvalidated; requires distinct-frame analysis and gameplay observation',
                        'started_monotonic': self.started, 'initial_native_log_offset': self._offset, 'command': command}
        try:
            self.process = subprocess.Popen(command, stdout=self.log, stderr=subprocess.STDOUT)
        except BaseException:
            self.log.close(); self.log = None
            raise
        self._thread = threading.Thread(target=self._watch, args=(native_log,), daemon=True)
        self._thread.start()

    def observe(self, path: Path, now: float) -> None:
        """Read fresh complete lines; retain exact marker text and detection time."""
        if not path.exists():
            return
        if path.stat().st_size < self._offset:
            self._offset = 0; self._pending = b''
        with path.open('rb') as stream:
            stream.seek(self._offset)
            fresh = stream.read()
            self._offset = stream.tell()
        lines = (self._pending + fresh).split(b'\n')
        self._pending = lines.pop()
        for raw in lines:
            line = raw.decode('utf-8', 'replace')
            if self.marker is None and self.pattern.search(line):
                self.marker = {'line': line, 'detected_monotonic': now,
                               'capture_seconds': max(0.0, now - self.started),
                               'selection_clock': 'monotonic log detection, 100ms poll; capture startup latency not calibrated'}

    def _watch(self, native_log: Path) -> None:
        while not self._stop.wait(.1):
            try:
                self.observe(native_log, time.monotonic())
            except OSError:
                pass  # A game may replace/truncate its log while loading.

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        process = self.process
        if process is not None:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=5)
                    self.error = 'recorder required forced kill; MP4 may be incomplete'
            # ffmpeg may return255 after SIGINT even when it finalizes correctly.
            if process.returncode not in (0, 255) and self.error is None:
                self.error = f'recorder exited {process.returncode}'
            self.process = None
        if self.log is not None:
            self.log.close(); self.log = None
        if self.started is not None:
            (self.run_dir / 'capture.json').write_text(json.dumps(
                {**self.capture, 'marker': self.marker, 'error': self.error}, indent=2) + '\n')


class X11WindowRecorder(X11Recorder):
    """Capture and continuously verify one immutable owned X11 window."""

    def __init__(self, run_dir: Path, *, verifier: Callable[[OwnedWindow], OwnedWindow],
                 lease, ffmpeg: str = 'ffmpeg', fps: int = 60,
                 marker_pattern: str = CREATIVE_MARKER, watch_interval: float = .25,
                 popen: Callable[..., object] = subprocess.Popen):
        super().__init__(run_dir, ffmpeg=ffmpeg, fps=fps, marker_pattern=marker_pattern)
        if watch_interval < .25:
            raise ValueError('window watch interval must be at least 250 ms')
        self._verifier, self._lease = verifier, lease
        self._watch_interval, self._popen = watch_interval, popen
        self.target = None
        self.failure = None
        self._stopping = False
        self._checks = 0
        self._failure_lock = threading.Lock()

    def start(self, target: OwnedWindow, native_log: Path) -> None:
        if self.process is not None or self.started is not None:
            raise RuntimeError('recorder already started')
        if not isinstance(target, OwnedWindow) or 'x11_window_capture' not in target.capture_capabilities:
            raise ValueError('exact-window recorder requires an admitted OwnedWindow')
        if target.window_id in ('0x0', '0x1') or target.width % 2 or target.height % 2:
            raise ValueError('capture target must be a non-root window with positive even geometry')
        if target.lease_id != self._lease.lease_id or target.display != self._lease.environment.get('DISPLAY'):
            raise RuntimeError('capture target belongs to another display lease')
        if not self._lease.is_alive():
            raise RuntimeError('capture target display lease is not live')
        verified = self._verifier(target)
        if verified != target:
            raise RuntimeError('capture target identity changed before recorder start')
        self.target = target
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.log = (self.run_dir / 'ffmpeg.log').open('wb')
        self._offset = native_log.stat().st_size if native_log.exists() else 0
        command = [self.ffmpeg, '-nostdin', '-y', '-threads', '2', '-f', 'x11grab',
                   '-framerate', str(self.fps), '-video_size', f'{target.width}x{target.height}',
                   '-window_id', target.window_id, '-i', target.display, '-an', '-c:v', 'libx264',
                   '-preset', 'ultrafast', '-crf', '28', '-pix_fmt', 'yuv420p', '-threads', '2',
                   str(self.run_dir / 'continuous.mp4')]
        self.started = time.monotonic()
        self.capture = {
            'kind': 'x11-window', 'root_capture': False, 'window_id': target.window_id,
            'input': target.display, 'lease_id': target.lease_id, 'command': tuple(command),
            'capture_sampling_fps_requested': self.fps, 'interpolation': False,
            'start': 'after_first_mapped_owned_window', 'status': 'running',
            'geometry_at_start': [target.width, target.height],
            'watch': {'interval_ms': int(self._watch_interval * 1000), 'checks': 0},
            'initial_native_log_offset': self._offset,
        }
        try:
            self.process = self._popen(command, env=dict(target.environment),
                                       stdout=self.log, stderr=subprocess.STDOUT)
        except BaseException:
            self.log.close(); self.log = None
            raise
        self._thread = threading.Thread(target=self._watch_window, args=(native_log,), daemon=True)
        self._thread.start()

    def _fail(self, error_class: str, detail: str, last: OwnedWindow | None = None) -> None:
        with self._failure_lock:
            if self.failure is not None or self._stopping:
                return
            self.failure = {
                'error_class': error_class, 'detail': detail,
                'elapsed_seconds': max(0.0, time.monotonic() - self.started),
                'initial_identity': self.target.receipt(),
                'last_verified_identity': None if last is None else last.receipt(),
                'ffmpeg_status': None if self.process is None else self.process.poll(),
            }
            self.error = f'{error_class}: {detail}'
            self.capture['status'] = 'failed'
            (self.run_dir / 'capture-failure.json').write_text(json.dumps(self.failure, indent=2) + '\n')
            self._stop.set()

    def _watch_window(self, native_log: Path) -> None:
        while not self._stop.wait(self._watch_interval):
            try:
                self.observe(native_log, time.monotonic())
                if target := self.target:
                    if target.lease_id != self._lease.lease_id:
                        self._fail('lease_identity_changed', 'capture target lease identity changed'); return
                if not self._lease.is_alive():
                    self._fail('lease_lost', 'owned Gamescope/readiness process exited'); return
                if self.process.poll() is not None:
                    self._fail('recorder_exited', f'ffmpeg exited {self.process.returncode}'); return
                current = self._verifier(self.target)
                self._checks += 1
                self.capture.setdefault('watch', {'interval_ms': int(self._watch_interval * 1000)})['checks'] = self._checks
                if current != self.target:
                    kind = 'window_resized' if (current.width, current.height) != (self.target.width, self.target.height) else 'window_identity_changed'
                    self._fail(kind, 'frozen owned-window identity changed', current); return
            except BaseException as error:
                self._fail('window_query_failed', f'{type(error).__name__}: {error}'); return

    def check(self) -> None:
        if self.failure is not None:
            raise RuntimeError(self.error)

    def stop(self) -> None:
        process = self.process
        if process is not None and process.poll() is not None and self.failure is None:
            self._fail('recorder_exited', f'ffmpeg exited {process.returncode} before orderly finalization')
        self._stopping = True
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2); self._thread = None
        was_live = process is not None and process.poll() is None
        if was_live:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)
                if self.failure is None:
                    self.error = 'recorder required forced kill; MP4 may be incomplete'
        if process is not None and process.returncode not in (0, 255):
            if self.failure is None:
                self.error = f'recorder exited {process.returncode}'
        if process is not None and process.returncode == 255 and not was_live and self.failure is None:
            self.error = 'recorder exited 255 before orderly finalization'
        if self.failure is None:
            self.capture['status'] = 'passed' if self.error is None else 'failed'
        self.process = None
        if self.log is not None:
            self.log.close(); self.log = None
        if self.started is not None:
            (self.run_dir / 'capture.json').write_text(json.dumps(
                {**self.capture, 'marker': self.marker, 'error': self.error}, indent=2) + '\n')

    def receipt(self) -> dict:
        continuous = self.run_dir / 'continuous.mp4'
        return {
            'capture': copy.deepcopy(self.capture),
            'cadence': {
                'capture_sampling_fps_requested': self.fps,
                'encoded': {'average_frame_rate': None, 'nominal_frame_rate': None, 'frame_count': None},
                'ffmpeg': {'duplicates': None, 'drops': None, 'diagnostics_status': 'recorded-or-unavailable'},
                'distinct_game_frames': {'status': 'unvalidated', 'method': None},
                'visual_review': {'status': 'pending', 'scope': 'native behavior, framing, readability, and cadence'},
            },
            'failure': copy.deepcopy(self.failure),
            'media': {'status': 'retained_failure_recording' if self.failure else 'retained_for_visual_review',
                      'continuous': artifact(continuous) if continuous.is_file() else None},
        }


def clip_window(duration: float, marker: dict | None, route_start: float = 0) -> dict:
    length = min(10.0, duration)
    if marker is not None:
        start = min(max(0.0, marker['capture_seconds'] - 1.0), max(0.0, duration - length))
        selection = 'first creative native-log marker'
    else:
        start = max(0.0, duration - length, min(route_start, duration - length))
        selection = 'fallback: final route interval; no creative marker, visual review required'
    return {'start_seconds': start, 'duration_seconds': length, 'selection': selection,
            'marker': marker, 'visual_review_required': True}


def render(run_dir: Path, *, marker: dict | None, route_start: float = 0,
           ffmpeg: str = 'ffmpeg', ffprobe: str = 'ffprobe') -> dict:
    """Call only for successful routes; generated media is not semantic proof."""
    run_dir = Path(run_dir)
    report = json.loads((run_dir / 'report.json').read_text())
    if report.get('ok') is not True or any(s.get('status') != 'ok' for s in report.get('steps', [])):
        raise ValueError('success media requires all route steps passed, without skips')
    source = run_dir / 'continuous.mp4'
    info = probe_video(source, ffprobe)
    selection = clip_window(info['duration_seconds'], marker, route_start)
    common = [ffmpeg, '-nostdin', '-y', '-v', 'error', '-threads', '2',
              '-ss', str(selection['start_seconds']), '-t', str(selection['duration_seconds']), '-i', str(source)]
    mp4, gif = run_dir / 'representative.mp4', run_dir / 'representative.gif'
    subprocess.run(common + ['-an', '-vf', 'scale=640:-2', '-filter_threads', '2',
                             '-c:v', 'libx264', '-preset', 'fast', '-crf', '24', '-threads', '2', str(mp4)],
                   check=True, timeout=180)
    subprocess.run(common + ['-filter_complex_threads', '1', '-filter_complex',
        'fps=8,scale=480:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3',
        '-threads', '2', str(gif)], check=True, timeout=180)
    receipt = {'source_video': artifact(source), 'source_geometry': info, **selection,
               'artifacts': {p.name: {**artifact(p), **probe_video(p, ffprobe)} for p in (mp4, gif)},
               'scope': 'route/media completion only; does not certify all example live obligations'}
    (run_dir / 'media.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt
