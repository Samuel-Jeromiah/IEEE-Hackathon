"""Smoke and CO alarms beep a loud, narrow tone around 3 kHz. Speech and rain never do.

The sound model alone mistakes some voices for alarms, so an alarm hazard also needs this check.
"""
from __future__ import annotations

import numpy as np

BAND_HZ = (2500.0, 4500.0)  # UL 217 / UL 2034 alarms sit near 3.1-3.5 kHz
CONTEXT_HZ = (1000.0, 8000.0)
PEAK_SHARE = 0.5  # the tone holds at least half the energy between 1 and 8 kHz
TONE_MIN = 0.03  # speech peaks near 0.02; a CO alarm's four short beeps under speech give 0.04+
FRAME = 2048
HOP = 1024


def alarm_tone_fraction(audio: np.ndarray, sr: int) -> float:
    """Share of short frames (about 40 ms) where one narrow tone in 2.5-4.5 kHz dominates."""
    if audio.size < FRAME:
        return 0.0
    window = np.hanning(FRAME)
    freqs = np.fft.rfftfreq(FRAME, 1.0 / sr)
    band = (freqs >= BAND_HZ[0]) & (freqs <= BAND_HZ[1])
    context = (freqs >= CONTEXT_HZ[0]) & (freqs <= CONTEXT_HZ[1])
    spread = max(1, int(round(60.0 / (sr / FRAME))))  # +-60 Hz around the peak
    starts = range(0, audio.size - FRAME + 1, HOP)
    tonal = 0
    for s in starts:
        power = np.abs(np.fft.rfft(audio[s:s + FRAME] * window)) ** 2
        total = power[context].sum()
        if total <= 1e-9:
            continue
        band_idx = np.flatnonzero(band)
        peak = band_idx[int(np.argmax(power[band_idx]))]
        share = power[max(0, peak - spread):peak + spread + 1].sum() / total
        tonal += share >= PEAK_SHARE
    return tonal / max(1, len(starts))
