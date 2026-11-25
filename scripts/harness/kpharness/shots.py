"""Screenshots: a periodic sanity check of the state, never a wait condition.

The `screenshot` command makes the runtime read the frame with glReadPixels
and write a PPM to the path given. The path is relative to the game's
working directory, because under Wine the DLL's file API does not see host
paths; the driver reads the file back from the staged tree, converts it to
PNG when Pillow is importable (it is under the system interpreter), and
stores it next to the run log with the state that was current.

OCR is optional and only ever a warning. A scenario step with
`expect_screen = "dialog"` runs tesseract over the frame and fuzzy-compares
the result with the reply texts the engine reported. Tesseract wants dark
text on a light background at around 30 px capital height, so the frame is
inverted and upscaled three times before recognition; dictionaries are off
because the words are proper names the dictionary would "correct".
"""
from __future__ import annotations

import difflib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .client import Channel, ChannelError

try:  # optional
    from PIL import Image, ImageOps  # type: ignore
except Exception:  # noqa: BLE001 - any import failure means "no Pillow"
    Image = None
    ImageOps = None


def have_pillow() -> bool:
    return Image is not None


def have_tesseract() -> bool:
    return shutil.which("tesseract") is not None


def ppm_to_png(src: Path, dst: Path) -> Path:
    """Convert when Pillow is present; otherwise keep the PPM as it is."""
    if Image is None:
        keep = dst.with_suffix(".ppm")
        if src.resolve() != keep.resolve():
            shutil.copy2(src, keep)
        return keep
    with Image.open(src) as im:
        im.save(dst, format="PNG")
    return dst


class Shooter:
    """Takes a frame every `interval` seconds when polled, and on demand."""

    def __init__(self, channel: Channel, game_dir: Path, run_dir: Path, *,
                 interval: float = 120.0, log=None, rel_dir: str = "kotorjit/shots"):
        self.channel = channel
        self.game_dir = Path(game_dir)
        self.run_dir = Path(run_dir)
        self.interval = interval
        self.log = log or (lambda s: None)
        self.rel_dir = rel_dir
        self.out_dir = self.run_dir / "shots"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.game_dir / rel_dir).mkdir(parents=True, exist_ok=True)
        self._n = 0
        self._last_at = 0.0
        self.last_path: Optional[Path] = None
        self.last_state: Optional[dict] = None

    def maybe(self, state: Optional[dict] = None) -> Optional[Path]:
        if self.interval <= 0:
            return None
        if time.monotonic() - self._last_at >= self.interval:
            return self.take("periodic", state)
        return None

    def take(self, label: str = "shot", state: Optional[dict] = None) -> Optional[Path]:
        self._n += 1
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", label)[:40]
        name = f"{self._n:04d}_{safe}"
        rel = f"{self.rel_dir}/{name}.ppm"
        self._last_at = time.monotonic()
        try:
            reply = self.channel.screenshot(rel, timeout=30.0)
        except ChannelError as e:
            self.log(f"screenshot {name}: {e}")
            return None
        src = self.game_dir / rel
        if isinstance(reply, dict) and reply.get("path"):
            cand = Path(str(reply["path"]))
            if cand.is_absolute() and cand.is_file():
                src = cand
        deadline = time.monotonic() + 10
        while not src.is_file() and time.monotonic() < deadline:
            time.sleep(0.1)
        if not src.is_file():
            self.log(f"screenshot {name}: runtime replied but {src} never appeared")
            return None
        try:
            out = ppm_to_png(src, self.out_dir / f"{name}.png")
        except Exception as e:  # noqa: BLE001 - a bad frame must not fail a run
            self.log(f"screenshot {name}: conversion failed ({e}); keeping PPM")
            out = self.out_dir / f"{name}.ppm"
            shutil.copy2(src, out)
        if state is None:
            try:
                state = self.channel.state()
            except ChannelError:
                state = None
        (self.out_dir / f"{name}.json").write_text(json.dumps(state, indent=1, default=str))
        try:
            src.unlink()
        except OSError:
            pass
        self.last_path, self.last_state = out, state
        self.log(f"screenshot -> {out.name}")
        return out


# --------------------------------------------------------------------- OCR --

def ocr_text(image: Path, region: Optional[Tuple[float, float, float, float]] = None,
             scale: int = 3) -> str:
    """Tesseract over `image`, optionally a fractional crop (l, t, r, b).

    Without Pillow the frame goes to tesseract as it is (no crop, no
    inversion), which is worse but still a check.
    """
    if not have_tesseract():
        return ""
    src = image
    tmp: Optional[Path] = None
    if Image is not None:
        with Image.open(image) as im:
            im = im.convert("L")
            if region:
                w, h = im.size
                l, t, r, b = region
                im = im.crop((int(w * l), int(h * t), int(w * r), int(h * b)))
            im = ImageOps.invert(im)
            im = im.resize((im.width * scale, im.height * scale), Image.LANCZOS)
            im = ImageOps.expand(im, border=10, fill=255)
            tmp = image.with_name(image.stem + ".ocr.png")
            im.save(tmp)
            src = tmp
    cmd = ["tesseract", str(src), "stdout", "--oem", "1", "--psm", "6",
           "-c", "load_system_dawg=0", "-c", "load_freq_dawg=0"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return r.stdout
    except (subprocess.SubprocessError, OSError):
        return ""
    finally:
        if tmp is not None:
            try:
                tmp.unlink()
            except OSError:
                pass


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


def best_match(ocr: str, expected: List[str]) -> Tuple[float, str]:
    """Highest difflib ratio of any expected line against any OCR line."""
    lines = [_norm(l) for l in ocr.splitlines() if _norm(l)]
    best, best_text = 0.0, ""
    for want in expected:
        w = _norm(want)
        if not w:
            continue
        for l in lines:
            r = difflib.SequenceMatcher(None, w, l).ratio()
            if w in l:
                r = max(r, 0.95)
            if r > best:
                best, best_text = r, want
    return best, best_text


def expected_texts(kind: str, state: Optional[Dict[str, Any]]) -> List[str]:
    """What the engine says is on screen for `kind` ("dialog" for now)."""
    if not state:
        return []
    if kind == "dialog":
        d = state.get("dialog") or {}
        out: List[str] = []
        if d.get("text"):
            out.append(str(d["text"]))
        for r in d.get("replies") or []:
            if isinstance(r, dict) and r.get("text"):
                out.append(str(r["text"]))
            elif isinstance(r, str):
                out.append(r)
        return out
    return []


def check_screen(kind: str, image: Optional[Path], state: Optional[Dict[str, Any]],
                 threshold: float = 0.6) -> Dict[str, Any]:
    """OCR cross-check. Returns a report; `ok` is None when the check could
    not run (no tesseract, no image, nothing expected)."""
    report: Dict[str, Any] = {"kind": kind, "image": str(image) if image else None,
                              "ok": None, "ratio": 0.0, "matched": "", "warning": ""}
    if image is None or not have_tesseract():
        report["warning"] = "no image or no tesseract; OCR check skipped"
        return report
    want = expected_texts(kind, state)
    if not want:
        report["warning"] = f"engine reported no {kind} text to compare"
        return report
    region = (0.0, 0.5, 1.0, 1.0) if kind == "dialog" else None
    text = ocr_text(image, region)
    ratio, matched = best_match(text, want)
    report.update(ratio=round(ratio, 3), matched=matched, ok=ratio >= threshold,
                  ocr=text[:2000])
    if ratio < threshold:
        report["warning"] = (f"OCR did not find the {kind} text the engine reported "
                             f"(best ratio {ratio:.2f})")
    return report
