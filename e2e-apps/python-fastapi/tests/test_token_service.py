from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.token_service import TokenBundle, refresh_access_token


def test_refresh_access_token_skips_refresh_when_token_is_still_valid() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    bundle = TokenBundle(
        access_token="current-access",
        refresh_token="refresh-me",
        expires_at=now + timedelta(minutes=10),
    )
    refresh_calls: list[str] = []

    refreshed = refresh_access_token(
        bundle,
        lambda refresh_token: refresh_calls.append(refresh_token) or {},
        now=now,
    )

    assert refreshed == bundle
    assert refreshed is not bundle
    assert refresh_calls == []


def test_refresh_access_token_refreshes_expiring_token_and_preserves_refresh_token() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    bundle = TokenBundle(
        access_token="current-access",
        refresh_token=" refresh-me ",
        expires_at=now + timedelta(seconds=20),
    )

    refreshed = refresh_access_token(
        bundle,
        lambda refresh_token: {
            "access_token": f"{refresh_token}-next",
            "expires_in": 120,
        },
        now=now,
    )

    assert refreshed.access_token == "refresh-me-next"
    assert refreshed.refresh_token == "refresh-me"
    assert refreshed.expires_at == now + timedelta(seconds=120)
    assert bundle.access_token == "current-access"
    assert bundle.refresh_token == " refresh-me "


def test_refresh_access_token_requires_refresh_token_when_refresh_is_needed() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    bundle = TokenBundle(
        access_token="current-access",
        refresh_token="   ",
        expires_at=now + timedelta(seconds=5),
    )

    with pytest.raises(ValueError, match="refresh_token_required"):
        refresh_access_token(bundle, lambda _refresh_token: {}, now=now)


def test_refresh_access_token_rejects_invalid_refresh_response() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    bundle = TokenBundle(
        access_token="current-access",
        refresh_token="refresh-me",
        expires_at=now - timedelta(seconds=1),
    )

    with pytest.raises(ValueError, match="access_token_required"):
        refresh_access_token(bundle, lambda _refresh_token: {"expires_in": 60}, now=now)


def test_refresh_access_token_uses_existing_expiry_when_provider_omits_lifetime() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    original_expiry = now + timedelta(seconds=15)
    bundle = TokenBundle(
        access_token="current-access",
        refresh_token="refresh-me",
        expires_at=original_expiry,
    )

    refreshed = refresh_access_token(
        bundle,
        lambda _refresh_token: {
            "access_token": "updated-access",
            "refresh_token": "",
        },
        now=now,
    )

    assert refreshed.access_token == "updated-access"
    assert refreshed.refresh_token == "refresh-me"
    assert refreshed.expires_at == original_expiry


def test_refresh_access_token_uses_provider_expiry_when_available() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    original_expiry = now + timedelta(seconds=15)
    refreshed_expiry = now + timedelta(minutes=5)
    bundle = TokenBundle(
        access_token="current-access",
        refresh_token="refresh-me",
        expires_at=original_expiry,
    )

    refreshed = refresh_access_token(
        bundle,
        lambda _refresh_token: {
            "access_token": "updated-access",
            "expires_at": refreshed_expiry,
        },
        now=now,
    )

    assert refreshed.access_token == "updated-access"
    assert refreshed.refresh_token == "refresh-me"
    assert refreshed.expires_at == refreshed_expiry
