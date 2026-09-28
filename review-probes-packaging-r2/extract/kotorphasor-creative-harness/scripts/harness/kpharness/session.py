"""GameSession: stage a writable tree, boot the game headless, connect, tear down.

The boot never scans for a window and never waits a fixed time. It is done
when the channel answers `status` with the build the target expects. Until
then the session watches the things that can go wrong before the listener
exists: the process dying, Wine's loader failing, the runtime refusing to
install.

Staging. The game is never copied (the K2 depot is tens of gigabytes).
tmp/<target>_harness/ is an overlay: real directories where the game or the
runtime writes, symlinks for everything else. Trees left by the earlier
harness (tmp/k1_harness as a full copy, tmp/k2_harness as an overlay) are
reused as they are. The runtime is installed the way
scripts/install_to_game.sh does it: the proxy replaces binkw32.dll and the
original is kept as binkw32_real.dll; on the ELF libkphasor.so is preloaded.

Locking. One display, one game, one owner. The lock file holds the owning
pid and that pid's start time, the same four lines scripts/harness/lock.sh
writes, so the two can see each other's locks. A dead or recycled pid is
reclaimed without a person. An orphan Xvfb lock or temporary lock in /tmp is
not reclaimable by pid, so display selection skips those numbers.

Logs. Every run gets tmp/<target>_harness/runs/<timestamp>/ and nothing in
it is deleted by the next run; the earlier harness overwrote its logs and
lost the evidence of the failures it was trying to explain.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import shlex
import signal
import subprocess
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import discover, targets as T
from .client import Channel, ChannelError
from .resources import Resource

Log = Callable[[str], None]

# Environment the desktop session leaks into a child. Wine's portal calls
# would otherwise register against the real session bus (see
# scripts/harness/env_isolate.sh).
STRIP_ENV = (
    "DBUS_SESSION_BUS_ADDRESS", "WAYLAND_DISPLAY", "XDG_SESSION_TYPE",
    "XDG_SESSION_DESKTOP", "XDG_CURRENT_DESKTOP", "XDG_SESSION_PATH",
    "XDG_SESSION_CLASS", "XDG_SESSION_ID", "QT_WAYLAND_RECONNECT",
    "SDL_VIDEODRIVER", "KONSOLE_DBUS_SERVICE", "KONSOLE_DBUS_SESSION",
    "KONSOLE_DBUS_WINDOW", "KONSOLE_DBUS_ACTIVATION_COOKIE",
    "PROTON_ENABLE_WAYLAND",
)

# What the crash oracle reads in the game's stderr and the runtime log.
WINE_FATAL = re.compile(r"wine: Unhandled|starting debugger|could not load|"
                        r"err:module|Application could not be started")
RUNTIME_FATAL = re.compile(r"fault in hook body|\[fault\] unrecoverable")
RUNTIME_REFUSAL = re.compile(r"refusing to install")
STEAM_REQUIRED = re.compile(r"This game needs Steam|SteamAPI_Init\(\) failed", re.I)

# How many times a boot may launch the game, and how long it settles between
# attempts. Fresh prefixes can need more than one retry while the platform tears
# itself down; this default leaves room for a second retry while still staying
# bounded.
# Wine/Xvfb can lose the first several launches while a touched prefix settles.
# Keep this bounded, but allow a reliable recovery window for fresh prefixes.
BOOT_ATTEMPTS = 5
BOOT_RETRY_SETTLE = 3.0


class BootFailure(Exception):
    """The game did not reach a live channel. `reason` is the class of failure."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


class LockHeld(Exception):
    pass


def _quiet(_: str) -> None:
    pass


# ------------------------------------------------------------- utilities --

def pid_start(pid: int) -> str:
    """Start time in jiffies from /proc, or "" when the pid is gone."""
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            data = f.read().decode("latin-1")
        # The comm field may hold spaces; the fields after the closing paren
        # are positional. Start time is field 22 overall.
        after = data[data.rindex(")") + 2:].split()
        return after[19]
    except (OSError, ValueError, IndexError):
        return ""


def pids_by_name(name: str) -> List[int]:
    """Exact process-name match, the equivalent of pgrep -x.

    Never -f: an unrelated job on this machine carries the game's path in
    its argv and a substring match would kill it.
    """
    out: List[int] = []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return out
    for e in entries:
        if not e.isdigit():
            continue
        try:
            with open(f"/proc/{e}/comm", "rb") as f:
                comm = f.read().decode("latin-1").strip()
        except OSError:
            continue
        # comm is truncated to 15 characters by the kernel.
        if comm == name or (len(name) > 15 and comm == name[:15]):
            out.append(int(e))
    return out


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def display_in_use(n: int, tmp: Path = Path("/tmp")) -> bool:
    """Whether Xvfb must not be started on display ``n``.

    Xorg first creates `.tX<n>-lock`, then promotes it to `.X<n>-lock`.
    A failed promotion can leave only the temporary lock, which is still an
    exclusive claim: choosing that display produces a delayed boot failure.
    ``tmp`` is injectable for offline regression tests; production callers
    retain the `/tmp` default.
    """
    return (tmp / f".X{n}-lock").exists() or (tmp / f".tX{n}-lock").exists() or \
        (tmp / ".X11-unix" / f"X{n}").exists()


def preflight_tmp_write() -> Optional[str]:
    """Xvfb writes /tmp/.X<n>-lock first; a full tmpfs looks like an Xvfb bug."""
    # A one-byte probe can still succeed when the user's tmpfs quota is at its
    # byte limit: Xorg subsequently asks xkbcomp to create a keymap and that
    # larger write fails.  Check the per-user quota too, so we choose a known
    # live display before staging or launching anything.
    quota_full = False
    quota_detail = ""
    try:
        q = subprocess.run(["quota", "-s"], capture_output=True, text=True,
                           timeout=2, check=False)
        for line in q.stdout.splitlines():
            fields = line.split()
            if len(fields) < 4 or fields[0] != "tmpfs":
                continue
            used = _human_size(fields[1])
            limit = _human_size(fields[3])
            if used is not None and limit is not None and limit > 0 and used >= limit:
                quota_full = True
                quota_detail = line.strip()
                break
    except (OSError, subprocess.SubprocessError):
        pass
    if quota_full:
        return ("/tmp user quota is full"
                + (f" ({quota_detail})" if quota_detail else "")
                + "; Xvfb needs it for its lock file and keymap")
    probe = Path(f"/tmp/.kp_harness_write_probe.{os.getpid()}")
    try:
        probe.write_text("ok")
        probe.unlink()
        return None
    except OSError as e:
        quota = ""
        try:
            q = subprocess.run(["quota", "-s"], capture_output=True, text=True,
                               timeout=2, check=False)
            lines = [line.strip() for line in q.stdout.splitlines() if "tmpfs" in line]
            if lines:
                quota = f"; quota: {lines[-1]}"
        except (OSError, subprocess.SubprocessError):
            pass
        return f"cannot write to /tmp ({e}){quota}; Xvfb needs it for its lock file"


def _human_size(value: str) -> Optional[int]:
    """Parse the compact quantities emitted by ``quota -s``."""
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([KMGTPE]?)\*?", value, re.I)
    if not match:
        return None
    powers = {"": 0, "K": 1, "M": 2, "G": 3, "T": 4, "P": 5, "E": 6}
    return int(float(match.group(1)) * (1024 ** powers[match.group(2).upper()]))


def wine_isolation_enabled() -> bool:
    return os.environ.get("KP_WINE_TMP_ISOLATE", "1") != "0" and bool(shutil.which("bwrap"))


def wine_tmp_roots() -> List[Path]:
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    return [runtime / "kpharness", Path("/dev/shm") / f"kpharness-{os.getuid()}"]


def wine_tmp_backing(game_dir: Path, wineprefix: Path) -> Path:
    """Return the stable private ``/tmp`` backing for one Wine prefix."""
    del game_dir
    key = hashlib.sha256(str(wineprefix.resolve()).encode()).hexdigest()[:16]
    for root in wine_tmp_roots():
        runtime = root.parent
        if not runtime.is_dir() or not os.access(runtime, os.W_OK | os.X_OK):
            continue
        try:
            backing = root / f"wine-{key}"
            backing.mkdir(parents=True, exist_ok=True, mode=0o700)
            return backing
        except OSError:
            continue
    raise BootFailure("wine tmp", "no writable XDG runtime directory or /dev/shm for Wine private /tmp")


def wine_command(command: List[str], game_dir: Path, wineprefix: Path, *,
                 tmp_dir: Optional[Path] = None, isolate: Optional[bool] = None,
                 die_with_parent: bool = True) -> List[str]:
    """Run Wine in the harness's persistent private ``/tmp`` when possible."""
    isolate = wine_isolation_enabled() if isolate is None else isolate
    if not isolate:
        return command
    if not shutil.which("bwrap"):
        raise BootFailure("wine tmp", "recorded private Wine /tmp requires bwrap; refusing host /tmp")
    tmp_dir = tmp_dir or wine_tmp_backing(game_dir, wineprefix)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    # Bind the private /tmp before paths below /tmp.  A later mount on /tmp
    # hides every earlier child mount, which otherwise makes a relocated game
    # and Wine prefix appear absent to Wine despite existing on the host.
    wrapped = ["bwrap"]
    if die_with_parent:
        wrapped.append("--die-with-parent")
    wrapped += ["--ro-bind", "/", "/",
               "--bind", str(tmp_dir), "/tmp",
               "--bind", str(game_dir), str(game_dir),
               "--bind", str(wineprefix), str(wineprefix)]
    # The root mount is read-only so the only writable filesystem state is
    # the harness staging tree and its persistent Wine socket directory.
    # Mesa still needs to open its render nodes read-write, including when
    # llvmpipe falls back through the host's Vulkan loader.
    dri = Path("/dev/dri")
    if dri.is_dir():
        wrapped += ["--dev-bind", str(dri), str(dri)]
    x11 = Path("/tmp/.X11-unix")
    if x11.is_dir():
        wrapped += ["--dir", "/tmp/.X11-unix", "--ro-bind", str(x11), str(x11)]
    return wrapped + ["--"] + command


def tune_ini(path: Path, keys: List[T.IniKey], log: Log = _quiet) -> None:
    """Force `keys` in an ini, keeping its line endings and everything else.

    Existing copies are still set in place everywhere (K2 repeats FullScreen
    in multiple sections), but the requested section is always populated too.
    Some real K1 INIs contain stale unsectioned keys after a damaged or
    hand-edited section; treating those as a substitute for [Graphics Options]
    left the renderer with no authoritative Width/Height.  A missing section
    key is appended under the named section, which is created at the end if
    absent.
    """
    if path.is_file():
        raw = path.read_bytes()
    else:
        raw = b""
    nl = "\r\n" if b"\r\n" in raw else "\n"
    lines = raw.decode("latin-1").splitlines()
    for section, key, value in keys:
        hit = False
        for i, line in enumerate(lines):
            m = re.match(r"^\s*([^=;#\[]+?)\s*=", line)
            if m and m.group(1).strip().lower() == key.lower():
                lines[i] = f"{key}={value}"
                hit = True
        header = f"[{section}]"
        idx = next((i for i, l in enumerate(lines) if l.strip().lower() == header.lower()), None)
        section_has_key = False
        if idx is not None:
            end = next((j for j in range(idx + 1, len(lines))
                        if re.match(r"^\s*\[[^]]+\]\s*$", lines[j])), len(lines))
            section_has_key = any(
                (m := re.match(r"^\s*([^=;#\[]+?)\s*=", lines[j]))
                and m.group(1).strip().lower() == key.lower()
                for j in range(idx + 1, end))
        if section_has_key:
            continue
        if idx is None:
            if lines and lines[-1].strip():
                lines.append("")
            lines.append(header)
            lines.append(f"{key}={value}")
        else:
            lines.insert(idx + 1, f"{key}={value}")
    path.write_bytes((nl.join(lines) + nl).encode("latin-1"))
    log(f"ini tuned: {path.name} ({len(keys)} keys)")


def write_runtime_ini(game_dir: Path, port: int, bind: str = "127.0.0.1") -> Path:
    """kotorphasor.ini next to the game. Section headers are ignored by the
    runtime, so the keys are the global harness_port and harness_bind."""
    path = game_dir / "kotorphasor.ini"
    kept: List[str] = []
    if path.is_file():
        for line in path.read_text(errors="replace").splitlines():
            s = line.strip()
            if s.startswith("[harness]") or s.startswith("harness_port") or s.startswith("harness_bind"):
                continue
            kept.append(line)
    while kept and not kept[-1].strip():
        kept.pop()
    kept += ["", "[harness]", f"harness_port = {port}", f"harness_bind = {bind}", ""]
    path.write_text("\n".join(kept))
    return path


def proxy_is_ours(dll: Path) -> bool:
    """The proxy is small and names kphasor; the real codec is ~370 KB."""
    try:
        if dll.stat().st_size >= 200000:
            return False
        return b"kphasor.dll" in dll.read_bytes()
    except OSError:
        return False


RUNTIME_WRITTEN_FILES = {"kphasor.dll", "steam_appid.txt", "kotorphasor.ini",
                         "kotorphasor.log", "kotorphasor-proxy.log"}


def overlay_tree(src: Path, dst: Path, writable: List[str], copy_files: bool,
                 depth: int = 0, log: Log = _quiet) -> None:
    """Symlink `src`'s entries into `dst`; real copies for `writable` dirs.

    Top-level files are copied when `copy_files` (the ELF and its bundled
    libraries must sit in a real directory next to each other; RPATH is
    ".") and symlinked otherwise. Writable directories are copied so the
    game finds its existing saves and can add to them without touching the
    install.
    """
    dst.mkdir(parents=True, exist_ok=True)
    for entry in sorted(src.iterdir()):
        target = dst / entry.name
        if target.exists() or target.is_symlink():
            continue
        if entry.is_dir():
            if entry.name.lower() in [w.lower() for w in writable]:
                shutil.copytree(entry, target, symlinks=True)
                log(f"  copied writable dir {entry.name}")
            else:
                target.symlink_to(entry)
        else:
            if (copy_files or entry.suffix.lower() == ".ini"
                    or entry.name.lower() in RUNTIME_WRITTEN_FILES):
                shutil.copy2(entry, target)
            else:
                target.symlink_to(entry)


# ---------------------------------------------------------------- session --

@dataclass
class SessionInfo:
    """What `boot` leaves behind so `status`, `exec` and `down` can find it."""
    target: str
    staged: str
    game_dir: str
    save_dir: str
    run_dir: str
    display: int
    port: int
    xvfb_pid: int
    launcher_pid: int
    lock_path: str
    wineprefix: str = ""
    wine_tmp_dir: str = ""
    wine_tmp_isolated: Optional[bool] = None
    process_name: str = ""
    build: str = ""
    started: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return dict(self.__dict__)

    @staticmethod
    def from_dict(d: Dict) -> "SessionInfo":
        return SessionInfo(**{k: d[k] for k in SessionInfo.__dataclass_fields__ if k in d})


def channel_timeout() -> float:
    """Seconds to wait for one channel reply. 30 s is plenty on an idle host;
    a world observation on a host at load 100+ has taken 90 s, and a reply that
    arrives late is not a hang. KP_CHANNEL_TIMEOUT overrides."""
    try:
        return max(5.0, float(os.environ.get("KP_CHANNEL_TIMEOUT", "30")))
    except ValueError:
        return 30.0


class GameSession:
    """One headless game. Use as a context manager or call boot()/teardown()."""

    def __init__(self, target: str, *, build_dir: Optional[str] = None,
                 display: Optional[int] = None, port: Optional[int] = None,
                 boot_timeout: float = 300.0, force: bool = False,
                 wine_debug: Optional[str] = None, log: Optional[Log] = None,
                 screen: tuple = (T.SCREEN_W, T.SCREEN_H), staged: Optional[str] = None,
                 wineprefix: Optional[str] = None, reset_saves: bool = False,
                 persistent: bool = False):
        self.target = T.get(target)
        self.root = discover.repo_root()
        self.build_dir = discover.build_dir(build_dir)
        self.requested_display = display
        self.requested_port = port
        self.boot_timeout = boot_timeout
        self.force = force
        self.wine_debug = wine_debug
        self.screen = screen
        self.reset_saves = reset_saves
        self.persistent = persistent
        self._log_fn = log or print

        self.staged: Path = (Path(staged).expanduser() if staged else self._stage_root()).resolve()
        self._wineprefix: Optional[Path] = (
            Path(wineprefix).expanduser().resolve() if wineprefix else self._wineprefix_root())
        self.run_dir: Path = self.staged / "runs" / time.strftime("%Y%m%d-%H%M%S")
        self.data_dir: Optional[Path] = None      # install's data tree
        self.game_dir: Optional[Path] = None      # where the runtime's game_dir is
        self.save_dir: Optional[Path] = None
        self.xdg_home: Optional[Path] = None
        self.display: int = -1
        self.port: int = 0
        self.lock_path: Optional[Path] = None
        # The display lock protects Xvfb.  Scenario runs additionally need a
        # lock for their shared staged game tree: they reset its input saves.
        self.stage_lock_path: Optional[Path] = None
        self.xvfb: Optional[subprocess.Popen] = None
        self.wm: Optional[subprocess.Popen] = None
        self.steam: Optional[subprocess.Popen] = None
        self.launcher: Optional[subprocess.Popen] = None
        # Set only by capture_owned_game_window() on this session's own Xvfb.
        # A physical-input adapter must not discover windows on a reused display.
        self.capture_window: Optional[str] = None
        self._capture_window_pid: Optional[int] = None
        self.env: Dict[str, str] = {}
        self.channel: Optional[Channel] = None
        self.build: str = ""
        self._stderr_path: Optional[Path] = None
        self._stderr_offset = 0
        self._runtime_log_offset = 0
        self._stack_dumped = False
        self._session_log = None
        self._wine_tmp_dir: Optional[Path] = None
        self._wine_tmp_isolated: Optional[bool] = None

    # ---------------------------------------------------------- logging --
    def log(self, msg: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        self._log_fn(line)
        if self._session_log is not None:
            try:
                self._session_log.write(line + "\n")
                self._session_log.flush()
            except OSError:
                pass

    # ---------------------------------------------------------- staging --
    def _stage_root(self) -> Path:
        override = os.environ.get("KP_STAGED_DIR")
        if override:
            return Path(override).expanduser().resolve()
        tmp = self.root / "tmp"
        preferred = tmp / f"{self.target.name}_harness"
        if preferred.is_dir():
            return preferred
        legacy = tmp / f"{self.target.game}_harness"
        if legacy.is_dir():
            return legacy
        return preferred

    @property
    def runtime_log(self) -> Path:
        assert self.game_dir is not None
        return self.game_dir / "kotorphasor.log"

    @property
    def wineprefix(self) -> Path:
        assert self._wineprefix is not None
        return self._wineprefix

    def _wineprefix_root(self) -> Path:
        override = os.environ.get("KP_WINEPREFIX")
        if override:
            return Path(override).expanduser().resolve()
        shared = self.root / "tmp" / "wineprefix-k1"
        if self.target.name == "k1" or shared.is_dir():
            return shared
        return self.root / "tmp" / f"wineprefix-{self.target.name}"

    def stage(self, resources: Optional[List[Resource]] = None) -> None:
        """Make tmp/<target>_harness/ usable: overlay, runtime, inis."""
        t = self.target
        data, install = self._validate_staged_path()
        self.data_dir = data
        staged = self.staged
        fresh = (not staged.is_dir()
                 or not any(p.name != ".kpharness-stage.lock" for p in staged.iterdir()))
        staged.mkdir(parents=True, exist_ok=True)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._session_log = open(self.run_dir / "session.log", "a")
        self.log(f"target {t.name}: data {data}")
        self.log(f"staged tree {staged}{' (new)' if fresh else ' (reused)'}")

        if t.name == "k1":
            if fresh:
                overlay_tree(install, staged, list(t.writable_dirs), copy_files=False, log=self.log)
            self.game_dir = staged
            self._recover_k1_save_backup()
        elif t.name == "k2-wine":
            # The exe lives in the data dir: that is the runtime's game_dir.
            sa = staged / "steamassets"
            if not sa.is_dir():
                overlay_tree(data, sa, list(t.writable_dirs), copy_files=False, log=self.log)
            self.game_dir = sa
        else:
            if fresh or not (staged / t.exe).is_file():
                overlay_tree(install, staged, list(t.writable_dirs), copy_files=True, log=self.log)
            sa = staged / "steamassets"
            if not sa.is_dir():
                overlay_tree(data, sa, list(t.writable_dirs), copy_files=False, log=self.log)
            self.game_dir = staged
            self.xdg_home = staged / "xdg"
            self.xdg_home.mkdir(exist_ok=True)
            self._ensure_miles_case_symlinks()

        if self.reset_saves and t.name == "k1":
            self._reset_k1_saves(install)

        self._stage_resources(install, resources or [])

        for d in t.writable_dirs:
            p = self.game_dir / d
            if p.is_symlink():
                # An older overlay linked it; the game must write here.
                real = p.resolve()
                p.unlink()
                shutil.copytree(real, p, symlinks=True)
            p.mkdir(parents=True, exist_ok=True)

        # Older overlay versions linked every non-INI file. Materialize files
        # that the loader/runtime write before those writes can reach source.
        private_names = set(RUNTIME_WRITTEN_FILES)
        private_names.update(p.name for p in self.game_dir.glob("*.ini"))
        for name in private_names:
            p = self.game_dir / name
            if p.is_symlink():
                source = p.resolve()
                p.unlink()
                if source.is_file():
                    shutil.copy2(source, p)

        exe = self._ensure_executable(install)
        self.log(f"executable {exe}")
        self._install_runtime()
        self._tune_inis()
        if t.steam_appid:
            (exe.parent / "steam_appid.txt").write_text(t.steam_appid + "\n")

    def _reset_k1_saves(self, install: Path) -> None:
        """Replace the reused K1 staging save tree with the source baseline."""
        assert self.game_dir is not None
        source = install / self.target.save_dir_name
        destination = self.game_dir / self.target.save_dir_name
        if not source.is_dir():
            raise BootFailure("save baseline", f"source save directory is missing: {source}")
        if pids_by_name(self.target.process_name):
            raise BootFailure("save baseline", "refusing to replace Saves while K1 is running")

        temporary = destination.with_name(f".{destination.name}.kpharness-reset-{os.getpid()}")
        backup = destination.with_name(f".{destination.name}.kpharness-backup-{os.getpid()}")
        for path in (temporary, backup):
            if path.is_symlink() or path.is_file():
                path.unlink()
            elif path.exists():
                shutil.rmtree(path)
        try:
            shutil.copytree(source, temporary, symlinks=True)
            if destination.exists() or destination.is_symlink():
                destination.rename(backup)
            temporary.rename(destination)
        except OSError as e:
            if not destination.exists() and backup.exists():
                backup.rename(destination)
            raise BootFailure("save baseline", f"could not reset staged Saves: {e}") from e
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
        if backup.is_symlink() or backup.is_file():
            backup.unlink()
        elif backup.exists():
            shutil.rmtree(backup)
        self.log(f"reset staged Saves from {source}")

    def _recover_k1_save_backup(self) -> None:
        """Recover an interrupted staged-Saves swap before any normal boot.

        A reset first renames ``Saves`` aside, then publishes a fully copied
        replacement.  If the process is interrupted between those renames,
        interactive ``boot`` must retain the prior input rather than quietly
        create an empty save directory.
        """
        assert self.game_dir is not None
        destination = self.game_dir / self.target.save_dir_name
        if destination.exists() or destination.is_symlink():
            return
        backups = sorted(self.game_dir.glob(f".{destination.name}.kpharness-backup-*"),
                         key=lambda p: p.stat().st_mtime, reverse=True)
        if not backups:
            return
        try:
            backups[0].rename(destination)
        except OSError as e:
            raise BootFailure("save baseline", f"could not recover staged Saves from {backups[0]}: {e}") from e
        self.log(f"recovered interrupted staged Saves replacement from {backups[0]}")

    def _stage_resources(self, install: Path, resources: List[Resource]) -> None:
        """Materialize declared route bytes from the selected target install.

        Route resources are content-addressed by the scenario's declared
        container resource, byte count and SHA-256.  A matching staged copy
        is therefore the same verified artifact and may be reused; this keeps
        a transiently slow external game volume from preventing every later
        live run.  A missing, unreadable, or mismatched copy is never trusted:
        it is freshly extracted with kq from the declared container, verified,
        then atomically replaced before launch.
        """
        if not resources:
            return
        assert self.game_dir is not None
        resource_dir = self.game_dir / "harness-resources"
        resource_dir.mkdir(parents=True, exist_ok=True)
        seen: Dict[Path, tuple[str, int, str]] = {}
        for raw in resources:
            try:
                # Accept older Python callers through the same typed validator.
                declaration = raw if isinstance(raw, Resource) else Resource.from_legacy(raw)
                resource = declaration.source
                relative_file = Path(declaration.file)
                expected_size = declaration.size
                expected_hash = declaration.sha256
            except (KeyError, TypeError, ValueError) as e:
                raise BootFailure("route resource", f"invalid resource declaration: {e}") from e
            destination = self.game_dir / relative_file
            declaration = (resource, expected_size, expected_hash)
            if destination in seen:
                if seen[destination] != declaration:
                    raise BootFailure("route resource", f"conflicting declarations for {relative_file}")
                continue
            seen[destination] = declaration
            parts = Path(resource).parts
            container, resref = "/".join(parts[:-1]), parts[-1]
            try:
                cached = destination.read_bytes() if destination.is_file() else None
            except OSError:
                cached = None
            if (cached is not None and len(cached) == expected_size and
                    hashlib.sha256(cached).hexdigest() == expected_hash):
                self.log(f"route resource cache verified for {container}/{resref} -> {relative_file}")
                continue
            binary = self._kq_binary()
            try:
                result = subprocess.run(
                    [binary, "--install", str(install), "cat", resref, "--type", "wok",
                     "--from", container, "--raw"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=60)
            except (OSError, subprocess.SubprocessError) as e:
                raise BootFailure("route resource", f"kq extraction failed for {resource}: {e}") from e
            if result.returncode:
                detail = result.stderr.decode("utf-8", "replace").strip()[-300:]
                raise BootFailure("route resource", f"kq could not extract {resource} ({detail or result.returncode})")
            data = result.stdout
            if len(data) != expected_size or hashlib.sha256(data).hexdigest() != expected_hash:
                raise BootFailure("route resource", f"kq bytes for {resource} do not match declared size/SHA-256")
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(destination.name + ".tmp")
            try:
                temporary.write_bytes(data)
                temporary.replace(destination)
            except OSError as e:
                temporary.unlink(missing_ok=True)
                raise BootFailure("route resource", f"cannot stage {resource}: {e}") from e
            self.log(f"route resource staged from {container}/{resref} -> {relative_file}")

    def _kq_binary(self) -> str:
        candidates = [os.environ.get("KQ_BIN", ""),
                      str(self.root.parent / "bioware_projects" / "cleanhouse" / "target" / "release" / "kq"),
                      str(Path.home() / ".cargo" / "bin" / "kq"), shutil.which("kq") or ""]
        for candidate in candidates:
            if candidate and os.access(candidate, os.X_OK):
                return candidate
        raise BootFailure("route resource", "kq is required to extract declared route resources")

    def _ensure_miles_case_symlinks(self) -> None:
        """k2-native only: the ELF's DT_NEEDED entries are libMiles.so and
        libMilesMidi.so (capital M) but the depot ships the real libraries
        lowercase. A same-directory, same-name-otherwise symlink satisfies
        the loader without touching what overlay_tree already staged.
        Idempotent: an existing link (or file) at the wanted name is left
        alone, and a missing lowercase source is skipped quietly rather than
        treated as an error -- not every install necessarily needs both.
        """
        assert self.game_dir is not None
        for real_name, want_name in (("libmiles.so", "libMiles.so"),
                                     ("libmilesmidi.so", "libMilesMidi.so")):
            real = self.game_dir / real_name
            link = self.game_dir / want_name
            if link.exists() or link.is_symlink():
                continue
            if not real.is_file():
                self.log(f"miles case-fix: no {real_name} in {self.game_dir}, skipping {want_name}")
                continue
            link.symlink_to(real_name)
            self.log(f"miles case-fix: {want_name} -> {real_name}")

    def _ensure_executable(self, install: Path) -> Path:
        t = self.target
        assert self.game_dir is not None
        staged_exe = self.game_dir / t.exe
        if staged_exe.is_file():
            return staged_exe
        found = discover.executable(t, self.data_dir or install)
        if found is None:
            if t.name == "k2-wine":
                raise BootFailure("no executable",
                                  f"{t.exe} is not shipped by the depot; place one in "
                                  f"{self.game_dir} or set KP_K2_EXE")
            raise BootFailure("no executable", f"{t.exe} not found under {install}")
        shutil.copy2(found, staged_exe)
        return staged_exe

    def _install_runtime(self) -> None:
        t = self.target
        gd = self.game_dir
        assert gd is not None
        for f in t.runtime_files:
            if not (self.build_dir / f).is_file():
                raise BootFailure("runtime not built", f"missing {self.build_dir / f}")
        kp = gd / "kotorphasor"
        kp.mkdir(exist_ok=True)
        (kp / "scripts").mkdir(exist_ok=True)
        sources = [self.build_dir / f for f in t.runtime_files]
        sources += sorted((self.root / "data" / "addresses").rglob("*"))
        digest = hashlib.sha256()
        for source in sources:
            if not source.is_file():
                continue
            stat = source.stat()
            digest.update(str(source.relative_to(self.root) if source.is_relative_to(self.root)
                              else source.relative_to(self.build_dir)).encode())
            digest.update(f"\0{stat.st_size}\0{stat.st_mtime_ns}\n".encode())
        manifest = digest.hexdigest()
        installed = kp / ".installed"
        runtime = gd / ("kphasor.dll" if t.wine else "kotorphasor/libkphasor.so")
        if (installed.is_file() and installed.read_text().strip() == manifest
                and runtime.is_file() and (kp / "addresses").is_dir()
                and (not t.wine or proxy_is_ours(gd / "binkw32.dll"))):
            self.log(f"runtime already current ({manifest[:12]})")
            return
        if t.wine:
            proxy = gd / "binkw32.dll"
            real = gd / "binkw32_real.dll"
            if not proxy.exists() and not proxy.is_symlink():
                raise BootFailure("not a game directory", f"no binkw32.dll in {gd}")
            if not real.exists():
                if proxy_is_ours(proxy):
                    raise BootFailure("install state", "binkw32.dll is the proxy but "
                                      "binkw32_real.dll is missing")
                shutil.copy2(proxy, real)
                self.log("saved original binkw32.dll -> binkw32_real.dll")
            if proxy.is_symlink():
                proxy.unlink()
            runtime_dll = gd / "kphasor.dll"
            if runtime_dll.is_symlink():
                runtime_dll.unlink()
            shutil.copy2(self.build_dir / "kphasor.dll", runtime_dll)
            shutil.copy2(self.build_dir / "binkw32.dll", proxy)
        else:
            shutil.copy2(self.build_dir / "libkphasor.so", kp / "libkphasor.so")
            if t.name == "k2-native":
                self._install_k2_libglu(kp)
        addr = kp / "addresses"
        if addr.is_symlink():
            addr.unlink()
        elif addr.is_dir():
            shutil.rmtree(addr)
        shutil.copytree(self.root / "data" / "addresses", addr)
        installed.write_text(manifest + "\n")
        self.log(f"runtime installed from {self.build_dir}")

    def _install_k2_libglu(self, kp_dir: Path) -> None:
        candidates = discover.libglu_dirs()
        if not candidates:
            self.log("k2-native: no libGLU candidates discovered; skipping GLU staging")
            return
        src = candidates[0] / "libGLU.so.1"
        if not src.is_file():
            self.log(f"k2-native: no usable libGLU at {candidates[0]}; skipping GLU staging")
            return
        target_dir = kp_dir / "lib"
        target_dir.mkdir(exist_ok=True)
        dst = target_dir / "libGLU.so.1"
        if dst.is_file():
            self.log(f"k2-native: reusing staged {dst}")
            return
        try:
            shutil.copy2(src, dst)
            self.log(f"k2-native: staged {src} -> {dst}")
        except OSError as e:
            self.log(f"k2-native: failed to stage libGLU from {src}: {e}")

    def _tune_inis(self) -> None:
        t = self.target
        gd = self.game_dir
        assert gd is not None
        keys = [(s, k, v) for (s, k, v) in t.ini_keys]
        keys = [(s, k, (str(self.screen[0]) if k == "Width" else
                        str(self.screen[1]) if k == "Height" else v)) for (s, k, v) in keys]
        if t.name == "k2-native":
            src_ini = gd / "steamassets" / t.ini_name
            xdg_dir = discover.xdg_game_dir(self.xdg_home or gd, t)
            xdg_dir.mkdir(parents=True, exist_ok=True)
            self.save_dir = xdg_dir / t.save_dir_name
            self.save_dir.mkdir(exist_ok=True)
            ini = xdg_dir / t.ini_name
            if not ini.is_file() and src_ini.is_file():
                shutil.copy2(src_ini, ini)
            tune_ini(ini, keys, self.log)
            if src_ini.is_file() and not src_ini.is_symlink():
                tune_ini(src_ini, keys, self.log)
        else:
            ini = gd / t.ini_name
            if ini.is_symlink():
                real = ini.resolve()
                ini.unlink()
                shutil.copy2(real, ini)
            tune_ini(ini, keys, self.log)
            self.save_dir = gd / t.save_dir_name
            self.save_dir.mkdir(exist_ok=True)
        if t.game == "k2":
            self._seed_k2_saves()

    def _seed_k2_saves(self) -> None:
        """The K2 depot ships no save under saves/; the store's cloud copies
        under cloudsaves/<id>/ are complete save folders. Copy them in once
        so the smoke scenario has something to load."""
        assert self.save_dir is not None
        if any(p.is_dir() for p in self.save_dir.iterdir()):
            return
        cloud = self.staged / "cloudsaves"
        if not cloud.is_dir():
            return
        n = 0
        for owner in sorted(cloud.iterdir()):
            if not owner.is_dir():
                continue
            for folder in sorted(owner.iterdir()):
                if folder.is_dir() and any(f.name.lower() == "savegame.sav" for f in folder.iterdir()):
                    shutil.copytree(folder, self.save_dir / folder.name)
                    n += 1
        if n:
            self.log(f"seeded {n} save folder(s) from cloudsaves into {self.save_dir}")

    # ------------------------------------------------------------- lock --
    def _lock_dir(self) -> Path:
        return self.root / "tmp" / "harness-locks"

    def _choose_display(self) -> int:
        if self.requested_display is not None:
            return self.requested_display
        n = 100
        while n < 400:
            if not display_in_use(n) and not self._lock_live(self._lock_dir() / f"display-{n}.lock"):
                return n
            n += 1
        raise BootFailure("no display", "no free X display number between 100 and 400")

    @staticmethod
    def _read_lock(path: Path) -> Optional[Dict[str, str]]:
        try:
            lines = path.read_text().splitlines()
        except OSError:
            return None
        if len(lines) < 2:
            return None
        return {"pid": lines[0], "start": lines[1],
                "display": lines[2] if len(lines) > 2 else "",
                "what": lines[3] if len(lines) > 3 else ""}

    def _lock_live(self, path: Path) -> bool:
        info = self._read_lock(path)
        if not info:
            return False
        try:
            pid = int(info["pid"])
        except ValueError:
            return False
        return pid_start(pid) != "" and pid_start(pid) == info["start"]

    def acquire_lock(self) -> None:
        path = self._lock_dir() / f"display-{self.display}.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        info = self._read_lock(path)
        if info is not None:
            if self._lock_live(path):
                if not self.force:
                    raise LockHeld(f"display {self.display} is held by pid {info['pid']} "
                                   f"({info['what']}); re-run with --force to take it")
                self.log(f"lock: FORCE, taking display {self.display} from pid {info['pid']}")
                if info["what"]:
                    for pid in pids_by_name(info["what"]):
                        self._kill(pid)
                self._kill_xvfb_by_display(self.display)
                time.sleep(2)
            else:
                self.log(f"lock: stale (pid {info['pid']} gone or recycled), reclaiming")
        path.write_text(f"{os.getpid()}\n{pid_start(os.getpid())}\n{self.display}\n"
                        f"{self.target.process_name}\n")
        self.lock_path = path

    def acquire_stage_lock(self) -> None:
        """Serialize a resettable scenario stage for this process lifetime."""
        self._validate_staged_path()
        path = self.staged / ".kpharness-stage.lock"
        info = self._read_lock(path)
        if info is not None:
            if self._lock_live(path):
                raise LockHeld(f"staged tree {self.staged} is held by pid {info['pid']} "
                               f"({info['what']})")
            self.log(f"stage lock: stale (pid {info['pid']} gone or recycled), reclaiming")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{os.getpid()}\n{pid_start(os.getpid())}\n{self.display}\n"
                        f"{self.target.process_name}\n")
        self.stage_lock_path = path

    def _validate_staged_path(self) -> tuple[Path, Path]:
        """Resolve source identity before any stage-owned path can be written."""
        data = discover.data_dir(self.target)
        install = discover.install_root(self.target, data)
        staged = self.staged.resolve()
        self.staged = staged
        if staged == install.resolve() or staged == data.resolve():
            raise BootFailure("unsafe staged tree",
                              f"staged tree must differ from source install: {staged}")
        return data, install

    def release_lock(self) -> None:
        if self.lock_path is None:
            return
        info = self._read_lock(self.lock_path)
        if info and info["pid"] == str(os.getpid()):
            try:
                self.lock_path.unlink()
            except OSError:
                pass
        self.lock_path = None

    def release_stage_lock(self) -> None:
        if self.stage_lock_path is None:
            return
        info = self._read_lock(self.stage_lock_path)
        if info and info["pid"] == str(os.getpid()):
            try:
                self.stage_lock_path.unlink()
            except OSError:
                pass
        self.stage_lock_path = None

    # ------------------------------------------------------------- xvfb --
    def start_xvfb(self) -> None:
        w, h = self.screen
        log = open(self.run_dir / "xvfb.log", "ab")
        self.xvfb = subprocess.Popen(
            ["Xvfb", f":{self.display}", "-screen", "0", f"{w}x{h}x24", "-nolisten", "tcp"],
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if Path(f"/tmp/.X11-unix/X{self.display}").exists():
                if subprocess.run(["xdpyinfo", "-display", f":{self.display}"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  timeout=10).returncode == 0:
                    self.log(f"Xvfb up on :{self.display} (pid {self.xvfb.pid})")
                    if self.target.name == "k2-native" and shutil.which("mwm"):
                        wm_env = dict(os.environ)
                        wm_env["DISPLAY"] = f":{self.display}"
                        wm_log = open(self.run_dir / "wm.log", "ab")
                        self.wm = subprocess.Popen(["mwm"], env=wm_env,
                                                   stdout=wm_log, stderr=subprocess.STDOUT,
                                                   start_new_session=True)
                        self.log(f"mwm up for native K2 (pid {self.wm.pid})")
                    if self.target.name == "k2-native":
                        configured = os.environ.get("KP_HARNESS_STEAM_CMD", "").strip()
                        steam = Path.home() / ".local/share/Steam/steam.sh"
                        steam_cmd = shlex.split(configured) if configured else [str(steam), "-silent"]
                        # Reuse the user's already authenticated client.  A
                        # second steam.sh invocation merely forwards to the
                        # existing client, often on the real display, and
                        # leaves the game racing SteamAPI initialisation.
                        existing = pids_by_name("steam")
                        if existing:
                            self.log(f"reusing existing Steam client (pid {existing[0]})")
                        elif steam_cmd and (configured or steam.is_file()):
                            steam_env = dict(os.environ)
                            steam_env["DISPLAY"] = f":{self.display}"
                            steam_env["SDL_VIDEODRIVER"] = "x11"
                            steam_log = open(self.run_dir / "steam.log", "ab")
                            self.steam = subprocess.Popen(steam_cmd, env=steam_env,
                                                          stdout=steam_log, stderr=subprocess.STDOUT,
                                                          start_new_session=True)
                            self.log(f"Steam CLI up for native K2 (pid {self.steam.pid}): {' '.join(steam_cmd)}")
                            # Steam's IPC endpoint is created asynchronously;
                            # give Steamworks a short, bounded handshake window
                            # before the ELF is launched below.
                            time.sleep(float(os.environ.get("KP_HARNESS_STEAM_SETTLE", "5")))
                    return
            if self.xvfb.poll() is not None:
                break
            time.sleep(0.3)
        raise BootFailure("xvfb", f"Xvfb :{self.display} did not come up; see {log.name}")

    def _kill_xvfb_by_display(self, n: int) -> None:
        for pid in pids_by_name("Xvfb"):
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as f:
                    argv = f.read().split(b"\0")
            except OSError:
                continue
            if len(argv) > 1 and argv[1] == f":{n}".encode():
                self._kill(pid)

    def capture_owned_game_window(self) -> str:
        """Find one visible game window on this session's newly owned X server.

        This deliberately refuses reused displays, ambiguous candidates, and a
        replacement for an already captured window.  It never scans a user's
        desktop: the Xvfb process and its exact DISPLAY must still belong to
        this session.
        """
        if self.xvfb is None or self.xvfb.poll() is not None:
            raise RuntimeError("owned game-window capture requires this session's live Xvfb")
        display = self.env.get("DISPLAY")
        if display != f":{self.display}":
            raise RuntimeError("owned game-window capture display does not match session Xvfb")
        env = dict(self.env)
        pids = set(self.game_pids())
        if self.launcher is not None and self.launcher.poll() is None:
            pids.add(self.launcher.pid)
        if not pids:
            raise RuntimeError("owned game-window capture has no live game process")

        def owner_and_geometry(window: str) -> tuple[int, int, int]:
            owner = subprocess.check_output(["xdotool", "getwindowpid", window], env=env,
                                            text=True, timeout=5).strip()
            geometry = subprocess.check_output(["xdotool", "getwindowgeometry", "--shell", window],
                                               env=env, text=True, timeout=5)
            fields = dict(line.split("=", 1) for line in geometry.splitlines() if "=" in line)
            return int(owner), int(fields.get("WIDTH", "0")), int(fields.get("HEIGHT", "0"))

        if self.capture_window is not None:
            try:
                owner, width, height = owner_and_geometry(self.capture_window)
            except (OSError, subprocess.SubprocessError, ValueError) as error:
                raise RuntimeError("previously owned game window was lost") from error
            if owner != self._capture_window_pid or owner not in pids or width <= 0 or height <= 0:
                raise RuntimeError("previously owned game window was replaced or is no longer valid")
            return self.capture_window

        candidates: set[str] = set()
        for pid in sorted(pids):
            try:
                result = subprocess.run(["xdotool", "search", "--onlyvisible", "--pid", str(pid)],
                                        env=env, text=True, capture_output=True, timeout=5, check=False)
            except (OSError, subprocess.SubprocessError) as error:
                raise RuntimeError("owned game-window discovery could not query X11") from error
            if result.returncode not in (0, 1):
                raise RuntimeError("owned game-window discovery failed")
            candidates.update(line.strip() for line in result.stdout.splitlines() if line.strip().isdigit())
        verified = []
        for window in sorted(candidates, key=int):
            try:
                owner, width, height = owner_and_geometry(window)
            except (OSError, subprocess.SubprocessError, ValueError):
                continue
            if owner in pids and width > 0 and height > 0:
                verified.append((window, owner))
        if len(verified) != 1:
            raise RuntimeError(f"owned game-window discovery requires exactly one visible game window, found {len(verified)}")
        window, owner = verified[0]
        self.capture_window = f"0x{int(window):x}"
        self._capture_window_pid = owner
        self.log(f"owned game window captured {self.capture_window} (pid {owner})")
        return self.capture_window

    # ------------------------------------------------------------ launch --
    def _build_env(self) -> Dict[str, str]:
        env = dict(os.environ)
        for k in STRIP_ENV:
            env.pop(k, None)
        env["SDL_VIDEODRIVER"] = "x11"
        env["DISPLAY"] = f":{self.display}"
        env["LIBGL_ALWAYS_SOFTWARE"] = "1"
        env["GALLIUM_DRIVER"] = "llvmpipe"
        env["LP_NUM_THREADS"] = env.get("KP_LP_NUM_THREADS", "2")
        env["KOTORPHASOR_HARNESS_PORT"] = str(self.port)
        # This host's /tmp can be quota-limited independently of its free
        # space. Wine and the game create transient files during launch, so
        # keep those files in the harness-owned staged tree instead of making
        # a healthy game boot depend on unrelated /tmp consumers. Xvfb itself
        # still needs /tmp for its lock, which boot() handles separately.
        assert self.game_dir is not None
        if self.target.wine:
            isolated, _ = self._wine_tmp()
            env["TMPDIR"] = "/tmp" if isolated else str(self.game_dir / "Temp")
            if not isolated:
                Path(env["TMPDIR"]).mkdir(parents=True, exist_ok=True)
        else:
            temp_dir = self.game_dir / "kotorphasor/tmp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            env["TMPDIR"] = str(temp_dir)
        # Steamworks uses these launch-context variables when a native binary
        # is started from a harness staging tree.  They identify the licensed
        # app to an already authenticated Steam client; they do not disable
        # SteamAPI authentication or replace the client.
        if self.target.steam_appid and not self.target.wine:
            env["SteamAppId"] = self.target.steam_appid
            env["SteamGameId"] = self.target.steam_appid
        if self.target.wine:
            env["WINEPREFIX"] = str(self.wineprefix)
            env["WINEDEBUG"] = self.wine_debug if self.wine_debug is not None else env.get("WINEDEBUG", "-all")
        else:
            assert self.xdg_home is not None
            env["LD_PRELOAD"] = str(self.game_dir / "kotorphasor" / "libkphasor.so")
            env["XDG_DATA_HOME"] = str(self.xdg_home)
            libs = [str(self.game_dir)]
            staged_glu = self.game_dir / "kotorphasor" / "lib"
            if staged_glu.is_dir():
                libs.insert(0, str(staged_glu))
            prior = env.get("LD_LIBRARY_PATH", "")
            if prior:
                libs.extend([p for p in prior.split(":") if p and p not in libs])
            env["LD_LIBRARY_PATH"] = ":".join(libs)
        return env

    def launch(self) -> None:
        assert self.game_dir is not None
        self.env = self._build_env()
        self._stderr_path = self.run_dir / ("wine.log" if self.target.wine else "game.log")
        try:
            self._stderr_offset = self._stderr_path.stat().st_size
        except OSError:
            self._stderr_offset = 0
        try:
            self._runtime_log_offset = self.runtime_log.stat().st_size
        except OSError:
            self._runtime_log_offset = 0
        out = open(self._stderr_path, "ab")
        if self.target.wine:
            self.wineprefix.mkdir(parents=True, exist_ok=True)
            # An initialised prefix does not need settling, and wineboot on
            # this machine intermittently hangs for its whole ceiling (see
            # docs/harness-research/map-harness-history.md, "10-minute wineboot
            # stalls"), which eats the scenario budget before the game starts.
            # system.reg is the marker wine itself writes once the prefix is
            # built. KP_WINEBOOT=1 forces the settle for a suspect prefix.
            settled = (self.wineprefix / "system.reg").is_file()
            if settled and os.environ.get("KP_WINEBOOT") != "1":
                self.log(f"wine prefix already initialised, skipping wineboot ({self.wineprefix})")
                self._settle_wineserver()
            else:
                self.log("settling wine prefix (wineboot -i)")
                with open(self.run_dir / "wineboot.log", "ab") as wb:
                    for step in (["wineboot", "-i"], ["wineserver", "-w"]):
                        try:
                            subprocess.run(self._wine_command(step), env=self.env,
                                           stdout=wb, stderr=subprocess.STDOUT,
                                           timeout=60)
                        except subprocess.TimeoutExpired:
                            # A stalled settle is not a reason to lose the run:
                            # the launch below either finds a usable prefix or
                            # fails with the game's own diagnostics.
                            self.log(f"warning: {' '.join(step)} did not finish in 60s, launching anyway")
            # Launch the executable directly. Wrapping it in a virtual desktop
            # (wine explorer /desktop=) was tried first and the game exited
            # within seconds with an empty stderr, while the same tree launched
            # directly ran and installed every hook. Xvfb already supplies a
            # root window of the size the ini asks for, so the extra desktop
            # buys nothing. KP_WINE_DESKTOP=1 restores it for debugging.
            if os.environ.get("KP_WINE_DESKTOP") == "1":
                w, h = self.screen
                cmd = ["wine", "explorer", f"/desktop=kp,{w}x{h}", self.target.exe]
            else:
                cmd = ["wine", self.target.exe]
            cmd = self._wine_command(cmd)
            cwd = self.game_dir
        else:
            cmd = [str(self.game_dir / self.target.exe)]
            cwd = self.game_dir
        self.log(f"launching: {' '.join(cmd)} (cwd {cwd})")
        self.launcher = subprocess.Popen(cmd, cwd=str(cwd), env=self.env, stdout=out,
                                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                         start_new_session=True)

    def _wine_command(self, command: List[str]) -> List[str]:
        """Run Wine with this session's persistent private ``/tmp``."""
        assert self.game_dir is not None
        isolated, tmp_dir = self._wine_tmp()
        return wine_command(command, self.game_dir, self.wineprefix,
                            tmp_dir=tmp_dir, isolate=isolated,
                            die_with_parent=not self.persistent)

    def _wine_tmp(self) -> tuple[bool, Optional[Path]]:
        """Choose once so launch and all later Wine commands share a namespace."""
        assert self.game_dir is not None
        if self._wine_tmp_isolated is None:
            self._wine_tmp_isolated = wine_isolation_enabled()
            if self._wine_tmp_isolated:
                self._wine_tmp_dir = wine_tmp_backing(self.game_dir, self.wineprefix)
        return self._wine_tmp_isolated, self._wine_tmp_dir

    def _settle_wineserver(self) -> None:
        """Wait briefly for a prior wineserver shutdown before a new launch."""
        timeout = max(1.0, float(os.environ.get("KP_WINESERVER_SETTLE", "15")))
        try:
            result = subprocess.run(self._wine_command(["wineserver", "-w"]), env=self.env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            self.log(f"warning: wineserver -w did not finish in {timeout:.0f}s; launching anyway")
        except (OSError, subprocess.SubprocessError) as e:
            self.log(f"warning: wineserver settle failed ({e}); launching anyway")
        else:
            if result.returncode:
                self.log(f"warning: wineserver -w exited {result.returncode}; launching anyway")
            else:
                self.log("wineserver settled before launch")

    # ------------------------------------------------------------- probe --
    # The Watchdog reads these; a fake session in the offline test implements
    # the same names.
    def process_alive(self) -> bool:
        return bool(pids_by_name(self.target.process_name)) or (
            self.launcher is not None and self.launcher.poll() is None
            and not self.target.wine)

    def game_pids(self) -> List[int]:
        return pids_by_name(self.target.process_name)

    def _read_new(self, path: Optional[Path], attr: str) -> str:
        if path is None or not path.is_file():
            return ""
        offset = getattr(self, attr)
        try:
            with open(path, "rb") as f:
                f.seek(offset)
                data = f.read()
        except OSError:
            return ""
        setattr(self, attr, offset + len(data))
        return data.decode("utf-8", "replace")

    def read_new_stderr(self) -> str:
        return self._read_new(self._stderr_path, "_stderr_offset")

    def read_new_runtime_log(self) -> str:
        return self._read_new(self.runtime_log if self.game_dir else None, "_runtime_log_offset")

    def stack_dump(self) -> str:
        """One-shot: attach gdb (and winedbg under Wine) for a backtrace.

        Best effort with a hard timeout; a dump that fails is a line in the
        verdict, never a reason for the oracle itself to fail.
        """
        if self._stack_dumped:
            return "(stack already dumped once this session)"
        self._stack_dumped = True
        pids = self.game_pids()
        if not pids:
            return "(no game process to attach)"
        pid = pids[0]
        chunks: List[str] = []
        if self.target.wine and shutil.which("winedbg"):
            try:
                r = subprocess.run(["winedbg", "--command", "info proc"], env=self.env,
                                   capture_output=True, text=True, timeout=30)
                chunks.append("winedbg info proc:\n" + r.stdout + r.stderr)
            except (subprocess.SubprocessError, OSError) as e:
                chunks.append(f"winedbg failed: {e}")
        if shutil.which("gdb"):
            try:
                r = subprocess.run(["gdb", "-p", str(pid), "-batch", "-ex", "thread apply all bt"],
                                   capture_output=True, text=True, timeout=90)
                chunks.append(f"gdb -p {pid}:\n" + r.stdout + r.stderr)
            except (subprocess.SubprocessError, OSError) as e:
                chunks.append(f"gdb failed: {e}")
        text = "\n".join(chunks) or "(no debugger available)"
        try:
            (self.run_dir / "stack.txt").write_text(text)
        except OSError:
            pass
        return text

    # ----------------------------------------------------------- connect --
    def connect(self, expect_build: bool = True) -> Channel:
        """Retry until `status` answers with an expected build, or fail with
        the class of failure the pre-channel oracles saw."""
        deadline = time.monotonic() + self.boot_timeout
        started = time.monotonic()
        last_err = ""
        ch = Channel("127.0.0.1", self.port, timeout=channel_timeout())
        while time.monotonic() < deadline:
            err_text = self.read_new_stderr()
            rt_text = self.read_new_runtime_log()
            if RUNTIME_REFUSAL.search(rt_text):
                line = next(l for l in rt_text.splitlines() if "refusing to install" in l)
                raise BootFailure("refusal", line.strip())
            if RUNTIME_FATAL.search(rt_text):
                raise BootFailure("crash", "fault in the runtime during boot")
            if WINE_FATAL.search(err_text):
                line = next(l for l in err_text.splitlines() if WINE_FATAL.search(l))
                raise BootFailure("crash", line.strip())
            # Wine can spend longer than the historical 15-second grace period
            # creating the 32-bit process while its launcher is still alive
            # (especially after a saturated /tmp or a busy external game
            # drive).  That is a slow boot, not a crash.  Only call it a
            # crash when the launcher itself has exited; a live launcher keeps
            # getting the scenario's full boot timeout to publish the channel.
            launcher_rc = self.launcher.poll() if self.launcher is not None else None
            if launcher_rc is not None and not self.process_alive():
                rc = launcher_rc
                try:
                    tail = self._stderr_path.read_text(errors="replace")[-1200:]
                except OSError:
                    tail = ""
                detail = f"{self.target.process_name} is not running (launcher_rc={rc})"
                if tail.strip():
                    detail += f"; last launch output: {tail.strip()}"
                raise BootFailure("crash", detail)
            try:
                ch.connect(connect_timeout=1.0)
                try:
                    status = ch.status()
                except (OSError, ChannelError) as status_error:
                    # K2-native can be live while its larger status payload is
                    # rejected by an early channel implementation.  Ping is a
                    # deliberately small, metadata-bearing fallback.
                    ch.close()
                    ch.connect(connect_timeout=1.0)
                    status = ch.ping()
                    if not status.get("pong"):
                        raise status_error
            except (OSError, ChannelError) as e:
                last_err = str(e)
                ch.close()
                time.sleep(1.0)
                continue
            build = str(status.get("build", ""))
            if expect_build and build not in self.target.builds:
                raise BootFailure("wrong build",
                                  f"status reports {build!r}, expected one of {self.target.builds}")
            self.build = build
            self.channel = ch
            self.log(f"channel up on 127.0.0.1:{self.port}: build {build}, "
                     f"{status.get('hooks', status.get('installed_hooks', '?'))} hooks, "
                     f"live={status.get('live')}")
            return ch
        raise BootFailure("boot timeout",
                          f"no status reply in {self.boot_timeout:.0f}s (last: {last_err})")

    def _launch_and_connect(self) -> Channel:
        """Launch the game and wait for its channel, up to BOOT_ATTEMPTS times.

        A launch that comes straight after `pkill swkotor.exe; wineserver -k`
        dies without writing a line -- seen twice out of two, and the immediate
        retry worked both times. The wineserver the kill left behind is still
        going away while the launch runs, so the first process finds a prefix
        mid-shutdown. Only that class of failure is retried: a refusal, a fault
        or the wrong build says something about the build, and repeating it
        would just cost the run its budget.
        """
        retryable = ("crash", "boot timeout")
        for attempt in range(1, BOOT_ATTEMPTS + 1):
            try:
                self.launch()
                return self.connect()
            except BootFailure as e:
                if attempt == BOOT_ATTEMPTS or e.reason not in retryable:
                    raise
                self.log(f"boot attempt {attempt} failed ({e.reason}: {e.detail}); "
                         f"settling {BOOT_RETRY_SETTLE:.0f}s and launching again")
                self._kill_game()
                time.sleep(BOOT_RETRY_SETTLE)
        raise BootFailure("boot timeout", "no attempt reached a channel")

    def _kill_game(self) -> None:
        """Stop the game processes of a failed attempt, leaving Xvfb and the
        lock alone: the next attempt reuses both."""
        for pid in self.game_pids():
            self._kill(pid)
        time.sleep(0.5)
        for pid in self.game_pids():
            self._kill(pid, signal.SIGKILL)
        if self.launcher is not None and self.launcher.poll() is None:
            self._kill(self.launcher.pid)
        self.launcher = None
        if self.target.wine:
            # A dead direct Wine launch can leave the prefix's wineserver
            # alive.  Merely waiting for it in the next launch retries the
            # same half-torn-down prefix until the attempt budget is gone.
            # This prefix is created solely for this harness, so a graceful
            # wineserver shutdown is scoped to the failed session rather than
            # to the user's normal Wine desktop.
            try:
                result = subprocess.run(self._wine_command(["wineserver", "-k"]), env=self.env,
                                        stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL, timeout=10,
                                        check=False)
            except (OSError, subprocess.SubprocessError) as e:
                self.log(f"warning: failed to stop Wine server after launch failure ({e})")
            else:
                if result.returncode:
                    self.log(f"warning: wineserver -k exited {result.returncode} after launch failure")
                else:
                    self.log("requested Wine-server shutdown after launch failure")

    # -------------------------------------------------------------- boot --
    def boot(self, resources: Optional[List[Resource]] = None) -> Channel:
        reuse_display = os.environ.get("KP_HARNESS_REUSE_DISPLAY", "")
        # Reusing a caller-owned display does not require creating an X lock;
        # a full /tmp quota must not reject an otherwise valid session.
        if not reuse_display.isdigit():
            problem = preflight_tmp_write()
            if problem:
                # Xvfb's lock/socket live in /tmp and cannot be redirected.
                # If quota is exhausted, reuse an already verified display so
                # the harness remains usable without deleting unrelated files.
                candidates = [n for n in range(100, 400)
                              if display_in_use(n) and
                              subprocess.run(["xdpyinfo", "-display", f":{n}"],
                                             stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL,
                                             timeout=2).returncode == 0]
                if candidates:
                    self.display = candidates[0]
                    reuse_display = str(self.display)
                    self.log(f"{problem}; reusing verified display :{self.display}")
                else:
                    raise BootFailure("preflight", problem)
        if reuse_display.isdigit():
            self.display = int(reuse_display)
            self.log(f"reusing caller-provided X display :{self.display}")
        else:
            self.display = self._choose_display()
        self.acquire_lock()
        try:
            # A scenario mutates the shared staged input tree.  Hold a
            # separate stage lock for the complete live session, not merely
            # while its files are being copied.
            if self.reset_saves:
                self.acquire_stage_lock()
            self.stage(resources)
            self.port = self.requested_port or free_port()
            assert self.game_dir is not None
            write_runtime_ini(self.game_dir, self.port)
            if not reuse_display.isdigit():
                self.start_xvfb()
            ch = self._launch_and_connect()
        except BaseException:
            self.teardown(graceful=False)
            raise
        self.write_session_info()
        return ch

    def write_session_info(self) -> Path:
        info = SessionInfo(
            target=self.target.name, staged=str(self.staged), game_dir=str(self.game_dir),
            save_dir=str(self.save_dir), run_dir=str(self.run_dir), display=self.display,
            port=self.port, xvfb_pid=self.xvfb.pid if self.xvfb else 0,
            launcher_pid=self.launcher.pid if self.launcher else 0,
            lock_path=str(self.lock_path or ""), wineprefix=str(self.wineprefix) if self.target.wine else "",
            wine_tmp_dir=str(self._wine_tmp_dir or "") if self.target.wine else "",
            wine_tmp_isolated=self._wine_tmp_isolated if self.target.wine else None,
            process_name=self.target.process_name, build=self.build)
        path = self.session_info_path(self.staged)
        path.write_text(json.dumps(info.to_dict(), indent=2))
        return path

    @staticmethod
    def session_info_path(staged: Path) -> Path:
        return staged / "session.json"

    # ---------------------------------------------------------- teardown --
    @staticmethod
    def _kill(pid: int, sig: int = signal.SIGTERM) -> None:
        try:
            os.kill(pid, sig)
        except OSError:
            pass

    def teardown(self, graceful: bool = True) -> None:
        """Kill by process name, stop Xvfb, release the lock, keep the logs."""
        if self.channel is not None and graceful:
            try:
                self.channel.quit()
            except ChannelError:
                pass
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and self.game_pids():
                time.sleep(0.25)
        if self.channel is not None:
            self.channel.close()
            self.channel = None
        for pid in self.game_pids():
            self._kill(pid)
        time.sleep(0.5)
        for pid in self.game_pids():
            self._kill(pid, signal.SIGKILL)
        if self.target.wine and self.env:
            try:
                subprocess.run(self._wine_command(["wineserver", "-k"]), env=self.env, timeout=30,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except (subprocess.SubprocessError, OSError):
                pass
        if self.launcher is not None and self.launcher.poll() is None:
            self._kill(self.launcher.pid)
        if self.xvfb is not None and self.xvfb.poll() is None:
            self._kill(self.xvfb.pid)
            try:
                self.xvfb.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._kill(self.xvfb.pid, signal.SIGKILL)
        if self.wm is not None and self.wm.poll() is None:
            self._kill(self.wm.pid)
        if self.steam is not None and self.steam.poll() is None:
            self._kill(self.steam.pid)
        self.release_stage_lock()
        self.release_lock()
        try:
            if self.game_dir and self.runtime_log.is_file():
                shutil.copy2(self.runtime_log, self.run_dir / "kotorphasor.log")
        except OSError:
            pass
        try:
            self.session_info_path(self.staged).unlink()
        except OSError:
            pass
        self.log(f"torn down; logs in {self.run_dir}")
        if self._session_log is not None:
            self._session_log.close()
            self._session_log = None

    def __enter__(self) -> "GameSession":
        self.boot()
        return self

    def __exit__(self, *exc) -> None:
        self.teardown()


def teardown_from_info(info: SessionInfo, log: Log = print) -> None:
    """`kpharness down` for a session booted by another process."""
    for pid in pids_by_name(info.process_name):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    time.sleep(1.0)
    for pid in pids_by_name(info.process_name):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    if info.wineprefix:
        env = dict(os.environ, WINEPREFIX=info.wineprefix)
        if info.wine_tmp_isolated is None:
            # Old session records predate namespace identity.  They may have
            # used the host /tmp before isolation, or game_dir/Temp during the
            # first private-/tmp implementation.  Probe both briefly.
            commands = [["wineserver", "-k"]]
            try:
                commands.append(wine_command(["wineserver", "-k"], Path(info.game_dir),
                                             Path(info.wineprefix),
                                             tmp_dir=Path(info.game_dir) / "Temp", isolate=True))
            except (BootFailure, OSError) as e:
                log(f"warning: could not probe legacy game-temp Wine namespace ({e})")
            timeout = 5
        elif info.wine_tmp_isolated and not info.wine_tmp_dir:
            log("session has isolated Wine without a recorded /tmp backing; skipping wineserver cleanup")
            commands = []
            timeout = 0
        else:
            try:
                commands = [wine_command(["wineserver", "-k"], Path(info.game_dir),
                                         Path(info.wineprefix),
                                         tmp_dir=Path(info.wine_tmp_dir) if info.wine_tmp_dir else None,
                                         isolate=info.wine_tmp_isolated)]
            except (BootFailure, OSError) as e:
                log(f"warning: could not reach recorded Wine namespace ({e})")
                commands = []
            timeout = 30
        for command in commands:
            try:
                subprocess.run(command, env=env, timeout=timeout,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except (BootFailure, subprocess.SubprocessError, OSError):
                pass
    for pid in (info.launcher_pid, info.xvfb_pid):
        if pid > 0:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
    lock = Path(info.lock_path) if info.lock_path else None
    if lock and lock.is_file():
        try:
            lines = lock.read_text().splitlines()
            if len(lines) > 2 and lines[2] == str(info.display):
                lock.unlink()
        except OSError:
            pass
    try:
        src = Path(info.game_dir) / "kotorphasor.log"
        if src.is_file():
            shutil.copy2(src, Path(info.run_dir) / "kotorphasor.log")
    except OSError:
        pass
    try:
        GameSession.session_info_path(Path(info.staged)).unlink()
    except OSError:
        pass
    log(f"session on :{info.display} torn down; logs in {info.run_dir}")
