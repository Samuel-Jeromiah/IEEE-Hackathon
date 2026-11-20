"""Frame sampling for the video worker — no models required."""
from pathlib import Path

import av
import numpy as np

from backend.workers.video import extract_frames


def _write_color_clip(path: Path, seconds: float = 1.0, w: int = 64, h: int = 48, fps: int = 8) -> None:
    """Write a tiny RGB mp4 that changes color halfway (red → blue)."""
    total = int(seconds * fps)
    with av.open(str(path), mode="w") as container:
        stream = container.add_stream("mpeg4", rate=fps)
        stream.width = w
        stream.height = h
        stream.pix_fmt = "yuv420p"
        for i in range(total):
            color = (200, 30, 30) if i < total // 2 else (30, 30, 200)
            frame_np = np.zeros((h, w, 3), dtype=np.uint8)
            frame_np[:, :] = color
            frame = av.VideoFrame.from_ndarray(frame_np, format="rgb24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)


def test_extract_frames_samples_evenly(tmp_path: Path):
    clip = tmp_path / "clip.mp4"
    _write_color_clip(clip, seconds=1.0)
    frames, used = extract_frames(
        clip, tmp_path / "frames", max_frames=4, frame_px=48, max_s=90.0,
    )
    assert used > 0
    assert 1 <= len(frames) <= 4
    assert all(f.path.exists() and f.thumb_b64 for f in frames)
    assert frames[0].t <= frames[-1].t
