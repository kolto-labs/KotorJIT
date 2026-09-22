"""Owned X11 recording and marker-selected media, independent of game control."""
from __future__ import annotations

import hashlib
import json
import math
import re
import signal
import subprocess
import threading
import time
from pathlib import Path

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
