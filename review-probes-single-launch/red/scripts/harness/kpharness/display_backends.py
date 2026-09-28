"""Immutable platform/display contracts for harness-owned game windows.

Host facts describe the machine.  They never imply that a backend is usable;
``admit_backend`` makes that separate, explicit decision.
"""
from __future__ import annotations

import os
import platform
import re
import copy
import datetime
import math
import hashlib
import json
import stat
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping, Protocol, Sequence


GAMESCOPE_BACKEND = "linux-wine-k1-gamescope"
SOFTWARE_BACKEND = "linux-wine-k1"
GAMESCOPE_TOOLS = ("gamescope", "glxinfo", "xdotool", "xwininfo", "ffmpeg")
WINDOW_CAPTURE_ADAPTER = "linux-gamescope-x11-window-v1"
GEOMETRY_METHOD = "xwininfo-shm-getimage-v1"
CONTENT_METHOD = "ffprobe-lavfi-signalstats-v1"
CONTENT_ROW_KEYS = ("ymin", "ymax", "yavg", "ydif", "udif", "vdif")
# Content thresholds come only from this trusted table, never from a receipt.
# A frame is distinct only when max(YDIF, UDIF, VDIF) exceeds the policy's
# ``distinct_noise_floor``. The master is lossy (libx264 ultrafast crf 28), so
# a repeated source frame decodes with small nonzero DIF.
#
# The diagnostic floor is calibrated (round 12) on the diagnostic's own pattern,
# ``capture_diagnostic.PATTERN_GRAPH``: testsrc2 with a per-frame full-frame
# luma step, so every fresh frame moves the whole frame by at least one level
# whatever the testsrc2 speed. Synthetic encodes at 1024x768 through the
# recorder's exact codec, read by the production probes (17 families, 7,825
# duplicate and 10,518 fresh frames): duplicate max 1.0167 (an I-frame
# duplicate), fresh min 15.2818. The floor 3.9 leaves 3.84x above the largest
# duplicate and 3.92x below the smallest fresh frame
# (docs/creative-runner.md, the content gate). ``separation_factor`` makes that
# margin a runtime check: any acceptance frame inside
# (floor / factor, floor * factor) means the populations are not cleanly
# separated, and the verdict is ``calibration_ambiguous``, never pass and never
# a capture failure.
#
# The game policy is unchanged. Its floor 0 is NOT calibrated: its 5% minimum
# is a weak liveness check, and its ratio is an upper bound on real change
# (encoder refinement also counts).
CONTENT_POLICIES = MappingProxyType({
    "game-capture-v1": MappingProxyType({
        "id": "game-capture-v1", "black_luma_max": 24, "minimum_distinct_ratio": .05,
        "distinct_noise_floor": 0.0}),
    "animated-diagnostic-v2": MappingProxyType({
        "id": "animated-diagnostic-v2", "black_luma_max": 24, "minimum_distinct_ratio": .99,
        "distinct_noise_floor": 3.9, "separation_factor": 3.0}),
})
# Fixed lower bin edges of the per-frame max-DIF histogram (last bin is open).
# Fixed, so a recomputation from the hashed artifact yields the same histogram.
CONTENT_HISTOGRAM_EDGES = (0.0, 0.125, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0)
MAX_CONTENT_BYTES = 64 * 1024 * 1024
_WINDOW_ID = re.compile(r"^0x[1-9a-f][0-9a-f]*$")
_DISPLAY_SCREEN_ZERO = re.compile(r"^:([0-9]+)(?:\.0)?$")
CADENCE_POLICY = MappingProxyType({
    "id": "gamescope-cadence-v1", "requested_fps": 60,
    "minimum_rate_ratio": .99, "maximum_drop_ratio": .005,
    "maximum_gap_seconds": .05,
})
MAX_CANONICAL_PTS_FRAMES = 250_000
MAX_CANONICAL_PTS_BYTES = 16 * 1024 * 1024
MAX_ROUTE_REPORT_BYTES = 8 * 1024 * 1024


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _probe_tool_matches(tool) -> bool:
    try:
        if not isinstance(tool, Mapping) or set(tool) != {'command', 'resolved_path', 'sha256'}:
            return False
        if not all(isinstance(tool[name], str) and tool[name] for name in tool):
            return False
        resolved = Path(tool['resolved_path'])
        if resolved.resolve(strict=True) != resolved or resolved.is_symlink():
            return False
        descriptor = os.open(resolved, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                return False
            digest = hashlib.sha256()
            while block := os.read(descriptor, 1024 * 1024):
                digest.update(block)
        finally:
            os.close(descriptor)
        return digest.hexdigest() == tool['sha256']
    except (KeyError, TypeError, ValueError, OSError):
        return False


def _canonical_pts(identity, media, probe_tool) -> list[float] | None:
    """Load one bounded, hashed, master-bound canonical PTS artifact."""
    descriptor = None
    try:
        if (not isinstance(identity, Mapping) or not isinstance(media, Mapping)
                or not _probe_tool_matches(probe_tool)):
            return None
        path = Path(identity['path']); master = Path(media['path'])
        if path.parent.resolve() != master.parent.resolve() or path.name != 'ffprobe-cadence.json':
            return None
        master_info = master.lstat()
        if not stat.S_ISREG(master_info.st_mode) or master.is_symlink():
            return None
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size <= 0 or info.st_size > MAX_CANONICAL_PTS_BYTES:
            return None
        raw = os.read(descriptor, info.st_size + 1)
        if len(raw) != info.st_size or hashlib.sha256(raw).hexdigest() != identity['sha256']:
            return None
        if _sha256_file(master) != media['sha256'] or identity['master_sha256'] != media['sha256']:
            return None
        artifact = json.loads(raw)
        pts_raw = artifact['pts_seconds']
        if (artifact.get('schema') != 1 or artifact.get('master') != {
                'path': str(master.resolve()), 'sha256': media['sha256']}
                or artifact.get('probe') != {**probe_tool,
                    'method': 'ffprobe-best-effort-timestamp-time-v1'}
                or not isinstance(pts_raw, list) or not 2 <= len(pts_raw) <= MAX_CANONICAL_PTS_FRAMES
                or artifact.get('frame_count') != len(pts_raw)
                or identity.get('frame_count') != len(pts_raw)):
            return None
        pts = [float(value) for value in pts_raw]
        if (any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in pts_raw)
                or any(not math.isfinite(value) or value < 0 for value in pts)
                or any(right <= left for left, right in zip(pts, pts[1:]))):
            return None
        return pts
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _exact_ints(*values) -> bool:
    return all(type(value) is int for value in values)


def geometry_precondition(*, window_id: str, map_state: str, absolute_origin, size, border_width: int,
                          root_size, lease_extent) -> dict:
    """Evaluate the exact ShmGetImage window checks (Xext/shm.c:639-654) for a full-window grab.

    FFmpeg grabs offset 0,0 at the window size. xwininfo reports the outer
    corner, so a zero border is required to make it the content origin.
    """
    x, y = absolute_origin; width, height = size; root_width, root_height = root_size
    lease_width, lease_height = lease_extent
    if not _exact_ints(x, y, width, height, border_width, root_width, root_height, lease_width, lease_height):
        raise ValueError("geometry precondition values must be exact integers")
    grab_x = grab_y = 0
    conditions = {
        "viewable": map_state == "IsViewable",
        "inside_screen": (x + grab_x >= 0 and x + grab_x + width <= root_width
                          and y + grab_y >= 0 and y + grab_y + height <= root_height),
        "inside_border": (grab_x >= -border_width and grab_x + width <= border_width + width
                          and grab_y >= -border_width and grab_y + height <= border_width + height),
        "border_width_zero": border_width == 0,
        "equals_lease": ([width, height] == [lease_width, lease_height] == [root_width, root_height]
                         and [x, y] == [0, 0]),
    }
    return {"method": GEOMETRY_METHOD, "window_id": window_id, "map_state": map_state,
            "absolute_origin": [x, y], "size": [width, height], "border_width": border_width,
            "root_size": [root_width, root_height], "lease_extent": [lease_width, lease_height],
            "capture_rectangle": {"offset": [grab_x, grab_y], "size": [width, height]},
            "conditions": conditions,
            "status": "verified" if all(conditions.values()) else "refused"}


def geometry_precondition_sha256(evidence) -> str:
    return hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _geometry_evidence_matches(evidence, *, window_id: str, width: int, height: int) -> bool:
    try:
        if not isinstance(evidence, Mapping) or set(evidence) != {"status", "initial", "pre_exec"}:
            return False
        pre_exec = evidence["pre_exec"]
        recomputed = geometry_precondition(
            window_id=pre_exec["window_id"], map_state=pre_exec["map_state"],
            absolute_origin=pre_exec["absolute_origin"], size=pre_exec["size"],
            border_width=pre_exec["border_width"], root_size=pre_exec["root_size"],
            lease_extent=pre_exec["lease_extent"])
        return bool(evidence["status"] == "verified" and evidence["initial"] == pre_exec
                    and recomputed == pre_exec and recomputed["status"] == "verified"
                    and pre_exec["window_id"] == window_id and pre_exec["lease_extent"] == [width, height])
    except (KeyError, TypeError, ValueError):
        return False


def _content_rows_valid(frames) -> bool:
    return isinstance(frames, list) and all(
        isinstance(row, Mapping) and set(row) == set(CONTENT_ROW_KEYS)
        and all(not isinstance(row[key], bool) and isinstance(row[key], (int, float))
                and math.isfinite(row[key]) and row[key] >= 0 for key in CONTENT_ROW_KEYS)
        for row in frames)


def _black(row, policy) -> bool:
    return not (row["ymax"] > policy["black_luma_max"] and row["ymax"] > row["ymin"])


def evaluate_content(frames, canonical_pts, interval_start, interval_end, policy) -> dict:
    """Content gate: a non-black first acceptance frame and distinct frames in the interval.

    The black check applies to the first frame at or after the acceptance-start
    marker. Black startup frames before the marker are evidence only.
    """
    policy = dict(policy)
    failures: list[str] = []
    result = {"status": "failed", "method": CONTENT_METHOD, "policy": policy,
              "frame_count": len(frames) if isinstance(frames, list) else None,
              "first_frame": None, "startup": None, "acceptance": None, "failures": failures}
    if not _content_rows_valid(frames) or not frames:
        failures.append("capture_content_failed: malformed signalstats rows")
        return result
    if len(frames) != len(canonical_pts):
        failures.append("capture_content_failed: content frame count differs from canonical PTS")
        return result
    floor = policy["distinct_noise_floor"]
    selected = [index for index, value in enumerate(canonical_pts) if interval_start <= value <= interval_end]
    before = [index for index, value in enumerate(canonical_pts) if value < interval_start]
    result["startup"] = {"frames_before_acceptance": len(before),
                         "black_frames_before_acceptance": sum(1 for index in before
                                                               if _black(frames[index], policy)),
                         "capture_first_frame": {"ymin": frames[0]["ymin"], "ymax": frames[0]["ymax"]}}
    if selected:
        first_index = selected[0]
        first = frames[first_index]
        result["first_frame"] = {"index": first_index, "pts_seconds": canonical_pts[first_index],
                                 "ymin": first["ymin"], "ymax": first["ymax"]}
        if _black(first, policy):
            failures.append("capture_content_black: first acceptance frame luma max is at or below "
                            "the black threshold or has zero variance")
    else:
        failures.append("capture_content_black: no frame at or after the acceptance start marker")
    expected = max(0, len(selected) - 1)
    values = [max(frames[index][key] for key in ("ydif", "udif", "vdif")) for index in selected[1:]]
    changed = sum(1 for value in values if value > floor)
    ratio = changed / expected if expected else 0.0
    result["acceptance"] = {"start_capture_seconds": interval_start, "end_capture_seconds": interval_end,
                            "frame_count": len(selected), "expected_changes": expected,
                            "changed_frames": changed, "distinct_noise_floor": floor,
                            "distinct_ratio": ratio}
    ambiguous = False
    if "separation_factor" in policy:
        result["separation"] = content_separation(values, floor, policy["separation_factor"])
        ambiguous = result["separation"]["status"] == "ambiguous"
    if ambiguous:
        # The floor cannot classify these frames, so the ratio says nothing about capture.
        failures.append("calibration_ambiguous: %d of %d acceptance frames have a difference inside the "
                        "guard band around the noise floor" % (result["separation"]["inside_band"], expected))
    elif expected == 0 or changed == 0 or ratio < policy["minimum_distinct_ratio"]:
        failures.append("capture_content_static: distinct-frame ratio is below the policy minimum")
    result["status"] = "passed" if not failures else "failed"
    return result


def content_separation(values, floor, factor) -> dict:
    """Bimodality rule: every value must lie at or below floor/factor or at or above floor*factor.

    The calibrated duplicate and fresh populations sit at least ``factor`` away
    from the floor, so a value strictly inside the band belongs to neither.
    """
    low, high = floor / factor, floor * factor
    below = [value for value in values if value <= low]
    above = [value for value in values if value >= high]
    inside = len(values) - len(below) - len(above)
    edges = CONTENT_HISTOGRAM_EDGES
    histogram = [{"lower": lower, "upper": edges[index + 1] if index + 1 < len(edges) else None,
                  "count": sum(1 for value in values if value >= lower
                               and (index + 1 == len(edges) or value < edges[index + 1]))}
                 for index, lower in enumerate(edges)]
    return {"rule": "no acceptance frame difference strictly inside (floor/factor, floor*factor)",
            "guard_band": [low, high], "factor": factor,
            "below_band": len(below), "inside_band": inside, "above_band": len(above),
            "duplicate_max": max(below) if below else None, "fresh_min": min(above) if above else None,
            "histogram": histogram, "status": "ambiguous" if inside else "separated"}


def _content_evidence_passed(cadence, media, canonical, interval) -> bool:
    """Reopen the hashed content artifact and recompute the gate under a trusted policy."""
    try:
        expected = content_recomputed(cadence, media, canonical, interval)
        return (expected is not None and cadence["content"] == expected
                and expected["status"] == "passed")
    except (KeyError, TypeError):
        return False


def content_recomputed(cadence, media, canonical, interval):
    """The content block recomputed from the hashed artifact, or None if the artifact is not intact."""
    descriptor = None
    try:
        content = cadence["content"]; identity = content["artifact"]
        policy = CONTENT_POLICIES.get(content["policy"]["id"])
        if policy is None or content["policy"] != dict(policy):
            return None
        path = Path(identity["path"]); master = Path(media["path"])
        if path.parent.resolve() != master.parent.resolve() or path.name != "ffprobe-content.json":
            return None
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_CONTENT_BYTES:
            return None
        raw = os.read(descriptor, info.st_size + 1)
        if (len(raw) != info.st_size or hashlib.sha256(raw).hexdigest() != identity["sha256"]
                or identity["master_sha256"] != media["sha256"]):
            return None
        artifact = json.loads(raw)
        frames = artifact["frames"]
        if (set(artifact) != {"schema", "master", "probe", "frame_count", "frames"}
                or artifact["schema"] != 1
                or artifact["master"] != {"path": str(master.resolve()), "sha256": media["sha256"]}
                or artifact["probe"] != {**cadence["probe_tool"], "method": CONTENT_METHOD}
                or not _content_rows_valid(frames) or artifact["frame_count"] != len(frames)
                or identity.get("frame_count") != len(frames) or len(frames) != len(canonical)):
            return None
        return {"artifact": dict(identity), **evaluate_content(
            frames, canonical, interval["start_capture_seconds"], interval["end_capture_seconds"], policy)}
    except (KeyError, TypeError, ValueError, OSError, AttributeError, json.JSONDecodeError):
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _pts_summary_matches(summary, *, fps: int, require_status: str | None = None) -> bool:
    """Recompute a serialized PTS summary under the versioned trusted policy."""
    try:
        pts = [float(value) for value in summary['included_pts_seconds']]
        start = float(summary['start_capture_seconds']); end = float(summary['end_capture_seconds'])
        if (len(pts) < 2 or not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start
                or any(not math.isfinite(value) or value < start or value > end for value in pts)
                or any(right <= left for left, right in zip(pts, pts[1:]))):
            return False
        gaps = [right - left for left, right in zip(pts, pts[1:])]
        span = pts[-1] - pts[0]; inter_count = len(gaps)
        ordered = sorted(gaps)
        percentile = lambda ratio: ordered[min(len(ordered) - 1,
            max(0, math.ceil(len(ordered) * ratio) - 1))]
        histogram = {}
        for gap in gaps:
            tick = str(max(1, int(round(gap * fps))))
            histogram[tick] = histogram.get(tick, 0) + 1
        requested_slots = max(1, round(span * fps))
        missing = max(0, requested_slots - inter_count)
        maximum = max(gaps)
        computed_status = ('passed' if inter_count / span >= fps * CADENCE_POLICY['minimum_rate_ratio']
            and missing / requested_slots <= CADENCE_POLICY['maximum_drop_ratio']
            and maximum <= CADENCE_POLICY['maximum_gap_seconds'] else 'failed')
        return bool(
            summary.get('thresholds') == {
                'minimum_rate_ratio': CADENCE_POLICY['minimum_rate_ratio'],
                'maximum_drop_ratio': CADENCE_POLICY['maximum_drop_ratio'],
                'maximum_gap_seconds': CADENCE_POLICY['maximum_gap_seconds']}
            and summary['first_included_pts'] == pts[0] and summary['last_included_pts'] == pts[-1]
            and summary['frame_count'] == len(pts) and summary['inter_frame_count'] == inter_count
            and abs(float(summary['span_seconds']) - span) <= 1e-9
            and abs(float(summary['effective_fps']) - inter_count / span) <= 1e-9
            and summary['requested_slot_count'] == requested_slots and summary['missing_slots'] == missing
            and summary['interval_histogram_ticks'] == histogram
            and abs(float(summary['p95_gap_seconds']) - percentile(.95)) <= 1e-9
            and abs(float(summary['p99_gap_seconds']) - percentile(.99)) <= 1e-9
            and abs(float(summary['maximum_gap_seconds']) - maximum) <= 1e-9
            and summary['gaps_above_ms'] == {str(limit): sum(gap > limit / 1000 for gap in gaps)
                                                for limit in (25, 50, 100)}
            and summary.get('status') == computed_status
            and (require_status is None or computed_status == require_status))
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return False


def _deep_frozen(value):
    if isinstance(value, Mapping):
        return MappingProxyType({key: _deep_frozen(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_deep_frozen(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_deep_frozen(item) for item in value)
    return copy.deepcopy(value)


@dataclass(frozen=True)
class HostFacts:
    os_family: str
    os_version: str
    architecture: str
    session_type: str | None
    desktop: str | None
    container: str | None
    crostini: bool
    executables: Mapping[str, bool] = field(default_factory=dict)
    probes: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "executables", _deep_frozen(self.executables))
        object.__setattr__(self, "probes", _deep_frozen(self.probes))


@dataclass(frozen=True)
class BackendCapabilities:
    adapter_id: str
    targets: tuple[str, ...]
    owned_display: bool
    window_enumeration: str | None
    exact_window_capture: str | None
    real_input: str | None
    acceleration_proof: str | None
    status: str
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "targets", tuple(self.targets))


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    start: str

    def __post_init__(self) -> None:
        if self.pid <= 0 or not self.start:
            raise ValueError("process identity requires a positive PID and start token")


@dataclass(frozen=True)
class OwnedWindow:
    window_id: str
    owner: ProcessIdentity
    width: int
    height: int
    title: str
    lease_id: str
    display: str
    environment: Mapping[str, str]
    discovered_monotonic: float
    capture_capabilities: frozenset[str]
    input_capabilities: frozenset[str]

    def __post_init__(self) -> None:
        if not _WINDOW_ID.fullmatch(self.window_id) or self.window_id == "0x1":
            raise ValueError("owned window requires a canonical non-root hexadecimal id")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("owned window geometry must be positive")
        if not self.lease_id or not self.display.startswith(":"):
            raise ValueError("owned window requires lease and private X11 display identity")
        authority = {key: value for key, value in self.environment.items()
                     if key in ("DISPLAY", "XAUTHORITY", "WAYLAND_DISPLAY") and value}
        if authority.get("DISPLAY") != self.display:
            raise ValueError("owned window authority does not match its display")
        object.__setattr__(self, "environment", MappingProxyType(authority))
        object.__setattr__(self, "capture_capabilities", frozenset(self.capture_capabilities))
        object.__setattr__(self, "input_capabilities", frozenset(self.input_capabilities))

    def receipt(self) -> dict:
        return {
            "status": "verified", "id": self.window_id, "pid": self.owner.pid,
            "pid_start": self.owner.start, "geometry": [self.width, self.height],
            "title": self.title, "discovered_monotonic": self.discovered_monotonic,
            "lease_id": self.lease_id,
        }


class DisplayLease(Protocol):
    adapter_id: str
    lease_id: str
    environment: Mapping[str, str]
    width: int
    height: int

    def is_alive(self) -> bool: ...
    def close(self) -> None: ...
    def receipt(self) -> dict: ...


def detect_host(*, environ: Mapping[str, str] | None = None,
                which: Callable[[str], str | None] = shutil.which,
                exists: Callable[[Path], bool] = Path.exists) -> HostFacts:
    env = os.environ if environ is None else environ
    crostini = exists(Path("/dev/.cros_milestone")) or bool(env.get("SOMMELIER_VERSION"))
    container = env.get("container") or ("crostini" if crostini else None)
    return HostFacts(
        os_family=platform.system().lower(), os_version=platform.release(),
        architecture=platform.machine(), session_type=env.get("XDG_SESSION_TYPE"),
        desktop=env.get("XDG_CURRENT_DESKTOP"), container=container, crostini=crostini,
        executables={name: which(name) is not None for name in GAMESCOPE_TOOLS},
        probes={"dri_present": exists(Path("/dev/dri"))},
    )


def admit_backend(identifier: str, facts: HostFacts, *, target: str = "k1",
                  reuse_display: bool = False) -> BackendCapabilities:
    if identifier == SOFTWARE_BACKEND:
        admitted = facts.os_family == "linux" and target == "k1"
        return BackendCapabilities(identifier, ("k1",), True, "xdotool-pid",
            None, "x11-xdotool", None, "admitted" if admitted else "refused",
            "owned Xvfb software path" if admitted else "Linux K1 only")
    if identifier != GAMESCOPE_BACKEND:
        return BackendCapabilities(identifier, (), False, None, None, None, None,
            "refused", "no validated owned display/input/capture adapter")
    missing = tuple(name for name in GAMESCOPE_TOOLS if not facts.executables.get(name, False))
    reason = None
    if facts.os_family != "linux" or target != "k1":
        reason = "Gamescope adapter is Linux K1 only"
    elif facts.crostini:
        reason = "Crostini requires a separate live GPU/input/capture admission"
    elif reuse_display:
        reason = "Gamescope adapter refuses caller display reuse"
    elif missing:
        reason = "missing required executables: " + ", ".join(missing)
    elif not facts.probes.get("dri_present"):
        reason = "no render device probe available"
    return BackendCapabilities(identifier, ("k1",), True, "xdotool-visible-pid",
        "ffmpeg-x11grab-window-id-v1", "x11-xdotool", "glxinfo-B",
        "refused" if reason else "admitted",
        reason or "owned Gamescope Xwayland lease")


def process_start(pid: int, *, proc_root: Path = Path("/proc")) -> str:
    raw = (proc_root / str(pid) / "stat").read_text()
    end = raw.rfind(")")
    fields = raw[end + 1:].split() if end > 0 else []
    if len(fields) < 20:
        raise RuntimeError(f"cannot read start identity for PID {pid}")
    return fields[19]


def process_relationship(pid: int, *, proc_root: Path = Path("/proc")) -> tuple[int, int, int, str]:
    raw = (proc_root / str(pid) / "stat").read_text()
    end = raw.rfind(")")
    fields = raw[end + 1:].split() if end > 0 else []
    if len(fields) < 20:
        raise RuntimeError(f"cannot read process relationship for PID {pid}")
    return int(fields[1]), int(fields[2]), int(fields[3]), fields[19]


def discover_owned_x11_window(
    lease: DisplayLease, game_pids: Sequence[int], *,
    run: Callable[..., object], monotonic: Callable[[], float],
    start_reader: Callable[[int], str] = process_start,
) -> OwnedWindow:
    """Freeze exactly one visible PID-owned window on a live private lease."""
    if not lease.is_alive():
        raise RuntimeError("owned display lease is not live")
    pids = tuple(sorted(set(int(pid) for pid in game_pids if int(pid) > 0)))
    if not pids:
        raise RuntimeError("no live owned game process")
    env = dict(lease.environment)
    candidates: list[tuple[str, int]] = []
    for pid in pids:
        result = run(["xdotool", "search", "--onlyvisible", "--pid", str(pid)],
                     env=env, text=True, capture_output=True, timeout=5, check=False)
        if getattr(result, "returncode", 1) not in (0, 1):
            raise RuntimeError("X11 window enumeration failed")
        for raw in getattr(result, "stdout", "").split():
            try:
                candidates.append((f"0x{int(raw, 0):x}", pid))
            except ValueError as error:
                raise RuntimeError("invalid X11 window id") from error
    if len(candidates) != 1:
        raise RuntimeError(f"expected one visible owned game window, found {len(candidates)}")
    window_id, expected_pid = candidates[0]
    details = run(["xdotool", "getwindowpid", window_id, "getwindowgeometry", "--shell",
                   window_id, "getwindowname", window_id], env=env, text=True,
                  capture_output=True, timeout=5, check=False)
    if getattr(details, "returncode", 1) != 0:
        raise RuntimeError("X11 window identity query failed")
    lines = getattr(details, "stdout", "").splitlines()
    try:
        owner_pid = int(lines[0]); values = dict(line.split("=", 1) for line in lines[1:] if "=" in line)
        width, height = int(values["WIDTH"]), int(values["HEIGHT"])
    except (ValueError, KeyError, IndexError) as error:
        raise RuntimeError("incomplete X11 window identity") from error
    if owner_pid != expected_pid or owner_pid not in pids:
        raise RuntimeError("foreign X11 window owner")
    title = values.get("TITLE", lines[-1] if lines else "")
    return OwnedWindow(window_id, ProcessIdentity(owner_pid, start_reader(owner_pid)),
        width, height, title, lease.lease_id, env["DISPLAY"], env, monotonic(),
        frozenset({"x11_window_capture"}), frozenset({"x11_input"}))


class OwnedWindowVerifier:
    """Revalidate the stable identity of a frozen window against its lease."""
    def __init__(self, lease: DisplayLease, *, run: Callable[..., object],
                 start_reader: Callable[[int], str] = process_start,
                 monotonic: Callable[[], float] | None = None):
        self.lease, self.run, self.start_reader = lease, run, start_reader
        self.monotonic = monotonic or __import__('time').monotonic

    def __call__(self, target: OwnedWindow) -> OwnedWindow:
        if target.lease_id != self.lease.lease_id or target.display != self.lease.environment.get("DISPLAY"):
            raise RuntimeError("window belongs to another display lease")
        current = discover_owned_x11_window(self.lease, [target.owner.pid], run=self.run,
            monotonic=self.monotonic, start_reader=self.start_reader)
        stable = (current.window_id, current.owner, current.width, current.height, current.title,
                  current.lease_id, current.display, current.capture_capabilities, current.input_capabilities)
        expected = (target.window_id, target.owner, target.width, target.height, target.title,
                    target.lease_id, target.display, target.capture_capabilities, target.input_capabilities)
        if stable != expected:
            raise RuntimeError("owned window stable identity changed")
        return target


def _single_flags(command, flags):
    if not isinstance(command, (list, tuple)) or not all(isinstance(item, str) for item in command):
        return None
    parsed = {}
    for flag in flags:
        indexes = [index for index, item in enumerate(command) if item == flag]
        if len(indexes) != 1 or indexes[0] + 1 >= len(command):
            return None
        parsed[flag] = command[indexes[0] + 1]
    return parsed


def _cadence_evidence_passed(cadence, capture, media, route) -> bool:
    try:
        thresholds = cadence['thresholds']; acceptance = cadence['acceptance_interval']
        canonical = _canonical_pts(cadence.get('pts_artifact'), media, cadence.get('probe_tool'))
        if canonical is None:
            return False
        expected_thresholds = {key: CADENCE_POLICY[key] for key in
                               ('minimum_rate_ratio', 'maximum_drop_ratio', 'maximum_gap_seconds')}
        whole = cadence.get('whole_capture')
        if (cadence.get('policy') != dict(CADENCE_POLICY) or cadence.get('requested_fps') != 60
                or capture.get('capture_sampling_fps_requested') != 60
                or thresholds != expected_thresholds
                or not _pts_summary_matches(whole, fps=60)
                or whole['included_pts_seconds'] != canonical
                or whole['start_capture_seconds'] != canonical[0]
                or whole['end_capture_seconds'] != canonical[-1]
                or not math.isfinite(float(whole['missing_or_dropped_ratio']))
                or abs(float(whole['missing_or_dropped_ratio'])
                       - whole['missing_slots'] / whole['requested_slot_count']) > 1e-12):
            return False
        start, end = acceptance['start_marker'], acceptance['end_marker']
        markers = capture['markers']
        if (not isinstance(markers, list) or len(markers) < 2
                or capture['marker_order']['status'] != 'ordered'):
            return False
        names = [marker['name'] for marker in markers]
        if len(set(names)) != len(names) or start not in names or end not in names:
            return False
        origin = float(capture['startup']['started_monotonic'])
        for index, marker in enumerate(markers):
            detected = float(marker['detected_monotonic']); captured = float(marker['capture_seconds'])
            uncertainty = float(marker['uncertainty_ms']) / 1000
            if (not isinstance(marker['native_log_byte_end'], int) or marker['native_log_byte_end'] <= 0
                    or not isinstance(marker['sequence'], int) or marker['sequence'] <= 0
                    or marker['poll_interval_ms'] != marker['uncertainty_ms']
                    or marker['poll_interval_ms'] != 100
                    or not all(math.isfinite(value) for value in (detected, captured, uncertainty))
                    or captured < 0 or uncertainty <= 0
                    or abs((detected - origin) - captured) > uncertainty + 1e-9):
                return False
            if index:
                prior = markers[index - 1]
                if (marker['native_log_byte_end'] <= prior['native_log_byte_end']
                        or marker['sequence'] <= prior['sequence']
                        or marker['capture_seconds'] < prior['capture_seconds']
                        or marker['detected_monotonic'] < prior['detected_monotonic']):
                    return False
        if names.index(start) >= names.index(end):
            return False
        configuration = cadence['marker_configuration']
        required_order = configuration['required_order']
        optional = configuration['optional_markers']
        if (configuration.get('version') != 1 or not isinstance(required_order, list)
                or len(required_order) < 2 or len(set(required_order)) != len(required_order)
                or optional != ['effect_start']
                or set(names) != set(required_order) | (set(names) & set(optional))
                or [name for name in names if name in required_order] != required_order
                or configuration['acceptance_pair'] != [start, end]
                or configuration['patterns'] != {marker['name']: marker['pattern'] for marker in markers
                                                   if marker['name'] in required_order}):
            return False
        intervals = cadence['intervals']
        if (not isinstance(intervals, list) or not intervals
                or any(not _pts_summary_matches(item, fps=60) for item in intervals)):
            return False
        pairs = []
        for item in intervals:
            left_name, right_name = item.get('start_marker'), item.get('end_marker')
            if left_name not in names or right_name not in names or names.index(left_name) >= names.index(right_name):
                return False
            left_marker, right_marker = markers[names.index(left_name)], markers[names.index(right_name)]
            if (abs(float(item['start_capture_seconds']) - float(left_marker['capture_seconds']))
                    > float(left_marker['uncertainty_ms']) / 1000 + 1e-9
                    or abs(float(item['end_capture_seconds']) - float(right_marker['capture_seconds']))
                    > float(right_marker['uncertainty_ms']) / 1000 + 1e-9):
                return False
            projected = [value for value in canonical
                         if float(item['start_capture_seconds']) <= value <= float(item['end_capture_seconds'])]
            if item['included_pts_seconds'] != projected:
                return False
            pairs.append((left_name, right_name))
        expected_pairs = list(zip(required_order, required_order[1:]))
        acceptance_pair = (start, end)
        if acceptance_pair not in expected_pairs:
            expected_pairs.append(acceptance_pair)
        if len(pairs) != len(set(pairs)) or set(pairs) != set(expected_pairs):
            return False
        matching = [item for item in intervals
                    if item.get('start_marker') == start and item.get('end_marker') == end]
        if len(matching) != 1:
            return False
        interval = matching[0]
        terminal = capture['diagnostics']['terminal']
        terminal_copy = cadence['terminal_progress']
        minimum = float(thresholds['minimum_rate_ratio'])
        maximum_drop = float(thresholds['maximum_drop_ratio'])
        maximum_gap = float(thresholds['maximum_gap_seconds'])
        fps = cadence['requested_fps']
        frame_count = interval['frame_count']; inter_count = interval['inter_frame_count']
        first_pts = float(interval['first_included_pts']); last_pts = float(interval['last_included_pts'])
        span = float(interval['span_seconds']); effective = float(interval['effective_fps'])
        requested_slots = interval['requested_slot_count']; missing = interval['missing_slots']
        ffmpeg = interval['ffmpeg']
        pts = [float(value) for value in interval['included_pts_seconds']]
        if (len(pts) < 2 or any(not math.isfinite(value) or value < 0 for value in pts)
                or any(right <= left for left, right in zip(pts, pts[1:]))):
            return False
        gaps = [right - left for left, right in zip(pts, pts[1:])]
        ordered_gaps = sorted(gaps)
        percentile = lambda ratio: ordered_gaps[min(len(ordered_gaps) - 1,
            max(0, math.ceil(len(ordered_gaps) * ratio) - 1))]
        histogram = {}
        for gap in gaps:
            tick = str(max(1, int(round(gap * fps))))
            histogram[tick] = histogram.get(tick, 0) + 1
        maximum_observed = max(gaps)
        start_marker = markers[names.index(start)]; end_marker = markers[names.index(end)]
        interval_start = float(interval['start_capture_seconds'])
        interval_end = float(interval['end_capture_seconds'])
        start_uncertainty = float(start_marker['uncertainty_ms']) / 1000
        end_uncertainty = float(end_marker['uncertainty_ms']) / 1000
        left = ffmpeg['start_sample']; right = ffmpeg['end_sample']
        counter_names = ('frame', 'out_time_us', 'dup_frames', 'drop_frames')
        if (not isinstance(fps, int) or isinstance(fps, bool) or fps != 60
                or not isinstance(frame_count, int) or frame_count < 2
                or inter_count != frame_count - 1 or frame_count != len(pts)
                or not all(math.isfinite(value) and value >= 0 for value in
                           (first_pts, last_pts, span, effective, interval_start, interval_end,
                            float(interval['missing_or_dropped_ratio']),
                            float(interval['maximum_gap_seconds']), float(interval['p95_gap_seconds']),
                            float(interval['p99_gap_seconds'])))
                or span <= 0 or interval_end <= interval_start
                or first_pts != pts[0] or last_pts != pts[-1]
                or abs((last_pts - first_pts) - span) > 1e-9
                or abs(effective - inter_count / span) > 1e-9
                or requested_slots != max(1, round(span * fps))
                or missing != max(0, requested_slots - inter_count)
                or interval['interval_histogram_ticks'] != histogram
                or abs(float(interval['p95_gap_seconds']) - percentile(.95)) > 1e-9
                or abs(float(interval['p99_gap_seconds']) - percentile(.99)) > 1e-9
                or abs(float(interval['maximum_gap_seconds']) - maximum_observed) > 1e-9
                or interval['gaps_above_ms'] != {str(limit): sum(gap > limit / 1000 for gap in gaps)
                                                  for limit in (25, 50, 100)}
                or ffmpeg.get('status') != 'bounded'
                or any(not isinstance(ffmpeg.get(name), int) or ffmpeg[name] < 0
                       for name in ('dup_frames', 'drop_frames'))
                or any(not isinstance(left.get(name), int) or left[name] < 0
                       or not isinstance(right.get(name), int) or right[name] < left[name]
                       for name in counter_names)
                or not all(math.isfinite(float(sample['capture_seconds']))
                           and float(sample['capture_seconds']) >= 0 for sample in (left, right))
                or float(left['capture_seconds']) > interval_start
                or float(right['capture_seconds']) < interval_end
                or float(right['capture_seconds']) < float(left['capture_seconds'])
                or ffmpeg['dup_frames'] != right['dup_frames'] - left['dup_frames']
                or ffmpeg['drop_frames'] != right['drop_frames'] - left['drop_frames']):
            return False
        prefix_start = sum(value <= interval_start for value in canonical)
        prefix_end = sum(value <= interval_end for value in canonical)
        frame_us = math.ceil(1_000_000 / fps)
        if (left['frame'] > prefix_start or right['frame'] < prefix_end
                or left['out_time_us'] > math.ceil(first_pts * 1_000_000) + frame_us
                or right['out_time_us'] + frame_us < math.floor(last_pts * 1_000_000)):
            return False
        route_bounds = route.get('capture_interval')
        route_summary = cadence.get('route_interval')
        if route_bounds is None:
            if route_summary is not None:
                return False
        else:
            if (not isinstance(route_bounds, Mapping) or set(route_bounds) != {'start_seconds', 'end_seconds'}
                    or route_summary is None or not _pts_summary_matches(route_summary, fps=60)
                    or route_summary['start_capture_seconds'] != route_bounds['start_seconds']
                    or route_summary['end_capture_seconds'] != route_bounds['end_seconds']
                    or route_summary['included_pts_seconds'] != [value for value in canonical
                        if route_bounds['start_seconds'] <= value <= route_bounds['end_seconds']]):
                return False
        missing_or_dropped = max(missing, ffmpeg['drop_frames'])
        drop_ratio = missing_or_dropped / requested_slots
        return bool(
            cadence.get('status') == 'passed' and start and end and start != end
            and 0 < minimum <= 1 and 0 <= maximum_drop <= 1 and 0 < maximum_gap <= 1
            and abs(interval_start - float(start_marker['capture_seconds'])) <= start_uncertainty + 1e-9
            and abs(interval_end - float(end_marker['capture_seconds'])) <= end_uncertainty + 1e-9
            and effective >= fps * minimum
            and interval['missing_or_dropped_slots'] == missing_or_dropped
            and abs(interval['missing_or_dropped_ratio'] - drop_ratio) <= 1e-12
            and drop_ratio <= maximum_drop
            and interval['maximum_gap_seconds'] <= maximum_gap
            and interval.get('status') == 'passed'
            and terminal_copy == terminal
            and set(terminal) == {'frame', 'out_time_us', 'dup_frames', 'drop_frames'}
            and all(type(terminal[name]) is int and terminal[name] >= 0
                    for name in ('frame', 'out_time_us', 'dup_frames', 'drop_frames'))
            and terminal['frame'] >= frame_count and terminal['out_time_us'] > 0
            and terminal['frame'] >= whole['frame_count']
            and terminal['out_time_us'] + math.ceil(1_000_000 / fps)
                >= math.floor(float(whole['last_included_pts']) * 1_000_000)
            and all(terminal[name] >= right[name]
                    for name in ('frame', 'out_time_us', 'dup_frames', 'drop_frames'))
            and terminal['dup_frames'] == 0 and ffmpeg['dup_frames'] == 0
            and terminal['drop_frames'] >= ffmpeg['drop_frames']
            and cadence.get('policy_scope') == {
                'rate_gap_missing': 'acceptance_interval',
                'ffmpeg_drop_delta': 'acceptance_interval',
                'ffmpeg_duplicates': 'whole_capture'}
            and not cadence.get('failures')
            # No cadence verdict passes without the bound content gate.
            and _content_evidence_passed(cadence, media, canonical, interval))
    except (KeyError, TypeError, ValueError, StopIteration, ZeroDivisionError):
        return False


def _window_capture_matches(capture, *, lease_id, xdisplay, width, height, window) -> bool:
    """Accept only exact verified child-window capture; root capture is never evidence here."""
    try:
        command = capture['command']
        parsed = _single_flags(command, ('-progress', '-f', '-draw_mouse', '-video_size', '-framerate',
                                         '-window_id', '-i'))
        source = capture['source']; authorization = capture['authorization']
        surface = authorization['authorized_surface']; coverage = authorization['coverage']
        startup = capture['startup']; shm = startup['shm']
        display_match = _DISPLAY_SCREEN_ZERO.fullmatch(xdisplay)
        if display_match is None or not _WINDOW_ID.fullmatch(window['id']):
            return False
        normalized = f':{int(display_match.group(1))}.0'
        fps = str(capture['capture_sampling_fps_requested'])
        source_segment = ['-f', 'x11grab', '-draw_mouse', '0', '-framerate', fps,
                          '-window_id', window['id'], '-video_size', f'{width}x{height}', '-i', normalized]
        source_start = command.index('-f') if parsed is not None else -1
        output = command[-1] if command else ''
        progress = parsed['-progress'] if parsed is not None else ''
        progress_match = re.fullmatch(r'/proc/self/fd/([0-9]+)', progress)
        output_match = re.fullmatch(r'/proc/self/fd/([0-9]+)/continuous\.mp4', output)
        progress_fd = int(progress_match.group(1)) if progress_match else -1
        output_fd = int(output_match.group(1)) if output_match else -1
        transport = capture['transport']
        expected_command = ([command[0], '-nostdin', '-y', '-threads', '2', '-nostats',
            '-stats_period', '0.25', '-progress', progress] + source_segment +
            ['-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28',
             '-pix_fmt', 'yuv420p', '-threads', '2', output]) if command else []
        return bool(
            parsed is not None
            and list(command) == expected_command
            and not any(item in command for item in ('-r', '-vsync', '-fps_mode'))
            and not any('fps=' in item or 'setpts' in item for item in command)
            and list(command[source_start:source_start + len(source_segment)]) == source_segment
            and progress_match is not None and output_match is not None
            and progress_fd >= 3 and output_fd >= 3 and progress_fd != output_fd
            and transport == {'version': 1,
                'progress': {'fd': progress_fd, 'role': 'regular-progress-file'},
                'output': {'directory_fd': output_fd, 'role': 'private-output-directory',
                           'name': 'continuous.mp4'}}
            and command.count(output) == 1 and command.count(progress) == 1
            and parsed['-window_id'] == window['id']
            and capture['adapter'] == WINDOW_CAPTURE_ADAPTER
            and source == {'kind': 'x11-window', 'input': normalized, 'window_id': window['id'],
                           'source_extent': [width, height], 'drawable': 'window',
                           'details': {'screen': 0, 'draw_mouse': False}}
            and _geometry_evidence_matches(capture.get('geometry_precondition'),
                                           window_id=window['id'], width=width, height=height)
            and authorization['lease_id'] == lease_id
            and authorization['private_display'] is True
            and authorization['caller_display_reused'] is False
            and surface == {'id': window['id'], 'pid': window['pid'],
                            'pid_start': window['pid_start'], 'extent': [width, height]}
            and coverage == {'status': 'exact', 'surface_origin': [0, 0],
                             'surface_extent': [width, height], 'source_extent': [width, height]}
            and startup['status'] == 'passed' and startup['timeout_seconds'] == 5.0
            and startup['first_frame'] >= 1
            and isinstance(startup['started_monotonic'], (int, float))
            and isinstance(startup['first_frame_monotonic'], (int, float))
            and startup['first_frame_monotonic'] >= startup['started_monotonic']
            and shm['status'] == 'no_fallback_observed'
            and shm['method'] == 'absence-of-fallback-through-first-frame-and-continuous-log-watch'
            and not shm['forbidden_matches']
            and capture['diagnostics']['status'] == 'complete'
            and capture['diagnostics']['terminal']['frame'] >= 1)
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def schema2_receipt(*, facts: HostFacts, capabilities: BackendCapabilities,
                    lease: DisplayLease, window: OwnedWindow, recorder: Mapping[str, object],
                    route_passed: bool, console_correlated: bool, cleanup: Mapping[str, str],
                    source_unchanged: bool, inputs_unchanged: bool,
                    visual_status: str = "pending", route_receipt: Mapping[str, object] | None = None,
                    capture_gate: Mapping[str, object] | None = None) -> dict:
    """Snapshot the backend evidence chain without allowing media to self-certify."""
    capture = copy.deepcopy(recorder.get("capture"))
    cadence = copy.deepcopy(recorder.get("cadence"))
    media = copy.deepcopy(recorder.get("media"))
    cleanup_snapshot = dict(cleanup)
    route_snapshot = copy.deepcopy(dict(route_receipt or {}))
    capture_gate_snapshot = copy.deepcopy(dict(capture_gate or {}))
    window_receipt = window.receipt()
    xdisplay = lease.environment.get("DISPLAY")
    identities_match = bool(
        capabilities.adapter_id == lease.adapter_id
        and window.lease_id == lease.lease_id
        and window.display == xdisplay
        and isinstance(capture, dict)
        and (window.width, window.height) == (lease.width, lease.height)
        and _window_capture_matches(capture, lease_id=lease.lease_id, xdisplay=xdisplay,
                                    width=lease.width, height=lease.height, window=window_receipt))
    admitted = capabilities.status == "admitted" and identities_match
    capture_passed = (isinstance(capture, dict) and capture.get("status") == "passed"
                      and not recorder.get("failure") and isinstance(media, dict)
                      and media.get("continuous") and media.get("status") == "retained_for_visual_review")
    cadence_passed = _cadence_evidence_passed(cadence, capture, media.get('continuous'), route_snapshot)
    cleanup_passed = (cleanup_snapshot.get("status") == "passed"
        and cleanup_snapshot.get("order") == ["recorder", "game_wine", "display"]
        and all(cleanup_snapshot.get(name) == "passed" for name in ("recorder", "game_wine", "display")))
    accepted = visual_status == "accepted"
    route_complete = (route_passed and route_snapshot.get('predicates_passed') is True
        and isinstance(route_snapshot.get('steps'), list) and bool(route_snapshot['steps'])
        and all(isinstance(step, Mapping) and step.get('status') == 'ok'
                for step in route_snapshot['steps']))
    ok = all((admitted, route_complete, capture_gate_snapshot == {'status': 'passed'},
              console_correlated, capture_passed, cadence_passed, cleanup_passed,
              source_unchanged, inputs_unchanged, accepted))
    result = {
        "schema": 2, "backend": capabilities.adapter_id,
        "platform": {
            "detected": {"os": facts.os_family, "version": facts.os_version,
                         "architecture": facts.architecture, "session": facts.session_type,
                         "desktop": facts.desktop, "container": facts.container,
                         "crostini": facts.crostini},
            "admission": {"status": capabilities.status, "reason": capabilities.reason},
        },
        "display": copy.deepcopy(lease.receipt()), "window": copy.deepcopy(window_receipt),
        "capture": capture, "cadence": cadence,
        "capture_gate": capture_gate_snapshot,
        "route": {**route_snapshot,
                  "status": "passed" if route_passed else "failed",
                  "physical_console_correlated": console_correlated},
        "media": media,
        "preservation": {"source_unchanged": source_unchanged, "inputs_unchanged": inputs_unchanged},
        "cleanup": cleanup_snapshot,
        "visual_review": {"status": visual_status,
                          "scope": "native behavior, framing, readability, cadence, defining effect, and transitions"},
        "ok": ok,
    }
    result["acceptance_ready"] = execution_evidence_ready(result, require_completion=False)
    return result


def execution_evidence_ready(receipt: Mapping[str, object], *, require_completion: bool = True) -> bool:
    """Authoritatively recompute whether serialized schema-2 execution passed."""
    try:
        platform_data = receipt["platform"]; display = receipt["display"]; window = receipt["window"]
        capture = receipt["capture"]; route = receipt["route"]; media = receipt["media"]
        preservation = receipt["preservation"]; cleanup = receipt["cleanup"]
        command = capture["command"]
        if receipt["schema"] != 2 or receipt["backend"] != GAMESCOPE_BACKEND:
            return False
        if platform_data["admission"]["status"] != "admitted" or not platform_data.get("detected"):
            return False
        lease_id = display["lease_id"]; xdisplay = display["x11"]["display"]
        owners = display["owner"]; group = display["process_group"]
        if (display["kind"] != "gamescope-xwayland" or display["readiness"]["status"] != "passed"
                or display["renderer"]["status"] != "accelerated" or display["renderer"]["direct"] is not True
                or not xdisplay or not display["x11"]["xauthority_present"]
                or any(type(owners[name]["pid"]) is not int or owners[name]["pid"] <= 0 or not owners[name]["start"]
                       for name in ("gamescope", "ready_child"))
                or type(group["pgid"]) is not int or type(group["session"]) is not int
                or group["child_descends_from_gamescope"] is not True):
            return False
        width, height = display["requested_geometry"]
        if (window["status"] != "verified" or window["lease_id"] != lease_id
                or window["pid"] <= 0 or not window["pid_start"]
                or window["geometry"] != [width, height] or width <= 0 or height <= 0
                or capture["status"] != "passed"
                or not _window_capture_matches(capture, lease_id=lease_id, xdisplay=xdisplay,
                                               width=width, height=height, window=window)
                or not _cadence_evidence_passed(receipt["cadence"], capture, media.get('continuous'), route)):
            return False
        continuous = media["continuous"]
        if not _route_report_matches(receipt, route):
            return False
        if (media["status"] != "retained_for_visual_review" or not continuous["path"]
                or not continuous["sha256"] or receipt['capture_gate'] != {'status': 'passed'}
                or route["status"] != "passed" or route.get('predicates_passed') is not True
                or not isinstance(route.get('steps'), list) or not route['steps']
                or any(not isinstance(step, Mapping) or step.get('status') != 'ok' for step in route['steps'])
                or route["physical_console_correlated"] is not True
                or preservation != {"source_unchanged": True, "inputs_unchanged": True}
                or cleanup.get("status") != "passed"
                or cleanup.get("order") != ["recorder", "game_wine", "display"]
                or any(cleanup.get(name) != "passed" for name in ("recorder", "game_wine", "display"))):
            return False
        if require_completion:
            started = datetime.datetime.fromisoformat(receipt["started_utc"])
            finished = datetime.datetime.fromisoformat(receipt["finished_utc"])
            if finished < started or not receipt.get("run_dir"):
                return False
        return True
    except (KeyError, TypeError, ValueError, IndexError):
        return False


def _route_report_matches(receipt: Mapping[str, object], route: Mapping[str, object]) -> bool:
    """Bind duplicated route fields to one bounded canonical ScenarioRunner report."""
    try:
        run_dir = Path(receipt['run_dir']).resolve(strict=True)
        route_source = receipt['route_source']
        if not isinstance(route_source, Mapping) or set(route_source) != {'path', 'sha256', 'identity'}:
            return False
        source_path = Path(route_source['path'])
        if (source_path.resolve(strict=True).parent != run_dir
                or source_path.name != 'executed-route.toml' or source_path.is_symlink()):
            return False
        source_fd = os.open(source_path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            source_info = os.fstat(source_fd)
            if not stat.S_ISREG(source_info.st_mode) or not 0 < source_info.st_size <= MAX_ROUTE_REPORT_BYTES:
                return False
            source_raw = os.read(source_fd, source_info.st_size + 1)
            source_after = os.fstat(source_fd)
            expected_source_identity = {'device': source_info.st_dev, 'inode': source_info.st_ino,
                'size': source_info.st_size, 'mtime_ns': source_info.st_mtime_ns,
                'ctime_ns': source_info.st_ctime_ns, 'links': source_info.st_nlink}
            if (len(source_raw) != source_info.st_size
                    or (source_info.st_dev, source_info.st_ino, source_info.st_size, source_info.st_mtime_ns,
                        source_info.st_ctime_ns, source_info.st_nlink)
                    != (source_after.st_dev, source_after.st_ino, source_after.st_size,
                        source_after.st_mtime_ns, source_after.st_ctime_ns, source_after.st_nlink)):
                return False
        finally:
            os.close(source_fd)
        if (route_source.get('identity') != expected_source_identity
                or expected_source_identity['links'] != 1
                or not isinstance(route_source['sha256'], str)
                or hashlib.sha256(source_raw).hexdigest() != route_source['sha256']):
            return False
        from .scenario import Scenario
        scenario = Scenario.parse(source_raw.decode('utf-8'), source_path)
        if scenario.target != 'k1' or receipt.get('target') != 'k1':
            return False
        build = receipt.get('build')
        runtime = receipt.get('runtime')
        if not isinstance(build, str) or not build or not isinstance(runtime, Mapping) or not runtime:
            return False
        from . import targets as target_registry
        if set(runtime) != set(target_registry.get('k1').runtime_files):
            return False
        runtime_sha = {}
        for name, artifact in runtime.items():
            if (not isinstance(name, str) or not name or not isinstance(artifact, Mapping)
                    or set(artifact) != {'path', 'sha256'}):
                return False
            runtime_path = Path(artifact['path'])
            if runtime_path.is_symlink() or not runtime_path.is_file():
                return False
            actual_sha = _sha256_file(runtime_path)
            if (not isinstance(artifact['sha256'], str) or actual_sha != artifact['sha256']):
                return False
            runtime_sha[name] = actual_sha
        binding = route.get('execution_identity')
        if binding != {'scenario': scenario.name, 'target': 'k1', 'build': build,
                       'route_source_sha256': route_source['sha256'],
                       'runtime_sha256': runtime_sha}:
            return False
        identity = route['report']
        if not isinstance(identity, Mapping) or set(identity) != {'path', 'sha256'}:
            return False
        path = Path(identity['path'])
        if path.resolve(strict=True).parent != run_dir or path.name != 'report.json' or path.is_symlink():
            return False
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_ROUTE_REPORT_BYTES:
                return False
            raw = os.read(descriptor, info.st_size + 1)
            after = os.fstat(descriptor)
            file_identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
            if (len(raw) != info.st_size
                    or file_identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
                return False
        finally:
            os.close(descriptor)
        digest = identity['sha256']
        if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
            return False
        if hashlib.sha256(raw).hexdigest() != digest:
            return False
        report = json.loads(raw)
        required = {'scenario', 'target', 'build', 'run_dir', 'started', 'finished', 'seconds',
                    'ok', 'error', 'verdict', 'execution', 'steps'}
        if not isinstance(report, dict) or set(report) != required:
            return False
        execution = report['execution']
        if (report['ok'] is not True or report['error'] != '' or report['verdict'] is not None
                or not _route_execution_matches(execution, scenario.settings['game_speed'])
                or Path(report['run_dir']).resolve() != run_dir
                or report['scenario'] != scenario.name or report['target'] != 'k1'
                or report['build'] != build):
            return False
        started, finished, seconds = report['started'], report['finished'], report['seconds']
        if (any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                for value in (started, finished, seconds)) or finished < started
                or seconds != round(finished - started, 3)):
            return False
        steps = report['steps']
        if not isinstance(steps, list) or not steps or route.get('steps') != steps:
            return False
        allowed = {'index', 'step', 'status', 'seconds', 'detail', 'verdict', 'state', 'screen'}
        required_step = {'index', 'step', 'status', 'seconds', 'detail'}
        for expected_index, step in enumerate(steps, 1):
            if (not isinstance(step, dict) or not required_step <= set(step) <= allowed
                    or step['index'] != expected_index or step['status'] != 'ok'
                    or not isinstance(step['step'], str) or not step['step']
                    or not isinstance(step['detail'], str)
                    or isinstance(step['seconds'], bool) or not isinstance(step['seconds'], (int, float))
                    or not math.isfinite(step['seconds']) or step['seconds'] < 0):
                return False
            if any(name in step and step[name] is not None and not isinstance(step[name], dict)
                   for name in ('verdict', 'state', 'screen')):
                return False
        if len(steps) != len(scenario.steps) or any(
                step['index'] != expected.index or step['step'] != expected.describe()
                for step, expected in zip(steps, scenario.steps)):
            return False
        return route.get('predicates_passed') is True
    except (KeyError, TypeError, ValueError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False


def _route_execution_matches(execution, configured_speed) -> bool:
    if not isinstance(execution, dict):
        return False
    required = {'game_speed_requested', 'game_speed_effective'}
    optional = {'game_speed_restored', 'game_speed_retained'}
    if not required <= set(execution) <= required | optional:
        return False
    if 'game_speed_restored' in execution and 'game_speed_retained' in execution:
        return False
    values = list(execution.values())
    if any(isinstance(value, bool) or not isinstance(value, (int, float))
           or not math.isfinite(value) or not 0 < value <= 16 for value in values):
        return False
    if not math.isclose(execution['game_speed_requested'], execution['game_speed_effective'],
                        rel_tol=0.0, abs_tol=1e-6):
        return False
    if (isinstance(configured_speed, bool) or not isinstance(configured_speed, (int, float))
            or not math.isclose(execution['game_speed_requested'], configured_speed,
                                rel_tol=0.0, abs_tol=1e-6)):
        return False
    if ('game_speed_retained' in execution and not math.isclose(
            execution['game_speed_retained'], execution['game_speed_effective'],
            rel_tol=0.0, abs_tol=1e-6)):
        return False
    return True
