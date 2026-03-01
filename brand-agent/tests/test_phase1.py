"""
Phase 1 Validation Tests
Verifies: database schema, CRUD operations, settings encryption,
and Threads API data normalization (without live API calls).
Run: python -m pytest brand-agent/tests/test_phase1.py -v
"""

import sys
import os
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timezone

# Make brand-agent importable
BRAND_AGENT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BRAND_AGENT_DIR))

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def temp_data_dir(tmp_path, monkeypatch):
    """Redirect DB and secrets to a temp directory for isolation."""
    import db.database as db_module
    import config.settings as cfg_module

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Patch DB path
    monkeypatch.setattr(db_module, "DB_PATH", str(data_dir / "test.db"))

    # Patch secrets paths
    monkeypatch.setattr(cfg_module, "SECRETS_FILE", config_dir / "secrets.enc")
    monkeypatch.setattr(cfg_module, "KEY_FILE", config_dir / ".key")

    # Initialize fresh schema
    db_module.init_db()
    yield tmp_path


# ── Database Tests ────────────────────────────────────────────────────────────

class TestDatabase:

    def test_init_db_creates_tables(self):
        """init_db should create all required tables."""
        from db.database import get_connection
        conn = get_connection()
        tables = {
            row[0] for row in
            conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        conn.close()
        assert "accounts" in tables
        assert "posts" in tables
        assert "metrics" in tables
        assert "ai_analyses" in tables
        assert "settings" in tables

    def test_upsert_and_get_account(self):
        """Should insert and retrieve an account record."""
        from db.database import upsert_account, get_accounts

        account_id = upsert_account(
            platform="threads",
            account_type="competitor",
            username="test_brand",
            account_id="123456",
            display_name="Test Brand",
            follower_count=5000,
        )
        assert account_id is not None and account_id > 0

        accounts = get_accounts(platform="threads", account_type="competitor")
        assert len(accounts) == 1
        acc = accounts[0]
        assert acc["username"] == "test_brand"
        assert acc["follower_count"] == 5000
        assert acc["account_type"] == "competitor"

    def test_upsert_account_is_idempotent(self):
        """Upserting the same account twice should not create duplicates."""
        from db.database import upsert_account, get_accounts

        upsert_account("threads", "own", "my_brand", follower_count=1000)
        upsert_account("threads", "own", "my_brand", follower_count=1100)

        accounts = get_accounts(platform="threads", account_type="own")
        assert len(accounts) == 1
        assert accounts[0]["follower_count"] == 1100

    def test_upsert_and_get_post(self):
        """Should insert a post linked to an account and retrieve it."""
        from db.database import upsert_account, upsert_post, get_posts

        acc_id = upsert_account("threads", "competitor", "brand_x", account_id="999")
        post_id = upsert_post(
            platform="threads",
            account_id=acc_id,
            post_id="post_abc123",
            post_type="text",
            content="Hello #test #brand",
            hashtags=json.dumps(["test", "brand"]),
            published_at="2026-03-01T10:00:00+00:00",
            like_count=120,
            comment_count=15,
            engagement_rate=2.7,
        )
        assert post_id > 0

        posts = get_posts(account_id=acc_id)
        assert len(posts) == 1
        p = posts[0]
        assert p["post_id"] == "post_abc123"
        assert p["like_count"] == 120
        assert p["engagement_rate"] == 2.7

    def test_upsert_post_updates_on_conflict(self):
        """Upserting same post_id should update rather than duplicate."""
        from db.database import upsert_account, upsert_post, get_posts

        acc_id = upsert_account("threads", "competitor", "brand_y", account_id="888")
        upsert_post("threads", acc_id, "post_xyz", like_count=50)
        upsert_post("threads", acc_id, "post_xyz", like_count=200)

        posts = get_posts(account_id=acc_id)
        assert len(posts) == 1
        assert posts[0]["like_count"] == 200

    def test_upsert_and_get_metric(self):
        """Should store and retrieve daily metrics."""
        from db.database import upsert_account, upsert_metric, get_metrics

        acc_id = upsert_account("instagram", "own", "my_ig")
        upsert_metric(
            account_id=acc_id,
            metric_date="2026-03-01",
            follower_count=10000,
            total_reach=5000,
            post_count=3,
        )
        metrics = get_metrics(account_id=acc_id, days=7)
        assert len(metrics) == 1
        m = metrics[0]
        assert m["follower_count"] == 10000
        assert m["total_reach"] == 5000

    def test_settings_get_set(self):
        """Should persist and retrieve app settings."""
        from db.database import set_setting, get_setting

        set_setting("report_email", "test@example.com")
        assert get_setting("report_email") == "test@example.com"
        assert get_setting("nonexistent", "default") == "default"

    def test_save_and_get_analysis(self):
        """Should save an AI analysis record and retrieve the latest."""
        from db.database import save_analysis, get_latest_analysis

        row_id = save_analysis(
            analysis_type="competitor",
            result_json='{"summary": "test summary"}',
            summary_text="test summary",
        )
        assert row_id > 0

        latest = get_latest_analysis("competitor")
        assert latest is not None
        assert latest["analysis_type"] == "competitor"
        data = json.loads(latest["result_json"])
        assert data["summary"] == "test summary"

    def test_deactivate_account(self):
        """Deactivating an account should exclude it from get_accounts."""
        from db.database import upsert_account, get_accounts, deactivate_account

        upsert_account("threads", "competitor", "brand_gone")
        deactivate_account("threads", "brand_gone")

        accounts = get_accounts(platform="threads", account_type="competitor")
        assert all(a["username"] != "brand_gone" for a in accounts)

    def test_get_top_posts(self):
        """get_top_posts should return posts sorted by engagement_rate."""
        from db.database import upsert_account, upsert_post, get_top_posts

        acc_id = upsert_account("threads", "competitor", "brand_z")
        for i in range(5):
            upsert_post(
                "threads", acc_id, f"post_{i}",
                like_count=i * 10,
                engagement_rate=float(i) * 1.5,
            )
        top = get_top_posts(acc_id, limit=3)
        assert len(top) == 3
        assert top[0]["engagement_rate"] >= top[1]["engagement_rate"]


# ── Settings / Encryption Tests ───────────────────────────────────────────────

class TestSettings:

    def test_set_and_get_secret(self):
        """Should encrypt, persist, and decrypt a secret value."""
        from config.settings import set_secret, get_secret

        set_secret("threads_access_token", "EAAtest12345")
        assert get_secret("threads_access_token") == "EAAtest12345"

    def test_delete_secret(self):
        """Deleted secret should return None."""
        from config.settings import set_secret, get_secret, delete_secret

        set_secret("temp_key", "temp_value")
        delete_secret("temp_key")
        assert get_secret("temp_key") is None

    def test_missing_secret_returns_default(self):
        """Non-existent secret should return provided default."""
        from config.settings import get_secret

        assert get_secret("not_a_real_key") is None
        assert get_secret("not_a_real_key", "fallback") == "fallback"

    def test_multiple_secrets_independent(self):
        """Multiple secrets should be stored and retrieved independently."""
        from config.settings import set_secret, get_secret

        set_secret("key_a", "value_a")
        set_secret("key_b", "value_b")
        assert get_secret("key_a") == "value_a"
        assert get_secret("key_b") == "value_b"

    def test_app_settings_report_emails(self):
        """AppSettings.set/get_report_emails should work correctly."""
        from db.database import init_db
        from config.settings import AppSettings

        init_db()
        AppSettings.set_report_emails(["a@test.com", "b@test.com"])
        emails = AppSettings.report_emails()
        assert "a@test.com" in emails
        assert "b@test.com" in emails

    def test_app_settings_competitor_accounts(self):
        """Should serialize and deserialize competitor accounts as JSON."""
        from db.database import init_db
        from config.settings import AppSettings

        init_db()
        accounts = [
            {"username": "brand_x", "user_id": "111"},
            {"username": "brand_y", "user_id": "222"},
        ]
        AppSettings.set_competitor_accounts(accounts)
        retrieved = AppSettings.competitor_accounts()
        assert len(retrieved) == 2
        assert retrieved[0]["username"] == "brand_x"


# ── Threads API Normalization Tests ───────────────────────────────────────────

class TestThreadsNormalization:

    def test_normalize_post_with_hashtags(self):
        """_normalize_post should extract hashtags from text."""
        from collectors.threads_api import ThreadsCollector

        raw = {
            "id": "post_001",
            "text": "New product launch! #brand #newproduct #launch",
            "media_type": "TEXT",
            "timestamp": "2026-03-01T09:00:00Z",
            "like_count": 50,
            "replies_count": 10,
            "reposts_count": 5,
            "quotes_count": 2,
        }
        normalized = ThreadsCollector._normalize_post(raw)

        assert normalized["post_id"] == "post_001"
        assert normalized["platform"] == "threads"
        assert normalized["like_count"] == 50
        assert normalized["comment_count"] == 10
        assert normalized["share_count"] == 7  # reposts + quotes
        assert "brand" in json.loads(normalized["hashtags"])
        assert "newproduct" in json.loads(normalized["hashtags"])

    def test_normalize_post_empty_text(self):
        """_normalize_post should handle posts with no text."""
        from collectors.threads_api import ThreadsCollector

        raw = {
            "id": "post_002",
            "text": None,
            "media_type": "IMAGE",
            "timestamp": "2026-03-01T10:00:00Z",
        }
        normalized = ThreadsCollector._normalize_post(raw)
        assert normalized["content"] == ""
        assert normalized["hashtags"] == "[]"

    def test_normalize_profile(self):
        """_normalize_profile should map all fields correctly."""
        from collectors.threads_api import ThreadsCollector

        raw = {
            "id": "123456",
            "username": "my_brand",
            "name": "My Brand Official",
            "followers_count": 8500,
            "threads_biography": "Official brand account.",
        }
        profile = ThreadsCollector._normalize_profile(raw)
        assert profile["platform"] == "threads"
        assert profile["username"] == "my_brand"
        assert profile["follower_count"] == 8500

    def test_normalize_post_timestamp_format(self):
        """Timestamp with 'Z' suffix should be converted to +00:00."""
        from collectors.threads_api import ThreadsCollector

        raw = {
            "id": "post_003",
            "media_type": "TEXT",
            "timestamp": "2026-03-01T12:00:00Z",
        }
        normalized = ThreadsCollector._normalize_post(raw)
        assert normalized["published_at"].endswith("+00:00")


# ── Instagram API Normalization Tests ─────────────────────────────────────────

class TestInstagramNormalization:

    def test_normalize_post_carousel(self):
        """carousel_album media type should be normalized to 'carousel'."""
        from collectors.instagram_api import InstagramCollector

        raw = {
            "id": "ig_post_001",
            "media_type": "CAROUSEL_ALBUM",
            "caption": "Check out our new collection #fashion #style",
            "timestamp": "2026-03-01T14:00:00+0000",
            "like_count": 200,
            "comments_count": 30,
        }
        normalized = InstagramCollector._normalize_post(raw)
        assert normalized["post_type"] == "carousel"
        assert normalized["like_count"] == 200
        assert "fashion" in json.loads(normalized["hashtags"])

    def test_normalize_post_reels(self):
        """Reels media type should be normalized correctly."""
        from collectors.instagram_api import InstagramCollector

        raw = {
            "id": "ig_reel_001",
            "media_type": "VIDEO",
            "caption": "Behind the scenes #bts",
            "thumbnail_url": "https://example.com/thumb.jpg",
            "timestamp": "2026-03-01T16:00:00+0000",
            "like_count": 500,
            "comments_count": 45,
        }
        normalized = InstagramCollector._normalize_post(raw)
        assert normalized["post_type"] == "video"
        assert normalized["media_url"] == "https://example.com/thumb.jpg"


# ── Integration: Write posts to DB ────────────────────────────────────────────

class TestPhase1Integration:

    def test_full_write_and_read_flow(self):
        """Full Phase 1 flow: create account, write 50 posts, read back."""
        from db.database import upsert_account, upsert_post, get_posts, get_top_posts
        from collectors.threads_api import ThreadsCollector
        import json

        # Create competitor account
        acc_id = upsert_account(
            platform="threads",
            account_type="competitor",
            username="integration_brand",
            account_id="int_001",
            follower_count=12000,
        )

        # Simulate 50 raw posts from API
        stored_count = 0
        for i in range(50):
            raw = {
                "id": f"post_{i:04d}",
                "text": f"Test post {i} #test #brand #{i % 5}",
                "media_type": "TEXT" if i % 3 != 0 else "IMAGE",
                "timestamp": f"2026-02-{(i % 28) + 1:02d}T{(i % 24):02d}:00:00Z",
                "like_count": i * 5,
                "replies_count": i * 2,
                "reposts_count": i,
                "quotes_count": i // 2,
            }
            normalized = ThreadsCollector._normalize_post(raw)
            total_engage = normalized["like_count"] + normalized["comment_count"] + normalized["share_count"]
            engagement_rate = round((total_engage / 12000) * 100, 4)

            upsert_post(
                platform="threads",
                account_id=acc_id,
                post_id=normalized["post_id"],
                post_type=normalized["post_type"],
                content=normalized["content"],
                hashtags=normalized["hashtags"],
                published_at=normalized["published_at"],
                like_count=normalized["like_count"],
                comment_count=normalized["comment_count"],
                share_count=normalized["share_count"],
                engagement_rate=engagement_rate,
            )
            stored_count += 1

        assert stored_count == 50

        # Read back and verify
        posts = get_posts(account_id=acc_id, limit=50)
        assert len(posts) == 50

        top = get_top_posts(acc_id, limit=5)
        assert len(top) == 5
        assert top[0]["engagement_rate"] >= top[4]["engagement_rate"]

        # Verify hashtag storage
        for p in posts:
            tags = json.loads(p["hashtags"])
            assert isinstance(tags, list)

        print(f"\n[Integration] ✅ Successfully stored and verified {stored_count} posts in SQLite")
        print(f"[Integration] Top post engagement rate: {top[0]['engagement_rate']:.4f}%")


if __name__ == "__main__":
    # Run with: python brand-agent/tests/test_phase1.py
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", __file__, "-v", "--tb=short"],
        cwd=str(BRAND_AGENT_DIR.parent),
    )
    sys.exit(result.returncode)
