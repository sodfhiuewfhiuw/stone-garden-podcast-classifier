"""
classifier.py — 4-layer degradation strategy for audio classification

Layer 1 (full):     librosa MFCC + chroma + ZCR analysis
Layer 2 (basic):    librosa waveform energy + duration only
Layer 3 (metadata): file size / sample-count heuristic, no audio decode
Layer 4 (record):   pure record mode — no classification, just log filename

Each layer returns a ClassificationResult. Callers check `.layer` to know
how reliable the result is.
"""

import io
import hashlib
from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class ClassificationResult:
    layer: int                      # 1-4: which layer produced this
    podcast_type: str
    category: str
    suggestion: str
    duration: Optional[str] = None
    sample_rate: Optional[str] = None
    samples: Optional[str] = None
    energy: Optional[str] = None
    rhythm: Optional[str] = None
    warning: Optional[str] = None  # set when degraded


SUGGESTIONS = {
    "energy":     "IG Reels: 15-20s | High energy background + crystal animation",
    "spiritual":  "Story/Shorts: 12-15s | Crystal aesthetics + lighting elements",
    "meditation": "TikTok: 20-30s | Calm background + flower animations",
    "education":  "YouTube Shorts: 30s | Information graphics + crystal knowledge",
    "unknown":    "Manual review required — classification unavailable",
}


def _categorize_from_features(energy: float, chroma_mean: float, rhythm: float) -> tuple:
    if energy > 0.01 and rhythm > 0.1:
        return "Energy & Motivation", "energy"
    if chroma_mean > 0.5:
        return "Spiritual Healing", "spiritual"
    if rhythm < 0.05:
        return "Meditation & Mindfulness", "meditation"
    return "Educational Teaching", "education"


# ── Layer 1: full librosa analysis ──────────────────────────────────────────

def _layer1(audio_bytes: bytes) -> ClassificationResult:
    import librosa  # imported lazily so layers 3-4 don't need it

    audio, sr = librosa.load(io.BytesIO(audio_bytes), sr=22050)
    duration = librosa.get_duration(y=audio, sr=sr)

    mfcc    = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=13)
    chroma  = librosa.feature.chroma_stft(y=audio, sr=sr)
    zcr     = librosa.feature.zero_crossing_rate(audio)

    energy        = float(np.sum(audio ** 2) / len(audio))
    rhythm        = float(np.std(zcr))
    chroma_mean   = float(np.mean(chroma[0]))

    ptype, cat = _categorize_from_features(energy, chroma_mean, rhythm)
    return ClassificationResult(
        layer=1,
        podcast_type=ptype,
        category=cat,
        suggestion=SUGGESTIONS[cat],
        duration=f"{duration:.1f}s",
        sample_rate=f"{sr}Hz",
        samples=f"{len(audio):,}",
        energy=f"{energy:.4f}",
        rhythm=f"{rhythm:.4f}",
    )


# ── Layer 2: basic waveform stats (no MFCC/chroma) ──────────────────────────

def _layer2(audio_bytes: bytes) -> ClassificationResult:
    import librosa

    audio, sr = librosa.load(io.BytesIO(audio_bytes), sr=22050)
    duration  = librosa.get_duration(y=audio, sr=sr)
    energy    = float(np.sum(audio ** 2) / len(audio))
    zcr       = librosa.feature.zero_crossing_rate(audio)
    rhythm    = float(np.std(zcr))

    ptype, cat = _categorize_from_features(energy, 0.0, rhythm)
    return ClassificationResult(
        layer=2,
        podcast_type=ptype,
        category=cat,
        suggestion=SUGGESTIONS[cat],
        duration=f"{duration:.1f}s",
        sample_rate=f"{sr}Hz",
        samples=f"{len(audio):,}",
        energy=f"{energy:.4f}",
        rhythm=f"{rhythm:.4f}",
        warning="L2 fallback: chroma analysis unavailable — accuracy reduced",
    )


# ── Layer 3: file-metadata heuristic (no audio decode) ──────────────────────

def _layer3(audio_bytes: bytes, filename: str) -> ClassificationResult:
    size_kb = len(audio_bytes) / 1024
    # rough bitrate assumption: 128 kbps → ~16 KB/s
    est_duration = size_kb / 16
    name_lower   = filename.lower()

    if any(k in name_lower for k in ("meditat", "calm", "relax", "sleep")):
        ptype, cat = "Meditation & Mindfulness", "meditation"
    elif any(k in name_lower for k in ("spirit", "heal", "chakra", "crystal")):
        ptype, cat = "Spiritual Healing", "spiritual"
    elif any(k in name_lower for k in ("motivat", "energy", "power", "hype")):
        ptype, cat = "Energy & Motivation", "energy"
    else:
        ptype, cat = "Educational Teaching", "education"

    return ClassificationResult(
        layer=3,
        podcast_type=ptype,
        category=cat,
        suggestion=SUGGESTIONS[cat],
        duration=f"~{est_duration:.0f}s (estimated)",
        warning="L3 fallback: audio decode failed — classification based on filename only",
    )


# ── Layer 4: record-only mode ────────────────────────────────────────────────

def _layer4(filename: str) -> ClassificationResult:
    return ClassificationResult(
        layer=4,
        podcast_type="Unclassified",
        category="unknown",
        suggestion=SUGGESTIONS["unknown"],
        warning="L4 record-only: all analysis layers failed — file logged for manual review",
    )


# ── Public entry point ───────────────────────────────────────────────────────

def classify(audio_bytes: bytes, filename: str) -> tuple[ClassificationResult, Optional[str]]:
    """
    Attempt classification through layers 1→2→3→4.
    Returns (result, error_message). error_message is None on full success.
    """
    errors = []

    for layer_fn, args in [
        (_layer1, (audio_bytes,)),
        (_layer2, (audio_bytes,)),
        (_layer3, (audio_bytes, filename)),
        (_layer4, (filename,)),
    ]:
        try:
            result = layer_fn(*args)
            err_msg = "; ".join(errors) if errors else None
            return result, err_msg
        except Exception as exc:
            errors.append(f"L{len(errors)+1}: {exc}")

    # Should never reach here — layer 4 never raises
    return _layer4(filename), "; ".join(errors)
