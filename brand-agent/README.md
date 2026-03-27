# Brand Content Strategy Agent 🎯

> AI-powered brand content strategy assistant for social media managers.
> Automates competitor monitoring, performance analysis, and weekly content planning using Claude AI + Threads API + Instagram Graph API.

---

## What It Does

This system eliminates the 8+ hours per week that brand marketers spend manually collecting competitor data and writing reports. It:

- **Monitors up to 10 competitor accounts** on Threads — engagement, hashtags, posting patterns
- **Analyzes your own Instagram/Threads performance** — reach, engagement rate, best posting times
- **Generates weekly content calendars** using Claude AI based on real data
- **Sends automated PDF reports** every Monday at 8:00 AM
- **Provides a zero-jargon setup UI** — no API/Token terminology shown to clients

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Layer 3: Dashboard                       │
│              Streamlit Web UI  (port 8501)                   │
│  Overview │ Competitor │ IG Analysis │ AI Suggestions │ Settings │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                    Layer 2: Processing                       │
│  Claude AI Analyzer │ Content Advisor │ APScheduler          │
│  Weekly Report PDF  │ Email SMTP      │ Encryption (Fernet)  │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                     Layer 1: Data                            │
│   Threads API  │  Instagram Graph API  │  SQLite Database    │
└─────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
brand-agent/
├── main.py                    # Entry point: scheduler + dashboard
├── requirements.txt
├── config/
│   ├── settings.py            # Encrypted credential management
│   └── secrets.enc            # Fernet-encrypted API keys (auto-generated)
├── collectors/
│   ├── threads_api.py         # Threads API integration
│   └── instagram_api.py       # Instagram Graph API integration
├── analysis/
│   ├── claude_analyzer.py     # Claude AI prompts & analysis
│   └── content_advisor.py     # Content calendar generation
├── dashboard/
│   ├── app.py                 # Streamlit main app
│   └── pages/
│       ├── overview.py        # KPI overview page
│       ├── competitor.py      # Competitor monitoring
│       ├── instagram.py       # IG performance analysis
│       ├── suggestions.py     # AI content suggestions
│       └── settings.py        # Zero-jargon client setup UI
├── reports/
│   └── weekly_report.py       # PDF generation + email sending
├── db/
│   └── database.py            # SQLite schema & CRUD
└── data/                      # Auto-created: DB, reports, logs
```

---

## Quick Start

### Prerequisites
- Python 3.11+
- Meta Developer Account (for Threads API + Instagram Graph API)
- Anthropic API Key
- Gmail or SMTP account (for email reports)

### Installation

```bash
git clone https://github.com/sodfhiuewfhiuw/stone-garden-podcast-classifier.git
cd stone-garden-podcast-classifier/brand-agent

pip install -r requirements.txt
```

### Configuration

Set your API key as an environment variable (recommended):

```bash
export ANTHROPIC_API_KEY=sk-ant-your-key-here
```

Or configure everything through the in-app Settings UI.

### Run

```bash
# Full system (scheduler + dashboard)
python main.py

# Dashboard only
python main.py --dashboard

# Fetch data immediately
python main.py --fetch-now

# Run AI analysis now
python main.py --analyze-now

# Generate and send weekly report
python main.py --report-now
```

Open your browser at **http://localhost:8501**

---

## First-Time Setup (via Settings UI)

1. **Connect Threads Account** — paste your Threads Access Token, test connection
2. **Connect Instagram Account** — paste IG Graph API Token + Account ID, test connection
3. **Add Competitors** — enter `@username` + Threads User ID for each competitor (up to 10)
4. **Set Report Email** — add recipients for the Monday weekly report
5. **Save & Activate** — all credentials encrypted locally with AES-256 Fernet

---

## Tech Stack

| Category | Technology |
|----------|-----------|
| AI Analysis | Claude Sonnet 4.6 (Anthropic) |
| Data Collection | Threads API v1.0 + Instagram Graph API v21.0 |
| Backend | Python 3.11 |
| Dashboard | Streamlit |
| Scheduler | APScheduler |
| Database | SQLite |
| Encryption | Python `cryptography` (Fernet) |
| PDF Reports | fpdf2 |
| Version Control | Git + GitHub |

---

## Automated Schedule

| Time | Task |
|------|------|
| Daily 03:00 (Taipei) | Fetch data from all platforms |
| Monday 06:00 | Run Claude AI weekly analysis |
| Monday 08:00 | Generate PDF report + send email |

---

## Privacy & Security

- All API tokens encrypted with **AES-256 Fernet symmetric encryption**
- Encryption key stored at `config/.key` — keep this file safe
- **No data uploaded to third-party servers**
- Reset by deleting `config/secrets.enc`

---

## Development Phases

| Phase | Status | Deliverable |
|-------|--------|-------------|
| Phase 1 | ✅ | Data layer: Threads API, SQLite, schema |
| Phase 2 | ✅ | AI layer: Claude analyzer, IG API, scheduler |
| Phase 3 | ✅ | Dashboard: all pages including zero-jargon settings |
| Phase 4 | ✅ | Reports: PDF generation, email automation |
| Phase 5 | ✅ | Portfolio: README, architecture, demo |

---

## Author

**祐誠 × Claude Sonnet 4.6** · 2026.03

*Built as a portfolio project demonstrating AI-powered automation for brand content strategy.*
