"""
Brand Content Strategy Agent — REST API for Automation
Provides HTTP endpoints for external tools (e.g., 龍蝦) to trigger
data fetch, AI analysis, and report generation programmatically.

Usage:
    python api.py                        # Run API server on port 8502
    python api.py --port 9000            # Custom port

Authentication:
    Set API_SECRET env var or configure via Settings UI.
    Pass as header:  X-API-Key: <your-secret>

Endpoints:
    GET  /health                         System status
    POST /actions/fetch                  Trigger data fetch
    POST /actions/analyze                Run AI weekly analysis
    POST /actions/report                 Generate + send PDF report
    POST /actions/hashtags               Generate hashtag suggestions
    GET  /data/posts                     Query recent posts
    GET  /data/competitors               List competitor accounts
    GET  /data/analysis/{type}           Get latest AI analysis result
"""

import sys
import os
import logging
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

logger = logging.getLogger(__name__)

# ── FastAPI app ────────────────────────────────────────────────────────────────

try:
    from fastapi import FastAPI, HTTPException, Security, BackgroundTasks
    from fastapi.security.api_key import APIKeyHeader
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    from typing import Optional
except ImportError:
    raise SystemExit("請先安裝依賴：pip install fastapi uvicorn")

app = FastAPI(
    title="Brand Content Strategy Agent API",
    description="龍蝦自動化操作介面 — 觸發資料抓取、AI 分析、週報生成",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── Authentication ─────────────────────────────────────────────────────────────

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def _get_configured_key() -> str:
    """Load API key from env var or secrets store."""
    key = os.environ.get("API_SECRET", "")
    if not key:
        try:
            from config.settings import get_secret
            key = get_secret("api_secret_key") or ""
        except Exception:
            pass
    return key


def require_api_key(api_key: str = Security(API_KEY_HEADER)):
    configured = _get_configured_key()
    if not configured:
        # No key configured → open access (dev mode)
        return
    if api_key != configured:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ── Request / Response Models ──────────────────────────────────────────────────

class HashtagRequest(BaseModel):
    topic: str
    post_type: str = "圖文"
    platform: str = "Instagram"
    brand_tone: str = ""


class ActionResponse(BaseModel):
    success: bool
    message: str
    data: dict = {}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _init():
    """Ensure DB and data directories are ready."""
    (BASE_DIR / "data").mkdir(exist_ok=True)
    (BASE_DIR / "data" / "reports").mkdir(exist_ok=True)
    from db.database import init_db
    init_db()


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Status"])
def health(api_key: str = Security(API_KEY_HEADER)):
    """系統健康狀態與帳號連接概況。"""
    require_api_key(api_key)
    try:
        from config.settings import Secrets, AppSettings
        threads_ok = bool(Secrets.threads_token())
        ig_ok = bool(Secrets.ig_token())
        claude_ok = bool(Secrets.claude_api_key())
        competitors = AppSettings.competitor_accounts()
        return {
            "status": "ok",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "connections": {
                "threads": threads_ok,
                "instagram": ig_ok,
                "claude_ai": claude_ok,
            },
            "competitor_count": len(competitors),
            "api_key_configured": bool(_get_configured_key()),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/actions/fetch", response_model=ActionResponse, tags=["Actions"])
def action_fetch(
    background_tasks: BackgroundTasks,
    api_key: str = Security(API_KEY_HEADER),
):
    """
    立即觸發資料抓取（Threads + Instagram）。
    在背景執行，立即回傳確認訊息。
    """
    require_api_key(api_key)

    def _do_fetch():
        _init()
        try:
            from config.settings import Secrets, AppSettings
            from collectors.threads_api import ThreadsCollector, fetch_and_store_own, fetch_and_store_competitor
            from collectors.instagram_api import InstagramCollector, fetch_and_store_ig

            threads_token = Secrets.threads_token()
            results = []

            if threads_token:
                collector = ThreadsCollector(threads_token)
                count = fetch_and_store_own(collector, limit=50)
                results.append(f"Threads own: {count}")
                for acc in AppSettings.competitor_accounts():
                    if acc.get("user_id"):
                        c = fetch_and_store_competitor(collector, acc["username"], acc["user_id"])
                        results.append(f"@{acc['username']}: {c}")

            ig_token = Secrets.ig_token()
            ig_id = Secrets.ig_account_id()
            if ig_token and ig_id:
                ig = InstagramCollector(ig_token, ig_id)
                count = fetch_and_store_ig(ig, limit=50)
                results.append(f"Instagram: {count}")

            logger.info(f"[API/fetch] Done: {results}")
        except Exception as exc:
            logger.error(f"[API/fetch] Failed: {exc}", exc_info=True)

    background_tasks.add_task(_do_fetch)
    return ActionResponse(success=True, message="資料抓取已在背景啟動，約 1-2 分鐘完成")


@app.post("/actions/analyze", response_model=ActionResponse, tags=["Actions"])
def action_analyze(
    background_tasks: BackgroundTasks,
    api_key: str = Security(API_KEY_HEADER),
):
    """
    立即觸發 Claude AI 週分析（競品分析 + 自家帳號 + 內容行事曆）。
    在背景執行，約 2-3 分鐘完成。
    """
    require_api_key(api_key)

    def _do_analyze():
        _init()
        try:
            from analysis.content_advisor import run_full_weekly_analysis
            from config.settings import AppSettings
            result = run_full_weekly_analysis(
                brand_tone=AppSettings.brand_tone(),
                post_target=int(AppSettings.get("post_target", "5")),
            )
            logger.info("[API/analyze] Weekly analysis complete")
        except Exception as exc:
            logger.error(f"[API/analyze] Failed: {exc}", exc_info=True)

    background_tasks.add_task(_do_analyze)
    return ActionResponse(success=True, message="AI 分析已在背景啟動，約 2-3 分鐘完成")


@app.post("/actions/report", response_model=ActionResponse, tags=["Actions"])
def action_report(
    background_tasks: BackgroundTasks,
    api_key: str = Security(API_KEY_HEADER),
):
    """
    立即生成 PDF 週報並寄出 Email。
    在背景執行，完成後寄至設定的收件信箱。
    """
    require_api_key(api_key)

    def _do_report():
        _init()
        try:
            from reports.weekly_report import generate_and_send_weekly_report
            result = generate_and_send_weekly_report()
            if result.get("success"):
                logger.info(f"[API/report] PDF: {result['pdf_path']} | Email: {result['email_sent']}")
            else:
                logger.error(f"[API/report] Failed: {result.get('error')}")
        except Exception as exc:
            logger.error(f"[API/report] Failed: {exc}", exc_info=True)

    background_tasks.add_task(_do_report)
    return ActionResponse(success=True, message="週報生成已在背景啟動，完成後將自動寄出")


@app.post("/actions/hashtags", tags=["Actions"])
def action_hashtags(
    body: HashtagRequest,
    api_key: str = Security(API_KEY_HEADER),
):
    """
    即時生成指定貼文的 hashtag 建議（同步執行）。

    Body:
        topic: 貼文主題
        post_type: 圖文 / Reels / 輪播 / 純文字
        platform: Instagram / Threads / 兩者
        brand_tone: 品牌語氣（選填）
    """
    require_api_key(api_key)
    _init()
    try:
        from analysis.content_advisor import suggest_hashtags
        result = suggest_hashtags(
            topic=body.topic,
            post_type=body.post_type,
            platform=body.platform,
            brand_tone=body.brand_tone,
        )
        if "error" in result:
            raise HTTPException(status_code=502, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/data/posts", tags=["Data"])
def data_posts(
    platform: str = None,
    account_type: str = None,
    limit: int = 20,
    api_key: str = Security(API_KEY_HEADER),
):
    """
    查詢資料庫中的貼文紀錄。

    Query params:
        platform: threads / instagram（選填）
        account_type: own / competitor（選填）
        limit: 筆數（預設 20，最多 100）
    """
    require_api_key(api_key)
    _init()
    try:
        from db.database import get_accounts, get_posts
        limit = min(limit, 100)
        accounts = get_accounts(platform=platform, account_type=account_type)
        posts = []
        for acc in accounts:
            acc_posts = get_posts(account_id=acc["id"], limit=limit)
            for p in acc_posts:
                p["account_username"] = acc["username"]
                p["account_type"] = acc["account_type"]
            posts.extend(acc_posts)
        posts.sort(key=lambda x: x.get("published_at") or "", reverse=True)
        return {"count": len(posts[:limit]), "posts": posts[:limit]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/data/competitors", tags=["Data"])
def data_competitors(api_key: str = Security(API_KEY_HEADER)):
    """列出目前監控中的競品帳號清單。"""
    require_api_key(api_key)
    _init()
    try:
        from config.settings import AppSettings
        competitors = AppSettings.competitor_accounts()
        return {"count": len(competitors), "competitors": competitors}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/data/analysis/{analysis_type}", tags=["Data"])
def data_analysis(
    analysis_type: str,
    api_key: str = Security(API_KEY_HEADER),
):
    """
    取得最新的 AI 分析結果。

    analysis_type:
        competitor       競品分析
        own_account      自家帳號分析
        content_calendar 內容行事曆
        weekly_report    週報摘要
    """
    require_api_key(api_key)
    valid_types = {"competitor", "own_account", "content_calendar", "weekly_report"}
    if analysis_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"analysis_type 必須是：{valid_types}")
    _init()
    try:
        import json
        from db.database import get_latest_analysis
        row = get_latest_analysis(analysis_type)
        if not row:
            return {"found": False, "message": "尚無分析結果，請先執行 POST /actions/analyze"}
        result = json.loads(row["result_json"]) if row.get("result_json") else {}
        return {
            "found": True,
            "analysis_type": analysis_type,
            "created_at": row.get("created_at"),
            "summary": row.get("summary_text"),
            "data": result,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Brand Agent REST API")
    parser.add_argument("--port", type=int, default=8502)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    print(f"\n Brand Content Strategy Agent API")
    print(f" URL:  http://localhost:{args.port}")
    print(f" Docs: http://localhost:{args.port}/docs")
    key = _get_configured_key()
    print(f" Auth: {'X-API-Key 已設定' if key else '未設定（開放存取，建議設定 API_SECRET 環境變數）'}")
    print()

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
