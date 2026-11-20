"""Lazy in-process models: faster-whisper (ASR) and CLAP (sound)."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import numpy as np

from backend.config import load_models_config, repo_path, resolved_models, selected_profile_name
from domain.storm.tones import alarm_tone_fraction

_lock = threading.Lock()
_whisper: Any = None
_clap: Any = None
_clap_processor: Any = None
_status = {"asr": "not_loaded", "sound": "not_loaded"}


def model_status() -> dict[str, str]:
    return dict(_status)


def _asr_path() -> Path:
    resolved = resolved_models()
    profile = load_models_config()["profiles"][selected_profile_name() or "mac16"]
    key = profile["asr"]
    entry = resolved[key]
    return repo_path(entry["path"])


def _clap_path() -> Path:
    resolved = resolved_models()
    profile = load_models_config()["profiles"][selected_profile_name() or "mac16"]
    key = profile["sound"]
    entry = resolved[key]
    return repo_path(entry["path"])


def get_whisper():
    global _whisper
    with _lock:
        if _whisper is None:
            from faster_whisper import WhisperModel

            path = _asr_path()
            # int8 on CPU is the planned default; Metal Mac still uses CPU for whisper here.
            _whisper = WhisperModel(str(path), device="cpu", compute_type="int8")
            _status["asr"] = "up"
        return _whisper


def get_clap():
    global _clap, _clap_processor
    with _lock:
        if _clap is None:
            from transformers import ClapModel, ClapProcessor

            path = _clap_path()
            _clap_processor = ClapProcessor.from_pretrained(str(path), local_files_only=True)
            _clap = ClapModel.from_pretrained(str(path), local_files_only=True)
            _clap.eval()
            _status["sound"] = "up"
        return _clap, _clap_processor


# Labels tried with several phrasings (plan: sound identification tries several wordings).
SOUND_LABELS: dict[str, list[str]] = {
    "smoke_alarm": ["smoke alarm beeping", "fire alarm chirping", "smoke detector beep"],
    "co_alarm": ["carbon monoxide alarm", "CO alarm beeping", "four beep alarm"],
    "siren": ["emergency siren", "ambulance siren", "police siren"],
    "rain": ["rain falling", "heavy rain", "rainfall"],
    "wind": ["strong wind", "wind howling", "gusty wind"],
    "rushing_water": ["rushing water", "flood water flowing", "water pouring"],
    "generator": ["portable generator running", "gas generator engine"],
    "chainsaw": ["chainsaw cutting", "chainsaw engine"],
    "speech": ["person speaking", "human speech", "conversation"],
}


def decode_audio(path: Path, sample_rate: int) -> np.ndarray:
    """Decode with PyAV to mono float32 at sample_rate."""
    import av

    samples: list[np.ndarray] = []
    with av.open(str(path)) as container:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            return np.zeros(0, dtype=np.float32)
        resampler = av.audio.resampler.AudioResampler(format="flt", layout="mono", rate=sample_rate)
        for packet in container.demux(stream):
            for frame in packet.decode():
                for out in resampler.resample(frame):
                    arr = out.to_ndarray()
                    if arr.ndim > 1:
                        arr = arr[0]
                    samples.append(np.asarray(arr, dtype=np.float32).reshape(-1))
        # flush
        for out in resampler.resample(None):
            arr = out.to_ndarray()
            if arr.ndim > 1:
                arr = arr[0]
            samples.append(np.asarray(arr, dtype=np.float32).reshape(-1))
    if not samples:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(samples)


def transcribe(path: Path) -> list[dict]:
    """Return segments with word timings: [{t_start,t_end,text,words}]."""
    model = get_whisper()
    audio = decode_audio(path, 16000)
    if audio.size == 0:
        return []
    segments, _info = model.transcribe(
        audio,
        language="en",
        word_timestamps=True,
        vad_filter=True,
    )
    out = []
    for seg in segments:
        words = []
        if seg.words:
            words = [{"t_start": w.start, "t_end": w.end, "text": w.word} for w in seg.words]
        out.append({
            "t_start": float(seg.start or 0.0),
            "t_end": float(seg.end or 0.0),
            "text": (seg.text or "").strip(),
            "words": words,
        })
    return out


def classify_sounds(path: Path, window_s: float = 5.0, hop_s: float = 2.5) -> list[dict]:
    """CLAP over sliding windows at 48 kHz. Returns [{t_start,t_end,label,score,tone}].

    tone is the share of the window with an alarm-like 3 kHz beep (domain/storm/tones.py).
    """
    import torch

    model, processor = get_clap()
    audio = decode_audio(path, 48000)
    if audio.size == 0:
        return []

    phrases: list[str] = []
    phrase_to_label: list[str] = []
    for label, variants in SOUND_LABELS.items():
        for v in variants:
            phrases.append(v)
            phrase_to_label.append(label)

    duration = audio.size / 48000.0
    events: list[dict] = []
    t = 0.0
    while t < duration:
        t_end = min(t + window_s, duration)
        start_i = int(t * 48000)
        end_i = int(t_end * 48000)
        chunk = audio[start_i:end_i]
        if chunk.size < 4800:  # < 0.1 s
            break
        inputs = processor(
            text=phrases,
            audios=[chunk],
            sampling_rate=48000,
            return_tensors="pt",
            padding=True,
        )
        with torch.no_grad():
            out = model(**inputs)
            probs = torch.softmax(out.logits_per_audio, dim=-1)[0].cpu().numpy()
        # Best phrase → map to label; keep if above threshold
        best_i = int(probs.argmax())
        score = float(probs[best_i])
        label = phrase_to_label[best_i]
        if score >= 0.18:  # low bar; label-specific tuning comes later
            events.append({"t_start": t, "t_end": t_end, "label": label, "score": round(score, 3),
                           "tone": round(alarm_tone_fraction(chunk, 48000), 3)})
        t += hop_s

    # Merge adjacent same-label windows
    merged: list[dict] = []
    for ev in events:
        if merged and merged[-1]["label"] == ev["label"] and ev["t_start"] <= merged[-1]["t_end"] + 0.1:
            merged[-1]["t_end"] = ev["t_end"]
            merged[-1]["score"] = max(merged[-1]["score"], ev["score"])
            merged[-1]["tone"] = max(merged[-1]["tone"], ev["tone"])
        else:
            merged.append(dict(ev))
    return merged
