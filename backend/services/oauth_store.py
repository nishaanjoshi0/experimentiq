"""In-memory GA4 OAuth token store keyed by Clerk user ID.

Not persisted — tokens are lost on server restart, which is fine for demo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class GA4Connection:
    access_token: str
    refresh_token: str | None
    property_id: str
    email: str = ""
    connected_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
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
