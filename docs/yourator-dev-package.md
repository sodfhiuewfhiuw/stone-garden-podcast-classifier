# Yourator 開發包（Dev Package）

> 版本：1.0.0 | 更新：2026-03-06

---

## 重大發現：Yourator 公開 API

Yourator 提供完整的公開 REST API，**無需 Playwright、無需登入、無需 API Key**。

| 項目 | 說明 |
|------|------|
| 端點 | `https://www.yourator.co/api/v4/jobs` |
| 認證 | 無（公開 API） |
| 格式 | JSON |
| 每頁筆數 | 20 筆 |
| 搜尋參數 | `keyword`, `page` |

---

## API 文件

### 基本請求

```
GET https://www.yourator.co/api/v4/jobs?page=1
GET https://www.yourator.co/api/v4/jobs?page=1&keyword=software+engineer
```

### 回應結構

```json
{
  "jobs": [
    {
      "id": 12345,
      "title": "Software Engineer",
      "company": {
        "brand_name": "Example Corp",
        "path": "example-corp"
      },
      "location": "台北市",
      "salary_min": 60000,
      "salary_max": 100000,
      "url": "https://www.yourator.co/companies/example-corp/jobs/software-engineer",
      "tags": [{ "name": "Node.js" }, { "name": "React" }],
      "updated_at": "2026-03-01T00:00:00Z"
    }
  ],
  "total_count": 480,
  "total_pages": 24,
  "current_page": 1
}
```

---

## 專案結構

```
stone-garden-podcast-classifier/
├── connectors/
│   ├── yourator.js        # Yourator 連接器（主體）
│   └── index.js           # MultiPlatformConnector（統一介面）
├── docs/
│   └── yourator-dev-package.md  # 本文件
├── hunter-config.js       # 搜尋設定
└── test-yourator-api.js   # API 探索 & 整合測試
```

---

## 完整連接器程式碼

> 檔案：`connectors/yourator.js`（可直接複製貼上）

```javascript
const https = require('https');

const YOURATOR_BASE_URL = 'https://www.yourator.co/api/v4/jobs';

function fetchJson(url) {
  return new Promise((resolve, reject) => {
    https.get(url, { headers: { Accept: 'application/json' } }, (res) => {
      let data = '';
      res.on('data', (c) => { data += c; });
      res.on('end', () => resolve(JSON.parse(data)));
    }).on('error', reject);
  });
}

function normalizeJob(job) {
  return {
    platform: 'yourator',
    id: String(job.id || ''),
    title: job.title || '',
    company: job.company?.brand_name || '',
    location: job.location || '',
    salary: job.salary_min ? `TWD ${job.salary_min} - ${job.salary_max}` : '',
    url: job.url || `https://www.yourator.co/jobs/${job.id}`,
    tags: (job.tags || []).map((t) => t.name || t),
    postedAt: job.updated_at || '',
  };
}

async function fetchPage({ keyword = '', page = 1 } = {}) {
  const params = new URLSearchParams({ page });
  if (keyword) params.append('keyword', keyword);
  const data = await fetchJson(`${YOURATOR_BASE_URL}?${params}`);
  return {
    jobs: (data.jobs || []).map(normalizeJob),
    totalPages: data.total_pages || 1,
    totalCount: data.total_count || 0,
  };
}

async function search(keyword, { maxPages = 3 } = {}) {
  const all = [];
  let page = 1, totalPages = 1;
  do {
    const result = await fetchPage({ keyword, page });
    all.push(...result.jobs);
    totalPages = result.totalPages;
    page++;
    if (page <= Math.min(totalPages, maxPages)) {
      await new Promise((r) => setTimeout(r, 1000));
    }
  } while (page <= Math.min(totalPages, maxPages));
  return all;
}

module.exports = { platform: 'yourator', search, fetchPage, normalizeJob };
```

---

## 快速開始

### 1. 安裝（無額外依賴）

Yourator 連接器只使用 Node.js 內建模組（`https`），無需安裝任何 npm 套件。

```bash
node --version  # 需要 Node.js 14+
```

### 2. 直接測試 API

```bash
node test-yourator-api.js                    # 預設搜尋 "engineer"
node test-yourator-api.js "software engineer"
node test-yourator-api.js "backend"
node test-yourator-api.js "frontend react"
```

### 3. 在程式碼中使用連接器

```javascript
const yourator = require('./connectors/yourator');

// 搜尋職缺（自動分頁）
const jobs = await yourator.search('software engineer', { maxPages: 3 });
console.log(`找到 ${jobs.length} 筆職缺`);
jobs.forEach((job) => {
  console.log(`${job.title} @ ${job.company} — ${job.salary}`);
});
```

### 4. 使用 MultiPlatformConnector

```javascript
const multi = require('./connectors');

const { results, errors } = await multi.search('backend engineer', {
  platforms: ['yourator'],
  maxPages: 2,
});
console.log(`共 ${results.length} 筆，${errors.length} 個錯誤`);
```

---

## 標準化輸出格式

每筆職缺統一輸出以下欄位，與現有系統相容：

| 欄位 | 型別 | 說明 |
|------|------|------|
| `platform` | string | 來源平台（`yourator`） |
| `id` | string | 職缺 ID |
| `title` | string | 職缺名稱 |
| `company` | string | 公司名稱 |
| `location` | string | 工作地點 |
| `salary` | string | 薪資範圍（TWD） |
| `description` | string | 職缺描述 |
| `requirements` | string | 職缺要求 |
| `url` | string | 職缺連結 |
| `tags` | string[] | 技能標籤 |
| `experience` | string | 工作經歷要求 |
| `jobType` | string | 職缺類型（全職/兼職） |
| `remote` | boolean | 是否支援遠端 |
| `postedAt` | string | 發布日期（ISO 8601） |
| `rawData` | object | 原始 API 回應 |

---

## 整合步驟

### Step 1：加入 MultiPlatformConnector

`connectors/index.js` 已自動引入 Yourator。若要新增其他平台：

```javascript
// connectors/index.js
const yourator = require('./yourator');
const newPlatform = require('./new-platform');  // 加入這行

const CONNECTORS = {
  yourator,
  newPlatform,  // 加入這行
};
```

### Step 2：更新 hunter-config.js

```javascript
// hunter-config.js
module.exports = {
  search: {
    keywords: ['software engineer', 'backend', 'frontend'],
    platforms: ['yourator'],  // 加入 'yourator'
    maxPages: 3,
  },
};
```

### Step 3：執行搜尋

```bash
node test-yourator-api.js "your keyword"
```

---

## 錯誤處理

連接器內建以下錯誤處理機制：

- **網路錯誤**：拋出帶有清楚訊息的 Error
- **JSON 解析失敗**：拋出帶有 URL 的 Error
- **空回應**：回傳空陣列（不拋出錯誤）
- **頁數超出**：自動停止分頁

MultiPlatformConnector 會捕捉各平台錯誤，確保單一平台失敗不影響其他平台：

```javascript
const { results, errors } = await multi.search('keyword');
// errors 陣列包含失敗平台的錯誤訊息
```

---

## 注意事項

1. **請求頻率**：兩次分頁請求之間預設延遲 1000ms，避免對伺服器造成壓力
2. **頁數限制**：建議 `maxPages` 設為 3-5，避免過度爬取
3. **API 穩定性**：此為公開 API，無法保證長期穩定；若回應格式改變，請更新 `normalizeJob`
4. **User-Agent**：連接器設定了合理的 User-Agent，請勿移除
