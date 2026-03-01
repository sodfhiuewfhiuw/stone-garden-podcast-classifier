# 品牌內容策略助手 — COWORK 安裝說明書

> 適用版本 v1.0 · Python 3.11+ · 2026/03

---

## 系統架構一覽

```
品牌策略助手
├── Dashboard (port 8501)   — Streamlit 視覺化後台（人工操作用）
├── REST API  (port 8502)   — FastAPI 自動化介面（龍蝦自動化操作用）
├── Scheduler               — APScheduler 排程（每日抓資料、每週週報）
└── SQLite DB               — 本地資料庫，存貼文、分析、設定
```

---

## 一、環境需求

| 項目 | 需求 |
|------|------|
| Python | 3.11 以上 |
| 作業系統 | macOS / Linux / Windows WSL |
| 硬碟空間 | 最少 500 MB |
| 對外網路 | 需要（抓 Threads / IG 資料、呼叫 Claude API）|

---

## 二、安裝步驟

### 1. 取得程式碼

```bash
git clone <repo-url>
cd stone-garden-podcast-classifier/brand-agent
```

### 2. 建立虛擬環境

```bash
python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows
```

### 3. 安裝所有套件

```bash
pip install -r requirements.txt
```

安裝清單包含：

| 套件 | 用途 |
|------|------|
| `streamlit` | Dashboard 視覺化後台 |
| `fastapi` + `uvicorn` | REST API server（龍蝦用）|
| `anthropic` | Claude AI 分析 |
| `apscheduler` | 自動排程 |
| `pandas` | 資料處理 |
| `fpdf2` | PDF 週報生成 |
| `cryptography` | Token 加密存儲 |
| `python-dotenv` | 環境變數讀取 |

---

## 三、帳號金鑰設定

系統支援兩種設定方式：**環境變數**（推薦）或 **Dashboard UI 設定頁面**。

### 方法 A — 環境變數（COWORK 伺服器部署首選）

建立 `.env` 檔案，放在 `brand-agent/` 目錄下：

```dotenv
# ── Claude AI ────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxx

# ── REST API 認證金鑰（龍蝦用，自訂任意字串）───────────────
API_SECRET=你想設定的任意密碼

# ── (選填) Threads / IG 也可用環境變數 ────────────────────
# 也可以在 Dashboard 設定頁填，會加密存到本地
THREADS_TOKEN=
IG_TOKEN=
IG_ACCOUNT_ID=
```

> **注意**：`.env` 已加入 `.gitignore`，不會被 commit。

### 方法 B — Dashboard UI 設定

1. 啟動 Dashboard（見下方）
2. 進入「⚙️ 設定」頁面
3. 填入 Threads Token、IG Token、Claude API Key、收件 Email 等
4. 點「儲存設定」

Token 會用 Fernet 加密後存在本地 `config/secrets.enc`。

---

## 四、啟動服務

### 一次啟動全部（推薦）

排程 + Dashboard 同時運行：

```bash
cd brand-agent
python main.py
```

- Dashboard：`http://localhost:8501`
- 排程在背景自動執行（每日 03:00 抓資料、每週一 08:00 寄週報）

---

### 單獨啟動 REST API（龍蝦自動化用）

```bash
python api.py
# 或
python main.py --api
```

- API 服務：`http://localhost:8502`
- API 文件（Swagger）：`http://localhost:8502/docs`

---

### 各服務分開啟動

```bash
# 只跑排程（背景資料抓取）
python main.py --scheduler

# 只跑 Dashboard
python main.py --dashboard

# 只跑 API
python main.py --api --api-port 8502
```

---

### 一次性手動執行（測試用）

```bash
# 立即抓一次資料
python main.py --fetch-now

# 立即跑 AI 分析
python main.py --analyze-now

# 立即生成並寄送週報
python main.py --report-now
```

---

## 五、REST API 使用說明（龍蝦自動化）

### 認證方式

每次呼叫帶上 Header：

```
X-API-Key: 你在 .env 設定的 API_SECRET
```

未設定 `API_SECRET` 時為開放存取（只建議本機測試時使用）。

---

### 所有端點

#### `GET /health` — 系統健康狀態

```bash
curl http://localhost:8502/health \
     -H "X-API-Key: 你的密碼"
```

回傳範例：
```json
{
  "status": "ok",
  "timestamp": "2026-03-01T10:00:00Z",
  "connections": {
    "threads": true,
    "instagram": true,
    "claude_ai": true
  },
  "competitor_count": 3,
  "api_key_configured": true
}
```

---

#### `POST /actions/fetch` — 立即抓取 Threads + IG 資料

```bash
curl -X POST http://localhost:8502/actions/fetch \
     -H "X-API-Key: 你的密碼"
```

> 背景執行，約 1-2 分鐘完成。

---

#### `POST /actions/analyze` — 立即執行 Claude AI 週分析

```bash
curl -X POST http://localhost:8502/actions/analyze \
     -H "X-API-Key: 你的密碼"
```

> 背景執行，約 2-3 分鐘完成。包含競品分析、自家帳號分析、內容行事曆。

---

#### `POST /actions/report` — 立即生成 PDF 週報並寄送

```bash
curl -X POST http://localhost:8502/actions/report \
     -H "X-API-Key: 你的密碼"
```

> 背景執行，完成後自動寄至設定的 Email 信箱。

---

#### `POST /actions/hashtags` — 即時 Hashtag 建議

```bash
curl -X POST http://localhost:8502/actions/hashtags \
     -H "X-API-Key: 你的密碼" \
     -H "Content-Type: application/json" \
     -d '{
       "topic": "岩盤浴健康療程",
       "post_type": "圖文",
       "platform": "Instagram",
       "brand_tone": "療癒、放鬆"
     }'
```

回傳範例：
```json
{
  "brand_hashtags": ["#石庭石療", "#岩盤浴"],
  "topic_hashtags": ["#健康療程", "#身心放鬆", "#SPA體驗"],
  "trending_hashtags": ["#週末放鬆", "#台北SPA"],
  "all_hashtags": ["#石庭石療", "#岩盤浴", "..."],
  "reasoning": "兼顧品牌識別與高搜尋量話題標籤，強化療癒形象定位"
}
```

---

#### `GET /data/posts` — 查詢貼文紀錄

```bash
# 查所有平台最新 20 篇
curl "http://localhost:8502/data/posts" \
     -H "X-API-Key: 你的密碼"

# 只查競品 Threads 資料，最多 50 筆
curl "http://localhost:8502/data/posts?platform=threads&account_type=competitor&limit=50" \
     -H "X-API-Key: 你的密碼"
```

Query 參數：

| 參數 | 說明 | 預設 |
|------|------|------|
| `platform` | `threads` / `instagram` | 全部 |
| `account_type` | `own` / `competitor` | 全部 |
| `limit` | 最多筆數（上限 100）| 20 |

---

#### `GET /data/competitors` — 競品帳號清單

```bash
curl http://localhost:8502/data/competitors \
     -H "X-API-Key: 你的密碼"
```

---

#### `GET /data/analysis/{type}` — 取得最新 AI 分析結果

```bash
# 競品分析
curl http://localhost:8502/data/analysis/competitor \
     -H "X-API-Key: 你的密碼"

# 自家帳號分析
curl http://localhost:8502/data/analysis/own_account \
     -H "X-API-Key: 你的密碼"

# 本週內容行事曆
curl http://localhost:8502/data/analysis/content_calendar \
     -H "X-API-Key: 你的密碼"

# 週報摘要
curl http://localhost:8502/data/analysis/weekly_report \
     -H "X-API-Key: 你的密碼"
```

---

## 六、自動排程說明

系統啟動後會依照以下時間自動執行：

| 時間 | 任務 |
|------|------|
| 每天 **03:00** (台灣時間) | 抓取 Threads + IG 最新資料 |
| 每週一 **06:00** | 執行 Claude AI 競品分析 + 內容行事曆 |
| 每週一 **08:00** | 生成 PDF 週報並寄送 Email |

---

## 七、目錄結構

```
brand-agent/
├── api.py                  ← REST API server（龍蝦用）
├── main.py                 ← 主程式入口
├── requirements.txt
├── COWORK_SETUP.md         ← 本文件
│
├── config/
│   ├── settings.py         ← 設定 & 加密 Token 管理
│   ├── secrets.enc         ← 加密存放的 API Token（自動生成）
│   └── .key                ← 加密金鑰（勿外傳）
│
├── collectors/
│   ├── threads_api.py      ← Threads 資料抓取
│   └── instagram_api.py    ← Instagram 資料抓取
│
├── analysis/
│   ├── claude_analyzer.py  ← Claude 競品 & 帳號分析
│   └── content_advisor.py  ← 內容行事曆 & Hashtag 建議
│
├── dashboard/
│   ├── app.py              ← Streamlit 主頁
│   └── pages/              ← 各頁面模組
│
├── reports/
│   └── weekly_report.py    ← PDF 週報 + Email 寄送
│
├── db/
│   └── database.py         ← SQLite CRUD
│
└── data/                   ← 資料目錄（自動建立）
    ├── brand_agent.db      ← SQLite 資料庫
    ├── reports/            ← PDF 週報存放
    └── app.log             ← 系統日誌
```

---

## 八、常見問題

**Q：API_SECRET 要設多少字元？**
> 隨意，建議 16 字元以上的隨機字串。可用 `python -c "import secrets; print(secrets.token_hex(16))"` 生成。

**Q：API 回傳 401？**
> 檢查 Header 是否正確：`X-API-Key: 你的密碼`，且與 `.env` 的 `API_SECRET` 一致。

**Q：`/actions/analyze` 回傳 502？**
> Claude API Key 未設定或額度不足。先用 `/health` 確認 `claude_ai: true`。

**Q：第一次執行 `/data/analysis/content_calendar` 回傳 found: false？**
> 正常，需先執行 `POST /actions/fetch` 抓資料，再執行 `POST /actions/analyze` 跑分析。

**Q：Dashboard 和 API 可以同時跑嗎？**
> 可以，分兩個 terminal 分別執行：
> ```bash
> # Terminal 1
> python main.py --dashboard
> # Terminal 2
> python api.py
> ```

---

*文件最後更新：2026-03-01*
