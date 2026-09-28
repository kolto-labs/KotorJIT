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
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping, Protocol, Sequence


GAMESCOPE_BACKEND = "linux-wine-k1-gamescope"
SOFTWARE_BACKEND = "linux-wine-k1"
GAMESCOPE_TOOLS = ("gamescope", "glxinfo", "xdotool", "ffmpeg")
_WINDOW_ID = re.compile(r"^0x[1-9a-f][0-9a-f]*$")


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
        "ffmpeg-x11grab-window-id", "x11-xdotool", "glxinfo-B",
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


def schema2_receipt(*, facts: HostFacts, capabilities: BackendCapabilities,
                    lease: DisplayLease, window: OwnedWindow, recorder: Mapping[str, object],
                    route_passed: bool, console_correlated: bool, cleanup: Mapping[str, str],
                    source_unchanged: bool, inputs_unchanged: bool,
                    visual_status: str = "pending", route_receipt: Mapping[str, object] | None = None) -> dict:
    """Snapshot the backend evidence chain without allowing media to self-certify."""
    capture = copy.deepcopy(recorder.get("capture"))
    cadence = copy.deepcopy(recorder.get("cadence"))
    media = copy.deepcopy(recorder.get("media"))
    cleanup_snapshot = dict(cleanup)
    command = capture.get("command", []) if isinstance(capture, dict) else []
    required = ("-f", "-video_size", "-framerate", "-window_id", "-i")
    parsed = {}
    argv_valid = isinstance(command, (list, tuple)) and all(isinstance(item, str) for item in command)
    if argv_valid:
        for flag in required:
            indexes = [index for index, item in enumerate(command) if item == flag]
            if len(indexes) != 1 or indexes[0] + 1 >= len(command):
                argv_valid = False; break
            parsed[flag] = command[indexes[0] + 1]
    identities_match = bool(
        capabilities.adapter_id == lease.adapter_id
        and window.lease_id == lease.lease_id
        and window.display == lease.environment.get("DISPLAY")
        and isinstance(capture, dict)
        and capture.get("lease_id") == lease.lease_id
        and capture.get("window_id") == window.window_id
        and capture.get("input") == window.display
        and capture.get("geometry_at_start") == [window.width, window.height]
        and argv_valid
        and parsed.get("-f") == "x11grab"
        and parsed.get("-video_size") == f"{window.width}x{window.height}"
        and parsed.get("-framerate") == str(capture.get("capture_sampling_fps_requested"))
        and parsed.get("-window_id") == window.window_id
        and parsed.get("-i") == window.display)
    admitted = capabilities.status == "admitted" and identities_match
    capture_passed = (isinstance(capture, dict) and capture.get("status") == "passed"
                      and not recorder.get("failure") and isinstance(media, dict)
                      and media.get("continuous") and media.get("status") == "retained_for_visual_review")
    cleanup_passed = (cleanup_snapshot.get("status") == "passed"
        and cleanup_snapshot.get("order") == ["recorder", "game_wine", "display"]
        and all(cleanup_snapshot.get(name) == "passed" for name in ("recorder", "game_wine", "display")))
    accepted = visual_status == "accepted"
    ok = all((admitted, route_passed, console_correlated, capture_passed, cleanup_passed,
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
        "display": copy.deepcopy(lease.receipt()), "window": copy.deepcopy(window.receipt()),
        "capture": capture, "cadence": cadence,
        "route": {**copy.deepcopy(dict(route_receipt or {})),
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
        width, height = window["geometry"]
        required = ("-f", "-video_size", "-framerate", "-window_id", "-i")
        if not isinstance(command, (list, tuple)) or not all(isinstance(item, str) for item in command):
            return False
        parsed = {}
        for flag in required:
            indexes = [i for i, item in enumerate(command) if item == flag]
            if len(indexes) != 1 or indexes[0] + 1 >= len(command): return False
            parsed[flag] = command[indexes[0] + 1]
        if (window["status"] != "verified" or window["lease_id"] != lease_id
                or window["pid"] <= 0 or not window["pid_start"] or width <= 0 or height <= 0
                or capture["status"] != "passed" or capture["lease_id"] != lease_id
                or capture["window_id"] != window["id"] or capture["input"] != xdisplay
                or capture["geometry_at_start"] != [width, height] or capture["root_capture"] is not False
                or parsed["-f"] != "x11grab" or parsed["-video_size"] != f"{width}x{height}"
                or parsed["-framerate"] != str(capture["capture_sampling_fps_requested"])
                or parsed["-window_id"] != window["id"] or parsed["-i"] != xdisplay):
            return False
        continuous = media["continuous"]
        if (media["status"] != "retained_for_visual_review" or not continuous["path"]
                or not continuous["sha256"] or route["status"] != "passed"
                or route["physical_console_correlated"] is not True
                or preservation != {"source_unchanged": True, "inputs_unchanged": True}
                or cleanup.get("status") != "passed"
                or cleanup.get("order") != ["recorder", "game_wine", "display"]
                or any(cleanup.get(name) != "passed" for name in ("recorder", "game_wine", "display"))):
            return False
        if require_completion:
            if not isinstance(route.get("report"), Mapping) or not route["report"].get("sha256"):
                return False
            started = datetime.datetime.fromisoformat(receipt["started_utc"])
            finished = datetime.datetime.fromisoformat(receipt["finished_utc"])
            if finished < started or not receipt.get("run_dir"):
                return False
        return True
    except (KeyError, TypeError, ValueError, IndexError):
        return False
