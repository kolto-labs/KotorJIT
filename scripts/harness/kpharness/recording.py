"""Owned X11 recording and marker-selected media, independent of game control."""
from __future__ import annotations

import hashlib
import copy
import json
import math
import os
import re
import signal
import shutil
import stat
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .display_backends import (CADENCE_POLICY, CONTENT_METHOD, CONTENT_POLICIES, CONTENT_ROW_KEYS,
                               WINDOW_CAPTURE_ADAPTER, OwnedWindow, evaluate_content,
                               geometry_precondition, pattern_index_cell_crops)

# Skip arming/startup announcements: these do not describe a creative effect.
CREATIVE_MARKER = r'\[(?:cursed:(?:roulette|shout|necro|boom|wheel|rave|mirror|pinata|slowmo|strike)|ahto|alarm|meditation|conscience|arrival|wounded)\](?!\s*(?:armed|the beat drops)\b)'
FORBIDDEN_X11_STARTUP = (b'Cannot get the image data', b'Continuing without shared memory')
MAX_DIAGNOSTIC_READ = 1024 * 1024
MAX_PROGRESS_SUFFIX = 64 * 1024
MAX_CANONICAL_PTS_FRAMES = 250_000
MAX_CANONICAL_PTS_BYTES = 16 * 1024 * 1024
_CANONICAL_COUNTER = re.compile(rb'(?:0|[1-9][0-9]*)\Z')
_DISPLAY_SCREEN_ZERO = re.compile(r'^:([0-9]+)(?:\.0)?$')
_FD_PATH = re.compile(r'/proc/self/fd/[0-9]+')
MAX_CONTENT_PROBE_BYTES = 64 * 1024 * 1024
# FFprobe deadlines scale with the frames it must decode, within a hard maximum.
PROBE_DEADLINE_BASE_SECONDS = 30.0
PROBE_DEADLINE_PER_FRAME_SECONDS = 0.2
PROBE_DEADLINE_MAX_SECONDS = 3600.0


def probe_deadline_seconds(frame_count: int) -> float:
    """Wall-clock bound for one FFprobe child that decodes ``frame_count`` frames."""
    if type(frame_count) is not int or frame_count < 0:
        raise ValueError('probe frame count must be a nonnegative integer')
    return min(PROBE_DEADLINE_MAX_SECONDS,
               PROBE_DEADLINE_BASE_SECONDS + frame_count * PROBE_DEADLINE_PER_FRAME_SECONDS)


@dataclass(frozen=True)
class FFmpegProgress:
    frame: int
    out_time_us: int
    dup_frames: int
    drop_frames: int
    speed: str
    terminal: bool


@dataclass(frozen=True)
class CadenceThresholds:
    minimum_rate_ratio: float = .99
    maximum_drop_ratio: float = .005
    maximum_gap_seconds: float = .050

    def __post_init__(self) -> None:
        values = (self.minimum_rate_ratio, self.maximum_drop_ratio, self.maximum_gap_seconds)
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not math.isfinite(value) for value in values):
            raise ValueError('cadence thresholds must be finite numbers')
        if not 0 < self.minimum_rate_ratio <= 1:
            raise ValueError('minimum rate ratio must be in (0,1]')
        if not 0 <= self.maximum_drop_ratio <= 1:
            raise ValueError('maximum drop ratio must be in [0,1]')
        if not 0 < self.maximum_gap_seconds <= 1:
            raise ValueError('maximum gap must be in (0,1]')


def _progress_counter(value: bytes, name: str) -> int:
    if not _CANONICAL_COUNTER.fullmatch(value):
        raise ValueError(f'noncanonical FFmpeg progress counter: {name}')
    return int(value)


def parse_progress_blocks(raw: bytes) -> tuple[list[FFmpegProgress], bytes]:
    """Parse complete ``-progress`` blocks, retaining an incomplete byte suffix."""
    if not isinstance(raw, bytes):
        raise TypeError('FFmpeg progress input must be bytes')
    complete_lines = raw.split(b'\n')
    suffix_line = complete_lines.pop() if not raw.endswith(b'\n') else b''
    current: dict[bytes, bytes] = {}
    blocks: list[FFmpegProgress] = []
    terminal = False
    consumed_incomplete: list[bytes] = []
    for line in complete_lines:
        if not line:
            continue
        if terminal:
            raise ValueError('FFmpeg progress data follows terminal block')
        if b'=' not in line:
            raise ValueError('malformed FFmpeg progress line')
        key, value = line.split(b'=', 1)
        if not key or key in current:
            raise ValueError('duplicate or empty FFmpeg progress key')
        current[key] = value
        if key != b'progress':
            continue
        if value not in (b'continue', b'end'):
            raise ValueError('unknown FFmpeg progress state')
        for required in (b'frame', b'dup_frames', b'drop_frames'):
            if required not in current:
                raise ValueError('incomplete FFmpeg progress block')
        block = FFmpegProgress(
            _progress_counter(current[b'frame'], 'frame'),
            _progress_counter(current.get(b'out_time_us', b'0'), 'out_time_us'),
            _progress_counter(current[b'dup_frames'], 'dup_frames'),
            _progress_counter(current[b'drop_frames'], 'drop_frames'),
            current.get(b'speed', b'').decode('utf-8', 'replace'), value == b'end')
        if blocks and any(getattr(block, field) < getattr(blocks[-1], field)
                          for field in ('frame', 'out_time_us', 'dup_frames', 'drop_frames')):
            raise ValueError('FFmpeg progress counter regression')
        blocks.append(block)
        current = {}
        terminal = block.terminal
    if terminal and (current or suffix_line):
        raise ValueError('FFmpeg progress data follows terminal block')
    if current:
        consumed_incomplete.extend(key + b'=' + value for key, value in current.items())
    if suffix_line:
        consumed_incomplete.append(suffix_line)
    suffix = b'\n'.join(consumed_incomplete)
    if suffix:
        suffix += b'\n' if raw.endswith(b'\n') and not suffix_line else b''
    return blocks, suffix


def analyze_pts(pts_seconds: list[float], *, requested_fps: int,
                interval_start: float, interval_end: float,
                thresholds: CadenceThresholds) -> dict:
    """Measure source timestamps inside one portable marker-bounded interval."""
    if isinstance(requested_fps, bool) or not isinstance(requested_fps, int) or requested_fps <= 0:
        raise ValueError('requested FPS must be a positive integer')
    if not isinstance(thresholds, CadenceThresholds):
        raise TypeError('cadence thresholds must be CadenceThresholds')
    if any(isinstance(value, bool) or not isinstance(value, (int, float))
           or not math.isfinite(value) or value < 0 for value in (interval_start, interval_end)):
        raise ValueError('interval bounds must be finite nonnegative numbers')
    if interval_end <= interval_start:
        raise ValueError('cadence interval end must follow start')
    if len(pts_seconds) < 2:
        raise ValueError('cadence analysis requires at least two frames')
    pts = [float(value) for value in pts_seconds]
    if any(not math.isfinite(value) or value < 0 for value in pts):
        raise ValueError('PTS values must be finite and nonnegative')
    if any(right <= left for left, right in zip(pts, pts[1:])):
        raise ValueError('PTS values must be strictly increasing')
    selected = [value for value in pts if interval_start <= value <= interval_end]
    if len(selected) < 2:
        raise ValueError('cadence interval contains fewer than two frames')
    gaps = [right - left for left, right in zip(selected, selected[1:])]
    span = selected[-1] - selected[0]
    effective = len(gaps) / span
    # Marker boundaries need not fall on frame PTS. Count the slots spanned by
    # the first and last included frames so partial boundary cells do not become
    # synthetic missing frames.
    expected_slots = max(1, int(round(span * requested_fps)))
    missing_slots = max(0, expected_slots - len(gaps))
    drop_ratio = missing_slots / expected_slots
    ordered = sorted(gaps)
    percentile = lambda ratio: ordered[min(len(ordered) - 1, max(0, math.ceil(len(ordered) * ratio) - 1))]
    histogram: dict[str, int] = {}
    for gap in gaps:
        tick = str(max(1, int(round(gap * requested_fps))))
        histogram[tick] = histogram.get(tick, 0) + 1
    maximum = max(gaps)
    passed = (effective >= requested_fps * thresholds.minimum_rate_ratio
              and drop_ratio <= thresholds.maximum_drop_ratio
              and maximum <= thresholds.maximum_gap_seconds)
    return {
        'status': 'passed' if passed else 'failed',
        'start_capture_seconds': interval_start, 'end_capture_seconds': interval_end,
        'first_included_pts': selected[0], 'last_included_pts': selected[-1],
        'frame_count': len(selected), 'inter_frame_count': len(gaps), 'span_seconds': span,
        'effective_fps': effective, 'requested_slot_count': expected_slots,
        'missing_slots': missing_slots, 'missing_or_dropped_ratio': drop_ratio,
        'included_pts_seconds': selected,
        'interval_histogram_ticks': histogram, 'p95_gap_seconds': percentile(.95),
        'p99_gap_seconds': percentile(.99), 'maximum_gap_seconds': maximum,
        'gaps_above_ms': {str(limit): sum(gap > limit / 1000 for gap in gaps)
                          for limit in (25, 50, 100)},
        'thresholds': {'minimum_rate_ratio': thresholds.minimum_rate_ratio,
                       'maximum_drop_ratio': thresholds.maximum_drop_ratio,
                       'maximum_gap_seconds': thresholds.maximum_gap_seconds},
    }


def normalize_display_screen_zero(display: str) -> str:
    match = _DISPLAY_SCREEN_ZERO.fullmatch(display)
    if match is None:
        raise ValueError('Gamescope capture requires a private X11 display on screen zero')
    return f':{int(match.group(1))}.0'


class ProbeCleanupError(subprocess.SubprocessError):
    """The exact FFprobe child survived all bounded owner cleanup attempts."""
    def __init__(self, process, command, detail: str):
        super().__init__(detail)
        self.process = process
        self.command = list(command)
        self.pid = getattr(process, 'pid', None)
        self.pid_start = getattr(process, 'pid_start', None)
        if not self.pid_start and type(self.pid) is int:
            from .session import pid_start
            self.pid_start = pid_start(self.pid)
        self.signal_errors: list[str] = []
        self.reaped = False


def _bounded_probe_cleanup(process, command) -> None:
    signal_errors = []
    for _ in range(2):
        try:
            process.kill()
        except ProcessLookupError:
            pass
        except Exception as error:  # signal failures never skip the bounded reap attempt
            signal_errors.append(f'{type(error).__name__}: {error}')
        try:
            process.wait(timeout=2)
            if signal_errors:
                failure = ProbeCleanupError(process, command, 'ffprobe signaling failed before bounded reap')
                failure.signal_errors = signal_errors
                failure.reaped = True
                raise failure
            return
        except subprocess.TimeoutExpired:
            continue
    failure = ProbeCleanupError(process, command, 'ffprobe child survived two bounded kill/reap attempts')
    failure.signal_errors = signal_errors
    raise failure


def probe_tool_identity(command: str) -> dict:
    if not isinstance(command, str) or not command:
        raise ValueError('ffprobe command must be a nonempty string')
    located = shutil.which(command)
    if located is None:
        raise ValueError('configured ffprobe executable was not found')
    resolved = Path(located).resolve(strict=True)
    if not stat.S_ISREG(resolved.stat().st_mode):
        raise ValueError('configured ffprobe executable is not a regular file')
    return {'command': command, 'resolved_path': str(resolved), 'sha256': sha256(resolved)}


def _bounded_probe_output(command: list[str], *, pass_fds: tuple[int, ...], maximum_bytes: int,
                          popen: Callable[..., subprocess.Popen], monotonic: Callable[[], float],
                          sleep: Callable[[float], None],
                          deadline_seconds: float = PROBE_DEADLINE_BASE_SECONDS) -> bytes:
    """Incrementally read one FFprobe child while enforcing hard time and byte bounds."""
    if (not isinstance(pass_fds, tuple) or any(type(fd) is not int or fd < 3 for fd in pass_fds)
            or len(set(pass_fds)) != len(pass_fds)):
        raise ValueError('ffprobe inherited descriptors must be distinct nonstandard integers')
    if (isinstance(deadline_seconds, bool) or not isinstance(deadline_seconds, (int, float))
            or not math.isfinite(deadline_seconds) or not 0 < deadline_seconds <= PROBE_DEADLINE_MAX_SECONDS):
        raise ValueError('ffprobe deadline must be positive, finite, and within the hard maximum')
    process = popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, pass_fds=pass_fds)
    # Retain the exact process-generation identity before any error path can reap it.
    if type(getattr(process, 'pid', None)) is int and not getattr(process, 'pid_start', None):
        from .session import pid_start
        process.pid_start = pid_start(process.pid)
    if process.stdout is None:
        if process.poll() is None:
            _bounded_probe_cleanup(process, command)
        raise OSError('ffprobe stdout pipe was not created')
    raw = bytearray()
    deadline = monotonic() + deadline_seconds
    os.set_blocking(process.stdout.fileno(), False)
    try:
        while True:
            eof = False
            while True:
                try:
                    remaining = maximum_bytes + 1 - len(raw)
                    block = os.read(process.stdout.fileno(), min(64 * 1024, remaining))
                except BlockingIOError:
                    break
                if not block:
                    eof = True
                    break
                raw.extend(block)
                if len(raw) > maximum_bytes:
                    raise ValueError('ffprobe output exceeds bounded size')
            status = process.poll()
            if status:
                raise subprocess.CalledProcessError(status, command)
            if status is not None and eof:
                break
            if monotonic() >= deadline:
                raise subprocess.TimeoutExpired(command, deadline_seconds)
            sleep(.01)
    except BaseException:
        if process.poll() is None:
            _bounded_probe_cleanup(process, command)
        raise
    finally:
        process.stdout.close()
    if len(raw) > maximum_bytes:
        raise ValueError('ffprobe output exceeds bounded size')
    return bytes(raw)


def probe_frame_pts(path: Path, ffprobe: str = 'ffprobe', *, pass_fds: tuple[int, ...] = (),
                    popen: Callable[..., subprocess.Popen] = subprocess.Popen,
                    monotonic: Callable[[], float] = time.monotonic,
                    sleep: Callable[[float], None] = time.sleep,
                    deadline_seconds: float = PROBE_DEADLINE_BASE_SECONDS) -> list[float]:
    """Incrementally read FFprobe output while enforcing hard time and byte bounds."""
    command = [str(ffprobe), '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', str(path)]
    raw = _bounded_probe_output(command, pass_fds=pass_fds, maximum_bytes=MAX_CANONICAL_PTS_BYTES,
                                popen=popen, monotonic=monotonic, sleep=sleep,
                                deadline_seconds=deadline_seconds)
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get('frames'), list):
        raise ValueError('ffprobe PTS output lacks a frames array')
    if len(data['frames']) > MAX_CANONICAL_PTS_FRAMES:
        raise ValueError('ffprobe PTS frame count exceeds bounded size')
    values = [float(frame['best_effort_timestamp_time']) for frame in data['frames']]
    if len(values) > MAX_CANONICAL_PTS_FRAMES:
        raise ValueError('ffprobe PTS frame count exceeds bounded size')
    if any(not math.isfinite(value) for value in values):
        raise ValueError('ffprobe PTS contains a nonfinite timestamp')
    # The pure analyzer provides the strict timestamp validation.
    return values


def probe_frame_content(path: Path, ffprobe: str = 'ffprobe', *, pass_fds: tuple[int, ...] = (),
                        popen: Callable[..., subprocess.Popen] = subprocess.Popen,
                        monotonic: Callable[[], float] = time.monotonic,
                        sleep: Callable[[float], None] = time.sleep,
                        deadline_seconds: float = PROBE_DEADLINE_BASE_SECONDS,
                        index_policy: dict | None = None, height: int | None = None) -> list[dict]:
    """Decode every frame through lavfi signalstats; the input is only an inherited descriptor path.

    When ``index_policy`` (``{'bits', 'cell', 'inset'}``) is given, the same
    movie is additionally split into one crop per index tile (both regions;
    see ``display_backends.pattern_index_cell_crops``) and each crop's own
    signalstats YAVG is read. ``split`` never drops or reorders frames, so
    every stream sees the identical sequence of source frames in lockstep;
    ffprobe emits them frame-major (all streams for frame 0, then frame 1,
    ...), which is asserted below via each entry's own ``stream_index``
    rather than assumed.
    """
    if not _FD_PATH.fullmatch(str(path)):
        # The filtergraph is never built from an arbitrary path that could need escaping.
        raise ValueError('content probe requires a /proc/self/fd/N descriptor path')
    tags = ','.join('lavfi.signalstats.' + key.upper() for key in CONTENT_ROW_KEYS)
    crops = (pattern_index_cell_crops(height, bits=index_policy['bits'], cell=index_policy['cell'],
                                      inset=index_policy['inset']) if index_policy is not None else [])
    if crops:
        stream_count = len(crops) + 1
        pads = ''.join(f'[o{i}]' for i in range(stream_count))
        chain = [f'movie={path},split={stream_count}{pads}', '[o0]signalstats[out0]']
        for position, (_, x0, y0, w, h) in enumerate(crops):
            chain.append(f'[o{position + 1}]crop={w}:{h}:{x0}:{y0},signalstats[out{position + 1}]')
        command = [str(ffprobe), '-v', 'error', '-f', 'lavfi', '-i', ';'.join(chain),
                   '-show_entries', 'frame=stream_index:frame_tags=' + tags, '-of', 'json']
    else:
        stream_count = 1
        command = [str(ffprobe), '-v', 'error', '-f', 'lavfi', '-i', f'movie={path},signalstats',
                   '-show_entries', 'frame_tags=' + tags, '-of', 'json']
    raw = _bounded_probe_output(command, pass_fds=pass_fds, maximum_bytes=MAX_CONTENT_PROBE_BYTES,
                                popen=popen, monotonic=monotonic, sleep=sleep,
                                deadline_seconds=deadline_seconds)
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get('frames'), list):
        raise ValueError('ffprobe signalstats output lacks a frames array')
    if len(data['frames']) > MAX_CANONICAL_PTS_FRAMES * stream_count:
        raise ValueError('ffprobe signalstats frame count exceeds bounded size')

    def row_from_tags(values) -> dict:
        if not isinstance(values, dict):
            raise ValueError('ffprobe signalstats frame lacks tags')
        row = {}
        for key in CONTENT_ROW_KEYS:
            text = values.get('lavfi.signalstats.' + key.upper())
            if not isinstance(text, str):
                raise ValueError('ffprobe signalstats frame lacks ' + key.upper())
            value = float(text)
            if not math.isfinite(value) or value < 0:
                raise ValueError('ffprobe signalstats value is not finite and nonnegative')
            row[key] = value
        return row

    if not crops:
        return [row_from_tags(frame.get('tags') if isinstance(frame, dict) else None)
               for frame in data['frames']]

    def cell_value(values) -> float:
        text = values.get('lavfi.signalstats.YAVG') if isinstance(values, dict) else None
        if not isinstance(text, str):
            raise ValueError('ffprobe signalstats crop frame lacks YAVG')
        value = float(text)
        if not math.isfinite(value) or value < 0:
            raise ValueError('ffprobe signalstats value is not finite and nonnegative')
        return value

    if len(data['frames']) % stream_count:
        raise ValueError('ffprobe signalstats output is not frame-aligned across index streams')
    frame_count = len(data['frames']) // stream_count
    if frame_count > MAX_CANONICAL_PTS_FRAMES:
        raise ValueError('ffprobe signalstats frame count exceeds bounded size')
    cells_per_region = index_policy['bits'] + 1
    rows = []
    for position in range(frame_count):
        entries = data['frames'][position * stream_count:(position + 1) * stream_count]
        if [entry.get('stream_index') if isinstance(entry, dict) else None
                for entry in entries] != list(range(stream_count)):
            raise ValueError('ffprobe signalstats output is not frame-aligned across index streams')
        row = row_from_tags(entries[0].get('tags'))
        cell_values = [cell_value(entry.get('tags')) for entry in entries[1:]]
        row['index_top'] = cell_values[:cells_per_region]
        row['index_bottom'] = cell_values[cells_per_region:]
        rows.append(row)
    return rows


def _xwininfo_fields(text: str) -> tuple[int, dict[str, str], bool]:
    header = next((line for line in text.splitlines() if 'Window id:' in line), None)
    if header is None:
        raise RuntimeError('capture geometry query response malformed')
    identifier = header.split('Window id:', 1)[1].split()[0]
    fields = {}
    for line in text.splitlines():
        if ':' in line and 'Window id:' not in line:
            key, value = line.split(':', 1)
            fields[key.strip()] = value.strip()
    return int(identifier, 16), fields, '(the root window)' in header


def parse_xwininfo_geometry(window_text: str, root_text: str, *, window_id: str,
                            lease_extent: tuple[int, int]) -> dict:
    """Turn `xwininfo -id` and `xwininfo -root` output into shm.c precondition evidence."""
    try:
        identifier, window, window_is_root = _xwininfo_fields(window_text)
        _, root, root_is_root = _xwininfo_fields(root_text)
        if identifier != int(window_id, 16) or window_is_root or not root_is_root:
            raise RuntimeError('capture geometry query described a foreign window')
        return geometry_precondition(
            window_id=window_id, map_state=window['Map State'],
            absolute_origin=[int(window['Absolute upper-left X']), int(window['Absolute upper-left Y'])],
            size=[int(window['Width']), int(window['Height'])],
            border_width=int(window['Border width']),
            root_size=[int(root['Width']), int(root['Height'])], lease_extent=list(lease_extent))
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise RuntimeError('capture geometry query response malformed') from error


def xwayland_rootless(lease) -> bool | None:
    """True/False from the admitted Xwayland argv; None when the lease cannot prove it."""
    access = getattr(lease, 'xwayland_access', None)
    try:
        cmdline = access['candidate']['cmdline']
    except (KeyError, TypeError):
        return None
    if not isinstance(cmdline, list) or not all(isinstance(item, str) for item in cmdline):
        return None
    return '-rootless' in cmdline


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
                 marker_pattern: str = CREATIVE_MARKER,
                 named_markers: dict[str, str] | None = None,
                 cadence_start_marker: str | None = None,
                 cadence_end_marker: str | None = None,
                 marker_poll_interval: float = .1):
        if isinstance(fps, bool) or not isinstance(fps, int) or not 1 <= fps <= 120:
            raise ValueError('capture FPS must be an integer in [1,120]')
        self.run_dir = Path(run_dir)
        self.ffmpeg, self.fps = ffmpeg, fps
        self.pattern = re.compile(marker_pattern)
        configured = dict(named_markers or {'effect_start': marker_pattern})
        self.named_patterns = {name: re.compile(pattern) for name, pattern in configured.items()}
        if (cadence_start_marker is None) != (cadence_end_marker is None):
            raise ValueError('cadence start and end markers must be configured together')
        if cadence_start_marker is not None and (cadence_start_marker not in configured
                                                  or cadence_end_marker not in configured):
            raise ValueError('cadence endpoint is not a configured marker')
        self.cadence_start_marker = cadence_start_marker
        self.cadence_end_marker = cadence_end_marker
        if not math.isfinite(marker_poll_interval) or marker_poll_interval <= 0:
            raise ValueError('marker poll interval must be positive and finite')
        self.marker_poll_interval = marker_poll_interval
        self.process = None
        self.log = None
        self.started = None
        self.marker = None
        self.markers: dict[str, dict] = {}
        self.marker_duplicates: list[str] = []
        self._marker_sequence = 0
        self._last_observe_monotonic = None
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
        byte_end = self._offset - len(self._pending) - sum(len(raw) + 1 for raw in lines)
        for raw in lines:
            byte_end += len(raw) + 1
            line = raw.decode('utf-8', 'replace')
            if self.marker is None and self.pattern.search(line):
                self.marker = {'line': line, 'detected_monotonic': now,
                               'capture_seconds': max(0.0, now - self.started),
                               'selection_clock': 'monotonic log detection, 100ms poll; capture startup latency not calibrated'}
            for name, pattern in self.named_patterns.items():
                if not pattern.search(line):
                    continue
                if name in self.markers:
                    if name not in self.marker_duplicates:
                        self.marker_duplicates.append(name)
                    continue
                self._marker_sequence += 1
                self.markers[name] = {
                    'name': name, 'pattern': pattern.pattern, 'line': line,
                    'native_log_byte_end': byte_end, 'detected_monotonic': now,
                    'capture_seconds': max(0.0, now - self.started),
                    'poll_interval_ms': int(round(self.marker_poll_interval * 1000)),
                    'uncertainty_ms': int(round(self.marker_poll_interval * 1000)),
                    'sequence': self._marker_sequence,
                }
        self._last_observe_monotonic = now

    def _marker_order_status(self) -> str:
        names = [name for name in self.named_patterns if name != 'effect_start']
        found = [self.markers[name] for name in names if name in self.markers]
        if len(found) != len(names):
            return 'incomplete'
        if any(right['native_log_byte_end'] <= left['native_log_byte_end']
               or right['sequence'] <= left['sequence']
               or right['capture_seconds'] < left['capture_seconds']
               for left, right in zip(found, found[1:])):
            return 'out_of_order'
        return 'ordered'

    def _watch(self, native_log: Path) -> None:
        while not self._stop.wait(self.marker_poll_interval):
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
    """Authorize an immutable game window, then capture exactly that verified window."""

    def __init__(self, run_dir: Path, *, verifier: Callable[[OwnedWindow], OwnedWindow],
                 lease, ffmpeg: str = 'ffmpeg', fps: int = 60,
                 marker_pattern: str = CREATIVE_MARKER, watch_interval: float = .25,
                 named_markers: dict[str, str] | None = None,
                 cadence_start_marker: str | None = None,
                 cadence_end_marker: str | None = None,
                 popen: Callable[..., object] = subprocess.Popen,
                 run: Callable[..., object] = subprocess.run,
                 monotonic: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep,
                 startup_timeout: float = 5.0, ffprobe: str = 'ffprobe',
                 pts_probe: Callable[[Path, str], list[float]] | None = None,
                 content_probe: Callable[..., list[dict]] | None = None,
                 content_policy: str = 'game-capture-v1', capture_target: str = 'window',
                 inherited_fds: tuple[int, ...] = ()):
        if fps != CADENCE_POLICY['requested_fps']:
            raise ValueError('Gamescope cadence policy requires 60 FPS capture')
        if capture_target not in ('window', 'root'):
            raise ValueError('capture target must be window (root is refused at start)')
        if content_policy not in CONTENT_POLICIES:
            raise ValueError('unknown content policy; choose one from the trusted table')
        super().__init__(run_dir, ffmpeg=ffmpeg, fps=fps, marker_pattern=marker_pattern,
                         named_markers=named_markers,
                         cadence_start_marker=cadence_start_marker,
                         cadence_end_marker=cadence_end_marker)
        if watch_interval < .25:
            raise ValueError('window watch interval must be at least 250 ms')
        if not math.isfinite(startup_timeout) or startup_timeout <= 0:
            raise ValueError('startup timeout must be positive and finite')
        self._verifier, self._lease = verifier, lease
        self._watch_interval, self._popen, self._run = watch_interval, popen, run
        self._monotonic, self._sleep, self._startup_timeout = monotonic, sleep, startup_timeout
        if (not isinstance(inherited_fds, tuple) or len(set(inherited_fds)) != len(inherited_fds)
                or any(type(fd) is not int or fd < 3 for fd in inherited_fds)):
            raise ValueError('inherited descriptors must be distinct nonstandard integers')
        # The live lock descriptor passes to every child this recorder starts:
        # FFmpeg, both FFprobe probes, and every xwininfo geometry query.
        self._inherited_fds = inherited_fds
        self.ffprobe = ffprobe
        self._probe_frames = 0
        self._pts_probe = pts_probe or self._default_pts_probe
        self._content_probe = content_probe or self._default_content_probe
        self._content_policy = content_policy
        self._capture_target = capture_target
        self._frozen_geometry: dict | None = None
        self.target = None
        self.failure = None
        self._stopping = False
        self._checks = 0
        self._failure_lock = threading.Lock()
        self._ffmpeg_log_offset = 0
        self._ffmpeg_log_tail = b''
        self._progress_offset = 0
        self._progress_pending = b''
        self._progress_blocks: list[FFmpegProgress] = []
        self._progress_samples: list[dict] = []
        self.route_interval: tuple[float, float] | None = None
        self._cadence = None
        self._native_log: Path | None = None
        self._capture_stage: Path | None = None
        self._capture_stage_fd: int | None = None
        self._run_dir_fd: int | None = None
        self._progress_fd: int | None = None
        self._diagnostic_identity: dict[Path, tuple[int, int]] = {}

    def _inherit(self, pass_fds: tuple[int, ...] = ()) -> tuple[int, ...]:
        return tuple(dict.fromkeys((*pass_fds, *self._inherited_fds)))

    def _default_pts_probe(self, path: Path, executable: str) -> list[float]:
        return probe_frame_pts(path, executable, pass_fds=self._inherit(),
                               deadline_seconds=probe_deadline_seconds(self._probe_frames))

    def _default_content_probe(self, path: Path, executable: str, *, pass_fds: tuple[int, ...] = ()) -> list[dict]:
        policy = CONTENT_POLICIES[self._content_policy]
        index_policy = ({'bits': policy['index_bits'], 'cell': policy['index_cell'],
                         'inset': policy['index_inset']} if 'index_bits' in policy else None)
        return probe_frame_content(path, executable, pass_fds=self._inherit(pass_fds),
                                   deadline_seconds=probe_deadline_seconds(self._probe_frames),
                                   index_policy=index_policy, height=self._lease.height)

    def _query(self, command: list[str], **kwargs):
        if self._inherited_fds:
            kwargs['pass_fds'] = self._inherit(tuple(kwargs.get('pass_fds', ())))
        return self._run(command, **kwargs)

    def set_route_interval(self, start: float, end: float) -> None:
        if not all(math.isfinite(value) and value >= 0 for value in (start, end)) or end <= start:
            raise ValueError('route interval must be finite, nonnegative, and increasing')
        self.route_interval = (start, end)

    @staticmethod
    def _progress_sample_receipt(sample: dict) -> dict:
        progress = sample['progress']
        return {'capture_seconds': sample['capture_seconds'], 'frame': progress.frame,
                'out_time_us': progress.out_time_us, 'dup_frames': progress.dup_frames,
                'drop_frames': progress.drop_frames}

    def _finalize_cadence(self, terminal: FFmpegProgress | None) -> dict:
        thresholds = CadenceThresholds(
            minimum_rate_ratio=CADENCE_POLICY['minimum_rate_ratio'],
            maximum_drop_ratio=CADENCE_POLICY['maximum_drop_ratio'],
            maximum_gap_seconds=CADENCE_POLICY['maximum_gap_seconds'])
        base = {
            'status': 'failed', 'requested_fps': self.fps,
            'policy': dict(CADENCE_POLICY),
            'policy_scope': {'rate_gap_missing': 'acceptance_interval',
                'ffmpeg_drop_delta': 'acceptance_interval', 'ffmpeg_duplicates': 'whole_capture'},
            'pts_artifact': None,
            'probe_tool': None,
            'marker_configuration': {'version': 1,
                'required_order': [name for name in self.named_patterns if name != 'effect_start'],
                'patterns': {name: pattern for name, pattern in self.named_patterns.items()
                             if name != 'effect_start'},
                'optional_markers': ['effect_start'],
                'acceptance_pair': [self.cadence_start_marker, self.cadence_end_marker]},
            'thresholds': {'minimum_rate_ratio': thresholds.minimum_rate_ratio,
                           'maximum_drop_ratio': thresholds.maximum_drop_ratio,
                           'maximum_gap_seconds': thresholds.maximum_gap_seconds},
            'acceptance_interval': {'start_marker': self.cadence_start_marker,
                                    'end_marker': self.cadence_end_marker},
            'whole_capture': {}, 'intervals': [], 'failures': [], 'content': None,
            'distinct_game_frames': {'status': 'unvalidated', 'method': None},
            'terminal_progress': None if terminal is None else {
                'frame': terminal.frame, 'out_time_us': terminal.out_time_us,
                'dup_frames': terminal.dup_frames, 'drop_frames': terminal.drop_frames},
        }
        if terminal is None:
            base['failures'].append('capture_cadence_failed: terminal progress diagnostics unavailable')
            return base
        if self.cadence_start_marker is None or self.cadence_end_marker is None:
            base['failures'].append('capture_markers_incomplete: cadence endpoints not configured')
            return base
        missing = [name for name in (self.cadence_start_marker, self.cadence_end_marker)
                   if name not in self.markers]
        if missing:
            base['failures'].append('capture_markers_incomplete: ' + ', '.join(missing))
            return base
        duplicate_required = [name for name in self.marker_duplicates if name != 'effect_start']
        if duplicate_required:
            base['failures'].append('capture_markers_incomplete: duplicate marker ' + duplicate_required[0])
            return base
        start_marker = self.markers[self.cadence_start_marker]
        end_marker = self.markers[self.cadence_end_marker]
        start = start_marker['capture_seconds']
        end = end_marker['capture_seconds']
        if self._marker_order_status() != 'ordered':
            base['failures'].append('capture_markers_incomplete: configured marker order changed')
            return base
        if end == start:
            # Lines observed in one poll retain byte order.  Use the conservative
            # adjacent uncertainty bounds rather than inventing equal event times.
            start = max(0.0, start - start_marker['uncertainty_ms'] / 1000)
            end = end_marker['capture_seconds']
        required_names = [name for name in self.named_patterns if name != 'effect_start']
        absent = [name for name in required_names if name not in self.markers]
        if absent:
            base['failures'].append('capture_markers_incomplete: ' + ', '.join(absent))
            return base
        ordered = sorted(self.markers.values(), key=lambda marker: marker['capture_seconds'])
        configured_order = required_names
        actual_order = [marker['name'] for marker in ordered if marker['name'] in configured_order]
        if actual_order != configured_order and len(set(marker['capture_seconds'] for marker in ordered)) == len(ordered):
            base['failures'].append('capture_markers_incomplete: configured marker order changed')
            return base
        media = self.run_dir / 'continuous.mp4'
        try:
            tool_identity = probe_tool_identity(self.ffprobe)
            # The terminal FFmpeg frame count sizes the PTS probe's deadline.
            self._probe_frames = max(0, int(terminal.frame))
            pts = self._pts_probe(media, self.ffprobe)
            if not 2 <= len(pts) <= MAX_CANONICAL_PTS_FRAMES:
                raise ValueError('canonical PTS frame count is outside bounded range')
            master_sha = sha256(media)
            raw_receipt = {'schema': 1,
                'master': {'path': str(media.resolve()), 'sha256': master_sha},
                'probe': {**tool_identity,
                          'method': 'ffprobe-best-effort-timestamp-time-v1'},
                'frame_count': len(pts), 'pts_seconds': pts}
            encoded = (json.dumps(raw_receipt, sort_keys=True, separators=(',', ':')) + '\n').encode()
            if len(encoded) > MAX_CANONICAL_PTS_BYTES:
                raise ValueError('canonical PTS artifact exceeds bounded size')
            pts_path = self.run_dir / 'ffprobe-cadence.json'
            pts_fd = os.open(pts_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                with os.fdopen(pts_fd, 'wb', closefd=False) as stream:
                    stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
            finally:
                os.close(pts_fd)
            base['pts_artifact'] = {**artifact(pts_path), 'master_sha256': master_sha,
                                    'frame_count': len(pts)}
            base['probe_tool'] = tool_identity
            whole = analyze_pts(pts, requested_fps=self.fps, interval_start=pts[0],
                                interval_end=pts[-1], thresholds=thresholds)
            acceptance = analyze_pts(pts, requested_fps=self.fps, interval_start=start,
                                     interval_end=end, thresholds=thresholds)
        except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
            base['failures'].append(f'capture_cadence_failed: {type(error).__name__}: {error}')
            return base
        expected = acceptance['requested_slot_count']
        before = [sample for sample in self._progress_samples
                  if sample['capture_seconds'] <= start]
        after = [sample for sample in self._progress_samples
                 if sample['capture_seconds'] >= end]
        interval_progress = {'status': 'unavailable', 'dup_frames': None, 'drop_frames': None}
        if before and after:
            left, right = before[-1], after[0]
            interval_progress = {
                'status': 'bounded',
                'dup_frames': right['progress'].dup_frames - left['progress'].dup_frames,
                'drop_frames': right['progress'].drop_frames - left['progress'].drop_frames,
                'start_sample': self._progress_sample_receipt(left),
                'end_sample': self._progress_sample_receipt(right),
            }
        interval_drops = interval_progress['drop_frames'] if interval_progress['status'] == 'bounded' else 0
        missing_or_dropped = max(acceptance['missing_slots'], interval_drops)
        acceptance.update(
            name=f'{self.cadence_start_marker}_to_{self.cadence_end_marker}',
            start_marker=self.cadence_start_marker, end_marker=self.cadence_end_marker,
            uncertainty_ms=200, crosses_boundary_uncertainty=True,
            ffmpeg=interval_progress,
            missing_or_dropped_slots=missing_or_dropped,
            missing_or_dropped_ratio=missing_or_dropped / expected)
        acceptance_passed = (acceptance['status'] == 'passed' and terminal.dup_frames == 0
            and interval_progress['status'] == 'bounded' and interval_progress['dup_frames'] == 0
            and missing_or_dropped / expected <= thresholds.maximum_drop_ratio)
        acceptance['status'] = 'passed' if acceptance_passed else 'failed'
        # The content gate is evaluated before any cadence verdict can pass.
        content = self._measure_content(media, master_sha, tool_identity, pts,
                                        acceptance['start_capture_seconds'],
                                        acceptance['end_capture_seconds'])
        base['content'] = content
        if content.get('acceptance') is not None:
            base['distinct_game_frames'] = {'status': 'measured', 'method': CONTENT_METHOD,
                                            'distinct_ratio': content['acceptance']['distinct_ratio']}
        intervals = [acceptance]
        marker_sequence = [self.markers[name] for name in configured_order]
        for left, right in zip(marker_sequence, marker_sequence[1:]):
            if (left['name'], right['name']) == (self.cadence_start_marker, self.cadence_end_marker):
                continue
            interval_left = left['capture_seconds']; interval_right = right['capture_seconds']
            if interval_left == interval_right:
                interval_left = max(0.0, interval_left - left['uncertainty_ms'] / 1000)
            if interval_left >= interval_right:
                continue
            try:
                interval = analyze_pts(pts, requested_fps=self.fps,
                    interval_start=interval_left, interval_end=interval_right,
                    thresholds=thresholds)
            except ValueError:
                continue
            interval.update(name=f"{left['name']}_to_{right['name']}",
                            start_marker=left['name'], end_marker=right['name'],
                            uncertainty_ms=200, crosses_boundary_uncertainty=True)
            intervals.append(interval)
        failures = [] if acceptance_passed else ['capture_cadence_failed: acceptance interval missed thresholds']
        failures.extend(content['failures'])
        base.update(status='passed' if not failures else 'failed', whole_capture=whole,
                    intervals=intervals, failures=failures)
        if self.route_interval is not None:
            try:
                base['route_interval'] = analyze_pts(pts, requested_fps=self.fps,
                    interval_start=self.route_interval[0], interval_end=self.route_interval[1],
                    thresholds=thresholds)
            except ValueError as error:
                base['route_interval'] = {'status': 'unavailable', 'error': str(error)}
        return base

    def _measure_content(self, media: Path, master_sha: str, tool_identity: dict, pts: list[float],
                         interval_start: float, interval_end: float) -> dict:
        policy = CONTENT_POLICIES[self._content_policy]
        try:
            descriptor = os.open(media, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                digest = hashlib.sha256()
                while block := os.read(descriptor, 1024 * 1024):
                    digest.update(block)
                if digest.hexdigest() != master_sha:
                    raise ValueError('master changed before the content probe')
                self._probe_frames = len(pts)
                rows = self._content_probe(Path(f'/proc/self/fd/{descriptor}'), self.ffprobe,
                                           pass_fds=(descriptor,))
            finally:
                os.close(descriptor)
            evaluation = evaluate_content(rows, pts, interval_start, interval_end, policy)
            encoded = (json.dumps({'schema': 1,
                'master': {'path': str(media.resolve()), 'sha256': master_sha},
                'probe': {**tool_identity, 'method': CONTENT_METHOD},
                'frame_count': len(rows), 'frames': rows},
                sort_keys=True, separators=(',', ':')) + '\n').encode()
            path = self.run_dir / 'ffprobe-content.json'
            artifact_fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                with os.fdopen(artifact_fd, 'wb', closefd=False) as stream:
                    stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
            finally:
                os.close(artifact_fd)
            return {'artifact': {**artifact(path), 'master_sha256': master_sha, 'frame_count': len(rows)},
                    **evaluation}
        except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
            return {'artifact': None, 'status': 'failed', 'method': CONTENT_METHOD, 'policy': dict(policy),
                    'frame_count': None, 'first_frame': None, 'startup': None, 'acceptance': None,
                    'failures': [f'capture_content_failed: {type(error).__name__}: {error}']}

    def _geometry(self, target: OwnedWindow) -> dict:
        """Read the exact window and root geometry that ShmGetImage will check."""
        env = dict(target.environment)
        window = self._query(['xwininfo', '-id', target.window_id], env=env, text=True,
                             capture_output=True, timeout=5, check=False)
        root = self._query(['xwininfo', '-root'], env=env, text=True,
                           capture_output=True, timeout=5, check=False)
        if getattr(window, 'returncode', 1) != 0 or getattr(root, 'returncode', 1) != 0:
            raise RuntimeError('capture geometry query failed')
        return parse_xwininfo_geometry(getattr(window, 'stdout', ''), getattr(root, 'stdout', ''),
                                       window_id=target.window_id,
                                       lease_extent=(self._lease.width, self._lease.height))

    def _binding(self, target: OwnedWindow) -> dict:
        evidence = self._geometry(target)
        if evidence['status'] != 'verified':
            failed = sorted(name for name, passed in evidence['conditions'].items() if not passed)
            raise RuntimeError('capture geometry precondition failed: ' + ', '.join(failed))
        if [target.width, target.height] != evidence['size']:
            raise RuntimeError('authorized window size differs from verified capture geometry')
        if self._frozen_geometry is not None and evidence != self._frozen_geometry:
            raise RuntimeError('capture geometry changed after the pre-exec verification')
        return evidence

    def _scan_ffmpeg_log(self) -> list[str]:
        path = self.run_dir / 'ffmpeg.log'
        try:
            fresh, self._ffmpeg_log_offset = self._read_diagnostic(path, self._ffmpeg_log_offset)
        except OSError as error:
            raise RuntimeError('capture_log_read_failed') from error
        combined = self._ffmpeg_log_tail + fresh
        matches = [token.decode() for token in FORBIDDEN_X11_STARTUP if token in combined]
        overlap = max(len(token) for token in FORBIDDEN_X11_STARTUP) - 1
        self._ffmpeg_log_tail = combined[-overlap:]
        return matches

    def _read_progress(self) -> list[FFmpegProgress]:
        path = self.run_dir / 'ffmpeg-progress.log'
        try:
            fresh, self._progress_offset = self._read_diagnostic(path, self._progress_offset)
        except OSError as error:
            raise RuntimeError('capture_log_read_failed') from error
        blocks, self._progress_pending = parse_progress_blocks(self._progress_pending + fresh)
        if len(self._progress_pending) > MAX_PROGRESS_SUFFIX:
            raise ValueError('FFmpeg progress suffix exceeds bounded size')
        previous = self._progress_blocks[-1] if self._progress_blocks else None
        for block in blocks:
            if previous and any(getattr(block, field) < getattr(previous, field)
                                for field in ('frame', 'out_time_us', 'dup_frames', 'drop_frames')):
                raise ValueError('FFmpeg progress counter regression')
            if previous and previous.terminal:
                raise ValueError('FFmpeg progress follows terminal block')
            self._progress_blocks.append(block); previous = block
            self._progress_samples.append({
                'capture_seconds': max(0.0, self._monotonic() - self.started),
                'progress': block,
            })
        return blocks

    def _read_diagnostic(self, path: Path, offset: int) -> tuple[bytes, int]:
        before = os.stat(path, follow_symlinks=False)
        expected = self._diagnostic_identity.get(path)
        if (not stat.S_ISREG(before.st_mode) or expected != (before.st_dev, before.st_ino)
                or before.st_size < offset):
            raise OSError('capture diagnostic was replaced or truncated')
        length = before.st_size - offset
        if length > MAX_DIAGNOSTIC_READ:
            raise OSError('capture diagnostic growth exceeds bounded read')
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            current = os.fstat(descriptor)
            if (current.st_dev, current.st_ino) != expected:
                raise OSError('capture diagnostic identity changed while opening')
            os.lseek(descriptor, offset, os.SEEK_SET)
            fresh = os.read(descriptor, length)
        finally:
            os.close(descriptor)
        if len(fresh) != length:
            raise OSError('capture diagnostic changed while reading')
        return fresh, offset + length

    def _valid_output(self) -> bool:
        if self._capture_stage_fd is None:
            return False
        try:
            info = os.stat('continuous.mp4', dir_fd=self._capture_stage_fd, follow_symlinks=False)
            return stat.S_ISREG(info.st_mode) and info.st_nlink == 1
        except OSError:
            return False

    def _publish_output(self) -> None:
        if self._capture_stage_fd is None or self._run_dir_fd is None:
            return
        try:
            info = os.stat('continuous.mp4', dir_fd=self._capture_stage_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise RuntimeError('capture output staging identity is invalid')
        try:
            os.link('continuous.mp4', 'continuous.mp4', src_dir_fd=self._capture_stage_fd,
                    dst_dir_fd=self._run_dir_fd, follow_symlinks=False)
        except FileExistsError as error:
            raise RuntimeError('capture output publication target already exists') from error
        os.unlink('continuous.mp4', dir_fd=self._capture_stage_fd)
        published = os.stat('continuous.mp4', dir_fd=self._run_dir_fd, follow_symlinks=False)
        if not stat.S_ISREG(published.st_mode) or (published.st_dev, published.st_ino) != (info.st_dev, info.st_ino):
            raise RuntimeError('capture output publication identity changed')

    def _close_capture_stage(self) -> None:
        if self._progress_fd is not None:
            os.close(self._progress_fd); self._progress_fd = None
        for name in ('_capture_stage_fd', '_run_dir_fd'):
            descriptor = getattr(self, name)
            if descriptor is not None:
                os.close(descriptor); setattr(self, name, None)
        if self._capture_stage is not None:
            try:
                self._capture_stage.rmdir()
            except OSError:
                pass
            self._capture_stage = None

    def _startup_cleanup(self) -> None:
        process = self.process
        cleanup = {'owned_process': process is not None, 'sigint_sent': False,
                   'grace_seconds': 2, 'kill_sent': False, 'kill_wait_seconds': 2,
                   'status': 'not_needed'}
        if process is None or process.poll() is not None:
            if self.failure is not None:
                self.failure['cleanup'] = cleanup
                (self.run_dir / 'capture-failure.json').write_text(json.dumps(self.failure, indent=2) + '\n')
            return
        try:
            process.send_signal(signal.SIGINT)
            cleanup['sigint_sent'] = True
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                cleanup['kill_sent'] = True
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    cleanup['status'] = 'failed'
                    cleanup['error'] = 'owned FFmpeg survived SIGKILL wait'
                else:
                    cleanup['status'] = 'passed'
            else:
                cleanup['status'] = 'passed'
        except OSError as error:
            cleanup['status'] = 'failed'
            cleanup['error'] = f'{type(error).__name__}: {error}'
        if self.failure is not None:
            self.failure['cleanup'] = cleanup
            (self.run_dir / 'capture-failure.json').write_text(json.dumps(self.failure, indent=2) + '\n')
        if cleanup['status'] == 'failed':
            raise RuntimeError(cleanup['error'])

    def _admit_startup(self) -> None:
        deadline = self.started + self._startup_timeout
        while self._monotonic() <= deadline:
            if not self._lease.is_alive():
                self._fail('capture_lease_lost', 'private display lease exited during capture startup'); break
            if self.process.poll() is not None:
                self._fail('capture_process_exited', f'ffmpeg exited {self.process.returncode} before first frame'); break
            try:
                matches = self._scan_ffmpeg_log()
                blocks = self._read_progress()
            except ValueError as error:
                self._fail('capture_progress_malformed', str(error)); break
            except RuntimeError as error:
                self._fail(str(error), 'unable to read capture diagnostics'); break
            if matches:
                self.capture['startup']['shm']['forbidden_matches'].extend(matches)
                self._fail('capture_shm_fallback', 'FFmpeg reported X11 shared-memory fallback'); break
            first = next((block for block in blocks if block.frame >= 1), None)
            if first is not None:
                if not self._valid_output():
                    self._fail('capture_output_invalid', 'first frame did not create a safe run-local output'); break
                now = self._monotonic()
                startup = self.capture['startup']
                startup.update(status='passed', first_frame=first.frame, first_frame_monotonic=now)
                startup['shm']['status'] = 'no_fallback_observed'
                return
            self._sleep(.05)
        if self.failure is None:
            self._fail('capture_start_timeout', 'no complete first-frame progress block within startup timeout')
        self._startup_cleanup()
        raise RuntimeError(self.error)

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
        self.run_dir.mkdir(parents=True, exist_ok=True)
        if self._capture_target != 'window':
            # Rootless Xwayland has a 0x0 root pixmap and an empty root borderClip,
            # so root ShmGetImage returns censored all-zero frames without error.
            rootless = xwayland_rootless(self._lease)
            self.capture = {'status': 'refused', 'requested_target': self._capture_target,
                            'xwayland_rootless': rootless}
            if rootless is False:
                self._fail('capture_target_unsupported',
                           'root capture is not an admitted Gamescope capture target')
            else:
                self._fail('capture_target_rootless_root',
                           'root capture on rootless (or unproven) Xwayland records black frames')
            raise RuntimeError(self.error)
        verified = self._verifier(target)
        if verified != target:
            raise RuntimeError('capture target identity changed before recorder start')
        normalized_display = normalize_display_screen_zero(target.display)
        try:
            initial = self._geometry(target)
        except (RuntimeError, OSError, subprocess.SubprocessError) as error:
            self._fail('capture_geometry_precondition', f'{type(error).__name__}: {error}')
            raise RuntimeError(self.error) from error
        if initial['status'] != 'verified' or [target.width, target.height] != initial['size']:
            self.capture = {'status': 'refused',
                            'geometry_precondition': {'status': 'refused', 'initial': initial}}
            failed = sorted(name for name, passed in initial['conditions'].items() if not passed)
            self._fail('capture_geometry_precondition',
                       'verified window geometry refused: ' + (', '.join(failed) or 'window size'))
            raise RuntimeError(self.error)
        coverage = {'status': 'exact', 'surface_origin': initial['absolute_origin'],
                    'surface_extent': initial['size'], 'source_extent': initial['root_size']}
        self.target = target
        self._native_log = Path(native_log)
        self.started = self._monotonic()
        self.capture = {'status': 'starting'}
        spawn_attempted = False
        try:
            public_output = self.run_dir / 'continuous.mp4'
            if os.path.lexists(public_output):
                raise FileExistsError('capture output publication target already exists')
            self._run_dir_fd = os.open(self.run_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self._capture_stage = Path(tempfile.mkdtemp(prefix='.capture-', dir=self.run_dir))
            os.chmod(self._capture_stage, 0o700)
            self._capture_stage_fd = os.open(self._capture_stage,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            log_path = self.run_dir / 'ffmpeg.log'
            log_fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            self.log = os.fdopen(log_fd, 'ab', buffering=0)
            progress_path = self.run_dir / 'ffmpeg-progress.log'
            self._progress_fd = os.open(progress_path,
                os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            self._diagnostic_identity = {
                log_path: (log_path.stat().st_dev, log_path.stat().st_ino),
                progress_path: (os.fstat(self._progress_fd).st_dev, os.fstat(self._progress_fd).st_ino),
            }
            self._offset = native_log.stat().st_size if native_log.exists() else 0
            command = [self.ffmpeg, '-nostdin', '-y', '-threads', '2', '-nostats',
                       '-stats_period', '0.25', '-progress', f'/proc/self/fd/{self._progress_fd}',
                       '-f', 'x11grab', '-draw_mouse', '0', '-framerate', str(self.fps),
                       '-window_id', target.window_id,
                       '-video_size', f'{self._lease.width}x{self._lease.height}', '-i', normalized_display,
                       '-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28',
                       '-pix_fmt', 'yuv420p', '-threads', '2',
                       f'/proc/self/fd/{self._capture_stage_fd}/continuous.mp4']
            self.capture = {
            'status': 'starting', 'adapter': WINDOW_CAPTURE_ADAPTER,
            'source': {'kind': 'x11-window', 'input': normalized_display, 'window_id': target.window_id,
                       'source_extent': [self._lease.width, self._lease.height], 'drawable': 'window',
                       'details': {'screen': 0, 'draw_mouse': False}},
            'geometry_precondition': {'status': 'pending', 'initial': initial},
            'authorization': {'lease_id': target.lease_id, 'private_display': True,
                'caller_display_reused': False,
                'authorized_surface': {'id': target.window_id, 'pid': target.owner.pid,
                    'pid_start': target.owner.start, 'extent': [target.width, target.height]},
                'coverage': coverage},
            'startup': {'status': 'pending', 'timeout_seconds': self._startup_timeout,
                'started_monotonic': self.started, 'first_frame_monotonic': None, 'first_frame': None,
                'shm': {'status': 'pending',
                    'method': 'absence-of-fallback-through-first-frame-and-continuous-log-watch',
                    'forbidden_matches': []}},
            'command': tuple(command), 'capture_sampling_fps_requested': self.fps,
            'transport': {'version': 1,
                'progress': {'fd': self._progress_fd, 'role': 'regular-progress-file'},
                'output': {'directory_fd': self._capture_stage_fd,
                           'role': 'private-output-directory', 'name': 'continuous.mp4'}},
            'interpolation': False, 'watch': {'interval_ms': int(self._watch_interval * 1000), 'checks': 0},
            'initial_native_log_offset': self._offset,
            'clock_alignment': 'shared-process-monotonic; capture origin is Popen start; first-frame latency retained',
            'diagnostics': {'status': 'pending', 'progress_path': 'ffmpeg-progress.log', 'terminal': None},
            }
            # Re-read immediately before exec: SHM loss latches on the first grab.
            try:
                pre_exec = self._geometry(target)
            except (RuntimeError, OSError, subprocess.SubprocessError) as error:
                self._fail('capture_geometry_precondition', f'pre-exec: {type(error).__name__}: {error}')
                raise
            self.capture['geometry_precondition']['pre_exec'] = pre_exec
            if pre_exec['status'] != 'verified':
                self.capture['geometry_precondition']['status'] = 'refused'
                self._fail('capture_geometry_precondition', 'pre-exec window geometry refused')
                raise RuntimeError(self.error)
            if pre_exec != initial:
                self.capture['geometry_precondition']['status'] = 'refused'
                self._fail('capture_geometry_changed', 'window geometry changed before exec')
                raise RuntimeError(self.error)
            self.capture['geometry_precondition']['status'] = 'verified'
            self._frozen_geometry = pre_exec
            spawn_attempted = True
            self.process = self._popen(command, env=dict(target.environment),
                stdout=subprocess.DEVNULL, stderr=self.log,
                pass_fds=self._inherit((self._capture_stage_fd, self._progress_fd)))
            self._admit_startup()
        except BaseException as error:
            if self.process is None and self.failure is None:
                failure_class = 'capture_process_exited' if spawn_attempted else 'capture_setup_failed'
                self._fail(failure_class, f'capture setup/start failed: {type(error).__name__}: {error}')
                self._startup_cleanup()
            process_live = (self.process is not None and self.process.poll() is None
                            and getattr(self.process, 'returncode', None) is None)
            if not process_live:
                if self.log is not None:
                    self.log.flush(); self.log.close(); self.log = None
                try:
                    self._publish_output()
                except RuntimeError:
                    pass
                self._close_capture_stage()
            raise RuntimeError(self.error) from error
        self.capture['status'] = 'running'
        self._thread = threading.Thread(target=self._watch_window, args=(native_log,), daemon=True)
        self._thread.start()

    def _fail(self, error_class: str, detail: str, last: OwnedWindow | None = None) -> None:
        with self._failure_lock:
            if self.failure is not None:
                return
            elapsed = 0.0 if self.started is None else max(0.0, self._monotonic() - self.started)
            self.failure = {
                'error_class': error_class, 'detail': detail,
                'elapsed_seconds': elapsed,
                'initial_identity': None if self.target is None else self.target.receipt(),
                'last_verified_identity': None if last is None else last.receipt(),
                'ffmpeg_status': None if self.process is None else self.process.poll(),
                'cleanup': {'owned_process': self.process is not None, 'status': 'pending'},
            }
            self.error = f'{error_class}: {detail}'
            self.capture['status'] = 'failed'
            (self.run_dir / 'capture-failure.json').write_text(json.dumps(self.failure, indent=2) + '\n')
            self._stop.set()

    def _watch_window(self, native_log: Path) -> None:
        now = self._monotonic()
        next_marker = now + self.marker_poll_interval
        next_binding = now + self._watch_interval
        wake_interval = min(self.marker_poll_interval, self._watch_interval) / 2
        while not self._stop.wait(wake_interval):
            try:
                if not self._lease.is_alive():
                    self._fail('capture_lease_lost', 'owned Gamescope/readiness process exited'); return
                if self.process.poll() is not None:
                    self._fail('capture_process_exited', f'ffmpeg exited {self.process.returncode}'); return
                now = self._monotonic()
                if now >= next_marker:
                    self.observe(native_log, now)
                    matches = self._scan_ffmpeg_log()
                    if matches:
                        self.capture['startup']['shm']['forbidden_matches'].extend(matches)
                        self._fail('capture_shm_fallback', 'FFmpeg reported X11 shared-memory fallback'); return
                    self._read_progress()
                    next_marker += self.marker_poll_interval
                if now >= next_binding:
                    current = self._verifier(self.target)
                    if current != self.target:
                        self._fail('capture_binding_changed', 'frozen owned-window identity changed', current); return
                    self._binding(current)
                    self._checks += 1
                    self.capture['watch']['checks'] = self._checks
                    next_binding += self._watch_interval
            except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
                if isinstance(error, ValueError):
                    failure = 'capture_progress_malformed'
                elif str(error) == 'capture_log_read_failed':
                    failure = 'capture_log_read_failed'
                else:
                    failure = 'capture_binding_changed'
                self._fail(failure, f'{type(error).__name__}: {error}'); return

    def check(self) -> None:
        if self.failure is not None:
            raise RuntimeError(self.error)

    def stop(self) -> None:
        if self.started is None and self.process is None:
            if self.log is not None:
                self.log.close(); self.log = None
            self._close_capture_stage()
            return
        process = self.process
        if process is not None and process.poll() is not None and self.failure is None:
            self._fail('capture_process_exited', f'ffmpeg exited {process.returncode} before orderly finalization')
        self._stopping = True
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2); self._thread = None
        if self._native_log is not None:
            try:
                self.observe(self._native_log, self._monotonic())
            except OSError as error:
                self._fail('capture_log_read_failed', f'final native-log drain failed: {error}')
        if self.target is not None:
            if not self._lease.is_alive():
                self._fail('capture_lease_lost', 'private display lease exited before finalization')
            else:
                try:
                    current = self._verifier(self.target)
                    if current != self.target:
                        raise RuntimeError('frozen owned-window identity changed')
                    self._binding(current)
                except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
                    self._fail('capture_binding_changed', f'pre-finalize binding check failed: {error}')
        was_live = process is not None and process.poll() is None
        if was_live:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._fail('capture_finalize_timeout', 'owned FFmpeg survived SIGKILL wait')
                    if self.failure is not None:
                        self.failure['cleanup'] = {'owned_process': True, 'status': 'failed',
                                                   'sigint_sent': True, 'kill_sent': True,
                                                   'error': 'owned FFmpeg survived SIGKILL wait'}
                        (self.run_dir / 'capture-failure.json').write_text(
                            json.dumps(self.failure, indent=2) + '\n')
                    raise RuntimeError('owned FFmpeg survived SIGKILL wait')
                self._fail('capture_finalize_timeout', 'recorder did not finalize within 15 seconds')
        if self.target is not None:
            if not self._lease.is_alive():
                self._fail('capture_lease_lost', 'private display lease exited during finalization')
            else:
                try:
                    current = self._verifier(self.target)
                    if current != self.target:
                        raise RuntimeError('frozen owned-window identity changed')
                    self._binding(current)
                except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
                    self._fail('capture_binding_changed', f'post-finalize binding check failed: {error}')
        try:
            matches = self._scan_ffmpeg_log()
            self._read_progress()
            if matches:
                self.capture['startup']['shm']['forbidden_matches'].extend(matches)
                self._fail('capture_shm_fallback', 'FFmpeg reported X11 shared-memory fallback')
        except ValueError as error:
            self._fail('capture_progress_malformed', str(error))
        except RuntimeError as error:
            self._fail(str(error), 'unable to read final capture diagnostics')
        try:
            self._publish_output()
        except RuntimeError as error:
            self._fail('capture_output_invalid', str(error))
        finally:
            self._close_capture_stage()
        terminal = self._progress_blocks[-1] if self._progress_blocks and self._progress_blocks[-1].terminal else None
        if terminal is None and self.failure is None:
            self._fail('capture_cadence_failed', 'terminal FFmpeg progress diagnostics are unavailable')
        if terminal is not None:
            self.capture['diagnostics'] = {'status': 'complete', 'progress_path': 'ffmpeg-progress.log',
                'terminal': {'frame': terminal.frame, 'out_time_us': terminal.out_time_us,
                             'dup_frames': terminal.dup_frames, 'drop_frames': terminal.drop_frames}}
        self.capture['markers'] = copy.deepcopy(list(self.markers.values()))
        self.capture['marker_order'] = {
            'status': self._marker_order_status(),
            'basis': 'strict native-log byte end and sequence; nondecreasing monotonic detection time',
        }
        self._cadence = self._finalize_cadence(terminal)
        if process is not None and process.returncode not in (0, 255) and self.failure is None:
            self._fail('capture_process_exited', f'recorder exited {process.returncode}')
        if self.failure is None:
            self.capture['status'] = 'passed'
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
            'cadence': copy.deepcopy(self._cadence or self._finalize_cadence(None)),
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
    artifacts = encode_clip(source, run_dir, start_seconds=selection['start_seconds'],
        duration_seconds=selection['duration_seconds'], gif_fps=8, ffmpeg=ffmpeg, ffprobe=ffprobe)
    receipt = {'source_video': artifact(source), 'source_geometry': info, **selection,
               'artifacts': artifacts,
               'scope': 'route/media completion only; does not certify all example live obligations'}
    (run_dir / 'media.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def encode_clip(source: Path, output_dir: Path, *, start_seconds: float,
                duration_seconds: float, gif_fps: int, ffmpeg: str = 'ffmpeg',
                ffprobe: str = 'ffprobe') -> dict:
    """Encode already-admitted bounds; callers own acceptance and publication."""
    common = [ffmpeg, '-nostdin', '-y', '-v', 'error', '-threads', '2',
              '-ss', str(start_seconds), '-t', str(duration_seconds), '-i', str(source)]
    mp4, gif = output_dir / 'representative.mp4', output_dir / 'representative.gif'
    subprocess.run(common + ['-an', '-vf', 'scale=640:-2', '-filter_threads', '2',
                             '-c:v', 'libx264', '-preset', 'fast', '-crf', '24', '-threads', '2', str(mp4)],
                   check=True, timeout=180)
    subprocess.run(common + ['-filter_complex_threads', '1', '-filter_complex',
        f'fps={gif_fps},scale=480:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3',
        '-threads', '2', str(gif)], check=True, timeout=180)
    return {p.name: {**artifact(p), **probe_video(p, ffprobe)} for p in (mp4, gif)}
