"""OAuth token store keyed by Clerk user ID.

Tokens are encrypted at rest using Fernet symmetric encryption.
Key is loaded from OAUTH_ENCRYPTION_KEY env var. If absent, an ephemeral key
is generated (tokens are lost on restart).

Credentials are persisted to CREDENTIAL_STORE_PATH (default /app/data/creds.json)
so they survive container restarts.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

_logger = logging.getLogger("experimentiq.oauth_store")

# ── Encryption ────────────────────────────────────────────────────────────────

def _get_fernet() -> Fernet:
    """Return a Fernet cipher using the configured encryption key.

    In production, OAUTH_ENCRYPTION_KEY must be set to a URL-safe base64
    32-byte key (generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())").

    In development, an ephemeral key is generated automatically. Tokens will
    not survive a server restart, which is fine for demo use.
    """
    key = os.getenv("OAUTH_ENCRYPTION_KEY", "").strip()
    if not key:
        key = Fernet.generate_key().decode()
        os.environ["OAUTH_ENCRYPTION_KEY"] = key
        _logger.warning(
            "OAUTH_ENCRYPTION_KEY not set — using an ephemeral encryption key. "
            "OAuth tokens will not survive server restarts. "
            "Set OAUTH_ENCRYPTION_KEY in production."
        )
    return Fernet(key.encode())


def _encrypt(value: str) -> bytes:
    return _get_fernet().encrypt(value.encode())


def _decrypt(token_bytes: bytes) -> str:
    try:
        return _get_fernet().decrypt(token_bytes).decode()
    except InvalidToken as exc:
        raise ValueError("Failed to decrypt OAuth token — key may have changed.") from exc


# ── Token Store ───────────────────────────────────────────────────────────────

@dataclass
class GA4Connection:
    _access_token_enc: bytes
    _refresh_token_enc: bytes | None
    property_id: str
    email: str = ""
    connected_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )

    @property
    def access_token(self) -> str:
        return _decrypt(self._access_token_enc)

    @property
    def refresh_token(self) -> str | None:
        if self._refresh_token_enc is None:
            return None
        return _decrypt(self._refresh_token_enc)

    @classmethod
    def create(
        cls,
        access_token: str,
        refresh_token: str | None,
        property_id: str,
        email: str = "",
    ) -> "GA4Connection":
        return cls(
            _access_token_enc=_encrypt(access_token),
            _refresh_token_enc=_encrypt(refresh_token) if refresh_token else None,
            property_id=property_id,
            email=email,
        )


_store: dict[str, GA4Connection] = {}


def save_ga4_connection(user_id: str, connection: GA4Connection) -> None:
    _store[user_id] = connection


def get_ga4_connection(user_id: str) -> GA4Connection | None:
    return _store.get(user_id)


def delete_ga4_connection(user_id: str) -> None:
    _store.pop(user_id, None)


def is_ga4_connected(user_id: str) -> bool:
    return user_id in _store


# ── Disk Persistence ─────────────────────────────────────────────────────────

_STORE_PATH = Path(os.getenv("CREDENTIAL_STORE_PATH", "/app/data/creds.json"))


def _serialize_conn(conn: "ApiKeyConnection") -> dict:
    return {
        "platform": conn.platform,
        "api_key_enc": base64.b64encode(conn._api_key_enc).decode(),
        "secret_enc": base64.b64encode(conn._secret_enc).decode() if conn._secret_enc else None,
        "extra": conn.extra,
        "connected_at": conn.connected_at,
    }


def _deserialize_conn(data: dict) -> "ApiKeyConnection":
    return ApiKeyConnection(
        platform=data["platform"],
        _api_key_enc=base64.b64decode(data["api_key_enc"]),
        _secret_enc=base64.b64decode(data["secret_enc"]) if data.get("secret_enc") else None,
        extra=data.get("extra", {}),
        connected_at=data.get("connected_at", datetime.now(tz=timezone.utc).isoformat()),
    )


def _save_stores() -> None:
    try:
        _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "platform_store": {
                uid: {p: _serialize_conn(c) for p, c in conns.items()}
                for uid, conns in _platform_store.items()
            },
            "exp_platform_store": {
                uid: {p: _serialize_conn(c) for p, c in conns.items()}
                for uid, conns in _exp_platform_store.items()
            },
        }
        _STORE_PATH.write_text(json.dumps(data))
    except Exception as exc:
        _logger.warning("Failed to persist credential store: %s", exc)


def _load_stores() -> None:
    try:
        if not _STORE_PATH.exists():
            return
        data = json.loads(_STORE_PATH.read_text())
        for uid, conns in data.get("platform_store", {}).items():
            _platform_store[uid] = {p: _deserialize_conn(c) for p, c in conns.items()}
        for uid, conns in data.get("exp_platform_store", {}).items():
            _exp_platform_store[uid] = {p: _deserialize_conn(c) for p, c in conns.items()}
        _logger.info("Loaded credential store from %s", _STORE_PATH)
    except Exception as exc:
        _logger.warning("Failed to load credential store: %s", exc)


# ── API Key Connections (Amplitude, Mixpanel, etc.) ───────────────────────────

@dataclass
class ApiKeyConnection:
    """Generic API key connection for platforms that don't use OAuth."""
    platform: str
    _api_key_enc: bytes
    _secret_enc: bytes | None
    extra: dict = field(default_factory=dict)
    connected_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )

    @property
    def api_key(self) -> str:
        return _decrypt(self._api_key_enc)

    @property
    def secret(self) -> str | None:
        if self._secret_enc is None:
            return None
        return _decrypt(self._secret_enc)

    @classmethod
    def create(
        cls,
        platform: str,
        api_key: str,
        secret: str | None = None,
        extra: dict | None = None,
    ) -> "ApiKeyConnection":
        return cls(
            platform=platform,
            _api_key_enc=_encrypt(api_key),
            _secret_enc=_encrypt(secret) if secret else None,
            extra=extra or {},
        )


# platform_store[user_id][platform] = ApiKeyConnection
_platform_store: dict[str, dict[str, ApiKeyConnection]] = {}


def save_platform_connection(user_id: str, conn: ApiKeyConnection) -> None:
    _platform_store.setdefault(user_id, {})[conn.platform] = conn
    _save_stores()


def get_platform_connection(user_id: str, platform: str) -> ApiKeyConnection | None:
    return _platform_store.get(user_id, {}).get(platform)


def delete_platform_connection(user_id: str, platform: str) -> None:
    _platform_store.get(user_id, {}).pop(platform, None)
    _save_stores()


def list_platform_connections(user_id: str) -> dict[str, str]:
    """Return a dict of platform -> connected_at for all connected platforms."""
    return {
        platform: conn.connected_at
        for platform, conn in _platform_store.get(user_id, {}).items()
    }


# ── Experiment Platform Connections (LaunchDarkly, Statsig) ──────────────────
# Separate namespace from analytics connections.

_exp_platform_store: dict[str, dict[str, ApiKeyConnection]] = {}


def save_exp_platform_connection(user_id: str, conn: ApiKeyConnection) -> None:
    _exp_platform_store.setdefault(user_id, {})[conn.platform] = conn
    _save_stores()


def get_exp_platform_connection(user_id: str, platform: str) -> ApiKeyConnection | None:
    return _exp_platform_store.get(user_id, {}).get(platform)


def delete_exp_platform_connection(user_id: str, platform: str) -> None:
    _exp_platform_store.get(user_id, {}).pop(platform, None)
    _save_stores()


def list_exp_platform_connections(user_id: str) -> dict[str, str]:
    """Return platform -> connected_at for all connected experiment platforms."""
    return {
        platform: conn.connected_at
        for platform, conn in _exp_platform_store.get(user_id, {}).items()
    }


# Load persisted credentials on startup
_load_stores()

# ── OAuth State Nonces ────────────────────────────────────────────────────────
# The state parameter in the OAuth flow is a server-issued nonce that maps to
# a user_id. This prevents an attacker from crafting a callback with an
# arbitrary state value to hijack another user's GA4 connection.

NONCE_TTL_SECONDS: int = 600  # 10 minutes

_nonce_store: dict[str, tuple[str, datetime]] = {}  # nonce -> (user_id, expires_at)


def create_oauth_nonce(user_id: str) -> str:
    """Generate a one-time state nonce tied to the given user_id."""
    nonce = secrets.token_urlsafe(32)
    expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=NONCE_TTL_SECONDS)
    _nonce_store[nonce] = (user_id, expires_at)
    return nonce


def consume_oauth_nonce(nonce: str) -> str | None:
    """Validate and consume a nonce. Returns the user_id or None if invalid/expired.

    The nonce is deleted on first use — replay attacks return None.
    """
    _purge_expired_nonces()
    entry = _nonce_store.pop(nonce, None)
    if entry is None:
        return None
    user_id, expires_at = entry
    if datetime.now(tz=timezone.utc) > expires_at:
        return None
    return user_id


def _purge_expired_nonces() -> None:
    """Remove expired nonces to prevent unbounded memory growth."""
    now = datetime.now(tz=timezone.utc)
    expired = [k for k, (_, exp) in _nonce_store.items() if now > exp]
    for k in expired:
        del _nonce_store[k]
