from datetime import UTC, datetime

from .extensions import db
from .models import Cookie


def _normalize_expiration(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def store_cookie(site_id: int, cookie: dict) -> Cookie:
    normalized_expiration = _normalize_expiration(cookie.get("expires_at"))

    existing_cookie = Cookie.query.filter_by(
        site_id=site_id,
        cookie_value=cookie["cookie_value"],
    ).first()

    if existing_cookie is None:
        stored_cookie = Cookie(
            site_id=site_id,
            cookie_name=cookie["cookie_name"],
            cookie_value=cookie["cookie_value"],
            expires_at=normalized_expiration,
            path=cookie.get("path", "/"),
            domain=cookie["domain"],
        )
        db.session.add(stored_cookie)
    else:
        stored_cookie = existing_cookie
        stored_cookie.cookie_value = cookie["cookie_value"]
        stored_cookie.expires_at = normalized_expiration
        stored_cookie.path = cookie.get("path", "/")
        stored_cookie.domain = cookie["domain"]

    db.session.commit()
    return stored_cookie


def get_valid_cookie(site_id: int) -> Cookie | None:
    now = datetime.now(UTC).replace(tzinfo=None)

    return (
        Cookie.query.filter(
            Cookie.site_id == site_id,
            (Cookie.expires_at.is_(None)) | (Cookie.expires_at > now),
        )
        .order_by(Cookie.expires_at.asc().nullsfirst(), Cookie.id.asc())
        .first()
    )


def get_valid_cookie_by_id(site_id: int, cookie_id: int) -> Cookie | None:
    now = datetime.now(UTC).replace(tzinfo=None)

    return (
        Cookie.query.filter(
            Cookie.id == cookie_id,
            Cookie.site_id == site_id,
            (Cookie.expires_at.is_(None)) | (Cookie.expires_at > now),
        )
        .order_by(Cookie.id.asc())
        .first()
    )


def delete_cookie(site_id: int, cookie_name: str) -> bool:
    cookie = Cookie.query.filter_by(site_id=site_id, cookie_name=cookie_name).first()
    if cookie is None:
        return False

    db.session.delete(cookie)
    db.session.commit()
    return True
