"""In-memory GA4 OAuth token store keyed by Clerk user ID.

Tokens are encrypted at rest using Fernet symmetric encryption.
Key is loaded from OAUTH_ENCRYPTION_KEY env var. If absent in development,
an ephemeral key is generated (tokens are lost on restart — acceptable for demo).

State nonces are stored server-side and validated on callback to prevent
an attacker from forging a callback with an arbitrary user_id in the state field.
"""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

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
