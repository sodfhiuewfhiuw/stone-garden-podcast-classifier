FROM python:3.9-slim

WORKDIR /app

# 安裝系統依賴
RUN apt-get update && apt-get install -y \
    libsndfile1 \
    libsndfile1-dev \
    && rm -rf /var/lib/apt/lists/*

# 複製 requirements.txt
COPY requirements.txt .

# 安裝 Python 依賴
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用檔案
COPY . .

# 暴露端口
EXPOSE 8501

# 設置 Streamlit 配置
RUN mkdir -p ~/.streamlit && echo '[server]\nheadless = true\nport = 8501' > ~/.streamlit/config.toml

# 運行應用
CMD ["streamlit", "run", "app.py"]
