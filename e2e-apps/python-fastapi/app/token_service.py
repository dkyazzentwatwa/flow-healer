from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(slots=True)
class TokenBundle:
    access_token: str
    refresh_token: str
    expires_at: datetime


def refresh_access_token(
    bundle: TokenBundle,
    refresh: Callable[[str], Mapping[str, object]],
    *,
    now: datetime | None = None,
    min_ttl_seconds: int = 30,
) -> TokenBundle:
    current_time = _normalize_now(now)
    if _seconds_until_expiry(bundle.expires_at, current_time) > min_ttl_seconds:
        return TokenBundle(
            access_token=bundle.access_token,
            refresh_token=bundle.refresh_token,
            expires_at=bundle.expires_at,
        )

    refresh_token = _normalize_text(bundle.refresh_token)
    if refresh_token is None:
        raise ValueError("refresh_token_required")

    refreshed = refresh(refresh_token)
    access_token = _normalize_text(refreshed.get("access_token"))
    if access_token is None:
        raise ValueError("access_token_required")

    next_refresh_token = _normalize_text(refreshed.get("refresh_token")) or refresh_token
    expires_at = _resolve_expiry(
        refreshed.get("expires_at"),
        refreshed.get("expires_in"),
        current_time,
        fallback=bundle.expires_at,
    )
    return TokenBundle(
        access_token=access_token,
        refresh_token=next_refresh_token,
        expires_at=expires_at,
    )


def _normalize_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now


def _seconds_until_expiry(expires_at: datetime, now: datetime) -> float:
    normalized_expiry = expires_at.replace(tzinfo=UTC) if expires_at.tzinfo is None else expires_at
    return (normalized_expiry - now).total_seconds()


def _normalize_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip()
    return normalized or None


def _resolve_expiry(
    raw_expires_at: object,
    raw_expires_in: object,
    now: datetime,
    *,
    fallback: datetime,
) -> datetime:
    if isinstance(raw_expires_at, datetime):
        if raw_expires_at.tzinfo is None:
            return raw_expires_at.replace(tzinfo=UTC)
        return raw_expires_at

    if raw_expires_in is None:
        return fallback

    try:
        expires_in = int(raw_expires_in)
    except (TypeError, ValueError):
        return fallback

    if expires_in < 0:
        return fallback
    return now + timedelta(seconds=expires_in)
