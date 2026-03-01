"""
Instagram Graph API collector.
Fetches own-account insights, post performance, and audience metrics
for Instagram Business / Creator accounts.

Docs: https://developers.facebook.com/docs/instagram-api
"""

import json
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

IG_BASE_URL = "https://graph.facebook.com/v21.0"

# Media fields for post listing
MEDIA_FIELDS = (
    "id,caption,media_type,media_url,permalink,thumbnail_url,"
    "timestamp,like_count,comments_count"
)

# Insights metrics available per post
POST_INSIGHT_METRICS = "reach,impressions,engagement,saved,video_views"

# Account-level insight metrics
ACCOUNT_INSIGHT_METRICS = [
    "impressions", "reach", "follower_count",
    "profile_views", "website_clicks",
]


class InstagramAPIError(Exception):
    def __init__(self, message: str, status_code: int = None, error_code: int = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class InstagramCollector:
    """
    Collects posts and insights from an Instagram Business account
    via the official Instagram Graph API.
    """

    def __init__(self, access_token: str, ig_account_id: str):
        if not access_token:
            raise ValueError("Instagram access token is required.")
        if not ig_account_id:
            raise ValueError("Instagram account ID is required.")
        self.access_token = access_token
        self.ig_account_id = ig_account_id
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def _get(self, endpoint: str, params: dict = None, retries: int = 3) -> dict:
        url = f"{IG_BASE_URL}/{endpoint}"
        params = params or {}
        params["access_token"] = self.access_token

        for attempt in range(retries):
            try:
                resp = self.session.get(url, params=params, timeout=30)
            except requests.RequestException as exc:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise InstagramAPIError(f"Network error: {exc}")

            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 60))
                logger.warning(f"[Instagram] Rate limited. Waiting {wait}s …")
                time.sleep(wait)
                continue

            if resp.status_code == 401:
                raise InstagramAPIError("授權碼無效或已過期", status_code=401)

            if resp.status_code == 403:
                raise InstagramAPIError("帳號權限不足", status_code=403)

            if not resp.ok:
                try:
                    err = resp.json().get("error", {})
                    msg = err.get("message", resp.text)
                    code = err.get("code")
                except Exception:
                    msg, code = resp.text, None
                raise InstagramAPIError(msg, status_code=resp.status_code, error_code=code)

            return resp.json()

        raise InstagramAPIError("Max retries exceeded")

    def get_account_info(self) -> dict:
        """Fetch basic profile info for the IG business account."""
        data = self._get(self.ig_account_id, {
            "fields": "id,username,name,biography,followers_count,follows_count,"
                      "media_count,profile_picture_url,website"
        })
        return {
            "platform": "instagram",
            "account_id": data.get("id"),
            "username": data.get("username", ""),
            "display_name": data.get("name", ""),
            "follower_count": data.get("followers_count", 0),
            "follows_count": data.get("follows_count", 0),
            "media_count": data.get("media_count", 0),
            "biography": data.get("biography", ""),
            "website": data.get("website", ""),
        }

    def get_media(self, limit: int = 50) -> list[dict]:
        """Fetch recent media (posts/reels/stories) from the account."""
        data = self._get(f"{self.ig_account_id}/media", {
            "fields": MEDIA_FIELDS,
            "limit": min(limit, 100),
        })
        posts = []
        while True:
            posts.extend(data.get("data", []))
            if len(posts) >= limit:
                break
            next_url = data.get("paging", {}).get("next")
            if not next_url:
                break
            # next_url already contains access_token
            resp = self.session.get(next_url, timeout=30)
            if not resp.ok:
                break
            data = resp.json()

        return [self._normalize_post(p) for p in posts[:limit]]

    def get_post_insights(self, media_id: str, media_type: str = "IMAGE") -> dict:
        """Fetch per-post insights. Available metrics depend on media type."""
        metrics = POST_INSIGHT_METRICS
        if media_type in ("VIDEO", "REELS"):
            metrics += ",plays"
        try:
            data = self._get(f"{media_id}/insights", {"metric": metrics})
            insights = {}
            for item in data.get("data", []):
                insights[item["name"]] = item.get("values", [{}])[0].get("value", 0)
            return insights
        except InstagramAPIError as exc:
            logger.warning(f"[Instagram] Could not fetch insights for {media_id}: {exc}")
            return {}

    def get_account_insights(self, days: int = 30) -> dict:
        """
        Fetch account-level insights for the last N days.
        Returns a dict of metric_name -> list of daily values.
        """
        since = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
        until = int(datetime.now(timezone.utc).timestamp())
        results = {}
        for metric in ACCOUNT_INSIGHT_METRICS:
            try:
                data = self._get(f"{self.ig_account_id}/insights", {
                    "metric": metric,
                    "period": "day",
                    "since": since,
                    "until": until,
                })
                values = data.get("data", [{}])[0].get("values", [])
                results[metric] = [
                    {"end_time": v.get("end_time"), "value": v.get("value", 0)}
                    for v in values
                ]
            except InstagramAPIError as exc:
                logger.warning(f"[Instagram] Could not fetch {metric}: {exc}")
                results[metric] = []
        return results

    def get_audience_demographics(self) -> dict:
        """Fetch audience city, country, age, and gender breakdown."""
        result = {}
        for breakdown in ["city", "country", "age", "gender"]:
            try:
                data = self._get(f"{self.ig_account_id}/insights", {
                    "metric": "follower_demographics",
                    "period": "lifetime",
                    "breakdown": breakdown,
                })
                result[breakdown] = data.get("data", [])
            except InstagramAPIError:
                result[breakdown] = []
        return result

    def test_connection(self) -> tuple[bool, str]:
        """Test if the access token and account ID are valid."""
        try:
            info = self.get_account_info()
            username = info.get("username", "unknown")
            return True, f"✅ 連接成功！已連接帳號：@{username}"
        except InstagramAPIError as exc:
            if exc.status_code == 401:
                return False, "❌ 授權碼輸入錯誤，請重新複製貼上，注意不要有多餘空格"
            if exc.status_code == 403:
                return False, "❌ 您的帳號尚未開啟必要權限，請點「查看教學」重新設定"
            if exc.status_code == 429:
                return False, "⏳ 系統請求太頻繁，請等待 5 分鐘後再試"
            return False, "🌐 網路連線異常，請確認您的網路後重試"

    # ── Normalization ─────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_post(raw: dict) -> dict:
        caption = raw.get("caption") or ""
        hashtags = [w.lstrip("#") for w in caption.split() if w.startswith("#")]
        published_at = raw.get("timestamp", "")
        media_type = raw.get("media_type", "IMAGE").lower()
        # Normalize carousel_album -> carousel
        if media_type == "carousel_album":
            media_type = "carousel"

        return {
            "platform": "instagram",
            "post_id": raw.get("id"),
            "post_type": media_type,
            "content": caption,
            "media_url": raw.get("media_url") or raw.get("thumbnail_url", ""),
            "permalink": raw.get("permalink", ""),
            "hashtags": json.dumps(hashtags),
            "published_at": published_at,
            "like_count": raw.get("like_count", 0) or 0,
            "comment_count": raw.get("comments_count", 0) or 0,
        }


# ── High-level fetch-and-store ────────────────────────────────────────────────

def fetch_and_store_ig(collector: InstagramCollector, limit: int = 50) -> int:
    """
    Fetch own IG account posts + per-post insights, persist to SQLite.
    Returns number of posts stored.
    """
    from db.database import upsert_account, upsert_post, upsert_metric

    info = collector.get_account_info()
    db_account_id = upsert_account(
        platform="instagram",
        account_type="own",
        username=info["username"],
        account_id=info["account_id"],
        display_name=info["display_name"],
        follower_count=info["follower_count"],
    )

    posts = collector.get_media(limit=limit)
    stored = 0
    for post in posts:
        insights = collector.get_post_insights(post["post_id"], post["post_type"].upper())
        reach = insights.get("reach", 0)
        impressions = insights.get("impressions", 0)
        engagement = insights.get("engagement", 0)
        saved = insights.get("saved", 0)

        followers = info["follower_count"] or 1
        total_engage = post["like_count"] + post["comment_count"] + saved
        engagement_rate = round((total_engage / followers) * 100, 4)

        upsert_post(
            platform="instagram",
            account_id=db_account_id,
            post_id=post["post_id"],
            post_type=post["post_type"],
            content=post["content"],
            media_url=post["media_url"],
            permalink=post["permalink"],
            hashtags=post["hashtags"],
            published_at=post["published_at"],
            like_count=post["like_count"],
            comment_count=post["comment_count"],
            reach=reach,
            impressions=impressions,
            engagement_rate=engagement_rate,
        )
        stored += 1

    # Daily account metric snapshot
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    account_insights = collector.get_account_insights(days=1)
    daily_reach = sum(
        v["value"] for v in account_insights.get("reach", [])
    )
    daily_impressions = sum(
        v["value"] for v in account_insights.get("impressions", [])
    )
    upsert_metric(
        account_id=db_account_id,
        metric_date=today,
        follower_count=info["follower_count"],
        post_count=info["media_count"],
        total_reach=daily_reach,
        total_impressions=daily_impressions,
    )

    logger.info(f"[Instagram] Stored {stored} posts for @{info['username']}")
    return stored
