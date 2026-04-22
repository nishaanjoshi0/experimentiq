"""Shared API utilities for ExperimentIQ route modules."""

from __future__ import annotations

import hashlib


def hash_value(value: str) -> str:
    """Return a SHA-256 hash for safe request logging."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
