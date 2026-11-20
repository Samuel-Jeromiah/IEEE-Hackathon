"""Smoke: load CLAP and score 0.5 s of silence against one label."""
from __future__ import annotations

import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend import manager  # noqa: E402


def main() -> int:
    sr = 48000
    audio = np.zeros(sr // 2, dtype=np.int16)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = Path(f.name)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(audio.tobytes())
    events = manager.classify_sounds(path, window_s=0.5, hop_s=0.5)
    path.unlink(missing_ok=True)
    print("clap events:", events[:3], "status:", manager.model_status())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
