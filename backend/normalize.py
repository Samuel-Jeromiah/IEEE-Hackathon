"""Normalize uploads: HEIC→JPEG, EXIF rotation, resize, GPS/time, audio decode prep."""
from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

# Register HEIC/HEIF openers when available.
try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except Exception:  # noqa: BLE001 — optional at import time; HEIC fails later with a clear error
    pass


@dataclass
class NormalizedFile:
    path: Path
    kind: str  # image | audio | document | video | text | code
    original_name: str | None = None
    converted_from: str | None = None
    mime: str | None = None
    lat: float | None = None
    lon: float | None = None
    captured_at: str | None = None
    work_dir: Path | None = None
    extra: dict = field(default_factory=dict)


def _gps_from_exif(exif) -> tuple[float | None, float | None]:
    try:
        gps = exif.get_ifd(0x8825)  # GPSInfo
    except Exception:
        return None, None
    if not gps:
        return None, None

    def _ratio(v) -> float:
        if hasattr(v, "numerator"):
            return float(v.numerator) / float(v.denominator or 1)
        if isinstance(v, tuple) and len(v) == 2:
            return float(v[0]) / float(v[1] or 1)
        return float(v)

    def _to_deg(values) -> float:
        d, m, s = (_ratio(x) for x in values)
        return d + m / 60.0 + s / 3600.0

    try:
        lat = _to_deg(gps[2])
        lon = _to_deg(gps[4])
        if gps.get(1) == "S":
            lat = -lat
        if gps.get(3) == "W":
            lon = -lon
        return lat, lon
    except Exception:
        return None, None


def _captured_at(exif) -> str | None:
    for key in (36867, 36868, 306):  # DateTimeOriginal, Digitized, DateTime
        raw = exif.get(key)
        if not raw:
            continue
        try:
            return datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S").isoformat()
        except ValueError:
            continue
    return None


def normalize_image(src: Path, dest_dir: Path, max_px: int, original_name: str | None = None) -> NormalizedFile:
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = original_name or src.name
    suffix = src.suffix.lower()
    converted_from = None
    if suffix in {".heic", ".heif"}:
        converted_from = suffix.lstrip(".")

    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        lat = lon = None
        captured = None
        try:
            exif = im.getexif()
            lat, lon = _gps_from_exif(exif)
            captured = _captured_at(exif)
        except Exception:
            pass

        # Resize longest side
        w, h = im.size
        scale = max_px / max(w, h) if max(w, h) > max_px else 1.0
        if scale < 1.0:
            im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)

        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        elif im.mode == "L":
            im = im.convert("RGB")

        out = dest_dir / "image.jpg"
        im.save(out, format="JPEG", quality=90)

    return NormalizedFile(
        path=out, kind="image", original_name=name, converted_from=converted_from,
        mime="image/jpeg", lat=lat, lon=lon, captured_at=captured, work_dir=dest_dir,
    )


def write_upload(data: bytes, filename: str | None, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe = Path(filename or "upload.bin").name
    path = dest_dir / safe
    path.write_bytes(data)
    return path


def text_file(text: str, dest_dir: Path) -> NormalizedFile:
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / "input.txt"
    path.write_text(text, encoding="utf-8")
    return NormalizedFile(path=path, kind="document", original_name="input.txt",
                          mime="text/plain", work_dir=dest_dir, extra={"text": text})


def copy_as(src: Path, dest_dir: Path, kind: str, original_name: str | None = None,
            converted_from: str | None = None) -> NormalizedFile:
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = original_name or src.name
    out = dest_dir / Path(name).name
    out.write_bytes(src.read_bytes())
    return NormalizedFile(path=out, kind=kind, original_name=name,
                          converted_from=converted_from, work_dir=dest_dir)


def make_work_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="stormlog_"))
