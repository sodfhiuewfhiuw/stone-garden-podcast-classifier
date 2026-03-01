"""
Settings management module with Fernet encryption.
All sensitive credentials (API tokens) are encrypted at rest.
Non-sensitive settings are stored in SQLite via database.set_setting().
"""

import os
import json
import base64
from pathlib import Path
from typing import Optional

# Lazily resolved — do NOT import at module level due to potential binary issues
CRYPTO_AVAILABLE: Optional[bool] = None  # None = not yet checked


def _check_crypto() -> bool:
    """Lazily test cryptography availability; cached after first call."""
    global CRYPTO_AVAILABLE
    if CRYPTO_AVAILABLE is not None:
        return CRYPTO_AVAILABLE
    try:
        # Use subprocess to safely probe cryptography without panicking this process
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "-c", "from cryptography.fernet import Fernet; Fernet.generate_key()"],
            capture_output=True, timeout=10,
        )
        CRYPTO_AVAILABLE = result.returncode == 0
    except Exception:
        CRYPTO_AVAILABLE = False
    return CRYPTO_AVAILABLE


def _get_fernet_cls():
    """Return Fernet class if available, else None."""
    if not _check_crypto():
        return None, None
    try:
        from cryptography.fernet import Fernet, InvalidToken
        return Fernet, InvalidToken
    except Exception:
        return None, None

# Paths
BASE_DIR = Path(__file__).parent.parent
SECRETS_FILE = BASE_DIR / "config" / "secrets.enc"
KEY_FILE = BASE_DIR / "config" / ".key"
DATA_DIR = BASE_DIR / "data"


def _get_or_create_key(Fernet) -> bytes:
    """Load existing Fernet key or generate a new one."""
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if KEY_FILE.exists():
        return KEY_FILE.read_bytes()
    key = Fernet.generate_key()
    KEY_FILE.write_bytes(key)
    KEY_FILE.chmod(0o600)
    return key


def load_secrets() -> dict:
    """Load and decrypt secrets from secrets.enc. Returns empty dict if not found."""
    if not SECRETS_FILE.exists():
        return {}
    Fernet, InvalidToken = _get_fernet_cls()
    if Fernet is None:
        # Fallback: plain JSON (dev only)
        try:
            return json.loads(SECRETS_FILE.read_text())
        except Exception:
            return {}
    key = _get_or_create_key(Fernet)
    fernet = Fernet(key)
    try:
        encrypted = SECRETS_FILE.read_bytes()
        decrypted = fernet.decrypt(encrypted)
        return json.loads(decrypted.decode())
    except Exception:
        return {}


def save_secrets(secrets: dict) -> None:
    """Encrypt and persist secrets to secrets.enc."""
    SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    Fernet, _ = _get_fernet_cls()
    if Fernet is None:
        SECRETS_FILE.write_text(json.dumps(secrets, ensure_ascii=False, indent=2))
        return
    key = _get_or_create_key(Fernet)
    fernet = Fernet(key)
    plaintext = json.dumps(secrets, ensure_ascii=False).encode()
    encrypted = fernet.encrypt(plaintext)
    SECRETS_FILE.write_bytes(encrypted)
    SECRETS_FILE.chmod(0o600)


def get_secret(key: str, default: str = None) -> Optional[str]:
    return load_secrets().get(key, default)


def set_secret(key: str, value: str) -> None:
    secrets = load_secrets()
    secrets[key] = value
    save_secrets(secrets)


def delete_secret(key: str) -> None:
    secrets = load_secrets()
    secrets.pop(key, None)
    save_secrets(secrets)


# ── Named accessors ───────────────────────────────────────────────────────────

class Secrets:
    """Typed accessors for all sensitive credentials."""

    THREADS_TOKEN = "threads_access_token"
    IG_TOKEN = "instagram_access_token"
    IG_ACCOUNT_ID = "instagram_account_id"
    CLAUDE_API_KEY = "claude_api_key"
    SMTP_PASSWORD = "smtp_password"

    @classmethod
    def threads_token(cls) -> Optional[str]:
        return get_secret(cls.THREADS_TOKEN)

    @classmethod
    def ig_token(cls) -> Optional[str]:
        return get_secret(cls.IG_TOKEN)

    @classmethod
    def ig_account_id(cls) -> Optional[str]:
        return get_secret(cls.IG_ACCOUNT_ID)

    @classmethod
    def claude_api_key(cls) -> Optional[str]:
        # Fall back to environment variable
        return get_secret(cls.CLAUDE_API_KEY) or os.environ.get("ANTHROPIC_API_KEY")

    @classmethod
    def smtp_password(cls) -> Optional[str]:
        return get_secret(cls.SMTP_PASSWORD)


class AppSettings:
    """Non-sensitive application settings backed by SQLite."""

    @staticmethod
    def _db():
        # Lazy import to avoid circular deps
        from db.database import get_setting, set_setting
        return get_setting, set_setting

    @classmethod
    def get(cls, key: str, default=None):
        try:
            get_setting, _ = cls._db()
            val = get_setting(key)
            return val if val is not None else default
        except Exception:
            return default

    @classmethod
    def set(cls, key: str, value) -> None:
        try:
            _, set_setting = cls._db()
            set_setting(key, str(value))
        except Exception:
            pass

    # Named settings
    REPORT_EMAIL = "report_email"
    BRAND_TONE = "brand_tone"
    SCHEDULE_HOUR = "schedule_hour"
    SMTP_HOST = "smtp_host"
    SMTP_PORT = "smtp_port"
    SMTP_USER = "smtp_user"
    COMPETITOR_ACCOUNTS = "competitor_accounts"

    @classmethod
    def report_emails(cls) -> list:
        raw = cls.get(cls.REPORT_EMAIL, "")
        return [e.strip() for e in raw.split(",") if e.strip()]

    @classmethod
    def set_report_emails(cls, emails: list) -> None:
        cls.set(cls.REPORT_EMAIL, ",".join(emails))

    @classmethod
    def competitor_accounts(cls) -> list:
        raw = cls.get(cls.COMPETITOR_ACCOUNTS, "[]")
        try:
            return json.loads(raw)
        except Exception:
            return []

    @classmethod
    def set_competitor_accounts(cls, accounts: list) -> None:
        cls.set(cls.COMPETITOR_ACCOUNTS, json.dumps(accounts))

    @classmethod
    def brand_tone(cls) -> str:
        return cls.get(cls.BRAND_TONE, "專業且親切，用詞簡潔有力")

    @classmethod
    def smtp_config(cls) -> dict:
        return {
            "host": cls.get(cls.SMTP_HOST, "smtp.gmail.com"),
            "port": int(cls.get(cls.SMTP_PORT, "587")),
            "user": cls.get(cls.SMTP_USER, ""),
            "password": Secrets.smtp_password() or "",
        }


if __name__ == "__main__":
    print("[Settings] Testing encryption...")
    set_secret("test_key", "hello_world_123")
    assert get_secret("test_key") == "hello_world_123"
    delete_secret("test_key")
    assert get_secret("test_key") is None
    print("[Settings] Encryption OK.")
