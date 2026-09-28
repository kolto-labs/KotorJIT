"""Durable ownership record for one staged mutable operation bundle."""
from __future__ import annotations
import json, os, tempfile, time, re, math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise LeaseError(f"duplicate lease field: {key}")
        result[key] = value
    return result

FORMAT = "kpharness.operation-lease/v1"
STATES = {"prepared", "released", "quarantined"}

class LeaseError(ValueError): pass

@dataclass(frozen=True)
class Lease:
    generation: int
    state: str
    manifest_sha256: str
    staged_bundle: str
    pid: int
    start: str
    created_at: float
    clearance_receipt: Optional[str] = None
    def to_dict(self):
        return {"format": FORMAT, "generation": self.generation, "state": self.state,
                "operation_manifest_sha256": self.manifest_sha256, "staged_bundle": self.staged_bundle,
                "owner": {"pid": self.pid, "start": self.start}, "created_at": self.created_at,
                "clearance_receipt": self.clearance_receipt}

def read(path: Path) -> Lease:
    try:
        raw=json.loads(Path(path).read_text(), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError, LeaseError, ValueError, OverflowError) as e:
        raise LeaseError(f"unreadable lease: {e}") from e
    if not isinstance(raw,dict) or raw.get("format") != FORMAT: raise LeaseError("invalid lease format")
    owner=raw.get("owner")
    keys={"format","generation","state","operation_manifest_sha256","staged_bundle","owner","created_at","clearance_receipt"}
    if set(raw)!=keys or not isinstance(owner,dict) or set(owner)!={"pid","start"}: raise LeaseError("invalid lease fields")
    if (not isinstance(raw["state"], str) or raw["state"] not in STATES
            or type(raw["generation"]) is not int or raw["generation"] < 1):
        raise LeaseError("invalid lease state or generation")
    if (not isinstance(raw["operation_manifest_sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", raw["operation_manifest_sha256"])):
        raise LeaseError("invalid operation manifest SHA-256")
    if not isinstance(raw["staged_bundle"],str) or not raw["staged_bundle"]:
        raise LeaseError("invalid staged bundle")
    if type(owner["pid"]) is not int or owner["pid"] < 1 or not isinstance(owner["start"],str) or not owner["start"]:
        raise LeaseError("invalid lease owner")
    created_at = raw["created_at"]
    if isinstance(created_at, bool) or not isinstance(created_at, (int, float)):
        raise LeaseError("invalid lease timestamp")
    try:
        created_at = float(created_at)
    except (TypeError, ValueError, OverflowError) as e:
        raise LeaseError("invalid lease timestamp") from e
    if not math.isfinite(created_at):
        raise LeaseError("invalid lease timestamp")
    clearance_receipt = raw["clearance_receipt"]
    if clearance_receipt is not None and (not isinstance(clearance_receipt, str) or not clearance_receipt):
        raise LeaseError("invalid clearance receipt")
    if raw["state"] == "released" and clearance_receipt is None:
        raise LeaseError("released lease lacks clearance receipt")
    return Lease(raw["generation"],raw["state"],raw["operation_manifest_sha256"],raw["staged_bundle"],owner["pid"],owner["start"],created_at,clearance_receipt)

def write(path: Path, lease: Lease) -> None:
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=path.name+".",dir=path.parent)
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(lease.to_dict(),f,sort_keys=True); f.write("\n"); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    except BaseException:
        try: os.unlink(tmp)
        except OSError: pass
        raise

def classify(path: Path, pid_start: Callable[[int],str]) -> str:
    """Return released, owned, or quarantined; malformed records never self-clear."""
    try: lease=read(path)
    except LeaseError: return "quarantined"
    if lease.state == "released": return "released"
    if lease.state == "quarantined": return "quarantined"
    return "owned" if pid_start(lease.pid) == lease.start else "quarantined"

def transition(path: Path, *, state: str, pid_start: Callable[[int], str], clearance_receipt: Optional[str] = None,
               expected: Optional[Lease] = None) -> Lease:
    """Publish one terminal transition for the exact lease admitted by this owner."""
    if state not in {"released", "quarantined"}:
        raise LeaseError("unsupported lease transition")
    lease = read(path)
    if expected is not None and lease != expected:
        raise LeaseError("lease identity changed before terminal transition")
    if lease.state != "prepared":
        raise LeaseError("terminal lease cannot transition again")
    owns = lease.pid == os.getpid() and pid_start(lease.pid) == lease.start
    if state == "released" and not owns:
        state = "quarantined"
    if state == "released" and not clearance_receipt:
        raise LeaseError("released lease requires clearance receipt")
    next_lease = Lease(lease.generation + 1, state, lease.manifest_sha256, lease.staged_bundle,
                       lease.pid, lease.start, time.time(), clearance_receipt)
    write(path, next_lease)
    return next_lease

def next_generation(path: Path, pid_start: Callable[[int], str]) -> int:
    """Admission generation for a successor; owned/quarantined records block reuse."""
    if not Path(path).exists(): return 1
    status = classify(path, pid_start)
    if status != "released":
        raise LeaseError(f"operation bundle is {status}; explicit clearance or a disjoint bundle is required")
    return read(path).generation + 1
