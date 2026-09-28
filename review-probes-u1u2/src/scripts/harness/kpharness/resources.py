"""Validated scenario artifacts, independent of the actions that consume them."""
from dataclasses import dataclass
from pathlib import PurePosixPath
import re


LEGACY_KEYS = ("walkmesh_resource", "walkmesh_file", "walkmesh_size", "walkmesh_sha256")


@dataclass(frozen=True)
class Resource:
    kind: str
    source: str
    file: str
    size: int
    sha256: str

    @classmethod
    def parse(cls, raw: dict) -> "Resource":
        if not isinstance(raw, dict) or set(raw) != {"kind", "source", "file", "size", "sha256"}:
            raise ValueError("resource requires exactly kind, source, file, size, sha256")
        if raw["kind"] != "walkmesh":
            raise ValueError("resource.kind must be 'walkmesh'")
        for key in ("source", "file"):
            value = raw[key]
            if not isinstance(value, str) or not value or any(c in value for c in ("\\", ":", "\0")):
                raise ValueError(f"resource.{key} must be a relative POSIX path")
            parts = PurePosixPath(value).parts
            if len(parts) < 2 or value.startswith("/") or ".." in parts:
                raise ValueError(f"resource.{key} must be a relative container/file path without '..'")
        if not raw["source"].lower().endswith(".wok"):
            raise ValueError("walkmesh resource.source must end in .wok")
        if PurePosixPath(raw["file"]).parts[0] != "harness-resources":
            raise ValueError("resource.file must be under harness-resources/")
        if type(raw["size"]) is not int or raw["size"] < 0:
            raise ValueError("resource.size must be a non-negative integer")
        if not isinstance(raw["sha256"], str) or not re.fullmatch(r"[0-9a-fA-F]{64}", raw["sha256"]):
            raise ValueError("resource.sha256 must contain 64 hexadecimal digits")
        return cls(raw["kind"], raw["source"], str(PurePosixPath(raw["file"])),
                   raw["size"], raw["sha256"].lower())

    @classmethod
    def from_legacy(cls, raw: dict) -> "Resource":
        if not all(key in raw for key in LEGACY_KEYS):
            raise ValueError("legacy walkmesh declaration requires " + ", ".join(LEGACY_KEYS))
        return cls.parse(dict(kind="walkmesh", source=raw["walkmesh_resource"],
                              file=raw["walkmesh_file"], size=raw["walkmesh_size"],
                              sha256=raw["walkmesh_sha256"]))
