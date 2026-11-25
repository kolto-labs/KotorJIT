"""Authenticated loopback bridge for the existing ``kp.console.v1`` wire.

The bridge adds HTTP framing only.  The native Console remains the sole Lua
evaluator and every accepted operation is forwarded unchanged through the
existing Channel client.  Attached playback-owner transport is intentionally
unsupported until the owner publishes a devtools forwarding API; standalone
mode is explicit and refuses a busy engine.
"""
from __future__ import annotations

import argparse
import hmac
import http.server
import json
import os
from pathlib import Path
import secrets
import socket
import threading
from typing import Any, Mapping
from urllib.parse import unquote

from .client import Channel, ChannelError, ChannelTimeout, ChannelClosed

PROTOCOL = "kp.console.v1"
OPS = frozenset(("status", "submit", "outcome", "output", "complete", "cancel"))
RESERVED = frozenset(("cmd", "protocol", "op", "timeout", "id", "self"))
# JSON can encode one source byte as six bytes (e.g. \\u0000). The native
# Console still enforces its decoded 16 KiB SourceLimit.
MAX_BODY = 6 * 16 * 1024 + 2048
WEB_ROOT = Path(__file__).resolve().parents[3] / "web" / "devtools"


class BridgeError(RuntimeError):
    pass


class StandaloneChannel(Channel):
    """Preserve native connection refusals, which have no request ID."""

    def _read_frame(self, deadline: float) -> dict:
        frame = super()._read_frame(deadline)
        if "id" not in frame and frame.get("ok") is False and isinstance(frame.get("error"), str):
            self.close()
            raise ChannelClosed(frame["error"])
        return frame


def state_dir() -> Path:
    root = os.environ.get("XDG_STATE_HOME")
    base = Path(root) if root and os.path.isabs(root) else Path.home() / ".local" / "state"
    path = base / "kpharness"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def read_or_create_token(path: Path) -> str:
    if path.exists():
        if path.is_symlink() or (os.name != "nt" and (path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077)):
            raise BridgeError("token file is not private")
        token = path.read_text(encoding="ascii").strip()
        if len(token) != 64 or any(c not in "0123456789abcdef" for c in token):
            raise BridgeError("token file has invalid contents")
        return token
    token = secrets.token_hex(32)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, token.encode("ascii"))
    finally:
        os.close(fd)
    return token


def _json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class Bridge:
    def __init__(self, channel: Any, token: str, *, web_root: Path = WEB_ROOT):
        self.channel = channel
        self.token = token
        self.web_root = web_root.resolve()
        self._lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(16)
        self._lost = False

    def forward(self, body: Mapping[str, Any]) -> Any:
        if self._lost:
            raise BridgeError("upstream_lost: channel is closed")
        if body.get("cmd") not in (None, "devtools"):
            raise BridgeError("only cmd=devtools is accepted")
        if body.get("protocol") not in (None, PROTOCOL):
            raise BridgeError("unsupported protocol")
        op = body.get("op")
        if not isinstance(op, str) or op not in OPS:
            raise BridgeError(f"unsupported console operation: {op!r}")
        if any(k in RESERVED for k in body if k not in {"cmd", "protocol", "op"}):
            raise BridgeError("transport-reserved field")
        fields = {k: v for k, v in body.items() if k not in {"cmd", "protocol", "op"}}
        if not self._slots.acquire(blocking=False):
            raise BridgeError("bridge request queue full")
        try:
            with self._lock:
                # A caller may have queued before the active request lost the
                # channel. Never send queued mutations after that boundary.
                if self._lost:
                    raise BridgeError("upstream_lost: channel is closed")
                try:
                    return self.channel.request("devtools", protocol=PROTOCOL, op=op, **fields)
                except (ChannelTimeout, ChannelClosed) as error:
                    self._lost = True
                    self.channel.close()
                    raise BridgeError(f"upstream_lost: {error}") from error
                except ChannelError as error:
                    raise BridgeError(str(error)) from error
        finally:
            self._slots.release()

    def static(self, request_path: str) -> tuple[bytes, str]:
        name = unquote(request_path.split("?", 1)[0])
        if name in ("", "/"):
            name = "/index.html"
        if not name.startswith("/") or ".." in Path(name).parts:
            raise FileNotFoundError(name)
        rel = name.lstrip("/")
        manifest = self.web_root / "MANIFEST"
        allowed = {line.strip() for line in manifest.read_text().splitlines() if line.strip()}
        if rel not in allowed:
            raise FileNotFoundError(name)
        path = (self.web_root / rel).resolve()
        if path.parent != self.web_root or path.name != rel:
            raise FileNotFoundError(name)
        data = path.read_bytes()
        content_type = "text/html; charset=utf-8" if path.suffix == ".html" else "text/javascript; charset=utf-8"
        return data, content_type

    @staticmethod
    def validate_publication(root: Path) -> None:
        manifest = {line.strip() for line in (WEB_ROOT / "MANIFEST").read_text().splitlines() if line.strip()}
        if root.is_symlink() or any(p.is_symlink() for p in root.rglob("*")):
            raise BridgeError("publication must not contain symlinks")
        actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
        if actual != manifest:
            raise BridgeError(f"publication allowlist mismatch: expected {sorted(manifest)}, found {sorted(actual)}")


class _Handler(http.server.BaseHTTPRequestHandler):
    server_version = "KotorJITDevtools/1"

    def setup(self) -> None:
        super().setup()
        self.request.settimeout(5.0)

    @property
    def bridge(self) -> Bridge:
        return self.server.bridge  # type: ignore[attr-defined]

    def _canonical(self) -> str:
        host = self.headers.get("Host", "")
        return f"127.0.0.1:{self.server.server_port}"  # type: ignore[attr-defined]

    def _guard(self) -> bool:
        if self.headers.get("Host") != self._canonical():
            self._reply(400, {"error": "canonical Host required"})
            return False
        if self.command == "POST":
            origin = self.headers.get("Origin")
            if origin != f"http://{self._canonical()}":
                self._reply(403, {"error": "canonical Origin required"})
                return False
            auth = self.headers.get("Authorization", "")
            expected = "Bearer " + self.bridge.token
            if not hmac.compare_digest(auth.encode("utf-8", "ignore"), expected.encode("ascii")):
                self._reply(401, {"error": "authorization required"})
                return False
        return True

    def _reply(self, status: int, obj: Any, *, content_type: str = "application/json") -> None:
        data = obj if isinstance(obj, bytes) else _json_bytes(obj)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:  # noqa: N802
        if self.headers.get("Host") != self._canonical() or self.headers.get("Origin") != f"http://{self._canonical()}":
            self._reply(403, {"error": "canonical Origin required"})
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", f"http://{self._canonical()}")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if not self._guard():
            return
        try:
            data, content_type = self.bridge.static(self.path)
        except (OSError, FileNotFoundError):
            self._reply(404, {"error": "not found"})
            return
        self._reply(200, data, content_type=content_type)

    def do_POST(self) -> None:  # noqa: N802
        if not self._guard():
            return
        if self.path.split("?", 1)[0] != "/v1/console":
            self._reply(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            self._reply(413, {"error": "request body too large"})
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(body, dict):
                raise ValueError("body must be an object")
            result = self.bridge.forward(body)
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
            self._reply(400, {"error": f"invalid JSON: {error}"})
            return
        except BridgeError as error:
            message = str(error)
            status = 502 if message.startswith("upstream_lost") else 429 if "queue full" in message else 400
            self._reply(status, {"error": message})
            return
        self._reply(200, result)

    def log_message(self, *_: Any) -> None:
        return


class BridgeServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address: tuple[str, int], bridge: Bridge):
        if address[0] != "127.0.0.1":
            raise BridgeError("devtools bridge must bind to 127.0.0.1")
        super().__init__(address, _Handler)
        self.bridge = bridge


def run_standalone(host: str, port: int, listen_port: int, token_path: Path) -> int:
    if host != "127.0.0.1":
        raise BridgeError("standalone upstream must be loopback")
    token = read_or_create_token(token_path)
    channel = StandaloneChannel(host, port, timeout=10.0)
    channel.connect()
    try:
        try:
            channel.request("devtools", protocol=PROTOCOL, op="status")
        except ChannelError as error:
            raise BridgeError(f"upstream unavailable: {error}") from error
        bridge = Bridge(channel, token)
        server = BridgeServer(("127.0.0.1", listen_port), bridge)
        print(f"http://127.0.0.1:{server.server_port}/", flush=True)
        print(f"token-file: {token_path}", flush=True)
        server.serve_forever()
    finally:
        channel.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="authenticated loopback kp.console.v1 bridge")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--standalone", action="store_true")
    mode.add_argument("--attach", metavar="OWNER", help="unsupported until playback publishes a devtools API")
    mode.add_argument("--check-publication", type=Path, metavar="DIRECTORY",
                      help="verify a staged directory against the source MANIFEST")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=False, default=0, help="standalone harness port")
    parser.add_argument("--listen", default="127.0.0.1:0")
    parser.add_argument("--token-file", type=Path)
    args = parser.parse_args(argv)
    if args.check_publication is not None:
        try:
            Bridge.validate_publication(args.check_publication)
        except (BridgeError, OSError) as error:
            print(f"devtools publication: {error}", file=os.sys.stderr)
            return 1
        print("devtools publication: exact MANIFEST match")
        return 0
    if args.attach:
        raise SystemExit("attach unsupported: playback owner has no devtools forwarding API")
    if ":" not in args.listen:
        raise SystemExit("--listen must be HOST:PORT")
    listen_host, listen_port = args.listen.rsplit(":", 1)
    if listen_host != "127.0.0.1":
        raise SystemExit("--listen must use 127.0.0.1")
    try:
        token_path = args.token_file or state_dir() / "devtools-bridge.token"
        return run_standalone(args.host, args.port, int(listen_port), token_path)
    except (BridgeError, OSError) as error:
        print(f"devtools bridge: {error}", file=os.sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
