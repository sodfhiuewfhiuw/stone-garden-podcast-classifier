# stone-garden-podcast-classifier
🎙️ 自動播客分類系統 - Stone Garden 版本。上傳 MP3 → 自動分類 → 獲得短視頻建議。


## 🚀 快速開始

### 本地運行
```bash
# 克隆項目
git clone https://github.com/sodfhiuewfhiuw/stone-garden-podcast-classifier.git
cd stone-garden-podcast-classifier

# 安裝依賴
pip install -r requirements.txt

# 運行應用
streamlit run app.py
```

### 線上部署

#### 選項 1: Streamlit Cloud（推薦）
1. 登入 https://share.streamlit.io
2. 點擊 "New app"
3. 選擇此 GitHub repo
4. 設置主檔案為 `app.py`
5. 部署完成！

#### 選項 2: Railway.app
[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template?template=https://github.com/sodfhiuewfhiuw/stone-garden-podcast-classifier)

## 📋 功能
- 🎙️ 上傳 MP3/WAV/M4A 播客文件
- 🤖 自動分類為 4 個類別
- 💡 获取短視頻推薦
- 📊 展示分析結果

## 🎯 分類類別
- 🚀 Energy/Motivational
- 💊 Spiritual/Healing
- 🧘 Meditation/Mindfulness  
- 📚 Educational/Teaching

## 技術棧
- Streamlit - Web UI
- Librosa - 音頻處理
- TensorFlow - 分類模型
- NumPy - 數據處理
