"""Smoke: one chat+image round-trip against the VLM llama-server (port 8081)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.clients import llm  # noqa: E402


async def main() -> int:
    # Tiny 1x1 JPEG
    jpeg = bytes.fromhex(
        "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707"
        "070909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c"
        "1c2837292c30313434341f27393d38323c2e333432ffdb0043010909090c0b0c180d"
        "0d1832211c2132323232323232323232323232323232323232323232323232323232"
        "323232323232323232323232323232323232323232ffc00011080001000103011100"
        "021101031101ffc40014000100000000000000000000000000000000ffc400141001"
        "00000000000000000000000000000000ffda000c0301000210031000003f00bf80ffd9"
    )
    import base64
    url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
    messages = [{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": url}},
            {"type": "text", "text": "Reply with exactly the word OK."},
        ],
    }]
    out = await llm.chat("vlm", messages, temperature=0.0, max_tokens=16, timeout_s=60)
    print("vlm:", out.strip()[:200])
    return 0 if out.strip() else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
