import streamlit as st
import librosa
import numpy as np
import io

st.set_page_config(page_title="Stone Garden Podcast Classifier", page_icon="gem", layout="wide")
st.title("Stone Garden Podcast Classifier")
st.markdown("### Auto-classify podcasts and get short video recommendations")
st.divider()

with st.sidebar:
    st.header("Usage Guide")
    st.markdown("""**Quick start:**
1. Upload MP3 file
2. System analyzes automatically
3. Get short video recommendations""")

uploaded_file = st.file_uploader("Select MP3 file", type=["mp3", "wav", "m4a"])

if uploaded_file is not None:
    st.success(f"Uploaded: {uploaded_file.name}")
    
    with st.spinner("Analyzing..."):
        audio_bytes = uploaded_file.read()
        audio, sr = librosa.load(io.BytesIO(audio_bytes), sr=22050)
        duration = librosa.get_duration(y=audio, sr=sr)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Duration", f"{duration:.1f}s")
        with col2:
            st.metric("Sample Rate", f"{sr}Hz")
        with col3:
            st.metric("Samples", f"{len(audio):,}")
        
        st.divider()
        st.subheader("Audio Features Analysis")
        
        mfcc = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=13)
        chroma = librosa.feature.chroma_stft(y=audio, sr=sr)
        zero_crossing = librosa.feature.zero_crossing_rate(audio)
        
        mfcc_mean = np.mean(mfcc, axis=1)
        chroma_mean = np.mean(chroma, axis=1)
        energy = np.sum(audio**2) / len(audio)
        rhythm_strength = np.std(zero_crossing)
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Energy Level", f"{energy:.4f}")
        with col2:
            st.metric("Rhythm Strength", f"{rhythm_strength:.4f}")
        
        st.divider()
        st.subheader("Classification Result")
        
        if energy > 0.01 and rhythm_strength > 0.1:
            podcast_type = "Energy & Motivation"
            category = "energy"
        elif chroma_mean[0] > 0.5:
            podcast_type = "Spiritual Healing"
            category = "spiritual"
        elif rhythm_strength < 0.05:
            podcast_type = "Meditation & Mindfulness"
            category = "meditation"
        else:
            podcast_type = "Educational Teaching"
            category = "education"
        
        st.success(f"### {podcast_type}")
        
        suggestions = {
            "energy": "IG Reels: 15-20s | High energy background + crystal animation",
            "spiritual": "Story/Shorts: 12-15s | Crystal aesthetics + lighting elements",
            "meditation": "TikTok: 20-30s | Calm background + flower animations",
            "education": "YouTube Shorts: 30s | Information graphics + crystal knowledge"
        }
        
        st.info(f"**Recommendation:** {suggestions[category]}")
else:
    st.info("Upload an MP3 file to start analysis")

# Updated 2025-12-04
