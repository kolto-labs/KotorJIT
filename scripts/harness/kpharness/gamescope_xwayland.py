"""Owned headless Gamescope/Xwayland lease for the Linux Wine adapter."""
from __future__ import annotations

import json
import hashlib
import errno
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping

from .display_backends import GAMESCOPE_BACKEND, ProcessIdentity, process_relationship, process_start
from .gamescope_snapshot import assert_persistable_evidence
from .gamescope_processes import (process_ids, process_state, verify_ancestry, verify_private_xwayland,
                                  establish_subreaper, subreaper_enabled, signal_identity)
from .gamescope_socket import cleanup_socket_node, canonical_lock_guard

_DISPLAY = re.compile(r"^:(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*))?$")
_SOFTWARE = re.compile(r"llvmpipe|softpipe|swrast|software rasterizer", re.I)
_SOFTWARE_KEYS = {"LIBGL_ALWAYS_SOFTWARE", "GALLIUM_DRIVER", "LP_NUM_THREADS"}
_ENV_EXACT = {"PATH", "HOME", "USER", "LOGNAME", "LANG", "TZ", "TMPDIR", "XDG_RUNTIME_DIR",
              "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "WINEPREFIX", "WINEARCH",
              "WINEDEBUG", "WINEDLLOVERRIDES", "SCRIPTFORGE_HARNESS_PORT", "SDL_VIDEODRIVER"}


def isolated_environment(source: Mapping[str, str], authority: Mapping[str, str]) -> Mapping[str, str]:
    """Build a child environment without borrowing desktop authority."""
    allowed = {key: value for key, value in source.items()
               if (key in _ENV_EXACT or key.startswith("LC_")) and key not in _SOFTWARE_KEYS}
    for key in ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY"):
        value = authority.get(key)
        if value:
            allowed[key] = value
    return MappingProxyType(allowed)


def parse_renderer(text: str) -> dict:
    fields = {}
    for line in text.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip().casefold()] = value.strip()
    renderer = fields.get("opengl renderer string", "")
    direct = fields.get("direct rendering", "").casefold() == "yes"
    accelerated = fields.get("accelerated", "").casefold() == "yes"
    if not renderer or not direct or not accelerated or _SOFTWARE.search(renderer):
        raise RuntimeError("renderer probe did not prove direct accelerated hardware rendering")
    return {"status": "accelerated", "probe": "renderer.txt", "renderer": renderer,
            "direct": direct, "accelerated": accelerated}


def process_authority(pid: int, *, proc_root: Path = Path("/proc")) -> Mapping[str, str]:
    pairs = (proc_root / str(pid) / "environ").read_bytes().split(b"\0")
    parsed = {}
    for pair in pairs:
        if b"=" in pair:
            key, value = pair.split(b"=", 1)
            name = key.decode("utf-8", "strict")
            if name in {"DISPLAY", "XAUTHORITY", "WAYLAND_DISPLAY"}:
                parsed[name] = value.decode("utf-8", "strict")
    return parsed


def readiness_child_command(path: Path, *, runtime: Path | None = None) -> list[str]:
    runtime = (runtime or Path(__file__).resolve().parents[1]).resolve()
    bootstrap = ("import runpy,sys;sys.path.insert(0," + repr(str(runtime)) + ");"
                 "runpy.run_module('kpharness.gamescope_xwayland',run_name='__main__')")
    return [str(Path(sys.executable).resolve()), "-I", "-S", "-B", "-c", bootstrap,
            "--ready-child", str(path)]


class GamescopeXwaylandLease:
    adapter_id = GAMESCOPE_BACKEND

    def __init__(self, run_dir: Path, width: int, height: int, *, deadline: float = 20.0,
                 source_env: Mapping[str, str] | None = None,
                 popen: Callable[..., object] = subprocess.Popen,
                 run: Callable[..., object] = subprocess.run,
                 monotonic: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep,
                 start_reader: Callable[[int], str] = process_start,
                 relationship_reader: Callable[[int], tuple[int, int, int, str]] = process_relationship,
                 authority_exists: Callable[[Path], bool] = Path.is_file,
                 authority_reader: Callable[[int], Mapping[str, str]] = process_authority,
                 pid_reader: Callable[[], list[int]] = process_ids,
                 state_reader: Callable[[int], str] = process_state,
                 xwayland_verifier: Callable[..., dict] = verify_private_xwayland,
                 controller_factory: Callable = establish_subreaper,
                 cleanup_lock_guard: Callable = canonical_lock_guard):
        if width <= 0 or height <= 0 or width % 2 or height % 2:
            raise ValueError("Gamescope geometry must be positive and even")
        self.run_dir, self.width, self.height = Path(run_dir), width, height
        self.deadline = deadline
        self.lease_id = "gamescope-" + uuid.uuid4().hex
        self._source_env = dict(os.environ if source_env is None else source_env)
        self._popen, self._run = popen, run
        self._monotonic, self._sleep, self._start_reader = monotonic, sleep, start_reader
        self._relationship_reader, self._authority_exists = relationship_reader, authority_exists
        self._authority_reader = authority_reader
        self._pid_reader, self._state_reader = pid_reader, state_reader
        self._xwayland_verifier = xwayland_verifier
        self._controller_factory = controller_factory
        self._cleanup_lock_guard = cleanup_lock_guard
        self.controller = None
        self.xwayland_candidates = []
        self.socket_cleanup = None
        self.candidate_display = None
        self.unknown_members = []
        self.reaped_children = []
        self.xwayland_access: dict | None = None
        self.boot_error: str | None = None
        self.cleanup_attempts: list[dict] = []
        self._known_members: dict[int, ProcessIdentity] = {}
        self.process = None
        self.log = None
        self.ready_path = self.run_dir / (self.lease_id + ".ready.json")
        self.environment: Mapping[str, str] = MappingProxyType({})
        self.owner: ProcessIdentity | None = None
        self.ready_child: ProcessIdentity | None = None
        self.renderer: dict | None = None
        self.pgid: int | None = None
        self.session_id: int | None = None
        self.command: tuple[str, ...] = ()
        self.readiness_elapsed = 0.0
        self.evidence_path = self.run_dir / "gamescope-lease.json"
        self.boot_phase = "created"
        self.cleanup_phase = "not_started"
        self._failure: str | None = None
        self._ready_display: str | None = None
        self._ready_xauthority_present = False
        self._parent_pid: int | None = None
        self._parent_start: str | None = None
        self._events: list[dict] = []
        self._rejected_ready_child: dict | None = None
        self._closed = False
        self._cleanup_error: BaseException | None = None

    def _write_evidence(self, *, boot_phase: str | None = None,
                        cleanup_phase: str | None = None, error: BaseException | None = None) -> None:
        """Atomically retain ownership facts, including partial boot failures.

        The receipt records only a display name and an authority presence flag;
        it never serializes an Xauthority path, cookie, or environment dump.
        """
        if boot_phase is not None:
            self.boot_phase = boot_phase
        if cleanup_phase is not None:
            self.cleanup_phase = cleanup_phase
        if error is not None:
            self._failure = f"{type(error).__name__}: {error}"
            if boot_phase == "failed" and self.boot_error is None:
                self.boot_error = self._failure
        self._events.append({"sequence": len(self._events) + 1, "monotonic_seconds": self._monotonic(),
                             "utc": datetime.now(timezone.utc).isoformat(), "boot_phase": self.boot_phase,
                             "cleanup_phase": self.cleanup_phase, "failure": self._failure})
        owner = None if self.owner is None else {"pid": self.owner.pid, "start": self.owner.start,
                                                  "parent_pid": self._parent_pid,
                                                  "parent_start": self._parent_start,
                                                  "pgid": self.pgid, "session": self.session_id}
        ready = None if self.ready_child is None else {"pid": self.ready_child.pid,
                                                        "start": self.ready_child.start,
                                                        "display": self._ready_display,
                                                        "xauthority_present": self._ready_xauthority_present}
        payload = {"schema": 1, "kind": "gamescope-xwayland-preliminary-lease",
                   "run_id": self.lease_id, "boot_phase": self.boot_phase,
                   "cleanup_phase": self.cleanup_phase, "command": list(self.command),
                   "owner": {"gamescope": owner, "ready_child": ready, "controller": self.controller},
                   "candidate_display": self.candidate_display,
                   "xwayland_candidates": self.xwayland_candidates,
                   "socket_cleanup": self.socket_cleanup, "unknown_members": self.unknown_members,
                   "known_members": [dict(pid=i.pid, start=i.start) for i in self._known_members.values()],
                   "reaped_children": self.reaped_children,
                   "rejected_ready_child": self._rejected_ready_child,
                   "failure": self.boot_error or self._failure, "boot_error": self.boot_error,
                   "cleanup_attempts": self.cleanup_attempts, "xwayland_access": self.xwayland_access,
                   "events": self._events}
        assert_persistable_evidence(payload)
        temporary = self.evidence_path.with_name("." + self.evidence_path.name + ".tmp-" + uuid.uuid4().hex)
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.evidence_path)
            descriptor = os.open(self.evidence_path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            temporary.unlink(missing_ok=True)

    def start(self) -> "GamescopeXwaylandLease":
        if self.process is not None or self._closed:
            raise RuntimeError("Gamescope lease cannot be restarted")
        self.candidate_display = None
        self.run_dir.mkdir(parents=True, exist_ok=True)
        if self.ready_path.exists():
            raise RuntimeError("refusing stale Gamescope readiness file")
        self.log = (self.run_dir / "gamescope.log").open("ab")
        child = readiness_child_command(self.ready_path)
        self.command = tuple(["gamescope", "--backend", "headless", "-w", str(self.width),
            "-h", str(self.height), "-W", str(self.width), "-H", str(self.height), "-r", "60", "--", *child])
        self._write_evidence(boot_phase="prepared")
        launch_env = dict(isolated_environment(self._source_env, {}))
        launch_env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        started = self._monotonic()
        try:
            self.controller = self._controller_factory()
            self._write_evidence(boot_phase="controller_verified")
            self.process = self._popen(list(self.command), env=launch_env, stdout=self.log,
                                      stderr=subprocess.STDOUT, start_new_session=True)
            self.owner = ProcessIdentity(self.process.pid, self._start_reader(self.process.pid))
            self._parent_pid, self.pgid, self.session_id, parent_start = self._relationship_reader(self.process.pid)
            if parent_start != self.owner.start or self.pgid != self.process.pid or self.session_id != self.process.pid:
                raise RuntimeError("Gamescope did not establish its owned process group/session")
            if self.controller and (self._parent_pid != self.controller['pid']
                                    or not subreaper_enabled()
                                    or self._start_reader(self._parent_pid) != self.controller['start']):
                raise RuntimeError("Gamescope launch differs from recorded controller")
            try:
                self._parent_start = self._start_reader(self._parent_pid) if self._parent_pid > 1 else None
            except OSError:
                self._parent_start = None
            self._write_evidence(boot_phase="leader_spawned")
            while self._monotonic() - started < self.deadline:
                if self.process.poll() is not None:
                    raise RuntimeError("owned Gamescope process exited before readiness")
                if self.ready_path.is_file():
                    raw_ready = self.ready_path.read_bytes()
                    try:
                        ready = json.loads(raw_ready)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        self._rejected_ready_child = {"raw_bytes": len(raw_ready),
                            "raw_sha256": hashlib.sha256(raw_ready).hexdigest(), "parse": "invalid_json"}
                        self._write_evidence(boot_phase="readiness_rejected")
                        raise RuntimeError("Gamescope child published malformed readiness data")
                    environment = ready.get("environment") if isinstance(ready, dict) else None
                    self._rejected_ready_child = {"raw_bytes": len(raw_ready),
                        "raw_sha256": hashlib.sha256(raw_ready).hexdigest(), "parse": "json",
                        "field_count": len(ready) if isinstance(ready, dict) else None,
                        "pid": ready.get("pid") if isinstance(ready, dict) and type(ready.get("pid")) is int else None,
                        "start": ready.get("start") if isinstance(ready, dict) and isinstance(ready.get("start"), str) else None,
                        "display": environment.get("DISPLAY") if isinstance(environment, dict)
                                   and _DISPLAY.fullmatch(str(environment.get("DISPLAY", ""))) else None}
                    # Syntactic candidate retention precedes all authority,
                    # environment and ancestry admission checks.
                    self.candidate_display = self._rejected_ready_child['display']
                    self._write_evidence(boot_phase="readiness_received")
                    break
                self._sleep(.05)
            else:
                raise RuntimeError("owned Gamescope Xwayland readiness timed out")
            if not isinstance(ready, dict):
                raise RuntimeError("Gamescope child published malformed readiness data")
            child_pid = ready.get("pid")
            child_start = ready.get("start")
            if type(child_pid) is not int or child_pid <= 0 or not isinstance(child_start, str):
                raise RuntimeError("Gamescope child published invalid process identity")
            observed_start = self._start_reader(child_pid)
            self._rejected_ready_child["observed_start"] = observed_start
            try:
                ppid, pgid, sid, start = self._relationship_reader(child_pid)
                self._rejected_ready_child["relationship"] = {"parent_pid": ppid,
                    "pgid": pgid, "session": sid, "start": start}
            except (OSError, RuntimeError, KeyError):
                self._rejected_ready_child["relationship"] = {"status": "unavailable"}
            self._write_evidence(boot_phase="readiness_received")
            authority = ready.get("environment")
            if set(ready) != {"pid", "start", "environment"} or not isinstance(authority, dict):
                raise RuntimeError("Gamescope child published malformed readiness data")
            if not set(authority).issubset({"DISPLAY", "XAUTHORITY", "WAYLAND_DISPLAY"}):
                raise RuntimeError("Gamescope child published unexpected authority")
            authority_path = Path(str(authority.get("XAUTHORITY", "")))
            has_authority = "XAUTHORITY" in authority
            display = str(authority.get("DISPLAY", ""))
            host_display = self._source_env.get("DISPLAY", "").split(".", 1)[0]
            if (not _DISPLAY.fullmatch(display) or display.split(".", 1)[0] == host_display
                    or (has_authority and (not isinstance(authority["XAUTHORITY"], str)
                        or not authority_path.is_absolute() or not self._authority_exists(authority_path)
                        or authority["XAUTHORITY"] == self._source_env.get("XAUTHORITY")))):
                raise RuntimeError("Gamescope child published invalid X11 authority")
            if observed_start != child_start:
                raise RuntimeError("Gamescope readiness child identity changed")
            chain = verify_ancestry(child_pid, self.owner, self.pgid, self.session_id,
                                    self._relationship_reader)
            if chain[0][1][3] != child_start:
                raise RuntimeError("Gamescope readiness child identity changed")
            # An ancestry-verified child is a cleanup anchor even when later
            # authority admission fails. It is not yet an admitted display child.
            self._known_members[child_pid] = ProcessIdentity(child_pid, child_start)
            self._rejected_ready_child["cleanup_identity_verified"] = True
            self._rejected_ready_child["ancestry"] = [
                {"pid": pid, "parent_pid": relation[0], "pgid": relation[1],
                 "session": relation[2], "start": relation[3]} for pid, relation in chain]
            self._write_evidence(boot_phase="readiness_received")
            if dict(self._authority_reader(child_pid)) != authority:
                raise RuntimeError("Gamescope readiness authority differs from the owned child environment")
            if has_authority:
                # A path, even a regular owned file, proves neither the server
                # endpoint nor an applicable authorization record. Keep this
                # mode closed until both contracts are implemented and tested.
                raise RuntimeError("explicit XAUTHORITY is unsupported without verified owned server authentication")
            self.candidate_display = display
            self._write_evidence(boot_phase="endpoint_candidate")
            def retain_candidates(candidates):
                self.xwayland_candidates = candidates
                self._write_evidence()
            if self.controller and not subreaper_enabled():
                raise RuntimeError("controller subreaper state changed")
            self.xwayland_access = self._xwayland_verifier(display, self.owner, self.pgid, self.session_id,
                controller=self.controller, evidence_callback=retain_candidates)
            for item in self.xwayland_access.get('ancestry', []):
                if not self.controller or item['pid'] != self.controller['pid']:
                    self._known_members[item['pid']] = ProcessIdentity(item['pid'], item['start'])
            # Revalidate the chain after reading external authority/socket evidence.
            if any(self._relationship_reader(pid) != relation for pid, relation in chain):
                raise RuntimeError("Gamescope ancestor identity changed")
            self.ready_child = ProcessIdentity(child_pid, child_start)
            self._rejected_ready_child = None
            self._ready_display = authority["DISPLAY"]
            self._ready_xauthority_present = has_authority
            self._write_evidence(boot_phase="ready_child_verified")
            client_authority = dict(authority)
            if not has_authority:
                # Suppress Xlib's implicit ~/.Xauthority fallback: this verified
                # socket accepts a setup request with no credentials.
                client_authority["XAUTHORITY"] = os.devnull
            self.environment = isolated_environment(self._source_env, client_authority)
            probe = self._run(["xdotool", "getdisplaygeometry"], env=dict(self.environment),
                              text=True, capture_output=True, timeout=5, check=False)
            if getattr(probe, "returncode", 1) != 0:
                raise RuntimeError("owned X11 display readiness probe failed")
            renderer_path = self.run_dir / "renderer.txt"
            renderer_probe = self._run(["glxinfo", "-B"], env=dict(self.environment),
                text=True, capture_output=True, timeout=10, check=False)
            renderer_path.write_text(getattr(renderer_probe, "stdout", "") + getattr(renderer_probe, "stderr", ""))
            if getattr(renderer_probe, "returncode", 1) != 0:
                raise RuntimeError("renderer probe failed")
            self.renderer = parse_renderer(renderer_path.read_text())
            self.readiness_elapsed = self._monotonic() - started
            self._write_evidence(boot_phase="ready")
            return self
        except BaseException as error:
            self._write_evidence(boot_phase="failed", error=error)
            try:
                self.close()
            except BaseException as cleanup_error:
                self._write_evidence(cleanup_phase="failed", error=cleanup_error)
            raise

    def is_alive(self) -> bool:
        if self._closed or self.process is None or self.process.poll() is not None:
            return False
        if self.ready_child is None:
            return False
        try:
            parent_live = self.owner is not None and self._start_reader(self.owner.pid) == self.owner.start
            child_live = self._start_reader(self.ready_child.pid) == self.ready_child.start
            _, pgid, session_id, _ = self._relationship_reader(self.ready_child.pid)
            if self.xwayland_access and "pid" in self.xwayland_access:
                if self._start_reader(self.xwayland_access["pid"]) != self.xwayland_access["start"]:
                    return False
            return bool(parent_live and child_live and pgid == self.pgid and session_id == self.session_id)
        except (OSError, RuntimeError, KeyError):
            return False

    def game_environment(self, base: Mapping[str, str]) -> Mapping[str, str]:
        if not self.is_alive():
            raise RuntimeError("cannot create game environment from dead display lease")
        return isolated_environment(base, self.environment)

    def receipt(self) -> dict:
        return {
            "kind": "gamescope-xwayland", "lease_id": self.lease_id,
            "owner": {
                "gamescope": None if self.owner is None else {"pid": self.owner.pid, "start": self.owner.start},
                "ready_child": None if self.ready_child is None else {"pid": self.ready_child.pid, "start": self.ready_child.start},
            },
            "process_group": {"pgid": self.pgid, "session": self.session_id,
                              "child_descends_from_gamescope": self.ready_child is not None},
            "requested_geometry": [self.width, self.height],
            "x11": {"display": self.environment.get("DISPLAY"),
                    "candidate_display": self.candidate_display, "socket_cleanup": self.socket_cleanup,
                    "xauthority_present": self._ready_xauthority_present,
                    "xauthority_mode": "authority-file" if self._ready_xauthority_present else (
                        "no-cookie-sentinel" if self.xwayland_access else "unverified"),
                    "access": self.xwayland_access},
            "readiness": {"status": "passed" if self.renderer else "pending",
                          "elapsed_seconds": self.readiness_elapsed},
            "renderer": self.renderer,
            "command": list(self.command),
            "forensic_lease_evidence": {"path": str(self.evidence_path), "retained": self.evidence_path.is_file()},
        }

    def close(self) -> None:
        if self._closed:
            return
        attempt = {"attempt": len(self.cleanup_attempts) + 1, "status": "started"}
        self.cleanup_attempts.append(attempt)
        try:
            self._close()
        except BaseException as error:
            self._cleanup_error = error
            attempt.update(status="failed", error=f"{type(error).__name__}: {error}")
            self._write_evidence(cleanup_phase="failed", error=error)
            raise
        else:
            attempt["status"] = "passed"
            self._write_evidence(cleanup_phase="passed")

    def _close(self) -> None:
        self._write_evidence(cleanup_phase="started")
        process = self.process
        if process is not None and self.socket_cleanup is None:
            self.socket_cleanup = {'status': 'unknown', 'reason': 'process cleanup pending',
                'path': '/tmp/.X11-unix/X' + self.candidate_display[1:].split('.')[0]
                        if self.candidate_display else None}

        def survivors():
            # poll() reaps the direct child before /proc survivor adjudication.
            if process is not None:
                process.poll()
            for identity in (self.owner, self.ready_child):
                if identity is not None:
                    self._known_members.setdefault(identity.pid, identity)
            found, unknown = [], []
            candidates = set(self._pid_reader()) | set(self._known_members)
            for pid in sorted(candidates):
                if self.controller and pid == self.controller['pid']:
                    continue
                known = self._known_members.get(pid)
                try:
                    parent, group, session, start = self._relationship_reader(pid)
                except (FileNotFoundError, ProcessLookupError, KeyError):
                    continue
                except (OSError, RuntimeError, ValueError, IndexError) as error:
                    if isinstance(error, OSError) and error.errno in (errno.ENOENT, errno.ESRCH):
                        continue
                    if known is not None:
                        raise RuntimeError(
                            f"cannot verify recorded Gamescope member PID {pid}: {type(error).__name__}") from error
                    continue
                if known is not None and start != known.start:
                    raise RuntimeError("refusing cleanup after Gamescope PID identity changed")
                if known is None:
                    if self.owner is None: continue
                    try:
                        chain = verify_ancestry(pid, self.owner, self.pgid, self.session_id,
                                                self._relationship_reader, controller=self.controller)
                        # A chain verified now, never another process's anchor,
                        # grants authority to this exact PID/start identity.
                        known = ProcessIdentity(pid, chain[0][1][3])
                        self._known_members[pid] = known
                    except (OSError, RuntimeError, KeyError) as error:
                        if (group, session) == (self.pgid, self.session_id):
                            unknown.append({'pid': pid, 'start': start, 'parent_pid': parent,
                                            'pgid': group, 'session': session,
                                            'failed_chain': getattr(error, 'evidence', None)})
                        continue
                # Reap only adopted direct children; Popen owns the leader status.
                if (self.controller and parent == self.controller['pid']
                        and (self.owner is None or pid != self.owner.pid)):
                    if (self._start_reader(self.controller['pid']) != self.controller['start']
                            or self._relationship_reader(pid) != (parent, group, session, start)):
                        raise RuntimeError('adopted child/controller identity changed before reap')
                    try:
                        reaped, status = os.waitpid(pid, os.WNOHANG)
                    except ChildProcessError as error:
                        raise RuntimeError('recorded adopted child is not waitable') from error
                    if reaped:
                        self.reaped_children.append({'pid': pid, 'start': start, 'wait_status': status})
                        continue
                # Zombies not reaped by this controller still prevent absence proof.
                found.append(pid)
            self.unknown_members = unknown
            return found

        live = survivors()
        if not live and process is not None and process.poll() is None and self.owner is not None:
            try:
                _, group, session, start = self._relationship_reader(self.owner.pid)
            except (OSError, RuntimeError, KeyError):
                raise RuntimeError("refusing cleanup after Gamescope PID identity changed")
            if (start, group, session) != (self.owner.start, self.pgid, self.session_id):
                raise RuntimeError("refusing cleanup after Gamescope PID identity changed")
        if live and (self.owner is None or self.pgid != self.owner.pid or self.session_id != self.owner.pid):
            raise RuntimeError("refusing cleanup without recorded Gamescope group identity")
        for sig in (signal.SIGTERM, signal.SIGKILL):
            if not live:
                break
            # Pin and recheck each independently verified identity before signalling.
            live = survivors()
            if not live:
                break
            for pid in live:
                try:
                    self._relationship_reader(pid)
                except (FileNotFoundError, ProcessLookupError, KeyError):
                    continue
                signal_identity(self._known_members[pid], sig, self._relationship_reader)
            deadline = self._monotonic() + 5
            live = survivors()
            while live and self._monotonic() < deadline:
                self._sleep(.05)
                live = survivors()
        if live:
            raise RuntimeError("owned Gamescope process group survived SIGKILL")
        if process is not None and process.poll() is None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired as error:
                raise RuntimeError("Gamescope leader did not reap after group termination") from error
        if self.unknown_members:
            raise RuntimeError("refusing cleanup without a surviving owned identity for observed group members")
        if self.xwayland_access and self.xwayland_access.get('pathname_node'):
            self.socket_cleanup = {}
            def owned_absent():
                if survivors() or self.unknown_members:
                    raise RuntimeError('owned or unknown Gamescope members remain')
            cleanup_socket_node(self.xwayland_access['pathname_node'], owned_absent=owned_absent,
                lock_guard=self._cleanup_lock_guard, evidence=self.socket_cleanup)
        elif self.candidate_display and not self.xwayland_access:
            # Failed admission grants no node deletion authority. Retain it and
            # explicitly fail cleanup if the candidate path or transport remains.
            from .gamescope_socket import socket_rows
            node = Path('/tmp/.X11-unix/X' + self.candidate_display[1:].split('.')[0])
            self.socket_cleanup = {'status': 'unadmitted', 'path': str(node)}
            try:
                node.lstat()
                node_present = True
            except FileNotFoundError:
                node_present = False
            if socket_rows(str(node)) or node_present:
                raise RuntimeError('unadmitted candidate X11 endpoint remains; no unlink authority')
            self.socket_cleanup['status'] = 'already_absent'
        elif self.process is not None and not self.xwayland_access:
            self.socket_cleanup = {'status': 'unknown', 'reason': 'launched without an established candidate display'}
            raise RuntimeError('candidate display unknown after Gamescope launch; socket absence unproven')
        if self.log is not None:
            self.log.close(); self.log = None
        self.ready_path.unlink(missing_ok=True)
        self._closed = True


def _ready_child(path: Path) -> None:
    environment = {key: os.environ[key] for key in ("DISPLAY", "XAUTHORITY", "WAYLAND_DISPLAY") if os.environ.get(key)}
    pid = os.getpid()
    payload = {"pid": pid, "start": process_start(pid), "environment": environment}
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload) + "\n")
    temporary.replace(path)
    signal.pause()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--ready-child":
        _ready_child(Path(sys.argv[2]))
    else:
        raise SystemExit(2)
