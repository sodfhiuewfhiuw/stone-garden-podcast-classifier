"""
app.py — Stone Garden Podcast Classifier

Systemic improvements:
  - PID lock: blocks duplicate Streamlit processes from sharing state
  - Health monitor: tracks error rates, consecutive failures, stale detection
  - 4-layer degradation: gracefully falls back when librosa analysis fails
  - Duplicate detection: SHA-256 per-session cache avoids re-analysis
  - Alert banners: surface actionable warnings immediately in the UI
"""

import hashlib
import os
import streamlit as st

from health import get_health, render_health_sidebar, render_alerts
from classifier import classify

# ── PID lock ──────────────────────────────────────────────────────────────────
# Warn when a second process tries to run — concurrent librosa loads on the
# same file cache can corrupt state.

LOCKFILE = "/tmp/stone-garden.pid"

def _check_pid_lock() -> bool:
    """Return True if this is the only running instance."""
    my_pid = str(os.getpid())
    if os.path.exists(LOCKFILE):
        try:
            stored = open(LOCKFILE).read().strip()
            if stored and stored != my_pid:
                try:
                    os.kill(int(stored), 0)  # signal 0 = existence check only
                    return False             # other process is alive
                except (ProcessLookupError, PermissionError):
                    pass                     # stale PID — safe to overwrite
        except (ValueError, OSError):
            pass
    open(LOCKFILE, "w").write(my_pid)
    return True


def _render_cached_result(cached: dict) -> None:
    layer = cached.get("layer", 1)
    layer_labels = {
        1: "L1 — Full analysis",
        2: "L2 — Basic analysis",
        3: "L3 — Metadata heuristic",
        4: "L4 — Record-only",
    }
    st.markdown(f"**Analysis layer (cached):** {layer_labels.get(layer, f'L{layer}')}")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Duration",    cached["duration"])
    with col2:
        st.metric("Sample Rate", cached["sample_rate"])
    with col3:
        st.metric("Samples",     cached["samples"])
    st.divider()
    st.success(f"### {cached['podcast_type']}")
    st.info(f"**Recommendation:** {cached['suggestion']}")


# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Stone Garden Podcast Classifier",
    page_icon="gem",
    layout="wide",
)
st.title("Stone Garden Podcast Classifier")
st.markdown("### Auto-classify podcasts and get short video recommendations")
st.divider()

# ── Session state init ────────────────────────────────────────────────────────

if "processed_hashes" not in st.session_state:
    st.session_state.processed_hashes = {}

health = get_health()

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Usage Guide")
    st.markdown("""**Quick start:**
1. Upload MP3 file
2. System analyzes automatically
3. Get short video recommendations""")
    st.divider()
    if st.button("Clear History"):
        st.session_state.processed_hashes = {}
        st.success("History cleared")
    render_health_sidebar(health)

# ── PID lock warning ──────────────────────────────────────────────────────────

if not _check_pid_lock():
    st.error(
        "DUPLICATE INSTANCE DETECTED — another Stone Garden process is already running. "
        "Close that tab or stop the other process to avoid cache conflicts."
    )
    st.stop()

# ── Alert banners ─────────────────────────────────────────────────────────────

render_alerts(health)

# ── Upload ────────────────────────────────────────────────────────────────────

uploaded_file = st.file_uploader("Select MP3 file", type=["mp3", "wav", "m4a"])

if uploaded_file is None:
    st.info("Upload an MP3 file to start analysis")
    st.stop()

audio_bytes = uploaded_file.read()
file_hash   = hashlib.sha256(audio_bytes).hexdigest()

# ── Duplicate detection ───────────────────────────────────────────────────────

if file_hash in st.session_state.processed_hashes:
    cached = st.session_state.processed_hashes[file_hash]
    st.warning(f"Duplicate detected: **{uploaded_file.name}** was already analyzed.")
    st.info(f"Showing cached result (original: **{cached['filename']}**)")
    _render_cached_result(cached)
    st.stop()

# ── Classification ────────────────────────────────────────────────────────────

st.success(f"Uploaded: {uploaded_file.name}")

with st.spinner("Analyzing…"):
    result, layer_error = classify(audio_bytes, uploaded_file.name)

# Layer status badge
layer_colors = {1: "green", 2: "orange", 3: "red", 4: "gray"}
layer_labels  = {
    1: "L1 — Full analysis (MFCC + Chroma + ZCR)",
    2: "L2 — Basic analysis (energy + ZCR only)",
    3: "L3 — Metadata heuristic (filename-based)",
    4: "L4 — Record-only (manual review required)",
}
color = layer_colors[result.layer]
st.markdown(f"**Analysis layer:** :{color}[{layer_labels[result.layer]}]")

if result.warning:
    st.error(result.warning) if result.layer >= 3 else st.warning(result.warning)

# ── Health tracking ───────────────────────────────────────────────────────────

if layer_error:
    health.record_failure(layer_error)
    render_alerts(health)
else:
    health.record_success(result.layer)

# ── Metrics ───────────────────────────────────────────────────────────────────

if any([result.duration, result.sample_rate, result.samples]):
    st.divider()
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Duration",    result.duration    or "—")
    with col2:
        st.metric("Sample Rate", result.sample_rate or "—")
    with col3:
        st.metric("Samples",     result.samples     or "—")

if any([result.energy, result.rhythm]):
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Energy Level",    result.energy or "—")
    with col2:
        st.metric("Rhythm Strength", result.rhythm or "—")

# ── Result ────────────────────────────────────────────────────────────────────

st.divider()
st.subheader("Classification Result")
st.success(f"### {result.podcast_type}")
st.info(f"**Recommendation:** {result.suggestion}")

# ── Cache ─────────────────────────────────────────────────────────────────────

st.session_state.processed_hashes[file_hash] = {
    "filename":     uploaded_file.name,
    "podcast_type": result.podcast_type,
    "suggestion":   result.suggestion,
    "duration":     result.duration     or "—",
    "sample_rate":  result.sample_rate  or "—",
    "samples":      result.samples      or "—",
    "energy":       result.energy       or "—",
    "rhythm":       result.rhythm       or "—",
    "layer":        result.layer,
}
