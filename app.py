app.pyimport streamlit as st
import librosa
import numpy as np
import io

# Page Config
st.set_page_config(
    page_title="🎙️ Stone Garden 播客分類器",
    page_icon="🎙️",
    layout="wide"
)

st.title("🎙️ Stone Garden 播客分類器")
st.markdown("### 自動分類播客 → 獲得短視頻建議 ✨")
st.divider()

with st.sidebar:
    st.header("📃 使用指南")
    st.markdown("""
    **3 步驟快速上手:**
    1. 上傳 MP3 播客檔案
    2. 系統自動分析
    3. 獲得短視頻建議
    """)

uploaded_file = st.file_uploader(
    "選擇 MP3 檔案",
    type=["mp3", "wav", "m4a"]
)

if uploaded_file is not None:
    st.success(f"✅ 已上傳: {uploaded_file.name}")
    
    with st.spinner("🔄 分析中..."):
        audio_bytes = uploaded_file.read()
        audio, sr = librosa.load(io.BytesIO(audio_bytes), sr=22050)
        duration = librosa.get_duration(y=audio, sr=sr)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("⏱️ 時長", f"{duration:.1f}秒")
    with col2:
        st.metric("🎵 採樣率", f"{sr}Hz")
    with col3:
        st.metric("📈 樣本數", f"{len(audio):,}")
    
    st.divider()
    st.subheader("🔍 音頻特徵分析")
    
    mfcc = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=13)
    chroma = librosa.feature.chroma_stft(y=audio, sr=sr)
    zero_crossing = librosa.feature.zero_crossing_rate(audio)
    
    mfcc_mean = np.mean(mfcc, axis=1)
    chroma_mean = np.mean(chroma, axis=1)
    energy = np.sum(audio**2) / len(audio)
    rhythm_strength = np.std(zero_crossing)
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("⚡ 能量", f"{energy:.4f}")
    with col2:
        st.metric(🎵 節奏強度", f"{rhythm_strength:.4f}")
    
    st.divider()
    st.subheader("🎯 播客分類結果")
    
    if energy > 0.01 and rhythm_strength > 0.1:
        podcast_type = "🚀 動能釨寶"
        category = "energy"
    elif chroma_mean[0] > 0.5:
        podcast_type = "💊 灵性羊毀"
        category = "spiritual"
    elif rhythm_strength < 0.05:
        podcast_type = "🚽 冪戃靜覽"
        category = "meditation"
    else:
        podcast_type = "📃 教學談話"
        category = "education"
    
    st.success(f"### {podcast_type}")
    
    suggestions = {
        "energy": "IG Reels: 15-20秒 | 高能量背景 + 水晶動画",
        "spiritual": "Story/Shorts: 12-15秒 | 水晶堂 + 採光元素",
        "meditation": "TikTok: 20-30秒 | 靜謂背景 + 花礙兠画",
        "education": "YouTube Shorts: 30秒 | 資訊表 + 水晶知識"
    }
    
    st.info(f"**建議**: {suggestions[category]}")
    
else:
    st.info("👆 請上傳一個 MP3 檔案開始分析")

