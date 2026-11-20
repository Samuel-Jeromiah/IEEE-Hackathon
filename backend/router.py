"""Deterministic routing: task_hint + file signatures (+ PyAV probe when needed)."""
from __future__ import annotations

from pathlib import Path

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".gif", ".bmp"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".opus", ".flac", ".aac"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}
DOC_EXT = {".pdf", ".docx", ".txt", ".md"}

# Magic-byte prefixes → kind
_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "image"),           # JPEG
    (b"\x89PNG\r\n\x1a\n", "image"),      # PNG
    (b"GIF87a", "image"),
    (b"GIF89a", "image"),
    (b"RIFF", "audio"),                   # WAV/WebP/AVI — refined below
    (b"%PDF", "document"),
    (b"PK\x03\x04", "document"),          # ZIP/DOCX — refined by extension
]


def _sniff(data: bytes) -> str | None:
    if len(data) >= 12 and data[:4] == b"RIFF":
        form = data[8:12]
        if form == b"WAVE":
            return "audio"
        if form == b"WEBP":
            return "image"
        if form == b"AVI ":
            return "video"
    if len(data) >= 8 and data[4:8] == b"ftyp":
        # ISO BMFF: HEIC/HEIF/MP4/MOV
        brand = data[8:12]
        if brand in {b"heic", b"heif", b"mif1", b"msf1"}:
            return "image"
        return "video"
    if data[:4] == b"OggS":
        return "audio"
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
        return "audio"
    for magic, kind in _SIGNATURES:
        if data.startswith(magic):
            return kind
    return None


def _probe_av(path: Path) -> str | None:
    try:
        import av

        with av.open(str(path)) as container:
            has_video = any(s.type == "video" for s in container.streams)
            has_audio = any(s.type == "audio" for s in container.streams)
            if has_video:
                return "video"
            if has_audio:
                return "audio"
    except Exception:
        return None
    return None


def route_kind(
    *,
    filename: str | None,
    task_hint: str | None,
    has_text: bool,
    data: bytes | None = None,
    path: Path | None = None,
) -> str:
    """Pick an artifact kind.

    task_hint from a tool tile wins for code, and for document when the file is an image
    (OCR path). Otherwise signatures and extensions decide.
    """
    hint = (task_hint or "").strip().lower() or None
    if hint == "code":
        return "code"
    if hint == "text" and not filename and has_text:
        return "text"

    sniffed = _sniff(data[:64]) if data else None
    ext = Path(filename or (path.name if path else "")).suffix.lower()

    # Document tool with a photo → OCR / document path
    if hint == "document" and (sniffed == "image" or ext in IMAGE_EXT):
        return "document"

    if hint in {"image", "audio", "document", "video"} and sniffed in {None, hint}:
        # Prefer hint when it matches or sniff is inconclusive
        if sniffed is None or sniffed == hint:
            if hint == "document" and (ext in DOC_EXT or has_text or sniffed == "document"):
                return "document"
            if hint != "document":
                return hint

    if sniffed:
        # DOCX is ZIP; keep as document when extension says so
        if sniffed == "document" and ext == ".docx":
            return "document"
        if sniffed == "document" and ext not in DOC_EXT | {".docx", ""} and ext in IMAGE_EXT | AUDIO_EXT | VIDEO_EXT:
            pass
        else:
            return sniffed

    if ext in IMAGE_EXT:
        return "image"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in VIDEO_EXT:
        return "video"
    if ext in DOC_EXT or has_text:
        return "document"

    if path and path.exists():
        probed = _probe_av(path)
        if probed:
            return probed

    if hint:
        return hint
    return "text"
