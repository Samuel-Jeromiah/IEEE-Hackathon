"""Smoke: load Whisper and transcribe 1 s of silence (no network)."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend import manager  # noqa: E402


def main() -> int:
    # Write a tiny WAV via numpy + wave
    import wave

    sr = 16000
    audio = (np.zeros(sr, dtype=np.float32) * 32767).astype(np.int16)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = Path(f.name)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(audio.tobytes())
    segs = manager.transcribe(path)
    path.unlink(missing_ok=True)
    print("whisper segments:", len(segs), "status:", manager.model_status())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
