"""
Threads API collector.
Fetches public posts and engagement metrics from Threads accounts
using the official Meta Threads API (v1.0+).

Docs: https://developers.facebook.com/docs/threads
"""

import json
import time
import logging
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

THREADS_BASE_URL = "https://graph.threads.net/v1.0"

# Fields to request for each post
POST_FIELDS = (
    "id,text,media_type,media_url,permalink,timestamp,"
    "like_count,replies_count,reposts_count,quotes_count"
)

# Fields for account profile
ACCOUNT_FIELDS = "id,username,name,threads_profile_picture_url,threads_biography,followers_count"


class ThreadsAPIError(Exception):
    """Raised when the Threads API returns an error response."""
    def __init__(self, message: str, status_code: int = None, error_code: int = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class ThreadsCollector:
    """
    Collects posts and metrics from Threads accounts via the official API.
    Supports both own-account (authenticated) and public account (basic) access.
    """

    def __init__(self, access_token: str):
        if not access_token:
            raise ValueError("Threads access token is required.")
        self.access_token = access_token
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def _get(self, endpoint: str, params: dict = None, retries: int = 3) -> dict:
        url = f"{THREADS_BASE_URL}/{endpoint}"
        params = params or {}
        params["access_token"] = self.access_token

        for attempt in range(retries):
            try:
                resp = self.session.get(url, params=params, timeout=30)
            except requests.RequestException as exc:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise ThreadsAPIError(f"Network error: {exc}")

            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 60))
                logger.warning(f"[Threads] Rate limited. Waiting {wait}s …")
                time.sleep(wait)
                continue

            if resp.status_code == 401:
                raise ThreadsAPIError("授權碼無效或已過期", status_code=401)

            if resp.status_code == 403:
                raise ThreadsAPIError("帳號權限不足", status_code=403)

            if not resp.ok:
                try:
                    err = resp.json().get("error", {})
                    msg = err.get("message", resp.text)
                    code = err.get("code")
                except Exception:
                    msg, code = resp.text, None
                raise ThreadsAPIError(msg, status_code=resp.status_code, error_code=code)

            return resp.json()

        raise ThreadsAPIError("Max retries exceeded")

    def get_own_profile(self) -> dict:
        """Fetch the authenticated user's own Threads profile."""
        data = self._get("me", {"fields": ACCOUNT_FIELDS})
        return self._normalize_profile(data)

    def get_own_threads(self, limit: int = 50) -> list[dict]:
        """Fetch posts from the authenticated account's Threads feed."""
        data = self._get("me/threads", {
            "fields": POST_FIELDS,
            "limit": min(limit, 100),
        })
        posts = []
        while True:
            posts.extend(data.get("data", []))
            if len(posts) >= limit:
                break
            next_cursor = data.get("paging", {}).get("cursors", {}).get("after")
            if not next_cursor:
                break
            data = self._get("me/threads", {
                "fields": POST_FIELDS,
                "limit": min(limit - len(posts), 100),
                "after": next_cursor,
            })
        return [self._normalize_post(p) for p in posts[:limit]]

    def get_user_profile(self, user_id: str) -> dict:
        """Fetch a public user's Threads profile by user ID."""
        data = self._get(user_id, {"fields": "id,username,name,followers_count"})
        return self._normalize_profile(data)

    def get_user_threads(self, user_id: str, limit: int = 50) -> list[dict]:
        """Fetch recent posts from a public Threads account by user ID."""
        data = self._get(f"{user_id}/threads", {
            "fields": POST_FIELDS,
            "limit": min(limit, 100),
        })
        posts = []
        while True:
            posts.extend(data.get("data", []))
            if len(posts) >= limit:
                break
            next_cursor = data.get("paging", {}).get("cursors", {}).get("after")
            if not next_cursor:
                break
            data = self._get(f"{user_id}/threads", {
                "fields": POST_FIELDS,
                "limit": min(limit - len(posts), 100),
                "after": next_cursor,
            })
        return [self._normalize_post(p) for p in posts[:limit]]

    def get_post_insights(self, post_id: str) -> dict:
        """Fetch engagement insights for a single post (own account only)."""
        try:
            data = self._get(f"{post_id}/insights", {
                "metric": "likes,replies,reposts,quotes,views"
            })
            insights = {}
            for item in data.get("data", []):
                insights[item["name"]] = item.get("values", [{}])[0].get("value", 0)
            return insights
        except ThreadsAPIError as exc:
            logger.warning(f"[Threads] Could not fetch insights for {post_id}: {exc}")
            return {}

    def test_connection(self) -> tuple[bool, str]:
        """
        Test if the access token is valid.
        Returns (success: bool, message: str).
        """
        try:
            profile = self.get_own_profile()
            username = profile.get("username", "unknown")
            return True, f"✅ 連接成功！已連接帳號：@{username}"
        except ThreadsAPIError as exc:
            if exc.status_code == 401:
                return False, "❌ 授權碼輸入錯誤，請重新複製貼上，注意不要有多餘空格"
            if exc.status_code == 403:
                return False, "❌ 您的帳號尚未開啟必要權限，請點「查看教學」重新設定"
            if exc.status_code == 429:
                return False, "⏳ 系統請求太頻繁，請等待 5 分鐘後再試"
            return False, f"🌐 網路連線異常，請確認您的網路後重試"

    # ── Normalization helpers ─────────────────────────────────────────────────

    @staticmethod
    def _normalize_profile(raw: dict) -> dict:
        return {
            "platform": "threads",
            "account_id": raw.get("id"),
            "username": raw.get("username", ""),
            "display_name": raw.get("name", ""),
            "follower_count": raw.get("followers_count", 0),
            "bio": raw.get("threads_biography", ""),
        }

    @staticmethod
    def _normalize_post(raw: dict) -> dict:
        hashtags = []
        text = raw.get("text") or ""
        if text:
            hashtags = [w.lstrip("#") for w in text.split() if w.startswith("#")]

        published_at = raw.get("timestamp", "")
        if published_at and published_at.endswith("Z"):
            published_at = published_at[:-1] + "+00:00"

        return {
            "platform": "threads",
            "post_id": raw.get("id"),
            "post_type": raw.get("media_type", "TEXT").lower(),
            "content": text,
            "media_url": raw.get("media_url", ""),
            "permalink": raw.get("permalink", ""),
            "hashtags": json.dumps(hashtags),
            "published_at": published_at,
            "like_count": raw.get("like_count", 0) or 0,
            "comment_count": raw.get("replies_count", 0) or 0,
            "share_count": (raw.get("reposts_count", 0) or 0) + (raw.get("quotes_count", 0) or 0),
            "reply_count": raw.get("replies_count", 0) or 0,
        }


# ── High-level fetch-and-store function ───────────────────────────────────────

def fetch_and_store_competitor(
    collector: ThreadsCollector,
    username: str,
    user_id: str,
    limit: int = 50,
) -> int:
    """
    Fetch latest posts from a competitor account and persist to SQLite.
    Returns number of posts stored.
    """
    from db.database import upsert_account, upsert_post, upsert_metric

    logger.info(f"[Threads] Fetching @{username} ({user_id}) …")
    profile = collector.get_user_profile(user_id)
    db_account_id = upsert_account(
        platform="threads",
        account_type="competitor",
        username=username,
        account_id=profile["account_id"],
        display_name=profile["display_name"],
        follower_count=profile["follower_count"],
    )

    posts = collector.get_user_threads(user_id, limit=limit)
    stored = 0
    for post in posts:
        total_engage = post["like_count"] + post["comment_count"] + post["share_count"]
        followers = profile["follower_count"] or 1
        engagement_rate = round((total_engage / followers) * 100, 4)
        upsert_post(
            platform="threads",
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
            share_count=post["share_count"],
            reply_count=post["reply_count"],
            engagement_rate=engagement_rate,
        )
        stored += 1

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    upsert_metric(
        account_id=db_account_id,
        metric_date=today,
        follower_count=profile["follower_count"],
        post_count=len(posts),
    )

    logger.info(f"[Threads] Stored {stored} posts for @{username}")
    return stored


def fetch_and_store_own(collector: ThreadsCollector, limit: int = 50) -> int:
    """Fetch own account posts and store them."""
    from db.database import upsert_account, upsert_post, upsert_metric

    profile = collector.get_own_profile()
    db_account_id = upsert_account(
        platform="threads",
        account_type="own",
        username=profile["username"],
        account_id=profile["account_id"],
        display_name=profile["display_name"],
        follower_count=profile["follower_count"],
    )

    posts = collector.get_own_threads(limit=limit)
    stored = 0
    for post in posts:
        total_engage = post["like_count"] + post["comment_count"] + post["share_count"]
        followers = profile["follower_count"] or 1
        engagement_rate = round((total_engage / followers) * 100, 4)

        # Enrich with post-level insights
        insights = collector.get_post_insights(post["post_id"])
        reach = insights.get("views", 0)

        upsert_post(
            platform="threads",
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
            share_count=post["share_count"],
            reply_count=post["reply_count"],
            reach=reach,
            engagement_rate=engagement_rate,
        )
        stored += 1

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    upsert_metric(
        account_id=db_account_id,
        metric_date=today,
        follower_count=profile["follower_count"],
        post_count=len(posts),
    )

    logger.info(f"[Threads] Stored {stored} own posts for @{profile['username']}")
    return stored
